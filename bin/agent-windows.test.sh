#!/usr/bin/env bash

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
bat="$script_dir/agent.bat"
runtime="$script_dir/agent-runtime.ps1"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_file() {
    [[ -f "$1" ]] || fail "文件不存在：$1"
}

assert_contains() {
    local file="$1"
    local needle="$2"
    rg -Fq -- "$needle" "$file" || fail "$file 缺少：$needle"
}

assert_not_contains() {
    local file="$1"
    local needle="$2"
    if rg -Fq -- "$needle" "$file"; then
        fail "$file 不应包含：$needle"
    fi
}

assert_file "$bat"
assert_file "$runtime"

for mapping in \
    'cl.bat' 'cls.bat' 'op.bat' 'ops.bat' 'co.bat' 'cos.bat'; do
    assert_contains "$bat" "$mapping"
done
assert_contains "$bat" 'agent-runtime.ps1'
assert_contains "$bat" 'AGENT_BAT_WORKDIR'
assert_contains "$bat" 'AGENT_BAT_SNSC'
assert_not_contains "$bat" 'LOG_FILE=.agent.'

for contract in \
    'function Start-Or-ResumeRun' \
    'function Write-Manifest' \
    'function Write-State' \
    'function Emit-Event' \
    'function Discover-Context' \
    'function Find-CodexThread' \
    '--max-turns' \
    '--max-runtime' \
    '--stop-file' \
    '--resume' \
    'Join-Path $script:DataRoot '\''runs'\'''; do
    assert_contains "$runtime" "$contract"
done
assert_contains "$runtime" "'-q' = @('gpt-6-astra', 'GPT-6 Astra')"
assert_contains "$runtime" "'-q' { 'max' }"
assert_contains "$runtime" 'features.fast_mode=$fastMode'

if command -v powershell.exe >/dev/null 2>&1; then
    ps_cmd=powershell.exe
elif command -v pwsh.exe >/dev/null 2>&1; then
    ps_cmd=pwsh.exe
else
    printf 'SKIP: 当前环境未找到 powershell.exe/pwsh.exe，未执行 PowerShell Parser\n'
    printf 'PASS: Windows launcher 静态契约\n'
    exit 0
fi

parser='
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile($args[0], [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count -gt 0) {
    $errors | ForEach-Object { $_.Message } | Write-Error
    exit 1
}
'
set +e
parser_output=$("$ps_cmd" -NoLogo -NoProfile -Command "$parser" "$runtime" 2>&1)
parser_status=$?
set -e
(( parser_status == 0 )) || fail "PowerShell Parser 失败：$parser_output"
printf 'PASS: PowerShell Parser 语法检查\n'
printf 'PASS: Windows launcher 静态契约\n'
