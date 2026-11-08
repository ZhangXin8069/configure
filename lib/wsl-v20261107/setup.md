# WSL 开发环境配置（wsl-v20261107）

本目录记录 Windows + WSL 2 上的一套完整开发环境：安装 Ubuntu 26.04 发行版并迁移到独立磁盘，
在发行版内部署本库、Miniforge/conda 工具链、CUDA 12.4、QUDA/PyQUDA 与常用桌面/网络组件。
命令按首次部署顺序排列，已在目标机器执行过的安装命令保留为注释时可作为复现依据。

## 文件

| 文件 | 用途 |
|---|---|
| `setup.md` | 本文档：从 Windows 安装 WSL 到发行版内编译 QUDA 的完整步骤 |
| `env.sh` | 机器级环境快照：CUDA/CPP/HDF5 变量与 netwatch 权限块，部署为 `~/env.sh` |

相关稳定入口：

| 主题 | 文档 |
|---|---|
| WSL 2 主机侧生命周期（`.wslconfig`、`/etc/wsl.conf`、导入导出、磁盘压缩） | [`../_wsl/setup.md`](../_wsl/setup.md) |
| 三层环境加载与版本快照 | [`../_env/setup.md`](../_env/setup.md) |
| Bash/Zsh/oh-my-zsh 部署 | [`../_shell/setup.md`](../_shell/setup.md) |
| Vim 部署与插件 | [`../_vim/setup.md`](../_vim/setup.md) |
| Git 身份、别名与忽略规则 | [`../_git/setup.md`](../_git/setup.md) |
| SSH 密钥、agent 与主机别名 | [`../_ssh/setup.md`](../_ssh/setup.md) |
| Node.js 与 Command Code | [`../_node-js/setup.md`](../_node-js/setup.md)、[`../_command-code/setup.md`](../_command-code/setup.md) |
| APT/Python 依赖清单 | [`../_package/setup.md`](../_package/setup.md) |
| Docker Desktop 集成 | [`../_docker/setup.md`](../_docker/setup.md) |
| ZeroTier | [`../_zerotier/setup.md`](../_zerotier/setup.md) |
| 用户命令总索引 | [`../_commands/setup.md`](../_commands/setup.md) |

## 环境基线

| 项 | 值 |
|---|---|
| 宿主 | Windows 10/11，WSL 2 |
| 发行版 | Ubuntu 26.04，名称 `env_zhangxin` |
| 发行版存储 | `F:\WSL`（Windows 路径） |
| Linux 用户 | `zhangxin` |
| Conda | `/home/zhangxin/miniforge3`（base 环境） |
| Python | 3.12.4 |
| CUDA | 12.4.0（conda-forge 工具链，不使用系统级 Linux 驱动） |
| 编译器 | `gfortran`、`gxx` |
| MPI/HDF5 | conda-forge `hdf5=2.2.0=mpi_openmpi*` |
| GPU 架构 | `sm_80` |
| 数据盘 | Windows `F:\Data`，WSL 内 `/mnt/f/Data` |

WSL 内不安装 NVIDIA Linux 显示驱动；GPU 由 Windows 驱动经 WSL 透传，宿主机侧检查见
[`../_wsl/setup.md`](../_wsl/setup.md) 的“文件系统、网络与 GPU”一节。

## 1. 安装与迁移发行版

在 Windows PowerShell 中执行：

```powershell
wsl --update
wsl -l -o
wsl --install Ubuntu-26.04 --name env_zhangxin
wsl --manage env_zhangxin --move "F:\WSL"
```

说明：

- `wsl --install` 可能要求重启 Windows 或完成首次用户创建；Ubuntu 26.04 的可用名称以
  `wsl -l -o` 的实际输出为准。
- `--move` 前先退出所有 WSL 会话；迁移过程中不要运行 Docker Desktop 或写入该发行版。
- 迁移失败时保留原 VHDX，不要手工移动或改写注册表路径。发行版导入、备份与磁盘压缩的完整边界见
  [`../_wsl/setup.md`](../_wsl/setup.md)。

以下命令在原始记录中保留为注释，按需使用：

```powershell
# 进入发行版
# wsl -d env_zhangxin
# 关闭全部 WSL 实例（会同时停止 Docker Desktop 的 WSL 后端）
# wsl --shutdown
# 注销发行版：永久删除注册信息和发行版存储，必须先导出并验证备份
# wsl --unregister env_zhangxin
```

`wsl --unregister`、删除 VHDX、磁盘压缩都属于不可逆或高风险操作，执行前必须由用户显式确认。

## 2. 用户、Git 与仓库

进入发行版后执行：

