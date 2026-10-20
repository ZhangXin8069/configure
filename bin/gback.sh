#!/usr/bin/env bash
# gback — 先 stash 本地全部分叉，再将当前分支强制对齐最新 upstream
#   · 当前分支提交、索引、工作区和 ignored 文件全部进入 stash
#   · stash 成功后清空工作区，不自动 pop，不影响对齐后的当前分支
#   · 其他本地分支与标签保持不变

_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel) || {
    echo "ERROR: 不在 git 仓库内。"
    exit 1
}
echo "Repo:    ${REPO_ROOT}"
cd "${REPO_ROOT}"

BRANCH=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)
if [[ -z "${BRANCH}" || "${BRANCH}" == "HEAD" ]]; then
    echo "ERROR: HEAD 处于游离状态，请先检出分支。"
    exit 1
fi
echo "Branch:  ${BRANCH}"

if [[ -e "$(git rev-parse --git-path MERGE_HEAD)" ]] \
    || [[ -d "$(git rev-parse --git-path rebase-merge)" ]] \
    || [[ -d "$(git rev-parse --git-path rebase-apply)" ]] \
    || [[ -e "$(git rev-parse --git-path CHERRY_PICK_HEAD)" ]] \
    || [[ -e "$(git rev-parse --git-path REVERT_HEAD)" ]]; then
    echo "ERROR: 当前仓库存在未完成的 merge/rebase/cherry-pick/revert，gback 已中止。"
    exit 1
fi

ORIGINAL_HEAD=$(git rev-parse HEAD) || {
    echo "ERROR: 无法解析当前 HEAD。"
    exit 1
}

# 只更新远程跟踪引用，不改写本地标签或其他分支。
git fetch --all --prune --no-tags || {
    echo "ERROR: git fetch 失败。"
    exit 1
}

UPSTREAM=$(git rev-parse --abbrev-ref --symbolic-full-name "${BRANCH}@{upstream}" 2>/dev/null) || {
    echo "ERROR: 分支 ${BRANCH} 无上游，无法以远程为基准。"
    exit 1
}
UPSTREAM_COMMIT=$(git rev-parse --verify "${UPSTREAM}^{commit}") || {
    echo "ERROR: 无法解析上游 ${UPSTREAM} 的最新提交。"
    exit 1
}
echo "Upstream: ${UPSTREAM} ($(git rev-parse --short "${UPSTREAM_COMMIT}"))"

_run_with_backup_identity() {
    local name
    local email

    name=$(git config --get user.name 2>/dev/null || true)
    email=$(git config --get user.email 2>/dev/null || true)
    if [[ -z "${name}" || -z "${email}" ]]; then
        name=$(git show -s --format=%an "${ORIGINAL_HEAD}" 2>/dev/null || true)
        email=$(git show -s --format=%ae "${ORIGINAL_HEAD}" 2>/dev/null || true)
    fi
    [[ -n "${name}" ]] || name=gback
    [[ -n "${email}" ]] || email=gback@localhost

    GIT_AUTHOR_NAME="${name}" GIT_AUTHOR_EMAIL="${email}" \
        GIT_COMMITTER_NAME="${name}" GIT_COMMITTER_EMAIL="${email}" "$@"
}

_worktree_has_state() {
    ! git diff --quiet \
        || ! git diff --cached --quiet \
        || [[ -n "$(git ls-files --others --exclude-standard)" ]] \
        || [[ -n "$(git ls-files --others --ignored --exclude-standard)" ]]
}

_stash_worktree() {
    local message=$1

    if _run_with_backup_identity git stash push --all --message "${message}" >/dev/null 2>&1; then
        return 0
    fi
    # Git < 2.13 uses the legacy stash save syntax.
    _run_with_backup_identity git stash save --quiet --all "${message}"
}

