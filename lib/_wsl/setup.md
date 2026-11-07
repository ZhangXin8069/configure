# WSL 2 配置、迁移与发行版内开发环境

本文面向 Windows 10/11 + WSL 2，命令以 PowerShell 为主。WSL 发行版维护与 Docker Desktop 数据维护必须分开：Docker Desktop 自建发行版和 VHDX 由 Docker Desktop 管理，不要套用本文的发行版迁移步骤。Docker 与 WSL 的集成边界、容器生命周期见 [`../_docker/setup.md`](../_docker/setup.md)；发行版内开发环境见下文“发行版内开发环境（本库）”。

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

`wsl-v20261107` 记录的实际安装顺序如下。`--name` 与 `--move` 会改变发行版名称和 VHDX 位置，执行前确认目标名称未被占用、目标磁盘空间充足：

```powershell
wsl --update
wsl --list --online
wsl --install Ubuntu-26.04 --name env_zhangxin
wsl --manage env_zhangxin --move "F:\WSL"
wsl -d env_zhangxin -- cat /etc/os-release
```

`wsl --move` 期间不要启动该发行版或 Docker Desktop 中的相关任务；移动失败时先保留原 VHDX，不要手工修改注册表。`wsl --shutdown` 与 `wsl --unregister` 只作为维护步骤列出，执行前必须由用户显式确认。

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

## 发行版内开发环境（本库）

本章记录 `wsl-v20261107` 快照实际使用的发行版内配置，并把通用步骤回链到本库稳定入口。版本化快照会随机器更新，执行前先查看 [`../wsl-v20261107/setup.md`](../wsl-v20261107/setup.md) 与 [`../wsl-v20261107/env.sh`](../wsl-v20261107/env.sh) 的当前内容，不要只按本文历史示例操作。

来源标记：`wsl-v20261107` 表示 2026-11-07 机器安装记录；其余链接指向本库稳定文档。

### 用户、Git 与 SSH 初始化

来源：`wsl-v20261107`；通用边界见 [`../_git/setup.md`](../_git/setup.md)、[`../_ssh/setup.md`](../_ssh/setup.md)。

```bash
cd ~
git config --global user.name "zhangxin"
git config --global user.email "zhangxin8069@qq.com"

test -f ~/.ssh/id_ed25519 || \
  ssh-keygen -t ed25519 -a 64 -C "zhangxin8069@qq.com" -f ~/.ssh/id_ed25519
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub
cat ~/.ssh/id_ed25519.pub
```