```bash
cd ~/
git config --global user.name "zhangxin"
git config --global user.email "zhangxin8069@qq.com"
ssh-keygen -t ed25519 -C "zhangxin8069@qq.com"
git clone git@gitlab.itp.ac.cn:ZhangXin8069/configure.git
ln -s ~/configure/lib/wsl-v20261107/env.sh ~/
source ~/configure/env.sh
vim_init.sh
```

说明：

- `ssh-keygen` 不是幂等操作。已有 `~/.ssh/id_ed25519` 时跳过，改用 `ssh-add` 加载并将公钥登记到
  GitLab；完整流程见 [`../_ssh/setup.md`](../_ssh/setup.md)。
- `ln -s ... ~/` 生成 `~/env.sh`，指向本目录的机器级快照。加载顺序为
  `~/configure/env.sh` → `~/env-key.sh` → `~/env.sh`，后加载者可覆盖前面的变量，见
  [`../_env/setup.md`](../_env/setup.md)。
- `vim_init.sh` 会把现有 `~/.vimrc`、`~/.vim` 备份为带时间戳的副本，再部署仓库版本，见
  [`../_vim/setup.md`](../_vim/setup.md)。

## 3. Miniforge 与 conda 工具链

下载并安装 Miniforge：

```bash
wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh
bash
```

重新进入 Bash 使安装器写入的初始化生效，然后配置镜像并安装工具链：

```bash
conda config --remove channels conda-forge
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge/
conda config --set show_channel_urls yes
conda clean -i
mamba update -n base -c conda-forge conda
```

```bash
mamba install conda-self zsh gfortran gxx make cmake htop btop nvtop netwatch tree nodejs \
  "cuda-version=12.4.0" "cuda-nvcc" "cuda-libraries-dev" "cuda-nvml-dev" \
  "cuda-nvvp" "cuda-gdb" "python=3.12.4" "hdf5=2.2.0=mpi_openmpi*" cupy
```

TeX 不通过 conda 安装，改用系统包：

```bash
sudo apt install texlive-xetex
```

说明：

- `conda config --remove channels conda-forge` 用于移除安装器默认的完整频道 URL，再显式加入清华
  conda-forge 镜像；镜像不可达时回退官方频道。
- `cuda-version=12.4.0` 与 `cuda-nvcc` 等包把 CUDA 工具链装在 conda 前缀中，避免在 WSL 内安装
  系统级 CUDA 仓库和 Linux 显示驱动。
- `hdf5=2.2.0=mpi_openmpi*` 选择 MPI 版本，供后续 `mpi4py`、`h5py` 源码编译使用。
- conda-forge 的 `texlive-core` 非常鸡肋：只提供极简 TeX 二进制和少量宏包，缺 XeLaTeX 常用组件，
  还容易与系统 TeX Live 混用产生 `PATH` 与版本冲突，因此不放入 mamba 列表；XeLaTeX 统一用
  `sudo apt install texlive-xetex`。
- `netwatch` 需要额外能力，见下一节。
- 回滚前先查看 base 历史：

```bash
conda list -n base --revisions
```

## 4. netwatch 权限

`netwatch` 需要抓包与性能事件能力；安装后执行：

```bash
b=$(readlink -f "$(which netwatch)") && \
  sudo groupadd -f netwatch && \
  sudo usermod -aG netwatch "$USER" && \
  sudo chown root:netwatch "$b" && \
  sudo chmod 0750 "$b" && \
  sudo setcap 'cap_net_raw,cap_bpf,cap_perfmon+eip' "$b" && \
  echo 'Log in again to join the group: netwatch cannot start until you do'
```

说明：

- 组权限只在重新登录后生效；未重新登录前 `netwatch` 无法启动。
- `env.sh` 中保留同一命令的注释块，便于换机器时复用。
- 同文件定义的 `alias iftop="sudo ${HOME}/miniforge3/bin/netwatch"` 依赖该路径；Miniforge 安装到其他
  前缀时需要同步修改。

## 5. Shell 初始化

```bash
echo ${HOME}'/miniforge3/bin/zsh' > ~/.bashrc && sh_init.sh -z && conda init zsh
```

说明：

- `>` 会截断并覆盖 `~/.bashrc`，使其在 Bash 登录时直接启动 Miniforge 的 Zsh。若还需要仓库的
  Bash 配置，应先备份，或在之后用 `sh_init.sh -b` 重新部署；两个动作会互相覆盖，顺序需自行确定。
- `sh_init.sh -z` 部署 `~/.zshrc` 与 oh-my-zsh，不处理 `~/.bashrc`，见
  [`../_shell/setup.md`](../_shell/setup.md)。
- `conda init zsh` 把 conda 初始化块写入 `~/.zshrc`；脚本重复执行会追加重复块，必要时先清理。

## 6. Python 依赖（源码编译）

以下命令均在已激活的 conda base 环境中执行：

