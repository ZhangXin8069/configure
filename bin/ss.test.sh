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
    if ! grep -Fxq -- "${expected}" <<< "${output}"; then
        _fail "输入 ${input} 应连接 ${expected}，实际输出：${output}"
    fi
}

main() {
    local bat_file="${_PATH}/ss.bat"
    local ps1_file="${_PATH}/ss.ps1"
    local fake_bin=$test_root/fake-bin
    local fake_screen=$fake_bin/screen
    local fake_ssh=$fake_bin/ssh
    local missing_screen=$test_root/missing-screen
    local output
    local status

    mkdir -p "$fake_bin"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'printf "%s\\n" "$*"' \
        'exit "${SSH_FAKE_STATUS:-0}"' >"$fake_ssh"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'printf "%s\\n" "$*"' \
        'exit "${SCREEN_FAKE_STATUS:-0}"' >"$fake_screen"
    chmod +x "$fake_ssh" "$fake_screen"
    export PATH="$fake_bin:$PATH"
    export SCREEN_BIN="$missing_screen"
    export SSH_SCREEN_NAME=''

    _assert_target 42 "-o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l zhangxin 192.168.188.42"
    _assert_target 1 "-o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l zhangxin 192.168.188.1"
    _assert_target 254 "-o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l zhangxin 192.168.188.254"
    _assert_target 20 "-o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l kfutfd 192.168.188.20"
    _assert_target 19 "-o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l kfutfd 192.168.188.19"
    _assert_target 3 "-o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l zhang 192.168.188.3"
    _assert_target k42 "-o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l kfutfd 192.168.188.42"
    _assert_target y42 "-o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l yang 192.168.188.42"
    _assert_target __NO_ARG__ "-o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l kfutfd 192.168.188.19"

    set +e
    output=$(SCREEN_BIN="$missing_screen" SSH_SCREEN_NAME='' _run_ss 42 2>&1)
    status=$?
    set -e
    (( status == 0 )) || _fail "screen 缺失时应继续 SSH 并返回 0，实际为 $status"
    grep -Fq 'Debian/Ubuntu: sudo apt update && sudo apt install screen' <<<"$output" ||
        _fail "screen 缺失告警缺少 Debian/Ubuntu 安装指南"
    grep -Fq 'Ctrl+a d' <<<"$output" || _fail "screen 缺失告警缺少使用指南"

    output=$(SCREEN_BIN="$fake_screen" SSH_SCREEN_NAME='' _run_ss 42 2>/dev/null)
    grep -Fq -- '-t ss.sh -S ss.sh -d -R sh -c ' <<<"$output" ||
        _fail "screen 可用时未以客户端名设置同名标题和会话"
    grep -Fq -- ' sh -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l zhangxin 192.168.188.42' <<<"$output" ||
        _fail "screen 可用时 SSH 参数未原样传递"

    output=$(SCREEN_BIN="$fake_screen" SSH_SCREEN_NAME='manual-name' _run_ss 42 2>/dev/null)
    grep -Fq -- '-t manual-name -S manual-name -d -R sh -c ' <<<"$output" ||
        _fail "SSH_SCREEN_NAME 未覆盖窗口标题和会话名"

    set +e
    SCREEN_FAKE_STATUS=29 SCREEN_BIN="$fake_screen" SSH_SCREEN_NAME='' _run_ss 42 >/dev/null 2>/dev/null
    status=$?
    set -e
    (( status == 29 )) || _fail "screen 已安装但执行失败时应保留其退出码 29，实际为 $status"

    set +e
    SSH_FAKE_STATUS=37 SCREEN_BIN="$missing_screen" _run_ss 42 >/dev/null 2>/dev/null
    status=$?
    set -e
    (( status == 37 )) || _fail "screen 缺失降级时应保留 SSH 退出码 37，实际为 $status"

    grep -Fq -- '-t "${session_name}" -S "${session_name}" -d -R sh -c' "${_PATH}/_ssh_screen.sh" ||
        _fail "_ssh_screen.sh 未保持窗口标题与 sockname 一致"
    grep -Fq '${STY:-}' "${_PATH}/_ssh_screen.sh" ||
        _fail "_ssh_screen.sh 未将窗口标题更新为完整的 <pid>.<sockname>"

    rg -Fq 'powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%_PATH%ss.ps1"' "${bat_file}" ||
        _fail "ss.bat 未通过 -File 调用独立的 ss.ps1 实现"
    if rg -q '^:|\bgoto\b' "${bat_file}"; then
        _fail "ss.bat 仍包含 LF 批处理下不可靠的标签或 goto"
    fi
    rg -Fq "'numeric' = @(\$numericFallbackUser, \$null)" "${ps1_file}" ||
        _fail "ss.ps1 未将 zhangxin 作为纯数字最低优先级默认用户"
    rg -Fq 'if ($numericAliases.ContainsKey($ipSuffix))' "${ps1_file}" ||
        _fail "ss.ps1 缺少已登记数字映射优先于默认用户的逻辑"

    local ssh_file
    for ssh_file in \
        ss.sh ss.ps1 ssnsc.sh ssnsc.bat ssjtu.sh xx99.sh \
        llingsheng.bat kkunshan.bat; do
        rg -Fq 'ServerAliveInterval=30' "${_PATH}/${ssh_file}" ||
            _fail "${ssh_file} 缺少 30 秒 SSH 保活间隔"
        rg -Fq 'ServerAliveCountMax=3' "${_PATH}/${ssh_file}" ||
            _fail "${ssh_file} 缺少 SSH 保活失联阈值"
    done

    for ssh_file in ss.sh ssnsc.sh ssjtu.sh xx99.sh; do
        grep -Fq 'source "${_PATH}/_ssh_screen.sh"' "${_PATH}/${ssh_file}" ||
            _fail "${ssh_file} 未加载统一 screen SSH 辅助"
        grep -Fq '_ssh_screen "${_NAME}"' "${_PATH}/${ssh_file}" ||
            _fail "${ssh_file} 未通过统一 screen SSH 辅助启动连接"
    done

    grep -Fq 'Get-Command screen' "$ps1_file" ||
        _fail "ss.ps1 未检测 screen"
    grep -Fq '_screen-guide.txt' "$ps1_file" ||
        _fail "ss.ps1 缺失 screen 安装与使用指南"
    for ssh_file in ssnsc.bat llingsheng.bat kkunshan.bat; do
        grep -Fq 'where screen' "${_PATH}/${ssh_file}" ||
            _fail "${ssh_file} 未检测 screen"
        grep -Fq '_screen-warning.bat' "${_PATH}/${ssh_file}" ||
            _fail "${ssh_file} 未在 screen 缺失时输出统一指南"
        grep -Fq -- '-t "%SSH_SCREEN_NAME%" -S "%SSH_SCREEN_NAME%" -d -R' "${_PATH}/${ssh_file}" ||
            _fail "${ssh_file} 未保持窗口标题与 sockname 一致"
    done

    grep -Fq -- '-t $screenSession -S $screenSession -d -R' "$ps1_file" ||
        _fail "ss.ps1 未保持窗口标题与 sockname 一致"
    grep -Fq 'type "%~dp0_screen-guide.txt"' "${_PATH}/_screen-warning.bat" ||
        _fail "_screen-warning.bat 未复用统一 screen 指南"
}

main "$@"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
