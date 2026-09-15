@echo off
setlocal enabledelayedexpansion

rem Uninstall Claude Code (native installer layout) on Windows.
rem Companion to cc-v20260706.ps1.

set "PURGE=0"
set "YES=0"
set "DRYRUN=0"
set "REMOVE_NPM=0"

:parse
if "%~1"=="" goto :parse_done
set "arg=%~1"
if /i "%arg%"=="-h" goto :usage
if /i "%arg%"=="--help" goto :usage
if /i "%arg%"=="-y" (set "YES=1" & shift & goto :parse)
if /i "%arg%"=="--yes" (set "YES=1" & shift & goto :parse)
if /i "%arg%"=="-purge" (set "PURGE=1" & shift & goto :parse)
if /i "%arg%"=="--purge" (set "PURGE=1" & shift & goto :parse)
if /i "%arg%"=="-npm" (set "REMOVE_NPM=1" & shift & goto :parse)
if /i "%arg%"=="--npm" (set "REMOVE_NPM=1" & shift & goto :parse)
if /i "%arg%"=="-dryrun" (set "DRYRUN=1" & shift & goto :parse)
if /i "%arg%"=="--dry-run" (set "DRYRUN=1" & shift & goto :parse)
echo Unknown option: %arg% 1>&2
goto :usage_err
:parse_done

set "BIN_DIR=%USERPROFILE%\.local\bin"
set "LINK_PATH=%BIN_DIR%\claude.exe"
set "INSTALL_BASE=%USERPROFILE%\.local\share\claude"
set "CONFIG_PATH=%USERPROFILE%\.claude.json"
set "CLAUDE_DIR=%USERPROFILE%\.claude"
set "STATE_DIR=%USERPROFILE%\.local\state\claude"
set "CACHE_DIR=%USERPROFILE%\.cache\claude"
set "NPM_PACKAGE=@anthropic-ai/claude-code"

goto :main

:usage
echo Usage: uninstall_cc-v20260812.bat [OPTIONS]
echo.
echo Uninstall Claude Code on Windows.
echo.
echo Options:
echo   -h, --help      Show this help message and exit
echo   -y, --yes       Skip the confirmation prompt
echo       --npm       Also uninstall the npm-installed @anthropic-ai/claude-code
echo       --purge     Also remove user data: %%USERPROFILE%%\.claude.json and %%USERPROFILE%%\.claude
echo       --dry-run   Show what would be removed without removing anything
echo.
echo Default behavior:
echo   Remove claude.exe and claude-*.exe from %%USERPROFILE%%\.local\bin,
echo   the version cache %%USERPROFILE%%\.local\share\claude, state and cache
echo   directories, and the .local\bin entry from the user PATH.
echo   User data is kept unless --purge is given.
exit /b 0

:usage_err
call :usage
exit /b 1

:rm_path
set "p=%~1"
if not exist "%p%" exit /b 0
if "%DRYRUN%"=="1" (
    echo [dry-run] would remove: %p%
    exit /b 0
)
if /i "%~2"=="dir" (
    rmdir /s /q "%p%" >nul 2>&1
) else (
    del /f /q "%p%" >nul 2>&1
)
if exist "%p%" (
    echo warning: could not fully remove: %p%
) else (
    echo removed: %p%
)
exit /b 0

:confirm
set "reply="
if "%YES%"=="1" exit /b 0
if "%DRYRUN%"=="1" exit /b 0
set /p reply="Remove %~1? [y/N] "
if /i "%reply%"=="y" exit /b 0
if /i "%reply%"=="yes" exit /b 0
echo Aborted.
exit /b 1

:strip_path
set "USERPATH="
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USERPATH=%%b"
if not defined USERPATH exit /b 0

set "bin_norm=%BIN_DIR%"
if "!bin_norm:~-1!"=="\" set "bin_norm=!bin_norm:~0,-1!"

set "kept="
set "changed=0"
for %%e in ("%USERPATH:;=" "%") do (
    set "entry=%%~e"
    if defined entry (
        set "enorm=!entry!"
        set "enorm=!enorm:%%USERPROFILE%%=%USERPROFILE%!"
        if "!enorm:~-1!"=="\" set "enorm=!enorm:~0,-1!"
        if /i "!enorm!"=="!bin_norm!" (
            set "changed=1"
        ) else (
            set "kept=!kept!;!entry!"
        )
    )
)
if "%changed%"=="0" exit /b 0
if "%DRYRUN%"=="1" (
    echo [dry-run] would remove %BIN_DIR% from the user PATH
    exit /b 0
)
if defined kept set "kept=!kept:~1!"
reg add "HKCU\Environment" /v Path /t REG_EXPAND_SZ /d "!kept!" /f >nul 2>&1
echo removed %BIN_DIR% from the user PATH
exit /b 0

:handle_npm
where npm >nul 2>&1
if errorlevel 1 exit /b 0
call npm ls -g --depth=0 %NPM_PACKAGE% >nul 2>&1
if errorlevel 1 exit /b 0
echo Found npm-installed Claude Code (%NPM_PACKAGE%).
if "%REMOVE_NPM%"=="1" (
    if "%DRYRUN%"=="1" (
        echo [dry-run] would run: npm uninstall -g %NPM_PACKAGE%
        exit /b 0
    )
    echo Running: npm uninstall -g %NPM_PACKAGE%
    call npm uninstall -g %NPM_PACKAGE%
) else (
    echo Run 'npm uninstall -g %NPM_PACKAGE%' or re-run with --npm to remove it.
)
exit /b 0

:main
echo === Claude Code uninstaller ===

set "BINARIES=0"
if exist "%LINK_PATH%" set "BINARIES=1"
if exist "%INSTALL_BASE%" set "BINARIES=1"
if exist "%BIN_DIR%\claude-*.exe" set "BINARIES=1"

set "DATA=0"
if "%PURGE%"=="1" (
    if exist "%CONFIG_PATH%" set "DATA=1"
    if exist "%CLAUDE_DIR%" set "DATA=1"
)

if "%BINARIES%"=="0" if "%DATA%"=="0" (
    echo No Claude Code installation found in the standard locations.
    call :handle_npm
    exit /b 0
)

set "SCOPE=binaries, version files, state and cache"
if "%PURGE%"=="1" set "SCOPE=binaries, version files, state, cache and user data (.claude.json, .claude)"

call :confirm "%SCOPE%"
if errorlevel 1 exit /b 1

call :rm_path "%LINK_PATH%" file
for %%f in ("%BIN_DIR%\claude-*.exe") do call :rm_path "%%f" file
call :rm_path "%INSTALL_BASE%" dir
call :rm_path "%STATE_DIR%" dir
call :rm_path "%CACHE_DIR%" dir
if "%PURGE%"=="1" (
    call :rm_path "%CONFIG_PATH%" file
    call :rm_path "%CLAUDE_DIR%" dir
)
call :strip_path

if "%PURGE%"=="0" (
    echo.
    echo User data kept: %CONFIG_PATH%, %CLAUDE_DIR%
    echo Re-run with --purge to remove them too.
)
call :handle_npm
echo.
echo Uninstall complete.
if "%DRYRUN%"=="1" echo (dry run - nothing was actually removed)
echo Restart your shell for PATH changes to take effect.
exit /b 0
