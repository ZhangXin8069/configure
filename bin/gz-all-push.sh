#!/usr/bin/env bash
# Run every gz-*-push.sh sibling sequentially in filename order.

_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}

for _arg in "$@"; do
    case "${_arg}" in
        -h|--help)
            cat <<'EOF'
Usage: gz-all-push.sh

Run every gz-*-push.sh script in this directory in filename order. At least two
matching child scripts are required.
EOF
            exit 0
            ;;
    esac
done

echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

if [[ ! -r "${_PATH}/_all_series.sh" ]]; then
    echo "ERROR: Missing aggregate series helper: ${_PATH}/_all_series.sh" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "${_PATH}/_all_series.sh"
_all_series_discover "${_NAME}" "${_PATH}" || exit 1
echo "Matched: ${_ALL_SERIES_PATTERN} (${#_ALL_SERIES_SCRIPTS[@]} scripts)"

_all_series_run "$@"
echo "Summary: failed=${_ALL_SERIES_FAILED}"
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"

if (( _ALL_SERIES_FAILED > 0 )); then
    exit 1
fi
