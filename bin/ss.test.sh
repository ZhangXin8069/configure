#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

test_root=$(mktemp -d "${TMPDIR:-/tmp}/configure-ss-test.XXXXXX")

_cleanup() {
    rm -rf -- "$test_root"
}
trap _cleanup EXIT HUP INT TERM

_fail() {
    echo "FAIL: $*" >&2
    exit 1
}

_run_ss() {
    if [[ "$1" == "__NO_ARG__" ]]; then
        bash "${_PATH}/ss.sh"
    else
        bash "${_PATH}/ss.sh" "$1"
    fi
}

_assert_target() {
    local input=$1
    local expected=$2
    local output

    output=$(_run_ss "${input}" 2>/dev/null)
    if ! grep -Fq -- "${expected}" <<< "${output}"; then
        _fail "输入 ${input} 应连接 ${expected}，实际输出：${output}"
    fi
}

main() {
    local bat_file="${_PATH}/ss.bat"
    local ps1_file="${_PATH}/ss.ps1"
    local fake_bin=$test_root/fake-bin
    local fake_ssh=$fake_bin/ssh
    local fake_remote_screen=$fake_bin/screen
    local fake_hostname=$fake_bin/hostname
    local local_screen_log=$test_root/local-screen.log
    local output
    local status

    mkdir -p "$fake_bin"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'printf "%s\\n" "$*"' \
        'exit "${SSH_FAKE_STATUS:-0}"' >"$fake_ssh"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'if [[ -n "${SCREEN_FAKE_LOG:-}" ]]; then printf "%s\\n" "$*" >> "$SCREEN_FAKE_LOG"; fi' \
        'printf "%s\\n" "$*"' >"$fake_remote_screen"
    printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\\n" "ssh-client-host"' >"$fake_hostname"
    chmod +x "$fake_ssh" "$fake_remote_screen" "$fake_hostname"
    export PATH="$fake_bin:$PATH"
    export SCREEN_BIN="$test_root/missing-screen"
    export SSH_SCREEN_NAME=''
    export SSH_REMOTE_SHELL=''
    export HOSTNAME=stale-hostname

    _assert_target 42 "-t -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l zhangxin 192.168.188.42"
    _assert_target 1 "-t -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l zhangxin 192.168.188.1"
    _assert_target 254 "-t -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l zhangxin 192.168.188.254"
    _assert_target 20 "-t -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l kfutfd 192.168.188.20"
    _assert_target 19 "-t -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l kfutfd 192.168.188.19"
    _assert_target 3 "-t -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l zhang 192.168.188.3"
    _assert_target k42 "-t -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l kfutfd 192.168.188.42"
    _assert_target y42 "-t -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l yang 192.168.188.42"
    _assert_target __NO_ARG__ "-t -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l kfutfd 192.168.188.19"

    for windows_target in 19 20 z20; do
        output=$(SSH_SCREEN_NAME='' _run_ss "${windows_target}" 2>/dev/null)
        grep -Fq '$ErrorActionPreference' <<<"$output" ||
            _fail "${windows_target} 号 Windows 目标未使用 PowerShell 远端脚本"
        if grep -Fq 'if command -v screen' <<<"$output"; then
            _fail "${windows_target} 号 Windows 目标仍收到 PowerShell 无法解析的 POSIX 条件语句"
        fi
        if grep -Fq 'exec "${SHELL:-/bin/sh}" -l' <<<"$output"; then
            _fail "${windows_target} 号 Windows 目标仍收到 POSIX 登录 shell"
        fi
    done

    output=$(SSH_REMOTE_SHELL=powershell SSH_SCREEN_NAME='' _run_ss 42 2>/dev/null)
    grep -Fq 'Get-Process -Id $PID' <<<"$output" ||
        _fail "SSH_REMOTE_SHELL=powershell 未覆盖远端脚本类型"

    output=$(SSH_REMOTE_SHELL=posix SSH_SCREEN_NAME='' _run_ss 19 2>/dev/null)
    grep -Fq 'exec "${SHELL:-/bin/sh}" -l' <<<"$output" ||
        _fail "SSH_REMOTE_SHELL=posix 未覆盖已知目标默认值"

    # 默认不启用 screen：远端脚本只能是登录 shell，不得含 screen 启动逻辑
    output=$(SSH_REMOTE_SHELL=posix SSH_SCREEN_NAME='' _run_ss 42 2>/dev/null)
    if grep -Fq 'command -v screen' <<<"$output"; then
        _fail "默认不应在远端启动 screen"
    fi
    [[ "$output" == *'exec "${SHELL:-/bin/sh}" -l'* ]] ||
        _fail "默认远端命令应为登录 shell：$output"

    output=$(SSH_REMOTE_SHELL=powershell SSH_SCREEN_NAME='' _run_ss 42 2>/dev/null)
    if grep -Fq 'Get-Command screen' <<<"$output"; then
        _fail "默认不应在 PowerShell 远端启动 screen"
    fi

    : > "$local_screen_log"
    output=$(SCREEN_FAKE_LOG="$local_screen_log" SSH_SCREEN_NAME='' _run_ss 42 2>/dev/null)
    [[ ! -s "$local_screen_log" ]] || _fail "本地 screen 不应在 SSH 前启动"
    output=$(SSH_SCREEN_NAME='' bash -c 'source "$1"; _ssh_screen ss --screen -p 22 user@example.test' configure-ssh-test "${_PATH}/_ssh_screen.sh" 2>/dev/null)
    grep -Fq "exec screen -U -T \"\${screen_term}\" -S 'ssh-client-host' -t 'ssh-client-host'" <<<"$output" ||
        _fail "--screen 未使用客户端主机名创建新 screen"
    grep -Fq 'if command -v screen >/dev/null 2>&1; then' <<<"$output" ||
        _fail "--screen 远端命令未先检测 screen"
    if grep -Eq -- '(^| )-(r|R)( |$)|-d -R' <<<"$output"; then
        _fail "SSH screen 逻辑仍会自动重连旧会话"
    fi

    output=$(SSH_SCREEN_NAME='manual-name' bash -c 'source "$1"; _ssh_screen ss --screen -p 22 user@example.test' configure-ssh-test "${_PATH}/_ssh_screen.sh" 2>/dev/null)
    grep -Fq "exec screen -U -T \"\${screen_term}\" -S 'manual-name' -t 'manual-name'" <<<"$output" ||
        _fail "SSH_SCREEN_NAME 未覆盖客户端主机名"

    output=$(HOSTNAME=ssh-client-host SSH_SCREEN_NAME='' bash -c '
        source "$1"
        _ssh_screen ss --screen -p 22 user@example.test -- "ddocker.bat; exec bash -l"
    ' configure-ssh-test "${_PATH}/_ssh_screen.sh" 2>/dev/null)
    grep -Fq "exec screen -U -T \"\${screen_term}\" -S 'ssh-client-host' -t 'ssh-client-host' sh -lc 'ddocker.bat; exec bash -l'" <<<"$output" ||
        _fail "既有远端命令未放入新 screen 内执行"

    output=$(SSH_SCREEN_NAME='' bash -c '
        source "$1"
        _ssh_screen ss -p 22 user@example.test -- "printf remote-ok"
    ' configure-ssh-test "${_PATH}/_ssh_screen.sh" 2>/dev/null)
    grep -Fq "exec sh -lc 'printf remote-ok'" <<<"$output" ||
        _fail "默认应直接执行远端命令而不包裹 screen"
    if grep -Fq 'screen' <<<"$output"; then
        _fail "默认远端命令不应包含 screen"
    fi

    remote_script=$(bash -c 'source "$1"; _ssh_screen_remote_script ssh-client-host' configure-ssh-test "${_PATH}/_ssh_screen.sh")
    [[ "$remote_script" == 'exec "${SHELL:-/bin/sh}" -l' ]] ||
        _fail "默认远端脚本参数错误：$remote_script"

    remote_script=$(bash -c 'source "$1"; _ssh_screen_remote_script ssh-client-host "" posix 1' configure-ssh-test "${_PATH}/_ssh_screen.sh")
    output=$(PATH="$fake_bin:$PATH" sh -c "$remote_script")
    [[ "$output" == '-U -T screen-256color -S ssh-client-host -t ssh-client-host' ]] ||
        _fail "远端 screen 启动脚本参数错误：$output"

    remote_script=$(bash -c 'source "$1"; _ssh_screen_remote_script ssh-client-host "printf remote-ok" posix 1' configure-ssh-test "${_PATH}/_ssh_screen.sh")
    output=$(PATH="$fake_bin:$PATH" sh -c "$remote_script")
    [[ "$output" == '-U -T screen-256color -S ssh-client-host -t ssh-client-host sh -lc printf remote-ok' ]] ||
        _fail "远端 screen 未正确包装既有命令：$output"

    remote_script=$(bash -c 'source "$1"; _ssh_screen_remote_script ssh-client-host "" powershell 0' configure-ssh-test "${_PATH}/_ssh_screen.sh")
    if grep -Fq 'Get-Command screen' <<<"$remote_script"; then
        _fail "默认 PowerShell 远端脚本不应检测 screen"
    fi
    grep -Fq '$hostShell -NoLogo -NoProfile' <<<"$remote_script" ||
        _fail "PowerShell 远端脚本缺少交互 shell"

    remote_script=$(bash -c 'source "$1"; _ssh_screen_remote_script ssh-client-host "" powershell 1' configure-ssh-test "${_PATH}/_ssh_screen.sh")
    grep -Fq 'Get-Command screen' <<<"$remote_script" ||
        _fail "PowerShell 远端脚本未检测 screen"
    grep -Fq '$hostShell -NoLogo -NoProfile' <<<"$remote_script" ||
        _fail "PowerShell 远端脚本缺少交互 shell 降级"
    if grep -Eq 'if command -v screen|>&2|exec "\$\{SHELL|screenCommand.Path.* & \$hostShell' <<<"$remote_script"; then
        _fail "PowerShell 远端脚本混入 POSIX 专用语法"
    fi

    remote_script=$(bash -c 'source "$1"; _ssh_screen_remote_script ssh-client-host "Write-Output '\''it'\'''\''s routed'\''" powershell 1' configure-ssh-test "${_PATH}/_ssh_screen.sh")
    expected_remote_ps="\$remoteCommand = 'Write-Output ''it''''s routed'''"
    grep -Fq "$expected_remote_ps" <<<"$remote_script" ||
        _fail "PowerShell 远端命令单引号未正确转义"

    fallback_bin=$test_root/fallback-bin
    mkdir -p "$fallback_bin"
    ln -s "$(command -v sh)" "$fallback_bin/sh"
    remote_command=$'printf '\''%s\n'\'' "it'\''s routed"'
    remote_script=$(bash -c 'source "$1"; _ssh_screen_remote_script ssh-client-host "$2"' configure-ssh-test "${_PATH}/_ssh_screen.sh" "$remote_command")
    output=$(PATH="$fallback_bin" /bin/sh -c "$remote_script" 2>/dev/null)
    [[ "$output" == "it's routed" ]] || _fail "远端命令单引号转义错误：$output"

    set +e
    SSH_FAKE_STATUS=37 _run_ss 42 >/dev/null 2>/dev/null
    status=$?
    set -e
    (( status == 37 )) || _fail "SSH 失败时应保留退出码 37，实际为 $status"

    grep -Fq 'command ssh "${ssh_args[@]}" "${remote_script}"' "${_PATH}/_ssh_screen.sh" ||
        _fail "_ssh_screen.sh 未在 SSH 建立后注入远端命令"
    if grep -Eq -- '(^| )-(r|R)( |$)|-d -R' "${_PATH}/_ssh_screen.sh"; then
        _fail "_ssh_screen.sh 仍包含自动重连旧 screen 的参数"
    fi
    grep -Fq -- '--screen' "${_PATH}/_ssh_screen.sh" ||
        _fail "_ssh_screen.sh 缺少 --screen 开关"

    grep -Fq 'powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%_PATH%ss.ps1"' "${bat_file}" ||
        _fail "ss.bat 未通过 -File 调用独立的 ss.ps1 实现"
    if grep -Eq '^:|\bgoto\b' "${bat_file}"; then
        _fail "ss.bat 仍包含 LF 批处理下不可靠的标签或 goto"
    fi
    grep -Fq "'numeric' = @(\$numericFallbackUser, \$null)" "${ps1_file}" ||
        _fail "ss.ps1 未将 zhangxin 作为纯数字最低优先级默认用户"
    grep -Fq 'if ($numericAliases.ContainsKey($ipSuffix))' "${ps1_file}" ||
        _fail "ss.ps1 缺少已登记数字映射优先于默认用户的逻辑"
    grep -Fq '[switch]$Screen' "${ps1_file}" ||
        _fail "ss.ps1 缺少 --screen 对应的 -Screen 开关"
    grep -Fq '$ipSuffix -in @(19, 20)' "${ps1_file}" ||
        _fail "ss.ps1 未把 20 号 Windows 主机纳入 PowerShell 远端判定"

    local ssh_file
    for ssh_file in \
        ss.sh ss.ps1 ssnsc.sh ssnsc.bat ssjtu.sh xx99.sh \
        llingsheng.bat kkunshan.bat; do
        grep -Fq 'ServerAliveInterval=30' "${_PATH}/${ssh_file}" ||
            _fail "${ssh_file} 缺少 30 秒 SSH 保活间隔"
        grep -Fq 'ServerAliveCountMax=3' "${_PATH}/${ssh_file}" ||
            _fail "${ssh_file} 缺少 SSH 保活失联阈值"
    done

    for ssh_file in ss.sh ssnsc.sh ssjtu.sh xx99.sh; do
        grep -Fq 'source "${_PATH}/_ssh_screen.sh"' "${_PATH}/${ssh_file}" ||
            _fail "${ssh_file} 未加载统一 SSH 辅助"
        grep -Fq '_ssh_screen "${_NAME}"' "${_PATH}/${ssh_file}" ||
            _fail "${ssh_file} 未通过统一 SSH 辅助启动连接"
        grep -Fq -- '--screen' "${_PATH}/${ssh_file}" ||
            _fail "${ssh_file} 缺少 --screen 开关"
    done

    grep -Fq '$env:COMPUTERNAME' "$ps1_file" ||
        _fail "ss.ps1 未使用客户端主机名作为 screen 名称"
    grep -Fq 'if ($Screen)' "$ps1_file" ||
        _fail "ss.ps1 未按 -Screen 决定是否启动远端 screen"
    grep -Fq 'Get-Command screen' "$ps1_file" ||
        _fail "ss.ps1 缺少 Windows 远端 PowerShell 分支"
    grep -Fq '$hostShell -NoLogo -NoProfile' "$ps1_file" ||
        _fail "ss.ps1 缺少 PowerShell 远端交互 shell"
    if grep -Eq -- '-d -R|Get-Command screen -CommandType Application' "$ps1_file"; then
        _fail "ss.ps1 仍含本地 screen 探测或自动重连旧会话"
    fi
    for ssh_file in ssnsc.bat llingsheng.bat kkunshan.bat; do
        grep -Fq 'set "SSH_SCREEN_NAME=%COMPUTERNAME%"' "${_PATH}/${ssh_file}" ||
            _fail "${ssh_file} 未使用客户端主机名作为默认 screen 名称"
        grep -Fq 'ssh -t ' "${_PATH}/${ssh_file}" ||
            _fail "${ssh_file} 未直接执行带 TTY 的 SSH"
        grep -Fq -- '"--screen"' "${_PATH}/${ssh_file}" ||
            _fail "${ssh_file} 缺少 --screen 开关"
        grep -Fq '_REMOTE_CMD=exec sh -l' "${_PATH}/${ssh_file}" ||
            _fail "${ssh_file} 默认未使用登录 shell"
        if grep -Eq -- '-d -R|where screen' "${_PATH}/${ssh_file}"; then
            _fail "${ssh_file} 仍使用 SSH 前本地 screen 或自动重连旧会话"
        fi
    done

    grep -Fq 'SSH_REMOTE_SHELL="${REMOTE_SHELL}"' "${_PATH}/xx99.sh" ||
        _fail "xx99.sh 未选择 PowerShell 远端脚本"
    grep -Fq -- '--screen' "${_PATH}/xx99.sh" ||
        _fail "xx99.sh 缺少 --screen 开关"
    grep -Fq 'USE_SCREEN=true' "${_PATH}/xx99.sh" ||
        _fail "xx99.sh 未在 --screen 时启用 screen"
    grep -Fq "Write-Host '[INFO] 已退出 ddocker，回到 x99 终端'" "${_PATH}/xx99.sh" ||
        _fail "xx99.sh 未使用 PowerShell 远端命令"
    if grep -Fq 'exec bash -l' "${_PATH}/xx99.sh"; then
        _fail "xx99.sh 仍向 PowerShell 远端发送 POSIX exec"
    fi
}

main "$@"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