- 先把公钥加入 GitLab/GitHub 账户，再执行 SSH clone；首次连接按提示核对主机指纹。
- `ssh-keygen` 不是幂等操作。已有 `~/.ssh/id_ed25519` 时不要重复生成，也不要在已有密钥时运行 `git_init.sh`。
- 私钥只保留在 `~/.ssh/`，不复制进仓库、聊天记录或镜像层。
- 需要当前 shell 立即加载密钥时：

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
ssh-add -l
```

### 克隆 configure 与三层环境加载

来源：`wsl-v20261107`；通用入口见 [`../_env/setup.md`](../_env/setup.md)。

```bash
git clone git@gitlab.itp.ac.cn:ZhangXin8069/configure.git ~/configure
ln -s ~/configure/lib/wsl-v20261107/env.sh ~/env.sh
source ~/configure/env.sh
```

`~/.bashrc` 与 `~/.zshrc` 按以下顺序加载，后加载者可以覆盖前面的变量：

```text
~/configure/env.sh      # 仓库通用入口：PATH、库路径、locale、别名
~/env-key.sh            # 本机密钥与令牌，不进入 Git，建议 600
~/env.sh                # 机器版本快照，指向 wsl-v20261107/env.sh
```

- `~/env.sh` 用符号链接跟随仓库更新；仓库目录移动或切换历史快照后链接会失效，需重新 `ln -s`。也可按 [`../_env/setup.md`](../_env/setup.md) 改为复制，并保留带时间戳的旧文件。
- `ln -s` 前先确认 `~/env.sh` 不存在；已存在时先移动到 `~/env.sh.bak.$(date +%Y%m%d-%H%M%S)`，不要直接覆盖。
- `~/env-key.sh` 只放本机密钥，权限建议 `600`；不得把真实 API key、令牌或带 userinfo 的代理 URL 写入仓库。
- 克隆后如需同步相邻仓库，可运行 `zg-all-pull.sh`；该命令会进入目标仓库调用 `gpull.sh`，先检查工作区状态，说明见 [`../_commands/setup.md`](../_commands/setup.md)。

验证当前 shell 的加载结果：

```bash
readlink -f ~/env.sh
ls -l ~/env-key.sh
bash --noprofile --norc -c 'source ~/configure/env.sh; command -v git; printf "%s\n" "$PATH"'
```

### Shell 与 Vim 部署

来源：`wsl-v20261107`；通用部署见 [`../_shell/setup.md`](../_shell/setup.md)、[`../_vim/setup.md`](../_vim/setup.md)。

```bash
source ~/configure/env.sh
sh_init.sh -z
vim_init.sh
```

等价显式路径：

```bash
bash ~/configure/bin/sh_init.sh -z
bash ~/configure/bin/vim_init.sh
```

- `sh_init.sh -z` 部署 `.zshrc` 与 `oh-my-zsh`；`-a` 同时部署 Bash、Zsh 与 oh-my-zsh，`-b` 只部署 `.bashrc`。重复执行会生成新的时间戳备份，不做原地合并。
- 快照把 Miniforge 的 zsh 写入 `~/.bashrc` 再执行 `sh_init.sh -z`：

```bash
printf '%s\n' "$HOME/miniforge3/bin/zsh" > ~/.bashrc
sh_init.sh -z
conda init zsh
```

  该写法让 Bash 登录会话直接切到 conda zsh，只适合已确定使用 Miniforge zsh 的机器。若需要仓库维护的 `.bashrc`，改用 `sh_init.sh -a`，不要覆盖后再部署。
- `vim_init.sh` 会先备份现有 `~/.vimrc`、`~/.vim`，再复制 `_vimrc` 与 `_vim`。`_vim/plugged` 是未配置 `.gitmodules` 的 gitlink，空目录时需联网执行 `:PlugInstall` 或复制完整插件副本。
- 部署完成后新开终端，或用 `exec zsh -l` 重新加载。

### Miniforge 与 conda

来源：`wsl-v20261107`；环境变量取自 [`../wsl-v20261107/env.sh`](../wsl-v20261107/env.sh)。

安装 Miniforge，并切换到清华 conda-forge 镜像：

```bash
wget -O /tmp/Miniforge3-Linux-x86_64.sh \
  https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash /tmp/Miniforge3-Linux-x86_64.sh
exec bash

conda config --remove channels conda-forge 2>/dev/null || true
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge/
conda config --set show_channel_urls yes
conda clean -i
```

更新 base 并安装工具链：

```bash
mamba update -n base -c conda-forge conda
mamba install conda-self zsh gfortran gxx make cmake htop btop nvtop netwatch tree nodejs texlive-core \
  "cuda-version=12.4.0" "cuda-nvcc" "cuda-libraries-dev" "cuda-nvml-dev" \
  "cuda-nvvp" "cuda-gdb" "python=3.12.4" "hdf5=2.2.0=mpi_openmpi*" cupy
