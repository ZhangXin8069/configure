@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title KUNSHAN Connect

echo ============================================================
echo   KUNSHAN Connect
echo ============================================================
echo.

ssh cancon.hpccube.com -p 65023 -l sunpeng_1 -i "C:\Users\zhang\cancon.hpccube.com_1013184004_rsa.txt" %*

exit /b %errorlevel%
