@echo off
setlocal EnableExtensions
chcp 65001 >nul

if exist "%~dp0_screen-guide.txt" (
    type "%~dp0_screen-guide.txt" 1>&2
) else (
    >&2 echo [WARN] screen is unavailable; continuing without a persistent session.
)

endlocal & exit /b 0
