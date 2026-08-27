@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Agent Launcher

rem ============================================================
rem  agent.bat - Windows unified agent launcher
rem  Distribution by filename (%%~nx0, cpupower.sh-style): 
rem    cl.bat -> Claude Code | op.bat -> OpenCode | co.bat -> Codex
rem  Deploy: copy agent.bat as cl.bat / op.bat / co.bat
rem          (or: mklink /H cl.bat agent.bat  on the same volume)
rem  Reference: agent.sh (Unix). Prompt read from agent-prompt.txt.
rem  Usage: {cl|op|co}.bat [-m|-o|-p|-q|-k|-g|-f|-h] [--model MODEL] [-file PATH] [-time DUR]
rem    --model MODEL    : override model id directly (env *AGENT*_MODEL also works)
rem    --variant LEVEL  : opencode only - build agent variant (max/xhigh/high/low etc.)
rem    --reasoning-effort LEVEL : codex only (low/medium/high/xhigh/max/ultra)
rem    --sandbox POLICY / --ask-for-approval POLICY : codex only
rem    -file PATH : drive mode (cl/op) - after the prompt round completes, send file
rem                 content as first instruction, then send "continue" every -time
rem    -time DUR  : "continue" interval; plain number=seconds; s/m/h suffix ok (default 30s)
rem ============================================================

set "_NAME=%~nx0"
set "_PATH=%~dp0"
set "_PWD=%CD%"

rem ---- distribution by filename ----
set "AGENT="
if /i "%_NAME%"=="cl.bat" set "AGENT=claude"
if /i "%_NAME%"=="op.bat" set "AGENT=opencode"
if /i "%_NAME%"=="co.bat" set "AGENT=codex"
if not defined AGENT (
    echo ERROR: %_NAME% is not a recognized launcher name.
    echo Usage: copy agent.bat as cl.bat / op.bat / co.bat  ^(or: mklink /H ^<name^>.bat agent.bat^)
    exit /b 1
)

rem ---- arg parsing: model flags + drive options ----
set "MODEL_FLAG="
set "MODEL_OVERRIDE="
set "VARIANT_OVERRIDE="
set "REASONING_OVERRIDE="
set "DRIVE_FILE="
set "DRIVE_TIME="
set "DRIVE_MODE=0"
set "SANDBOX_MODE=danger-full-access"
set "APPROVAL_POLICY=never"
:parse_args
if "%~1"=="" goto args_done
set "_a=%~1"
if "%_a%"=="-m" (set "MODEL_FLAG=-m") else if "%_a%"=="-o" (set "MODEL_FLAG=-o") else if "%_a%"=="-p" (set "MODEL_FLAG=-p") else if "%_a%"=="-q" (set "MODEL_FLAG=-q") else if "%_a%"=="-k" (set "MODEL_FLAG=-k") else if "%_a%"=="-g" (set "MODEL_FLAG=-g") else if "%_a%"=="-f" (set "MODEL_FLAG=-f") else if "%_a%"=="-h" (set "MODEL_FLAG=-h") else if /i "%_a%"=="--model" (
    if "%~2"=="" (echo ERROR: %_a% missing model argument & exit /b 64)
    set "MODEL_OVERRIDE=%~2"
    shift
    shift
    goto parse_args
) else if /i "%_a%"=="--variant" (
    if not "%AGENT%"=="opencode" (echo ERROR: --variant is only supported by op.bat & exit /b 64)
    if "%~2"=="" (echo ERROR: %_a% missing level argument & exit /b 64)
    set "VARIANT_OVERRIDE=%~2"
    shift
    shift
    goto parse_args
) else if /i "%_a%"=="--reasoning-effort" (
    if not "%AGENT%"=="codex" (echo ERROR: --reasoning-effort is only supported by co.bat & exit /b 64)
    if "%~2"=="" (echo ERROR: %_a% missing level argument & exit /b 64)
    set "REASONING_OVERRIDE=%~2"
    shift
    shift
    goto parse_args
) else if /i "%_a%"=="--sandbox" (
    if not "%AGENT%"=="codex" (echo ERROR: --sandbox is only supported by co.bat & exit /b 64)
    if "%~2"=="" (echo ERROR: %_a% missing policy argument & exit /b 64)
    set "SANDBOX_MODE=%~2"
    shift
    shift
    goto parse_args
) else if /i "%_a%"=="--ask-for-approval" (
    if not "%AGENT%"=="codex" (echo ERROR: --ask-for-approval is only supported by co.bat & exit /b 64)
    if "%~2"=="" (echo ERROR: %_a% missing policy argument & exit /b 64)
    set "APPROVAL_POLICY=%~2"
    shift
    shift
    goto parse_args
) else if /i "%_a%"=="--help" (
    echo Usage: %_NAME% [-m^-o^-p^-q^-k^-g^-f^-h] [--model MODEL] [-file PATH] [-time 30s]
    if "%AGENT%"=="opencode" echo   opencode extra: [--variant LEVEL]
    if "%AGENT%"=="codex" echo   codex extra: [--reasoning-effort LEVEL] [--sandbox POLICY] [--ask-for-approval POLICY]
    exit /b 0
) else if /i "%_a%"=="-file" (
    if "%AGENT%"=="codex" (echo ERROR: -file is not supported by co.bat & exit /b 64)
    if "%~2"=="" (echo ERROR: %_a% missing path argument & exit /b 64)
    set "DRIVE_FILE=%~2"
    set "DRIVE_MODE=1"
    shift
    shift
    goto parse_args
) else if /i "%_a%"=="--file" (
    if "%AGENT%"=="codex" (echo ERROR: --file is not supported by co.bat & exit /b 64)
    if "%~2"=="" (echo ERROR: %_a% missing path argument & exit /b 64)
    set "DRIVE_FILE=%~2"
    set "DRIVE_MODE=1"
    shift
    shift
    goto parse_args
) else if /i "%_a%"=="-time" (
    if "%~2"=="" (echo ERROR: %_a% missing duration argument & exit /b 64)
    set "DRIVE_TIME=%~2"
    set "DRIVE_MODE=1"
    shift
    shift
    goto parse_args
) else if /i "%_a%"=="--time" (
    if "%~2"=="" (echo ERROR: %_a% missing duration argument & exit /b 64)
    set "DRIVE_TIME=%~2"
    set "DRIVE_MODE=1"
    shift
    shift
    goto parse_args
) else (
    echo ERROR: unknown argument %_a%
    echo Usage: %_NAME% [-m^-o^-p^-q^-k^-g^-f^-h] [--model MODEL] [-file PATH] [-time 30s]
    exit /b 64
)
shift
goto parse_args
:args_done

