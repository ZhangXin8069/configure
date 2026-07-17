#!/usr/bin/env bash
# xx99.sh — X99 工作站一键连接 (ZeroTier + SSH → ddocker)
#
# 功能: 确保 ZeroTier 在线 → SSH 到 x99 → 自动运行 ddocker.bat
# 目标: 172.25.193.104:22 (x99 局域网 IP, ZeroTier 路由)
#
# 用法: bash xx99.sh [-n]
#   -n  跳过 ddocker，直接 SSH 到 x99 终端
#
# 前置: 需先运行 zerotier_init.sh 加入 ZeroTier 网络

set -euo pipefail

_PATH=$(cd "$(dirname "$0")" && pwd)
_NAME=$(basename "$0")
echo "### ${_NAME} started : $(date "+%Y-%m-%d-%H-%M-%S") ###"

readonly TARGET_HOST="172.25.193.104"
readonly SSH_PORT="${SSH_PORT:-22}"
readonly SSH_USER="${SSH_USER:-kfutfd}"

# 解析命令行参数
NO_DDOCKER=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        -n) NO_DDOCKER=true; shift ;;
        *)  shift ;;
    esac
done

# ──────────────────────────────────────────────
# 1. 确保 zerotier-cli 可用
# ──────────────────────────────────────────────
if ! command -v zerotier-cli &>/dev/null; then
    echo "[ERROR] 未检测到 zerotier-cli，请先运行 zerotier_init.sh"
    echo "  sudo bash ${_PATH}/zerotier_init.sh"
    exit 1
fi

# ──────────────────────────────────────────────
# 2. 如果 ZeroTier 未运行，尝试启动
# ──────────────────────────────────────────────
if zerotier-cli status 2>/dev/null | grep -q 'ONLINE'; then
    echo "[OK] ZeroTier 在线"
else
    echo "[STEP] ZeroTier 未运行，尝试启动..."

    _SUDO=""
    if [[ $EUID -ne 0 ]]; then
        if sudo -n true 2>/dev/null; then
            _SUDO="sudo"
        elif [[ "$(uname -s)" == "Darwin" ]]; then
            echo "[WARN] 无免密 sudo，跳过自动启动（macOS 将继续尝试 SSH）"
        else
            echo "[ERROR] 无免密 sudo 权限，请手动启动 ZeroTier"
            echo "  sudo systemctl start zerotier-one"
            exit 1
        fi
    fi

    if command -v systemctl &>/dev/null && systemctl is-system-running &>/dev/null 2>&1; then
        ${_SUDO} systemctl start zerotier-one 2>/dev/null || true
    elif command -v service &>/dev/null; then
        ${_SUDO} service zerotier-one start 2>/dev/null || true
    else
        ${_SUDO} pkill zerotier-one 2>/dev/null || true
        sleep 1
        ${_SUDO} zerotier-one -d 2>/dev/null &
        sleep 2
    fi

    for i in $(seq 1 15); do
        if zerotier-cli status 2>/dev/null | grep -q 'ONLINE'; then
            echo "[OK] ZeroTier 已上线"
            break
        fi
        sleep 1
    done

    if ! zerotier-cli status 2>/dev/null | grep -q 'ONLINE'; then
        if [[ "$(uname -s)" == "Darwin" ]]; then
            echo "[WARN] ZeroTier 启动失败，继续尝试 SSH..."
        else
            echo "[ERROR] ZeroTier 启动失败"
            exit 1
        fi
    fi
fi

# ──────────────────────────────────────────────
# 3. 快速连通性检查
# ──────────────────────────────────────────────
if ping -c 1 -W 2 "${TARGET_HOST}" &>/dev/null; then
    echo "[OK] ${TARGET_HOST} 可达"
else
    echo "[WARN] ${TARGET_HOST} ping 不通，仍尝试 SSH..."
fi

# ──────────────────────────────────────────────
# 4. SSH → 自动运行 ddocker.bat（-n 跳过）
# ──────────────────────────────────────────────
echo ""
if [[ "${NO_DDOCKER}" == true ]]; then
    echo "[STEP] SSH → ${SSH_USER}@${TARGET_HOST}（跳过 ddocker）"
    echo ""
    ssh -t -p "${SSH_PORT}" "${SSH_USER}@${TARGET_HOST}"
else
    echo "[STEP] SSH → ${SSH_USER}@${TARGET_HOST} → ddocker.bat"
    echo ""
    # -t 强制分配 TTY（docker exec -it 需要）; 远程执行 ddocker.bat
    # ddocker.bat 退出后（成功退出容器或登入失败），始终退回 x99 SSH 终端，避免直接断开连接
    ssh -t -p "${SSH_PORT}" "${SSH_USER}@${TARGET_HOST}" \
        "ddocker.bat; echo ''; echo '[INFO] 已退出 ddocker，回到 x99 终端'; exec bash -l"
fi

echo ""
echo "### ${_NAME} done : $(date "+%Y-%m-%d-%H-%M-%S") ###"
