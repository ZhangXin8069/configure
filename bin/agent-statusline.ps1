# Claude Code statusLine 渲染器（Windows）：输出与 co（Codex tui.status_line）同款字段的一行状态栏。
# 由 Claude Code 高频调用（stdin 传入官方状态 JSON，stdout 首行为状态栏），只输出一行，不打印其他内容。
# 官方字段映射：model.display_name→model-with-reasoning、effort.level→推理强度、
#   workspace.current_dir→current-dir、context_window.*→context-used、
#   rate_limits.seven_day.used_percentage→weekly-limit、fast_mode→fast-mode、
#   cost.total_cost_usd→estimated-thread-cost、session_id→thread-id。
# 配置由 agent-runtime.ps1 从 agent-config.json / agent-custom.json 注入同名环境变量：
#   AGENT_STATUSLINE_SEGMENTS / AGENT_STATUSLINE_USE_COLORS / AGENT_PERMISSION_MODE / AGENT_RUN_DIR

$ErrorActionPreference = 'SilentlyContinue'

$raw = [Console]::In.ReadToEnd()
try { $payload = $raw | ConvertFrom-Json } catch { $payload = $null }

$segmentsRaw = $env:AGENT_STATUSLINE_SEGMENTS
if ([string]::IsNullOrWhiteSpace($segmentsRaw)) { $segmentsRaw = '[]' }
$segments = @()
try { $segments = @($segmentsRaw | ConvertFrom-Json) } catch { $segments = @() }

$useColors = ($env:AGENT_STATUSLINE_USE_COLORS -ne 'false')

$esc = [char]27
if ($useColors) {
    $cDim = "$esc[2m"; $cCyan = "$esc[36m"; $cGreen = "$esc[32m"
    $cYellow = "$esc[33m"; $cMagenta = "$esc[35m"; $cReset = "$esc[0m"
} else {
    $cDim = ''; $cCyan = ''; $cGreen = ''; $cYellow = ''; $cMagenta = ''; $cReset = ''
}

function Get-PayloadString {
    param($Node, [string[]]$Path)

    $cursor = $Node
    foreach ($key in $Path) {
        if ($null -eq $cursor) { return '' }
        $cursor = $cursor.$key
    }
    if ($null -eq $cursor) { return '' }
    return [string]$cursor
}

