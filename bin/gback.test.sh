#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

TEST_DIR="${_PATH}/.gback-test.$$"
cleanup() {
    rm -rf -- "${TEST_DIR}"
}
trap cleanup EXIT
mkdir -p "${TEST_DIR}"

_fail() {
    echo "FAIL: $*" >&2
    exit 1
}

_configure_identity() {
    local repo=$1
    git -C "${repo}" config user.name gback-test
    git -C "${repo}" config user.email gback-test@example.invalid
}

_make_fixture() {
    local name=$1
    FIXTURE_REMOTE="${TEST_DIR}/${name}-remote.git"
    FIXTURE_SEED="${TEST_DIR}/${name}-seed"
    FIXTURE_WORK="${TEST_DIR}/${name}-work"
    FIXTURE_OTHER="${TEST_DIR}/${name}-other"

    git init -q --bare "${FIXTURE_REMOTE}"
    git -C "${FIXTURE_REMOTE}" symbolic-ref HEAD refs/heads/main

    git init -q "${FIXTURE_SEED}"
    _configure_identity "${FIXTURE_SEED}"
    git -C "${FIXTURE_SEED}" checkout -q -b main
    printf 'base\n' > "${FIXTURE_SEED}/tracked.txt"
    printf 'ignored.txt\n' > "${FIXTURE_SEED}/.gitignore"
    git -C "${FIXTURE_SEED}" add tracked.txt .gitignore
    git -C "${FIXTURE_SEED}" commit -q -m initial
    git -C "${FIXTURE_SEED}" remote add origin "${FIXTURE_REMOTE}"
    git -C "${FIXTURE_SEED}" push -q -u origin main

    git clone -q "${FIXTURE_REMOTE}" "${FIXTURE_WORK}"
    _configure_identity "${FIXTURE_WORK}"
    git clone -q "${FIXTURE_REMOTE}" "${FIXTURE_OTHER}"
    _configure_identity "${FIXTURE_OTHER}"

    printf 'remote update\n' > "${FIXTURE_OTHER}/remote.txt"
    git -C "${FIXTURE_OTHER}" add remote.txt
    git -C "${FIXTURE_OTHER}" commit -q -m remote-update
    git -C "${FIXTURE_OTHER}" push -q
}

_clear_local_identity() {
    local repo=$1
    git -C "${repo}" config --unset-all user.name || true
    git -C "${repo}" config --unset-all user.email || true
}

_test_clean_divergence_is_stashed() {
    _make_fixture clean-divergence
    local repo="${FIXTURE_WORK}"
    local no_identity_home="${TEST_DIR}/clean-no-identity-home"

    printf 'existing stash\n' > "${repo}/tracked.txt"
    git -C "${repo}" stash push -q -m preexisting-backup
    printf 'local commit\n' > "${repo}/local.txt"
    git -C "${repo}" add local.txt
    git -C "${repo}" commit -q -m local-side
    local local_commit
    local_commit=$(git -C "${repo}" rev-parse HEAD)
    git -C "${repo}" branch keep-me "${local_commit}"
    git -C "${repo}" tag keep-tag "${local_commit}"
    _clear_local_identity "${repo}"
    mkdir -p "${no_identity_home}"

    (
        cd "${repo}"
        HOME="${no_identity_home}" GIT_CONFIG_NOSYSTEM=1 bash "${_PATH}/gback.sh"
    ) > "${TEST_DIR}/clean-divergence.log" 2>&1 || {
        cat "${TEST_DIR}/clean-divergence.log" >&2
        _fail "gback 应成功恢复干净分叉仓库"
    }

    [[ "$(git -C "${repo}" rev-parse HEAD)" == "$(git -C "${repo}" rev-parse origin/main)" ]] \
        || _fail "HEAD 未与最新 origin/main 一致"
    [[ -z "$(git -C "${repo}" status --porcelain --ignored)" ]] \
        || _fail "gback 后工作区不干净"
    [[ "$(git -C "${repo}" rev-parse 'stash@{0}^1')" == "${local_commit}" ]] \
        || _fail "stash 未保留本地分叉提交"
    git -C "${repo}" stash list | grep -Fq 'gback backup' \
        || _fail "stash 缺少 gback 备份说明"
    git -C "${repo}" stash list | grep -Fq 'preexisting-backup' \
        || _fail "gback 不应删除原有 stash"
    git -C "${repo}" show-ref --verify --quiet refs/heads/keep-me \
        || _fail "gback 不应删除其他本地分支"
    git -C "${repo}" show-ref --verify --quiet refs/tags/keep-tag \
        || _fail "gback 不应删除其他本地标签"

    git -C "${repo}" stash branch restored-anchor stash@{0} >/dev/null 2>&1
    [[ "$(git -C "${repo}" rev-parse HEAD)" == "${local_commit}" ]] \
        || _fail "stash branch 未能恢复本地分叉提交"
}

