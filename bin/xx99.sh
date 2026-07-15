#!/usr/bin/env bash
# xx99.sh — X99 工作站一键连接 (ZeroTier + SSH + ddocker)
#
# 功能:
#   1. 确保 ZeroTier 在线 (自动启动)
#   2. SSH 连接到 x99 工作站 (172.25.193.104)
#   3. 自动运行 ddocker.bat 进入 Docker 容器
#
# 用法:
#   bash xx99.sh              默认: SSH → 自动执行 ddocker.bat
#   bash xx99.sh --no-ddocker  仅 SSH，不运行 ddocker
#   bash xx99.sh -- <cmd>      仅 SSH，执行自定义命令
#
# 前置: 需先运行 zerotier_init.sh 加入 ZeroTier 网络

set -euo pipefail

_PATH=$(cd "$(dirname "$0")" && pwd)
_NAME=$(basename "$0")
echo "### ${_NAME} started : $(date "+%Y-%m-%d-%H-%M-%S") ###"

readonly TARGET_HOST="172.25.193.104"
readonly SSH_PORT="${SSH_PORT:-22}"
readonly SSH_USER="${SSH_USER:-kfutfd}"

# 远程 Windows 上 ddocker.bat 路径 (相对于用户 HOME)
readonly REMOTE_DDOCKER="${REMOTE_DDOCKER:-configure\\bin\\ddocker.bat}"

# ── 解析参数 ──
AUTO_DDOCKER=true
SSH_EXTRA=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-ddocker)
            AUTO_DDOCKER=false
            shift
            ;;
        --)
            shift
            SSH_EXTRA=("$@")
            break
            ;;
        *)
            SSH_EXTRA+=("$1")
            shift
            ;;
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

    # 尝试 systemd / service / 手动启动
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

    # 等待上线，最多 15 秒
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
            echo "  zerotier-cli status"
            exit 1
        fi
    fi
fi

# ──────────────────────────────────────────────
# 3. 连通性检查 (快速，非阻塞)
# ──────────────────────────────────────────────
if ping -c 1 -W 2 "${TARGET_HOST}" &>/dev/null; then
    echo "[OK] ${TARGET_HOST} 可达"
else
    echo "[WARN] ${TARGET_HOST} ping 不通，仍尝试 SSH..."
fi

# ──────────────────────────────────────────────
# 4. SSH 连接
# ──────────────────────────────────────────────
echo ""

if [[ "$AUTO_DDOCKER" == true && ${#SSH_EXTRA[@]} -eq 0 ]]; then
    echo "[STEP] SSH → ${SSH_USER}@${TARGET_HOST} → ${REMOTE_DDOCKER}"
    echo ""
    # -t 强制分配 TTY，docker exec -it 需要
    ssh -t -p "${SSH_PORT}" "${SSH_USER}@${TARGET_HOST}" "${REMOTE_DDOCKER}"
elif [[ ${#SSH_EXTRA[@]} -gt 0 ]]; then
    echo "[STEP] SSH → ${SSH_USER}@${TARGET_HOST}，执行: ${SSH_EXTRA[*]}"
    echo ""
    ssh -t -p "${SSH_PORT}" "${SSH_USER}@${TARGET_HOST}" "${SSH_EXTRA[@]}"
else
    echo "[STEP] SSH → ${SSH_USER}@${TARGET_HOST} (交互模式)"
    echo ""
    ssh -p "${SSH_PORT}" "${SSH_USER}@${TARGET_HOST}"
fi

echo ""
echo "### ${_NAME} done : $(date "+%Y-%m-%d-%H-%M-%S") ###"
