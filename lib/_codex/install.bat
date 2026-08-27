@echo off
rem Install Codex CLI (Windows x64) via npm into the global npm bin directory
rem Usage: install.bat [VERSION]   (default: latest)

setlocal EnableExtensions EnableDelayedExpansion

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

rem ---- 版本解析 / 安装 ----
set "VER=%~1"
set "PKG=@openai/codex"
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
where codex >nul 2>nul
if errorlevel 1 (
    echo   ERROR: codex not found after install (npm global bin not on PATH?).
    exit /b 1
)
call codex --version

echo.
echo   Codex installed via npm. Reopen the terminal, then run: codex login
endlocal
exit /b 0