function Format-Segment {
    param([string]$Segment)

    switch ($Segment) {
        'model-with-reasoning' {
            $model = Get-PayloadString $payload @('model', 'display_name')
            if ([string]::IsNullOrWhiteSpace($model)) { $model = [string]$env:ANTHROPIC_MODEL }
            if ([string]::IsNullOrWhiteSpace($model)) { return '' }
            $level = [string]$payload.effort.level
            if ([string]::IsNullOrWhiteSpace($level)) { $level = [string]$env:CLAUDE_CODE_EFFORT_LEVEL }
            if ([string]::IsNullOrWhiteSpace($level)) { return "$cCyan$model$cReset" }
            return "$cCyan$model$cReset $cDim($level)$cReset"
        }
        'current-dir' {
            $dir = Get-PayloadString $payload @('workspace', 'current_dir')
            if ([string]::IsNullOrWhiteSpace($dir)) { return '' }
            $homeRoot = [Environment]::GetEnvironmentVariable('USERPROFILE')
            if (-not [string]::IsNullOrWhiteSpace($homeRoot) -and $dir.StartsWith($homeRoot)) {
                $dir = '~' + $dir.Substring($homeRoot.Length)
            }
            return "$cDim$dir$cReset"
        }
        'hostname' {
            return "$cDim$([Environment]::MachineName)$cReset"
        }
        'branch-changes' {
            $cwd = Get-PayloadString $payload @('workspace', 'current_dir')
            if ([string]::IsNullOrWhiteSpace($cwd)) { $cwd = (Get-Location).Path }
            if (-not (Test-Path -LiteralPath (Join-Path $cwd '.git'))) { return '' }
            $branch = (& git -C $cwd rev-parse --abbrev-ref HEAD 2>$null | Select-Object -First 1)
            if ([string]::IsNullOrWhiteSpace($branch)) { return '' }
            $changes = @(& git -C $cwd status --porcelain 2>$null).Count
            $text = "$cGreen$branch$cReset"
            if ($changes -gt 0) { $text += "$cYellow*$changes$cReset" }
            return $text
        }
        'run-state' {
            $runDir = [string]$env:AGENT_RUN_DIR
            if ([string]::IsNullOrWhiteSpace($runDir)) { return '' }
            $stateFile = Join-Path $runDir 'state.env'
            if (-not (Test-Path -LiteralPath $stateFile)) { return '' }
            $state = (Select-String -LiteralPath $stateFile -Pattern '^state=' | Select-Object -First 1)
            if ($null -eq $state) { return '' }
            return "$cMagenta$($state.Line.Substring(6))$cReset"
        }
        'permissions' {
            if ([string]::IsNullOrWhiteSpace([string]$env:AGENT_PERMISSION_MODE)) { return '' }
            return "$cYellow$($env:AGENT_PERMISSION_MODE)$cReset"
        }
        'approval-mode' {
            if ([string]::IsNullOrWhiteSpace([string]$env:AGENT_PERMISSION_MODE)) { return '' }
            return "${cYellow}approval:$($env:AGENT_PERMISSION_MODE)$cReset"
        }
        'context-used' {
            $used = $payload.context_window.used_percentage
            if ($null -eq $used) { return '' }
            $percent = [int64][double]$used
            $total = $payload.context_window.total_input_tokens
            $size = $payload.context_window.context_window_size
            if ($null -ne $size -and [int64]$size -gt 0 -and $null -ne $total) {
                return "${cDim}ctx $percent% $([int64]([int64]$total / 1000))k/$([int64]([int64]$size / 1000))k$cReset"
            }
            return "${cDim}ctx $percent%$cReset"
        }
        'context-window-size' {
            # 上下文窗口容量（tokens）：官方 context_window.context_window_size，
            # 默认 200000，扩展上下文模型为 1000000。与 context-used 相互独立。
            $size = $payload.context_window.context_window_size
            if ($null -eq $size) { return '' }
            $tokens = [int64][double]$size
            if ($tokens -le 0) { return '' }
            if ($tokens -ge 1000000 -and ($tokens % 1000000) -eq 0) {
                return "${cDim}ctx-max $([int64]($tokens / 1000000))M$cReset"
            }
            return "${cDim}ctx-max $([int64]($tokens / 1000))k$cReset"
        }
        'weekly-limit' {
            $used = $payload.rate_limits.seven_day.used_percentage
            if ($null -eq $used) { return '' }
            return "${cDim}7d $([int64][double]$used)%$cReset"
        }
        'fast-mode' {
            if ($payload.fast_mode -ne $true) { return '' }
            return "${cMagenta}fast$cReset"
        }
        'estimated-thread-cost' {
            $cost = Get-PayloadString $payload @('cost', 'total_cost_usd')
            if ([string]::IsNullOrWhiteSpace($cost)) { return '' }
            return "$cDim`$$cost$cReset"
        }
        'thread-id' {
            $sid = Get-PayloadString $payload @('session_id')
            if ([string]::IsNullOrWhiteSpace($sid)) { return '' }
            if ($sid.Length -gt 8) { $sid = $sid.Substring(0, 8) }
            return "$cDim$sid$cReset"
        }
        default { return '' }
    }
}

$parts = New-Object System.Collections.Generic.List[string]
foreach ($segment in $segments) {
    $name = ([string]$segment).Trim()
    if ([string]::IsNullOrWhiteSpace($name)) { continue }
    $text = Format-Segment $name
    if (-not [string]::IsNullOrWhiteSpace($text)) { $parts.Add($text) }
}
$separator = " $cDim|$cReset "
[Console]::Out.WriteLine(($parts -join $separator))
