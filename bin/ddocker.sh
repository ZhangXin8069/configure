#!/bin/bash
#===========================================================================
# docker-connect-linux.sh  —  Linux 原生版
#
# 0. 检查 Docker CLI 是否安装，未安装则显示各发行版安装指引
# 1. 检测 Docker 是否运行，未运行则尝试启动 (systemd/SysV/OpenRC)
# 2. 找到最近创建的容器，未运行则启动
# 3. 在新终端窗口中进入该容器的交互式终端
#===========================================================================

set -e

# ── 颜色 ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_ok()   { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_err()  { echo -e "${RED}[ERR]${NC}   $*"; }
log_step() { echo -e "${CYAN}[STEP]${NC}  $*"; }

SETUP_URL="https://gitee.com/zhangxin8069/configure/raw/stab10/lib/_docker/setup.md"

print_docker_install_guide() {
    echo ""
    echo "  ============================================="
    echo "    Docker 安装指引 - Linux"
    echo "  ============================================="
    echo ""
    echo "  通用方式 (推荐):"
    echo "    curl -fsSL https://get.docker.com | sudo sh"
    echo ""
    echo "  Debian / Ubuntu:"
    echo "    sudo apt-get update && sudo apt-get install docker.io"
    echo ""
    echo "  CentOS / RHEL / Fedora:"
    echo "    sudo dnf install docker"
    echo ""
    echo "  Arch Linux:"
    echo "    sudo pacman -S docker"
    echo ""
    echo "  openSUSE:"
    echo "    sudo zypper install docker"
    echo ""
    echo "  Alpine:"
    echo "    sudo apk add docker"
    echo ""
    echo "  启动服务:"
    echo "    sudo systemctl enable docker --now   # systemd"
    echo "    sudo rc-update add docker boot       # OpenRC"
    echo ""
    echo "  添加用户到 docker 组 (免 sudo):"
    echo "    sudo usermod -aG docker \$USER"
    echo "    newgrp docker"
    echo "  ============================================="
    echo ""
}

# Helper: detect available shell in a container
detect_shell() {
    local container="$1"
    for s in bash sh ash; do
        if docker exec "$container" which "$s" &>/dev/null; then
            echo "$s" && return 0
        fi
    done
    for s in bash sh ash; do
        if docker exec "$container" test -x "/bin/$s" &>/dev/null; then
            echo "$s" && return 0
        fi
    done
    return 1
}

# Helper: start Docker daemon
start_docker_daemon() {
    local need_sudo=""
    if [ "$(id -u)" -ne 0 ]; then
        if groups "$USER" | grep -q docker; then
            need_sudo=""
        else
            need_sudo="sudo"
        fi
    fi

    if command -v systemctl &>/dev/null; then
        $need_sudo systemctl start docker
    elif command -v rc-service &>/dev/null; then
        $need_sudo rc-service docker start
    elif command -v service &>/dev/null; then
        $need_sudo service docker start
    else
        return 1
    fi
    return 0
}

# Helper: launch container in a new terminal window
launch_terminal() {
    local title="$1" container="$2" shell="$3"
    local cmd="echo 'Container: $container'; echo 'Shell: /bin/$shell'; echo; docker exec -it '$container' $shell"

    if command -v gnome-terminal &>/dev/null; then
        gnome-terminal --title="$title" -- bash -c "$cmd"
    elif command -v xfce4-terminal &>/dev/null; then
        xfce4-terminal --title="$title" --command "bash -c \"$cmd\""
    elif command -v konsole &>/dev/null; then
        konsole --new-tab --title "$title" -e bash -c "$cmd"
    elif command -v lxterminal &>/dev/null; then
        lxterminal --title="$title" --command "bash -c \"$cmd\""
    elif command -v xterm &>/dev/null; then
        xterm -title "$title" -e bash -c "$cmd" &
    elif command -v alacritty &>/dev/null; then
        alacritty --title "$title" -e bash -c "$cmd" &
    elif command -v kitty &>/dev/null; then
        kitty --title "$title" bash -c "$cmd" &
    elif command -v terminology &>/dev/null; then
        terminology --title "$title" -e bash -c "$cmd" &
    elif command -v foot &>/dev/null; then
        foot --title "$title" bash -c "$cmd" &
    else
        return 1
    fi
    return 0
}

# ──────────────────────────────────────────────────────────
# 步骤 0：检查 Docker CLI 是否安装
# ──────────────────────────────────────────────────────────
log_step "检查 Docker CLI..."

if ! command -v docker &>/dev/null; then
    log_err "Docker CLI 未找到，请先安装 Docker。"
    print_docker_install_guide
    echo ""
    read -p "Press Enter to exit..." _
    exit 1
fi
log_ok "Docker CLI 已就绪"
echo ""

# ──────────────────────────────────────────────────────────
# 步骤 1：确保 Docker 守护进程运行
# ──────────────────────────────────────────────────────────
log_step "检查 Docker 守护进程..."

if docker info &>/dev/null; then
    DOCKER_VER=$(docker info --format '{{.ServerVersion}}')
    log_ok "Docker 已在运行 (v$DOCKER_VER)"
