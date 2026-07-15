# ZeroTier — Linux 客户端连接教程

## 什么是 ZeroTier

ZeroTier 是一个开源的虚拟网络（SDN）平台，基于 P2P 协议，能够在互联网上组建加密的二层以太网。它可以把分布在任意网络环境下的多台设备**虚拟到同一个局域网**中，就像它们插在同一个交换机上一样。

核心概念：

| 概念 | 说明 |
|------|------|
| **Network ID** | 16 位十六进制字符串，唯一标识一个 ZeroTier 虚拟网络 |
| **Node ID** | 10 位十六进制字符串，每台设备安装 ZeroTier 后自动生成的唯一标识 |
| **ZeroTier Central (服务端)** | Web 管理后台 (https://my.zerotier.com)，用于创建网络、管理成员、配置 IP 和路由规则 |
| **ZeroTier One (客户端)** | 运行在每台设备上的后台服务，负责建立和维护 P2P 隧道 |
| **Planet / Root Server** | ZeroTier 官方的根服务器，用于节点发现和 NAT 穿透协调 |

实际使用中，"服务端"指 ZeroTier Central 上创建的网络（以及对应的 Network ID），"客户端"指加入该网络的各台设备。

---

## 1. 注册 ZeroTier Central 并创建网络（服务端准备）

在连接任何客户端之前，需要先在 ZeroTier Central 上准备好网络。

1. 打开 https://my.zerotier.com ，注册账号（免费版支持最多 25 个节点）
2. 登录后点击 **"Create A Network"**，系统会自动生成一个 Network ID（形如 `48d6023c464e0a5c`）
3. 点击该网络进入详情页，记下 Network ID，后面客户端加入时需要用到
4. 在 **Settings** 面板中配置网络参数：
   - **Name**：给网络起个好记的名字（如 `my-lab`）
   - **IPv4 Auto-Assign**：选择一个私有 IP 段（如 `10.147.17.*`），客户端加入并授权后会自动分配 IP
   - **IPv6 Auto-Assign**：可以关闭，不需要 IPv6 的话
   - **Routes**：如果有需要路由的子网，在这里添加（通常是 ZeroTier 网段本身 `10.147.17.0/24 (LAN)`）

> 服务端准备完成后，**Network ID** 就是你所有客户端需要"加入"的目标。

---

## 2. 客户端安装 ZeroTier One

### 2.1 一键安装（推荐）

```bash
curl -s https://install.zerotier.com | sudo bash
```

该脚本会自动检测操作系统和发行版，添加官方源并安装 `zerotier-one` 包。

### 2.2 各发行版手动安装

**Ubuntu / Debian：**

```bash
curl -s 'https://raw.githubusercontent.com/zerotier/ZeroTierOne/master/doc/contact%40zerotier.com.gpg' | gpg --import
# 如果提示 gpg 不可使用，直接执行:
curl -s https://install.zerotier.com | sudo bash
```

或者手动添加源：

```bash
# Ubuntu 20.04+ / Debian 11+
curl -fsSL https://raw.githubusercontent.com/zerotier/ZeroTierOne/master/doc/contact%40zerotier.com.gpg | sudo gpg --dearmor -o /usr/share/keyrings/zerotier-archive-keyring.gpg

echo "deb [signed-by=/usr/share/keyrings/zerotier-archive-keyring.gpg] http://download.zerotier.com/debian/$(lsb_release -cs) $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/zerotier.list

sudo apt update
sudo apt install -y zerotier-one
```

**CentOS / RHEL / Fedora：**

```bash
# RHEL 7 / CentOS 7
curl -fsSL https://raw.githubusercontent.com/zerotier/ZeroTierOne/master/doc/contact%40zerotier.com.gpg | sudo rpm --import
sudo yum install -y https://download.zerotier.com/redhat/el/7/x86_64/zerotier-one-latest.rpm

# RHEL 8+ / Fedora
sudo dnf install -y https://download.zerotier.com/redhat/el/8/x86_64/zerotier-one-latest.rpm
```

**Arch Linux：**

```bash
yay -S zerotier-one
# 或
sudo pacman -S zerotier-one
```

**OpenSUSE：**

```bash
sudo zypper install -y https://download.zerotier.com/redhat/el/8/x86_64/zerotier-one-latest.rpm
```

---

## 3. 启动服务并设为开机自启

安装完成后，启动 `zerotier-one` 服务：

```bash
# systemd 系统（主流发行版通用）
sudo systemctl start zerotier-one
sudo systemctl enable zerotier-one

# 检查服务状态
sudo systemctl status zerotier-one

# 老式 init 系统
sudo service zerotier-one start
```

验证安装是否成功：

```bash
sudo zerotier-cli status
# 输出: 200 info {node_id} {version} ONLINE
```

其中 `{node_id}` 是 10 位十六进制字符，代表这台设备的唯一标识。请记下这个 Node ID，后面在服务端授权时会用到。

---

## 4. 加入网络

```bash
sudo zerotier-cli join 48d6023c464e0a5c
```

输出 `200 join OK` 表示加入请求已发送。此时客户端会尝试连接 ZeroTier 根服务器，但**尚未被授权访问网络**。

验证加入状态：

```bash
sudo zerotier-cli listnetworks
```

输出示例：

```
200 listnetworks <nwid>   <name>   <mac>             <status>   <type>   <dev>   <ZT assigned ips>
200 listnetworks 48d6023c464e0a5c   my-lab   02:xx:xx:xx:xx:xx  ACCESS_DENIED  PRIVATE  zt0     -
```

状态 `ACCESS_DENIED` 表示客户端已找到网络但尚未获得授权 —— 这是正常的，需要下一步在服务端手动批准。

---

## 5. 在 ZeroTier Central 授权客户端（服务端操作）

1. 打开 https://my.zerotier.com 并登录
2. 点击目标网络（Network ID 为 `48d6023c464e0a5c` 的那个）
3. 在 **Members** 面板中，找到刚才加入的新节点（状态显示 `NOT Authorized`）
   - 可以通过 Node ID 来确认是哪台设备
4. 勾选该节点左侧的 **Auth?** 复选框（或者点击扳手图标 → 勾选 Authorized）
5. 页面会自动保存。几秒后客户端状态会从 `ACCESS_DENIED` 变为 `OK`

> 提示：可以在 **Name / Description** 字段中给节点添加备注（如 "办公室工作站"、"家庭 NAS"），方便后续管理。

---

## 6. 验证连接

回到客户端，确认网络状态：

```bash
sudo zerotier-cli listnetworks
```

此时输出应为：

```
200 listnetworks 48d6023c464e0a5c   my-lab   02:xx:xx:xx:xx:xx  OK           PRIVATE  zt0     10.147.17.x/24
```

关键变化：
- 状态从 `ACCESS_DENIED` → **OK**
- `ZT assigned ips` 列显示了从服务端自动分配的 IP

检查虚拟网卡：

```bash
ip addr show zt0
# 或
ifconfig zt0
```

输出应包含 ZeroTier 分配的 IP 地址，例如 `10.147.17.x`。

### 6.1 基本连通性测试

从客户端 ping 同一 ZeroTier 网络中的其他已授权节点：

```bash
ping 10.147.17.1       # 示例：ping 另一台设备
ping 10.147.17.100     # 示例：ping 目标设备
```

如果双方都显示 `OK` 状态且能互相 ping 通，说明 ZeroTier 虚拟网络已组建成功。

### 6.2 测试 P2P 直连

```bash
sudo zerotier-cli peers
```

输出中搜索目标节点的 Node ID，查看 `PATH` 列：
- `DIRECT`：已建立 P2P 直连（最佳状态）
- `RELAY`：通过中继服务器转发（说明 NAT 穿透未成功，但仍可通信）

---

## 7. 多客户端场景示例

假设有三台设备需要组建虚拟局域网：

| 设备 | 角色 | 物理网络 | ZeroTier IP |
|------|------|----------|-------------|
| 办公室工作站 | 工作机 | 公司内网 (NAT) | 10.147.17.10 |
| 家庭台式机 | 开发机 | 家庭宽带 (NAT) | 10.147.17.20 |
| 云服务器 | 中转/存储 | 公有云 (公网 IP) | 10.147.17.30 |

**操作流程：**

1. 三台设备都执行安装和加入：`sudo zerotier-cli join 48d6023c464e0a5c`
2. 在 ZeroTier Central 的 Members 面板中，把三个节点全部勾选 `Auth`
3. 任一设备上执行 `ping 10.147.17.30`（ping 云服务器），应能通
4. 三台设备之间现在可以：
   - 通过 SSH 互访：`ssh user@10.147.17.10`
   - 挂载 NFS 共享、访问内网服务等
   - 完全像在同一个物理局域网中一样通信

---

## 8. 高级配置

### 8.1 手动设置静态 IP

默认情况下 IP 是自动分配的。如果需要在 ZeroTier Central 中手动指定某个节点的 IP：

1. 在 Members 面板中找到目标节点，点击扳手图标
2. 取消勾选 **"Auto-Assign IP"**
3. 在 IP 字段中手动填入所需地址（必须在网络设定的 IP 段内）
4. 保存即可

### 8.2 添加本地路由

如果需要让 ZeroTier 节点能够访问某个节点的物理局域网，可以在 ZeroTier Central 的 Settings → **Managed Routes** 中添加路由：

```
目标网段         转发节点
192.168.1.0/24   10.147.17.10    # 通过办公室工作站访问办公室内网
```

配合在转发节点上开启 IP 转发：

```bash
sudo sysctl -w net.ipv4.ip_forward=1
# 永久生效
echo "net.ipv4.ip_forward = 1" | sudo tee -a /etc/sysctl.conf
```

### 8.3 查看和管理所有已加入的网络

```bash
# 列出已加入的所有网络
sudo zerotier-cli listnetworks

# 查看节点信息（Node ID、版本等）
sudo zerotier-cli info

# 查看已连接的 peers（P2P/中继状态）
sudo zerotier-cli peers
```

### 8.4 离开网络

```bash
sudo zerotier-cli leave 48d6023c464e0a5c
```

离开后该节点在 ZeroTier Central 的 Members 列表中仍会保留，可手动删除。

### 8.5 重装或重置节点

如果某台设备需要以全新身份加入（换一个新的 Node ID）：

```bash
sudo systemctl stop zerotier-one
sudo rm -rf /var/lib/zerotier-one/identity.*
sudo systemctl start zerotier-one
```

重启后 ZeroTier 会生成新的 Node ID。注意需要在 ZeroTier Central 中**重新授权**新身份，并手动删除旧节点条目。

---

## 9. 常见问题排查

### 9.1 状态始终显示 ACCESS_DENIED

- **原因**：未在 ZeroTier Central 授权该节点
- **解决**：登录 https://my.zerotier.com → 找到对应网络 → Members → 勾选 Auth

### 9.2 状态显示 OK 但 ping 不通

- **检查 IP 是否分配**：`sudo zerotier-cli listnetworks` 看 IP 是否为空
  - 如果为空，检查 ZeroTier Central 中是否配置了 IPv4 Auto-Assign
- **检查防火墙**：ZeroTier 使用 UDP 9993 端口
  ```bash
  sudo ufw allow 9993/udp
  # 或 iptables
  sudo iptables -A INPUT -p udp --dport 9993 -j ACCEPT
  ```
- **检查 peers 状态**：`sudo zerotier-cli peers`，如果目标节点不出现，可能是双方 UDP 9993 都无法出站

### 9.3 连接不稳定或延迟高

- `sudo zerotier-cli peers` 查看 `PATH` 列
  - 如果是 `RELAY` 而非 `DIRECT`，说明 NAT 穿透失败，流量经过中继
  - 确保至少一端的 UDP 9993 端口可从公网访问（如云服务器有公网 IP）
  - 在有公网 IP 的节点上，可以考虑开启端口转发来提高穿透成功率

### 9.4 服务启动失败

```bash
# 查看日志
sudo journalctl -u zerotier-one -f

# 检查 tun 内核模块是否加载
lsmod | grep tun
# 如果未加载
sudo modprobe tun
```

### 9.5 虚拟网卡 (zt0) 没有出现

```bash
# 检查设备列表
ip link show

# 如果没有 zt0，手动安装并加载 tun 模块
sudo modprobe tun
echo "tun" | sudo tee -a /etc/modules-load.d/modules.conf

# 重启 ZeroTier
sudo systemctl restart zerotier-one
```

### 9.6 DNS 问题（无法解析 .zerotier 域名）

ZeroTier 网络默认不提供 DNS 服务。如需内网 DNS：
- 自行部署 DNS 服务器（如 dnsmasq、CoreDNS）
- 或直接使用 IP 地址通信（对大多数场景已足够）
- 在 ZeroTier Central 的 Settings 中可以为网络配置 DNS 服务器地址

---

## 10. 快速参考卡片

```bash
#========== 安装 & 启停 ==========#
curl -s https://install.zerotier.com | sudo bash    # 安装
sudo systemctl start zerotier-one                   # 启动
sudo systemctl enable zerotier-one                  # 开机自启
sudo systemctl status zerotier-one                  # 查看状态

#========== 网络管理 ==========#
sudo zerotier-cli status                            # 查看本机状态
sudo zerotier-cli info                              # 查看 Node ID
sudo zerotier-cli join <Network ID>                 # 加入网络
sudo zerotier-cli leave <Network ID>                # 离开网络
sudo zerotier-cli listnetworks                      # 列出网络及状态
sudo zerotier-cli peers                             # 查看 P2P 连接状态

#========== 服务端 ==========#
https://my.zerotier.com                             # ZeroTier Central 管理后台
# → Members → 勾选 Auth                             # 授权新节点
# → Settings → IPv4 Auto-Assign                     # 配置 IP 池
# → Settings → Managed Routes                       # 配置路由

#========== 故障排查 ==========#
sudo zerotier-cli peers                             # DIRECT=直连, RELAY=中继
sudo journalctl -u zerotier-one -f                  # 实时日志
sudo modprobe tun                                   # 加载 tun 模块
sudo ufw allow 9993/udp                             # 开放防火墙端口
```

```
# 本笔记涉及的网络信息:
Network ID: 48d6023c464e0a5c
其他标识:   240f181d35
```
