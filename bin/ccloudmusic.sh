#!/usr/bin/env bash
# CloudMusic Connect: launches NetEase CloudMusic on Windows (WSL) / macOS / Linux
# ============================================================================
# Step 1: Check if CloudMusic is already running
# Step 2: Find the executable
# Step 3: Launch it
# ============================================================================
set -euo pipefail

echo "============================================================"
echo "  CloudMusic Connect"
echo "============================================================"
echo

pause() { read -r -p "Press Enter to continue..."; }

# ── Detect platform ──────────────────────────────────────────────────────────

OS="$(uname -s)"

# ── Step 1: Check if already running ─────────────────────────────────────────

echo "[1/3] Checking CloudMusic..."

RUNNING=0

case "${OS}" in
    Darwin)
        if pgrep -x "cloudmusic" &>/dev/null || pgrep -f "NetEaseMusic" &>/dev/null; then
            RUNNING=1
        fi
        ;;
    Linux)
        # WSL: check via tasklist.exe
        if command -v tasklist.exe &>/dev/null; then
            if tasklist.exe 2>/dev/null | grep -iq "cloudmusic"; then
                RUNNING=1
            fi
        else
            if pgrep -x "cloudmusic" &>/dev/null; then
                RUNNING=1
            fi
        fi
        ;;
esac

if (( RUNNING == 1 )); then
    echo "       CloudMusic is already running."
    echo "============================================================"
    echo
    exit 0
fi

echo "       Not running."
echo

# ── Step 2: Find executable ──────────────────────────────────────────────────

echo "[2/3] Finding CloudMusic executable..."

CM_EXE=""

case "${OS}" in
    Darwin)
        # Check common macOS paths
        for p in \
            "/Applications/NeteaseMusic.app" \
            "$HOME/Applications/NeteaseMusic.app"; do
            if [[ -d "$p" ]]; then
                CM_EXE="$p"
                break
            fi
        done
        ;;
    Linux)
        if command -v tasklist.exe &>/dev/null; then
            # WSL: find Windows executable via PowerShell
            if command -v powershell.exe &>/dev/null; then
                CM_EXE=$(powershell.exe -NoProfile -Command "
                    \$paths = @(
                        'C:\Program Files\NetEase\CloudMusic\cloudmusic.exe',
                        \"\$env:ProgramFiles\NetEase\CloudMusic\cloudmusic.exe\"
                    )
                    foreach (\$p in \$paths) { if (Test-Path \$p) { Write-Output \$p; exit 0 } }
                    try {
                        \$r = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\cloudmusic.exe' -EA SilentlyContinue
                        if (\$r) { Write-Output \$r.'(default)' }
                    } catch {}
                " 2>/dev/null | tr -d '\r')
            fi
        else
            # Native Linux
            if command -v netease-cloud-music &>/dev/null; then
                CM_EXE="netease-cloud-music"
            elif [[ -x "/opt/netease/netease-cloud-music/netease-cloud-music.bash" ]]; then
                CM_EXE="/opt/netease/netease-cloud-music/netease-cloud-music.bash"
            fi
        fi
        ;;
esac

if [[ -z "${CM_EXE}" ]]; then
    echo "[FAIL] CloudMusic executable not found."
    echo
    echo "  Install NetEase CloudMusic:"
    echo "    https://music.163.com/"
    echo
    pause
    exit 1
fi

echo "       Found: ${CM_EXE}"
echo

# ── Step 3: Launch ───────────────────────────────────────────────────────────

echo "[3/3] Launching CloudMusic..."

case "${OS}" in
    Darwin)
        open "${CM_EXE}"
        ;;
    Linux)
        if command -v tasklist.exe &>/dev/null; then
            # WSL: launch Windows executable
            if command -v cmd.exe &>/dev/null; then
                cmd.exe /c start "" "$(wslpath -w "${CM_EXE}" 2>/dev/null || echo "${CM_EXE}")"
            else
                "${CM_EXE}" &>/dev/null &
            fi
        else
            nohup "${CM_EXE}" &>/dev/null &
        fi
        ;;
esac

# Wait for it to appear (max 30s)
for (( n = 0; n < 30; n++ )); do
    sleep 1
    case "${OS}" in
        Darwin)
            pgrep -x "cloudmusic" &>/dev/null && break
            pgrep -f "NetEaseMusic" &>/dev/null && break
            ;;
        Linux)
            if command -v tasklist.exe &>/dev/null; then
                tasklist.exe 2>/dev/null | grep -iq "cloudmusic" && break
            else
                pgrep -x "cloudmusic" &>/dev/null && break
            fi
            ;;
    esac
done

echo "       CloudMusic launched."
echo "============================================================"
echo
