#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

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

    ssh() {
        printf '%s\n' "$*"
    }
    export -f ssh

    output=$(_run_ss "${input}")
    if ! grep -Fxq -- "${expected}" <<< "${output}"; then
        _fail "输入 ${input} 应连接 ${expected}，实际输出：${output}"
    fi
}

main() {
    local bat_file="${_PATH}/ss.bat"
    local ps1_file="${_PATH}/ss.ps1"

    _assert_target 42 "192.168.188.42 -l zhangxin"
    _assert_target 1 "192.168.188.1 -l zhangxin"
    _assert_target 254 "192.168.188.254 -l zhangxin"
    _assert_target 20 "192.168.188.20 -l kfutfd"
    _assert_target 19 "192.168.188.19 -l kfutfd"
    _assert_target 3 "192.168.188.3 -l zhang"
    _assert_target k42 "192.168.188.42 -l kfutfd"
    _assert_target y42 "192.168.188.42 -l yang"
    _assert_target __NO_ARG__ "192.168.188.19 -l kfutfd"

    rg -Fq 'powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%_PATH%ss.ps1"' "${bat_file}" ||
        _fail "ss.bat 未通过 -File 调用独立的 ss.ps1 实现"
    if rg -q '^:|\bgoto\b' "${bat_file}"; then
        _fail "ss.bat 仍包含 LF 批处理下不可靠的标签或 goto"
    fi
    rg -Fq "'numeric' = @(\$numericFallbackUser, \$null)" "${ps1_file}" ||
        _fail "ss.ps1 未将 zhangxin 作为纯数字最低优先级默认用户"
    rg -Fq 'if ($numericAliases.ContainsKey($ipSuffix))' "${ps1_file}" ||
        _fail "ss.ps1 缺少已登记数字映射优先于默认用户的逻辑"
}

main "$@"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
