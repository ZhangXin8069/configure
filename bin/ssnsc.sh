#!/usr/bin/env bash
_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
source "${_PATH}/_ssh_screen.sh"
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

_usage() {
    echo "用法: ssnsc [--screen]" >&2
    echo "  --screen  在远端创建或进入同名 screen 会话（默认关闭）" >&2
}

use_screen=0
while (( $# > 0 )); do
    case "$1" in
        --screen) use_screen=1; shift;;
        --no-screen) use_screen=0; shift;;
        -h|--help) _usage; exit 0;;
        *) echo "###${_NAME}: 未知参数 '$1'###" >&2; _usage; exit 64;;
    esac
done

screen_arg=()
if (( use_screen )); then screen_arg=(--screen); fi
_ssh_screen "${_NAME}" "${screen_arg[@]}" \
    -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
    -p 10023 -l zhangxin 222.200.137.16
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
