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

_write_child() {
    local path=$1
    local repo_path=$2
    local label=$3

    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'if [[ ${1:-} == --print-repo-path ]]; then' \
        "    printf '%s\\n' '${repo_path}'" \
        '    exit 0' \
        'fi' \
        "printf '%s\\n' '${label}' >> \"\${EVENT_LOG:?}\"" > "${path}"
    chmod +x "${path}"
}

_make_fixture() {
    local fixture=$1
    local wrapper_bin="${fixture}/configure/bin"

    mkdir -p "${wrapper_bin}" "${fixture}/configure/.git"
    cp "${_PATH}/zg-all-pull.sh" "${wrapper_bin}/"
    cp "${_PATH}/_all_series.sh" "${wrapper_bin}/"
    _write_child "${wrapper_bin}/zg-configure-pull.sh" "${fixture}/configure" configure
    _write_child "${wrapper_bin}/zg-pyqcd-pull.sh" "${fixture}/PyQCD" pyqcd
    _write_child "${wrapper_bin}/zg-pyqcu-pull.sh" "${fixture}/PyQCU" pyqcu
}

_make_fake_git() {
    local fake_bin=$1
    local mode=$2

    mkdir -p "${fake_bin}"
    if [[ "${mode}" == auto ]]; then
        printf '%s\n' \
            '#!/usr/bin/env bash' \
            'if [[ ${1:-} == clone ]]; then' \
            '    printf "%s\n" "$*" >> "${GIT_CLONE_LOG:?}"' \
            '    if [[ ${2:-} == git@* ]]; then' \
            '        exit 128' \
            '    fi' \
            '    mkdir -p "${3:?}/.git"' \
            '    exit 0' \
            'fi' \
            'exit 1' > "${fake_bin}/git"
    else
        printf '%s\n' \
            '#!/usr/bin/env bash' \
            'if [[ ${1:-} == clone ]]; then' \
            '    printf "%s\n" "$*" >> "${GIT_CLONE_LOG:?}"' \
            '    mkdir -p "${3:?}/.git"' \
            '    exit 0' \
            'fi' \
            'exit 1' > "${fake_bin}/git"
    fi
    chmod +x "${fake_bin}/git"
}

_test_forced_https_clone_and_filename_order() {
    local fixture="${TEST_DIR}/https"
    local wrapper_bin="${fixture}/configure/bin"
    local fake_bin="${TEST_DIR}/https-bin"
    local clone_log="${TEST_DIR}/https-clone.log"
    local event_log="${TEST_DIR}/https-events.log"

    _make_fixture "${fixture}"
    _write_child "${wrapper_bin}/zg-aaa-pull.sh" "${fixture}/existing-a" existing-a
    mkdir -p "${fixture}/existing-a/.git"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'if [[ ${1:-} == --print-repo-path ]]; then' \
        '    exit 1' \
        'fi' \
        'printf "dynamic\n" >> "${EVENT_LOG:?}"' > "${wrapper_bin}/zg-dynamic-pull.sh"
    chmod +x "${wrapper_bin}/zg-dynamic-pull.sh"
    _make_fake_git "${fake_bin}" https

    PATH="${fake_bin}:${PATH}" \
        GIT_CLONE_LOG="${clone_log}" \
        EVENT_LOG="${event_log}" \
        ZG_GIT_PROTOCOL=https \
        bash "${wrapper_bin}/zg-all-pull.sh" > "${TEST_DIR}/https.log" 2>&1

    [[ "$(grep -Fc 'clone https://gitee.com/zhangxin8069/' "${clone_log}")" -eq 2 ]] \
        || _fail "应按文件名发现并克隆两个缺失仓库"
    ! grep -Fq 'git@gitee.com' "${clone_log}" || _fail "强制 HTTPS 时不应尝试 SSH"
    [[ "$(paste -sd, "${event_log}")" == existing-a,configure,dynamic,pyqcd,pyqcu ]] \
        || _fail "子系列未按文件名顺序执行或动态发现/自定义脚本兼容失败"
}

_test_auto_falls_back_to_https() {
    local fixture="${TEST_DIR}/auto"
    local wrapper_bin="${fixture}/configure/bin"
    local fake_bin="${TEST_DIR}/auto-bin"
    local clone_log="${TEST_DIR}/auto-clone.log"
    local event_log="${TEST_DIR}/auto-events.log"

    _make_fixture "${fixture}"
    _make_fake_git "${fake_bin}" auto

    PATH="${fake_bin}:${PATH}" \
        GIT_CLONE_LOG="${clone_log}" \
        EVENT_LOG="${event_log}" \
        ZG_GIT_PROTOCOL=auto \
        bash "${wrapper_bin}/zg-all-pull.sh" > "${TEST_DIR}/auto.log" 2>&1

    [[ "$(grep -Fc 'clone git@gitee.com:' "${clone_log}")" -eq 2 ]] \
        || _fail "auto 模式应先尝试两个 SSH clone"
    [[ "$(grep -Fc 'clone https://gitee.com/zhangxin8069/' "${clone_log}")" -eq 2 ]] \
        || _fail "auto 模式应在 SSH 失败后回退两个 HTTPS clone"
}

_test_requires_multiple_matching_children() {
    local fixture="${TEST_DIR}/minimum"
    local wrapper_bin="${fixture}/configure/bin"
    local status

    _make_fixture "${fixture}"
    rm -f -- "${wrapper_bin}/zg-pyqcd-pull.sh" "${wrapper_bin}/zg-pyqcu-pull.sh"

    set +e
    bash "${wrapper_bin}/zg-all-pull.sh" > "${TEST_DIR}/minimum.log" 2>&1
    status=$?
    set -e

    ((status != 0)) || _fail "少于两个子系列时应失败"
    grep -Fq 'requires at least 2 matching' "${TEST_DIR}/minimum.log" \
        || _fail "缺少最小子系列数量错误"
}

_test_help_is_non_mutating() {
    local fixture="${TEST_DIR}/help"
    local wrapper_bin="${fixture}/configure/bin"

    _make_fixture "${fixture}"
    bash "${wrapper_bin}/zg-all-pull.sh" --help > "${TEST_DIR}/help.log" 2>&1
    grep -Fq 'Usage: zg-all-pull.sh' "${TEST_DIR}/help.log" || _fail "缺少帮助"
    [[ ! -e "${fixture}/PyQCD" ]] || _fail "help 不应触发 clone"
}

main() {
    _test_forced_https_clone_and_filename_order
    _test_auto_falls_back_to_https
    _test_requires_multiple_matching_children
    _test_help_is_non_mutating
}

main "$@"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
