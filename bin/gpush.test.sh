#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

TEST_DIR="${_PATH}/.gpush-test.$$"
cleanup() {
    rm -rf -- "${TEST_DIR}"
}
trap cleanup EXIT
mkdir -p "${TEST_DIR}/bin" "${TEST_DIR}/repo"

_fail() {
    echo "FAIL: $*" >&2
    exit 1
}

cat > "${TEST_DIR}/bin/git" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${FAKE_GIT_LOG}"
case "$*" in
    "rev-parse --show-toplevel") printf '%s\n' "${FAKE_REPO_ROOT}" ;;
    "ls-files --stage -z") ;;
    "add -A -- ."|"diff --cached --quiet --ignore-submodules=all") ;;
    "symbolic-ref --quiet --short HEAD") printf 'main\n' ;;
    "rev-parse --abbrev-ref HEAD") printf 'main\n' ;;
    "push --recurse-submodules=no origin main") ;;
    "push --recurse-submodules=no origin --tags") exit 1 ;;
    *) exit 1 ;;
esac
if [[ ${1:-} == push ]]; then
    printf 'push-locale=%s/%s\n' "${LANG:-}" "${LC_ALL:-}" >> "${FAKE_GIT_LOG}"
fi
SH
chmod +x "${TEST_DIR}/bin/git"

set +e
PATH="${TEST_DIR}/bin:${PATH}" \
FAKE_GIT_LOG="${TEST_DIR}/git.log" \
FAKE_REPO_ROOT="${TEST_DIR}/repo" \
    bash "${_PATH}/gpush.sh" > "${TEST_DIR}/output.log" 2>&1
status=$?
set -e

((status != 0)) || {
    cat "${TEST_DIR}/output.log" >&2
    _fail "标签 push 失败后 gpush 仍返回 0"
}
grep -Fq 'ERROR: tag push failed' "${TEST_DIR}/output.log" || {
    cat "${TEST_DIR}/output.log" >&2
    _fail "标签 push 失败后未输出明确错误"
}
! grep -Fq "###${_NAME%.test.sh} is done" "${TEST_DIR}/output.log" || {
    cat "${TEST_DIR}/output.log" >&2
    _fail "标签 push 失败后仍打印 done"
}
grep -Fqx 'push --recurse-submodules=no origin main' "${TEST_DIR}/git.log" || {
    cat "${TEST_DIR}/git.log" >&2
    _fail "分支 push 未显式禁用子模块递归"
}
grep -Fqx 'push --recurse-submodules=no origin --tags' "${TEST_DIR}/git.log" || {
    cat "${TEST_DIR}/git.log" >&2
    _fail "标签 push 未显式禁用子模块递归"
}
grep -Fqx 'push-locale=C/C' "${TEST_DIR}/git.log" || {
    cat "${TEST_DIR}/git.log" >&2
    _fail "git push 未同时使用 POSIX LANG/LC_ALL"
}

_test_does_not_recurse_into_submodules() {
    local root="${TEST_DIR}/no-submodule-push"
    local sub_remote="${root}/sub-remote.git"
    local sub_seed="${root}/sub-seed"
    local super_remote="${root}/super-remote.git"
    local repo="${root}/super"
    local sub_one
    local sub_two
    local remote_after
    local parent_before

    mkdir -p "${root}"
    git init -q --bare "${sub_remote}"
    git -C "${sub_remote}" symbolic-ref HEAD refs/heads/main
    git init -q -b main "${sub_seed}"
    git -C "${sub_seed}" config user.name gpush-test
    git -C "${sub_seed}" config user.email gpush-test@example.invalid
    printf 'one\n' > "${sub_seed}/value.txt"
    git -C "${sub_seed}" add value.txt
    git -C "${sub_seed}" commit -q -m sub-one
    git -C "${sub_seed}" remote add origin "${sub_remote}"
    git -C "${sub_seed}" push -q -u origin main
    sub_one=$(git -C "${sub_seed}" rev-parse HEAD)

    git init -q -b main "${repo}"
    git -C "${repo}" config user.name gpush-test
    git -C "${repo}" config user.email gpush-test@example.invalid
    git -C "${repo}" -c protocol.file.allow=always \
        submodule add -q "${sub_remote}" child
    git -C "${repo}/child" config user.name gpush-test
    git -C "${repo}/child" config user.email gpush-test@example.invalid

    git init -q --bare "${super_remote}"
    git -C "${super_remote}" symbolic-ref HEAD refs/heads/main
    git -C "${repo}" add .gitmodules child
    git -C "${repo}" commit -q -m parent-one
    git -C "${repo}" remote add origin "${super_remote}"
    git -C "${repo}" push -q -u origin main

    printf 'two\n' > "${repo}/child/value.txt"
    git -C "${repo}/child" commit -q -am sub-two
    sub_two=$(git -C "${repo}/child" rev-parse HEAD)
    git -C "${repo}" config push.recurseSubmodules on-demand

    parent_before=$(git -C "${repo}" rev-parse HEAD)
    (
        cd "${repo}"
        GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null bash "${_PATH}/gpush.sh"
    ) > "${TEST_DIR}/no-submodule-push.log" 2>&1

    [[ "$(git -C "${repo}" rev-parse HEAD)" == "${parent_before}" ]] \
        || _fail "只有子模块指针变化时 gpush 不应创建父仓库提交"
    grep -Fq 'Nothing to commit.' "${TEST_DIR}/no-submodule-push.log" \
        || _fail "只有子模块指针变化时 gpush 未报告无改动"
    remote_after=$(git --git-dir="${sub_remote}" rev-parse refs/heads/main)
    [[ "${remote_after}" == "${sub_one}" ]] \
        || _fail "gpush 不应在 push.recurseSubmodules=on-demand 时推送子模块提交"
    [[ "${sub_two}" != "${sub_one}" ]] || _fail "测试夹具未创建新的子模块提交"

    printf 'parent change\n' > "${repo}/parent.txt"
    (
        cd "${repo}"
        GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null bash "${_PATH}/gpush.sh"
    ) > "${TEST_DIR}/parent-change-push.log" 2>&1
    [[ "$(git -C "${repo}" rev-parse HEAD)" != "${parent_before}" ]] \
        || _fail "父仓库普通文件变化应被 gpush 提交"
    [[ "$(git -C "${repo}" diff-tree --no-commit-id --name-only -r HEAD)" == 'parent.txt' ]] \
        || _fail "gpush 提交范围应只包含父仓库普通文件"
    [[ "$(git -C "${repo}" rev-parse HEAD:child)" == "${sub_one}" ]] \
        || _fail "gpush 不应把本地子模块 HEAD 写入父仓库新提交"

    git -C "${repo}" add child
    set +e
    (
        cd "${repo}"
        GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null bash "${_PATH}/gpush.sh"
    ) > "${TEST_DIR}/staged-submodule.log" 2>&1
    local staged_status=$?
    set -e
    ((staged_status != 0)) || _fail "已有暂存 gitlink 时 gpush 应失败"
    grep -Fq 'Staged submodule changes require an explicit submodule workflow' \
        "${TEST_DIR}/staged-submodule.log" \
        || _fail "已有暂存 gitlink 时缺少明确错误"
}