rem ---- default model flag per agent ----
if not defined MODEL_FLAG (
    if "%AGENT%"=="opencode" set "MODEL_FLAG=-f"
    if "%AGENT%"=="codex" set "MODEL_FLAG=-m"
    if "%AGENT%"=="claude" set "MODEL_FLAG=-m"
)

rem ---- model table per agent ----
set "MODEL_ID="
set "MODEL_NAME="
set "VARIANT=max"
set "REASONING_EFFORT=max"
if "%AGENT%"=="opencode" goto model_opencode
if "%AGENT%"=="codex" goto model_codex
goto model_claude

:model_opencode
set "MODEL_ID=opencode-go/deepseek-v4-flash"
set "MODEL_NAME=DeepSeek V4 Flash (2x usage)"
if "%MODEL_FLAG%"=="-m" (set "MODEL_ID=opencode-go/muse-spark-1.2-contributor" & set "MODEL_NAME=Build auto·Muse Spark 1.2 Contributor OpenCode Go" & set "VARIANT=xhigh")
if "%MODEL_FLAG%"=="-o" (set "MODEL_ID=opencode-go/ox-alpha-free" & set "MODEL_NAME=Build auto · Ox Alpha Free (Unlimited) OpenCode Go")
if "%MODEL_FLAG%"=="-p" (set "MODEL_ID=opencode-go/deepseek-v4-pro" & set "MODEL_NAME=DeepSeek V4 Pro (New)")
if "%MODEL_FLAG%"=="-q" (set "MODEL_ID=opencode-go/qwen3.8-max" & set "MODEL_NAME=Qwen3.8 Max")
if "%MODEL_FLAG%"=="-k" (set "MODEL_ID=opencode-go/kimi-k3" & set "MODEL_NAME=Kimi K3")
if "%MODEL_FLAG%"=="-g" (set "MODEL_ID=opencode-go/gpt-5.6-luna" & set "MODEL_NAME=GPT-5.6 Luna (2x usage)")
if "%MODEL_FLAG%"=="-h" (set "MODEL_ID=opencode-go/hy3" & set "MODEL_NAME=Hy3" & set "VARIANT=high")
if defined OPENCODE_MODEL_M if "%MODEL_FLAG%"=="-m" set "MODEL_ID=%OPENCODE_MODEL_M%"
if defined OPENCODE_MODEL_O if "%MODEL_FLAG%"=="-o" set "MODEL_ID=%OPENCODE_MODEL_O%"
if defined OPENCODE_MODEL_P if "%MODEL_FLAG%"=="-p" set "MODEL_ID=%OPENCODE_MODEL_P%"
if defined OPENCODE_MODEL_Q if "%MODEL_FLAG%"=="-q" set "MODEL_ID=%OPENCODE_MODEL_Q%"
if defined OPENCODE_MODEL_K if "%MODEL_FLAG%"=="-k" set "MODEL_ID=%OPENCODE_MODEL_K%"
if defined OPENCODE_MODEL_G if "%MODEL_FLAG%"=="-g" set "MODEL_ID=%OPENCODE_MODEL_G%"
if defined OPENCODE_MODEL_F if "%MODEL_FLAG%"=="-f" set "MODEL_ID=%OPENCODE_MODEL_F%"
if defined OPENCODE_MODEL_H if "%MODEL_FLAG%"=="-h" set "MODEL_ID=%OPENCODE_MODEL_H%"
if defined OPENCODE_MODEL set "MODEL_ID=%OPENCODE_MODEL%"
goto model_done

