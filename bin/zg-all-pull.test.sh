#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

TEST_DIR="${_PATH}/.zg-all-pull-test.$$"
cleanup() {
    rm -rf -- "${TEST_DIR}"
}
trap cleanup EXIT
mkdir -p "${TEST_DIR}"

_fail() {
    echo "FAIL: $*" >&2
    exit 1
}

_test_forced_https_clone() {
    local wrapper_root="${TEST_DIR}/wrapper"
    local wrapper_bin="${wrapper_root}/a/bin"
    local fake_bin="${TEST_DIR}/fake-bin"
    local clone_log="${TEST_DIR}/clone.log"

    mkdir -p "${wrapper_bin}" "${fake_bin}"
    cp "${_PATH}/zg-all-pull.sh" "${wrapper_bin}/"
    printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "${wrapper_bin}/zg-configure-pull.sh"
    chmod +x "${wrapper_bin}/zg-configure-pull.sh"

    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'if [[ ${1:-} == clone ]]; then' \
        '    printf "%s\n" "$*" >> "${GIT_CLONE_LOG:?}"' \
        '    mkdir -p "${3:?}/.git"' \
        '    exit 0' \
        'fi' \
        'exit 1' > "${fake_bin}/git"
    chmod +x "${fake_bin}/git"

    PATH="${fake_bin}:${PATH}" \
        GIT_CLONE_LOG="${clone_log}" \
        ZG_GIT_PROTOCOL=https \
        bash "${wrapper_bin}/zg-all-pull.sh" > "${TEST_DIR}/zg-all-pull.log" 2>&1

    [[ "$(grep -Fc 'clone https://gitee.com/zhangxin8069/' "${clone_log}")" -eq 3 ]] \
        || _fail "强制 HTTPS 时应克隆三个仓库"
    ! grep -Fq 'git@gitee.com' "${clone_log}" || _fail "强制 HTTPS 时不应尝试 SSH"
}

_test_auto_falls_back_to_https() {
    local wrapper_root="${TEST_DIR}/auto-wrapper"
    local wrapper_bin="${wrapper_root}/a/bin"
    local fake_bin="${TEST_DIR}/auto-fake-bin"
    local clone_log="${TEST_DIR}/auto-clone.log"

    mkdir -p "${wrapper_bin}" "${fake_bin}"
    cp "${_PATH}/zg-all-pull.sh" "${wrapper_bin}/"
    printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "${wrapper_bin}/zg-configure-pull.sh"
    chmod +x "${wrapper_bin}/zg-configure-pull.sh"

    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'if [[ ${1:-} == clone ]]; then' \
        '    printf "%s\n" "$*" >> "${GIT_CLONE_LOG:?}"' \
        '    if [[ ${2:-} == git@* ]]; then' \
        '        mkdir -p "${3:?}"' \
        '        exit 128' \
        '    fi' \
        '    mkdir -p "${3:?}/.git"' \
        '    exit 0' \
        'fi' \
        'exit 1' > "${fake_bin}/git"
    chmod +x "${fake_bin}/git"

    PATH="${fake_bin}:${PATH}" \
        GIT_CLONE_LOG="${clone_log}" \
        ZG_GIT_PROTOCOL=auto \
        bash "${wrapper_bin}/zg-all-pull.sh" > "${TEST_DIR}/auto-zg-all-pull.log" 2>&1

    [[ "$(grep -Fc 'clone git@gitee.com:' "${clone_log}")" -eq 3 ]] \
        || _fail "auto 模式应先尝试三个 SSH clone"
    [[ "$(grep -Fc 'clone https://gitee.com/zhangxin8069/' "${clone_log}")" -eq 3 ]] \
        || _fail "auto 模式应在 SSH 失败后回退三个 HTTPS clone"
}

main() {
    _test_forced_https_clone
    _test_auto_falls_back_to_https
}

main "$@"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
