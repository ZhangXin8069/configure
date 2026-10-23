#!/usr/bin/env bash
_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}
_REPO_PATH="${_PATH}/../../PyQCD"
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
if [[ ! -e "${_REPO_PATH}/.git" ]]; then
    echo "SKIP: PyQCD is not a Git checkout: ${_REPO_PATH}"
    exit 0
fi
pushd "${_REPO_PATH}" >/dev/null || exit 1
bash "${_PATH}/gback.sh" "$@"
_STATUS=$?
popd >/dev/null || exit 1
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
exit "${_STATUS}"
