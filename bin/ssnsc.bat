@echo off
setlocal enabledelayedexpansion
title NSC Connect

echo ============================================================
echo   NSC Connect
echo ============================================================
echo.

ssh 222.200.137.16 -p 10023 -l zhangxin %*

exit /b %errorlevel%
