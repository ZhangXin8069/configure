#!/usr/bin/env bash
# ZeroTier 初始化脚本
# 功能: 安装 ZeroTier One, 启动服务, 加入虚拟局域网, 设置 orbit 卫星节点
# 网络: Network ID = 48d6023c464e0a5c
# Orbit: 240f181d35 (卫星/中转节点, 加速 NAT 穿透)
# 服务端: https://my.zerotier.com → Members → 勾选 Auth 授权本节点
#
# 兼容: Linux (systemd/sysvinit/容器/WSL), macOS (brew/launchd)
#
# 用法: sudo bash zerotier_init.sh
#  或切换到 root 后: bash zerotier_init.sh

set -euo pipefail

_PATH=$(
    cd "$(dirname "$0")"
    pwd
)
_NAME=$(basename "$0")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

readonly NETWORK_ID="48d6023c464e0a5c"
readonly ORBIT_ID="240f181d35"

# ──────────────────────────────────────────────
# 0. 平台 & 权限检查
# ──────────────────────────────────────────────
_OS="unknown"
case "$(uname -s)" in
    Linux)  _OS="linux"  ;;
    Darwin) _OS="macos"  ;;
    *)
        echo "[ERROR] 不支持的操作系统: $(uname -s)"
        exit 1
        ;;
esac
echo "[INFO] 操作系统: $(uname -s) ($(uname -m))"

if [[ $EUID -ne 0 ]]; then
    echo "[ERROR] 该脚本必须以 root 运行 (需要安装软件包和启动系统服务)"
    echo "  请执行: sudo bash ${_NAME}"
    exit 1
fi

# ──────────────────────────────────────────────
# 1. 环境探测
# ──────────────────────────────────────────────
_IS_SYSTEMD=false
_IS_LAUNCHD=false
_IS_CONTAINER=false
_START_METHOD=""

_detect_init() {
    if [[ "${_OS}" == "macos" ]]; then
        _IS_LAUNCHD=true
        _START_METHOD="launchd"
        echo "[INFO] 检测到 macOS launchd 环境"
        return
    fi

    # Linux 环境检测
    local _pid1
    _pid1=$(ps -p 1 -o comm= 2>/dev/null || true)
    if [[ "${_pid1}" == "systemd" ]]; then
        _IS_SYSTEMD=true
        _START_METHOD="systemd"
        echo "[INFO] 检测到 systemd 环境 (PID 1 = systemd)"
        return
    fi

    if grep -qE 'docker|kubepods|containerd' /proc/1/cgroup 2>/dev/null || \
       [[ -f /.dockerenv ]] || \
       [[ -f /run/.containerenv ]]; then
        _IS_CONTAINER=true
        _START_METHOD="manual"
        echo "[INFO] 检测到容器环境"
        return
    fi

    if [[ -f /proc/sys/fs/binfmt_misc/WSLInterop ]]; then
        if systemctl is-system-running &>/dev/null 2>&1; then
            _IS_SYSTEMD=true
            _START_METHOD="systemd"
            echo "[INFO] 检测到 WSL (systemd 已启用)"
        else
            _IS_CONTAINER=true
            _START_METHOD="manual"
            echo "[INFO] 检测到 WSL (systemd 未启用, 使用手动模式)"
        fi
        return
    fi

    if command -v service &>/dev/null; then
        _START_METHOD="sysvinit"
        echo "[INFO] 检测到 sysvinit / upstart 环境"
        return
    fi

    _START_METHOD="manual"
    echo "[INFO] 未检测到标准 init 系统, 使用手动模式"
}
_detect_init

# ──────────────────────────────────────────────
# 2. 检查是否已安装并加入网络
# ──────────────────────────────────────────────
_ALREADY_JOINED=false
if command -v zerotier-cli &>/dev/null; then
    echo "[INFO] 检测到 zerotier-cli 已安装"

    if zerotier-cli listnetworks 2>/dev/null | grep -q "${NETWORK_ID}"; then
        _STATUS=$(zerotier-cli listnetworks 2>/dev/null | grep "${NETWORK_ID}" | awk '{print $4}')
        echo "[INFO] 已加入网络 ${NETWORK_ID}, 当前状态: ${_STATUS}"
        _ALREADY_JOINED=true
    fi
fi

