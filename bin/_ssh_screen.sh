#!/usr/bin/env bash
# SSH 公共辅助: 先建立 SSH，再在远端创建独立的 UTF-8 screen 会话。

_ssh_screen_quote() {
    local value=$1 single_quote="'" escaped_quote="'\\''"
    value=${value//${single_quote}/${escaped_quote}}
    printf "'%s'" "${value}"
}

_ssh_screen_powershell_quote() {
    local value=$1 single_quote="'" escaped_quote="''"
    value=${value//${single_quote}/${escaped_quote}}
    printf "'%s'" "${value}"
}

_ssh_screen_client_hostname() {
    local fallback=${1:-ssh-client} client_host=${SSH_SCREEN_NAME:-}
    if [[ -z "${client_host}" ]]; then
        client_host=$(hostname 2>/dev/null || true)
    fi
    if [[ -z "${client_host}" ]]; then
        client_host=${HOSTNAME:-}
    fi
    if [[ -z "${client_host}" ]]; then
        client_host=$(uname -n 2>/dev/null || true)
    fi
    client_host=${client_host//[^A-Za-z0-9_.-]/_}
    printf '%s' "${client_host:-${fallback:-ssh-client}}"
}

_ssh_screen_powershell_script() {
    local session_name=$1 remote_command=${2:-} quoted_session quoted_command screen_path host_shell
    quoted_session=$(_ssh_screen_powershell_quote "${session_name}")
    screen_path='$screenCommand.Path'
    host_shell='$hostShell'
    printf '%s\n' \
        '$ErrorActionPreference = '\''SilentlyContinue'\''' \
        '$screenCommand = Get-Command screen -ErrorAction SilentlyContinue' \
        '$screenTerm = '\''screen'\''' \
        '$infocmpCommand = Get-Command infocmp -ErrorAction SilentlyContinue' \
        'if ($null -ne $infocmpCommand) {' \
        '    & $infocmpCommand.Path screen-256color *> $null' \
        '    if ($LASTEXITCODE -eq 0) { $screenTerm = '\''screen-256color'\'' }' \
        '}' \
        '$hostShell = (Get-Process -Id $PID).Path' \
        'if ([string]::IsNullOrWhiteSpace($hostShell)) { $hostShell = '\''powershell.exe'\'' }'
    if [[ -n "${remote_command}" ]]; then
        quoted_command=$(_ssh_screen_powershell_quote "${remote_command}")
        printf '%s\n' \
            "\$remoteCommand = ${quoted_command}" \
            'if ($null -ne $screenCommand) {' \
            "    & ${screen_path} -U -T \$screenTerm -S ${quoted_session} -t ${quoted_session}; & ${host_shell} -NoLogo -NoProfile -Command \$remoteCommand" \
            '} else {' \
            '    Write-Warning '\''remote screen is unavailable; continuing without it.'\''' \
            '    Invoke-Expression $remoteCommand' \
            "    & ${host_shell} -NoLogo -NoProfile" \
            '}'
        return 0
    fi
    printf '%s\n' \
        'if ($null -ne $screenCommand) {' \
        "    & ${screen_path} -U -T \$screenTerm -S ${quoted_session} -t ${quoted_session}" \
        '} else {' \
        '    Write-Warning '\''remote screen is unavailable; continuing without it.'\''' \
        "    & ${host_shell} -NoLogo -NoProfile" \
        '}'
}

_ssh_screen_remote_script() {
    local session_name=$1 remote_command=${2:-} remote_shell=${3:-posix} quoted_session quoted_command
    case "${remote_shell}" in
        posix|powershell) ;;
        *)
            printf '_ssh_screen: 不支持的 SSH_REMOTE_SHELL=%s（允许 posix/powershell）\n' "${remote_shell}" >&2
            return 64
            ;;
    esac
    if [[ "${remote_shell}" == powershell ]]; then
        _ssh_screen_powershell_script "${session_name}" "${remote_command}"
        return
    fi
    quoted_session=$(_ssh_screen_quote "${session_name}")
    if [[ -n "${remote_command}" ]]; then
        quoted_command=$(_ssh_screen_quote "${remote_command}")
        printf '%s\n' \
            'if command -v screen >/dev/null 2>&1; then' \
            '    screen_term=screen' \
            '    if command -v infocmp >/dev/null 2>&1 && infocmp screen-256color >/dev/null 2>&1; then' \
            '        screen_term=screen-256color' \
            '    fi' \
            "    exec screen -U -T \"\${screen_term}\" -S ${quoted_session} -t ${quoted_session} sh -lc ${quoted_command}" \
            'fi' \
            "printf '%s\\n' '[WARN] remote screen is unavailable; continuing without it.' >&2" \
            "exec sh -lc ${quoted_command}"
        return 0
    fi
    printf '%s\n' \
        'if command -v screen >/dev/null 2>&1; then' \
        '    screen_term=screen' \
        '    if command -v infocmp >/dev/null 2>&1 && infocmp screen-256color >/dev/null 2>&1; then' \
        '        screen_term=screen-256color' \
        '    fi' \
        "    exec screen -U -T \"\${screen_term}\" -S ${quoted_session} -t ${quoted_session}" \
        'fi' \
        "printf '%s\\n' '[WARN] remote screen is unavailable; continuing without it.' >&2" \
        'exec "${SHELL:-/bin/sh}" -l'
}

_ssh_screen() {
    if (( $# < 1 )); then
        printf '用法: _ssh_screen <回退会话名> <ssh 参数...> [-- <远端命令>]\n' >&2
        return 64
    fi

    local fallback_session_name=$1
    shift
    local -a ssh_args=()
    local remote_command='' arg has_tty=0
    while (( $# > 0 )); do
        if [[ "$1" == '--' ]]; then
            shift
            remote_command="$*"
            break
        fi
        ssh_args+=("$1")
        shift
    done
    if (( ${#ssh_args[@]} == 0 )); then
        printf '_ssh_screen: 缺少 SSH 目标参数\n' >&2
        return 64
    fi
    for arg in "${ssh_args[@]}"; do
        case "${arg}" in
            -t|-tt) has_tty=1 ;;
        esac
    done
    if (( has_tty == 0 )); then
        ssh_args=(-t "${ssh_args[@]}")
    fi

    local session_name remote_script remote_shell=${SSH_REMOTE_SHELL:-posix}
    session_name=$(_ssh_screen_client_hostname "${fallback_session_name}")
    remote_script=$(_ssh_screen_remote_script "${session_name}" "${remote_command}" "${remote_shell}") || return $?
    command ssh "${ssh_args[@]}" "${remote_script}"
}
