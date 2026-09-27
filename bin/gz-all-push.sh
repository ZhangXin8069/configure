#!/usr/bin/env bash
_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
bash ${_PATH}/gz-configure-push.sh
bash ${_PATH}/gz-pyqcd-push.sh
bash ${_PATH}/gz-myqcd-push.sh
bash ${_PATH}/gz-pyqcu-push.sh
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