# ──────────────────────────────────────────────
# 3. 安装 ZeroTier One
# ──────────────────────────────────────────────
_install_zerotier() {
    echo "[STEP] 安装 ZeroTier One..."

    if [[ "${_OS}" == "macos" ]]; then
        if command -v brew &>/dev/null; then
            echo "[INFO] 使用 Homebrew 安装..."
            brew install zerotier-one
        else
            echo "[ERROR] macOS 需要 Homebrew (https://brew.sh) 或手动下载 pkg"
            echo "  安装 Homebrew 后重试, 或访问: https://www.zerotier.com/download/"
            exit 1
        fi

    elif command -v apt-get &>/dev/null; then
        echo "[INFO] 检测到 apt-get, 使用官方源安装..."
        if command -v gpg &>/dev/null; then
            curl -fsSL https://raw.githubusercontent.com/zerotier/ZeroTierOne/master/doc/contact%40zerotier.com.gpg 2>/dev/null | \
                gpg --dearmor -o /usr/share/keyrings/zerotier-archive-keyring.gpg 2>/dev/null || true
        fi
        local _codename
        _codename=$(lsb_release -cs 2>/dev/null || echo 'bookworm')
        echo "deb [signed-by=/usr/share/keyrings/zerotier-archive-keyring.gpg] http://download.zerotier.com/debian/${_codename} ${_codename} main" \
            > /etc/apt/sources.list.d/zerotier.list 2>/dev/null || true
        apt-get update -qq 2>/dev/null
        DEBIAN_FRONTEND=noninteractive apt-get install -y -qq zerotier-one 2>&1 | \
            grep -vE '(invoke-rc.d|policy-rc.d|debconf:)' || true

    elif command -v dnf &>/dev/null; then
        echo "[INFO] 检测到 dnf, 使用官方 RPM 安装..."
        dnf install -y https://download.zerotier.com/redhat/el/8/x86_64/zerotier-one-latest.rpm 2>&1 | grep -v '^$' || true

    elif command -v yum &>/dev/null; then
        echo "[INFO] 检测到 yum, 使用官方 RPM 安装..."
        yum install -y https://download.zerotier.com/redhat/el/7/x86_64/zerotier-one-latest.rpm 2>&1 | grep -v '^$' || true

    elif command -v zypper &>/dev/null; then
        echo "[INFO] 检测到 zypper, 使用官方 RPM 安装..."
        zypper --non-interactive install -y https://download.zerotier.com/redhat/el/8/x86_64/zerotier-one-latest.rpm 2>&1 | grep -v '^$' || true

    elif command -v pacman &>/dev/null; then
        echo "[INFO] 检测到 pacman, 使用社区源安装..."
        pacman -S --noconfirm zerotier-one 2>&1 | grep -v '^$' || true

    else
        echo "[INFO] 使用官方一键安装脚本..."
        if ! command -v curl &>/dev/null; then
            echo "[ERROR] 需要 curl 才能在线安装 ZeroTier, 请手动安装"
            exit 1
        fi
        curl -s https://install.zerotier.com | bash
    fi

    if ! command -v zerotier-cli &>/dev/null; then
        echo "[ERROR] ZeroTier 安装失败, 请检查网络或手动安装"
        exit 1
    fi
    echo "[OK] ZeroTier One 安装完成"
}

if [[ "${_ALREADY_JOINED}" == false ]]; then
    _install_zerotier
fi

# ──────────────────────────────────────────────
# 4. tun 设备检测
# ──────────────────────────────────────────────
_tun_check() {
    if [[ "${_OS}" == "macos" ]]; then
        echo "[INFO] macOS 使用 ZeroTier 内置虚拟网卡, 无需 tun 模块"
        return 0
    fi

    if [[ -c /dev/net/tun ]]; then
        echo "[INFO] /dev/net/tun 设备节点存在"
        return 0
    fi

    if [[ -r /proc/modules ]] && grep -q '^tun ' /proc/modules 2>/dev/null; then
        echo "[INFO] tun 内核模块已加载"
        return 0
    fi

    if command -v lsmod &>/dev/null && lsmod 2>/dev/null | grep -q '^tun '; then
        echo "[INFO] tun 内核模块已加载"
        return 0
    fi

    return 1
}

if _tun_check; then
    :
else
    echo "[STEP] 加载 tun 内核模块..."
    if command -v modprobe &>/dev/null; then
        if modprobe tun 2>/dev/null; then
            echo "[OK] tun 模块已通过 modprobe 加载"
        else
            echo "[WARN] modprobe tun 失败"
            if [[ "${_IS_CONTAINER}" == true ]]; then
                echo "  容器中 tun 需宿主机提供: docker run --cap-add=NET_ADMIN --device=/dev/net/tun ..."
            fi
        fi
    else
        echo "[WARN] modprobe 不可用"
        if [[ "${_IS_CONTAINER}" == true ]]; then
            echo "  容器启动参数: --cap-add=NET_ADMIN --device=/dev/net/tun"
        fi
    fi