elif docker version &>/dev/null; then
    DOCKER_VER=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "unknown")
    log_ok "Docker 已在运行 (v$DOCKER_VER)"
else
    log_warn "Docker 守护进程未运行，尝试启动..."

    if start_docker_daemon; then
        log_ok "已发送启动命令。"
    else
        log_err "无法识别 init 系统，请手动启动 Docker 后重试。"
        echo ""
        echo "  常见启动方式:"
        echo "    sudo systemctl start docker       # systemd"
        echo "    sudo service docker start         # SysV init"
        echo "    sudo rc-service docker start      # OpenRC"
        echo ""
        read -p "Press Enter to exit..." _
        exit 1
    fi

    # 等待就绪，最多 30 秒
    for i in $(seq 1 30); do
        if docker info &>/dev/null; then
            log_ok "Docker 已就绪。"
            break
        fi
        sleep 1
    done

    if ! docker info &>/dev/null; then
        log_err "Docker 启动超时，请手动排查。"
        echo ""
        read -p "Press Enter to exit..." _
        exit 1
    fi
fi
echo ""

# ──────────────────────────────────────────────────────────
# 步骤 2：找到最近创建的容器
# ──────────────────────────────────────────────────────────
log_step "查找最近创建的容器..."

LATEST=$(docker ps -a --format '{{.Names}}' --latest 2>/dev/null)

# Double-check via container ID
if [ -z "$LATEST" ]; then
    last_id=$(docker ps -aq --last 1 2>/dev/null)
    if [ -n "$last_id" ]; then
        LATEST=$(docker inspect -f '{{.Name}}' "$last_id" 2>/dev/null | sed 's|^/||')
    fi
fi

if [ -z "$LATEST" ]; then
    log_err "本地没有任何容器。"
    echo ""
    echo "  ============================================="
    echo "    快速上手"
    echo "  ============================================="
    echo ""

    if [ -n "$(docker images -q 2>/dev/null)" ]; then
        echo "  本地已有镜像，执行以下命令创建并进入容器:"
        echo ""
        echo "  1. 查看本地镜像:"
        echo "    docker images"
        echo ""
        echo "  2. 创建容器 (以 ubuntu 为例):"
        echo "    docker run -d --name my-ubuntu ubuntu tail -f /dev/null"
        echo ""
        echo "  3. 再次运行本脚本即可自动连接。"
    else
        echo "  你的机器上还没有任何 Docker 镜像或容器。"
        echo "  按以下步骤开始:"
        echo ""
        echo "  第 1 步 - 拉取镜像 (任选一个):"
        echo "    docker pull alpine        # ~5MB, 最轻量"
        echo "    docker pull ubuntu        # ~78MB, 常用"
        echo "    docker pull debian        # ~124MB"
        echo ""
        echo "  第 2 步 - 创建后台容器:"
        echo "    docker run -d --name test alpine tail -f /dev/null"
        echo ""
        echo "  第 3 步 - 再次运行本脚本即可自动连接。"
        echo ""
        echo "  详细配置和更多镜像请参考:"
        echo "    $SETUP_URL"
    fi
    echo ""
    echo "  ============================================="
    echo ""
    read -p "Press Enter to exit..." _
    exit 1
fi

log_ok "最近创建的容器: ${GREEN}$LATEST${NC}"
echo ""

# ──────────────────────────────────────────────────────────
# 步骤 3：确保容器在运行
# ──────────────────────────────────────────────────────────
STATUS=$(docker inspect -f '{{.State.Status}}' "$LATEST" 2>/dev/null)

if [ "$STATUS" = "running" ]; then
    log_ok "容器 $LATEST 已在运行。"
else
    log_warn "容器 $LATEST 状态为 $STATUS，正在启动..."
    if ! docker start "$LATEST"; then
        log_err "容器启动失败。检查: docker logs \"$LATEST\""
        echo ""
        read -p "Press Enter to exit..." _
        exit 1
    fi
    log_ok "容器已启动。"
fi
echo ""

# ──────────────────────────────────────────────────────────
# 步骤 4：进入容器终端（新窗口）
# ──────────────────────────────────────────────────────────
log_step "检测容器内可用的 shell..."

CONTAINER_SHELL=$(detect_shell "$LATEST")

if [ -z "$CONTAINER_SHELL" ]; then
    log_err "容器内没有 bash / sh / ash，无法进入终端。"
    echo ""
    read -p "Press Enter to exit..." _
    exit 1
fi

log_ok "找到 /bin/$CONTAINER_SHELL"
log_step "在新窗口中打开容器终端..."

if ! launch_terminal "Docker: $LATEST" "$LATEST" "$CONTAINER_SHELL"; then
    # No GUI terminal found — fall back to in-place execution
    log_warn "未检测到 GUI 终端模拟器，在当前终端中进入容器。"
    echo ""
    echo "  Container: $LATEST"
    echo "  Shell:     /bin/$CONTAINER_SHELL"
    echo ""
    exec docker exec -it "$LATEST" "$CONTAINER_SHELL"
fi

echo ""
log_ok "容器终端已在新窗口中打开。"
log_ok "可以关闭此启动器窗口。"
exit 0
