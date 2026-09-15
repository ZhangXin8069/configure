@echo off
rem Install DeepSeek Harness CLI (dsh) (Windows) via npm global
rem Usage: install.bat [VERSION]   (default: latest)

setlocal EnableExtensions EnableDelayedExpansion

title DeepSeek Harness Installer

echo ============================================================
echo   DeepSeek Harness Installer (Windows, npm)
echo ============================================================
echo.

rem ---- node / npm 检查 ----
where node >nul 2>nul
if errorlevel 1 (
    echo   ERROR: Node.js not found. Install Node.js first: https://nodejs.org/
    echo   Recommended: Node.js 22.19+ or 24+
    exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
    echo   ERROR: npm not found. Reinstall Node.js LTS: https://nodejs.org/
    exit /b 1
)

rem ---- 版本解析 / 安装 ----
set "VER=%~1"
set "PKG=@deepseek-ai/dsh"
if not "%VER%"=="" (
    echo   Installing %PKG%@%VER% ...
    call npm install -g "%PKG%@%VER%"
) else (
    echo   Installing %PKG%@latest ...
    call npm install -g "%PKG%@latest"
)
if errorlevel 1 (
    echo   ERROR: npm install failed.
    exit /b 1
)

rem ---- 验证 ----
where dsh >nul 2>nul
if errorlevel 1 (
    echo   ERROR: dsh not found after install (npm global bin not on PATH?).
    exit /b 1
)
call dsh --version

echo.
echo   DeepSeek Harness installed via npm. Reopen the terminal, then run: dsh web
echo   Configure the DeepSeek API key in Settings - Models, or run config.sh on WSL/Git Bash.
endlocal
exit /b 0
