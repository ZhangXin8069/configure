# WSL 2 实用配置与迁移指南

本文面向 Windows 10/11 + WSL 2，命令以 PowerShell 为主。WSL 发行版维护与 Docker Desktop 数据维护必须分开：Docker Desktop 自建发行版和 VHDX 由 Docker Desktop 管理，不要套用本文的发行版迁移步骤。

删除发行版、执行 `wsl --unregister`、覆盖 VHDX、压缩磁盘或修改系统级虚拟化设置都属于需要明确确认的操作。本文只提供步骤，不提供自动执行脚本。

## 基线与升级

先确认 WSL 版本、默认发行版和虚拟化状态：

```powershell
wsl --version
wsl --status
wsl --list --verbose
wsl --list --online
```

`wsl --version` 无法识别通常表示仍是较旧的 Windows 内置版本。安装或更新：

```powershell
wsl --update
wsl --set-default-version 2
```

安装第一个发行版：

```powershell
wsl --install -d Ubuntu
```

安装过程可能要求重启 Windows 或完成首次用户创建。已有 WSL 环境时，不要反复运行完整 `wsl --install` 来“修复”问题；先用 `wsl --status`、`wsl --list --verbose` 和事件日志定位具体组件。

设置默认发行版并进入其默认目录：

```powershell
wsl --set-default Ubuntu
wsl -d Ubuntu
```

## 全局配置 `.wslconfig`

`%UserProfile%\.wslconfig` 只作用于 WSL 2 虚拟机，对 WSL 1 无效。新版 WSL 优先使用开始菜单中的 **WSL Settings** 图形界面；手工编辑时配置示例：

```ini
[wsl2]
memory=12GB
processors=8
swap=8GB
localhostForwarding=true

# Windows 11 22H2+ 可选；启用前先验证 VPN、防火墙和端口转发行为。
# networkingMode=mirrored
# dnsTunneling=true
# firewall=true

[experimental]
# 仅影响新建 VHDX，不会缩小已有磁盘。
# sparseVhd=true
# 按需启用，避免频繁回收造成性能波动。
# autoMemoryReclaim=gradual
```

配置原则：

- `memory` 是 WSL 2 虚拟机的上限，不是预留量。设置过低会让 Docker 构建、编译和 CUDA 任务出现 OOM 或退出码 137。
- `processors` 不宜占满宿主全部逻辑 CPU，至少给 Windows、Docker Desktop 和图形界面保留资源。
- `swap` 使用磁盘空间；Swap 很大不代表可以替代足够的物理内存。
- `networkingMode=mirrored` 需要 Windows 11 22H2 及以上和较新的 WSL。修改网络模式后必须完整重启 WSL，并重新验证端口、VPN 和防火墙规则。
- `autoMemoryReclaim`、`sparseVhd` 属于高级或实验性选项，只在明确需要回收空间或页面缓存时启用。

修改后关闭所有 WSL 实例：

```powershell
wsl --shutdown
```

`wsl --shutdown` 会停止所有 WSL 发行版，并可能停止 Docker Desktop 的 WSL 后端；先保存正在写入的数据和构建任务。配置通常在 WSL 虚拟机下次启动时生效。关闭单个发行版可用 `wsl --terminate <发行版名>`，它不会关闭其他发行版或 Docker Desktop 管理的 WSL 实例。

## 单发行版配置 `/etc/wsl.conf`

`/etc/wsl.conf` 只配置指定发行版。常用最小配置：

```ini
[user]
default=zhangxin

[boot]
systemd=true

[interop]
enabled=true
appendWindowsPath=false

[automount]
enabled=true
root=/mnt/
options="metadata,umask=22,fmask=11"
mountFsTab=true
```

说明：

