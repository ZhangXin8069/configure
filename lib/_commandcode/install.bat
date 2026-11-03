@echo off
rem Install Command Code on native Windows through the official npm package.
rem Usage: install.bat [VERSION^|--new]
rem Env:   COMMAND_CODE_INSTALL_DIR  install directory (default %USERPROFILE%\.local\bin)

setlocal EnableExtensions EnableDelayedExpansion

set "PACKAGE_NAME=command-code"
set "DEFAULT_VERSION=1.88.2"
set "INSTALL_DIR=%USERPROFILE%\.local\bin"
if defined COMMAND_CODE_INSTALL_DIR set "INSTALL_DIR=%COMMAND_CODE_INSTALL_DIR%"

if /i "%~1"=="--help" goto :usage
if /i "%~1"=="-h" goto :usage
if not "%~2"=="" (
    echo ERROR: expected at most one version argument.
    exit /b 1
)

set "ARG=%~1"
if not defined ARG (
    set "VERSION=%DEFAULT_VERSION%"
) else if /i "!ARG!"=="--new" (
    set "VERSION=latest"
) else (
    set "VERSION=!ARG!"
)

if "!VERSION:~0,1!"=="-" (
    echo ERROR: unknown option: !VERSION!
    exit /b 1
)
if "!VERSION:~0,1!"=="v" set "VERSION=!VERSION:~1!"

where node >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js was not found. Install Node.js 22 or newer.
    exit /b 1
)
where npm >nul 2>&1
if errorlevel 1 (
    echo ERROR: npm was not found. Install Node.js 22 or newer.
    exit /b 1
)

set "NODE_MAJOR="
for /f "usebackq delims=" %%v in (`node -p "Number(process.versions.node.split('.')[0])"`) do set "NODE_MAJOR=%%v"
if not defined NODE_MAJOR (
    echo ERROR: failed to determine the Node.js major version.
    exit /b 1
)
if !NODE_MAJOR! LSS 22 (
    echo ERROR: Command Code requires Node.js 22 or newer.
    exit /b 1
)

echo Installing Command Code: %PACKAGE_NAME%@!VERSION!
call npm install --global --prefix "%INSTALL_DIR%" --no-fund --no-audit "%PACKAGE_NAME%@!VERSION!"
if errorlevel 1 (
    echo ERROR: npm installation failed.
    exit /b 1
)

rem Windows npm normally puts global shims in the prefix directory itself. Keep a
rem fallback for npm variants that create a bin subdirectory.
set "BIN_DIR=%INSTALL_DIR%"
if not exist "%INSTALL_DIR%\command-code.cmd" if exist "%INSTALL_DIR%\bin\command-code.cmd" set "BIN_DIR=%INSTALL_DIR%\bin"
set "COMMAND_CODE_CMD="
if exist "!BIN_DIR!\command-code.cmd" set "COMMAND_CODE_CMD=!BIN_DIR!\command-code.cmd"
if not defined COMMAND_CODE_CMD (
    for /f "delims=" %%i in ('where command-code.cmd 2^>nul') do if not defined COMMAND_CODE_CMD set "COMMAND_CODE_CMD=%%i"
)
if not defined COMMAND_CODE_CMD (
    echo ERROR: npm installation finished, but command-code.cmd was not found under "%INSTALL_DIR%".
    exit /b 1
)

for /f "usebackq delims=" %%v in (`"!COMMAND_CODE_CMD!" --version`) do set "INSTALLED_VERSION=%%v"
if not defined INSTALLED_VERSION (
    echo ERROR: installed command-code could not report its version.
    exit /b 1
)

echo.
echo Command Code installed: !INSTALLED_VERSION!
echo Install directory: !BIN_DIR!

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
    echo Added "%BIN_DIR%" to user PATH ^(takes effect in new terminals^).
) else (
    echo PATH already contains "%BIN_DIR%".
)

echo Use cmdc for the short alias, or command-code for the full command.
echo Next: cmdc login

endlocal
exit /b 0

:usage
echo Usage: install.bat [VERSION^|--new]
echo.
echo   VERSION       Install a specific version (default: %DEFAULT_VERSION%)
echo   --new         Install the latest npm release
echo   -h, --help    Show this help
echo.
echo Requires Node.js 22 or newer and npm.
echo Install directory: %INSTALL_DIR%
echo Override with COMMAND_CODE_INSTALL_DIR.
exit /b 0
