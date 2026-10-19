#!/usr/bin/env bash
# 依次以各仓库的远程上游为基准执行 gback.sh；不存在的兄弟仓库仅跳过。

_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in
    */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/" ;;
    *) _DIR=. ;;
esac
if [[ "${_DIR}" == /* ]]; then
    _PATH="${_DIR}"
else
    _PATH=$(cd "${_DIR}" && pwd)
fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

_CONFIGURE_ROOT=$(cd "${_PATH}/.." && pwd) || {
    echo "ERROR: 无法解析 configure 仓库根目录。"
    exit 1
}
_GBACK_PATH="${_PATH}/gback.sh"
if [[ ! -r "${_GBACK_PATH}" ]]; then
    echo "ERROR: 找不到可读取的恢复脚本: ${_GBACK_PATH}"
    exit 1
fi
_FAILED=0
_RESTORED=0
_SKIPPED=0

_restore_repo() {
    local repo_name=$1
    local repo_path=$2

    if [[ ! -d "${repo_path}/.git" ]]; then
        echo "SKIP: ${repo_name} 不存在或不是 Git 仓库: ${repo_path}"
        ((_SKIPPED += 1))
        return 0
    fi

    echo "### ${repo_name}: ${repo_path} ###"
    if (cd "${repo_path}" && bash "${_GBACK_PATH}"); then
        echo "OK: ${repo_name} 已按远程上游恢复"
        ((_RESTORED += 1))
    else
        echo "ERROR: ${repo_name} 恢复失败，继续处理其余仓库"
        ((_FAILED += 1))
    fi
}

_restore_repo PyQCD "${_CONFIGURE_ROOT}/../PyQCD"
_restore_repo MyQCD "${_CONFIGURE_ROOT}/../MyQCD"
_restore_repo PyQCU "${_CONFIGURE_ROOT}/../PyQCU"
_restore_repo configure "${_CONFIGURE_ROOT}"

echo "Summary: restored=${_RESTORED} skipped=${_SKIPPED} failed=${_FAILED}"
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"

if ((_FAILED > 0)); then
    exit 1
fi
