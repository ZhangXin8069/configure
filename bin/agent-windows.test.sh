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
    'function Merge-JsonNode' \
    'function Import-AgentConfig' \
    'function Get-OpenCodeProviderConfig' \
    '--max-turns' \
    '--max-runtime' \
    '--stop-file' \
    '--resume' \
    'Join-Path $script:DataRoot '\''runs'\'''; do
    assert_contains "$runtime" "$contract"
done
assert_contains "$runtime" "'agent-config.json'"
assert_contains "$runtime" "'agent-custom.json.refer'"
assert_contains "$runtime" '$agentConfig.default_flag'
assert_contains "$runtime" '$agentConfig.flags.$defaultFlag'
assert_contains "$runtime" '$permissionMode'
assert_contains "$runtime" 'agents.opencode.agent'
assert_contains "$runtime" 'model_providers.$providerId.env_key'
assert_contains "$runtime" 'model_providers.$providerId.wire_api'
assert_contains "$runtime" 'features.fast_mode=$fastMode'
assert_contains "$runtime" 'function Set-ClaudeDefaults'
assert_contains "$runtime" 'function New-ClaudeSettingsFile'
assert_contains "$runtime" "'--settings', \$script:ClaudeSettingsFile"

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
$target = $env:AGENT_TEST_PARSE_TARGET
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile($target, [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count -gt 0) {
    $errors | ForEach-Object { $_.Message } | Write-Error
    exit 1
}
'
set +e
parser_output=$(AGENT_TEST_PARSE_TARGET="$runtime" "$ps_cmd" -NoLogo -NoProfile -Command "$parser" 2>&1)
parser_status=$?
set -e
(( parser_status == 0 )) || fail "PowerShell Parser 失败：$parser_output"
printf 'PASS: PowerShell Parser 语法检查\n'
printf 'PASS: Windows launcher 静态契约\n'
