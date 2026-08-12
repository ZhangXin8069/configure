@echo off
rem Install opencode (Windows x64) from GitHub releases into %USERPROFILE%\.opencode\bin
rem Usage: install.bat [VERSION]   (default: latest)

setlocal EnableExtensions EnableDelayedExpansion

title OpenCode Installer

echo ============================================================
echo   OpenCode Installer (Windows)
echo ============================================================
echo.

rem ---- 架构检测 ----
set "PROC_ARCH=%PROCESSOR_ARCHITECTURE%"
if defined PROCESSOR_ARCHITEW6432 set "PROC_ARCH=%PROCESSOR_ARCHITEW6432%"
if /i "%PROC_ARCH%"=="ARM64" (
    echo   ERROR: opencode does not support Windows ARM64 yet.
    exit /b 1
)
if /i "%PROC_ARCH%"=="x86" (
    echo   ERROR: opencode does not support 32-bit Windows.
    exit /b 1
)

rem ---- AVX2 检测（老 CPU 用 baseline 构建）----
set "TARGET=windows-x64"
set "HAS_AVX2="
for /f "delims=" %%i in ('powershell -NoProfile -NonInteractive -Command "(Add-Type -MemberDefinition '[DllImport(""kernel32.dll"")] public static extern bool IsProcessorFeaturePresent(int ProcessorFeature);' -Name Kernel32 -Namespace Win32 -PassThru)::IsProcessorFeaturePresent(40)" 2^>nul') do set "HAS_AVX2=%%i"
if /i not "%HAS_AVX2%"=="True" if not "%HAS_AVX2%"=="1" (
    echo   CPU without AVX2 detected - using baseline build.
    set "TARGET=windows-x64-baseline"
)

rem ---- 版本解析 / 下载地址 ----
set "VER=%~1"
set "FILENAME=opencode-%TARGET%.zip"
set "URL=https://github.com/anomalyco/opencode/releases/latest/download/%FILENAME%"
if not "%VER%"=="" (
    set "URL=https://github.com/anomalyco/opencode/releases/download/v%VER%/%FILENAME%"
)

echo   Version: %VER%   (empty = latest)
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
if not exist "%USERPROFILE%\.opencode\bin" mkdir "%USERPROFILE%\.opencode\bin"
if exist "%EXTRACT_DIR%\opencode.exe" (
    move /y "%EXTRACT_DIR%\opencode.exe" "%USERPROFILE%\.opencode\bin\opencode.exe" >nul
) else (
    move /y "%EXTRACT_DIR%\opencode" "%USERPROFILE%\.opencode\bin\opencode.exe" >nul
)
del /q "%TEMP%\opencode-install.zip" 2>nul
rmdir /s /q "%EXTRACT_DIR%" 2>nul

rem ---- 验证 ----
"%USERPROFILE%\.opencode\bin\opencode.exe" --version
if errorlevel 1 (
    echo   ERROR: installed binary failed to run.
    exit /b 1
)

rem ---- 写入用户 PATH（幂等，保留 REG_EXPAND_SZ）----
set "BIN_DIR=%USERPROFILE%\.opencode\bin"
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
echo   OpenCode installed: %USERPROFILE%\.opencode\bin\opencode.exe
echo   Reopen the terminal, then run: opencode
endlocal
exit /b 0