fi

if [[ "${_OS}" == "linux" && "${_IS_CONTAINER}" == false ]]; then
    if [[ -d /etc/modules-load.d ]] && ! grep -q '^tun' /etc/modules-load.d/modules.conf 2>/dev/null; then
        echo "tun" >> /etc/modules-load.d/modules.conf
        echo "[OK] tun 已添加到 /etc/modules-load.d/modules.conf"
    elif [[ -f /etc/modules ]] && ! grep -q '^tun' /etc/modules 2>/dev/null; then
        echo "tun" >> /etc/modules
        echo "[OK] tun 已添加到 /etc/modules"
    fi
fi

# ──────────────────────────────────────────────
# 5. 启动服务
# ──────────────────────────────────────────────
_check_online() {
    local _timeout="${1:-5}"
    for i in $(seq 1 "${_timeout}"); do
        if zerotier-cli status 2>/dev/null | grep -q 'ONLINE'; then
            return 0
        fi
        sleep 1
    done
    return 1
}

_start_service() {
    echo "[STEP] 启动 zerotier-one 服务..."

    case "${_START_METHOD}" in
    systemd)
        if systemctl start zerotier-one 2>/dev/null; then
            systemctl enable zerotier-one 2>/dev/null || true
            if _check_online 10; then
                echo "[OK] zerotier-one 已启动 (systemd)"
                return
            fi
            echo "[WARN] systemd 启动超时, 尝试手动模式..."
        else
            echo "[WARN] systemctl 启动失败, 尝试手动模式..."
        fi
        ;;

    launchd)
        local _plist="/Library/LaunchDaemons/com.zerotier.zerotier-one.plist"
        if [[ -f "${_plist}" ]]; then
            launchctl unload "${_plist}" 2>/dev/null || true
            launchctl load "${_plist}" 2>/dev/null || true
            if _check_online 10; then
                echo "[OK] zerotier-one 已启动 (launchd)"
                return
            fi
            echo "[WARN] launchd 启动超时, 尝试手动模式..."
        else
            echo "[WARN] 未找到 ZeroTier launchd plist, 尝试手动模式..."
        fi
        ;;

    sysvinit)
        service zerotier-one start 2>/dev/null || true
        if command -v update-rc.d &>/dev/null; then
            update-rc.d zerotier-one defaults 2>/dev/null || true
        elif command -v chkconfig &>/dev/null; then
            chkconfig zerotier-one on 2>/dev/null || true
        fi
        sleep 2
        if _check_online 5; then
            echo "[OK] zerotier-one 已启动 (sysvinit)"
            return
        fi
        echo "[WARN] sysvinit 启动失败, 尝试手动模式..."
        ;;

    manual)
        echo "[INFO] 使用手动 daemon 模式..."
        ;;
    esac

    # 通用回退: 手动 daemon
    pkill zerotier-one 2>/dev/null || true
    sleep 1
    zerotier-one -d 2>/dev/null &
    sleep 2
    if _check_online 8; then
        local _pid
        _pid=$(pgrep -x zerotier-one | head -1 || echo "?")
        echo "[OK] zerotier-one 已手动启动 (PID: ${_pid})"
    else
        echo "[ERROR] zerotier-one 启动失败"
        echo "  - 日志: journalctl -u zerotier-one 或 /var/log/syslog"
        echo "  - tun 设备: ls -la /dev/net/tun"
        if [[ "${_IS_CONTAINER}" == true ]]; then
            echo "  - 容器参数: --cap-add=NET_ADMIN --device=/dev/net/tun"
        fi
        if [[ "${_OS}" == "macos" ]]; then
            echo "  - macOS: 检查 系统偏好设置 → 隐私与安全性 → 允许 ZeroTier 系统扩展"
        fi
        exit 1
    fi
}

if zerotier-cli status 2>/dev/null | grep -q 'ONLINE'; then
    echo "[INFO] zerotier-one 服务已在运行"
else
    _start_service
fi

# ──────────────────────────────────────────────
# 6. 加入网络 + 设置 orbit 卫星节点
# ──────────────────────────────────────────────
if ! zerotier-cli status 2>/dev/null | grep -q 'ONLINE'; then
    echo "[ERROR] zerotier-one 未在线, 无法加入网络"
    echo "  请检查: zerotier-cli status"
    exit 1
fi

