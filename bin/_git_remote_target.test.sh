#!/usr/bin/env bash

_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

TEST_DIR="${_PATH}/.git-remote-target-test.$$"
cleanup() {
    rm -rf -- "${TEST_DIR}"
}
trap cleanup EXIT

_fail() {
    echo "FAIL: $*" >&2
    exit 1
}

# shellcheck source=/dev/null
source "${_PATH}/_git_remote_target.sh"

_test_parse_args() {
    _git_remote_target_parse_args -t github.com --dry-run
    [[ "${_GIT_REMOTE_SELECTED_TARGET}" == github.com ]] \
        || _fail "explicit target was not parsed"
    [[ "${_GIT_REMOTE_REMAINING_ARGS[0]}" == --dry-run ]] \
        || _fail "non-target option was not preserved"

    _git_remote_target_parse_args -t
    [[ "${_GIT_REMOTE_SELECTED_TARGET}" == code.itp.ac.cn ]] \
        || _fail "bare -t did not select code.itp.ac.cn"
    [[ "${#_GIT_REMOTE_REMAINING_ARGS[@]}" -eq 0 ]] \
        || _fail "bare -t changed the remaining arguments"

    _git_remote_target_parse_args --target=gitee.com --path child
    [[ "${_GIT_REMOTE_SELECTED_TARGET}" == gitee.com ]] \
        || _fail "--target=DOMAIN was not parsed"
    [[ "${_GIT_REMOTE_REMAINING_ARGS[*]}" == "--path child" ]] \
        || _fail "--target=DOMAIN consumed unrelated arguments"

    _git_remote_target_parse_args
    [[ -z "${_GIT_REMOTE_SELECTED_TARGET}" ]] \
        || _fail "omitting -t must not select a target"
}

_test_invalid_target() {
    local status

    set +e
    ( _git_remote_target_parse_args -t example.com ) >"${TEST_DIR}/invalid.log" 2>&1
    status=$?
    set -e
    [[ "${status}" -eq 64 ]] || _fail "invalid target returned ${status}, expected 64"
    grep -Fq 'Unsupported remote target: example.com' "${TEST_DIR}/invalid.log" \
        || _fail "invalid target did not explain the accepted values"
}

_test_url_rewrite_is_temporary() {
    local repo="${TEST_DIR}/repo"

    git init -q -b main "${repo}"
    git -C "${repo}" remote add origin git@code.itp.ac.cn:owner/repo.git
    git -C "${repo}" remote add https-origin https://code.itp.ac.cn/owner/repo.git
    git -C "${repo}" remote add ssh-origin ssh://git@code.itp.ac.cn/owner/repo.git
    git -C "${repo}" remote add git-ssh-origin git+ssh://git@code.itp.ac.cn/owner/repo.git
    git -C "${repo}" remote add http-origin http://code.itp.ac.cn/owner/repo.git
    git -C "${repo}" remote add git-origin git://code.itp.ac.cn/owner/repo.git
    git -C "${repo}" remote add local-origin "${TEST_DIR}/local-repo.git"

    (
        _git_remote_target_apply github.com >/dev/null
        [[ "$(git -C "${repo}" remote get-url origin)" == git@github.com:owner/repo.git ]] \
            || _fail "scp-like URL did not preserve protocol, user, and path"
        [[ "$(git -C "${repo}" remote get-url https-origin)" == https://github.com/owner/repo.git ]] \
            || _fail "HTTPS URL was not rewritten"
        [[ "$(git -C "${repo}" remote get-url ssh-origin)" == ssh://git@github.com/owner/repo.git ]] \
            || _fail "SSH URL was not rewritten"
        [[ "$(git -C "${repo}" remote get-url git-ssh-origin)" == git+ssh://git@github.com/owner/repo.git ]] \
            || _fail "git+ssh URL was not rewritten"
        [[ "$(git -C "${repo}" remote get-url http-origin)" == http://github.com/owner/repo.git ]] \
            || _fail "HTTP URL was not rewritten"
        [[ "$(git -C "${repo}" remote get-url git-origin)" == git://github.com/owner/repo.git ]] \
            || _fail "git protocol URL was not rewritten"
        [[ "$(git -C "${repo}" remote get-url local-origin)" == "${TEST_DIR}/local-repo.git" ]] \
            || _fail "local URLs must not be rewritten"
    )

    [[ "$(git -C "${repo}" remote get-url origin)" == git@code.itp.ac.cn:owner/repo.git ]] \
        || _fail "remote URL override leaked outside the invocation"
}

_test_reapply_and_existing_config() {
    local repo="${TEST_DIR}/reapply-repo"

    git init -q -b main "${repo}"
    git -C "${repo}" remote add origin git@code.itp.ac.cn:owner/repo.git

    (
        export GIT_CONFIG_COUNT=1
        export GIT_CONFIG_KEY_0=test.sentinel
        export GIT_CONFIG_VALUE_0=kept
        _git_remote_target_apply github.com >/dev/null
        _git_remote_target_apply gitlab.com >/dev/null
        [[ "$(git -C "${repo}" config test.sentinel)" == kept ]] \
            || _fail "existing environment Git config was not preserved"
        [[ "$(git -C "${repo}" remote get-url origin)" == git@gitlab.com:owner/repo.git ]] \
            || _fail "a later target did not replace the earlier temporary mapping"
    )
}

main() {
    mkdir -p "${TEST_DIR}"
    _test_parse_args
    _test_invalid_target
    _test_url_rewrite_is_temporary
    _test_reapply_and_existing_config
}

main "$@"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