_test_worktree_state_is_stashed() {
    _make_fixture worktree-state
    local repo="${FIXTURE_WORK}"
    local no_identity_home="${TEST_DIR}/worktree-no-identity-home"
    local original_head

    printf 'local commit\n' > "${repo}/local-commit.txt"
    git -C "${repo}" add local-commit.txt
    git -C "${repo}" commit -q -m local-side
    original_head=$(git -C "${repo}" rev-parse HEAD)
    printf 'local tracked\n' > "${repo}/tracked.txt"
    printf 'staged\n' > "${repo}/staged.txt"
    git -C "${repo}" add staged.txt
    printf 'untracked\n' > "${repo}/untracked.txt"
    printf 'ignored\n' > "${repo}/ignored.txt"
    _clear_local_identity "${repo}"
    mkdir -p "${no_identity_home}"

    (
        cd "${repo}"
        HOME="${no_identity_home}" GIT_CONFIG_NOSYSTEM=1 bash "${_PATH}/gback.sh"
    ) > "${TEST_DIR}/worktree-state.log" 2>&1 || {
        cat "${TEST_DIR}/worktree-state.log" >&2
        _fail "gback 应成功 stash 全部工作区状态"
    }

    [[ "$(git -C "${repo}" rev-parse HEAD)" == "$(git -C "${repo}" rev-parse origin/main)" ]] \
        || _fail "工作区 stash 后 HEAD 未与远程一致"
    [[ -z "$(git -C "${repo}" status --porcelain --ignored)" ]] \
        || _fail "工作区 stash 后仍有文件残留"
    [[ "$(git -C "${repo}" rev-parse 'stash@{0}^1')" == "${original_head}" ]] \
        || _fail "工作区 stash 的父提交不是原 HEAD"
    [[ "$(git -C "${repo}" show 'stash@{0}:tracked.txt')" == 'local tracked' ]] \
        || _fail "stash 未保存 tracked 修改"
    [[ "$(git -C "${repo}" show 'stash@{0}:staged.txt')" == 'staged' ]] \
        || _fail "stash 未保存 staged 文件"
    git -C "${repo}" ls-tree -r --name-only 'stash@{0}^3' | grep -Fqx 'untracked.txt' \
        || _fail "stash 未保存 untracked 文件"
    git -C "${repo}" ls-tree -r --name-only 'stash@{0}^3' | grep -Fqx 'ignored.txt' \
        || _fail "stash 未保存 ignored 文件"

    git -C "${repo}" stash branch restored-work stash@{0} >/dev/null 2>&1
    [[ "$(git -C "${repo}" rev-parse HEAD)" == "${original_head}" ]] \
        || _fail "stash branch 未恢复原 HEAD"
    [[ "$(cat "${repo}/tracked.txt")" == 'local tracked' ]] \
        || _fail "stash branch 未恢复 tracked 修改"
    [[ "$(cat "${repo}/untracked.txt")" == 'untracked' ]] \
        || _fail "stash branch 未恢复 untracked 文件"
    [[ "$(cat "${repo}/ignored.txt")" == 'ignored' ]] \
        || _fail "stash branch 未恢复 ignored 文件"
}

