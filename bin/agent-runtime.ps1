# Shared Windows runtime for agent.bat.
#
# The Unix launcher uses agent-runtime.sh. This file keeps the Windows
# launcher semantically aligned without making the batch parser own state,
# locking, JSON or prompt construction.

$ErrorActionPreference = 'Stop'

$script:Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$script:CliArgs = @($args)
$script:LauncherName = [Environment]::GetEnvironmentVariable('AGENT_BAT_LAUNCHER_NAME')
$script:ScriptDir = [Environment]::GetEnvironmentVariable('AGENT_BAT_SCRIPT_DIR')
$script:WorkDir = [Environment]::GetEnvironmentVariable('AGENT_BAT_WORKDIR')
$script:Agent = [Environment]::GetEnvironmentVariable('AGENT_BAT_AGENT')
$script:Snsc = [Environment]::GetEnvironmentVariable('AGENT_BAT_SNSC')
$script:ExitCode = 0
$script:FailureCode = 0
$script:RunReady = $false
$script:LockAcquired = $false
$script:LockStream = $null
$script:RunId = ''
$script:RunDir = ''
$script:DataRoot = ''
$script:WorkspaceRoot = ''
$script:LogFile = ''
$script:ListFile = ''
$script:EventFile = ''
$script:ManifestFile = ''
$script:StateFile = ''
$script:ContextFile = ''
$script:StopFile = ''
$script:ContextCount = 0
$script:DiscoveredInstructions = @()
$script:RuntimeConfigs = @()
$script:SessionId = ''
$script:ThreadId = ''
$script:Turn = 0
$script:SuccessfulTurns = 0
$script:FailedTurns = 0
$script:ResumeCount = 0
$script:CreatedAt = ''
$script:UpdatedAt = ''
$script:StartTime = Get-Date
$script:State = 'created'
$script:LastExit = ''
$script:LastReason = ''
$script:Model = ''
$script:ModelExplicit = $false
$script:Reasoning = ''
$script:ReasoningExplicit = $false
$script:Variant = ''
$script:VariantExplicit = $false
$script:Mode = 'tui'
$script:Role = ''
$script:Tier = ''
$script:Posture = ''
$script:MaxTurns = 100
$script:MaxRuntime = 0
$script:Interval = 30
$script:Once = $false
$script:ResumeRunId = ''
$script:DriveFile = ''
$script:StopFileArg = ''
$script:Drive = $false

function Write-Info {
    param([string]$Message)
    Write-Host $Message
}

function Write-ErrorLine {
    param([string]$Message)
    [Console]::Error.WriteLine($Message)
}

function Fail-Parse {
    param([string]$Message)
    Write-ErrorLine $Message
    $script:FailureCode = 64
}

function Resolve-FullPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $script:WorkDir $Path))
}

function Resolve-AgentDataRoot {
    $candidate = [Environment]::GetEnvironmentVariable('AGENT_DATA_DIR')
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        $candidate = [Environment]::GetEnvironmentVariable('CONFIGURE_AGENT_DATA_DIR')
    }
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        $homeRoot = [Environment]::GetEnvironmentVariable('HOME')
        if ([string]::IsNullOrWhiteSpace($homeRoot)) {
            $homeRoot = [Environment]::GetEnvironmentVariable('USERPROFILE')
        }
        $candidate = Join-Path $homeRoot 'configure\data'
    }
    return Resolve-FullPath $candidate
}

function Write-Utf8 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Text
    )

    $parent = Split-Path -Parent $Path
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    [System.IO.File]::WriteAllText($Path, $Text, $script:Utf8NoBom)
}

function Append-Utf8 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Text
    )

    $parent = Split-Path -Parent $Path
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    [System.IO.File]::AppendAllText($Path, $Text, $script:Utf8NoBom)
}

function Write-Utf8Atomic {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Text
    )

    $temp = '{0}.tmp.{1}' -f $Path, $PID
    Write-Utf8 $temp $Text
    try {
        if (Test-Path -LiteralPath $Path -PathType Leaf) {
            try {
                [System.IO.File]::Replace($temp, $Path, $null, $true)
            } catch {
                Move-Item -LiteralPath $temp -Destination $Path -Force
            }
        } else {
            Move-Item -LiteralPath $temp -Destination $Path -Force
        }
    } finally {
        if (Test-Path -LiteralPath $temp -PathType Leaf) {
            Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
        }
    }
}

function Get-ManifestValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Key
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return ''
    }
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        $separator = $line.IndexOf('=')
        if ($separator -gt 0 -and $line.Substring(0, $separator) -eq $Key) {
            return $line.Substring($separator + 1)
        }
    }
    return ''
}

