#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

TEST_DIR="${_PATH}/.gz-all-push-test.$$"
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
    cp "${_PATH}/gz-all-push.sh" "${fixture}/bin/"
    cp "${_PATH}/_all_series.sh" "${fixture}/bin/"
    _write_child "${fixture}/bin/gz-alpha-push.sh" alpha ALPHA_STATUS
    _write_child "${fixture}/bin/gz-zeta-push.sh" zeta ZETA_STATUS
}

_test_sorted_execution_and_failure_aggregation() {
    local fixture="${TEST_DIR}/ordered"
    local event_log="${fixture}/events.log"

    _make_fixture "${fixture}"
    EVENT_LOG="${event_log}" bash "${fixture}/bin/gz-all-push.sh" \
        > "${TEST_DIR}/ordered.log" 2>&1
    [[ "$(paste -sd, "${event_log}")" == alpha,zeta ]] || _fail "push 子系列未按文件名执行"

    : > "${event_log}"
    set +e
    EVENT_LOG="${event_log}" ALPHA_STATUS=7 bash "${fixture}/bin/gz-all-push.sh" \
        > "${TEST_DIR}/failure.log" 2>&1
    local status=$?
    set -e
    ((status != 0)) || _fail "push 子系列失败应传播"
    [[ "$(paste -sd, "${event_log}")" == alpha,zeta ]] || _fail "失败后未继续后续 push"
    grep -Fq 'Summary: failed=1' "${TEST_DIR}/failure.log" || _fail "失败汇总错误"
}

_test_requires_multiple_matching_children() {
    local fixture="${TEST_DIR}/minimum"
    local status

    _make_fixture "${fixture}"
    rm -f -- "${fixture}/bin/gz-zeta-push.sh"
    set +e
    bash "${fixture}/bin/gz-all-push.sh" > "${TEST_DIR}/minimum.log" 2>&1
    status=$?
    set -e
    ((status != 0)) || _fail "少于两个 push 子系列时应失败"
    grep -Fq 'requires at least 2 matching' "${TEST_DIR}/minimum.log" \
        || _fail "缺少最小子系列数量错误"
}

main() {
    _test_sorted_execution_and_failure_aggregation
    _test_requires_multiple_matching_children
}

main "$@"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