```

- `cuda-version=12.4.0` 约束 CUDA 运行时与编译器版本；`cuda-nvcc` 提供 `nvcc`，CUDA 头文件位于 `$CONDA_PREFIX/targets/x86_64-linux/include`。
- `hdf5=2.2.0=mpi_openmpi*` 固定 MPI 变体；mpi4py、h5py、QUDA 必须使用同一 MPI，不能混用系统 OpenMPI 与 conda OpenMPI。
- `netwatch` 需要抓包权限。安装后执行：

```bash
b=$(readlink -f "$(which netwatch)") &&
sudo groupadd -f netwatch &&
sudo usermod -aG netwatch "$USER" &&
sudo chown root:netwatch "$b" &&
sudo chmod 0750 "$b" &&
sudo setcap 'cap_net_raw,cap_bpf,cap_perfmon+eip' "$b" &&
echo '重新登录后 netwatch 才能启动'
```

  组变更只对新登录会话生效；完成上述命令后退出并重新进入 WSL。`../wsl-v20261107/env.sh` 保留 `@NETWATCH@` 权限命令的注释块，并定义了 `alias iftop='sudo ~/miniforge3/bin/netwatch'`；别名在文件加载后即生效，但 `netwatch` 仍需 setcap 权限和重新登录才能运行。
- 让 zsh 自动加载 conda：

```bash
conda init zsh
exec zsh -l
```

- 版本快照在 conda base 激活后导出以下变量；`CONDA_PREFIX` 为空时这些路径会退化为 `/targets/...`，执行前先确认已激活 base：

```bash
export CUDA_PATH=$CONDA_PREFIX/targets/x86_64-linux
export CPLUS_INCLUDE_PATH=$CUDA_PATH/include:$CPLUS_INCLUDE_PATH
export PATH=$CONDA_PREFIX/nvvm/bin:$PATH
export HDF5_MPI="ON"
export HDF5_DIR=$CONDA_PREFIX
```

验证：

```bash
conda --version
mamba --version
python --version
command -v nvcc
nvcc --version
nvidia-smi
```

### 源码编译 pip 依赖

来源：`wsl-v20261107`；见 [`../wsl-v20261107/setup.md`](../wsl-v20261107/setup.md)。这些包在 conda 环境中源码编译，以匹配 conda 的 MPI、HDF5 与 CUDA。

```bash
python -m pip install --upgrade pip
pip install mpi4py --no-binary=mpi4py --no-cache-dir
pip install h5py --no-binary=h5py --no-cache-dir
pip install tilelang --no-binary=tilelang --no-cache-dir
pip install torch torchvision --no-binary=torch --no-cache-dir
pip install scipy cython seaborn opt_einsum lsqfit
```

- 编译前确认 `mpicc`、`mpicxx`、`h5cc` 均来自当前 conda 环境：

```bash
command -v mpicc mpicxx h5cc
mpicc -show
h5cc -showconfig | grep -E 'MPI|Version'
```

- `mpi4py` 依赖 MPI 头文件和编译器；`h5py` 依赖 `HDF5_MPI=ON` 与 `HDF5_DIR`。变量缺失时会在构建阶段失败，而不是安装完成后才暴露。
- `torch` 源码编译耗时且占用大量内存和磁盘。WSL 内存不足时先提高 `.wslconfig` 的 `memory`/`swap`，并降低并发编译数；若不需要源码构建，可改用与 CUDA 12.4 匹配的官方 wheel，但不要与源码构建的 `torchvision` 混装。
- `--no-binary=torch` 只约束 `torch`；`torchvision` 必须与已安装的 `torch` 版本匹配。
- 验证：

```bash
python - <<'PY'
import mpi4py, h5py, torch, torchvision
print('mpi4py', mpi4py.__version__)
print('h5py', h5py.__version__)
print('torch', torch.__version__, 'cuda', torch.cuda.is_available())
print('torchvision', torchvision.__version__)
PY
```

### QUDA 与 PyQUDA

来源：`wsl-v20261107`；见 [`../wsl-v20261107/setup.md`](../wsl-v20261107/setup.md)。

QUDA 使用 CUDA 12.4、MPI 和 SM80 架构源码构建：

```bash
cd ~
unset NVCC_PREPEND_FLAGS
mkdir -p "$CONDA_PREFIX/targets/x86_64-linux/include/cccl"
git clone https://github.com/lattice/quda.git
pushd quda
mkdir -p build
pushd build
cmake .. \
  -DQUDA_DIRAC_DOMAIN_WALL=OFF \
  -DQUDA_CLOVER_DYNAMIC=OFF \
  -DQUDA_CLOVER_RECONSTRUCT=OFF \
  -DQUDA_DIRAC_NDEG_TWISTED_CLOVER=OFF \
  -DQUDA_DIRAC_NDEG_TWISTED_MASS=OFF \
  -DQUDA_DIRAC_TWISTED_CLOVER=OFF \
  -DQUDA_DIRAC_TWISTED_MASS=OFF \
  -DQUDA_INTERFACE_MILC=OFF \
  -DQUDA_LAPLACE=ON \
  -DQUDA_MULTIGRID=ON \
  -DQUDA_GPU_ARCH=sm_80 \
  -DQUDA_MPI=ON
