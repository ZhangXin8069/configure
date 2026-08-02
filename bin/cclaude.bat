@echo off
setlocal enabledelayedexpansion
title Claude Code

echo ============================================================
echo   Claude Code (permission-mode: auto)
echo ============================================================
echo.

claude --permission-mode auto %*

exit /b %errorlevel%
