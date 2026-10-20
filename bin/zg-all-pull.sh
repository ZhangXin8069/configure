#!/usr/bin/env bash
_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

_CLONE_PROTOCOL=${ZG_GIT_PROTOCOL:-auto}
case "${_CLONE_PROTOCOL}" in
    auto|https|ssh) ;;
    *)
        echo "ERROR: ZG_GIT_PROTOCOL must be one of: auto, https, ssh." >&2
        exit 64
        ;;
esac

_clone_url() {
    case "$1" in
        https) printf 'https://gitee.com/zhangxin8069/%s.git\n' "$2" ;;
        ssh) printf 'git@gitee.com:zhangxin8069/%s.git\n' "$2" ;;
    esac
}

_clone_repo() {
    local repo=$1
    local target=$2
    local protocol=$3
    local url

    url=$(_clone_url "${protocol}" "${repo}")
    git clone "${url}" "${target}" 2>/dev/null
}

ensure_repo() {
    local dir=$1 repo=$2
    if [ ! -d "${_PATH}/${dir}/.git" ]; then
        echo "### ${repo} 本地不存在，git clone ... ###"
        case "${_CLONE_PROTOCOL}" in
            ssh)
                _clone_repo "${repo}" "${_PATH}/${dir}" ssh \
                    && echo "### ${repo} 已 clone (ssh) ###" \
                    || echo "### ${repo} clone 失败，跳过 pull ###"
                ;;
            https)
                _clone_repo "${repo}" "${_PATH}/${dir}" https \
                    && echo "### ${repo} 已 clone (https) ###" \
                    || echo "### ${repo} clone 失败，跳过 pull ###"
                ;;
            auto)
                if _clone_repo "${repo}" "${_PATH}/${dir}" ssh; then
                    echo "### ${repo} 已 clone (ssh) ###"
                elif rm -rf "${_PATH}/${dir}" \
                    && _clone_repo "${repo}" "${_PATH}/${dir}" https; then
                    echo "### ${repo} 已 clone (https) ###"
                else
                    echo "### ${repo} clone 失败，跳过 pull ###"
                fi
                ;;
        esac
        return 1
    fi
    return 0
}

PYQCD_CLONED=0
ensure_repo ../../PyQCD PyQCD || PYQCD_CLONED=1
MYQCD_CLONED=0
ensure_repo ../../MyQCD MyQCD || MYQCD_CLONED=1
PYQCU_CLONED=0
ensure_repo ../../PyQCU PyQCU || PYQCU_CLONED=1

_STATUS=0
bash "${_PATH}/zg-configure-pull.sh" || _STATUS=1
[ "${PYQCD_CLONED}" -ne 0 ] || bash "${_PATH}/zg-pyqcd-pull.sh" || _STATUS=1
[ "${MYQCD_CLONED}" -ne 0 ] || bash "${_PATH}/zg-myqcd-pull.sh" || _STATUS=1
[ "${PYQCU_CLONED}" -ne 0 ] || bash "${_PATH}/zg-pyqcu-pull.sh" || _STATUS=1

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
exit "${_STATUS}"