```bash
pip install mpi4py --no-binary=mpi4py --no-cache-dir
pip install h5py --no-binary=h5py --no-cache-dir
pip install tilelang --no-binary=tilelang --no-cache-dir
pip install torch torchvision --no-binary=torch --no-cache-dir
pip install scipy cython seaborn opt_einsum lsqfit
```

说明：

- `--no-binary=<包名>` 只对指定包强制源码编译：`torch` 行中的 `torchvision` 不受该约束，仍可能安装二进制轮子，需自行确认版本匹配。
- `torch` 源码编译耗时和磁盘占用都远高于二进制轮子；只在确实需要匹配本地 CUDA/MPI 时使用。
- `--no-cache-dir` 避免在 WSL VHDX 中保留大型构建缓存，代价是重装时需要重新下载。

## 7. QUDA 与 PyQUDA

先更新相邻仓库，再克隆 QUDA：

```bash
zg-all-pull.sh
git clone https://github.com/lattice/quda.git
```

构建：

```bash
unset NVCC_PREPEND_FLAGS
mkdir -p $CONDA_PREFIX/targets/x86_64-linux/include/cccl
pushd ./quda
mkdir -p build && pushd build
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
# cmake --build . -j${nproc}
cmake --build . -j6
cmake --install .
popd
popd
```

安装 Python 绑定：

```bash
export QUDA_PATH=$HOME/quda/build
pip install PyQUDA
```

说明：

- `-DQUDA_GPU_ARCH=sm_80` 必须与实际 GPU 架构匹配；换成其他显卡时同时调整该值和 CUDA 工具链。
- `unset NVCC_PREPEND_FLAGS` 用于去掉 conda `cuda-nvcc` 注入的编译参数，否则 QUDA 的 CMake 探测
  可能失败。
- `mkdir -p $CONDA_PREFIX/targets/x86_64-linux/include/cccl` 为 CCCL 头文件准备目录；目录已存在时
  该命令无副作用。
- `cmake --build . -j6` 使用保守并发，避免在共享或内存受限的 WSL 虚拟机中触发 OOM。
- 未显式指定 `CMAKE_INSTALL_PREFIX` 时，`cmake --install .` 使用 CMake 的默认前缀；需要写入系统
  目录时应自行加 `sudo` 或改用 `$CONDA_PREFIX`。`QUDA_PATH` 指向构建树，PyQUDA 按该路径查找库。
- `zg-all-pull.sh` 会进入相邻仓库执行拉取，行为与风险见 [`../_commands/setup.md`](../_commands/setup.md)。

## 8. Windows 数据盘与互操作

```bash
md /mnt/f/Data/public
ln -s /mnt/f/Data ~/data
sudo ln -s /mnt/f/Data/public /
```

说明：

- `md` 是 `cmd.exe` 内建命令，不是 WSL 可执行程序。在 WSL 中应使用
  `mkdir -p /mnt/f/Data/public`；在 `cmd.exe` 中则使用 `md F:\Data\public`。原始记录保留 `md` 写法。
- `ln -s /mnt/f/Data ~/data` 建立家目录入口；`sudo ln -s /mnt/f/Data/public /` 在根目录建立
  `/public`。两者都是跨文件系统符号链接，Windows 侧移动或重命名目标后链接会失效。
- Windows 盘通过 `/mnt/<盘符>` 访问，权限与性能语义不同于 ext4。高频编译、数据库和 Git 操作应放在
  WSL 的 `/home/<用户>`；需要 Windows 应用直接读取的数据才放在 `/mnt/f`。路径差异见
  [`../_wsl/setup.md`](../_wsl/setup.md) 的“文件系统、网络与 GPU”一节。

## 9. StarVPN

```bash
wget -O /tmp/starvpn-install.sh https://file.starvpn.cn/stars/shell/prod/linux/install.sh && \
  STARVPN_VERSION=6.1.3 sudo -i sh /tmp/starvpn-install.sh
sudo stars login
sudo stars info
sudo stars list
```

说明：

- 安装脚本以 root 身份从网络获取并执行；执行前应确认下载来源和脚本内容，不要把凭据写入命令历史或
  仓库。
- `sudo -i` 默认重置环境变量，`STARVPN_VERSION=6.1.3` 可能不会传递到脚本；安装后用
  `stars info` 确认实际版本。
- `stars login` 为交互式登录，凭据只保存在本机，不进入 Git。

## 10. WSL 内 OpenSSH 服务

```bash
sudo apt update
sudo apt install openssh-server
sudo systemctl start ssh
sudo systemctl enable ssh
```

说明：

- `systemctl` 要求发行版启用 systemd，即在 `/etc/wsl.conf` 中设置 `[boot] systemd=true` 并重启
  发行版；配置方法见 [`../_wsl/setup.md`](../_wsl/setup.md)。
