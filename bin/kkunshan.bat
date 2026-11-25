@echo off
setlocal EnableExtensions
chcp 65001 >nul
title KUNSHAN Connect
if not defined SSH_SCREEN_NAME set "SSH_SCREEN_NAME=%COMPUTERNAME%"
if not defined SSH_SCREEN_NAME set "SSH_SCREEN_NAME=windows-client"

echo ============================================================
echo   KUNSHAN Connect
echo ============================================================
echo.

set "_REMOTE_CMD=exec sh -l"
if not "%~1"=="--screen" goto run
set "_REMOTE_CMD=if command -v screen >/dev/null 2>&1; then screen_term=screen; if command -v infocmp >/dev/null 2>&1 && infocmp screen-256color >/dev/null 2>&1; then screen_term=screen-256color; fi; exec screen -U -T $screen_term -S '%SSH_SCREEN_NAME%' -t '%SSH_SCREEN_NAME%'; fi; printf '%s\n' '[WARN] remote screen is unavailable; continuing without it.' >&2; exec sh -l"

:run
ssh -t -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -p 65023 -l sunpeng_1 -i "C:\Users\zhang\cancon.hpccube.com_1013184004_rsa.txt" cancon.hpccube.com "%_REMOTE_CMD%"

exit /b %errorlevel%
