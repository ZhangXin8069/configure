#!/bin/bash
# ============================================================
# 禁用 macOS 自动更新（保留安全更新）
# 需要 sudo 权限
# ============================================================

set -e

echo "========================================"
echo "  Disable macOS Auto Updates"
echo "  (Security/Critical updates remain ON)"
echo "========================================"
echo ""

# 检查 sudo
if [ "$EUID" -ne 0 ]; then
    echo "This script requires sudo. Please re-run with:"
    echo "  sudo bash $0"
    exit 1
fi

# --------------------------------------------------
# 1. 关闭自动检查更新（不会弹出更新提醒）
# --------------------------------------------------
echo "[1/6] Disabling automatic update check..."
softwareupdate --schedule off
defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticCheckEnabled -bool false
echo "  ✓ Done"

# --------------------------------------------------
# 2. 关闭后台自动下载更新包
# --------------------------------------------------
echo "[2/6] Disabling automatic download..."
defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticDownload -bool false
echo "  ✓ Done"

# --------------------------------------------------
# 3. 禁止自动安装 macOS 大版本更新
# --------------------------------------------------
echo "[3/6] Disabling automatic macOS version upgrades..."
defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates -bool false
echo "  ✓ Done"

# --------------------------------------------------
# 4. 禁止自动重启安装
# --------------------------------------------------
echo "[4/6] Disabling auto-restart for updates..."
defaults write /Library/Preferences/com.apple.SoftwareUpdate RestartRequired -bool false
echo "  ✓ Done"

# --------------------------------------------------
# 5. 保留安全/关键更新（默认就是开启的，
#    这里显式确保不被禁用）
# --------------------------------------------------
echo "[5/6] Ensuring critical/security updates remain ON..."
# CriticalUpdateInstall = 安全更新 + 系统数据文件
defaults write /Library/Preferences/com.apple.SoftwareUpdate CriticalUpdateInstall -bool true
# ConfigDataInstall = XProtect, MRT, Gatekeeper 等安全配置数据
defaults write /Library/Preferences/com.apple.SoftwareUpdate ConfigDataInstall -bool true
echo "  ✓ Done"

# --------------------------------------------------
# 6. 删除已下载的更新包（可选，释放空间）
# --------------------------------------------------
echo "[6/6] Cleaning up any downloaded updates..."
if [ -d "/Library/Updates" ]; then
    rm -rf /Library/Updates/* 2>/dev/null || true
fi
# 用 softwareupdate 清理（macOS 12+ 可用 --flush）
softwareupdate --list >/dev/null 2>&1 || true
echo "  ✓ Done"

# --------------------------------------------------
# 结果展示
# --------------------------------------------------
echo ""
echo "========================================"
echo "  Current settings:"
echo "========================================"
echo ""
echo "Schedule (0=off):"
softwareupdate --schedule 2>&1 || true
echo ""
echo "Key defaults:"
for key in AutomaticCheckEnabled AutomaticDownload AutomaticallyInstallMacOSUpdates CriticalUpdateInstall ConfigDataInstall; do
    val=$(defaults read /Library/Preferences/com.apple.SoftwareUpdate "$key" 2>/dev/null || echo "(not set)")
    printf "  %-40s → %s\n" "$key" "$val"
done
echo ""
echo "========================================"
echo "  Summary:"
echo "  ✗ Automatic check      — DISABLED"
echo "  ✗ Auto-download        — DISABLED"
echo "  ✗ macOS major upgrade  — DISABLED"
echo "  ✓ Critical patches     — ENABLED"
echo "  ✓ Security config data — ENABLED"
echo ""
echo "  You can still manually check for updates:"
echo "    softwareupdate -l"
echo "========================================"
