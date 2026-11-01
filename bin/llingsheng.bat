@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title LINGSHENG Connect

echo ============================================================
echo   LINGSHENG Connect
echo ============================================================
echo.

ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -l nsls_yangyb 10.44.9.4 %*

exit /b %errorlevel%
