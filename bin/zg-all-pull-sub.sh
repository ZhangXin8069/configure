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

Update configure, PyQCD, MyQCD, and PyQCU parent repositories, then fast-forward
their mapped submodules. Missing parent repositories are cloned by zg-all-pull.sh.

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

_CONFIGURE_ROOT=$(cd "${_PATH}/.." && pwd) || {
    echo "ERROR: 无法解析 configure 仓库根目录。" >&2
    exit 1
}
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

_pull_repo_submodules() {
    local repo_name=$1
    local repo_path=$2
    local wrapper=$3
    shift 3

    if [[ ! -d "${repo_path}/.git" ]]; then
        echo "SKIP: ${repo_name} 不存在或不是 Git 仓库: ${repo_path}"
        return 0
    fi
    if [[ ! -r "${_PATH}/${wrapper}" ]]; then
        echo "ERROR: 找不到 ${repo_name} 子模块 pull 包装器: ${_PATH}/${wrapper}" >&2
        return 1
    fi

    echo "### ${repo_name} 参考子模块: ${repo_path} ###"
    bash "${_PATH}/${wrapper}" "$@" || return 1
}

_pull_repo_submodules configure "${_CONFIGURE_ROOT}" zg-configure-pull-sub.sh "$@" \
    || _STATUS=1
_pull_repo_submodules PyQCD "${_CONFIGURE_ROOT}/../PyQCD" zg-pyqcd-pull-sub.sh "$@" \
    || _STATUS=1
_pull_repo_submodules MyQCD "${_CONFIGURE_ROOT}/../MyQCD" zg-myqcd-pull-sub.sh "$@" \
    || _STATUS=1
_pull_repo_submodules PyQCU "${_CONFIGURE_ROOT}/../PyQCU" zg-pyqcu-pull-sub.sh "$@" \
    || _STATUS=1

echo "Summary: failed=${_STATUS}"
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
exit "${_STATUS}"