# 6a. 加入网络
if [[ "${_ALREADY_JOINED}" == true ]]; then
    echo "[INFO] 已加入网络 ${NETWORK_ID}, 跳过 join 步骤"
else
    echo "[STEP] 加入 ZeroTier 网络: ${NETWORK_ID} ..."
    _JOIN_RESULT=$(zerotier-cli join "${NETWORK_ID}" 2>&1) || true
    if echo "${_JOIN_RESULT}" | grep -qE '200 join OK|already a member'; then
        echo "[OK] 已向网络 ${NETWORK_ID} 发起加入请求"
    else
        echo "[ERROR] 加入网络失败: ${_JOIN_RESULT}"
        exit 1
    fi
fi

# 6b. 设置 orbit 卫星节点 (加速 NAT 穿透, 幂等操作)
echo "[STEP] 设置 orbit 卫星节点: ${ORBIT_ID} ..."
_ORBIT_RESULT=$(zerotier-cli orbit "${ORBIT_ID}" "${ORBIT_ID}" 2>&1) || true
if echo "${_ORBIT_RESULT}" | grep -qE '200 orbit OK|already orbiting'; then
    echo "[OK] orbit ${ORBIT_ID} 已设置"
else
    echo "[WARN] orbit 设置返回: ${_ORBIT_RESULT}"
    echo "  (如果显示 already orbiting 可忽略此警告)"
fi

# ──────────────────────────────────────────────
# 7. 收集本机信息
# ──────────────────────────────────────────────
_NODE_ID=$(zerotier-cli info 2>/dev/null | awk '{print $3}' || echo "未知")
_HOSTNAME=$(hostname)

_NET_INFO=""
for i in $(seq 1 15); do
    _NET_INFO=$(zerotier-cli listnetworks 2>/dev/null | grep "${NETWORK_ID}" || true)
    [[ -n "${_NET_INFO}" ]] && break
    sleep 1
done

if [[ -n "${_NET_INFO}" ]]; then
    _NET_STATUS=$(echo "${_NET_INFO}" | awk '{print $4}')
    _ZT_IP=$(echo "${_NET_INFO}" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | head -1)
    [[ -z "${_NET_STATUS}" ]] && _NET_STATUS="UNKNOWN"
    [[ -z "${_ZT_IP}" ]] && _ZT_IP="等待分配"
else
    _NET_STATUS="UNKNOWN"
    _ZT_IP="等待分配"
    echo "[WARN] 网络 ${NETWORK_ID} 未在 listnetworks 中出现"
    if [[ "${_IS_CONTAINER}" == true ]] && [[ ! -c /dev/net/tun ]]; then
        echo "  可能原因: 容器缺少 /dev/net/tun 设备"
        echo "  解决方案: docker run --cap-add=NET_ADMIN --device=/dev/net/tun ..."
    fi
fi

# ──────────────────────────────────────────────
# 8. 使用说明
# ──────────────────────────────────────────────

