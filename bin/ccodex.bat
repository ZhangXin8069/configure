@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Codex Launcher

rem ============================================================
rem  ccodex.bat - Windows launcher for Codex
rem  Reference: ccodex.sh (Unix). Prompt read from ccodex-prompt.txt.
rem  Usage: ccodex.bat [-h|-o|-p|-f|-q|-k|-g|-m] [--model MODEL]
rem                    [-time DUR]  (default -m, GPT-5.6-Luna max)
rem ============================================================

set "_PATH=%~dp0"
set "_PWD=%CD%"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd-HH-mm-ss"') do set "_TS=%%i"
set "LOG_FILE=.agent.%_TS%.log"

rem ---- arg parsing: model flags + drive options ----
set "MODEL_FLAG=-m"
set "MODEL_OVERRIDE="
set "REASONING_OVERRIDE="
set "DRIVE_TIME="
set "DRIVE_MODE=0"
:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="-m" (set "MODEL_FLAG=-m" & shift & goto parse_args)
if /i "%~1"=="-o" (set "MODEL_FLAG=-o" & shift & goto parse_args)
if /i "%~1"=="-p" (set "MODEL_FLAG=-p" & shift & goto parse_args)
if /i "%~1"=="-q" (set "MODEL_FLAG=-q" & shift & goto parse_args)
if /i "%~1"=="-k" (set "MODEL_FLAG=-k" & shift & goto parse_args)
if /i "%~1"=="-g" (set "MODEL_FLAG=-g" & shift & goto parse_args)
if /i "%~1"=="-f" (set "MODEL_FLAG=-f" & shift & goto parse_args)
if /i "%~1"=="-h" (set "MODEL_FLAG=-h" & shift & goto parse_args)
if /i "%~1"=="--help" (
    echo Usage: %~nx0 [-m^-o^-p^-q^-k^-g^-f^-h] [--model MODEL] [--reasoning-effort LEVEL] [-time DUR]
    exit /b 0
)
if /i "%~1"=="--model" (
    if "%~2"=="" (echo ERROR: --model missing model argument ^& exit /b 64)
    set "MODEL_OVERRIDE=%~2"
    shift
    shift
    goto parse_args
)
if /i "%~1"=="--reasoning-effort" (
    if "%~2"=="" (echo ERROR: --reasoning-effort missing level argument ^& exit /b 64)
    set "REASONING_OVERRIDE=%~2"
    shift
    shift
    goto parse_args
)
if /i "%~1"=="-time" goto parse_time
if /i "%~1"=="--time" goto parse_time
echo ERROR: unknown argument %~1
exit /b 64

:parse_time
if "%~2"=="" (echo ERROR: %~1 missing duration argument ^& exit /b 64)
set "DRIVE_TIME=%~2"
set "DRIVE_MODE=1"
shift
shift
goto parse_args

:args_done
rem ---- model selection; CODEX_MODEL* variables can override these defaults ----
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
if defined MODEL_OVERRIDE set "MODEL_ID=%MODEL_OVERRIDE%"
if defined MODEL_OVERRIDE set "MODEL_NAME=%MODEL_OVERRIDE% (override)"
if defined CODEX_REASONING_EFFORT set "REASONING_OVERRIDE=%CODEX_REASONING_EFFORT%"
if defined REASONING_OVERRIDE set "REASONING_EFFORT=%REASONING_OVERRIDE%"
set "SANDBOX_MODE=danger-full-access"
set "APPROVAL_POLICY=never"
if defined CODEX_SANDBOX set "SANDBOX_MODE=%CODEX_SANDBOX%"
if defined CODEX_APPROVAL set "APPROVAL_POLICY=%CODEX_APPROVAL%"
if "%DRIVE_MODE%"=="1" if not defined DRIVE_TIME set "DRIVE_TIME=30s"

if not exist "%_PATH%ccodex-prompt.txt" (
    echo ERROR: %_PATH%ccodex-prompt.txt not found
    exit /b 127
)

echo ============================================================
echo   Codex: %MODEL_NAME% ^| reasoning=%REASONING_EFFORT%
echo   log: %LOG_FILE%
if "%DRIVE_MODE%"=="1" (
    echo   drive mode: ON ^| interval=%DRIVE_TIME% ^| prompt + continue
) else (
    echo   mode: TUI interactive
)
echo   sandbox: %SANDBOX_MODE% ^| approval: %APPROVAL_POLICY%
echo ============================================================

