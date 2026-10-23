#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

TEST_DIR="${_PATH}/.zg-all-pull-sub-test.$$"
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
    local label=$2
    local status_var=$3

    printf '%s\n' \
        '#!/usr/bin/env bash' \
        "printf '%s:%s\\n' '${label}' \"\$*\" >> \"\${EVENT_LOG:?}\"" \
        "exit \"\${${status_var}:-0}\"" > "${path}"
    chmod +x "${path}"
}

_make_fixture() {
    local fixture=$1
    local wrapper_bin="${fixture}/configure/bin"

    mkdir -p "${wrapper_bin}"
    cp "${_PATH}/zg-all-pull-sub.sh" "${wrapper_bin}/"
    cp "${_PATH}/_all_series.sh" "${wrapper_bin}/"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'printf "parent-all\n" >> "${EVENT_LOG:?}"' \
        'exit "${PARENT_STATUS:-0}"' > "${wrapper_bin}/zg-all-pull.sh"
    chmod +x "${wrapper_bin}/zg-all-pull.sh"
    _write_child "${wrapper_bin}/zg-configure-pull-sub.sh" configure CONFIGURE_STATUS
    _write_child "${wrapper_bin}/zg-myqcd-pull-sub.sh" myqcd MYQCD_STATUS
    _write_child "${wrapper_bin}/zg-pyqcd-pull-sub.sh" pyqcd PYQCD_STATUS
    _write_child "${wrapper_bin}/zg-pyqcu-pull-sub.sh" pyqcu PYQCU_STATUS
}

_test_parent_then_sorted_children() {
    local fixture="${TEST_DIR}/all"
    local event_log="${fixture}/events.log"
    local wrapper_bin="${fixture}/configure/bin"

    _make_fixture "${fixture}"
    _write_child "${wrapper_bin}/zg-aaa-pull-sub.sh" aaa AAA_STATUS

    EVENT_LOG="${event_log}" bash "${wrapper_bin}/zg-all-pull-sub.sh" \
        > "${TEST_DIR}/all.log" 2>&1

    [[ "$(paste -sd, "${event_log}")" \
        == parent-all,aaa:,configure:,myqcd:,pyqcd:,pyqcu: ]] \
        || _fail "父仓库或动态发现的子系列执行顺序错误"
}

_test_help_is_non_mutating() {
    local fixture="${TEST_DIR}/help"
    local event_log="${fixture}/events.log"

    _make_fixture "${fixture}"
    EVENT_LOG="${event_log}" bash "${fixture}/configure/bin/zg-all-pull-sub.sh" --help \
        > "${TEST_DIR}/help.log" 2>&1

    grep -Fq 'Usage: zg-all-pull-sub.sh' "${TEST_DIR}/help.log" || _fail "缺少聚合帮助"
    [[ ! -e "${event_log}" ]] || _fail "help 不应执行父仓库或子系列"
}

_test_dry_run_skips_parent_and_forwards_arguments() {
    local fixture="${TEST_DIR}/dry-run"
    local event_log="${fixture}/events.log"

    _make_fixture "${fixture}"
    EVENT_LOG="${event_log}" \
        bash "${fixture}/configure/bin/zg-all-pull-sub.sh" --dry-run --path refer/example \
        > "${TEST_DIR}/dry-run.log" 2>&1

    ! grep -Fqx 'parent-all' "${event_log}" || _fail "dry-run 不应更新父仓库"
    grep -Fqx 'configure:--dry-run --path refer/example' "${event_log}" \
        || _fail "configure 参数未透传"
    grep -Fqx 'pyqcu:--dry-run --path refer/example' "${event_log}" \
        || _fail "PyQCU 参数未透传"
}

