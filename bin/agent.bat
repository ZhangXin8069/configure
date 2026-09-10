@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Agent Launcher

rem ============================================================
rem  agent.bat - Windows unified agent launcher
<<<<<<< HEAD
rem  Distribution by filename (%%~nx0, cpupower.sh-style): 
rem    cl.bat -> Claude Code | op.bat -> OpenCode | co.bat -> Codex
rem  Deploy: copy agent.bat as cl.bat / op.bat / co.bat
rem          (or: mklink /H cl.bat agent.bat  on the same volume)
rem  Reference: agent.sh (Unix). Prompt read from agent-prompt.txt.
rem  Usage: {cl|op|co}.bat [-m|-o|-p|-q|-k|-g|-f|-h] [--model MODEL] [-file PATH] [-time DUR]
rem    Codex 默认模型: gpt-6-astra / medium（CODEX_DEFAULT_MODEL_FLAG 可覆盖默认旗标）
rem    --model MODEL    : override model id directly (env *AGENT*_MODEL also works)
rem    --variant LEVEL  : opencode only - build agent variant (max/xhigh/high/low etc.)
rem    --reasoning-effort LEVEL : codex only (low/medium/high/xhigh/max/ultra)
rem    --sandbox POLICY / --ask-for-approval POLICY : codex only
rem    codex default provider: lqcd / api / fast / pragmatic (key via LQCD_API_KEY)
rem    -file PATH : drive mode (cl/op) - after the prompt round completes, send file
rem                 content as first instruction, then send "continue" every -time
rem    -time DUR  : "continue" interval; plain number=seconds; s/m/h suffix ok (default 30s)
=======
rem  Distribution by filename:
rem    cl[ s ].bat -> Claude Code
rem    op[ s ].bat -> OpenCode
rem    co[ s ].bat -> Codex
rem  The implementation lives in agent-runtime.ps1 so that state,
rem  locking, JSON events and bounded drive semantics remain testable.
>>>>>>> 18a5bfec545adc0029cee1129dba8a3437730299
rem ============================================================

set "_NAME=%~nx0"
set "_PATH=%~dp0"
set "_PWD=%CD%"
set "_AGENT="
set "_SNSC=0"

if /i "%_NAME%"=="cl.bat"  set "_AGENT=claude"
if /i "%_NAME%"=="cls.bat" (
    set "_AGENT=claude"
    set "_SNSC=1"
)
if /i "%_NAME%"=="op.bat"  set "_AGENT=opencode"
if /i "%_NAME%"=="ops.bat" (
    set "_AGENT=opencode"
    set "_SNSC=1"
)
if /i "%_NAME%"=="co.bat"  set "_AGENT=codex"
if /i "%_NAME%"=="cos.bat" (
    set "_AGENT=codex"
    set "_SNSC=1"
)

if not defined _AGENT (
    echo 用法：将 agent.bat 复制或链接为 cl.bat、op.bat、co.bat
    echo HPC 变体：cls.bat、ops.bat、cos.bat
    exit /b 1
)

<<<<<<< HEAD
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
    if defined CODEX_DEFAULT_MODEL_FLAG (
        set "MODEL_FLAG=%CODEX_DEFAULT_MODEL_FLAG%"
    ) else (
        if "%AGENT%"=="opencode" set "MODEL_FLAG=-f"
        if "%AGENT%"=="codex" set "MODEL_FLAG=-q"
        if "%AGENT%"=="claude" set "MODEL_FLAG=-m"
    )
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
set "MODEL_ID=gpt-6-astra"
set "MODEL_NAME=GPT-6-Astra"
set "REASONING_EFFORT=medium"
if "%MODEL_FLAG%"=="-o" (set "MODEL_ID=gpt-5.6-sol" & set "MODEL_NAME=GPT-5.6-Sol" & set "REASONING_EFFORT=max")
if "%MODEL_FLAG%"=="-p" (set "MODEL_ID=gpt-5.6-terra" & set "MODEL_NAME=GPT-5.6-Terra" & set "REASONING_EFFORT=high")
if "%MODEL_FLAG%"=="-q" (set "MODEL_ID=gpt-6-astra" & set "MODEL_NAME=GPT-6-Astra" & set "REASONING_EFFORT=medium")
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
if not defined CODEX_PROVIDER_ID set "CODEX_PROVIDER_ID=lqcd"
if not defined CODEX_PROVIDER_NAME set "CODEX_PROVIDER_NAME=lqcd"
if not defined CODEX_PROVIDER_BASE_URL set "CODEX_PROVIDER_BASE_URL=http://nat200.natappvip.cc/v1"
if not defined CODEX_PROVIDER_ENV_KEY set "CODEX_PROVIDER_ENV_KEY=LQCD_API_KEY"
if not defined CODEX_MODEL_CONTEXT_WINDOW set "CODEX_MODEL_CONTEXT_WINDOW=1000000"
if not defined CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT set "CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT=900000"
if not defined CODEX_SERVICE_TIER set "CODEX_SERVICE_TIER=off"
if not defined CODEX_PERSONALITY set "CODEX_PERSONALITY=pragmatic"
if not defined CODEX_APPROVALS_REVIEWER set "CODEX_APPROVALS_REVIEWER=auto_review"
if not defined CODEX_FORCED_LOGIN_METHOD set "CODEX_FORCED_LOGIN_METHOD=api"
if not defined CODEX_TUI_STATUS_LINE set "CODEX_TUI_STATUS_LINE=["model-with-reasoning","current-dir","hostname","branch-changes","run-state","permissions","approval-mode","context-used","weekly-limit","estimated-thread-cost","thread-id","fast-mode","task-progress"]"
if not defined CODEX_TUI_STATUS_LINE_USE_COLORS set "CODEX_TUI_STATUS_LINE_USE_COLORS=true"

rem ---- timestamp & log file ----
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd-HH-mm-ss"') do set "_TS=%%i"
set "LOG_FILE=.agent.%_TS%.log"
set "LIST_FILE=.agent.%_TS%.list"

rem ---- prompt template must exist ----
if not exist "%_PATH%agent-prompt.txt" (
    echo ERROR: %_PATH%agent-prompt.txt not found
=======
if not exist "%_PATH%agent-runtime.ps1" (
    echo ERROR: %_PATH%agent-runtime.ps1 不存在
>>>>>>> 18a5bfec545adc0029cee1129dba8a3437730299
    exit /b 127
)

set "AGENT_BAT_LAUNCHER_NAME=%_NAME%"
set "AGENT_BAT_SCRIPT_DIR=%_PATH%"
set "AGENT_BAT_WORKDIR=%_PWD%"
set "AGENT_BAT_AGENT=%_AGENT%"
set "AGENT_BAT_SNSC=%_SNSC%"

set "_PS_CMD="
where powershell.exe >nul 2>&1
if not errorlevel 1 set "_PS_CMD=powershell.exe"
if not defined _PS_CMD (
    where pwsh.exe >nul 2>&1
    if not errorlevel 1 set "_PS_CMD=pwsh.exe"
)
if not defined _PS_CMD (
    echo ERROR: 未找到 powershell.exe 或 pwsh.exe
    exit /b 127
)

"%_PS_CMD%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%_PATH%agent-runtime.ps1" %*
set "_RC=%errorlevel%"
echo ###%_NAME% in %_PATH% is done......:%date% %time%###
exit /b %_RC%
