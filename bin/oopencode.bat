@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title OpenCode Launcher

rem ============================================================
rem  oopencode.bat - Windows launcher for opencode (build agent)
rem  Reference: oopencode.sh (Unix). Prompt read from oopencode-prompt.txt.
rem  Usage: oopencode.bat [-h|-o|-p|-f|-q|-k|-g|-m] [-file PATH] [-time DUR]  (default -m)
rem    -file PATH : drive mode - after the prompt round completes, send file
rem                 content as first instruction, then send "continue" every -time
rem                 until Ctrl+C or 3 consecutive failures
rem    -time DUR  : "continue" interval; plain number=seconds; s/m/h suffix ok (default 30s)
rem ============================================================

set "_PATH=%~dp0"
set "_PWD=%CD%"

rem ---- arg parsing loop: model flags + drive options ----
set "MODEL_FLAG=-m"
set "DRIVE_FILE="
set "DRIVE_TIME="
:parse_args
if "%~1"=="" goto args_done
set "_a=%~1"
if "%_a%"=="-m" (set "MODEL_FLAG=-m") else if "%_a%"=="-o" (set "MODEL_FLAG=-o") else if "%_a%"=="-p" (set "MODEL_FLAG=-p") else if "%_a%"=="-q" (set "MODEL_FLAG=-q") else if "%_a%"=="-k" (set "MODEL_FLAG=-k") else if "%_a%"=="-g" (set "MODEL_FLAG=-g") else if "%_a%"=="-f" (set "MODEL_FLAG=-f") else if "%_a%"=="-h" (set "MODEL_FLAG=-h") else if /i "%_a%"=="-file" (
    if "%~2"=="" (echo ERROR: %_a% missing path argument & exit /b 64)
    set "DRIVE_FILE=%~2"
    shift
    shift
    goto parse_args
) else if /i "%_a%"=="--file" (
    if "%~2"=="" (echo ERROR: %_a% missing path argument & exit /b 64)
    set "DRIVE_FILE=%~2"
    shift
    shift
    goto parse_args
) else if /i "%_a%"=="-time" (
    if "%~2"=="" (echo ERROR: %_a% missing duration argument & exit /b 64)
    set "DRIVE_TIME=%~2"
    shift
    shift
    goto parse_args
) else if /i "%_a%"=="--time" (
    if "%~2"=="" (echo ERROR: %_a% missing duration argument & exit /b 64)
    set "DRIVE_TIME=%~2"
    shift
    shift
    goto parse_args
) else (
    echo ERROR: unknown argument %_a%
    echo Usage: %~nx0 [-h^-o^-p^-f^-q^-k^-g^-m] [-file PATH] [-time 30s]
    exit /b 64
)
shift
goto parse_args
:args_done

rem ---- model selection (default -m Build auto·Muse Spark 1.2 Contributor OpenCode Go xhigh) ----
set "MODEL_ID=opencode-go/muse-spark-1.2"
set "MODEL_NAME=Build auto·Muse Spark 1.2 Contributor OpenCode Go"
set "VARIANT=xhigh"
if "%MODEL_FLAG%"=="-o" (set "MODEL_ID=opencode-go/ox-alpha-free" & set "MODEL_NAME=Build auto · Ox Alpha Free (Unlimited) OpenCode Go" & set "VARIANT=max")
if "%MODEL_FLAG%"=="-p" (set "MODEL_ID=opencode-go/deepseek-v4-pro" & set "MODEL_NAME=DeepSeek V4 Pro (New)" & set "VARIANT=max")
if "%MODEL_FLAG%"=="-q" (set "MODEL_ID=opencode-go/qwen3.8-max" & set "MODEL_NAME=Qwen3.8 Max" & set "VARIANT=max")
if "%MODEL_FLAG%"=="-k" (set "MODEL_ID=opencode-go/kimi-k3" & set "MODEL_NAME=Kimi K3" & set "VARIANT=max")
if "%MODEL_FLAG%"=="-g" (set "MODEL_ID=opencode-go/gpt-5.6-luna" & set "MODEL_NAME=GPT-5.6 Luna (2x usage)" & set "VARIANT=max")
if "%MODEL_FLAG%"=="-f" (set "MODEL_ID=opencode-go/deepseek-v4-flash" & set "MODEL_NAME=DeepSeek V4 Flash (2x usage)" & set "VARIANT=max")
if "%MODEL_FLAG%"=="-h" (set "MODEL_ID=opencode-go/hy3" & set "MODEL_NAME=Hy3" & set "VARIANT=high")

rem ---- timestamp & log/list file names ----
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd-HH-mm-ss"') do set "_TS=%%i"
set "LOG_FILE=.agent.%_TS%.log"
set "LIST_FILE=.agent.%_TS%.list"

rem ---- prompt template must exist ----
if not exist "%_PATH%oopencode-prompt.txt" (
    echo ERROR: %_PATH%oopencode-prompt.txt not found
    exit /b 127
)