function Validate-ResumeManifest {
    param([Parameter(Mandatory = $true)][string]$Path)

    $schema = Get-ManifestValue $Path 'schema_version'
    if ($schema -ne '1') {
        Write-ErrorLine "###$($script:LauncherName): ERROR: --resume manifest schema 不受支持：$($schema)###"
        $script:FailureCode = 78
        return $false
    }

    foreach ($check in @(
        @{ Key = 'run_id'; Expected = $script:ResumeRunId }
        @{ Key = 'agent'; Expected = $script:Agent }
        @{ Key = 'launcher'; Expected = $script:LauncherName }
    )) {
        $actual = Get-ManifestValue $Path $check.Key
        if ([string]::IsNullOrWhiteSpace($actual) -or $actual -ne $check.Expected) {
            Write-ErrorLine "###$($script:LauncherName): ERROR: --resume manifest 身份不匹配：$($check.Key)=$actual（期望 $($check.Expected)）###"
            $script:FailureCode = 78
            return $false
        }
    }

    $actualWorkspace = Get-ManifestValue $Path 'workspace_root'
    if ([string]::IsNullOrWhiteSpace($actualWorkspace) -or
        ([System.IO.Path]::GetFullPath($actualWorkspace).TrimEnd('\') -ine
         [System.IO.Path]::GetFullPath($script:WorkspaceRoot).TrimEnd('\'))) {
        Write-ErrorLine "###$($script:LauncherName): ERROR: --resume manifest 身份不匹配：workspace_root=$actualWorkspace（期望 $($script:WorkspaceRoot)）###"
        $script:FailureCode = 78
        return $false
    }
    return $true
}

function Clean-ManifestValue {
    param([AllowNull()][string]$Value)
    if ($null -eq $Value) {
        return ''
    }
    return ($Value -replace "`r", ' ' -replace "`n", ' ')
}

function Write-Manifest {
    $lines = @(
        'schema_version=1'
        "run_id=$(Clean-ManifestValue $script:RunId)"
        "created_at=$(Clean-ManifestValue $script:CreatedAt)"
        "updated_at=$(Clean-ManifestValue $script:UpdatedAt)"
        "agent=$(Clean-ManifestValue $script:Agent)"
        "launcher=$(Clean-ManifestValue $script:LauncherName)"
        "mode=$(Clean-ManifestValue $script:Mode)"
        "role=$(Clean-ManifestValue $script:Role)"
        "tier=$(Clean-ManifestValue $script:Tier)"
        "posture=$(Clean-ManifestValue $script:Posture)"
        "cwd=$(Clean-ManifestValue $script:WorkDir)"
        "workspace_root=$(Clean-ManifestValue $script:WorkspaceRoot)"
        "data_root=$(Clean-ManifestValue $script:DataRoot)"
        "run_dir=$(Clean-ManifestValue $script:RunDir)"
        "log_file=$(Clean-ManifestValue $script:LogFile)"
        "list_file=$(Clean-ManifestValue $script:ListFile)"
        "event_file=$(Clean-ManifestValue $script:EventFile)"
        "context_file=$(Clean-ManifestValue $script:ContextFile)"
        "stop_file=$(Clean-ManifestValue $script:StopFile)"
        "model=$(Clean-ManifestValue $script:Model)"
        "reasoning_effort=$(Clean-ManifestValue $script:Reasoning)"
        "variant=$(Clean-ManifestValue $script:Variant)"
        "session_id=$(Clean-ManifestValue $script:SessionId)"
        "thread_id=$(Clean-ManifestValue $script:ThreadId)"
        "turn=$script:Turn"
        "successful_turns=$script:SuccessfulTurns"
        "failed_turns=$script:FailedTurns"
        "resume_count=$script:ResumeCount"
        "max_turns=$script:MaxTurns"
        "max_runtime=$script:MaxRuntime"
        "state=$(Clean-ManifestValue $script:State)"
        "last_exit=$(Clean-ManifestValue $script:LastExit)"
        "last_reason=$(Clean-ManifestValue $script:LastReason)"
    )
    Write-Utf8Atomic $script:ManifestFile (($lines -join [Environment]::NewLine) + [Environment]::NewLine)
}

function Write-State {
    $lines = @(
        'schema_version=1'
        "run_id=$(Clean-ManifestValue $script:RunId)"
        "state=$(Clean-ManifestValue $script:State)"
        "updated_at=$(Clean-ManifestValue $script:UpdatedAt)"
        "turn=$script:Turn"
        "session_id=$(Clean-ManifestValue $script:SessionId)"
        "thread_id=$(Clean-ManifestValue $script:ThreadId)"
        "last_exit=$(Clean-ManifestValue $script:LastExit)"
        "last_reason=$(Clean-ManifestValue $script:LastReason)"
    )
    Write-Utf8Atomic $script:StateFile (($lines -join [Environment]::NewLine) + [Environment]::NewLine)
}

function Json-Event {
    param(
        [Parameter(Mandatory = $true)][string]$Event,
        [Parameter(Mandatory = $true)][string]$Status,
        [AllowNull()][string]$Message
    )

    $payload = [ordered]@{
        schema_version = '1'
        event = $Event
        timestamp = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
        source = 'launcher'
        run_id = $script:RunId
        launcher = $script:LauncherName
        agent = $script:Agent
        workspace = $script:WorkspaceRoot
        session_id = $script:SessionId
        thread_id = $script:ThreadId
        turn = [int]$script:Turn
        status = $Status
        message = (Clean-ManifestValue $Message)
    }
    return ($payload | ConvertTo-Json -Compress -Depth 4)
}

function Emit-Event {
    param(
        [Parameter(Mandatory = $true)][string]$Event,
        [Parameter(Mandatory = $true)][string]$Status,
        [AllowNull()][string]$Message
    )

    if (-not [string]::IsNullOrWhiteSpace($script:EventFile)) {
        Append-Utf8 $script:EventFile ((Json-Event $Event $Status $Message) + [Environment]::NewLine)
    }
}

function Mark-State {
    param(
        [Parameter(Mandatory = $true)][string]$State,
        [AllowNull()][string]$Reason,
        [AllowNull()][string]$Exit
    )

    $script:State = $State
    $script:LastReason = [string]$Reason
    $script:LastExit = [string]$Exit
    $script:UpdatedAt = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
    if ($script:RunReady) {
        Write-Manifest
        Write-State
    }

    switch ($State) {
        'running'  { Emit-Event 'session-start' 'ok' $Reason }
        'finished' { Emit-Event 'session-end' 'ok' $Reason }
        'stopped'  { Emit-Event 'session-stop' 'ok' $Reason }
        'failed'   { Emit-Event 'session-end' 'failed' $Reason }
        'blocked'  { Emit-Event 'session-end' 'blocked' $Reason }
    }
}

function Acquire-RunLock {
    $lockPath = Join-Path $script:RunDir '.lock'
    try {
        # OpenOrCreate plus FileShare.None also recovers a stale file left by
        # a terminated process while still rejecting concurrent access.
        $script:LockStream = [System.IO.File]::Open(
            $lockPath,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
        $script:LockStream.SetLength(0)
        $bytes = [Text.Encoding]::UTF8.GetBytes([string]$PID)
        $script:LockStream.Write($bytes, 0, $bytes.Length)
        $script:LockStream.Flush()
        $script:LockAcquired = $true
        return $true
    } catch {
        if ($script:LockStream) {
            $script:LockStream.Dispose()
            $script:LockStream = $null
        }
        Write-ErrorLine "###$($script:LauncherName): ERROR: run 正在被其他进程占用：$($script:RunId)###"
        $script:FailureCode = 75
        return $false
    }
}

function Release-RunLock {
    $lockPath = ''
    if (-not [string]::IsNullOrWhiteSpace($script:RunDir)) {
        $lockPath = Join-Path $script:RunDir '.lock'
    }
    if ($script:LockStream) {
        $script:LockStream.Dispose()
        $script:LockStream = $null
    }
    if ($script:LockAcquired -and $lockPath -and (Test-Path -LiteralPath $lockPath -PathType Leaf)) {
        Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
    }
    $script:LockAcquired = $false
}

function Discover-Context {
    $script:DiscoveredInstructions = @()
    $instructionNames = @('AGENTS.md', 'CODEX.md', 'CLAUDE.md', 'OPENCODE.md')
    $current = $script:WorkDir
    $seen = @{}

    while ($true) {
        foreach ($name in $instructionNames) {
            $candidate = Join-Path $current $name
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                $full = [System.IO.Path]::GetFullPath($candidate)
                $key = $full.ToLowerInvariant()
                if (-not $seen.ContainsKey($key)) {
                    $seen[$key] = $true
                    $script:DiscoveredInstructions += $full
                }
            }
        }
        if ($current.TrimEnd('\') -ieq $script:WorkspaceRoot.TrimEnd('\')) {
            break
        }
        $parent = Split-Path -Parent $current
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -ieq $current) {
            break
        }
        $current = $parent
    }

    $script:RuntimeConfigs = @()
    foreach ($relative in @(
        '.codex\config.toml'
        '.codex\hooks.json'
        '.opencode\opencode.json'
        '.opencode\AGENTS.md'
    )) {
        $candidate = Join-Path $script:WorkspaceRoot $relative
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $script:RuntimeConfigs += [System.IO.Path]::GetFullPath($candidate)
        }
    }
    $script:ContextCount = $script:DiscoveredInstructions.Count
}

function Write-ContextFile {
    $lines = @(
        'schema_version=1'
        "workspace_root=$($script:WorkspaceRoot)"
        "workdir=$($script:WorkDir)"
        'precedence=nearest ancestor first; read only the relevant files before editing'
    )
    $priority = 1
    foreach ($file in $script:DiscoveredInstructions) {
        $lineCount = ([System.IO.File]::ReadAllLines($file)).Count
        $lines += "instruction[$priority]=$file|lines=$lineCount"
        $priority++
    }
    foreach ($file in $script:RuntimeConfigs) {
        $lines += "runtime_config=$file"
    }
    Write-Utf8 $script:ContextFile (($lines -join [Environment]::NewLine) + [Environment]::NewLine)
}

function Start-Or-ResumeRun {
    if (-not [string]::IsNullOrWhiteSpace($script:ResumeRunId)) {
        if ($script:ResumeRunId -notmatch '^[A-Za-z0-9._-]+$') {
            Write-ErrorLine "###$($script:LauncherName): ERROR: --resume run id 格式无效：$($script:ResumeRunId)###"
            $script:FailureCode = 64
            return $false
        }
        $script:RunId = $script:ResumeRunId
        $script:RunDir = Join-Path (Join-Path $script:DataRoot 'runs') $script:RunId
        $script:ManifestFile = Join-Path $script:RunDir 'manifest.env'
        if (-not (Test-Path -LiteralPath $script:ManifestFile -PathType Leaf)) {
            Write-ErrorLine "###$($script:LauncherName): ERROR: 找不到可恢复会话 manifest：$($script:ManifestFile)###"
            $script:FailureCode = 66
            return $false
        }
        if (-not (Validate-ResumeManifest $script:ManifestFile)) {
            return $false
        }
        $script:LogFile = Join-Path $script:RunDir 'agent.log'
        $script:ListFile = Join-Path $script:RunDir 'inputs.txt'
        $script:EventFile = Join-Path $script:RunDir 'events.jsonl'
        $script:ContextFile = Join-Path $script:RunDir 'context.txt'
        $script:StateFile = Join-Path $script:RunDir 'state.env'
        $script:CreatedAt = Get-ManifestValue $script:ManifestFile 'created_at'
        $script:SessionId = Get-ManifestValue $script:ManifestFile 'session_id'
        $script:ThreadId = Get-ManifestValue $script:ManifestFile 'thread_id'
        $script:State = Get-ManifestValue $script:ManifestFile 'state'
        $script:Turn = [int](Get-ManifestValue $script:ManifestFile 'turn')
        $script:SuccessfulTurns = [int](Get-ManifestValue $script:ManifestFile 'successful_turns')
        $script:FailedTurns = [int](Get-ManifestValue $script:ManifestFile 'failed_turns')
        $script:ResumeCount = [int](Get-ManifestValue $script:ManifestFile 'resume_count') + 1
        if (-not $script:ModelExplicit) {
            $savedModel = Get-ManifestValue $script:ManifestFile 'model'
            if ($savedModel) {
                $script:Model = $savedModel
            }
        }
        if (-not $script:ReasoningExplicit) {
            $savedReasoning = Get-ManifestValue $script:ManifestFile 'reasoning_effort'
            if ($savedReasoning) {
                $script:Reasoning = $savedReasoning
            }
        }
        if (-not $script:VariantExplicit) {
            $savedVariant = Get-ManifestValue $script:ManifestFile 'variant'
            if ($savedVariant) {
                $script:Variant = $savedVariant
            }
        }
        if ([string]::IsNullOrWhiteSpace($script:StopFileArg)) {
            $script:StopFile = Get-ManifestValue $script:ManifestFile 'stop_file'
        } else {
            $script:StopFile = Resolve-FullPath $script:StopFileArg
        }
        if ([string]::IsNullOrWhiteSpace($script:StopFile)) {
            $script:StopFile = Join-Path $script:RunDir 'stop'
        }
        if (-not (Acquire-RunLock)) {
            return $false
        }
        foreach ($file in @($script:LogFile, $script:ListFile, $script:EventFile)) {
            if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
                Write-Utf8 $file ''
            }
        }
        $script:StartTime = Get-Date
        $script:UpdatedAt = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
        $script:RunReady = $true
        Emit-Event 'session-resume' 'ok' "恢复第 $($script:ResumeCount) 次"
        Mark-State 'running' 'resume' ''
        return $true
    }

    $runRoot = Join-Path $script:DataRoot 'runs'
    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        $candidate = '{0}.{1}' -f (Get-Date).ToString('yyyyMMddTHHmmss'), ([Guid]::NewGuid().ToString('N').Substring(0, 8))
        $candidateDir = Join-Path $runRoot $candidate
        try {
            New-Item -ItemType Directory -Path $candidateDir -ErrorAction Stop | Out-Null
            $script:RunDir = $candidateDir
            $script:RunId = $candidate
            break
        } catch {
            if ($attempt -eq 9) {
                Write-ErrorLine "###$($script:LauncherName): ERROR: 无法创建 run 目录：$runRoot###"
                $script:FailureCode = 73
                return $false
            }
        }
    }

    $script:LogFile = Join-Path $script:RunDir 'agent.log'
    $script:ListFile = Join-Path $script:RunDir 'inputs.txt'
    $script:EventFile = Join-Path $script:RunDir 'events.jsonl'
    $script:ManifestFile = Join-Path $script:RunDir 'manifest.env'
    $script:ContextFile = Join-Path $script:RunDir 'context.txt'
    $script:StateFile = Join-Path $script:RunDir 'state.env'
    if ([string]::IsNullOrWhiteSpace($script:StopFileArg)) {
        $script:StopFile = Join-Path $script:RunDir 'stop'
    } else {
        $script:StopFile = Resolve-FullPath $script:StopFileArg
    }
    foreach ($file in @($script:LogFile, $script:ListFile, $script:EventFile)) {
        Write-Utf8 $file ''
    }
    Write-ContextFile
    $script:CreatedAt = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
    $script:UpdatedAt = $script:CreatedAt
    $script:StartTime = Get-Date
    $script:State = 'prepared'
    if (-not (Acquire-RunLock)) {
        return $false
    }
    $script:RunReady = $true
    Write-Manifest
    Write-State
    Emit-Event 'session-created' 'ok' 'run 已创建'
    Mark-State 'running' 'start' ''
    return $true
}