- `default` 必须对应发行版内已存在的 Linux 用户名。导入完成后首次进入通常是 `root`，确认用户存在后再修改。
- `systemd=true` 仅适用于支持 systemd 的新版 WSL 2，会增加启动时间。使用 Docker Desktop 集成时，不要再在同一发行版启动第二套 Docker Engine。
- `appendWindowsPath=false` 可减少 Windows 命令遮蔽 Linux 命令，但使用 `code.exe`、`explorer.exe` 等 Windows 程序时仍需完整命令名或显式 PATH。
- `metadata` 让挂载盘支持部分 Linux 权限元数据，适合需要权限语义的共享目录；启用后应重新验证挂载权限。

在发行版内编辑：

```bash
sudoedit /etc/wsl.conf
```

保存后退出并重启该发行版：

```powershell
wsl --terminate Ubuntu
wsl -d Ubuntu -- bash -lc 'id; systemd-detect-virt'
```

若配置格式错误，WSL 仍可能启动但忽略部分设置。先用 `wsl -d Ubuntu -- cat /etc/wsl.conf` 检查内容，再排查用户、systemd 和挂载设置。

## `wsl --import-in-place`

`wsl --import-in-place` 直接把一个现有 ext4 VHDX 注册为新的 WSL 2 发行版，不经过 tar 解包。适用场景：

- 已有一个可用的 WSL 2 `ext4.vhdx`，需要在当前机器注册。
- 从旧机器或备份保留了完整 VHDX，希望直接恢复。
- 需要把已经准备好的 Linux 根文件系统 VHDX 接入 WSL。

最低验证：

```powershell
wsl --shutdown
Test-Path -LiteralPath 'D:\WSL\Ubuntu-New\ext4.vhdx'
wsl --list --quiet
wsl --import-in-place Ubuntu-New 'D:\WSL\Ubuntu-New\ext4.vhdx'
wsl --list --verbose
wsl -d Ubuntu-New -- cat /etc/os-release
```

关键边界：

- VHDX 必须是 ext4，并采用 WSL 2 可识别的虚拟磁盘布局；任意 Linux 虚拟机磁盘或动态 VHD 不一定能直接导入。
- WSL 注册后会直接使用该 VHDX。导入前先 `wsl --shutdown`，导入后不要从其他虚拟机或挂载工具同时写入。
- 发行版名称必须唯一。`--import-in-place` 不会注销旧的发行版，也不会自动复制 VHDX。
- 不要把网络共享、同步盘或可移动介质上的 VHDX 作为长期运行存储；休眠、拔盘或同步冲突可能损坏文件系统。
- 导入后默认用户可能变回 `root`。先验证 `/home/<用户>` 是否存在，再通过 `/etc/wsl.conf` 设置 `[user] default=<用户>`。
- 导入成功不等于数据完整。至少检查 `/etc/os-release`、用户目录、包管理器状态和关键项目，再决定是否处理旧发行版。

### 从现有发行版安全克隆

不要直接复制正在运行的 `ext4.vhdx`。可使用 WSL 自带导出流程生成新 VHDX：

```powershell
New-Item -ItemType Directory -Force -Path 'D:\WSL\Ubuntu-New' | Out-Null
wsl --shutdown
wsl --export Ubuntu 'D:\WSL\Ubuntu-New\ext4.vhdx' --vhd
wsl --import-in-place Ubuntu-New 'D:\WSL\Ubuntu-New\ext4.vhdx'
wsl -d Ubuntu-New -- cat /etc/os-release
```

验证新发行版后，原发行版保持不变。确认不再需要原发行版时，`wsl --unregister Ubuntu` 会永久删除其注册信息和发行版存储；该动作必须单独确认，且不能把“已在 Windows 资源管理器中看到目录”当作可用备份。

克隆 VHDX 会复制主机名、machine-id、SSH host key 等身份信息。若两个发行版会同时运行或对外提供网络服务，应在新发行版中按发行版规范重新生成这些标识，不能把克隆体直接当作独立主机加入集群。

### 导入已有的外部 VHDX

用户提供的示例可以写成：

```powershell
wsl --shutdown
wsl --import-in-place Ubuntu-New "D:\WSL\Ubuntu-New\ext4.vhdx"
wsl --list --verbose
```

