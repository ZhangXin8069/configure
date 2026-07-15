#!/usr/bin/env bash
# xx99 工作站连接脚本
# 功能: 确保 ZeroTier 在线, 然后 SSH 连接到 x99 工作站
# 目标: 172.25.193.104:22 (x99 局域网 IP, 通过 ZeroTier 路由可达)
# 前置: 需先运行 zerotier_init.sh 加入 ZeroTier 网络
#
# 用法: bash xx99.sh [ssh 额外参数]

set -euo pipefail

_PATH=$(
    cd "$(dirname "$0")"
    pwd
)
_NAME=$(basename "$0")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

readonly TARGET_HOST="172.25.193.104"
readonly SSH_PORT="${SSH_PORT:-22}"
readonly SSH_USER="${SSH_USER:-kfutfd}"

# ──────────────────────────────────────────────
# 1. 确保 zerotier-cli 可用
# ──────────────────────────────────────────────
if ! command -v zerotier-cli &>/dev/null; then
    echo "[ERROR] 未检测到 zerotier-cli, 请先运行 zerotier_init.sh 安装 ZeroTier"
    echo "  sudo bash ${_PATH}/zerotier_init.sh"
    exit 1
fi

# ──────────────────────────────────────────────
# 2. 如果 ZeroTier 未运行, 尝试启动
# ──────────────────────────────────────────────
if zerotier-cli status 2>/dev/null | grep -q 'ONLINE'; then
    echo "[INFO] ZeroTier 已在线"
else
    echo "[STEP] ZeroTier 未运行, 尝试启动..."

    if [[ $EUID -ne 0 ]]; then
        echo "[WARN] 启动 ZeroTier 需要 root 权限, 将尝试 sudo..."
        if ! sudo -n true 2>/dev/null; then
            _OS_NAME="$(uname -s)"
            if [[ "${_OS_NAME}" == "Darwin" ]]; then
                echo "[WARN] 无免密 sudo 权限, 跳过 ZeroTier 启动"
                echo "  请手动启动: sudo zerotier-one -d"
                echo "  或通过 launchd: sudo launchctl load /Library/LaunchDaemons/com.zerotier.zerotier-one.plist"
                echo "  将继续尝试 SSH 连接..."
                _SUDO=""
            else
                echo "[ERROR] 无免密 sudo 权限, 请手动启动:"
                echo "  sudo systemctl start zerotier-one"
                echo "  或"
                echo "  sudo zerotier-one -d"
                exit 1
            fi
        else
            _SUDO="sudo"
        fi
    else
        _SUDO=""
    fi

    # 尝试 systemd / service / 手动
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

    # 等待上线
    for i in $(seq 1 15); do
        if zerotier-cli status 2>/dev/null | grep -q 'ONLINE'; then
            echo "[OK] ZeroTier 已上线"
            break
        fi
        sleep 1
    done

    if ! zerotier-cli status 2>/dev/null | grep -q 'ONLINE'; then
        _OS_NAME="$(uname -s)"
        if [[ "${_OS_NAME}" == "Darwin" ]]; then
            echo "[WARN] ZeroTier 启动失败或未运行"
            echo "  请手动排查: zerotier-cli status"
            echo "  或: sudo zerotier-one -d"
            echo "  将继续尝试 SSH 连接..."
        else
            echo "[ERROR] ZeroTier 启动失败, 请手动排查"
            echo "  sudo systemctl status zerotier-one"
            echo "  zerotier-cli status"
            exit 1
        fi
    fi
fi

# ──────────────────────────────────────────────
# 3. 连通性检查 (可选, 非致命)
# ──────────────────────────────────────────────
echo "[INFO] 检测到 ${TARGET_HOST} 的连通性..."
if ping -c 1 -W 2 "${TARGET_HOST}" &>/dev/null; then
    echo "[OK] ${TARGET_HOST} 可达"
else
    echo "[WARN] ${TARGET_HOST} ping 不通, 但仍尝试 SSH 连接"
    echo "  (可能对方禁 ping, 或 ZeroTier 路由尚未建立)"
fi

# ──────────────────────────────────────────────
# 4. SSH 连接
# ──────────────────────────────────────────────
echo "[STEP] SSH 连接 ${SSH_USER}@${TARGET_HOST}:${SSH_PORT} ..."
echo ""

# 传递额外参数 (如 -p 端口等)
ssh -p "${SSH_PORT}" "${SSH_USER}@${TARGET_HOST}" "$@"

echo ""
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
