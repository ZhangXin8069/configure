@echo off
rem Install DeepSeek Harness CLI (dsh) (Windows) via npm global.
rem TUI (@deepseek-harness-tui/dsh-tui) is installed alongside by default.
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
set "TUI_PKG=@deepseek-harness-tui/dsh-tui"

rem npm 11+ 默认拦截依赖的 install-time 脚本（node-pty/koffi/sharp 等）；能力探测后按需传入
set "ALLOW_SCRIPTS="
npm install --help 2>nul | findstr /c:"--allow-scripts" >nul
if not errorlevel 1 set "ALLOW_SCRIPTS=--allow-scripts=@deepseek-ai/dsh-subprocess-local,koffi,node-pty,@google/genai,protobufjs,sharp"

if not "%VER%"=="" (
    echo   Installing %PKG%@%VER% ...
    call npm install -g %ALLOW_SCRIPTS% "%PKG%@%VER%"
) else (
    echo   Installing %PKG%@latest ...
    call npm install -g %ALLOW_SCRIPTS% "%PKG%@latest"
)
if errorlevel 1 (
    echo   ERROR: npm install failed.
    exit /b 1
)

rem ---- TUI 配套安装（失败不阻断，dsh 本体已可用） ----
echo   Installing TUI %TUI_PKG%@latest ...
call npm install -g %ALLOW_SCRIPTS% "%TUI_PKG%@latest"
if errorlevel 1 (
    echo   WARNING: TUI install failed; dsh itself is installed.
    echo            Retry later: npm install -g %TUI_PKG%
)

rem ---- 验证 ----
where dsh >nul 2>nul
if errorlevel 1 (
    echo   ERROR: dsh not found after install (npm global bin not on PATH?).
    exit /b 1
)
call dsh --version

where dsh-tui >nul 2>nul
if errorlevel 1 (
    echo   WARNING: dsh-tui not found on PATH after install.
) else (
    echo   TUI command ready: dsh-tui / dst
)

echo.
echo   DeepSeek Harness installed via npm. Reopen the terminal, then run: dsh-tui
echo   First run initializes the dsh-tui profile; it needs pnpm if missing: npm install -g pnpm
echo   Web UI alternative: dsh web
echo   Configure the DeepSeek API key in the TUI /settings or Web UI Settings - Models,
echo   or run config.sh on WSL/Git Bash.
endlocal
exit /b 0