_test_commit_failure_aborts_before_push() {
    local root="${TEST_DIR}/commit-failure"
    local remote="${root}/remote.git"
    local repo="${root}/repo"
    local fake_bin="${root}/fake-bin"
    local real_git
    local parent_before
    local remote_before
    local status

    mkdir -p "${fake_bin}"
    git init -q --bare "${remote}"
    git -C "${remote}" symbolic-ref HEAD refs/heads/main
    git init -q -b main "${repo}"
    git -C "${repo}" config user.name gpush-test
    git -C "${repo}" config user.email gpush-test@example.invalid
    printf 'base\n' > "${repo}/tracked.txt"
    git -C "${repo}" add tracked.txt
    git -C "${repo}" commit -q -m initial
    git -C "${repo}" remote add origin "${remote}"
    git -C "${repo}" push -q -u origin main
    parent_before=$(git -C "${repo}" rev-parse HEAD)
    remote_before=$(git --git-dir="${remote}" rev-parse refs/heads/main)
    printf 'local update\n' > "${repo}/tracked.txt"

    real_git=$(command -v git)
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'printf "%s\n" "$*" >> "${FAKE_GIT_LOG:?}"' \
        'if [[ ${1:-} == commit ]]; then exit 1; fi' \
        "exec $(printf '%q' "${real_git}") \"\$@\"" > "${fake_bin}/git"
    chmod +x "${fake_bin}/git"

    set +e
    (
        cd "${repo}"
        PATH="${fake_bin}:${PATH}" FAKE_GIT_LOG="${root}/git.log" \
            bash "${_PATH}/gpush.sh"
    ) > "${TEST_DIR}/commit-failure.log" 2>&1
    status=$?
    set -e

    ((status != 0)) || {
        cat "${TEST_DIR}/commit-failure.log" >&2
        _fail "commit 失败后 gpush 仍返回 0"
    }
    grep -Fq 'commit failed' "${TEST_DIR}/commit-failure.log" \
        || _fail "commit 失败后缺少明确错误"
    grep -Fq 'ERROR: commit failed' "${TEST_DIR}/commit-failure.log" \
        || _fail "commit 失败后缺少 ERROR 标记"
    [[ "$(git -C "${repo}" rev-parse HEAD)" == "${parent_before}" ]] \
        || _fail "commit 失败后不应移动 HEAD"
    [[ "$(git --git-dir="${remote}" rev-parse refs/heads/main)" == "${remote_before}" ]] \
        || _fail "commit 失败后不应改变远端分支"
    ! grep -Eq '^push ' "${root}/git.log" || _fail "commit 失败后不应继续 push"
}

_test_detached_head_is_rejected() {
    local root="${TEST_DIR}/detached"
    local remote="${root}/remote.git"
    local repo="${root}/repo"
    local detached_head
    local status

    git init -q --bare "${remote}"
    git -C "${remote}" symbolic-ref HEAD refs/heads/main
    git init -q -b main "${repo}"
    git -C "${repo}" config user.name gpush-test
    git -C "${repo}" config user.email gpush-test@example.invalid
    printf 'base\n' > "${repo}/tracked.txt"
    git -C "${repo}" add tracked.txt
    git -C "${repo}" commit -q -m initial
    git -C "${repo}" remote add origin "${remote}"
    git -C "${repo}" push -q -u origin main
    git -C "${repo}" checkout -q --detach HEAD
    detached_head=$(git -C "${repo}" rev-parse HEAD)
    printf 'local update\n' > "${repo}/tracked.txt"

    set +e
    (
        cd "${repo}"
        bash "${_PATH}/gpush.sh"
    ) > "${TEST_DIR}/detached.log" 2>&1
    status=$?
    set -e

    ((status != 0)) || _fail "detached HEAD 下 gpush 应返回非零"
    grep -Fq 'Detached HEAD' "${TEST_DIR}/detached.log" \
        || _fail "detached HEAD 下 gpush 缺少明确错误"
    [[ "$(git -C "${repo}" rev-parse HEAD)" == "${detached_head}" ]] \
        || _fail "detached HEAD 下 gpush 不应创建本地提交"
}

_test_does_not_recurse_into_submodules
_test_commit_failure_aborts_before_push
_test_detached_head_is_rejected

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
