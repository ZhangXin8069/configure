@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title LINGSHENG Connect

echo ============================================================
echo   LINGSHENG Connect
echo ============================================================
echo.

ssh 10.44.9.4 -l nsls_yangyb %*

exit /b %errorlevel%