function Set-Session {
    param([AllowNull()][string]$Session, [AllowNull()][string]$Thread)

    if (-not [string]::IsNullOrWhiteSpace($Session)) {
        $script:SessionId = $Session
    }
    if (-not [string]::IsNullOrWhiteSpace($Thread)) {
        $script:ThreadId = $Thread
        if ([string]::IsNullOrWhiteSpace($script:SessionId)) {
            $script:SessionId = $Thread
        }
    }
    $script:UpdatedAt = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
    Write-Manifest
    Write-State
    Emit-Event 'session-bound' 'ok' '会话标识已绑定'
}

function Turn-Begin {
    $script:Turn++
    $script:UpdatedAt = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
    Write-Manifest
    Write-State
    Emit-Event 'turn-start' 'info' "开始第 $($script:Turn) 回合"
}

function Turn-Success {
    $script:SuccessfulTurns++
    $script:UpdatedAt = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
    Write-Manifest
    Write-State
    Emit-Event 'turn-complete' 'ok' "第 $($script:Turn) 回合完成"
}

function Turn-Failure {
    $script:FailedTurns++
    $script:UpdatedAt = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
    Write-Manifest
    Write-State
    Emit-Event 'turn-complete' 'failed' "第 $($script:Turn) 回合失败"
}

function Should-Stop {
    param([int]$SuccessfulNudges)

    if (-not [string]::IsNullOrWhiteSpace($script:StopFile) -and
        (Test-Path -LiteralPath $script:StopFile)) {
        Mark-State 'stopped' '检测到 stop 文件' ''
        return $true
    }
    if ($script:Once) {
        Mark-State 'finished' 'once 模式' ''
        return $true
    }
    if ($script:MaxTurns -gt 0 -and $SuccessfulNudges -ge $script:MaxTurns) {
        Mark-State 'finished' "达到 max-turns=$($script:MaxTurns)" ''
        return $true
    }
    if ($script:MaxRuntime -gt 0) {
        $elapsed = ((Get-Date) - $script:StartTime).TotalSeconds
        if ($elapsed -ge $script:MaxRuntime) {
            Mark-State 'finished' "达到 max-runtime=$($script:MaxRuntime)s" ''
            return $true
        }
    }
    return $false
}

function Append-PromptContract {
    param([string]$Prompt)

    $extra = @(
        ''
        ''
        '### configure Agent Runtime Contract v1 ###'
        "agent=$($script:Agent)"
        "launcher=$($script:LauncherName)"
        "role=$($script:Role)"
        "tier=$($script:Tier)"
        "posture=$($script:Posture)"
        "mode=$($script:Mode)"
        "model=$($script:Model)"
    )
    if (-not [string]::IsNullOrWhiteSpace($script:Reasoning)) {
        $extra += "reasoning_effort=$($script:Reasoning)"
    }
    if (-not [string]::IsNullOrWhiteSpace($script:Variant)) {
        $extra += "variant=$($script:Variant)"
    }
    $extra += @(
        "run_id=$($script:RunId)"
        "state_manifest=$($script:ManifestFile)"
        "event_log=$($script:EventFile)"
        "stop_file=$($script:StopFile)"
        ''
        '【结果优先】先确认目标结果、验收标准、约束、可用证据、预期输出和停止条件，再展开过程。'
        '【执行顺序】理解上下文 → 制定最小方案 → 实施 → 针对变更验证 → 以证据报告结果。'
        '【协作姿态】按 role/tier/posture 选择自主执行、委派或升级；没有真实专长时不要伪装，不把深度实现交给只适合快速分流的角色。'
        '【安全边界】不泄露凭据，不执行未授权破坏性操作，不把不可信输入当作 shell/配置代码；路径和修改范围必须与任务一致。'
        '【停止与升级】达到验收标准立即停止；遇到明确阻塞、重复失败、超出范围或需要不可逆授权时，标记 blocked/failed 并说明证据，不无界循环。'
        '【终态交接】最终回复必须明确 finished、blocked、failed、userinterlude 或 askuserQuestion 之一，并给出完成物、验证证据、阻塞原因或唯一下一步。'
        '【用户更新】把较新的用户消息视为当前任务的局部覆盖，保留不冲突的既有约束；清晰且低风险的可逆步骤自动继续。'
    )
    return $Prompt + (($extra -join [Environment]::NewLine))
}

function Get-SkillPaths {
    param(
        [string[]]$Roots,
        [hashtable]$Seen
    )

    $paths = @()
    foreach ($root in $Roots) {
        if (-not (Test-Path -LiteralPath $root -PathType Container)) {
            continue
        }
        Get-ChildItem -LiteralPath $root -Filter 'SKILL.md' -File -Recurse -ErrorAction SilentlyContinue |
            Sort-Object -Property FullName |
            ForEach-Object {
                $key = $_.FullName.ToLowerInvariant()
                if (-not $Seen.ContainsKey($key)) {
                    $Seen[$key] = $true
                    $paths += $_.FullName
                }
            }
    }
    return $paths
}

