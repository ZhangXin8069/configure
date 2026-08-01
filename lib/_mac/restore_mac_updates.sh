#!/bin/bash
# ============================================================
# 恢复 macOS 自动更新的默认设置
# 需要 sudo 权限
# ============================================================

set -e

if [ "$EUID" -ne 0 ]; then
    echo "This script requires sudo. Please re-run with:"
    echo "  sudo bash $0"
    exit 1
fi

echo "========================================"
echo "  Restore macOS Auto Update Defaults"
echo "========================================"
echo ""

echo "[1/5] Re-enabling automatic update check..."
softwareupdate --schedule on
defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticCheckEnabled -bool true
echo "  ✓ Done"

echo "[2/5] Re-enabling automatic download..."
defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticDownload -bool true
echo "  ✓ Done"

echo "[3/5] Re-enabling automatic macOS upgrades..."
defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates -bool true
echo "  ✓ Done"

echo "[4/5] Re-enabling auto-restart..."
defaults write /Library/Preferences/com.apple.SoftwareUpdate RestartRequired -bool true
echo "  ✓ Done"

echo "[5/5] Keeping critical/security updates ON..."
defaults write /Library/Preferences/com.apple.SoftwareUpdate CriticalUpdateInstall -bool true
defaults write /Library/Preferences/com.apple.SoftwareUpdate ConfigDataInstall -bool true
echo "  ✓ Done"

echo ""
echo "========================================"
echo "  All auto-update defaults restored."
echo "  A reboot is recommended."
echo "========================================"
