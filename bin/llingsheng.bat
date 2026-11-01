@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title LINGSHENG Connect
if not defined SSH_SCREEN_NAME set "SSH_SCREEN_NAME=%~n0"

echo ============================================================
echo   LINGSHENG Connect
echo ============================================================
echo.

where screen >nul 2>&1
if errorlevel 1 (
    call "%~dp0_screen-warning.bat"
    ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l nsls_yangyb 10.44.9.4 %*
) else (
    screen -t "%SSH_SCREEN_NAME%" -S "%SSH_SCREEN_NAME%" -d -R ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l nsls_yangyb 10.44.9.4 %*
)

exit /b %errorlevel%
