#!/usr/bin/env bash
# Update parent repositories first, then fast-forward their mapped submodules.

_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then
    _PATH="${_DIR}"
else
    _PATH=$(cd "${_DIR}" && pwd)
fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

_usage() {
    cat <<'EOF'
Usage: zg-all-pull-sub.sh [gpull-sub options]

Update managed parent repositories, then fast-forward their mapped submodules.
Missing parent repositories are cloned by zg-all-pull.sh.

Repository child scripts are discovered from zg-*-pull-sub.sh in this directory;
at least two matching scripts must exist. Matches run sequentially by filename.
Options and positional paths supported by gpull-sub.sh are forwarded unchanged.
--dry-run skips all parent-repository updates and only shows the submodule plan.
EOF
}

for _arg in "$@"; do
    case "${_arg}" in
        -h|--help)
            _usage
            exit 0
            ;;
    esac
done

if [[ ! -r "${_PATH}/_all_series.sh" ]]; then
    echo "ERROR: 找不到聚合脚本发现器: ${_PATH}/_all_series.sh" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "${_PATH}/_all_series.sh"
_all_series_discover "${_NAME}" "${_PATH}" || exit 1

_ZG_ALL_PULL="${_PATH}/zg-all-pull.sh"
if [[ ! -r "${_ZG_ALL_PULL}" ]]; then
    echo "ERROR: 找不到父仓库 pull 聚合脚本: ${_ZG_ALL_PULL}" >&2
    exit 1
fi

_STATUS=0
_DRY_RUN=0
for _arg in "$@"; do
    case "${_arg}" in
        --dry-run) _DRY_RUN=1 ;;
    esac
done

if (( _DRY_RUN )); then
    echo "DRY-RUN: 跳过父仓库 pull（仅展示已存在仓库的子模块更新计划）。"
else
    bash "${_ZG_ALL_PULL}" || _STATUS=1
fi

echo "Matched: ${_ALL_SERIES_PATTERN} (${#_ALL_SERIES_SCRIPTS[@]} scripts)"
_all_series_run "$@"
_STATUS=$((_STATUS + _ALL_SERIES_FAILED))

echo "Summary: failed=${_STATUS}"
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
exit "${_STATUS}"