cmake --build . -j6
cmake --install .
popd
popd

export QUDA_PATH="$HOME/quda/build"
pip install PyQUDA
```

- `QUDA_GPU_ARCH=sm_80` 对应 A100 / RTX 30 系列；其他 GPU 架构应改为实际 compute capability，不要盲目沿用。
- `QUDA_MPI=ON` 要求 MPI 编译器可用，并与 mpi4py、h5py 使用同一实现；`mpicc -show` 应指向 conda 环境。
- `unset NVCC_PREPEND_FLAGS` 用于移除 conda `cuda-nvcc` 注入的编译参数；残留时 CMake 配置或编译可能报错。
- `$CONDA_PREFIX/targets/x86_64-linux/include/cccl` 是 CUDA 12.4 工具链查找 CCCL/Thrust 头文件的目录。该目录已由 `cuda-cccl` 提供时无需重复创建。
- 构建并发 `-j6` 是快照值；内存不足出现退出码 137 时降低并发，不要直接扩大 swap 掩盖 OOM。
- `QUDA_PATH` 必须在安装 PyQUDA 前导出；PyQUDA 依赖该路径查找 QUDA 库。
- 验证：

```bash
python -c 'import pyquda; print(pyquda.__version__)'
ls -l "$QUDA_PATH/lib/libquda.so"
```

常见构建问题：

| 现象 | 检查 |
|---|---|
| CMake 找不到 CUDA | `CUDA_PATH`、`command -v nvcc`、`$CONDA_PREFIX` 是否已激活 |
| `NVCC_PREPEND_FLAGS` 导致参数冲突 | `unset NVCC_PREPEND_FLAGS` 后删除 `build/` 重新 configure |
| 找不到 `cuda/std/...` 或 CCCL 头 | `$CONDA_PREFIX/targets/x86_64-linux/include/cccl` |
| MPI 链接错误 | `mpicc -show`、`mpi4py`/`h5py`/QUDA 是否使用同一 MPI |
| 编译被 OOM 杀死（137） | 降低 `-j`，检查 `.wslconfig` 与宿主内存压力 |

### Windows 数据盘与 `/mnt/f/Data` 互操作

来源：`wsl-v20261107`，见 [`../wsl-v20261107/setup.md`](../wsl-v20261107/setup.md)；路径差异与文件系统边界见 [`../_docker/setup.md`](../_docker/setup.md)、[`../_windows/setup.md`](../_windows/setup.md)。

Windows 侧先创建数据目录：

```powershell
New-Item -ItemType Directory -Force -Path 'F:\Data\public' | Out-Null
```

WSL 内建立稳定入口：

```bash
mkdir -p /mnt/f/Data/public
ln -s /mnt/f/Data ~/data
sudo ln -s /mnt/f/Data/public /
ls -ld ~/data /public
```

- 同一路径的三种写法：Windows `F:\Data`、WSL `/mnt/f/Data`、Git Bash `/f/Data`。脚本和文档中不要混用。
- `/mnt/f` 是 drvfs 挂载，跨文件系统 I/O 明显慢于 ext4。编译目录、conda 环境、Git 仓库和高频数据库应留在 `/home/<用户>`；大文件、数据集和 Windows 应用共享内容放在数据盘。
- 需要 Linux 权限语义时，在 `/etc/wsl.conf` 的 `[automount]` 启用 `metadata,umask=22,fmask=11`，并重新验证挂载权限；NTFS 权限模型与 ext4 不等价。
- 建立符号链接需要目标存在且当前用户有权限；`sudo ln -s` 只用于确实需要根目录入口的场景，不要把整个数据盘暴露给不可信进程。
- 不要把正在运行的 `ext4.vhdx`、备份归档或同步盘目录放到 `/mnt/f` 后长期读写；休眠、拔盘和同步冲突可能损坏文件系统。

### StarVPN 与 WSL 内 OpenSSH server

来源：`wsl-v20261107`，见 [`../wsl-v20261107/setup.md`](../wsl-v20261107/setup.md)；SSH 安全边界见 [`../_ssh/setup.md`](../_ssh/setup.md)、[`../_zerotier/setup.md`](../_zerotier/setup.md)。

安装 StarVPN：

```bash
wget -O /tmp/starvpn-install.sh https://file.starvpn.cn/stars/shell/prod/linux/install.sh
STARVPN_VERSION=6.1.3 sudo -i sh /tmp/starvpn-install.sh
sudo stars login
sudo stars info
sudo stars list
```

- 安装脚本来自第三方站点并以 root 执行；执行前核对来源和脚本内容，不要在生产机器上无条件运行。
- `stars login` 为交互式登录，不要把密码或令牌写入命令历史、脚本或仓库。
- VPN 可能修改默认路由和 DNS。使用 `networkingMode=mirrored` 时，需重新验证 Windows 与 WSL 的 `localhost` 转发、端口和防火墙行为；连接异常时先看 `stars info` 与路由表。

安装并启用 OpenSSH server：

```bash
sudo apt update
sudo apt install openssh-server
sudo systemctl enable --now ssh
sudo systemctl status ssh --no-pager
ss -tlnp | grep ':22'
```

- WSL 内 systemd 必须已启用（`/etc/wsl.conf` 的 `[boot] systemd=true`），否则 `systemctl` 不可用，需改用 `service ssh start` 并接受进程生命周期限制。
- Windows NAT 模式下，Windows 侧可通过 `localhost:22` 访问 WSL；局域网其他主机访问需要端口转发或 mirrored 网络，并单独配置 Windows Firewall 规则。
- Windows 自身可能已运行 OpenSSH server 并占用 22 端口；先检查 `Get-Service sshd` 和 `netstat -ano`，不要直接改端口冲突的一方。
- 只对可信网络开放，优先使用密钥认证并禁用密码登录；需要跨主机访问时优先走 ZeroTier 等受控网络，不要把 SSH 直接暴露到公网。
- 克隆发行版会复制 SSH host key；若克隆体会同时对外提供 SSH，应按发行版规范重新生成 host key，避免与源发行版冲突。

### 其他本库入口

| 需求 | 文档 |
|---|---|
| Node.js 22+ 安装与版本检查 | [`../_node-js/setup.md`](../_node-js/setup.md) |
| Command Code（Linux/WSL） | [`../_command-code/setup.md`](../_command-code/setup.md) |
| Shell 与 oh-my-zsh 部署 | [`../_shell/setup.md`](../_shell/setup.md) |
| Vim 部署与插件状态 | [`../_vim/setup.md`](../_vim/setup.md) |
| Git 身份、别名与同步命令 | [`../_git/setup.md`](../_git/setup.md) |
| SSH 密钥、agent 与主机别名 | [`../_ssh/setup.md`](../_ssh/setup.md) |
| APT/Python 包清单 | [`../_package/setup.md`](../_package/setup.md) |
| 用户命令总索引 | [`../_commands/setup.md`](../_commands/setup.md) |
| Docker Desktop 与容器 | [`../_docker/setup.md`](../_docker/setup.md) |
| ZeroTier 虚拟网络 | [`../_zerotier/setup.md`](../_zerotier/setup.md) |
| Windows 批处理与 PowerShell | [`../_windows/setup.md`](../_windows/setup.md) |

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