:model_codex
set "MODEL_ID=gpt-5.6-luna"
set "MODEL_NAME=GPT-5.6-Luna"
set "REASONING_EFFORT=max"
if "%MODEL_FLAG%"=="-o" (set "MODEL_ID=gpt-5.6-sol" & set "MODEL_NAME=GPT-5.6-Sol" & set "REASONING_EFFORT=max")
if "%MODEL_FLAG%"=="-p" (set "MODEL_ID=gpt-5.6-terra" & set "MODEL_NAME=GPT-5.6-Terra" & set "REASONING_EFFORT=high")
if "%MODEL_FLAG%"=="-q" (set "MODEL_ID=gpt-5.5" & set "MODEL_NAME=GPT-5.5" & set "REASONING_EFFORT=high")
if "%MODEL_FLAG%"=="-k" (set "MODEL_ID=gpt-5.4-mini" & set "MODEL_NAME=GPT-5.4-Mini" & set "REASONING_EFFORT=high")
if "%MODEL_FLAG%"=="-g" (set "MODEL_ID=gpt-5.6-luna" & set "MODEL_NAME=GPT-5.6-Luna" & set "REASONING_EFFORT=high")
if "%MODEL_FLAG%"=="-f" (set "MODEL_ID=gpt-5.6-sol" & set "MODEL_NAME=GPT-5.6-Sol" & set "REASONING_EFFORT=low")
if "%MODEL_FLAG%"=="-h" (set "MODEL_ID=gpt-5.6-luna" & set "MODEL_NAME=GPT-5.6-Luna" & set "REASONING_EFFORT=high")
if defined CODEX_MODEL_M if "%MODEL_FLAG%"=="-m" set "MODEL_ID=%CODEX_MODEL_M%"
if defined CODEX_MODEL_O if "%MODEL_FLAG%"=="-o" set "MODEL_ID=%CODEX_MODEL_O%"
if defined CODEX_MODEL_P if "%MODEL_FLAG%"=="-p" set "MODEL_ID=%CODEX_MODEL_P%"
if defined CODEX_MODEL_Q if "%MODEL_FLAG%"=="-q" set "MODEL_ID=%CODEX_MODEL_Q%"
if defined CODEX_MODEL_K if "%MODEL_FLAG%"=="-k" set "MODEL_ID=%CODEX_MODEL_K%"
if defined CODEX_MODEL_G if "%MODEL_FLAG%"=="-g" set "MODEL_ID=%CODEX_MODEL_G%"
if defined CODEX_MODEL_F if "%MODEL_FLAG%"=="-f" set "MODEL_ID=%CODEX_MODEL_F%"
if defined CODEX_MODEL_H if "%MODEL_FLAG%"=="-h" set "MODEL_ID=%CODEX_MODEL_H%"
if defined CODEX_MODEL set "MODEL_ID=%CODEX_MODEL%"
if defined CODEX_REASONING_EFFORT set "REASONING_OVERRIDE=%CODEX_REASONING_EFFORT%"
if defined CODEX_SANDBOX set "SANDBOX_MODE=%CODEX_SANDBOX%"
if defined CODEX_APPROVAL set "APPROVAL_POLICY=%CODEX_APPROVAL%"
goto model_done

