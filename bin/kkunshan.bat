@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title KUNSHAN Connect
if not defined SSH_SCREEN_NAME set "SSH_SCREEN_NAME=%~n0"

echo ============================================================
echo   KUNSHAN Connect
echo ============================================================
echo.

where screen >nul 2>&1
if errorlevel 1 (
    call "%~dp0_screen-warning.bat"
    ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -p 65023 -l sunpeng_1 -i "C:\Users\zhang\cancon.hpccube.com_1013184004_rsa.txt" cancon.hpccube.com %*
) else (
    screen -t "%SSH_SCREEN_NAME%" -S "%SSH_SCREEN_NAME%" -d -R ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -p 65023 -l sunpeng_1 -i "C:\Users\zhang\cancon.hpccube.com_1013184004_rsa.txt" cancon.hpccube.com %*
)

exit /b %errorlevel%
