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
    [[ "${_GIT_REMOTE_SELECTED_TARGET}" == gitlab.itp.ac.cn ]] \
        || _fail "bare -t did not select gitlab.itp.ac.cn"
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
    git -C "${repo}" remote add origin git@gitlab.itp.ac.cn:owner/repo.git
    git -C "${repo}" remote add legacy-origin git@code.itp.ac.cn:owner/repo.git
    git -C "${repo}" remote add custom-origin git@legacy.example.invalid:owner/repo.git
    git -C "${repo}" remote add custom-port https://legacy.example.invalid:8443/owner/repo.git
    git -C "${repo}" remote add https-origin https://gitlab.itp.ac.cn/owner/repo.git
    git -C "${repo}" remote add ssh-origin ssh://git@gitlab.itp.ac.cn/owner/repo.git
    git -C "${repo}" remote add git-ssh-origin git+ssh://git@gitlab.itp.ac.cn/owner/repo.git
    git -C "${repo}" remote add http-origin http://gitlab.itp.ac.cn/owner/repo.git
    git -C "${repo}" remote add git-origin git://gitlab.itp.ac.cn/owner/repo.git
    git -C "${repo}" remote add local-origin "${TEST_DIR}/local-repo.git"

    (
        cd "${repo}"
        _git_remote_target_apply github.com >/dev/null
        [[ "$(git remote get-url origin)" == git@github.com:owner/repo.git ]] \
            || _fail "scp-like URL did not preserve protocol, user, and path"
        [[ "$(git remote get-url legacy-origin)" == git@github.com:owner/repo.git ]] \
            || _fail "legacy configured URL was not overridden"
        [[ "$(git remote get-url custom-origin)" == git@github.com:owner/repo.git ]] \
            || _fail "custom configured URL was not overridden"
        [[ "$(git remote get-url custom-port)" == https://github.com:8443/owner/repo.git ]] \
            || _fail "configured URL port was not preserved"
        [[ "$(git remote get-url https-origin)" == https://github.com/owner/repo.git ]] \
            || _fail "HTTPS URL was not rewritten"
        [[ "$(git remote get-url ssh-origin)" == ssh://git@github.com/owner/repo.git ]] \
            || _fail "SSH URL was not rewritten"
        [[ "$(git remote get-url git-ssh-origin)" == git+ssh://git@github.com/owner/repo.git ]] \
            || _fail "git+ssh URL was not rewritten"
        [[ "$(git remote get-url http-origin)" == http://github.com/owner/repo.git ]] \
            || _fail "HTTP URL was not rewritten"
        [[ "$(git remote get-url git-origin)" == git://github.com/owner/repo.git ]] \
            || _fail "git protocol URL was not rewritten"
        [[ "$(git remote get-url local-origin)" == "${TEST_DIR}/local-repo.git" ]] \
            || _fail "local URLs must not be rewritten"
    )

    [[ "$(git -C "${repo}" remote get-url origin)" == git@gitlab.itp.ac.cn:owner/repo.git ]] \
        || _fail "remote URL override leaked outside the invocation"
}

_test_reapply_and_existing_config() {
    local repo="${TEST_DIR}/reapply-repo"

    git init -q -b main "${repo}"
    git -C "${repo}" remote add origin git@gitlab.itp.ac.cn:owner/repo.git

    (
        cd "${repo}"
        export GIT_CONFIG_COUNT=1
        export GIT_CONFIG_KEY_0=test.sentinel
        export GIT_CONFIG_VALUE_0=kept
        _git_remote_target_apply github.com >/dev/null
        _git_remote_target_apply gitlab.com >/dev/null
        [[ "$(git config test.sentinel)" == kept ]] \
            || _fail "existing environment Git config was not preserved"
        [[ "$(git remote get-url origin)" == git@gitlab.com:owner/repo.git ]] \
            || _fail "a later target did not replace the earlier temporary mapping"
    )
}

_test_same_target_reapply_discovers_new_remotes() {
    local first="${TEST_DIR}/same-target-first"
    local second="${TEST_DIR}/same-target-second"

    git init -q -b main "${first}"
    git -C "${first}" remote add origin git@first.example.invalid:owner/first.git
    git init -q -b main "${second}"
    git -C "${second}" remote add origin git@second.example.invalid:owner/second.git

    (
        cd "${first}"
        _git_remote_target_apply github.com >/dev/null
        [[ "$(git remote get-url origin)" == git@github.com:owner/first.git ]] \
            || _fail "initial configured URL was not overridden"

        cd "${second}"
        _git_remote_target_apply github.com >/dev/null
        [[ "$(git remote get-url origin)" == git@github.com:owner/second.git ]] \
            || _fail "same-target reapply did not discover the second repository URL"
    )
}

_test_configured_url_controls_transport() {
    local repo="${TEST_DIR}/transport-repo"
    local fake_ssh="${TEST_DIR}/fake-ssh"
    local ssh_log="${TEST_DIR}/ssh.log"

    git init -q -b main "${repo}"
    git -C "${repo}" remote add origin git@legacy.example.invalid:owner/repo.git
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'printf "%s\n" "$*" >> "${SSH_CAPTURE:?}"' \
        'exit 1' >"${fake_ssh}"
    chmod +x "${fake_ssh}"

    (
        cd "${repo}"
        _git_remote_target_apply github.com >/dev/null
        set +e
        GIT_SSH_COMMAND="${fake_ssh}" SSH_CAPTURE="${ssh_log}" GIT_TERMINAL_PROMPT=0 \
            git ls-remote origin >"${TEST_DIR}/transport.log" 2>&1
        set -e
    )

    grep -Fq 'git@github.com' "${ssh_log}" \
        || _fail "configured URL did not control the actual SSH transport target"
}

_test_bare_target_overrides_configured_url() {
    local repo="${TEST_DIR}/bare-target-repo"

    git init -q -b main "${repo}"
    git -C "${repo}" remote add origin git@legacy.example.invalid:owner/repo.git

    (
        cd "${repo}"
        _git_remote_target_parse_args -t
        _git_remote_target_apply "${_GIT_REMOTE_SELECTED_TARGET}" >/dev/null
        [[ "$(git remote get-url origin)" == git@gitlab.itp.ac.cn:owner/repo.git ]] \
            || _fail "bare -t did not use the default target for a configured URL"
    )
}

main() {
    mkdir -p "${TEST_DIR}"
    _test_parse_args
    _test_invalid_target
    _test_url_rewrite_is_temporary
    _test_reapply_and_existing_config
    _test_same_target_reapply_discovers_new_remotes
    _test_configured_url_controls_transport
    _test_bare_target_overrides_configured_url
}

main "$@"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
