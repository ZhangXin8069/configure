@echo off
setlocal EnableExtensions
chcp 65001 >nul
title SS Connect

set "_PATH=%~dp0"
set "_NAME=%~nx0"
echo ###%_NAME% in %_PATH% is running...:%date% %time%###

set "_SCREEN_ARG="
set "_SHORT=%~1"
if /i "%~1"=="--screen" (
    set "_SCREEN_ARG=-Screen"
    set "_SHORT=%~2"
)

if not exist "%_PATH%ss.ps1" (
    echo ERROR: "%_PATH%ss.ps1" was not found.
    endlocal & exit /b 127
)

if not defined _SHORT set "_SHORT=k"
set "SS_SHORT=%_SHORT%"
if not defined SSH_SCREEN_NAME set "SSH_SCREEN_NAME=%~n0"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%_PATH%ss.ps1" %_SCREEN_ARG%
set "_RC=%errorlevel%"

echo ###%_NAME% in %_PATH% is done......:%date% %time%###
endlocal & exit /b %_RC%
