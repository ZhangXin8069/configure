@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title OpenCode Launcher

rem ============================================================
rem  oopencode.bat - Windows launcher for opencode (build agent)
rem  Reference: oopencode.sh (Unix). Prompt read from oopencode-prompt.txt.
rem  Usage: oopencode.bat [-p|-q|-k|-g|-f]  (default -f)
rem ============================================================

set "_PATH=%~dp0"
set "_PWD=%CD%"

rem ---- model selection (default -f DeepSeek V4 Flash) ----
set "MODEL_ID=opencode-go/deepseek-v4-flash"
if /i "%~1"=="-p" set "MODEL_ID=opencode-go/deepseek-v4-pro"
if /i "%~1"=="-q" set "MODEL_ID=opencode-go/qwen3.8-max"
if /i "%~1"=="-k" set "MODEL_ID=opencode-go/kimi-k3"
if /i "%~1"=="-g" set "MODEL_ID=opencode-go/gpt-5.6-luna"

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
echo   OpenCode launcher: build ^| auto ^| %MODEL_ID% (max)
echo   log: %LOG_FILE%
echo   user-input list: %LIST_FILE%
echo ============================================================

rem ---- run opencode via powershell: ----
rem   * OPENCODE_CONFIG_CONTENT set in this process env (inherited)
rem   * prompt file read as-is (UTF-8, multiline preserved)
rem   * ${HOME}/${_PWD}/${LIST_FILE} placeholders substituted
rem   * stderr redirected to .agent.<TS>.log (cmd-level redirect)
set OPENCODE_CONFIG_CONTENT={"agent":{"build":{"model":"%MODEL_ID%","variant":"max"}}}

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p=[IO.File]::ReadAllText('%_PATH%oopencode-prompt.txt');" ^
  "$p=$p.Replace('${HOME}',$env:USERPROFILE).Replace('${_PWD}','%_PWD%').Replace('${LIST_FILE}','%LIST_FILE%');" ^
  "& opencode --agent build --auto --prompt $p --print-logs --log-level DEBUG" 2> "%LOG_FILE%"

echo.
echo   user inputs -^> %LIST_FILE%  (recovered on exit by trap-equivalent; see log)
echo   logs -^> %LOG_FILE%

exit /b %errorlevel%
