#!/usr/bin/env bash
# Force-align mapped submodules without touching parent repository checkouts.

_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

_usage() {
    cat <<'EOF'
Usage: zg-all-back-sub.sh [gback-sub options]

Force-align mapped submodules to the latest remote default branches. Parent
repository branches, indexes, commits, and worktrees are not restored or
otherwise checked. Child scripts are discovered from zg-*-back-sub.sh in this
directory; at least two are required.

Options and positional paths supported by gback-sub.sh are forwarded unchanged.
--dry-run only shows the submodule restore plan.
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
    echo "ERROR: Missing aggregate series helper: ${_PATH}/_all_series.sh" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "${_PATH}/_all_series.sh"
_all_series_discover "${_NAME}" "${_PATH}" || exit 1

echo "Matched: ${_ALL_SERIES_PATTERN} (${#_ALL_SERIES_SCRIPTS[@]} scripts)"
_all_series_run "$@"
_STATUS=${_ALL_SERIES_FAILED}

echo "Summary: failed=${_STATUS}"
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
exit "${_STATUS}"