echo ============================================================
echo   OpenCode launcher: build ^| auto ^| %MODEL_NAME% (%VARIANT%)
echo   log: %LOG_FILE%
echo   user-input list: %LIST_FILE%
if defined DRIVE_FILE (set "_DF=%DRIVE_FILE%") else set "_DF=<none, continue-loop only>"
if defined DRIVE_TIME (set "_DM=ON") else if defined DRIVE_FILE set "_DM=ON"
if defined _DM (
    echo   drive mode: ON ^| first-instruction: %_DF%
) else (
    echo   mode: TUI interactive
)
echo ============================================================

rem ---- run opencode via powershell: ----
rem   * OPENCODE_CONFIG_CONTENT set in this process env (inherited)
rem   * prompt file read as-is (UTF-8, multiline preserved)
rem   * ${HOME}/${_PWD}/${LIST_FILE} placeholders substituted
rem   * stderr redirected to .agent.<TS>.log
set OPENCODE_CONFIG_CONTENT={"lsp":true,"agent":{"build":{"model":"%MODEL_ID%","variant":"%VARIANT%"}}}

if not defined DRIVE_FILE if not defined DRIVE_TIME goto tui_launch

rem ---- drive mode: headless opencode run chain ----
rem   round 1: prompt -> extract session.id -> optional first instruction -> "continue" every interval
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$msg=[string][char]0x7EE7+[char]0x7EED;" ^
  "$iv='%DRIVE_TIME%';" ^
  "if ($iv -eq '') { $sec=30 } else {" ^
  "  $mm=[regex]::Match($iv,'^(\d+)([smh]?)$');" ^
  "  if (-not $mm.Success) { Write-Host ('ERROR: bad --time value: ' + $iv); exit 64 }" ^
  "  $n=[int]$mm.Groups[1].Value;" ^
  "  switch ($mm.Groups[2].Value) { 's' {$sec=$n} 'm' {$sec=$n*60} 'h' {$sec=$n*3600} default {$sec=$n} }" ^
  "}" ^
  "$p=[IO.File]::ReadAllText('%_PATH%oopencode-prompt.txt');" ^
  "$p=$p.Replace('${HOME}',$env:USERPROFILE).Replace('${_PWD}','%_PWD%').Replace('${LIST_FILE}','%LIST_FILE%');" ^
  "Write-Host ('---- drive: prompt round start ' + (Get-Date -Format 'yyyy-MM-dd-HH:mm:ss'));" ^
  "& opencode run --agent build --auto --print-logs --log-level DEBUG $p 2>>'%LOG_FILE%';" ^
  "if ($LASTEXITCODE -ne 0) { Write-Host ('ERROR: prompt round failed, rc=' + $LASTEXITCODE); exit $LASTEXITCODE }" ^
  "$m=Select-String -Path '%LOG_FILE%' -Pattern 'session.id=([A-Za-z0-9_-]+)' | Select-Object -First 1;" ^
  "if (-not $m) { Write-Host 'ERROR: cannot extract session.id'; exit 1 }" ^
  "$sid=$m.Matches[0].Groups[1].Value;" ^
  "Write-Host ('---- drive: session=' + $sid + ' interval=' + $sec + 's ----');" ^
  "if ('%DRIVE_FILE%' -ne '') {" ^
  "  if (-not (Test-Path '%DRIVE_FILE%')) { Write-Host ('ERROR: --file not readable: %DRIVE_FILE%'); exit 66 }" ^
  "  Write-Host ('---- drive: first instruction <- %DRIVE_FILE% ----');" ^
  "  & opencode run -s $sid --agent build --auto --print-logs --log-level DEBUG ([IO.File]::ReadAllText('%DRIVE_FILE%')) 2>>'%LOG_FILE%';" ^
  "  if ($LASTEXITCODE -ne 0) { Write-Host ('WARN: first-instruction round rc=' + $LASTEXITCODE + ', entering continue loop anyway') }" ^
  "} else { Write-Host '---- drive: no -file, enter continue loop directly ----' }" ^
  "$nudges=0; $fails=0;" ^
  "while ($true) {" ^
  "  Start-Sleep -Seconds $sec;" ^
  "  & opencode run -s $sid --agent build --auto --print-logs --log-level DEBUG $msg 2>>'%LOG_FILE%';" ^
  "  if ($LASTEXITCODE -eq 0) { $nudges++; $fails=0; Write-Host ('---- drive: continue #' + $nudges + ' ok ' + (Get-Date -Format 'yyyy-MM-dd-HH:mm:ss')) }" ^
  "  else { $fails++; Write-Host ('WARN: continue send failed ' + $fails + '/3'); if ($fails -ge 3) { Write-Host ('ERROR: 3 consecutive failures, stop (total ok=' + $nudges + ')'); break } }" ^
  "}"
goto run_done

:tui_launch
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p=[IO.File]::ReadAllText('%_PATH%oopencode-prompt.txt');" ^
  "$p=$p.Replace('${HOME}',$env:USERPROFILE).Replace('${_PWD}','%_PWD%').Replace('${LIST_FILE}','%LIST_FILE%');" ^
  "& opencode --agent build --auto --prompt $p --print-logs --log-level DEBUG" 2> "%LOG_FILE%"

:run_done
echo.
echo   user inputs -^> %LIST_FILE%  (recovered on exit by trap-equivalent; see log)
echo   logs -^> %LOG_FILE%

exit /b %errorlevel%
