@echo off
setlocal enabledelayedexpansion
title SNSC Connect

echo ============================================================
echo   SNSC Connect
echo ============================================================
echo.

ssh 222.200.137.16 -p 10023 -l zhangxin %*

exit /b %errorlevel%
