@echo off
setlocal enabledelayedexpansion
title SNSC Connect

echo ============================================================
echo   SNSC Connect
echo ============================================================
echo.

ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -p 10023 -l zhangxin 222.200.137.16 %*

exit /b %errorlevel%