若 `D:\WSL\Ubuntu-New\ext4.vhdx` 正被另一个已注册发行版使用，应先关闭 WSL，使用 `wsl --export <原发行版> <新路径> --vhd` 复制，而不是让两个发行版共享同一个 VHDX。路径存在不代表 VHDX 未被占用，也不代表文件系统一致。

## 备份、恢复与迁移

### tar 备份与恢复

tar 适合可压缩归档和跨机器迁移：

```powershell
New-Item -ItemType Directory -Force -Path 'D:\WSL\backup' | Out-Null
wsl --shutdown
wsl --export Ubuntu 'D:\WSL\backup\Ubuntu-20261025.tar'
wsl --import Ubuntu-Restore 'D:\WSL\Ubuntu-Restore' 'D:\WSL\backup\Ubuntu-20261025.tar' --version 2
wsl -d Ubuntu-Restore -- cat /etc/os-release
```

`wsl --export` 不包含 Docker Desktop 的容器、镜像和命名卷。需要迁移 Docker 数据时，另行使用镜像仓库、`docker save`、命名卷归档或 Docker Desktop 提供的备份能力。

### VHDX 备份与恢复

VHDX 备份速度快，但通常体积更大，且与 WSL 虚拟磁盘格式绑定：

```powershell
wsl --shutdown
wsl --export Ubuntu 'D:\WSL\backup\Ubuntu-20261025.vhdx' --vhd
wsl --import-in-place Ubuntu-Restore 'D:\WSL\backup\Ubuntu-20261025.vhdx'
```

恢复出的发行版名称必须未占用，目标 VHDX 必须完整且可写。导入前至少保留一份未参与验证的备份，不要将唯一备份直接注册后继续修改。

### 迁移到其他目录

优先使用“导出到新位置 → 以新名称导入 → 验证 → 再决定是否注销旧发行版”的可逆流程。不要手工移动已注册发行版的 VHDX 后只修改注册表路径，也不要移动 Docker Desktop 的 `docker-desktop` 数据磁盘。

## 磁盘占用与压缩

WSL 2 的 VHDX 会随写入增长，但删除 Linux 文件后通常不会立刻缩小。先确认 VHDX 路径：

```powershell
(Get-ChildItem -Path HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss |
  Where-Object { $_.GetValue('DistributionName') -eq 'Ubuntu-New' }
).GetValue('BasePath') + '\ext4.vhdx'
```

发行版内清理无用文件并通知文件系统释放块：

```bash
sudo fstrim -av
df -h
du -xhd1 / 2>/dev/null | sort -h
```

然后关闭 WSL，管理员 PowerShell 执行只读挂载、压缩和卸载。压缩可能耗时，执行前必须有可用备份：

```powershell
wsl --shutdown
diskpart
```

在 `DISKPART>` 中：

```text
select vdisk file="D:\WSL\Ubuntu-New\ext4.vhdx"
attach vdisk readonly
compact vdisk
detach vdisk
exit
```

不要在 WSL 运行、Docker Desktop 使用该磁盘或文件被同步软件扫描时压缩。`defaultVhdSize` 只控制新建发行版的上限，不改变已有 VHDX，也不能替代文件清理。

## 文件系统、网络与 GPU

### 文件系统