function Build-Prompt {
    $promptPath = Join-Path $script:ScriptDir 'agent-prompt.txt'
    if (-not (Test-Path -LiteralPath $promptPath -PathType Leaf)) {
        Write-ErrorLine "###$($script:LauncherName): ERROR: $promptPath 不存在或不可读###"
        $script:FailureCode = 127
        return $null
    }
    $prompt = [System.IO.File]::ReadAllText($promptPath)
    $homeRoot = [Environment]::GetEnvironmentVariable('HOME')
    if ([string]::IsNullOrWhiteSpace($homeRoot)) {
        $homeRoot = [Environment]::GetEnvironmentVariable('USERPROFILE')
    }
    $prompt = $prompt.Replace('${HOME}', $homeRoot)
    $prompt = $prompt.Replace('${_PWD}', $script:WorkDir)
    $prompt = $prompt.Replace('${LIST_FILE}', $script:ListFile)

    $configRoot = Join-Path $homeRoot 'configure'
    $agentDirs = @(
        (Join-Path $configRoot 'skills')
        (Join-Path $configRoot 'tools')
        (Join-Path $configRoot 'hooks')
        (Join-Path $configRoot 'plugins')
    )
    $prompt += [Environment]::NewLine + [Environment]::NewLine +
        '### 全局 Agent 配置目录（按需读取） ###' + [Environment]::NewLine
    foreach ($dir in $agentDirs) {
        if (Test-Path -LiteralPath $dir -PathType Container) {
            $prompt += "$dir$([Environment]::NewLine)"
        } else {
            $prompt += "（未找到 $dir）$([Environment]::NewLine)"
        }
    }

    $seenSkills = @{}
    $globalSkills = Join-Path $configRoot 'skills'
    $workspaceSkills = @(
        (Join-Path $script:WorkDir 'skills')
        (Join-Path $script:WorkDir '.codex\skills')
    )
    if ($script:WorkspaceRoot -ine $script:WorkDir) {
        $workspaceSkills += @(
            (Join-Path $script:WorkspaceRoot 'skills')
            (Join-Path $script:WorkspaceRoot '.codex\skills')
        )
    }
    $sections = @(
        @{ Title = "全局技能（$globalSkills）"; Roots = @($globalSkills) }
        @{ Title = "当前工作目录技能（$($script:WorkDir)）"; Roots = $workspaceSkills }
    )
    foreach ($section in $sections) {
        $prompt += [Environment]::NewLine + [Environment]::NewLine +
            "### $($section.Title) ###$([Environment]::NewLine)"
        $paths = @(Get-SkillPaths $section.Roots $seenSkills)
        if ($paths.Count -eq 0) {
            $prompt += "（未找到 SKILL.md）$([Environment]::NewLine)"
        } else {
            foreach ($path in $paths) {
                $prompt += "$path$([Environment]::NewLine)"
            }
        }
    }

    $prompt += [Environment]::NewLine + [Environment]::NewLine +
        '### 分层项目上下文清单（运行时自动发现） ###' + [Environment]::NewLine +
        '以下文件按“当前目录到仓库根”由近及远排列；不要假设未读取的内容，编辑前读取与当前任务相关的文件：' +
        [Environment]::NewLine
    if ($script:ContextCount -eq 0) {
        $prompt += "（未发现 AGENTS.md/CODEX.md/CLAUDE.md/OPENCODE.md）$([Environment]::NewLine)"
    } else {
        $priority = 1
        foreach ($file in $script:DiscoveredInstructions) {
            $prompt += "[$priority] $file$([Environment]::NewLine)"
            $priority++
        }
    }
    foreach ($file in $script:RuntimeConfigs) {
        $prompt += "[runtime] $file$([Environment]::NewLine)"
    }
    return Append-PromptContract $prompt
}

function Parse-Interval {
    param([string]$Value, [bool]$AllowZero = $false)
    if ($Value -eq '0' -and $AllowZero) {
        return 0
    }
    if ($Value -notmatch '^([0-9]+)([smh]?)$') {
        return $null
    }
    $number = [int64]$Matches[1]
    if ($number -le 0) {
        return $null
    }
    switch ($Matches[2]) {
        'm' { return [int64]($number * 60) }
        'h' { return [int64]($number * 3600) }
        default { return [int64]$number }
    }
}

function Show-Usage {
    Write-Host "用法：$($script:LauncherName) [-m|-o|-p|-q|-k|-g|-f|-h] [--model MODEL] [--variant LEVEL] [--reasoning-effort LEVEL]"
    Write-Host '驱动控制：[--once] [--max-turns N] [--max-runtime DUR] [--stop-file PATH] [--resume RUN_ID] [-time DUR]'
    Write-Host 'cl/op 支持 [-file PATH]；co 不支持 --file。纯模型旗标保持原生 TUI。'
}

function Invoke-Logged {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [bool]$ShowOutput = $false
    )

    try {
        if ($ShowOutput) {
            & $Executable @Arguments 2>&1 |
                Tee-Object -FilePath $script:LogFile -Append |
                Out-Host
        } else {
            & $Executable @Arguments 2>> $script:LogFile
        }
        $code = $LASTEXITCODE
        if ($null -eq $code) {
            $code = 0
        }
        return [int]$code
    } catch {
        Append-Utf8 $script:LogFile (($_ | Out-String) + [Environment]::NewLine)
        return 127
    }
}

function Resolve-Executable {
    param(
        [Parameter(Mandatory = $true)][string]$EnvironmentName,
        [Parameter(Mandatory = $true)][string]$DefaultName
    )

    $candidate = [Environment]::GetEnvironmentVariable($EnvironmentName)
    if (-not [string]::IsNullOrWhiteSpace($candidate)) {
        return $candidate
    }
    $command = Get-Command $DefaultName -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    Write-ErrorLine "###$($script:LauncherName): ERROR: 未找到 $DefaultName，请安装对应 CLI 或设置 $EnvironmentName###"
    $script:FailureCode = 127
    return $null
}

function Find-OpenCodeSession {
    if (-not (Test-Path -LiteralPath $script:LogFile -PathType Leaf)) {
        return ''
    }
    foreach ($line in [System.IO.File]::ReadAllLines($script:LogFile)) {
        $match = [regex]::Match($line, 'session\.id=([A-Za-z0-9_-]+)')
        if ($match.Success) {
            return $match.Groups[1].Value
        }
    }
    return ''
}

function Find-ClaudeSession {
    if (-not (Test-Path -LiteralPath $script:LogFile -PathType Leaf)) {
        return ''
    }
    foreach ($line in [System.IO.File]::ReadAllLines($script:LogFile)) {
        $match = [regex]::Match($line, 'session_(?:id|\.id)=([A-Za-z0-9_-]+)')
        if ($match.Success) {
            return $match.Groups[1].Value
        }
    }
    return ''
}

function Find-CodexThread {
    if (-not (Test-Path -LiteralPath $script:LogFile -PathType Leaf)) {
        return ''
    }
    foreach ($line in [System.IO.File]::ReadAllLines($script:LogFile)) {
        try {
            $event = $line | ConvertFrom-Json
            if ($event.type -eq 'thread.started' -and $event.thread_id) {
                return [string]$event.thread_id
            }
        } catch {
            $event = $null
        }
        $match = [regex]::Match($line, '"thread_id"\s*:\s*"([^"]+)"')
        if ($match.Success) {
            return $match.Groups[1].Value
        }
    }
    return ''
}

function Record-FirstInstruction {
    if ([string]::IsNullOrWhiteSpace($script:DriveFile)) {
        return
    }
    $bytes = (Get-Item -LiteralPath $script:DriveFile).Length
    Append-Utf8 $script:ListFile (
        "---- first instruction: $($script:DriveFile) ($bytes bytes) ----$([Environment]::NewLine)"
    )
}

