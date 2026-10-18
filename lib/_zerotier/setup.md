# ZeroTier 配置操作

## 目标

安装 ZeroTier One，加入仓库当前使用的虚拟网络，在 ZeroTier Central 授权节点，并验证 `zt0`、分配 IP 和 P2P/中继状态。

完整教程见 [`../zerotier-v20260715/setup.md`](../zerotier-v20260715/setup.md)。本页给出稳定操作入口和当前仓库脚本的关键限制。

## 当前固定参数

| 参数 | 值 | 来源 |
|---|---|---|
| Network ID | `48d6023c464e0a5c` | `bin/zerotier_init.sh` |
| Orbit ID | `240f181d35` | `bin/zerotier_init.sh` |
| 客户端 | Linux、macOS | `bin/zerotier_init.sh` |
| 服务端管理 | `https://my.zerotier.com` | ZeroTier Central |

这些参数只适用于当前个人网络。其他部署应先修改源脚本或手工执行等价命令。

## 安装和初始化

Linux 需要 root：

```bash
sudo bash bin/zerotier_init.sh
```

macOS 应先以普通用户安装 Homebrew 包，再用 root 运行初始化脚本：

```bash
brew install zerotier-one
brew_prefix="$(brew --prefix)"
sudo env PATH="$brew_prefix/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
  bash bin/zerotier_init.sh
```

不要让 Homebrew 以 root 安装。显式传入 Homebrew `bin`，避免 root 环境找不到已安装的 `zerotier-cli`。若还没有 Homebrew，应先按 Homebrew 官方流程以普通用户安装。

脚本会依次执行：

1. 检测 `systemd`、`sysvinit`、容器、WSL 或 macOS `launchd`。
2. 在缺失 `zerotier-cli` 时按平台安装客户端。
3. 检查或加载 Linux `tun` 模块。
4. 启动并尽量启用 `zerotier-one`。
5. 加入固定网络并设置 orbit。
6. 输出 Node ID、状态和虚拟 IP。

## 授权

首次加入后，客户端通常显示 `ACCESS_DENIED`。在 ZeroTier Central 中：

1. 打开目标网络。
2. 在 Members 中找到脚本输出的 Node ID。
3. 勾选授权，并为节点添加可识别名称。
4. 回到客户端等待状态变为 `OK`。

验证：

```bash
zerotier-cli status
zerotier-cli info
zerotier-cli listnetworks
zerotier-cli peers
```

`DIRECT` 优于 `RELAY`。`RELAY` 仍可通信，但延迟和带宽可能较差。

## 容器与 WSL

容器没有宿主机内核能力时，`modprobe tun` 无法生效。运行容器需要等价参数：

```bash
docker run --cap-add=NET_ADMIN --device=/dev/net/tun ...
```

WSL 优先启用 systemd。未启用时脚本退回手动 daemon 模式，进程生命周期可能随终端结束。

## 停止、离开和重置

```bash
sudo systemctl stop zerotier-one
sudo zerotier-cli leave 48d6023c464e0a5c
sudo systemctl start zerotier-one
```

重置 Node ID 会删除身份文件，属于破坏性操作：

```bash
sudo systemctl stop zerotier-one
sudo rm -rf /var/lib/zerotier-one/identity.*
sudo systemctl start zerotier-one
```

重置后必须在 Central 重新授权新节点。上述删除命令只应在明确需要更换身份时执行。

## 常见故障

| 现象 | 检查 |
|---|---|
| `zerotier-cli` 不存在 | 安装是否成功、`PATH` 是否包含 `/usr/sbin` |
| 状态始终 `ACCESS_DENIED` | Central 是否授权 |
| 状态 `OK` 但无 IP | 网络是否启用 IPv4 Auto-Assign |
| `zt0` 不存在 | `tun` 模块、容器设备与权限 |
| 延迟高 | `zerotier-cli peers` 是否为 `RELAY` |
| SSH 不通 | ZeroTier IP、远端 SSH 服务、防火墙和用户权限 |

## 验证

```bash
bash -n bin/zerotier_init.sh
zerotier-cli status
zerotier-cli listnetworks
ping -c 1 <对端 ZeroTier IP>
```

脚本退出成功只表示安装、服务启动和 join 请求完成，不表示 Central 已授权或主机之间一定能通信。
