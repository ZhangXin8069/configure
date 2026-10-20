#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

TEST_DIR="${_PATH}/.gpull-test.$$"
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
    git -C "${repo}" config user.name gpull-test
    git -C "${repo}" config user.email gpull-test@example.invalid
}

_test_pull_preserves_changes() {
    local remote="${TEST_DIR}/remote.git"
    local seed="${TEST_DIR}/seed"
    local work="${TEST_DIR}/work"
    local other="${TEST_DIR}/other"
    local real_git
    local fake_bin="${TEST_DIR}/fake-bin"
    local fake_git="${fake_bin}/git"

    git init -q --bare "${remote}"
    git -C "${remote}" symbolic-ref HEAD refs/heads/main

    git init -q "${seed}"
    _configure_identity "${seed}"
    git -C "${seed}" checkout -q -b main
    printf 'base\n' > "${seed}/local.txt"
    printf 'base\n' > "${seed}/remote.txt"
    git -C "${seed}" add local.txt remote.txt
    git -C "${seed}" commit -q -m initial
    git -C "${seed}" remote add origin "${remote}"
    git -C "${seed}" push -q -u origin main

    git clone -q "${remote}" "${work}"
    _configure_identity "${work}"
    git clone -q "${remote}" "${other}"
    _configure_identity "${other}"

    printf 'remote update\n' > "${other}/remote.txt"
    git -C "${other}" add remote.txt
    git -C "${other}" commit -q -m remote-update
    git -C "${other}" push -q

    printf 'local update\n' > "${work}/local.txt"
    (
        cd "${work}"
        bash "${_PATH}/gpull.sh"
    ) > "${TEST_DIR}/pull.log" 2>&1

    grep -Fqx 'remote update' "${work}/remote.txt" || _fail "未拉取远端更新"
    grep -Fqx 'local update' "${work}/local.txt" || _fail "未恢复本地 tracked 改动"
    [[ -z "$(git -C "${work}" stash list)" ]] || _fail "拉取后仍有未恢复的自动 stash"

    real_git=$(command -v git)
    mkdir -p "${fake_bin}"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'if [[ ${1:-} == pull && ${2:-} == -h ]]; then' \
        '    echo "usage: git pull [<options>] (autostash unavailable)"' \
        '    exit 0' \
        'fi' \
        'if [[ ${1:-} == stash && ${2:-} == push ]]; then' \
        '    exit 129' \
        'fi' \
        "exec $(printf '%q' "${real_git}") \"\$@\"" > "${fake_git}"
    chmod +x "${fake_git}"

    printf 'remote update 2\n' > "${other}/remote.txt"
    git -C "${other}" add remote.txt
    git -C "${other}" commit -q -m remote-update-2
    git -C "${other}" push -q
    printf 'local update 2\n' > "${work}/local.txt"

    (
        cd "${work}"
        PATH="${fake_bin}:${PATH}" bash "${_PATH}/gpull.sh"
    ) > "${TEST_DIR}/fallback.log" 2>&1

    grep -Fq 'manual stash fallback' "${TEST_DIR}/fallback.log" || _fail "未进入旧版 Git 回退流程"
    grep -Fqx 'remote update 2' "${work}/remote.txt" || _fail "旧版 Git 回退未拉取远端更新"
    grep -Fqx 'local update 2' "${work}/local.txt" || _fail "旧版 Git 回退未恢复本地改动"
    [[ -z "$(git -C "${work}" stash list)" ]] || _fail "旧版 Git 回退后仍有未恢复的 stash"

    git -C "${work}" checkout -q --detach HEAD
    set +e
    (
        cd "${work}"
        bash "${_PATH}/gpull.sh"
    ) > "${TEST_DIR}/detached.log" 2>&1
    local detached_status=$?
    set -e
    ((detached_status != 0)) || _fail "detached HEAD 应返回非零"
    grep -Fq 'Detached HEAD' "${TEST_DIR}/detached.log" || _fail "缺少 detached HEAD 错误提示"
}

_test_wrapper_propagates_failure() {
    local wrapper_root="${TEST_DIR}/wrapper"
    local wrapper_bin="${wrapper_root}/bin"

    mkdir -p "${wrapper_bin}"
    cp "${_PATH}/zg-configure-pull.sh" "${wrapper_bin}/"
    cp "${_PATH}/gpull.sh" "${wrapper_bin}/"
    git init -q "${wrapper_root}"
    _configure_identity "${wrapper_root}"
    printf 'base\n' > "${wrapper_root}/file.txt"
    git -C "${wrapper_root}" add file.txt
    git -C "${wrapper_root}" commit -q -m initial
    git -C "${wrapper_root}" checkout -q --detach HEAD

    set +e
    bash "${wrapper_bin}/zg-configure-pull.sh" > "${TEST_DIR}/wrapper.log" 2>&1
    local wrapper_status=$?
    set -e
    ((wrapper_status != 0)) || _fail "zg-configure-pull.sh 应传播 gpull 失败"
    grep -Fq 'Detached HEAD' "${TEST_DIR}/wrapper.log" || _fail "包装脚本未输出根因"
}

_test_fetch_failure_propagates() {
    local repo="${TEST_DIR}/fetch-failure"

    git init -q "${repo}"
    _configure_identity "${repo}"
    printf 'base\n' > "${repo}/file.txt"
    git -C "${repo}" add file.txt
    git -C "${repo}" commit -q -m initial
    git -C "${repo}" remote add origin "${TEST_DIR}/missing.git"

    set +e
    (
        cd "${repo}"
        bash "${_PATH}/gpull.sh"
    ) > "${TEST_DIR}/fetch-failure.log" 2>&1
    local fetch_status=$?
    set -e
    ((fetch_status != 0)) || _fail "fetch 失败应返回非零"
    grep -Fq 'git fetch failed' "${TEST_DIR}/fetch-failure.log" || _fail "缺少 fetch 失败提示"
}

main() {
    _test_pull_preserves_changes
    _test_wrapper_propagates_failure
    _test_fetch_failure_propagates
}

main "$@"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
