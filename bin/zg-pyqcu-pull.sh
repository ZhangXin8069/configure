#!/usr/bin/env bash
_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}
_REPO_PATH="${_PATH}/../../PyQCU"
if [[ ${1:-} == --print-repo-path ]]; then
    printf '%s\n' "${_REPO_PATH}"
    exit 0
fi
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
pushd "${_REPO_PATH}" >/dev/null || exit 1
bash "${_PATH}/gpull.sh"
_STATUS=$?
popd >/dev/null || exit 1
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
exit "${_STATUS}"
