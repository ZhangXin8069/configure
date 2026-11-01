@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title KUNSHAN Connect

echo ============================================================
echo   KUNSHAN Connect
echo ============================================================
echo.

ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -p 65023 -l sunpeng_1 -i "C:\Users\zhang\cancon.hpccube.com_1013184004_rsa.txt" cancon.hpccube.com %*

exit /b %errorlevel%