_test_stash_failure_aborts_reset() {
    _make_fixture stash-failure
    local repo="${FIXTURE_WORK}"
    local fake_bin="${TEST_DIR}/stash-failure-bin"
    local real_git
    local original_head

    printf 'local tracked\n' > "${repo}/tracked.txt"
    original_head=$(git -C "${repo}" rev-parse HEAD)
    real_git=$(command -v git)
    mkdir -p "${fake_bin}"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'if [[ ${1:-} == stash && (${2:-} == push || ${2:-} == save) ]]; then' \
        '    exit 1' \
        'fi' \
        "exec $(printf '%q' "${real_git}") \"\$@\"" > "${fake_bin}/git"
    chmod +x "${fake_bin}/git"

    set +e
    (
        cd "${repo}"
        PATH="${fake_bin}:${PATH}" bash "${_PATH}/gback.sh"
    ) > "${TEST_DIR}/stash-failure.log" 2>&1
    local status=$?
    set -e

    ((status != 0)) || _fail "stash 失败时 gback 应返回非零"
    [[ "$(git -C "${repo}" rev-parse HEAD)" == "${original_head}" ]] \
        || _fail "stash 失败时不应移动 HEAD"
    [[ "$(cat "${repo}/tracked.txt")" == 'local tracked' ]] \
        || _fail "stash 失败时不应覆盖工作区文件"
}

_test_legacy_stash_fallback() {
    _make_fixture legacy-stash
    local repo="${FIXTURE_WORK}"
    local fake_bin="${TEST_DIR}/legacy-stash-bin"
    local real_git

    printf 'local tracked\n' > "${repo}/tracked.txt"
    printf 'untracked\n' > "${repo}/untracked.txt"
    real_git=$(command -v git)
    mkdir -p "${fake_bin}"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'if [[ ${1:-} == stash && ${2:-} == push ]]; then' \
        '    exit 129' \
        'fi' \
        "exec $(printf '%q' "${real_git}") \"\$@\"" > "${fake_bin}/git"
    chmod +x "${fake_bin}/git"

    (
        cd "${repo}"
        PATH="${fake_bin}:${PATH}" bash "${_PATH}/gback.sh"
    ) > "${TEST_DIR}/legacy-stash.log" 2>&1 || {
        cat "${TEST_DIR}/legacy-stash.log" >&2
        _fail "旧版 Git stash save 回退失败"
    }

    [[ "$(git -C "${repo}" rev-parse HEAD)" == "$(git -C "${repo}" rev-parse origin/main)" ]] \
        || _fail "旧版 stash 回退后 HEAD 未对齐"
    [[ -z "$(git -C "${repo}" status --porcelain --ignored)" ]] \
        || _fail "旧版 stash 回退后工作区不干净"
    git -C "${repo}" stash list | grep -Fq 'gback backup' \
        || _fail "旧版 stash 回退未生成备份"
}

_test_detached_head_is_rejected() {
    local repo="${TEST_DIR}/detached-repo"
    local original_head

    git init -q "${repo}"
    _configure_identity "${repo}"
    git -C "${repo}" commit -q --allow-empty -m initial
    git -C "${repo}" checkout -q --detach HEAD
    original_head=$(git -C "${repo}" rev-parse HEAD)

    set +e
    (
        cd "${repo}"
        bash "${_PATH}/gback.sh"
    ) > "${TEST_DIR}/detached.log" 2>&1
    local status=$?
    set -e

    ((status != 0)) || _fail "detached HEAD 应被拒绝"
    grep -Fq 'HEAD 处于游离状态' "${TEST_DIR}/detached.log" \
        || _fail "detached HEAD 缺少明确错误"
    [[ "$(git -C "${repo}" rev-parse HEAD)" == "${original_head}" ]] \
        || _fail "拒绝 detached HEAD 时不应改变 HEAD"
}

main() {
    _test_clean_divergence_is_stashed
    _test_worktree_state_is_stashed
    _test_stash_failure_aborts_reset
    _test_legacy_stash_fallback
    _test_detached_head_is_rejected
}

main "$@"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
