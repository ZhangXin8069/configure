@echo off
rem Install Codex CLI (Windows x64) via npm into %USERPROFILE%\.local\bin
rem Usage: install.bat [--new] [VERSION]
rem        default: 0.154.0 ; --new: latest ; VERSION: explicit (overrides --new)
rem Env:   CODEX_INSTALL_DIR  install directory (default %USERPROFILE%\.local\bin)

setlocal EnableExtensions EnableDelayedExpansion

set "DEFAULT_VERSION=0.154.0"

rem ---- 安装目录 ----
set "INSTALL_DIR=%USERPROFILE%\.local\bin"
if defined CODEX_INSTALL_DIR set "INSTALL_DIR=%CODEX_INSTALL_DIR%"

title Codex Installer

echo ============================================================
echo   Codex Installer (Windows, npm)
echo ============================================================
echo.

rem ---- npm 检查 ----
where npm >nul 2>nul
if errorlevel 1 (
    echo   ERROR: npm not found. Install Node.js LTS first: https://nodejs.org/
    exit /b 1
)

rem ---- 参数解析 ----
rem 无参数 => %DEFAULT_VERSION%；--new => latest；显式 VERSION 优先级最高
set "USE_LATEST="
set "VER="
:parse_args
if "%~1"=="" goto args_parsed
set "ARG=%~1"
if /i "!ARG!"=="--new" (
    set "USE_LATEST=1"
) else (
    if "!ARG:~0,1!"=="-" (
        echo   ERROR: unknown option: !ARG!
        exit /b 1
    )
    set "VER=!ARG!"
)
shift
goto parse_args
:args_parsed

rem ---- 版本解析 / 安装 ----
rem 注意: Windows 下 npm 全局 bin 目录即 prefix 目录本身（Unix 下为 prefix/bin），
rem       故 --prefix 指向 %INSTALL_DIR%，codex.cmd 直接落于其中（连同 node_modules/）。
set "PKG=@openai/codex"
set "SPEC=%PKG%@%DEFAULT_VERSION%"
if not "%VER%"=="" set "SPEC=%PKG%@%VER%"
if defined USE_LATEST (
    if "%VER%"=="" set "SPEC=%PKG%@latest"
)
echo   Installing %SPEC% ...
call npm install -g --prefix "%INSTALL_DIR%" "%SPEC%"
if errorlevel 1 (
    echo   ERROR: npm install failed.
    exit /b 1
)

rem ---- 定位可执行文件（兼容把 bin 置于 prefix\bin 的 npm 版本）----
set "BIN_DIR=%INSTALL_DIR%"
if not exist "%INSTALL_DIR%\codex.cmd" if exist "%INSTALL_DIR%\bin\codex.cmd" set "BIN_DIR=%INSTALL_DIR%\bin"
if not exist "%BIN_DIR%\codex.cmd" (
    echo   ERROR: codex.cmd not found under "%INSTALL_DIR%" after install.
    exit /b 1
)

rem ---- 验证 ----
call "%BIN_DIR%\codex.cmd" --version
if errorlevel 1 (
    echo   ERROR: installed codex failed to run.
    exit /b 1
)

rem ---- 写入用户 PATH（幂等，保留 REG_EXPAND_SZ）----
echo %PATH% | find /i "%BIN_DIR%" >nul
if errorlevel 1 (
    set "CUR_PATH="
    for /f "skip=2 tokens=2,*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "CUR_PATH=%%b"
    if defined CUR_PATH (
        setx PATH "!CUR_PATH!;%BIN_DIR%" >nul
    ) else (
        setx PATH "%BIN_DIR%" >nul
    )
    echo   Added "%BIN_DIR%" to user PATH (takes effect in new terminals).
) else (
    echo   PATH already contains "%BIN_DIR%".
)

echo.
echo   Codex installed via npm: %BIN_DIR%\codex.cmd
echo   Reopen the terminal, then run: codex login
endlocal
exit /b 0