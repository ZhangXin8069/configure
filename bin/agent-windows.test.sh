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
assert_file "$script_dir/agent-statusline.ps1"
assert_contains "$script_dir/agent-statusline.ps1" 'context_window.used_percentage'
assert_contains "$script_dir/agent-statusline.ps1" 'context_window.context_window_size'
assert_contains "$script_dir/agent-statusline.ps1" "'context-window-size'"
assert_contains "$script_dir/agent-statusline.ps1" 'rate_limits.seven_day'
assert_contains "$script_dir/agent-statusline.ps1" 'fast_mode'

for mapping in \
    'cl.bat' 'cls.bat' 'op.bat' 'ops.bat' 'co.bat' 'cos.bat'; do
    assert_contains "$bat" "$mapping"
done
assert_contains "$bat" 'agent-runtime.ps1'
assert_contains "$bat" 'AGENT_BAT_WORKDIR'
assert_contains "$bat" 'AGENT_BAT_SECURE'
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
assert_not_contains "$runtime" 'default_flag'
assert_not_contains "$runtime" '$agentConfig.flags'
assert_not_contains "$runtime" 'DEFAULT_MODEL_FLAG'
assert_contains "$runtime" '$permissionMode'
assert_contains "$runtime" 'agents.opencode.agent'
assert_contains "$runtime" 'function Initialize-SecureBinary'
assert_contains "$runtime" 'function Expand-HomePath'
assert_contains "$runtime" 'agents.$SecureAgentName.secure_binary'
assert_contains "$runtime" "Resolve-Executable 'CLAUDE_BIN' 'claude' 'claude'"
assert_contains "$runtime" "Resolve-Executable 'OPENCODE_BIN' 'opencode' 'opencode'"
assert_contains "$runtime" "Resolve-Executable 'CODEX_BIN' 'codex' 'codex'"
assert_contains "$runtime" 'secure_binary 缺失，已从'
assert_contains "$runtime" 'model_providers.$providerId.env_key'
assert_contains "$runtime" 'model_providers.$providerId.wire_api'
assert_contains "$runtime" 'features.fast_mode=$fastMode'
assert_contains "$runtime" 'function Set-ClaudeDefaults'
assert_contains "$runtime" 'function New-ClaudeSettingsFile'
assert_contains "$runtime" "'--settings', \$script:ClaudeSettingsFile"
assert_contains "$runtime" "'--permission-mode', \$permissionMode, '--model', \$script:Model, \$prompt"
assert_contains "$runtime" 'Resolve-ProviderAlias'
assert_contains "$runtime" "'pay', 'go', 'gpt', 'deepseek-pay', 'opencode-go', 'custom-gpt'"
assert_contains "$runtime" 'Get-ProviderDefaultModel'
assert_contains "$runtime" 'providers.$providerForModel.default_models.$agentKey'
assert_contains "$runtime" 'Get-ProviderDefaultStrength'
assert_contains "$runtime" 'default_strengths.$AgentName'
assert_contains "$runtime" 'agents.$agentKey.model'
assert_contains "$runtime" '$agentConfig.strength'
assert_contains "$runtime" '$script:ClaudeStrength'
assert_not_contains "$runtime" "'-m', '-o', '-p', '-q', '-k', '-g', '-f', '-h'"
assert_contains "$runtime" 'Invoke-LegacyKeyMigration'
assert_contains "$runtime" "'DEEPSEEK_PAY_API_KEY', 'DEEPSEEK_API_KEY'"
assert_contains "$runtime" "'CUSTOM_GPT_API_KEY', 'LQCD_API_KEY'"
assert_contains "$runtime" 'agent-statusline.ps1'
assert_contains "$runtime" 'AGENT_STATUSLINE_SEGMENTS'
assert_contains "$runtime" 'statusLine'
assert_contains "$runtime" '$providerWebsockets'
assert_contains "$runtime" 'check_for_update_on_startup'
assert_contains "$runtime" 'DISABLE_AUTOUPDATER'
assert_contains "$runtime" 'OPENCODE_AUTOUPDATE'
assert_contains "$runtime" 'autoupdate'
assert_contains "$runtime" 'function Get-CodexModelCatalogPath'
assert_contains "$runtime" '& $Bin debug models'
assert_contains "$runtime" 'model_catalog_json'
assert_contains "$runtime" 'codex-models-$versionKey-$safeModel-$key.json'
assert_contains "$runtime" 'CODEX_MODEL_CATALOG'
assert_contains "$runtime" '$codexConfig.model_catalog'

# 多场景部署：configure 根/数据根跟随部署位置（与 Unix 端 agent-runtime.sh 语义一致）
assert_contains "$runtime" 'function Get-ConfigureRoot'
assert_contains "$runtime" 'function Test-IsConfigureRoot'
assert_contains "$runtime" 'function Test-WritableDirectory'
assert_contains "$runtime" 'function Get-HomeRoot'
assert_contains "$runtime" 'AGENT_CONFIGURE_ROOT'
assert_contains "$runtime" '${CONFIGURE_ROOT}'
assert_not_contains "$runtime" 'configure\skills'
assert_not_contains "$runtime" 'configure\tools'

# 缺失可执行文件时自动安装（与 Unix 端 agent-runtime.sh 语义一致）
for contract in \
    'function Get-AgentInstallScript' \
    'function Add-AgentPathEntry' \
    'function Install-AgentExecutable' \
    "'_claude-code'" \
    "'_opencode'" \
    "'_codex'" \
    "'install.bat', 'install.ps1', 'install.sh'" \
    'AGENT_AUTO_INSTALL' \
    'AGENT_AUTO_INSTALL_DONE' \
    'AGENT_INSTALL_DIR' \
    '未找到 $AgentName，自动运行安装脚本' \
    '安装完成：'; do
    assert_contains "$runtime" "$contract"
done
# 安装脚本输出必须走 Out-Host（前述 stdout 混入返回值会污染 secure_binary 路径）
assert_contains "$runtime" '& cmd.exe /c "`"$scriptPath`"" | Out-Host'
assert_contains "$runtime" '& bash $scriptPath | Out-Host'

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