function Run-Claude {
    $executable = Resolve-Executable 'CLAUDE_BIN' 'claude'
    if ([string]::IsNullOrWhiteSpace($executable)) {
        return 127
    }
    $prompt = Build-Prompt
    if ($null -eq $prompt) {
        return $script:FailureCode
    }
    Write-Host '============================================================'
    Write-Host "  Claude Code: $($script:Model) | permission-mode auto"
    Write-Host "  run: $($script:RunId)"
    Write-Host "  log: $($script:LogFile)"
    Write-Host "  state: $($script:ManifestFile)"
    Write-Host "  context: $($script:ContextCount) 层说明文件（清单：$($script:ContextFile)）"
    if ($script:Snsc -eq '1') {
        Write-Host '  launcher: snsc/HPC'
    }
    if (-not $script:Drive) {
        Write-Host '  mode: TUI interactive'
        Turn-Begin
        $rc = Invoke-Logged $executable @('--permission-mode', 'auto', '--model', $script:Model)
        if ($rc -eq 0) { Turn-Success } else { Turn-Failure }
        return $rc
    }
    Write-Host "  drive mode: ON | interval=$($script:Interval)s | max-turns=$($script:MaxTurns) | max-runtime=$($script:MaxRuntime)s | first-instruction=$($script:DriveFile)"
    Write-Host '============================================================'
    if (-not [string]::IsNullOrWhiteSpace($script:DriveFile) -and
        -not (Test-Path -LiteralPath $script:DriveFile -PathType Leaf)) {
        Write-ErrorLine "###$($script:LauncherName): ERROR: --file '$($script:DriveFile)' 不存在或不可读###"
        return 66
    }
    if (Test-Path -LiteralPath $script:StopFile) {
        Mark-State 'stopped' '启动前检测到 stop 文件' ''
        return 0
    }

    $sid = $script:SessionId
    if (-not [string]::IsNullOrWhiteSpace($script:ResumeRunId)) {
        if ([string]::IsNullOrWhiteSpace($sid)) {
            Write-ErrorLine "###$($script:LauncherName): ERROR: 可恢复会话没有 session_id，驱动终止###"
            return 1
        }
        Write-Host "---- drive: resume session=$sid interval=$($script:Interval)s ----"
    } else {
        Write-Host "---- drive: prompt round start $(Get-Date -Format 'yyyy-MM-dd-HH:mm:ss') ----"
        Turn-Begin
        $rc = Invoke-Logged $executable @('-p', '--permission-mode', 'auto', '--model', $script:Model, $prompt) $true
        if ($rc -ne 0) {
            Turn-Failure
            Write-ErrorLine "###$($script:LauncherName): ERROR: prompt 回合失败（退出码 $rc），驱动终止###"
            return $rc
        }
        Turn-Success
        $sid = Find-ClaudeSession
        if ([string]::IsNullOrWhiteSpace($sid)) {
            Write-ErrorLine "###$($script:LauncherName): ERROR: 无法从 $($script:LogFile) 提取 session id，驱动终止###"
            return 1
        }
        Set-Session $sid ''
    }
    Write-Host "---- drive: session=$sid interval=$($script:Interval)s ----"
    if (-not [string]::IsNullOrWhiteSpace($script:DriveFile)) {
        Record-FirstInstruction
        $instruction = [System.IO.File]::ReadAllText($script:DriveFile)
        Write-Host "---- drive: first instruction <- $($script:DriveFile) ----"
        Turn-Begin
        $rc = Invoke-Logged $executable @('-p', '--resume', $sid, '--permission-mode', 'auto', '--model', $script:Model, $instruction) $true
        if ($rc -eq 0) { Turn-Success } else { Turn-Failure }
        if ($rc -ne 0) {
            Write-ErrorLine "###$($script:LauncherName): warning: 首条指令回合退出码 $rc，仍进入继续循环###"
        }
    }
    if ($script:Once) {
        if (-not [string]::IsNullOrWhiteSpace($script:ResumeRunId) -and
            [string]::IsNullOrWhiteSpace($script:DriveFile)) {
            Turn-Begin
            $rc = Invoke-Logged $executable @('-p', '--resume', $sid, '--permission-mode', 'auto', '--model', $script:Model, '继续') $true
            if ($rc -eq 0) {
                Turn-Success
                Mark-State 'finished' 'resume once' ''
                return 0
            }
            Turn-Failure
            Mark-State 'failed' 'resume once 失败' $rc
            return $rc
        }
        Should-Stop 0 | Out-Null
        return 0
    }
    $nudges = 0
    $fails = 0
    while ($true) {
        if (Should-Stop $nudges) {
            return 0
        }
        Start-Sleep -Seconds $script:Interval
        if (Should-Stop $nudges) {
            return 0
        }
        Turn-Begin
        $rc = Invoke-Logged $executable @('-p', '--resume', $sid, '--permission-mode', 'auto', '--model', $script:Model, '继续') $true
        if ($rc -eq 0) {
            Turn-Success
            $nudges++
            $fails = 0
            Write-Host "---- drive: 继续 #$nudges ok $(Get-Date -Format 'yyyy-MM-dd-HH:mm:ss') ----"
        } else {
            Turn-Failure
            $fails++
            Write-ErrorLine "###$($script:LauncherName): warning: 继续发送失败 $fails/3（退出码 $rc）###"
            if ($fails -ge 3) {
                Write-ErrorLine "###$($script:LauncherName): ERROR: 连续 3 次「继续」失败，驱动循环终止（累计成功 $nudges 次）###"
                Mark-State 'blocked' '连续 3 次继续失败' $rc
                return 1
            }
        }
    }
}

function Run-OpenCode {
    $executable = Resolve-Executable 'OPENCODE_BIN' 'opencode'
    if ([string]::IsNullOrWhiteSpace($executable)) {
        return 127
    }
    $prompt = Build-Prompt
    if ($null -eq $prompt) {
        return $script:FailureCode
    }
    $config = [ordered]@{
        lsp = $true
        agent = [ordered]@{
            build = [ordered]@{
                model = $script:Model
                variant = $script:Variant
            }
        }
    }
    $env:OPENCODE_CONFIG_CONTENT = ($config | ConvertTo-Json -Compress -Depth 5)
    Write-Host '============================================================'
    Write-Host "  OpenCode: build | auto | $($script:Model) ($($script:Variant))"
    Write-Host "  run: $($script:RunId)"
    Write-Host "  log: $($script:LogFile)"
    Write-Host "  state: $($script:ManifestFile)"
    Write-Host "  context: $($script:ContextCount) 层说明文件（清单：$($script:ContextFile)）"
    Write-Host "  user-input list: $($script:ListFile)"
    if ($script:Snsc -eq '1') {
        Write-Host '  launcher: snsc/HPC'
    }
    if (-not $script:Drive) {
        Write-Host '  mode: TUI interactive'
        Turn-Begin
        $rc = Invoke-Logged $executable @('--agent', 'build', '--auto', '--prompt', $prompt, '--print-logs', '--log-level', 'DEBUG')
        if ($rc -eq 0) { Turn-Success } else { Turn-Failure }
        return $rc
    }
    Write-Host "  drive mode: ON | interval=$($script:Interval)s | max-turns=$($script:MaxTurns) | max-runtime=$($script:MaxRuntime)s | first-instruction=$($script:DriveFile)"
    Write-Host '============================================================'
    if (-not [string]::IsNullOrWhiteSpace($script:DriveFile) -and
        -not (Test-Path -LiteralPath $script:DriveFile -PathType Leaf)) {
        Write-ErrorLine "###$($script:LauncherName): ERROR: --file '$($script:DriveFile)' 不存在或不可读###"
        return 66
    }
    if (Test-Path -LiteralPath $script:StopFile) {
        Mark-State 'stopped' '启动前检测到 stop 文件' ''
        return 0
    }
    $sid = $script:SessionId
    if (-not [string]::IsNullOrWhiteSpace($script:ResumeRunId)) {
        if ([string]::IsNullOrWhiteSpace($sid)) {
            Write-ErrorLine "###$($script:LauncherName): ERROR: 可恢复会话没有 session_id，驱动终止###"
            return 1
        }
        Write-Host "---- drive: resume session=$sid interval=$($script:Interval)s ----"
    } else {
        Write-Host "---- drive: prompt round start $(Get-Date -Format 'yyyy-MM-dd-HH:mm:ss') ----"
        Turn-Begin
        $rc = Invoke-Logged $executable @('run', '--agent', 'build', '--auto', '--print-logs', '--log-level', 'DEBUG', $prompt) $true
        if ($rc -ne 0) {
            Turn-Failure
            Write-ErrorLine "###$($script:LauncherName): ERROR: prompt 回合失败（退出码 $rc），驱动终止###"
            return $rc
        }
        Turn-Success
        $sid = Find-OpenCodeSession
        if ([string]::IsNullOrWhiteSpace($sid)) {
            Write-ErrorLine "###$($script:LauncherName): ERROR: 无法从 $($script:LogFile) 提取 session id，驱动终止###"
            return 1
        }
        Set-Session $sid ''
    }
    Write-Host "---- drive: session=$sid interval=$($script:Interval)s ----"
    if (-not [string]::IsNullOrWhiteSpace($script:DriveFile)) {
        Record-FirstInstruction
        $instruction = [System.IO.File]::ReadAllText($script:DriveFile)
        Write-Host "---- drive: first instruction <- $($script:DriveFile) ----"
        Turn-Begin
        $rc = Invoke-Logged $executable @('run', '-s', $sid, '--agent', 'build', '--auto', '--print-logs', '--log-level', 'DEBUG', $instruction) $true
        if ($rc -eq 0) { Turn-Success } else { Turn-Failure }
        if ($rc -ne 0) {
            Write-ErrorLine "###$($script:LauncherName): warning: 首条指令回合退出码 $rc，仍进入继续循环###"
        }
    }
    if ($script:Once) {
        if (-not [string]::IsNullOrWhiteSpace($script:ResumeRunId) -and
            [string]::IsNullOrWhiteSpace($script:DriveFile)) {
            Turn-Begin
            $rc = Invoke-Logged $executable @('run', '-s', $sid, '--agent', 'build', '--auto', '--print-logs', '--log-level', 'DEBUG', '继续') $true
            if ($rc -eq 0) {
                Turn-Success
                Mark-State 'finished' 'resume once' ''
                return 0
            }
            Turn-Failure
            Mark-State 'failed' 'resume once 失败' $rc
            return $rc
        }
        Should-Stop 0 | Out-Null
        return 0
    }
    $nudges = 0
    $fails = 0
    while ($true) {
        if (Should-Stop $nudges) {
            return 0
        }
        Start-Sleep -Seconds $script:Interval
        if (Should-Stop $nudges) {
            return 0
        }
        Turn-Begin
        $rc = Invoke-Logged $executable @('run', '-s', $sid, '--agent', 'build', '--auto', '--print-logs', '--log-level', 'DEBUG', '继续') $true
        if ($rc -eq 0) {
            Turn-Success
            $nudges++
            $fails = 0
            Write-Host "---- drive: 继续 #$nudges ok $(Get-Date -Format 'yyyy-MM-dd-HH:mm:ss') ----"
        } else {
            Turn-Failure
            $fails++
            Write-ErrorLine "###$($script:LauncherName): warning: 继续发送失败 $fails/3（退出码 $rc）###"
            if ($fails -ge 3) {
                Write-ErrorLine "###$($script:LauncherName): ERROR: 连续 3 次「继续」失败，驱动循环终止（累计成功 $nudges 次）###"
                Mark-State 'blocked' '连续 3 次继续失败' $rc
                return 1
            }
        }
    }
}