:model_claude
set "MODEL_ID=claude-sonnet-4-5"
set "MODEL_NAME=Claude Sonnet 4.5"
if "%MODEL_FLAG%"=="-o" (set "MODEL_ID=claude-opus-4-1" & set "MODEL_NAME=Claude Opus 4.1")
if "%MODEL_FLAG%"=="-p" (set "MODEL_ID=claude-opus-4-1" & set "MODEL_NAME=Claude Opus 4.1")
if "%MODEL_FLAG%"=="-q" (set "MODEL_ID=claude-sonnet-4-5" & set "MODEL_NAME=Claude Sonnet 4.5")
if "%MODEL_FLAG%"=="-k" (set "MODEL_ID=claude-haiku-4-5" & set "MODEL_NAME=Claude Haiku 4.5")
if "%MODEL_FLAG%"=="-g" (set "MODEL_ID=claude-sonnet-4-5" & set "MODEL_NAME=Claude Sonnet 4.5")
if "%MODEL_FLAG%"=="-f" (set "MODEL_ID=claude-haiku-4-5" & set "MODEL_NAME=Claude Haiku 4.5")
if "%MODEL_FLAG%"=="-h" (set "MODEL_ID=claude-sonnet-4-5" & set "MODEL_NAME=Claude Sonnet 4.5")
if defined CLAUDE_MODEL_M if "%MODEL_FLAG%"=="-m" set "MODEL_ID=%CLAUDE_MODEL_M%"
if defined CLAUDE_MODEL_O if "%MODEL_FLAG%"=="-o" set "MODEL_ID=%CLAUDE_MODEL_O%"
if defined CLAUDE_MODEL_P if "%MODEL_FLAG%"=="-p" set "MODEL_ID=%CLAUDE_MODEL_P%"
if defined CLAUDE_MODEL_Q if "%MODEL_FLAG%"=="-q" set "MODEL_ID=%CLAUDE_MODEL_Q%"
if defined CLAUDE_MODEL_K if "%MODEL_FLAG%"=="-k" set "MODEL_ID=%CLAUDE_MODEL_K%"
if defined CLAUDE_MODEL_G if "%MODEL_FLAG%"=="-g" set "MODEL_ID=%CLAUDE_MODEL_G%"
if defined CLAUDE_MODEL_F if "%MODEL_FLAG%"=="-f" set "MODEL_ID=%CLAUDE_MODEL_F%"
if defined CLAUDE_MODEL_H if "%MODEL_FLAG%"=="-h" set "MODEL_ID=%CLAUDE_MODEL_H%"
if defined CLAUDE_MODEL set "MODEL_ID=%CLAUDE_MODEL%"
goto model_done

:model_done
if defined MODEL_OVERRIDE set "MODEL_ID=%MODEL_OVERRIDE%"
if defined MODEL_OVERRIDE set "MODEL_NAME=%MODEL_OVERRIDE% (override)"
if defined VARIANT_OVERRIDE set "VARIANT=%VARIANT_OVERRIDE%"
if defined REASONING_OVERRIDE set "REASONING_EFFORT=%REASONING_OVERRIDE%"

rem ---- timestamp & log file ----
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd-HH-mm-ss"') do set "_TS=%%i"
set "LOG_FILE=.agent.%_TS%.log"
set "LIST_FILE=.agent.%_TS%.list"

rem ---- prompt template must exist ----
if not exist "%_PATH%agent-prompt.txt" (
    echo ERROR: %_PATH%agent-prompt.txt not found
    exit /b 127
)

echo ============================================================
if "%AGENT%"=="opencode" echo   OpenCode: build ^| auto ^| %MODEL_NAME% (%VARIANT%)
if "%AGENT%"=="codex" echo   Codex: %MODEL_NAME% ^| reasoning=%REASONING_EFFORT%
if "%AGENT%"=="claude" echo   Claude Code: %MODEL_NAME% ^| permission-mode auto
echo   log: %LOG_FILE%
if "%AGENT%"=="opencode" echo   user-input list: %LIST_FILE%
if "%AGENT%"=="codex" echo   sandbox: %SANDBOX_MODE% ^| approval: %APPROVAL_POLICY%
if "%DRIVE_MODE%"=="1" (
    echo   drive mode: ON ^| interval=%DRIVE_TIME% ^| first-instruction: %DRIVE_FILE%
) else (
    echo   mode: TUI interactive
)
echo ============================================================

