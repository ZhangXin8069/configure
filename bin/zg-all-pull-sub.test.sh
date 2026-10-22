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

_make_fixture() {
    local fixture=$1
    local wrapper_bin="${fixture}/configure/bin"
    local event_log="${fixture}/events.log"

    mkdir -p "${wrapper_bin}" \
        "${fixture}/configure/.git" \
        "${fixture}/PyQCD/.git" \
        "${fixture}/MyQCD/.git" \
        "${fixture}/PyQCU/.git"
    cp "${_PATH}/zg-all-pull-sub.sh" "${wrapper_bin}/"
    cp "${_PATH}/zg-configure-pull-sub.sh" "${wrapper_bin}/"
    cp "${_PATH}/zg-pyqcd-pull-sub.sh" "${wrapper_bin}/"
    cp "${_PATH}/zg-myqcd-pull-sub.sh" "${wrapper_bin}/"
    cp "${_PATH}/zg-pyqcu-pull-sub.sh" "${wrapper_bin}/"
    cp "${_PATH}/gpull-sub.sh" "${wrapper_bin}/"

    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'printf "parent-all\n" >> "${EVENT_LOG:?}"' \
        'exit "${PARENT_STATUS:-0}"' > "${wrapper_bin}/zg-all-pull.sh"

    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'printf "configure:%s\n" "$*" >> "${EVENT_LOG:?}"' \
        'exit "${CONFIGURE_STATUS:-0}"' > "${wrapper_bin}/zg-configure-pull-sub.sh"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'printf "pyqcd:%s\n" "$*" >> "${EVENT_LOG:?}"' \
        'exit "${PYQCD_STATUS:-0}"' > "${wrapper_bin}/zg-pyqcd-pull-sub.sh"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'printf "myqcd:%s\n" "$*" >> "${EVENT_LOG:?}"' \
        'exit "${MYQCD_STATUS:-0}"' > "${wrapper_bin}/zg-myqcd-pull-sub.sh"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'printf "pyqcu:%s\n" "$*" >> "${EVENT_LOG:?}"' \
        'exit "${PYQCU_STATUS:-0}"' > "${wrapper_bin}/zg-pyqcu-pull-sub.sh"
    chmod +x "${wrapper_bin}/"*.sh
}

_test_parent_and_all_repositories_run() {
    local fixture="${TEST_DIR}/all"
    local event_log="${fixture}/events.log"

    _make_fixture "${fixture}"
    EVENT_LOG="${event_log}" \
        bash "${fixture}/configure/bin/zg-all-pull-sub.sh" \
        > "${TEST_DIR}/all.log" 2>&1

    [[ "$(sed -n '1p' "${event_log}")" == parent-all ]] \
        || _fail "父仓库 pull 应先执行"
    grep -Fqx 'configure:' "${event_log}" || _fail "configure 未执行"
    grep -Fqx 'pyqcd:' "${event_log}" || _fail "PyQCD 未执行"
    grep -Fqx 'myqcd:' "${event_log}" || _fail "MyQCD 未执行"
    grep -Fqx 'pyqcu:' "${event_log}" || _fail "PyQCU 未执行"
}

_test_help_is_non_mutating() {
    local fixture="${TEST_DIR}/help"
    local event_log="${fixture}/events.log"

    _make_fixture "${fixture}"
    EVENT_LOG="${event_log}" \
        bash "${fixture}/configure/bin/zg-all-pull-sub.sh" --help \
        > "${TEST_DIR}/help.log" 2>&1

    grep -Fq 'Usage: zg-all-pull-sub.sh' "${TEST_DIR}/help.log" || _fail "缺少聚合帮助"
    [[ ! -e "${event_log}" ]] || _fail "help 不应更新父仓库或子模块"
}

_test_dry_run_skips_parent_and_forwards_arguments() {
    local fixture="${TEST_DIR}/dry-run"
    local event_log="${fixture}/events.log"

    _make_fixture "${fixture}"
    EVENT_LOG="${event_log}" \
        bash "${fixture}/configure/bin/zg-all-pull-sub.sh" --dry-run \
        > "${TEST_DIR}/dry-run.log" 2>&1

    ! grep -Fqx 'parent-all' "${event_log}" || _fail "dry-run 不应更新父仓库"
    grep -Fqx 'configure:--dry-run' "${event_log}" || _fail "configure 参数未透传"
    grep -Fqx 'pyqcd:--dry-run' "${event_log}" || _fail "PyQCD 参数未透传"
    grep -Fqx 'myqcd:--dry-run' "${event_log}" || _fail "MyQCD 参数未透传"
    grep -Fqx 'pyqcu:--dry-run' "${event_log}" || _fail "PyQCU 参数未透传"
}

_test_missing_repository_is_skipped() {
    local fixture="${TEST_DIR}/missing"
    local event_log="${fixture}/events.log"

    _make_fixture "${fixture}"
    rm -rf -- "${fixture}/PyQCU/.git"
    EVENT_LOG="${event_log}" \
        bash "${fixture}/configure/bin/zg-all-pull-sub.sh" \
        > "${TEST_DIR}/missing.log" 2>&1

    grep -Fq 'SKIP: PyQCU 不存在或不是 Git 仓库' "${TEST_DIR}/missing.log" \
        || _fail "缺少仓库时应明确跳过"
    ! grep -Fq 'pyqcu:' "${event_log}" || _fail "缺失仓库不应调用子模块包装器"
}

_test_failures_are_aggregated() {
    local fixture="${TEST_DIR}/failure"
    local event_log="${fixture}/events.log"

    _make_fixture "${fixture}"
    set +e
    EVENT_LOG="${event_log}" \
        PARENT_STATUS=4 \
        MYQCD_STATUS=5 \
        bash "${fixture}/configure/bin/zg-all-pull-sub.sh" \
        > "${TEST_DIR}/failure.log" 2>&1
    local status=$?
    set -e

    ((status != 0)) || _fail "父仓或子模块失败应聚合为非零"
    grep -Fqx 'pyqcd:' "${event_log}" || _fail "MyQCD 失败后仍应继续处理 PyQCU"
    grep -Fq 'pyqcu:' "${event_log}" || _fail "失败后未继续处理后续仓库"
    grep -Fq 'Summary: failed=1' "${TEST_DIR}/failure.log" || _fail "缺少失败汇总"
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
    _test_parent_and_all_repositories_run
    _test_help_is_non_mutating
    _test_dry_run_skips_parent_and_forwards_arguments
    _test_missing_repository_is_skipped
    _test_failures_are_aggregated
    _test_wrappers_change_into_target_repositories
}

main "$@"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
