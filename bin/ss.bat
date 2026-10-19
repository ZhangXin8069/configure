@echo off
setlocal EnableExtensions
chcp 65001 >nul
title SS Connect

set "_PATH=%~dp0"
set "_NAME=%~nx0"
echo ###%_NAME% in %_PATH% is running...:%date% %time%###

if not "%~2"=="" (
    echo ERROR: ss accepts only one alias, number, or combined argument.
    endlocal & exit /b 64
)

if not exist "%_PATH%ss.ps1" (
    echo ERROR: "%_PATH%ss.ps1" was not found.
    endlocal & exit /b 127
)

set "_SHORT=%~1"
if not defined _SHORT set "_SHORT=k"
set "SS_SHORT=%_SHORT%"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%_PATH%ss.ps1"
set "_RC=%errorlevel%"

echo ###%_NAME% in %_PATH% is done......:%date% %time%###
endlocal & exit /b %_RC%