rem ---- run per agent ----
if "%AGENT%"=="opencode" goto run_opencode
if "%AGENT%"=="codex" goto run_codex
goto run_claude

rem ============================================================
rem  OpenCode: TUI or headless opencode run chain (session.id)
rem ============================================================
:run_opencode
set "OPENCODE_CONFIG_CONTENT={"lsp":true,"agent":{"build":{"model":"%MODEL_ID%","variant":"%VARIANT%"}}}
if "%DRIVE_MODE%"=="0" goto op_tui
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$opencode=if($env:OPENCODE_BIN){$env:OPENCODE_BIN}else{'opencode'};" ^
  "$msg=[string][char]0x7EE7+[char]0x7EED;" ^
  "$iv='%DRIVE_TIME%';" ^
  "if ($iv -eq '') { $sec=30 } else {" ^
  "  $mm=[regex]::Match($iv,'^(\d+)([smh]?)$');" ^
  "  if (-not $mm.Success) { Write-Host ('ERROR: bad --time value: ' + $iv); exit 64 }" ^
  "  $n=[int]$mm.Groups[1].Value;" ^
  "  switch ($mm.Groups[2].Value) { 's' {$sec=$n} 'm' {$sec=$n*60} 'h' {$sec=$n*3600} default {$sec=$n} }" ^
  "}" ^
  "$p=[IO.File]::ReadAllText('%_PATH%agent-prompt.txt');" ^
  "$p=$p.Replace('${HOME}',$env:USERPROFILE).Replace('${_PWD}','%_PWD%').Replace('${LIST_FILE}','%LIST_FILE%');" ^
  "Write-Host ('---- drive: prompt round start ' + (Get-Date -Format 'yyyy-MM-dd-HH:mm:ss'));" ^
  "& $opencode run --agent build --auto --print-logs --log-level DEBUG $p 2>>'%LOG_FILE%';" ^
  "if ($LASTEXITCODE -ne 0) { Write-Host ('ERROR: prompt round failed, rc=' + $LASTEXITCODE); exit $LASTEXITCODE }" ^
  "$m=Select-String -Path '%LOG_FILE%' -Pattern 'session.id=([A-Za-z0-9_-]+)' | Select-Object -First 1;" ^
  "if (-not $m) { Write-Host 'ERROR: cannot extract session.id'; exit 1 }" ^
  "$sid=$m.Matches[0].Groups[1].Value;" ^
  "Write-Host ('---- drive: session=' + $sid + ' interval=' + $sec + 's ----');" ^
  "if ('%DRIVE_FILE%' -ne '') {" ^
  "  if (-not (Test-Path '%DRIVE_FILE%')) { Write-Host ('ERROR: --file not readable: %DRIVE_FILE%'); exit 66 }" ^
  "  Write-Host ('---- drive: first instruction <- %DRIVE_FILE% ----');" ^
  "  & $opencode run -s $sid --agent build --auto --print-logs --log-level DEBUG ([IO.File]::ReadAllText('%DRIVE_FILE%')) 2>>'%LOG_FILE%';" ^
  "  if ($LASTEXITCODE -ne 0) { Write-Host ('WARN: first-instruction round rc=' + $LASTEXITCODE + ', entering continue loop anyway') }" ^
  "} else { Write-Host '---- drive: no -file, enter continue loop directly ----' }" ^
  "$nudges=0; $fails=0;" ^
  "while ($true) {" ^
  "  Start-Sleep -Seconds $sec;" ^
  "  & $opencode run -s $sid --agent build --auto --print-logs --log-level DEBUG $msg 2>>'%LOG_FILE%';" ^
  "  if ($LASTEXITCODE -eq 0) { $nudges++; $fails=0; Write-Host ('---- drive: continue #' + $nudges + ' ok ' + (Get-Date -Format 'yyyy-MM-dd-HH:mm:ss')) }" ^
  "  else { $fails++; Write-Host ('WARN: continue send failed ' + $fails + '/3'); if ($fails -ge 3) { Write-Host ('ERROR: 3 consecutive failures, stop (total ok=' + $nudges + ')'); break } }" ^
  "}"
goto run_done