rem ---- pass data through the environment so PowerShell preserves spaces/newlines ----
set "CODEX_PROMPT_FILE=%_PATH%ccodex-prompt.txt"
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
  "function Get-SkillSection([string]$title,[string[]]$roots){ $paths=@(); foreach($root in $roots){ if(Test-Path -LiteralPath $root -PathType Container){ Get-ChildItem -LiteralPath $root -Filter SKILL.md -File -Recurse -ErrorAction SilentlyContinue | Sort-Object -Property FullName | ForEach-Object { $key=$_.FullName.ToLowerInvariant(); if(!$seen.ContainsKey($key)){ $seen[$key]=$true; $paths+=$_.FullName } } } }; $text=$eol+$eol+'### '+$title+' ###'+$eol; if($paths.Count){$text+=($paths -join $eol)+$eol}else{$text+='（未找到 SKILL.md）'+$eol}; return $text };" ^
  "$workspaceRoot=$env:CODEX_RUN_CWD; try{$gitRoot=((& git -C $workspaceRoot rev-parse --show-toplevel 2>$null | Select-Object -First 1) -as [string]).Trim();if($gitRoot){$workspaceRoot=$gitRoot}}catch{};" ^
  "$globalSkills=Join-Path $homeRoot 'configure\skills'; $workspaceSkills=@((Join-Path $env:CODEX_RUN_CWD 'skills'),(Join-Path $env:CODEX_RUN_CWD '.codex\skills')); if($workspaceRoot -ne $env:CODEX_RUN_CWD){$workspaceSkills += @((Join-Path $workspaceRoot 'skills'),(Join-Path $workspaceRoot '.codex\skills'))};" ^
  "$prompt += Get-SkillSection ('全局技能（'+$globalSkills+'）') @($globalSkills); $prompt += Get-SkillSection ('当前工作目录技能（'+$env:CODEX_RUN_CWD+'）') $workspaceSkills;" ^
  "$common=@('--model',$env:CODEX_MODEL_ID,'--config',('model_reasoning_effort='+[char]34+$env:CODEX_REASONING+[char]34),'--config',('approval_policy='+[char]34+$env:CODEX_APPROVAL_POLICY+[char]34),'--config',('sandbox_mode='+[char]34+$env:CODEX_SANDBOX_MODE+[char]34));" ^
  "if($env:CODEX_DRIVE_MODE -eq '0'){ $a=@()+'--' + $prompt; & $codex @common @a 2>>$env:CODEX_LOG_FILE; exit $LASTEXITCODE };" ^
  "$raw=$env:CODEX_DRIVE_TIME; if(!$raw){$sec=30} elseif($raw -match '^(\d+)([smh]?)$'){ $n=[int64]$Matches[1]; if($n -le 0){Write-Host 'ERROR: bad --time value'; exit 64}; switch($Matches[2]){'s'{$sec=$n};'m'{$sec=$n*60};'h'{$sec=$n*3600};default{$sec=$n}} } else {Write-Host ('ERROR: bad --time value: '+$raw); exit 64};" ^
  "$common += @('--json'); function Invoke-Codex([bool]$resume,[string]$message){ $a=@('exec'); if($resume){$a+=@('resume')}; $a+=$common; if($resume){$a+=@($thread,'--',$message)}else{$a+=@('--',$message)}; & $codex @a 2>>$env:CODEX_LOG_FILE | Tee-Object -FilePath $env:CODEX_LOG_FILE -Append; return $LASTEXITCODE };" ^
  "$rc=Invoke-Codex $false $prompt; if($rc -ne 0){Write-Host ('ERROR: prompt round failed, rc='+$rc); exit $rc};" ^
  "$thread=$null; foreach($line in [IO.File]::ReadLines($env:CODEX_LOG_FILE)){try{$e=$line|ConvertFrom-Json}catch{continue}; if($e.type -eq 'thread.started' -and $e.thread_id){$thread=$e.thread_id;break}}; if(!$thread){Write-Host 'ERROR: cannot extract thread_id'; exit 1}; Write-Host ('---- drive: thread='+$thread+' interval='+$sec+'s ----');" ^
  "$nudges=0; $fails=0; while($true){Start-Sleep -Seconds $sec; $rc=Invoke-Codex $true '继续'; if($rc -eq 0){$nudges++;$fails=0;Write-Host ('---- drive: continue #'+$nudges+' ok '+(Get-Date -Format 'yyyy-MM-dd-HH:mm:ss'))}else{$fails++;Write-Host ('WARN: continue send failed '+$fails+'/3');if($fails -ge 3){Write-Host ('ERROR: 3 consecutive failures, stop (total ok='+$nudges+')');break}}}"

:run_done
set "_RC=%ERRORLEVEL%"
echo.
echo   logs -^> %LOG_FILE%
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd-HH-mm-ss"') do set "_NOW=%%i"
echo ###%~nx0 in %_PATH% is done......:%_NOW%###
exit /b %_RC%