- 仅启动 `sshd` 不等于可从 Windows 宿主或局域网访问；还需要 Windows 防火墙规则和端口转发。对外
  暴露前先确认监听地址、认证方式和密钥权限，见 [`../_ssh/setup.md`](../_ssh/setup.md)。
- 使用密钥认证，避免在 WSL 中开启密码登录后直接暴露到网络。

## 11. 验证

```bash
wsl --version
wsl -l -v
conda --version
mamba --version
python -c "import mpi4py, h5py, torch, cupy; print('python deps ok')"
nvidia-smi
printf 'CUDA_PATH=%s\n' "$CUDA_PATH"
printf 'QUDA_PATH=%s\n' "$QUDA_PATH"
git -C ~/configure status --short
```

预期：发行版为 `VERSION 2` 且状态 `Running`；`nvidia-smi` 能识别 Windows 透传的 GPU；`CUDA_PATH`
指向 `$CONDA_PREFIX/targets/x86_64-linux`；`QUDA_PATH` 指向 `~/quda/build`。`nvidia-smi` 失败时先
检查 Windows 驱动与 WSL 更新，不要安装 Linux 显示驱动。

## `env.sh` 内容

| 变量/别名 | 值 | 说明 |
|---|---|---|
| `CUDA_PATH` | `"${CONDA_PREFIX}/targets/x86_64-linux"` | 依赖 conda 已激活；未激活时展开为 `/targets/...` |
| `CPLUS_INCLUDE_PATH` | `"${CUDA_PATH}/include":${CPLUS_INCLUDE_PATH}` | 供 C++ 扩展编译 |
| `PATH` | `"${CONDA_PREFIX}/nvvm/bin":${PATH}` | NVVM 工具 |
| `HDF5_MPI` | `ON` | 让 h5py 构建启用 MPI |
| `HDF5_DIR` | `"${CONDA_PREFIX}"` | HDF5 安装前缀 |
| `iftop` | `sudo ${HOME}/miniforge3/bin/netwatch` | 依赖 netwatch 的 setcap 权限 |

文件开头的 `cd ${HOME}` 会在每次 source 时切换当前目录；交互式使用时注意它会覆盖调用者的工作目录。
`@NETWATCH@` 块是注释掉的权限配置，`@EXPORT@` 块是实际生效的环境变量。导出值统一用双引号包裹；
`CPLUS_INCLUDE_PATH` 与 `PATH` 的既有部分按原样追加，语义与未加引号的旧写法一致。

## 风险与回滚

| 操作 | 风险 | 回滚/边界 |
|---|---|---|
| `wsl --unregister env_zhangxin` | 永久删除发行版注册信息和存储 | 先 `wsl --export` 并验证恢复；不可撤销 |
| `wsl --manage ... --move` | 迁移中断可能留下不可用 VHDX | 迁移前 `wsl --shutdown`，保留原盘；失败时不要手工改注册表 |
| `wsl --shutdown` | 停止全部发行版和 Docker Desktop WSL 后端 | 先保存构建与写入任务 |
| 磁盘压缩 | 压缩期间写入可能损坏 VHDX | 先备份、`fstrim`、关闭占用进程 |
| `echo ... > ~/.bashrc` | 覆盖已部署的 Bash 配置 | 先备份；需要时用 `sh_init.sh -b` 重新部署 |
| `mamba install` 升级 base | 可能破坏现有 Python 依赖 | 用 `conda list -n base --revisions` 查看并回退 |
| 源码编译 `torch`/QUDA | 耗时长、占用磁盘、架构不匹配会失败 | 清理 `build/` 与 pip 缓存后重试；必要时改用二进制轮子 |
| `setcap` + `chmod 0750` | 授予 netwatch 抓包能力 | 用 `setcap -r` 撤销，或恢复原权限 |
| StarVPN 安装脚本 | 以 root 执行网络脚本 | 执行前审阅；凭据仅保存在本机 |
| OpenSSH 对外监听 | 暴露登录面 | 使用密钥、限制监听地址和防火墙 |

## 参考

- WSL 主机侧配置、导入导出与磁盘维护：[`../_wsl/setup.md`](../_wsl/setup.md)
- 环境加载链：[`../_env/setup.md`](../_env/setup.md)
- Shell/Vim/SSH/Git：[`../_shell/setup.md`](../_shell/setup.md)、[`../_vim/setup.md`](../_vim/setup.md)、[`../_ssh/setup.md`](../_ssh/setup.md)、[`../_git/setup.md`](../_git/setup.md)
- Docker Desktop 与 WSL 集成：[`../_docker/setup.md`](../_docker/setup.md)
- ZeroTier 在 WSL 中的 systemd 要求：[`../_zerotier/setup.md`](../_zerotier/setup.md)
- 用户命令索引：[`../_commands/setup.md`](../_commands/setup.md)
