#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

TEST_DIR="${_PATH}/.zg-all-back-sub-test.$$"
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
    cp "${_PATH}/zg-all-back-sub.sh" "${wrapper_bin}/"
    cp "${_PATH}/_all_series.sh" "${wrapper_bin}/"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'printf "parent-back\n" >> "${EVENT_LOG:?}"' \
        'exit "${PARENT_STATUS:-0}"' > "${wrapper_bin}/zg-all-back.sh"
    chmod +x "${wrapper_bin}/zg-all-back.sh"
    _write_child "${wrapper_bin}/zg-configure-back-sub.sh" configure CONFIGURE_STATUS
    _write_child "${wrapper_bin}/zg-myqcd-back-sub.sh" myqcd MYQCD_STATUS
    _write_child "${wrapper_bin}/zg-pyqcd-back-sub.sh" pyqcd PYQCD_STATUS
    _write_child "${wrapper_bin}/zg-pyqcu-back-sub.sh" pyqcu PYQCU_STATUS
}

_test_parent_then_sorted_children() {
    local fixture="${TEST_DIR}/ordered"
    local event_log="${fixture}/events.log"

    _make_fixture "${fixture}"
    EVENT_LOG="${event_log}" bash "${fixture}/configure/bin/zg-all-back-sub.sh" --path refer/x \
        > "${TEST_DIR}/ordered.log" 2>&1
    [[ "$(paste -sd, "${event_log}")" \
        == parent-back,configure:--path\ refer/x,myqcd:--path\ refer/x,pyqcd:--path\ refer/x,pyqcu:--path\ refer/x ]] \
        || _fail "父仓库或 back-sub 子系列顺序/参数错误"
}

_test_dry_run_skips_parent() {
    local fixture="${TEST_DIR}/dry-run"
    local event_log="${fixture}/events.log"

    _make_fixture "${fixture}"
    EVENT_LOG="${event_log}" bash "${fixture}/configure/bin/zg-all-back-sub.sh" --dry-run \
        > "${TEST_DIR}/dry-run.log" 2>&1
    ! grep -Fqx 'parent-back' "${event_log}" || _fail "dry-run 不应恢复父仓库"
    grep -Fqx 'pyqcd:--dry-run' "${event_log}" || _fail "dry-run 未传给 back-sub 子系列"
}

_test_failures_are_aggregated() {
    local fixture="${TEST_DIR}/failure"
    local event_log="${fixture}/events.log"
    local status

    _make_fixture "${fixture}"
    set +e
    EVENT_LOG="${event_log}" PARENT_STATUS=4 MYQCD_STATUS=5 \
        bash "${fixture}/configure/bin/zg-all-back-sub.sh" \
        > "${TEST_DIR}/failure.log" 2>&1
    status=$?
    set -e

    ((status != 0)) || _fail "父仓或 back-sub 子系列失败应传播"
    grep -Fqx 'pyqcd:' "${event_log}" || _fail "MyQCD 失败后未继续 PyQCD"
    grep -Fqx 'pyqcu:' "${event_log}" || _fail "MyQCD 失败后未继续 PyQCU"
    grep -Fq 'Summary: failed=2' "${TEST_DIR}/failure.log" || _fail "失败汇总错误"
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
    cp "${_PATH}/zg-configure-back-sub.sh" "${wrapper_bin}/"
    cp "${_PATH}/zg-pyqcd-back-sub.sh" "${wrapper_bin}/"
    cp "${_PATH}/zg-myqcd-back-sub.sh" "${wrapper_bin}/"
    cp "${_PATH}/zg-pyqcu-back-sub.sh" "${wrapper_bin}/"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'printf "%s|%s\n" "${PWD##*/}" "$*" >> "${WORK_LOG:?}"' > "${wrapper_bin}/gback-sub.sh"
    chmod +x "${wrapper_bin}/"*.sh

    WORK_LOG="${work_log}" bash "${wrapper_bin}/zg-configure-back-sub.sh" --init
    WORK_LOG="${work_log}" bash "${wrapper_bin}/zg-pyqcd-back-sub.sh" --recursive
    WORK_LOG="${work_log}" bash "${wrapper_bin}/zg-myqcd-back-sub.sh" --dry-run
    WORK_LOG="${work_log}" bash "${wrapper_bin}/zg-pyqcu-back-sub.sh" --path refer/example

    grep -Fqx 'configure|--init' "${work_log}" || _fail "configure back-sub 目录或参数错误"
    grep -Fqx 'PyQCD|--recursive' "${work_log}" || _fail "PyQCD back-sub 目录或参数错误"
    grep -Fqx 'MyQCD|--dry-run' "${work_log}" || _fail "MyQCD back-sub 目录或参数错误"
    grep -Fqx 'PyQCU|--path refer/example' "${work_log}" || _fail "PyQCU back-sub 目录或参数错误"
}

main() {
    _test_parent_then_sorted_children
    _test_dry_run_skips_parent
    _test_failures_are_aggregated
    _test_wrappers_change_into_target_repositories
}

main "$@"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
