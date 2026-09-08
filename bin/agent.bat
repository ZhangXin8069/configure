@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Agent Launcher

rem ============================================================
rem  agent.bat - Windows unified agent launcher
rem  Distribution by filename:
rem    cl[ s ].bat -> Claude Code
rem    op[ s ].bat -> OpenCode
rem    co[ s ].bat -> Codex
rem  The implementation lives in agent-runtime.ps1 so that state,
rem  locking, JSON events and bounded drive semantics remain testable.
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

if not exist "%_PATH%agent-runtime.ps1" (
    echo ERROR: %_PATH%agent-runtime.ps1 不存在
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