- Linux 工具链、编译、数据库和高频 I/O 项目放在 WSL 的 `/home/<用户>`。
- Windows 应用需要直接访问的项目放在 Windows 盘，但 WSL 通过 `/mnt/c`、`/mnt/d` 访问时通常更慢。
- Windows 访问 Linux 文件使用 `\\wsl.localhost\<发行版名>\` 或发行版内 `explorer.exe .`。
- Git Bash 的 `/d/...`、WSL 的 `/mnt/d/...` 和 PowerShell 的 `D:\...` 是三种不同语法，不能互换。

### 网络

NAT 模式下，Windows 通常可通过 `localhost` 访问 WSL 监听端口；WSL 访问 Windows 服务时使用默认网关或宿主地址。启用 `networkingMode=mirrored` 后，Linux 访问 Windows 服务也可尝试 `127.0.0.1`，但需重新验证 VPN、防火墙和端口冲突。

Docker 容器连接 Windows 宿主服务时优先使用 `host.docker.internal`，不要硬编码经常变化的 WSL 虚拟网卡地址。跨主机访问前先检查服务是否监听 `0.0.0.0` 以及 Windows Firewall 规则。

### GPU

WSL 和 Docker Desktop 的 NVIDIA GPU 支持依赖 Windows NVIDIA 驱动、最新 WSL 内核及 Docker Desktop WSL 2 backend。不要在普通 WSL 发行版中再安装一套 Linux NVIDIA 显示驱动。

```powershell
wsl --update
wsl -d Ubuntu -- nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

`wsl` 内失败而 Docker 内成功，通常是 WSL 用户环境或发行版问题；两者都失败，应先检查 Windows 驱动、WSL 更新和 Docker Desktop GPU 后端。

## 常见故障

| 现象 | 优先检查 | 处理边界 |
|---|---|---|
| `wsl --import-in-place` 提示 VHDX 无效 | 是否 ext4/WSL 2 VHDX、文件是否完整、是否仍被占用 | 不通过强挂载或修改分区表猜测修复 |
| 导入后直接登录 `root` | `/etc/wsl.conf` 的 `[user] default` 和 Linux 用户是否存在 | 先确认用户目录，再改默认用户 |
| WSL 内存长期居高不下 | `.wslconfig`、WSL 版本、自动内存回收、Docker 构建缓存 | 不直接删除 WSL VHDX |
| VHDX 占用远大于可用空间 | 已删除文件、`fstrim`、备份和压缩条件 | 压缩前先备份并确保没有进程占用 |
| WSL 内 `docker` 连不上 | Docker Desktop 是否启动、WSL Integration、`docker context` | 不同时启动第二套 Docker Engine |
| `localhost` 端口无法访问 | 监听地址、端口冲突、NAT/mirrored 模式、防火墙 | 不关闭全部防火墙规则来绕过问题 |
| WSL 文件权限异常 | Drive mount 的 `metadata`、`umask/fmask`、文件实际所在系统 | 不把 Windows NTFS 与 Linux ext4 权限模型视为等价 |
| 注销发行版后数据丢失 | 是否已导出并验证恢复 | `wsl --unregister` 不可撤销 |

## 操作检查清单

变更前：

- 记录 `wsl --version`、`wsl --status` 和 `wsl --list --verbose`。
- 确认目标发行版的 VHDX 路径、可用磁盘空间和备份位置。
- 关闭 WSL 与 Docker Desktop 中会占用目标磁盘的任务。
- 对注销、覆盖、迁移和压缩单独确认风险与回滚路径。

变更后：

- 检查发行版列表、版本、默认用户和 `/etc/os-release`。
- 验证关键目录、包管理器、网络端口和 GPU。
- 保留旧发行版或备份，直到新环境完成完整验收。
- 在删除任何旧数据前，至少执行一次真实恢复验证。

## 参考

- Microsoft Learn：[Basic commands for WSL](https://learn.microsoft.com/windows/wsl/basic-commands)
- Microsoft Learn：[Advanced settings configuration in WSL](https://learn.microsoft.com/windows/wsl/wsl-config)
- Microsoft Learn：[How to manage WSL disk space](https://learn.microsoft.com/windows/wsl/disk-space)
- Microsoft Learn：[Working across Windows and Linux file systems](https://learn.microsoft.com/windows/wsl/filesystems)
- Microsoft Learn：[Accessing network applications with WSL](https://learn.microsoft.com/windows/wsl/networking)
- Docker Docs：[Docker Desktop WSL 2 backend on Windows](https://docs.docker.com/desktop/features/wsl/)
- Docker Docs：[GPU support in Docker Desktop](https://docs.docker.com/desktop/features/gpu/)
