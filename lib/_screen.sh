#!/usr/bin/env bash
# screen 公共辅助: 默认会话名取 SSH 客户端地址，供 env.sh 与 bin/_ssh_screen.sh 复用。

_screen_is_available() {
    local screen_bin=${SCREEN_BIN:-screen}
    command -v "${screen_bin}" >/dev/null 2>&1
}

_screen_client_name() {
    local requested=${1:-${SSH_SCREEN_NAME:-}}
    if [[ -z "${requested}" ]]; then
        requested=${SSH_CLIENT:-${SSH_CONNECTION:-}}
        requested=${requested%% *}
    fi
    printf '%s' "${requested:-local}"
}

_screen_warn_unavailable() {
    if [[ -n "${_SCREEN_GUIDE_PATH:-}" && -r "${_SCREEN_GUIDE_PATH}" ]]; then
        command cat "${_SCREEN_GUIDE_PATH}" >&2
    else
        printf '%s\n' \
            '[WARN] screen 不可用，已跳过持久会话，继续执行原命令。' \
            '安装 screen：' \
            '  Debian/Ubuntu: sudo apt update && sudo apt install screen' \
            '  RHEL/CentOS/Fedora: sudo dnf install screen（旧版使用 sudo yum install screen）' \
            '  Arch/Manjaro: sudo pacman -S screen' \
            '  openSUSE: sudo zypper install screen' \
            '  Alpine: sudo apk add screen' \
            '  FreeBSD: sudo pkg install screen' \
            '  macOS: brew install screen（或 sudo port install screen）' \
            '使用: screen -t <名字> -S <名字>; Ctrl+a d; screen -ls; screen -dr <名字>' >&2
    fi
}

_screen_exec() {
    local screen_bin=${SCREEN_BIN:-screen}
    if ! _screen_is_available; then
        _screen_warn_unavailable
        return 127
    fi
    command "${screen_bin}" "$@"
}

_screen_new() {
    local session_name
    session_name=$(_screen_client_name "${1:-}")
    _screen_exec -t "${session_name}" -S "${session_name}" sh -c \
        'printf "\033k%s\033\\" "${STY:-}"; exec "${SHELL:-/bin/sh}"' sh
}

_screen_list() {
    _screen_exec -ls
}

_screen_resume() {
    local session_name
    session_name=$(_screen_client_name "${1:-}")
    _screen_exec -t "${session_name}" -dr "${session_name}"
}