_create_head_anchor_stash() {
    local message=$1
    local tree
    local index_anchor
    local anchor

    tree=$(git rev-parse "${ORIGINAL_HEAD}^{tree}") || return 1
    index_anchor=$(printf '%s\n' "${message} index" | _run_with_backup_identity \
        git commit-tree "${tree}" -p "${ORIGINAL_HEAD}") || return 1
    anchor=$(printf '%s\n' "${message}" | _run_with_backup_identity \
        git commit-tree "${tree}" -p "${ORIGINAL_HEAD}" -p "${index_anchor}") || return 1
    if ! git stash store --message "${message}" "${anchor}"; then
        git update-ref -m "${message}" refs/stash "${anchor}" || return 1
    fi
}

N_STASH=$(git stash list 2>/dev/null | wc -l)
if (( N_STASH > 0 )); then
    echo "提示: 已存在 ${N_STASH} 个 stash，将保留并在其前新增本次备份。"
fi

OLD_STASH=$(git rev-parse --quiet --verify refs/stash 2>/dev/null || true)

LOCAL_HAS_EXTRA_COMMITS=0
if ! git merge-base --is-ancestor "${ORIGINAL_HEAD}" "${UPSTREAM_COMMIT}"; then
    LOCAL_HAS_EXTRA_COMMITS=1
fi

if (( LOCAL_HAS_EXTRA_COMMITS )); then
    echo "将 stash 的本地独有提交："
    git log --oneline --reverse "${UPSTREAM_COMMIT}..${ORIGINAL_HEAD}" | head -20 || true
else
    echo "本地提交均已包含于 ${UPSTREAM}。"
fi

if _worktree_has_state; then
    echo "将 stash 的工作区状态（含 staged/untracked/ignored）："
    git status --short --untracked-files=all --ignored | head -20 || true
else
    echo "工作区无本地改动。"
fi

STASH_MESSAGE="gback backup $(date "+%Y-%m-%d-%H-%M-%S") ${BRANCH} before ${UPSTREAM}"
STASH_CREATED=0
if _worktree_has_state; then
    if ! _stash_worktree "${STASH_MESSAGE}"; then
        echo "ERROR: 无法 stash 本地工作区，gback 已中止，未执行 reset。" >&2
        exit 1
    fi
    STASH_CREATED=1
fi

if (( LOCAL_HAS_EXTRA_COMMITS )) && (( STASH_CREATED == 0 )); then
    if ! _create_head_anchor_stash "${STASH_MESSAGE}"; then
        echo "ERROR: 无法为本地分叉提交创建 stash，gback 已中止，未执行 reset。" >&2
        exit 1
    fi
    STASH_CREATED=1
fi

NEW_STASH=$(git rev-parse --quiet --verify refs/stash 2>/dev/null || true)
if (( STASH_CREATED )) && [[ "${NEW_STASH}" == "${OLD_STASH}" ]]; then
    echo "ERROR: 未能创建新的 stash，gback 已中止，未执行 reset。" >&2
    exit 1
fi

STILL_DIRTY=$(git status --porcelain --ignored)
if [[ -n "${STILL_DIRTY}" ]]; then
    echo "ERROR: stash 后工作区仍不干净，gback 已中止，未执行 reset：" >&2
    echo "${STILL_DIRTY}" | head -20 >&2
    exit 1
fi

# stash 已确认成功，强制当前分支与最新 upstream 完全一致。
git reset --hard "${UPSTREAM_COMMIT}"
git clean -fdx

if (( STASH_CREATED )); then
    echo "Stash:   stash@{0} (${STASH_MESSAGE})"
    echo "恢复查看: git stash list"
    echo "恢复分支: git stash branch <new-branch> stash@{0}"
fi

STILL_DIRTY=$(git status --porcelain --ignored)
if [[ -z "${STILL_DIRTY}" ]]; then
    echo "OK: 工作区干净，包含 ignored 文件在内均与 ${UPSTREAM} 一致"
else
    echo "ERROR: reset 后工作区仍有差异：" >&2
    echo "${STILL_DIRTY}" >&2
    exit 1
fi
if [[ "$(git rev-parse HEAD)" == "${UPSTREAM_COMMIT}" ]]; then
    echo "OK: 本地 ${BRANCH} 与 ${UPSTREAM} 完全一致"
else
    echo "ERROR: 本地 ${BRANCH} 未能对齐 ${UPSTREAM}" >&2
    exit 1
fi
echo "HEAD:    $(git log --oneline -1)"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
