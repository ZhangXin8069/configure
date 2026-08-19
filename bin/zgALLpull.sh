#!/usr/bin/env bash
_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

ensure_repo() {
    local dir=$1 repo=$2
    if [ ! -d "${_PATH}/${dir}/.git" ]; then
        echo "### ${repo} 本地不存在，git clone ... ###"
        if git clone "git@gitee.com:zhangxin8069/${repo}.git" "${_PATH}/${dir}" 2>/dev/null; then
            echo "### ${repo} 已 clone (ssh) ###"
        elif rm -rf "${_PATH}/${dir}" \
            && git clone "https://gitee.com/zhangxin8069/${repo}.git" "${_PATH}/${dir}" 2>/dev/null; then
            echo "### ${repo} 已 clone (https) ###"
        else
            echo "### ${repo} clone 失败，跳过 pull ###"
        fi
        return 1
    fi
    return 0
}

PYQCD_CLONED=0
ensure_repo ../../PyQCD PyQCD || PYQCD_CLONED=1
PYQCU_CLONED=0
ensure_repo ../../PyQCU PyQCU || PYQCU_CLONED=1

bash ${_PATH}/zgCONFIGUREpull.sh
[ "${PYQCD_CLONED}" -eq 0 ] && bash ${_PATH}/zgPyQCDpull.sh
[ "${PYQCU_CLONED}" -eq 0 ] && bash ${_PATH}/zgPYQCUpull.sh

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
