#!/usr/bin/env bash
# SSH screen 公共辅助: screen 可用时创建或重连会话，不可用时告警并直接执行 SSH。

_screen_ssh_src=${BASH_SOURCE[0]:-${0}}
case "${_screen_ssh_src}" in
*/*) _screen_ssh_dir=${_screen_ssh_src%/*}; [ -n "${_screen_ssh_dir}" ] || _screen_ssh_dir="/" ;;
*) _screen_ssh_dir=. ;;
esac
if [[ "${_screen_ssh_dir}" == /* ]]; then
    _screen_ssh_path=${_screen_ssh_dir}
else
    _screen_ssh_path=$(cd "${_screen_ssh_dir}" && pwd)
fi

_SCREEN_GUIDE_PATH="${_screen_ssh_path}/_screen-guide.txt"
source "${_screen_ssh_path}/../lib/_screen.sh"
unset _screen_ssh_src _screen_ssh_dir _screen_ssh_path

_ssh_screen() {
    if (( $# < 1 )); then
        printf '用法: _ssh_screen <默认会话名> <ssh 参数...>\n' >&2
        return 64
    fi

    local default_session_name=$1
    shift
    local session_name=${SSH_SCREEN_NAME:-${default_session_name}}
    [[ -n "${session_name}" ]] || session_name=$(_screen_client_name)

    if ! _screen_is_available; then
        _screen_warn_unavailable
        command ssh "$@"
        return
    fi

    local screen_bin=${SCREEN_BIN:-screen}
    command "${screen_bin}" -t "${session_name}" -S "${session_name}" -d -R sh -c \
        'printf "\033k%s\033\\" "${STY:-}"; exec ssh "$@"' sh "$@"
}