:op_tui
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$opencode=if($env:OPENCODE_BIN){$env:OPENCODE_BIN}else{'opencode'};" ^
  "$p=[IO.File]::ReadAllText('%_PATH%agent-prompt.txt');" ^
  "$p=$p.Replace('${HOME}',$env:USERPROFILE).Replace('${_PWD}','%_PWD%').Replace('${LIST_FILE}','%LIST_FILE%');" ^
  "& $opencode --agent build --auto --prompt $p --print-logs --log-level DEBUG" 2> "%LOG_FILE%"
goto run_done

rem ============================================================
rem  Codex: TUI or headless codex exec -> exec resume chain
rem ============================================================
:run_codex
set "CODEX_PROMPT_FILE=%_PATH%agent-prompt.txt"
set "CODEX_RUN_CWD=%_PWD%"
set "CODEX_LOG_FILE=%LOG_FILE%"
set "CODEX_MODEL_ID=%MODEL_ID%"
set "CODEX_REASONING=%REASONING_EFFORT%"
set "CODEX_SANDBOX_MODE=%SANDBOX_MODE%"
set "CODEX_APPROVAL_POLICY=%APPROVAL_POLICY%"
set "CODEX_DRIVE_MODE=%DRIVE_MODE%"
set "CODEX_DRIVE_TIME=%DRIVE_TIME%"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Continue';" ^
  "$codex=if($env:CODEX_BIN){$env:CODEX_BIN}else{'codex'};" ^
  "$prompt=[IO.File]::ReadAllText($env:CODEX_PROMPT_FILE);" ^
  "$homeRoot=if($env:HOME){$env:HOME}else{$env:USERPROFILE}; $prompt=$prompt.Replace('${HOME}',$homeRoot).Replace('${_PWD}',$env:CODEX_RUN_CWD);" ^
  "$eol=[Environment]::NewLine; $seen=@{};" ^
  "$agentConfigDirs=@((Join-Path $homeRoot 'configure\skills'),(Join-Path $homeRoot 'configure\tools'),(Join-Path $homeRoot 'configure\hooks'),(Join-Path $homeRoot 'configure\plugins'));" ^
  "$prompt += $eol+$eol+'### 全局 Agent 配置目录（按需读取） ###'+$eol+($agentConfigDirs -join $eol)+$eol;" ^
  "function Get-SkillSection([string]$title,[string[]]$roots){ $paths=@(); foreach($root in $roots){ if(Test-Path -LiteralPath $root -PathType Container){ Get-ChildItem -LiteralPath $root -Filter SKILL.md -File -Recurse -ErrorAction SilentlyContinue | Sort-Object -Property FullName | ForEach-Object { $key=$_.FullName.ToLowerInvariant(); if(!$seen.ContainsKey($key)){ $seen[$key]=$true; $paths+=$_.FullName } } } }; $text=$eol+$eol+'### '+$title+' ###'+$eol; if($paths.Count){$text+=($paths -join $eol)+$eol}else{$text+='（未找到 SKILL.md）'+$eol}; return $text };" ^
  "$workspaceRoot=$env:CODEX_RUN_CWD; try{$gitRoot=((& git -C $workspaceRoot rev-parse --show-toplevel 2>$null | Select-Object -First 1) -as [string]).Trim();if($gitRoot){$workspaceRoot=$gitRoot}}catch{};" ^
  "$globalSkills=Join-Path $homeRoot 'configure\skills'; $workspaceSkills=@((Join-Path $env:CODEX_RUN_CWD 'skills'),(Join-Path $env:CODEX_RUN_CWD '.codex\skills')); if($workspaceRoot -ne $env:CODEX_RUN_CWD){$workspaceSkills += @((Join-Path $workspaceRoot 'skills'),(Join-Path $workspaceRoot '.codex\skills'))};" ^
  "$prompt += Get-SkillSection ('全局技能（'+$globalSkills+'）') @($globalSkills); $prompt += Get-SkillSection ('当前工作目录技能（'+$env:CODEX_RUN_CWD+'）') $workspaceSkills;" ^
  "$common=@('--model',$env:CODEX_MODEL_ID,'--config',('model_reasoning_effort='+[char]34+$env:CODEX_REASONING+[char]34),'--config',('approval_policy='+[char]34+$env:CODEX_APPROVAL_POLICY+[char]34),'--config',('sandbox_mode='+[char]34+$env:CODEX_SANDBOX_MODE+[char]34)); $initialCommon=@($common); foreach($dir in $agentConfigDirs){if(Test-Path -LiteralPath $dir -PathType Container){$initialCommon+=@('--add-dir',$dir)}};" ^
  "if($env:CODEX_DRIVE_MODE -eq '0'){ $a=@()+'--' + $prompt; & $codex @initialCommon @a 2>>$env:CODEX_LOG_FILE; exit $LASTEXITCODE };" ^
  "$raw=$env:CODEX_DRIVE_TIME; if(!$raw){$sec=30} elseif($raw -match '^(\d+)([smh]?)$'){ $n=[int64]$Matches[1]; if($n -le 0){Write-Host 'ERROR: bad --time value'; exit 64}; switch($Matches[2]){'s'{$sec=$n};'m'{$sec=$n*60};'h'{$sec=$n*3600};default{$sec=$n}} } else {Write-Host ('ERROR: bad --time value: '+$raw); exit 64};" ^
  "$common += @('--json'); $initialCommon += @('--json'); function Invoke-Codex([bool]$resume,[string]$message){ $a=@('exec'); if($resume){$a+=@('resume');$a+=$common}else{$a+=$initialCommon}; if($resume){$a+=@($thread,'--',$message)}else{$a+=@('--',$message)}; & $codex @a 2>>$env:CODEX_LOG_FILE | Tee-Object -FilePath $env:CODEX_LOG_FILE -Append; return $LASTEXITCODE };" ^
  "$rc=Invoke-Codex $false $prompt; if($rc -ne 0){Write-Host ('ERROR: prompt round failed, rc='+$rc); exit $rc};" ^
  "$thread=$null; foreach($line in [IO.File]::ReadLines($env:CODEX_LOG_FILE)){try{$e=$line|ConvertFrom-Json}catch{continue}; if($e.type -eq 'thread.started' -and $e.thread_id){$thread=$e.thread_id;break}}; if(!$thread){Write-Host 'ERROR: cannot extract thread_id'; exit 1}; Write-Host ('---- drive: thread='+$thread+' interval='+$sec+'s ----');" ^
  "$nudges=0; $fails=0; while($true){Start-Sleep -Seconds $sec; $rc=Invoke-Codex $true '继续'; if($rc -eq 0){$nudges++;$fails=0;Write-Host ('---- drive: continue #'+$nudges+' ok '+(Get-Date -Format 'yyyy-MM-dd-HH:mm:ss'))}else{$fails++;Write-Host ('WARN: continue send failed '+$fails+'/3');if($fails -ge 3){Write-Host ('ERROR: 3 consecutive failures, stop (total ok='+$nudges+')');break}}}"
