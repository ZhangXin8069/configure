@echo off
setlocal enabledelayedexpansion
title Docker Connect

echo ============================================================
echo   Docker Connect
echo ============================================================
echo.

REM ===========================================================================
REM Step 1: Check Docker
REM ===========================================================================
echo [1/4] Checking Docker...

REM Try docker info first
docker info >nul 2>&1
if not errorlevel 1 goto DOCKER_OK

REM Try docker version as lighter fallback
docker version >nul 2>&1
if not errorlevel 1 goto DOCKER_OK

REM Docker daemon not running -- try to start Docker Desktop
echo        Daemon not running, launching Docker Desktop...

set DD=
for %%d in (
    "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
    "%LocalAppData%\Docker\Docker Desktop.exe"
) do if not defined DD if exist %%d set DD=%%~d

if not defined DD (
    for /f "skip=2 tokens=2*" %%a in (
        'reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Docker Desktop.exe" /ve 2^>nul'
    ) do if not defined DD set DD=%%b
)

if not defined DD (
    echo [FAIL] Docker Desktop not found.
    echo        Install: winget install Docker.DockerDesktop
    echo.
    pause
    exit /b 1
)

start "" "!DD!"

REM Wait for daemon (max 90s)
set /a N=0
:WAIT_DD
    timeout /t 1 /nobreak >nul
    set /a N+=1
    docker info >nul 2>&1 && goto DOCKER_OK
    if !N! lss 90 goto WAIT_DD

echo [FAIL] Docker daemon did not start in 90s.
echo.
pause
exit /b 1

:DOCKER_OK
for /f "delims=" %%v in ('docker info --format "{{.ServerVersion}}" 2^>nul') do set DKR_VER=%%v
if "!DKR_VER!"=="" set DKR_VER=unknown
echo        Docker is running (v!DKR_VER!)
echo.

REM ===========================================================================
REM Step 2: Find container
REM ===========================================================================
echo [2/4] Finding container...

set LATEST=
for /f "delims=" %%i in ('docker ps -a --format "{{.Names}}" --latest 2^>nul') do set LATEST=%%i

REM Fallback by ID
if "!LATEST!"=="" (
    for /f "delims=" %%i in ('docker ps -aq --last 1 2^>nul') do (
        for /f "delims=" %%n in ('docker inspect -f "{{.Name}}" %%i 2^>nul') do set LATEST=%%n
        if not "!LATEST!"=="" set LATEST=!LATEST:~1!
    )
)

if not "!LATEST!"=="" goto GOT_CONTAINER

echo [FAIL] No containers found.
echo.
set HAS_IMG=0
for /f "delims=" %%i in ('docker images -q 2^>nul') do set HAS_IMG=1
if "!HAS_IMG!"=="1" (
    echo   Images found. Create a container:
    echo     docker run -d --name test ubuntu tail -f /dev/null
) else (
    echo   Pull an image and create a container:
    echo     docker pull ubuntu
    echo     docker run -d --name test ubuntu tail -f /dev/null
    echo.
    echo   Guide: https://gitee.com/zhangxin8069/configure/raw/stab10/lib/_docker/setup.md
)
echo.
pause
exit /b 1

:GOT_CONTAINER
echo        Container: !LATEST!
echo.

REM ===========================================================================
REM Step 3: Ensure running
REM ===========================================================================
echo [3/4] Checking container status...

for /f "delims=" %%s in ('docker inspect -f "{{.State.Status}}" "!LATEST!" 2^>nul') do set STATUS=%%s

if "!STATUS!"=="running" (
    echo        Already running
) else (
    echo        Status: !STATUS! -- starting...
    docker start "!LATEST!" >nul 2>&1
    if errorlevel 1 (
        echo [FAIL] Could not start container.
        echo        docker logs "!LATEST!"
        echo.
        pause
        exit /b 1
    )
    echo        Started
)
echo.

REM ===========================================================================
REM Step 4: Detect shell, enter container, cd $HOME, launch zsh
REM ===========================================================================
echo [4/4] Detecting shell and opening terminal...

set SH=
docker exec "!LATEST!" which bash >nul 2>&1    && set SH=bash
if "!SH!"=="" docker exec "!LATEST!" which sh  >nul 2>&1 && set SH=sh
if "!SH!"=="" docker exec "!LATEST!" test -x /bin/bash >nul 2>&1 && set SH=bash
if "!SH!"=="" docker exec "!LATEST!" test -x /bin/sh   >nul 2>&1 && set SH=sh
if "!SH!"=="" docker exec "!LATEST!" test -x /bin/ash  >nul 2>&1 && set SH=ash

if "!SH!"=="" (
    echo [FAIL] No shell found in container.
    echo.
    pause
    exit /b 1
)

echo        Base shell: /bin/!SH!

REM Check if zsh is available (preferred)
set HAS_ZSH=0
docker exec "!LATEST!" which zsh       >nul 2>&1 && set HAS_ZSH=1
if "!HAS_ZSH!"=="0" docker exec "!LATEST!" test -x /bin/zsh >nul 2>&1 && set HAS_ZSH=1

if "!HAS_ZSH!"=="1" (
    set FINAL=zsh
    echo        Using zsh
) else (
    set FINAL=!SH!
)

echo        cd $HOME ^&^& exec !FINAL!
echo ============================================================
echo.

REM Launch: the shell -c runs "cd $HOME && exec <final_shell>"
REM $HOME is expanded by the container's shell, not by CMD
docker exec -it "!LATEST!" !SH! -c "cd $HOME && exec !FINAL! -l"

exit /b 0
