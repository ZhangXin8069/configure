@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title SNSC Connect
if not defined SSH_SCREEN_NAME set "SSH_SCREEN_NAME=%~n0"

echo ============================================================
echo   SNSC Connect
echo ============================================================
echo.

where screen >nul 2>&1
if errorlevel 1 (
    call "%~dp0_screen-warning.bat"
    ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -p 10023 -l zhangxin 222.200.137.16 %*
) else (
    screen -t "%SSH_SCREEN_NAME%" -S "%SSH_SCREEN_NAME%" -d -R ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -p 10023 -l zhangxin 222.200.137.16 %*
)

exit /b %errorlevel%
