#!/usr/bin/env bash
# gback — 先 stash 本地全部分叉，再将当前分支强制对齐最新 upstream
#   · 当前分支提交、索引、工作区和 ignored 文件全部进入 stash
#   · 子模块指针差异会进入 stash；子模块内部有未提交状态时安全中止
#   · 未在 .gitmodules 注册的 gitlink 不参与遍历，保持原样
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
    ! git diff --quiet --ignore-submodules=none \
        || ! git diff --cached --quiet --ignore-submodules=none \
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

# 全局 submodule 命令会拒绝未注册 gitlink，因此只遍历 .gitmodules 中的显式路径。
_registered_submodule_paths() {
    local gitmodules=$1
    local record
    local path

    [[ -f "${gitmodules}" ]] || return 0
    while IFS= read -r -d '' record; do
        path=${record#*$'\n'}
        [[ -n "${path}" ]] && printf '%s\0' "${path}"
    done < <(git config --file "${gitmodules}" --get-regexp --null \
        '^submodule\..*\.path$' 2>/dev/null)
}

_initialized_submodules_are_clean() {
    local path

    while IFS= read -r -d '' path; do
        [[ -e "${path}/.git" ]] || continue
        [[ -z "$(git -C "${path}" status --porcelain --untracked-files=all --ignored \
            --ignore-submodules=none)" ]] || return 1
    done < <(_registered_submodule_paths ".gitmodules")
}

_diff_has_gitlink_state() {
    local header
    local path
    local old_mode
    local new_mode
    local old_sha
    local new_sha
    local status

    while IFS= read -r -d '' header; do
        IFS= read -r -d '' path || return 1
        read -r old_mode new_mode old_sha new_sha status <<<"${header#:}"
        [[ "${old_mode}" == 160000 || "${new_mode}" == 160000 ]] && return 0
    done < <("$@")
    return 1
}

_submodule_pointer_has_state() {
    _diff_has_gitlink_state git diff --raw --no-renames -z --ignore-submodules=none \
        || _diff_has_gitlink_state git diff --cached --raw --no-renames -z \
            --ignore-submodules=none
}

_update_initialized_submodules() {
    local -a paths=()
    local path

    while IFS= read -r -d '' path; do
        [[ -e "${path}/.git" ]] && paths+=("${path}")
    done < <(_registered_submodule_paths ".gitmodules")
    (( ${#paths[@]} == 0 )) || git submodule update --recursive --checkout -- "${paths[@]}"
}

_store_stash_anchor() {
    local message=$1
    local anchor=$2

    _run_with_backup_identity git update-ref --create-reflog \
        -m "${message}" refs/stash "${anchor}"
}

_create_anchor_stash() {
    local message=$1
    local worktree_tree=$2
    local index_tree
    local index_anchor
    local anchor

    index_tree=$(git write-tree) || return 1
    index_anchor=$(printf '%s\n' "${message} index" | _run_with_backup_identity \
        git commit-tree "${index_tree}" -p "${ORIGINAL_HEAD}") || return 1
    anchor=$(printf '%s\n' "${message}" | _run_with_backup_identity \
        git commit-tree "${worktree_tree}" -p "${ORIGINAL_HEAD}" -p "${index_anchor}") || return 1
    _store_stash_anchor "${message}" "${anchor}"
}

_create_head_anchor_stash() {
    local message=$1
    local tree

    tree=$(git rev-parse "${ORIGINAL_HEAD}^{tree}") || return 1
    _create_anchor_stash "${message}" "${tree}"
}

_create_worktree_anchor_stash() {
    local message=$1
    local git_dir
    local temp_index
    local worktree_tree

    git_dir=$(git rev-parse --git-dir) || return 1
    temp_index=$(mktemp "${git_dir}/gback-index.XXXXXX") || return 1
    rm -f -- "${temp_index}" || return 1
    if ! GIT_INDEX_FILE="${temp_index}" git read-tree "${ORIGINAL_HEAD}" \
        || ! GIT_INDEX_FILE="${temp_index}" git add --all --force; then
        rm -f -- "${temp_index}"
        return 1
    fi
    worktree_tree=$(GIT_INDEX_FILE="${temp_index}" git write-tree) || {
        rm -f -- "${temp_index}"
        return 1
    }
    rm -f -- "${temp_index}"
    _create_anchor_stash "${message}" "${worktree_tree}"
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
    git status --short --untracked-files=all --ignored --ignore-submodules=none | head -20 || true
else
    echo "工作区无本地改动。"
fi

STASH_MESSAGE="gback backup $(date "+%Y-%m-%d-%H-%M-%S") ${BRANCH} before ${UPSTREAM}"
STASH_CREATED=0
SUBMODULE_SNAPSHOT=0
if _worktree_has_state; then
    if ! _initialized_submodules_are_clean; then
        echo "ERROR: 已初始化子模块内部存在未提交状态；为避免 reset 丢数据，gback 已中止。" >&2
        exit 1
    fi
    if _submodule_pointer_has_state; then
        if ! _create_worktree_anchor_stash "${STASH_MESSAGE}"; then
            echo "ERROR: 无法保存含子模块指针的工作区快照，gback 已中止，未执行 reset。" >&2
            exit 1
        fi
        SUBMODULE_SNAPSHOT=1
    else
        if ! _stash_worktree "${STASH_MESSAGE}"; then
            echo "ERROR: 无法 stash 本地工作区，gback 已中止，未执行 reset。" >&2
            exit 1
        fi
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

if (( SUBMODULE_SNAPSHOT == 0 )); then
    STILL_DIRTY=$(git status --porcelain --ignored --ignore-submodules=none)
    if [[ -n "${STILL_DIRTY}" ]]; then
        echo "ERROR: stash 后工作区仍不干净，gback 已中止，未执行 reset：" >&2
        echo "${STILL_DIRTY}" | head -20 >&2
        exit 1
    fi
fi

# stash 已确认成功，强制当前分支与最新 upstream 完全一致。
git reset --hard "${UPSTREAM_COMMIT}" || {
    echo "ERROR: 无法将当前分支重置到 ${UPSTREAM}。" >&2
    exit 1
}
_update_initialized_submodules || {
    echo "ERROR: 无法将已初始化子模块切换到上游记录的提交。" >&2
    exit 1
}
git clean -fdx || {
    echo "ERROR: 无法清理当前工作区。" >&2
    exit 1
}

if (( STASH_CREATED )); then
    echo "Stash:   stash@{0} (${STASH_MESSAGE})"
    echo "恢复查看: git stash list"
    echo "恢复分支: git stash branch <new-branch> stash@{0}"
    if (( SUBMODULE_SNAPSHOT )); then
        echo "注意:     git stash branch 不会切换子模块；若需恢复子模块指针，请改用："
        echo "          git stash apply stash@{0}"
        echo "          git checkout stash@{0} -- <子模块路径>"
        echo "          git submodule update --init --recursive --checkout <子模块路径>"
    fi
fi

STILL_DIRTY=$(git status --porcelain --ignored --ignore-submodules=none)
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