_test_failures_are_aggregated() {
    local fixture="${TEST_DIR}/failure"
    local event_log="${fixture}/events.log"
    local status

    _make_fixture "${fixture}"
    set +e
    EVENT_LOG="${event_log}" \
        PARENT_STATUS=4 \
        MYQCD_STATUS=5 \
        bash "${fixture}/configure/bin/zg-all-pull-sub.sh" \
        > "${TEST_DIR}/failure.log" 2>&1
    status=$?
    set -e

    ((status != 0)) || _fail "父仓或子系列失败应聚合为非零"
    grep -Fqx 'pyqcd:' "${event_log}" || _fail "MyQCD 失败后仍应继续 PyQCD"
    grep -Fqx 'pyqcu:' "${event_log}" || _fail "MyQCD 失败后仍应继续 PyQCU"
    grep -Fq 'Summary: failed=2' "${TEST_DIR}/failure.log" || _fail "失败数量汇总错误"
}

_test_requires_multiple_matching_children() {
    local fixture="${TEST_DIR}/minimum"
    local wrapper_bin="${fixture}/configure/bin"
    local status

    _make_fixture "${fixture}"
    rm -f -- "${wrapper_bin}/zg-myqcd-pull-sub.sh" \
        "${wrapper_bin}/zg-pyqcd-pull-sub.sh" \
        "${wrapper_bin}/zg-pyqcu-pull-sub.sh"
    set +e
    bash "${wrapper_bin}/zg-all-pull-sub.sh" > "${TEST_DIR}/minimum.log" 2>&1
    status=$?
    set -e

    ((status != 0)) || _fail "少于两个子系列时应失败"
    grep -Fq 'requires at least 2 matching' "${TEST_DIR}/minimum.log" \
        || _fail "缺少最小子系列数量错误"
}

_test_wrappers_change_into_target_repositories() {
    local fixture="${TEST_DIR}/wrapper"
    local wrapper_bin="${fixture}/configure/bin"
    local work_log="${fixture}/work.log"

    mkdir -p "${wrapper_bin}" \
        "${fixture}/configure/.git" \
        "${fixture}/PyQCD/.git" \
        "${fixture}/MyQCD/.git" \
        "${fixture}/PyQCU/.git"
    cp "${_PATH}/zg-configure-pull-sub.sh" "${wrapper_bin}/"
    cp "${_PATH}/zg-pyqcd-pull-sub.sh" "${wrapper_bin}/"
    cp "${_PATH}/zg-myqcd-pull-sub.sh" "${wrapper_bin}/"
    cp "${_PATH}/zg-pyqcu-pull-sub.sh" "${wrapper_bin}/"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'printf "%s|%s\n" "${PWD##*/}" "$*" >> "${WORK_LOG:?}"' > "${wrapper_bin}/gpull-sub.sh"
    chmod +x "${wrapper_bin}/"*.sh

    WORK_LOG="${work_log}" bash "${wrapper_bin}/zg-configure-pull-sub.sh" --init
    WORK_LOG="${work_log}" bash "${wrapper_bin}/zg-pyqcd-pull-sub.sh" --recursive
    WORK_LOG="${work_log}" bash "${wrapper_bin}/zg-myqcd-pull-sub.sh" --dry-run
    WORK_LOG="${work_log}" bash "${wrapper_bin}/zg-pyqcu-pull-sub.sh" --path refer/example

    grep -Fqx 'configure|--init' "${work_log}" || _fail "configure 包装器目录或参数错误"
    grep -Fqx 'PyQCD|--recursive' "${work_log}" || _fail "PyQCD 包装器目录或参数错误"
    grep -Fqx 'MyQCD|--dry-run' "${work_log}" || _fail "MyQCD 包装器目录或参数错误"
    grep -Fqx 'PyQCU|--path refer/example' "${work_log}" || _fail "PyQCU 包装器目录或参数错误"
}

main() {
    _test_parent_then_sorted_children
    _test_help_is_non_mutating
    _test_dry_run_skips_parent_and_forwards_arguments
    _test_failures_are_aggregated
    _test_requires_multiple_matching_children
    _test_wrappers_change_into_target_repositories
}

main "$@"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