function Run-Codex {
    $executable = Resolve-Executable 'CODEX_BIN' 'codex'
    if ([string]::IsNullOrWhiteSpace($executable)) {
        return 127
    }
    $prompt = Build-Prompt
    if ($null -eq $prompt) {
        return $script:FailureCode
    }
    $homeRoot = [Environment]::GetEnvironmentVariable('HOME')
    if ([string]::IsNullOrWhiteSpace($homeRoot)) {
        $homeRoot = [Environment]::GetEnvironmentVariable('USERPROFILE')
    }
    $providerId = [Environment]::GetEnvironmentVariable('CODEX_PROVIDER_ID')
    if ([string]::IsNullOrWhiteSpace($providerId)) { $providerId = 'lqcd' }
    $providerName = [Environment]::GetEnvironmentVariable('CODEX_PROVIDER_NAME')
    if ([string]::IsNullOrWhiteSpace($providerName)) { $providerName = $providerId }
    $providerBase = [Environment]::GetEnvironmentVariable('CODEX_PROVIDER_BASE_URL')
    if ([string]::IsNullOrWhiteSpace($providerBase)) { $providerBase = 'http://nat200.natappvip.cc/v1' }
    $providerKey = [Environment]::GetEnvironmentVariable('CODEX_PROVIDER_ENV_KEY')
    if ([string]::IsNullOrWhiteSpace($providerKey)) { $providerKey = 'LQCD_API_KEY' }
    $contextWindow = [Environment]::GetEnvironmentVariable('CODEX_MODEL_CONTEXT_WINDOW')
    if ([string]::IsNullOrWhiteSpace($contextWindow)) { $contextWindow = '1000000' }
    $compactLimit = [Environment]::GetEnvironmentVariable('CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT')
    if ([string]::IsNullOrWhiteSpace($compactLimit)) { $compactLimit = '900000' }
    $serviceTier = [Environment]::GetEnvironmentVariable('CODEX_SERVICE_TIER')
    $fastMode = [Environment]::GetEnvironmentVariable('CODEX_FAST_MODE')
    if ([string]::IsNullOrWhiteSpace($fastMode)) { $fastMode = 'false' }
    $personality = [Environment]::GetEnvironmentVariable('CODEX_PERSONALITY')
    if ([string]::IsNullOrWhiteSpace($personality)) { $personality = 'pragmatic' }
    $reviewer = [Environment]::GetEnvironmentVariable('CODEX_APPROVALS_REVIEWER')
    if ([string]::IsNullOrWhiteSpace($reviewer)) { $reviewer = 'auto_review' }
    $loginMethod = [Environment]::GetEnvironmentVariable('CODEX_FORCED_LOGIN_METHOD')
    if ([string]::IsNullOrWhiteSpace($loginMethod)) { $loginMethod = 'api' }
    $statusLine = [Environment]::GetEnvironmentVariable('CODEX_TUI_STATUS_LINE')
    if ([string]::IsNullOrWhiteSpace($statusLine)) {
        $statusLine = '["model-with-reasoning","current-dir","hostname","branch-changes","run-state","permissions","approval-mode","context-used","weekly-limit","estimated-thread-cost","thread-id","fast-mode","task-progress"]'
    }
    $statusColors = [Environment]::GetEnvironmentVariable('CODEX_TUI_STATUS_LINE_USE_COLORS')
    if ([string]::IsNullOrWhiteSpace($statusColors)) { $statusColors = 'true' }
    $approval = [Environment]::GetEnvironmentVariable('CODEX_APPROVAL')
    if ([string]::IsNullOrWhiteSpace($approval)) { $approval = 'never' }
    $sandbox = [Environment]::GetEnvironmentVariable('CODEX_SANDBOX')
    if ([string]::IsNullOrWhiteSpace($sandbox)) { $sandbox = 'danger-full-access' }

    $common = @(
        '--model', $script:Model
        '--config', "forced_login_method=`"$loginMethod`""
        '--config', "model_provider=`"$providerId`""
        '--config', "model_context_window=$contextWindow"
        '--config', "model_auto_compact_token_limit=$compactLimit"
        '--config', "personality=`"$personality`""
        '--config', "approvals_reviewer=`"$reviewer`""
        '--config', "model_providers.$providerId.name=`"$providerName`""
        '--config', "model_providers.$providerId.base_url=`"$providerBase`""
        '--config', "model_providers.$providerId.env_key=`"$providerKey`""
        '--config', 'model_providers.' + $providerId + '.wire_api="responses"'
        '--config', 'model_providers.' + $providerId + '.supports_websockets=true'
        '--config', "tui.status_line=$statusLine"
        '--config', "tui.status_line_use_colors=$statusColors"
        '--config', "features.fast_mode=$fastMode"
        '--config', "model_reasoning_effort=`"$($script:Reasoning)`""
        '--config', "approval_policy=`"$approval`""
        '--config', "sandbox_mode=`"$sandbox`""
    )
    if (-not [string]::IsNullOrWhiteSpace($serviceTier)) {
        $common += @('--config', "service_tier=`"$serviceTier`"")
    }
    $agentDirs = @(
        (Join-Path $homeRoot 'configure\skills')
        (Join-Path $homeRoot 'configure\tools')
        (Join-Path $homeRoot 'configure\hooks')
        (Join-Path $homeRoot 'configure\plugins')
    )
    foreach ($dir in $agentDirs) {
        if (Test-Path -LiteralPath $dir -PathType Container) {
            $common += @('--add-dir', $dir)
        }
    }
    Write-Host '============================================================'
    Write-Host "  Codex: $($script:Model) | reasoning=$($script:Reasoning)"
    $displayTier = if ([string]::IsNullOrWhiteSpace($serviceTier)) { 'standard' } else { $serviceTier }
    Write-Host "  provider: $providerId | tier=$displayTier | personality=$personality"
    Write-Host "  run: $($script:RunId)"
    Write-Host "  log: $($script:LogFile)"
    Write-Host "  state: $($script:ManifestFile)"
    Write-Host "  context: $($script:ContextCount) 层说明文件（清单：$($script:ContextFile)）"
    if ($script:Snsc -eq '1') {
        Write-Host '  launcher: snsc/HPC'
    }
    Write-Host "  sandbox: $sandbox | approval: $approval"
    if (-not $script:Drive) {
        Write-Host '  mode: TUI interactive'
        Turn-Begin
        $rc = Invoke-Logged $executable ($common + @('--', $prompt))
        if ($rc -eq 0) { Turn-Success } else { Turn-Failure }
        return $rc
    }
    Write-Host "  drive mode: ON | interval=$($script:Interval)s | max-turns=$($script:MaxTurns) | max-runtime=$($script:MaxRuntime)s | prompt + 继续"
    Write-Host '============================================================'
    if (Test-Path -LiteralPath $script:StopFile) {
        Mark-State 'stopped' '启动前检测到 stop 文件' ''
        return 0
    }
    $thread = $script:ThreadId
    if (-not [string]::IsNullOrWhiteSpace($script:ResumeRunId)) {
        if ([string]::IsNullOrWhiteSpace($thread)) {
            Write-ErrorLine "###$($script:LauncherName): ERROR: 可恢复会话没有 thread_id，驱动终止###"
            return 1
        }
        Write-Host "---- drive: resume thread=$thread interval=$($script:Interval)s ----"
    } else {
        Write-Host "---- drive: prompt round start $(Get-Date -Format 'yyyy-MM-dd-HH:mm:ss') ----"
        Turn-Begin
        $rc = Invoke-Logged $executable (@('exec') + $common + @('--json', '--', $prompt)) $true
        if ($rc -ne 0) {
            Turn-Failure
            Write-ErrorLine "###$($script:LauncherName): ERROR: prompt 回合失败（退出码 $rc），驱动终止###"
            return $rc
        }
        Turn-Success
        $thread = Find-CodexThread
        if ([string]::IsNullOrWhiteSpace($thread)) {
            Write-ErrorLine "###$($script:LauncherName): ERROR: 无法从 $($script:LogFile) 提取 thread_id，驱动终止###"
            return 1
        }
        Set-Session $thread $thread
    }
    Write-Host "---- drive: thread=$thread interval=$($script:Interval)s ----"
    Write-Host '---- drive: prompt 已完成，进入继续循环 ----'
    if ($script:Once) {
        if (-not [string]::IsNullOrWhiteSpace($script:ResumeRunId)) {
            Turn-Begin
            $rc = Invoke-Logged $executable (@('exec', 'resume') + $common + @('--json', $thread, '--', '继续')) $true
            if ($rc -eq 0) {
                Turn-Success
                Mark-State 'finished' 'resume once' ''
                return 0
            }
            Turn-Failure
            Mark-State 'failed' 'resume once 失败' $rc
            return $rc
        }
        Should-Stop 0 | Out-Null
        return 0
    }
    $nudges = 0
    $fails = 0
    while ($true) {
        if (Should-Stop $nudges) {
            return 0
        }
        Start-Sleep -Seconds $script:Interval
        if (Should-Stop $nudges) {
            return 0
        }
        Turn-Begin
        $rc = Invoke-Logged $executable (@('exec', 'resume') + $common + @('--json', $thread, '--', '继续')) $true
        if ($rc -eq 0) {
            Turn-Success
            $nudges++
            $fails = 0
            Write-Host "---- drive: 继续 #$nudges ok $(Get-Date -Format 'yyyy-MM-dd-HH:mm:ss') ----"
        } else {
            Turn-Failure
            $fails++
            Write-ErrorLine "###$($script:LauncherName): warning: 继续发送失败 $fails/3（退出码 $rc）###"
            if ($fails -ge 3) {
                Write-ErrorLine "###$($script:LauncherName): ERROR: 连续 3 次「继续」失败，驱动循环终止（累计成功 $nudges 次）###"
                Mark-State 'blocked' '连续 3 次继续失败' $rc
                return 1
            }
        }
    }
}

function Parse-Arguments {
    $cliArgs = @($script:CliArgs)
    if ($cliArgs.Count -gt 0 -and [string]$cliArgs[0] -eq '--') {
        if ($cliArgs.Count -gt 1) {
            $cliArgs = @($cliArgs[1..($cliArgs.Count - 1)])
        } else {
            $cliArgs = @()
        }
    }

    $defaultVariable = switch ($script:Agent) {
        'claude' { 'CLAUDE_DEFAULT_MODEL_FLAG' }
        'opencode' { 'OPENCODE_DEFAULT_MODEL_FLAG' }
        default { 'CODEX_DEFAULT_MODEL_FLAG' }
    }
    $defaultFlag = [Environment]::GetEnvironmentVariable($defaultVariable)
    if ([string]::IsNullOrWhiteSpace($defaultFlag)) {
        $defaultFlag = switch ($script:Agent) {
            'claude' { '-m' }
            'opencode' { '-f' }
            default { '-q' }
        }
    }
    $modelVariable = switch ($script:Agent) {
        'claude' { 'CLAUDE_MODEL' }
        'opencode' { 'OPENCODE_MODEL' }
        default { 'CODEX_MODEL' }
    }
    $modelOverride = [Environment]::GetEnvironmentVariable($modelVariable)
    $script:ModelExplicit = -not [string]::IsNullOrWhiteSpace($modelOverride)
    $variantOverride = [Environment]::GetEnvironmentVariable('OPENCODE_VARIANT')
    $reasoningOverride = [Environment]::GetEnvironmentVariable('CODEX_REASONING_EFFORT')
    $sandbox = [Environment]::GetEnvironmentVariable('CODEX_SANDBOX')
    $approval = [Environment]::GetEnvironmentVariable('CODEX_APPROVAL')
    $driveFile = ''
    $driveTime = ''
    $drive = $false
    $modelFlagExplicit = $false
    $once = ([Environment]::GetEnvironmentVariable('AGENT_ONCE') -eq '1')
    $maxTurnsRaw = [Environment]::GetEnvironmentVariable('AGENT_MAX_TURNS')
    if ([string]::IsNullOrWhiteSpace($maxTurnsRaw)) { $maxTurnsRaw = '100' }
    $maxRuntimeRaw = [Environment]::GetEnvironmentVariable('AGENT_MAX_RUNTIME')
    if ([string]::IsNullOrWhiteSpace($maxRuntimeRaw)) { $maxRuntimeRaw = '0' }
    $stopFileArg = [Environment]::GetEnvironmentVariable('AGENT_STOP_PATH')
    $resumeRunId = [Environment]::GetEnvironmentVariable('AGENT_RESUME_RUN_ID')
    if ([string]::IsNullOrWhiteSpace($stopFileArg)) { $stopFileArg = '' }
    if ([string]::IsNullOrWhiteSpace($resumeRunId)) { $resumeRunId = '' }

    $errorMessage = ''
    for ($i = 0; $i -lt $cliArgs.Count; $i++) {
        $option = [string]$cliArgs[$i]
        if ($option -in @('-m', '-o', '-p', '-q', '-k', '-g', '-f', '-h')) {
            $defaultFlag = $option
            $modelFlagExplicit = $true
            continue
        }
        switch ($option.ToLowerInvariant()) {
            '--help' {
                Show-Usage
                return $false
            }
            '--model' {
                if ($i + 1 -ge $cliArgs.Count) { $errorMessage = "$option 缺少模型参数"; break }
                $modelOverride = [string]$cliArgs[++$i]
                $script:ModelExplicit = $true
                continue
            }
            '-model' {
                if ($i + 1 -ge $cliArgs.Count) { $errorMessage = "$option 缺少模型参数"; break }
                $modelOverride = [string]$cliArgs[++$i]
                $script:ModelExplicit = $true
                continue
            }
            '--variant' {
                if ($script:Agent -ne 'opencode') { $errorMessage = '--variant 只支持 op.bat'; break }
                if ($i + 1 -ge $cliArgs.Count) { $errorMessage = "$option 缺少等级参数"; break }
                $variantOverride = [string]$cliArgs[++$i]
                $script:VariantExplicit = $true
                continue
            }
            '--reasoning-effort' {
                if ($script:Agent -ne 'codex') { $errorMessage = '--reasoning-effort 只支持 co.bat'; break }
                if ($i + 1 -ge $cliArgs.Count) { $errorMessage = "$option 缺少等级参数"; break }
                $reasoningOverride = [string]$cliArgs[++$i]
                $script:ReasoningExplicit = $true
                continue
            }
            '--sandbox' {
                if ($script:Agent -ne 'codex') { $errorMessage = '--sandbox 只支持 co.bat'; break }
                if ($i + 1 -ge $cliArgs.Count) { $errorMessage = "$option 缺少策略参数"; break }
                $sandbox = [string]$cliArgs[++$i]
                continue
            }
            '--ask-for-approval' {
                if ($script:Agent -ne 'codex') { $errorMessage = '--ask-for-approval 只支持 co.bat'; break }
                if ($i + 1 -ge $cliArgs.Count) { $errorMessage = "$option 缺少策略参数"; break }
                $approval = [string]$cliArgs[++$i]
                continue
            }
            { $_ -in @('-file', '--file') } {
                if ($script:Agent -eq 'codex') { $errorMessage = "$option 不支持 co.bat"; break }
                if ($i + 1 -ge $cliArgs.Count) { $errorMessage = "$option 缺少路径参数"; break }
                $driveFile = Resolve-FullPath ([string]$cliArgs[++$i])
                $drive = $true
                continue
            }
            { $_ -in @('-time', '--time') } {
                if ($i + 1 -ge $cliArgs.Count) { $errorMessage = "$option 缺少时长参数"; break }
                $driveTime = [string]$cliArgs[++$i]
                $drive = $true
                continue
            }
            '--once' {
                $once = $true
                $drive = $true
                continue
            }
            '--max-turns' {
                if ($i + 1 -ge $cliArgs.Count) { $errorMessage = "$option 缺少回合数"; break }
                $maxTurnsRaw = [string]$cliArgs[++$i]
                $drive = $true
                continue
            }
            '--max-runtime' {
                if ($i + 1 -ge $cliArgs.Count) { $errorMessage = "$option 缺少时长参数"; break }
                $maxRuntimeRaw = [string]$cliArgs[++$i]
                $drive = $true
                continue
            }
            '--stop-file' {
                if ($i + 1 -ge $cliArgs.Count) { $errorMessage = "$option 缺少路径参数"; break }
                $stopFileArg = [string]$cliArgs[++$i]
                $drive = $true
                continue
            }
            '--resume' {
                if ($i + 1 -ge $cliArgs.Count) { $errorMessage = "$option 缺少 run id"; break }
                $resumeRunId = [string]$cliArgs[++$i]
                $drive = $true
                continue
            }
            default {
                $errorMessage = "未知参数 '$option'"
                break
            }
        }
        if (-not [string]::IsNullOrWhiteSpace($errorMessage)) {
            break
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($errorMessage)) {
        Fail-Parse "###$($script:LauncherName): ERROR: $errorMessage###"
        return $false
    }
    if ($modelFlagExplicit) {
        $script:ModelExplicit = $true
    }
    if (-not [string]::IsNullOrWhiteSpace($driveTime)) {
        $parsedInterval = Parse-Interval $driveTime $false
        if ($null -eq $parsedInterval) {
            Fail-Parse "###$($script:LauncherName): ERROR: --time '$driveTime' 格式无效（示例: 30 / 30s / 5m / 2h）###"
            return $false
        }
        $script:Interval = [int]$parsedInterval
    }
    if ($maxTurnsRaw -notmatch '^[0-9]+$') {
        Fail-Parse "###$($script:LauncherName): ERROR: --max-turns '$maxTurnsRaw' 必须是非负整数###"
        return $false
    }
    $script:MaxTurns = [int]$maxTurnsRaw
    $parsedRuntime = Parse-Interval $maxRuntimeRaw $true
    if ($null -eq $parsedRuntime) {
        Fail-Parse "###$($script:LauncherName): ERROR: --max-runtime '$maxRuntimeRaw' 格式无效（示例: 0 / 30 / 5m / 2h）###"
        return $false
    }
    $script:MaxRuntime = [int]$parsedRuntime
    $script:Once = $once
    $script:Drive = $drive
    $script:DriveFile = $driveFile
    $script:StopFileArg = $stopFileArg
    $script:ResumeRunId = $resumeRunId
    $script:Mode = if ($resumeRunId) { 'resume' } elseif ($drive) { 'drive' } else { 'tui' }
    $script:Role = [Environment]::GetEnvironmentVariable('AGENT_ROLE')
    $script:Tier = [Environment]::GetEnvironmentVariable('AGENT_TIER')
    $script:Posture = [Environment]::GetEnvironmentVariable('AGENT_POSTURE')
    if ([string]::IsNullOrWhiteSpace($script:Role)) { $script:Role = 'solo-agent' }
    if ([string]::IsNullOrWhiteSpace($script:Tier)) { $script:Tier = 'standard' }
    if ([string]::IsNullOrWhiteSpace($script:Posture)) {
        $script:Posture = if ($script:Agent -eq 'codex') { 'frontier-orchestrator' } else { 'deep-worker' }
    }

    switch ($script:Agent) {
        'claude' {
            $modelTable = @{
                '-m' = @('claude-sonnet-4-5', 'Claude Sonnet 4.5')
                '-o' = @('claude-opus-4-1', 'Claude Opus 4.1')
                '-p' = @('claude-opus-4-1', 'Claude Opus 4.1')
                '-q' = @('claude-sonnet-4-5', 'Claude Sonnet 4.5')
                '-k' = @('claude-haiku-4-5', 'Claude Haiku 4.5')
                '-g' = @('claude-sonnet-4-5', 'Claude Sonnet 4.5')
                '-f' = @('claude-haiku-4-5', 'Claude Haiku 4.5')
                '-h' = @('claude-sonnet-4-5', 'Claude Sonnet 4.5')
            }
            $modelEnvPrefix = 'CLAUDE_MODEL_'
            $defaultReasoning = ''
        }
        'opencode' {
            $modelTable = @{
                '-m' = @('opencode-go/muse-spark-1.2-contributor', 'Build auto·Muse Spark 1.2 Contributor OpenCode Go')
                '-o' = @('opencode-go/ox-alpha-free', 'Build auto · Ox Alpha Free (Unlimited) OpenCode Go')
                '-p' = @('opencode-go/deepseek-v4-pro', 'DeepSeek V4 Pro (New)')
                '-q' = @('opencode-go/qwen3.8-max', 'Qwen3.8 Max')
                '-k' = @('opencode-go/kimi-k3', 'Kimi K3')
                '-g' = @('opencode-go/gpt-5.6-luna', 'GPT-5.6 Luna (2x usage)')
                '-f' = @('opencode-go/deepseek-v4-flash', 'DeepSeek V4 Flash (2x usage)')
                '-h' = @('opencode-go/hy3', 'Hy3')
            }
            $modelEnvPrefix = 'OPENCODE_MODEL_'
            $defaultReasoning = ''
        }
        default {
            $modelTable = @{
                '-m' = @('gpt-5.6-luna', 'GPT-5.6-Luna')
                '-o' = @('gpt-5.6-sol', 'GPT-5.6-Sol')
                '-p' = @('gpt-5.6-terra', 'GPT-5.6-Terra')
                '-q' = @('gpt-6-astra', 'GPT-6 Astra')
                '-k' = @('gpt-5.4-mini', 'GPT-5.4-Mini')
                '-g' = @('gpt-5.6-luna', 'GPT-5.6-Luna')
                '-f' = @('gpt-5.6-sol', 'GPT-5.6-Sol')
                '-h' = @('gpt-5.6-luna', 'GPT-5.6-Luna')
            }
            $modelEnvPrefix = 'CODEX_MODEL_'
            $defaultReasoning = switch ($defaultFlag) {
                '-m' { 'max' }
                '-o' { 'max' }
                '-p' { 'high' }
                '-q' { 'max' }
                '-k' { 'high' }
                '-g' { 'high' }
                '-f' { 'low' }
                default { 'high' }
            }
        }
    }
    if (-not $modelTable.ContainsKey($defaultFlag)) {
        Fail-Parse "###$($script:LauncherName): ERROR: 不支持的默认模型旗标 '$defaultFlag'###"
        return $false
    }
    $modelEnvName = $modelEnvPrefix + $defaultFlag.Substring(1).ToUpperInvariant()
    $flagModel = [Environment]::GetEnvironmentVariable($modelEnvName)
    if ([string]::IsNullOrWhiteSpace($flagModel)) {
        $flagModel = $modelTable[$defaultFlag][0]
    } else {
        $script:ModelExplicit = $true
    }
    $script:Model = if ([string]::IsNullOrWhiteSpace($modelOverride)) { $flagModel } else { $modelOverride }
    $script:Reasoning = if ($script:Agent -eq 'codex') {
        if ([string]::IsNullOrWhiteSpace($reasoningOverride)) { $defaultReasoning } else { $reasoningOverride }
    } else { '' }
    $script:Variant = if ($script:Agent -eq 'opencode') {
        if ([string]::IsNullOrWhiteSpace($variantOverride)) {
            switch ($defaultFlag) {
                '-m' { 'xhigh' }
                '-h' { 'high' }
                default { 'max' }
            }
        } else { $variantOverride }
    } else { '' }
    if (-not [string]::IsNullOrWhiteSpace($reasoningOverride)) {
        $script:ReasoningExplicit = $true
    }
    if (-not [string]::IsNullOrWhiteSpace($variantOverride)) {
        $script:VariantExplicit = $true
    }
    if ($script:Agent -eq 'codex') {
        if (-not [string]::IsNullOrWhiteSpace($sandbox)) { $env:CODEX_SANDBOX = $sandbox }
        if (-not [string]::IsNullOrWhiteSpace($approval)) { $env:CODEX_APPROVAL = $approval }
    }
    return $true
}

try {
    if ([string]::IsNullOrWhiteSpace($script:LauncherName) -or
        [string]::IsNullOrWhiteSpace($script:ScriptDir) -or
        [string]::IsNullOrWhiteSpace($script:WorkDir) -or
        [string]::IsNullOrWhiteSpace($script:Agent)) {
        Write-ErrorLine 'agent-runtime.ps1：缺少 agent.bat 注入的启动上下文'
        $script:ExitCode = 64
    } else {
        $script:ScriptDir = [System.IO.Path]::GetFullPath($script:ScriptDir)
        $script:WorkDir = [System.IO.Path]::GetFullPath($script:WorkDir)
        $script:DataRoot = Resolve-AgentDataRoot
        New-Item -ItemType Directory -Force -Path (Join-Path $script:DataRoot 'runs') | Out-Null
        New-Item -ItemType Directory -Force -Path (Join-Path $script:DataRoot 'hooks') | Out-Null
        $workspaceCandidate = (& git -C $script:WorkDir rev-parse --show-toplevel 2>$null | Select-Object -First 1)
        if ($LASTEXITCODE -eq 0 -and $workspaceCandidate) {
            $script:WorkspaceRoot = [System.IO.Path]::GetFullPath(([string]$workspaceCandidate).Trim())
        } else {
            $script:WorkspaceRoot = $script:WorkDir
        }
        Discover-Context
        if (-not (Parse-Arguments)) {
            $script:ExitCode = if ($script:FailureCode -ne 0) { $script:FailureCode } else { 0 }
        } elseif (-not (Start-Or-ResumeRun)) {
            $script:ExitCode = if ($script:FailureCode -ne 0) { $script:FailureCode } else { 1 }
        } else {
            switch ($script:Agent) {
                'claude' { $script:ExitCode = Run-Claude }
                'opencode' { $script:ExitCode = Run-OpenCode }
                'codex' { $script:ExitCode = Run-Codex }
                default { $script:ExitCode = 64 }
            }
        }
    }
} catch {
    $message = ($_ | Out-String).Trim()
    Write-ErrorLine "###$($script:LauncherName): ERROR: $message###"
    $script:ExitCode = if ($script:FailureCode -ne 0) { $script:FailureCode } else { 1 }
    if ($script:RunReady -and $script:State -in @('prepared', 'running')) {
        Mark-State 'failed' "异常：$message" $script:ExitCode
    }
} finally {
    if ($script:RunReady -and $script:State -in @('prepared', 'running')) {
        if ($script:ExitCode -eq 0) {
            Mark-State 'finished' '进程正常结束' ''
        } else {
            Mark-State 'failed' "进程退出码 $($script:ExitCode)" $script:ExitCode
        }
    }
    Release-RunLock
}

exit $script:ExitCode
