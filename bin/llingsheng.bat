@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title LINGSHENG Connect
if not defined SSH_SCREEN_NAME set "SSH_SCREEN_NAME=%COMPUTERNAME%"
if not defined SSH_SCREEN_NAME set "SSH_SCREEN_NAME=windows-client"

echo ============================================================
echo   LINGSHENG Connect
echo ============================================================
echo.

ssh -t -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l nsls_yangyb 10.44.9.4 "if command -v screen >/dev/null 2>&1; then screen_term=screen; if command -v infocmp >/dev/null 2>&1 && infocmp screen-256color >/dev/null 2>&1; then screen_term=screen-256color; fi; exec screen -U -T $screen_term -S '%SSH_SCREEN_NAME%' -t '%SSH_SCREEN_NAME%'; fi; printf '%s\n' '[WARN] remote screen is unavailable; continuing without it.' >&2; exec sh -l"

exit /b %errorlevel%
