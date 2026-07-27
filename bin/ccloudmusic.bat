@echo off
setlocal enabledelayedexpansion
title CloudMusic Connect

echo ============================================================
echo   CloudMusic Connect
echo ============================================================
echo.

REM ===========================================================================
REM Step 1: Check if CloudMusic is already running
REM ===========================================================================
echo [1/3] Checking CloudMusic...

tasklist /fi "imagename eq cloudmusic.exe" 2^>nul | find /i "cloudmusic.exe" >nul
if not errorlevel 1 (
    echo        CloudMusic is already running.
    echo ============================================================
    echo.
    pause
    exit /b 0
)

echo        Not running.
echo.

REM ===========================================================================
REM Step 2: Find CloudMusic executable
REM ===========================================================================
echo [2/3] Finding CloudMusic executable...

set CM=

REM Try known installation paths
for %%d in (
    "C:\Program Files\NetEase\CloudMusic\cloudmusic.exe"
    "%ProgramFiles%\NetEase\CloudMusic\cloudmusic.exe"
    "%LocalAppData%\NetEase\CloudMusic\cloudmusic.exe"
    "D:\Program Files\NetEase\CloudMusic\cloudmusic.exe"
) do if not defined CM if exist %%d set CM=%%~d

REM Fallback: registry query
if not defined CM (
    for /f "skip=2 tokens=2*" %%a in (
        'reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\cloudmusic.exe" /ve 2^>nul'
    ) do if not defined CM set CM=%%b
)

if not defined CM (
    echo [FAIL] CloudMusic not found.
    echo.
    echo   Install NetEase CloudMusic:
    echo     https://music.163.com/
    echo.
    echo   Or via winget:
    echo     winget install NetEase.CloudMusic
    echo.
    pause
    exit /b 1
)

echo        Found: !CM!
echo.

REM ===========================================================================
REM Step 3: Launch CloudMusic
REM ===========================================================================
echo [3/3] Launching CloudMusic...

start "" "!CM!"

REM Wait for it to start (max 30s)
set /a N=0
:WAIT_CM
    timeout /t 1 /nobreak >nul
    set /a N+=1
    tasklist /fi "imagename eq cloudmusic.exe" 2^>nul | find /i "cloudmusic.exe" >nul
    if not errorlevel 1 goto CM_RUNNING
    if !N! lss 30 goto WAIT_CM

echo [WARN] CloudMusic did not appear in tasklist after 30s.
echo        It may still be starting...
echo ============================================================
echo.
pause
exit /b 0

:CM_RUNNING
echo        CloudMusic started successfully.
echo ============================================================
echo.
exit /b 0
