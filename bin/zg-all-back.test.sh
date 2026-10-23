#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

TEST_DIR="${_PATH}/.zg-all-back-test.$$"
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
        "printf '%s\\n' '${label}' >> \"\${EVENT_LOG:?}\"" \
        "exit \"\${${status_var}:-0}\"" > "${path}"
    chmod +x "${path}"
}

_make_fixture() {
    local fixture=$1

    mkdir -p "${fixture}/bin"
    cp "${_PATH}/zg-all-back.sh" "${fixture}/bin/"
    cp "${_PATH}/_all_series.sh" "${fixture}/bin/"
    _write_child "${fixture}/bin/zg-alpha-back.sh" alpha ALPHA_STATUS
    _write_child "${fixture}/bin/zg-zeta-back.sh" zeta ZETA_STATUS
}

_test_sorted_execution_and_failure_aggregation() {
    local fixture="${TEST_DIR}/ordered"
    local event_log="${fixture}/events.log"

    _make_fixture "${fixture}"
    EVENT_LOG="${event_log}" bash "${fixture}/bin/zg-all-back.sh" \
        > "${TEST_DIR}/ordered.log" 2>&1
    [[ "$(paste -sd, "${event_log}")" == alpha,zeta ]] || _fail "back 子系列未按文件名执行"

    : > "${event_log}"
    set +e
    EVENT_LOG="${event_log}" ALPHA_STATUS=6 bash "${fixture}/bin/zg-all-back.sh" \
        > "${TEST_DIR}/failure.log" 2>&1
    local status=$?
    set -e
    ((status != 0)) || _fail "back 子系列失败应传播"
    [[ "$(paste -sd, "${event_log}")" == alpha,zeta ]] || _fail "失败后未继续后续 back"
    grep -Fq 'Summary: failed=1' "${TEST_DIR}/failure.log" || _fail "失败汇总错误"
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
    cp "${_PATH}/zg-configure-back.sh" "${wrapper_bin}/"
    cp "${_PATH}/zg-pyqcd-back.sh" "${wrapper_bin}/"
    cp "${_PATH}/zg-myqcd-back.sh" "${wrapper_bin}/"
    cp "${_PATH}/zg-pyqcu-back.sh" "${wrapper_bin}/"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'printf "%s\n" "${PWD##*/}" >> "${WORK_LOG:?}"' > "${wrapper_bin}/gback.sh"
    chmod +x "${wrapper_bin}/"*.sh

    WORK_LOG="${work_log}" bash "${wrapper_bin}/zg-configure-back.sh"
    WORK_LOG="${work_log}" bash "${wrapper_bin}/zg-pyqcd-back.sh"
    WORK_LOG="${work_log}" bash "${wrapper_bin}/zg-myqcd-back.sh"
    WORK_LOG="${work_log}" bash "${wrapper_bin}/zg-pyqcu-back.sh"

    [[ "$(paste -sd, "${work_log}")" == configure,PyQCD,MyQCD,PyQCU ]] \
        || _fail "back 包装器目标目录错误"
}

main() {
    _test_sorted_execution_and_failure_aggregation
    _test_wrappers_change_into_target_repositories
}

main "$@"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