# 计算字符串视觉显示宽度 (CJK 等多字节 UTF-8 字符 = 2列, ASCII = 1列)
# 注意: 本函数不处理 box-drawing 字符 (U+2500-U+257F), 因其为 1 列
_vwidth() {
    local s="$1" w=0 ord i=0
    while [[ $i -lt ${#s} ]]; do
        printf -v ord '%d' "'${s:$i:1}"
        if [[ $ord -le 127 ]]; then
            w=$((w+1))
            ((i++))
        else
            # 根据 UTF-8 首字节判断序列长度, 跳过后续字节
            local lead
            if (( (ord & 0xF8) == 0xF0 )); then
                lead=4
            elif (( (ord & 0xF0) == 0xE0 )); then
                lead=3
            elif (( (ord & 0xE0) == 0xC0 )); then
                lead=2
            else
                lead=2
            fi
            w=$((w+2))
            i=$((i+lead))
        fi
    done
    echo "$w"
}

# 输出含 │ 包围的内容行, 右侧自动补齐空格到 62 列
_box_line() {
    local content="$1" vis_w pad _sp=""
    vis_w=$(_vwidth "$content")
    pad=$((62 - vis_w))
    while [[ $pad -gt 0 ]]; do _sp="$_sp "; pad=$((pad-1)); done
    echo "  │  ${content}${_sp}│"
}

echo ""

if [[ "${_OS}" == "macos" ]]; then
    _TITLE="ZeroTier 初始化 — macOS"
else
    _TITLE="ZeroTier 初始化 — Linux"
fi

# 边框行直接用 echo 硬编码 (box-drawing 字符视觉宽度无法用 _vwidth 精确计算)
echo "  ┌──────────────────────────────────────────────────────────────┐"

# 标题行用 _box_line (含 CJK 文字)
_box_line "${_TITLE}"

echo "  ├──────────────────────────────────────────────────────────────┤"
echo "  │                                                              │"

# 信息行用 _box_line (含 CJK 文字, 视觉宽度计算正确)
_box_line "  主机名  : ${_HOSTNAME}"
_box_line "  Node ID : ${_NODE_ID}"
_box_line "  网络 ID : ${NETWORK_ID}"
_box_line "  虚拟 IP : ${_ZT_IP}"
_box_line "  状态    : ${_NET_STATUS}"

echo "  │                                                              │"
echo "  └──────────────────────────────────────────────────────────────┘"
echo ""

if [[ "${_NET_STATUS}" == "OK" ]]; then
    cat << 'USAGE_OK'

  ┌──────────────────────────────────────────────────────────────┐
  │  当前状态: OK — 网络已正常连接                               │
  ├──────────────────────────────────────────────────────────────┤
  │                                                              │
  │  常用命令                                                    │
  │    zerotier-cli status          查看节点在线状态             │
  │    zerotier-cli listnetworks    列出所有网络及 IP            │
  │    zerotier-cli peers           查看 P2P 直连状态            │
  │    zerotier-cli listpeers       查看卫星节点连接             │
  │                                                              │
  │  测试连通性                                                  │
  │    ping <对端 ZeroTier IP>      测试与对方通信               │
  │                                                              │
  └──────────────────────────────────────────────────────────────┘
USAGE_OK
else
    cat << 'USAGE_DENIED'

  ┌──────────────────────────────────────────────────────────────┐
  │  当前状态: ACCESS_DENIED — 需要在服务端授权                  │
  ├──────────────────────────────────────────────────────────────┤
  │                                                              │
  │  1. 打开 ZeroTier Central                                    │
  │     https://my.zerotier.com                                  │
  │                                                              │
  │  2. 登录后进入网络 48d6023c464e0a5c                           │
  │                                                              │
  │  3. Members 面板 → 找到本机 Node ID → 勾选 Auth              │
  │     (可填写 Name 备注方便管理)                               │
  │                                                              │
  │  4. 返回本机验证 (授权后几秒生效):                           │
  │     zerotier-cli listnetworks                                │
  │     状态变为 OK 且获取 IP = 成功                             │
  │                                                              │
  └──────────────────────────────────────────────────────────────┘
USAGE_DENIED
fi

# 平台特定的启停说明
if [[ "${_OS}" == "macos" ]]; then
    cat << 'USAGE_TAIL'

  ┌──────────────────────────────────────────────────────────────┐
  │  macOS 启停控制                                              │
  │    sudo launchctl unload /Library/LaunchDaemons/com.zerotier.zerotier-one.plist
  │    sudo launchctl load   /Library/LaunchDaemons/com.zerotier.zerotier-one.plist
  │                                                              │
  │  故障排查                                                    │
  │    zerotier-cli peers   (DIRECT=直连, RELAY=中继)            │
  │    ifconfig | grep feth            查看虚拟网卡              │
  │    tail -f /Library/Application\ Support/ZeroTier/One/*.log  │
  │                                                              │
  │  详细教程: ~/configure/lib/zerotier-v20260715/setup.md       │
  │                                                              │
  └──────────────────────────────────────────────────────────────┘
USAGE_TAIL
else
    cat << 'USAGE_TAIL'

  ┌──────────────────────────────────────────────────────────────┐
  │  Linux 启停控制                                              │
  │    systemctl start/stop/restart zerotier-one  (systemd)      │
  │    service  zerotier-one start/stop          (sysvinit)      │
  │                                                              │
  │  离开 / 重加 / 重置                                          │
  │    zerotier-cli leave 48d6023c464e0a5c                        │
  │    zerotier-cli join  48d6023c464e0a5c                        │
  │    rm -rf /var/lib/zerotier-one/identity.* && restart         │
  │                                                              │
  │  故障排查                                                    │
  │    zerotier-cli peers          (DIRECT=直连, RELAY=中继)     │
  │    journalctl -u zerotier-one -f           实时日志          │
  │    ip addr show zt0                        虚拟网卡          │
  │    ufw allow 9993/udp                      防火墙端口        │
  │    ls -la /dev/net/tun                     检查 tun          │
  │                                                              │
  │  详细教程: ~/configure/lib/zerotier-v20260715/setup.md       │
  │                                                              │
  └──────────────────────────────────────────────────────────────┘
USAGE_TAIL
fi

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
