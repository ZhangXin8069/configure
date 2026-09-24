@echo off
rem Install OpenCode V2 (Windows x64/ARM64) into %USERPROFILE%\.local\bin
rem Usage: install.bat [VERSION]   (default: latest)
rem Env:   OPENCODE_INSTALL_DIR  install directory (default %USERPROFILE%\.local\bin)
rem        OPENCODE_BASE_URL     binary source (default https://opencode.ai/files/bin)

setlocal EnableExtensions EnableDelayedExpansion

rem ---- 安装目录 ----
set "INSTALL_DIR=%USERPROFILE%\.local\bin"
if defined OPENCODE_INSTALL_DIR set "INSTALL_DIR=%OPENCODE_INSTALL_DIR%"
set "OPENCODE_BASE=https://opencode.ai/files/bin"
if defined OPENCODE_BASE_URL set "OPENCODE_BASE=%OPENCODE_BASE_URL%"

title OpenCode Installer

echo ============================================================
echo   OpenCode Installer (Windows)
echo ============================================================
echo.

rem ---- 架构检测 ----
set "PROC_ARCH=%PROCESSOR_ARCHITECTURE%"
if defined PROCESSOR_ARCHITEW6432 set "PROC_ARCH=%PROCESSOR_ARCHITEW6432%"
if /i "%PROC_ARCH%"=="ARM64" (
    set "TARGET=windows-arm64"
)
if /i "%PROC_ARCH%"=="x86" (
    echo   ERROR: opencode does not support 32-bit Windows.
    exit /b 1
)

rem ---- AVX2 检测（老 x64 CPU 用 baseline 构建；ARM64 不需要）----
if not defined TARGET (
    set "TARGET=windows-x64"
    set "HAS_AVX2="
    for /f "delims=" %%i in ('powershell -NoProfile -NonInteractive -Command "(Add-Type -MemberDefinition '[DllImport(""kernel32.dll"")] public static extern bool IsProcessorFeaturePresent(int ProcessorFeature);' -Name Kernel32 -Namespace Win32 -PassThru)::IsProcessorFeaturePresent(40)" 2^>nul') do set "HAS_AVX2=%%i"
    if /i not "%HAS_AVX2%"=="True" if not "%HAS_AVX2%"=="1" (
        echo   CPU without AVX2 detected - using baseline build.
        set "TARGET=windows-x64-baseline"
    )
)

rem ---- 版本解析 / 下载地址 ----
set "VER=%~1"
if defined VER if /i "%VER:~0,1%"=="v" set "VER=%VER:~1%"
if not defined VER (
    for /f "usebackq delims=" %%i in (`powershell -NoProfile -NonInteractive -Command "(Invoke-RestMethod -Uri 'https://opencode.ai/update/api/latest/cli/npm').version"`) do set "VER=%%i"
)
if not defined VER (
    echo   ERROR: failed to resolve latest OpenCode V2 version.
    exit /b 1
)
set "FILENAME=opencode-%TARGET%.zip"
set "URL=%OPENCODE_BASE%/%VER%/%FILENAME%"

echo   Version: %VER%
echo   Asset:   %FILENAME%
echo   Downloading...
curl.exe -fL --progress-bar -o "%TEMP%\opencode-install.zip" "%URL%"
if errorlevel 1 (
    echo   ERROR: download failed.
    exit /b 1
)

rem ---- 解压 ----
echo   Extracting...
set "EXTRACT_DIR=%TEMP%\opencode-install"
if exist "%EXTRACT_DIR%" rmdir /s /q "%EXTRACT_DIR%"
powershell -NoProfile -NonInteractive -Command "Expand-Archive -Path '%TEMP%\opencode-install.zip' -DestinationPath '%EXTRACT_DIR%' -Force"
if errorlevel 1 (
    echo   ERROR: extraction failed.
    exit /b 1
)

rem ---- 安装 ----
echo   Installing...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if exist "%EXTRACT_DIR%\opencode.exe" (
    move /y "%EXTRACT_DIR%\opencode.exe" "%INSTALL_DIR%\opencode.exe" >nul
) else (
    move /y "%EXTRACT_DIR%\opencode" "%INSTALL_DIR%\opencode.exe" >nul
)
del /q "%TEMP%\opencode-install.zip" 2>nul
rmdir /s /q "%EXTRACT_DIR%" 2>nul

rem ---- 验证 ----
"%INSTALL_DIR%\opencode.exe" --version
if errorlevel 1 (
    echo   ERROR: installed binary failed to run.
    exit /b 1
)

rem ---- 写入用户 PATH（幂等，保留 REG_EXPAND_SZ）----
set "BIN_DIR=%INSTALL_DIR%"
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
echo   OpenCode installed: %INSTALL_DIR%\opencode.exe
echo   Reopen the terminal, then run: opencode
endlocal
exit /b 0
