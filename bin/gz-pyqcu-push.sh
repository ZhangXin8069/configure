#!/usr/bin/env bash
_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
pushd "${_PATH}/../../PyQCU" >/dev/null || exit 1
bash "${_PATH}/gpush.sh" "$@"
_STATUS=$?
popd >/dev/null || exit 1
if (( _STATUS != 0 )); then
    echo "###${_NAME} in ${_PATH} failed......:$(date "+%Y-%m-%d-%H-%M-%S")###" >&2
    exit "${_STATUS}"
fi
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
