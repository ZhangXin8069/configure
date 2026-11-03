@echo off
rem Install Node.js for the current user on native Windows (no admin required).
rem Usage: install.bat [VERSION|--check|--help]
rem Env:   NODE_VERSION        target major or full version (default 22)
rem        NODE_INSTALL_DIR    install directory (default %LOCALAPPDATA%\nodejs)

setlocal EnableExtensions EnableDelayedExpansion

set "DEFAULT_VERSION=22"
set "TARGET_VERSION=%DEFAULT_VERSION%"
if defined NODE_VERSION set "TARGET_VERSION=%NODE_VERSION%"
set "NODE_DIR=%LOCALAPPDATA%\nodejs"
if defined NODE_INSTALL_DIR set "NODE_DIR=%NODE_INSTALL_DIR%"
set "CHECK_ONLY="
set "ARG=%~1"

if /i "%ARG%"=="--help" goto :usage
if /i "%ARG%"=="-h" goto :usage
if /i "%ARG%"=="--check" set "CHECK_ONLY=1"
if not "%~2"=="" (
    echo ERROR: expected at most one version argument.
    exit /b 1
)
if defined ARG if not defined CHECK_ONLY set "TARGET_VERSION=%ARG%"

if not defined TARGET_VERSION (
    echo ERROR: target version is empty.
    exit /b 1
)
if /i "%TARGET_VERSION:~0,1%"=="v" set "TARGET_VERSION=%TARGET_VERSION:~1%"
set "TARGET_MAJOR=%TARGET_VERSION%"
for /f "tokens=1 delims=." %%a in ("%TARGET_VERSION%") do set "TARGET_MAJOR=%%a"
set "NON_DIGIT="
for /f "delims=0123456789" %%a in ("%TARGET_MAJOR%") do set "NON_DIGIT=%%a"
if defined NON_DIGIT (
    echo ERROR: invalid version: %TARGET_VERSION%
    echo Use a numeric version such as 22, 24 or 22.11.0.
    exit /b 1
)

set "CUR_MAJOR="
set "CUR_VERSION="
where node >nul 2>&1
if not errorlevel 1 (
    for /f "usebackq delims=" %%v in (`node -p "Number(process.versions.node.split('.')[0])"`) do set "CUR_MAJOR=%%v"
    for /f "usebackq delims=" %%v in (`node --version`) do set "CUR_VERSION=%%v"
)
set "HAS_NPM="
where npm >nul 2>&1
if not errorlevel 1 set "HAS_NPM=1"

if defined CUR_MAJOR if defined HAS_NPM if !CUR_MAJOR! GEQ !TARGET_MAJOR! (
    echo Node.js !CUR_VERSION! already satisfies ^>= !TARGET_MAJOR!, and npm is available.
    exit /b 0
)

if "!CHECK_ONLY!"=="1" (
    if defined CUR_MAJOR (
        echo Node.js !CUR_VERSION! does not satisfy ^>= !TARGET_MAJOR!, or npm is missing.
    ) else (
        echo Node.js was not found.
    )
    exit /b 1
)

set "NODE_ARCH=x64"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "NODE_ARCH=arm64"
if /i "%PROCESSOR_ARCHITEW6432%"=="ARM64" set "NODE_ARCH=arm64"

set "NODE_VERSION_FULL="
for /f "usebackq delims=" %%v in (`powershell -NoProfile -NonInteractive -Command "$c=(Invoke-WebRequest -UseBasicParsing 'https://nodejs.org/dist/latest-v%TARGET_MAJOR%.x/SHASUMS256.txt').Content; if ($c -match 'node-v([0-9]+\.[0-9]+\.[0-9]+)-win-%NODE_ARCH%\.zip') { $Matches[1] }"`) do set "NODE_VERSION_FULL=%%v"
if not defined NODE_VERSION_FULL (
    echo ERROR: failed to resolve Node.js %TARGET_MAJOR%.x for win-%NODE_ARCH%.
    echo Check the version or your network/proxy settings.
    exit /b 1
)

set "TEMP_ZIP=%TEMP%\node-v%NODE_VERSION_FULL%-win-%NODE_ARCH%.zip"
set "EXTRACT_DIR=%TEMP%\node-install-%RANDOM%-%RANDOM%"
echo Downloading Node.js %NODE_VERSION_FULL% ^(win-%NODE_ARCH%^)...
powershell -NoProfile -NonInteractive -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://nodejs.org/dist/v%NODE_VERSION_FULL%/node-v%NODE_VERSION_FULL%-win-%NODE_ARCH%.zip' -OutFile '%TEMP_ZIP%'"
if errorlevel 1 (
    echo ERROR: download failed.
    exit /b 1
)
powershell -NoProfile -NonInteractive -Command "Expand-Archive -Path '%TEMP_ZIP%' -DestinationPath '%EXTRACT_DIR%' -Force"
if errorlevel 1 (
    del /q "%TEMP_ZIP%" 2>nul
    echo ERROR: extraction failed.
    exit /b 1
)
set "EXTRACTED=%EXTRACT_DIR%\node-v%NODE_VERSION_FULL%-win-%NODE_ARCH%"
if not exist "%EXTRACTED%\node.exe" (
    del /q "%TEMP_ZIP%" 2>nul
    rmdir /s /q "%EXTRACT_DIR%" 2>nul
    echo ERROR: node.exe was not found in the downloaded archive.
    exit /b 1
)

if not exist "%NODE_DIR%" mkdir "%NODE_DIR%"
if errorlevel 1 (
    echo ERROR: cannot create "%NODE_DIR%".
    exit /b 1
)
xcopy /E /I /Y /Q "%EXTRACTED%\*" "%NODE_DIR%\" >nul
if errorlevel 1 (
    del /q "%TEMP_ZIP%" 2>nul
    rmdir /s /q "%EXTRACT_DIR%" 2>nul
    echo ERROR: failed to copy Node.js into "%NODE_DIR%".
    exit /b 1
)
del /q "%TEMP_ZIP%" 2>nul
rmdir /s /q "%EXTRACT_DIR%" 2>nul

for /f "usebackq delims=" %%v in (`"%NODE_DIR%\node.exe" --version`) do set "INSTALLED_VERSION=%%v"
if not defined INSTALLED_VERSION (
    echo ERROR: installed node.exe could not report its version.
    exit /b 1
)

echo.
echo Node.js installed: !INSTALLED_VERSION!
echo Install directory: %NODE_DIR%

echo %PATH% | find /i "%NODE_DIR%" >nul
if errorlevel 1 (
    set "CUR_PATH="
    for /f "skip=2 tokens=2,*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "CUR_PATH=%%b"
    if defined CUR_PATH (
        setx PATH "!CUR_PATH!;%NODE_DIR%" >nul
    ) else (
        setx PATH "%NODE_DIR%" >nul
    )
    echo Added "%NODE_DIR%" to user PATH ^(takes effect in new terminals^).
) else (
    echo PATH already contains "%NODE_DIR%".
)

echo Reopen the terminal before using node and npm.
echo Next: install Command Code with lib\_command-code\install.bat.

endlocal
exit /b 0

:usage
echo Usage: install.bat [VERSION^|--check^|--help]
echo.
echo   VERSION       Target major or full version (default: %DEFAULT_VERSION%)
echo   --check       Only check node/npm; do not modify anything
echo   -h, --help    Show this help
echo.
echo Installs Node.js for the current user from nodejs.org.
echo Install directory: %NODE_DIR%
echo Override with NODE_INSTALL_DIR; target version with NODE_VERSION.
exit /b 0