goto run_done

rem ============================================================
rem  Claude Code: TUI or headless claude -p -> --resume chain
rem ============================================================
:run_claude
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$claude=if($env:CLAUDE_BIN){$env:CLAUDE_BIN}else{'claude'};" ^
  "$msg=[string][char]0x7EE7+[char]0x7EED;" ^
  "$iv='%DRIVE_TIME%';" ^
  "if ($iv -eq '') { $sec=30 } else {" ^
  "  $mm=[regex]::Match($iv,'^(\d+)([smh]?)$');" ^
  "  if (-not $mm.Success) { Write-Host ('ERROR: bad --time value: ' + $iv); exit 64 }" ^
  "  $n=[int]$mm.Groups[1].Value;" ^
  "  switch ($mm.Groups[2].Value) { 's' {$sec=$n} 'm' {$sec=$n*60} 'h' {$sec=$n*3600} default {$sec=$n} }" ^
  "}" ^
  "$p=[IO.File]::ReadAllText('%_PATH%agent-prompt.txt');" ^
  "$homeRoot=if($env:HOME){$env:HOME}else{$env:USERPROFILE}; $p=$p.Replace('${HOME}',$homeRoot).Replace('${_PWD}','%_PWD%');" ^
  "$eol=[Environment]::NewLine; $seen=@{};" ^
  "$agentConfigDirs=@((Join-Path $homeRoot 'configure\skills'),(Join-Path $homeRoot 'configure\tools'),(Join-Path $homeRoot 'configure\hooks'),(Join-Path $homeRoot 'configure\plugins'));" ^
  "$p += $eol+$eol+'### 全局 Agent 配置目录（按需读取） ###'+$eol+($agentConfigDirs -join $eol)+$eol;" ^
  "function Get-SkillSection([string]$title,[string[]]$roots){ $paths=@(); foreach($root in $roots){ if(Test-Path -LiteralPath $root -PathType Container){ Get-ChildItem -LiteralPath $root -Filter SKILL.md -File -Recurse -ErrorAction SilentlyContinue | Sort-Object -Property FullName | ForEach-Object { $key=$_.FullName.ToLowerInvariant(); if(!$seen.ContainsKey($key)){ $seen[$key]=$true; $paths+=$_.FullName } } } }; $text=$eol+$eol+'### '+$title+' ###'+$eol; if($paths.Count){$text+=($paths -join $eol)+$eol}else{$text+='（未找到 SKILL.md）'+$eol}; return $text };" ^
  "$workspaceRoot='%_PWD%'; try{$gitRoot=((& git -C $workspaceRoot rev-parse --show-toplevel 2>$null | Select-Object -First 1) -as [string]).Trim();if($gitRoot){$workspaceRoot=$gitRoot}}catch{};" ^
  "$globalSkills=Join-Path $homeRoot 'configure\skills'; $workspaceSkills=@('%_PWD%\skills','%_PWD%\.codex\skills'); if($workspaceRoot -ne '%_PWD%'){$workspaceSkills += @((Join-Path $workspaceRoot 'skills'),(Join-Path $workspaceRoot '.codex\skills'))};" ^
  "$p += Get-SkillSection ('全局技能（'+$globalSkills+'）') @($globalSkills); $p += Get-SkillSection ('当前工作目录技能（%_PWD%）') $workspaceSkills;" ^
  "if ('%DRIVE_MODE%' -eq '0') { & $claude --permission-mode auto --model '%MODEL_ID%' 2>>'%LOG_FILE%'; exit $LASTEXITCODE };" ^
  "Write-Host ('---- drive: prompt round start ' + (Get-Date -Format 'yyyy-MM-dd-HH:mm:ss'));" ^
  "& $claude -p --permission-mode auto --model '%MODEL_ID%' $p 2>>'%LOG_FILE%';" ^
  "if ($LASTEXITCODE -ne 0) { Write-Host ('ERROR: prompt round failed, rc=' + $LASTEXITCODE); exit $LASTEXITCODE }" ^
  "$m=Select-String -Path '%LOG_FILE%' -Pattern 'session_id=([A-Za-z0-9_-]+)' | Select-Object -First 1;" ^
  "if (-not $m) { Write-Host 'ERROR: cannot extract session_id'; exit 1 }" ^
  "$sid=$m.Matches[0].Groups[1].Value;" ^
  "Write-Host ('---- drive: session=' + $sid + ' interval=' + $sec + 's ----');" ^
  "if ('%DRIVE_FILE%' -ne '') {" ^
  "  if (-not (Test-Path '%DRIVE_FILE%')) { Write-Host ('ERROR: --file not readable: %DRIVE_FILE%'); exit 66 }" ^
  "  Write-Host ('---- drive: first instruction <- %DRIVE_FILE% ----');" ^
  "  & $claude -p --resume $sid --permission-mode auto --model '%MODEL_ID%' ([IO.File]::ReadAllText('%DRIVE_FILE%')) 2>>'%LOG_FILE%';" ^
  "  if ($LASTEXITCODE -ne 0) { Write-Host ('WARN: first-instruction round rc=' + $LASTEXITCODE + ', entering continue loop anyway') }" ^
  "} else { Write-Host '---- drive: no -file, enter continue loop directly ----' }" ^
  "$nudges=0; $fails=0;" ^
  "while ($true) {" ^
  "  Start-Sleep -Seconds $sec;" ^
  "  & $claude -p --resume $sid --permission-mode auto --model '%MODEL_ID%' $msg 2>>'%LOG_FILE%';" ^
  "  if ($LASTEXITCODE -eq 0) { $nudges++; $fails=0; Write-Host ('---- drive: continue #' + $nudges + ' ok ' + (Get-Date -Format 'yyyy-MM-dd-HH:mm:ss')) }" ^
  "  else { $fails++; Write-Host ('WARN: continue send failed ' + $fails + '/3'); if ($fails -ge 3) { Write-Host ('ERROR: 3 consecutive failures, stop (total ok=' + $nudges + ')'); break } }" ^
  "}"
goto run_done

:run_done
echo.
echo   logs -^> %LOG_FILE%
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd-HH-mm-ss"') do set "_NOW=%%i"
echo ###%_NAME% in %_PATH% is done......:%_NOW%###
exit /b %errorlevel%