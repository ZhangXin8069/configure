# 环境配置操作

## 三层环境

| 层级 | 文件 | 职责 |
|---|---|---|
| 仓库通用入口 | `env.sh` | 冲突预检（当前暂停）、PATH、库路径、locale、Git 别名、通用别名 |
| 机器版本快照 | `lib/<name>-vYYYYMMDD>/env.sh` | module、conda、编译器、工具链和机器专属路径 |
| 用户本机覆盖 | `~/env-key.sh`、`~/env.sh` | 密钥、登录令牌和不在仓库中维护的本机参数 |

`~/.bashrc` 和 `~/.zshrc` 当前 source 顺序为：

```text
~/configure/env.sh
~/env-key.sh
~/env.sh
```

后加载文件可以覆盖前面的变量。把机器配置是否覆盖仓库通用值的决定写清楚，不要依赖偶然顺序。

## 通用入口

```bash
source ./env.sh
command -v git
printf '%s\n' "$PATH"
printf '%s\n' "$LD_LIBRARY_PATH"
```

`env.sh` 通过自身位置解析仓库根，适合部署在 `$HOME/configure` 之外。大规模冲突预检当前按用户要求
注释暂停，其余 PATH、locale、alias 和 function 继续加载；成功后导出
`_CONFIGURE_ENV_LOADED_PATH`。当前 Shell 或子 Shell 再次 source 且路径完全匹配时直接幂等返回。
它会避免重复加入仓库 `bin/` 和 `lib/`，但不能阻止机器 `env.sh` 自己重复追加路径。
在 screen 内加载时还会把继承的基础/哑终端 `TERM` 归一化为可用的 256 色 screen term。

## conda base 快捷入口 `zda`

`env.sh` 定义别名 `zda`，指向 `_zda_activate_base`：激活 `${HOME}/miniforge3` 的
conda base，并把 base 里的开发路径注入对应环境变量，同时清掉会遮蔽 base 的旧别名。

### 激活与失败分支

| 情形 | 行为 |
|---|---|
| `$HOME/miniforge3/etc/profile.d/conda.sh` 可读 | source 它并 `conda activate base`，打印 `zda: 已激活 <prefix>（base）` |
| 已在 base（`CONDA_PREFIX` 与 `$HOME/miniforge3` 同一目录） | 跳过激活，但仍补做变量同步与别名清理，保证旧 shell 生效 |
| 目录或 `conda.sh` 缺失 | 打印 `[WARN]`，再输出 `bin/_zda-guide.txt` 的安装指南，返回 1 |
| `conda activate base` 失败 | 打印 `[WARN]` 并返回 1，不中断调用方 shell |
| 激活后 `CONDA_PREFIX` 不符合预期 | 打印实际值与期望值并返回 1 |

### 环境变量声明

`zda` 同步下列变量，规则是**目录/可执行必须真实存在**、**conda 项前置**、**旧值保留在后面**、
**重复项按物理路径去重**（`lib/python3.1 -> python3.12` 只保留一条），可重复执行。
唯一权威清单在 `env.sh` 的 `# zda 注入的环境变量声明` 注释块，`env.test.sh` 会解析该块
逐项核对是否真的被设置，防止声明与实现漂移。

| 变量 | 注入内容 |
|---|---|
| `PATH` | `bin`、`sbin`、`nvvm/bin` |
| `LD_LIBRARY_PATH`、`LIBRARY_PATH` | `lib`、`lib64`、`targets/*/lib`（`_ZDA_SKIP_LIBPATH=1` 时跳过） |
| `CPATH`、`CPLUS_INCLUDE_PATH`、`C_INCLUDE_PATH` | `include`、`targets/*/include` |
| `PYTHONPATH` | `lib/python*/site-packages` |
| `PKG_CONFIG_PATH` | `lib/pkgconfig`、`share/pkgconfig` |
| `CMAKE_PREFIX_PATH` | 前缀根 |
| `MANPATH`、`ACLOCAL_PATH` | `share/man`、`man` / `share/aclocal` |

CUDA：

| 变量 | 值 |
|---|---|
| `CUDA_PATH`、`CUDA_HOME`、`CUDA_ROOT`、`CUDAToolkit_ROOT` | `targets/<arch>`（CMake ≥3.17 认 `CUDAToolkit_ROOT`，其余工具链各认一个） |
| `CUDA_INCLUDE_PATH` | `targets/<arch>/include` |
| `CUDA_LIBRARY_PATH` | `targets/<arch>/lib`、`targets/<arch>/lib/stubs` |
| `CUDACXX` | `bin/nvcc` |

MPI（存在 `bin/mpicc` 时整体启用）：

| 变量 | 值 |
|---|---|
| `MPI_HOME`、`OPENMPI_ROOT`、`OPAL_PREFIX` | 前缀根 |
| `MPICC`、`MPICXX`、`MPIF77`、`MPIF90`、`MPIFORT` | `bin/` 下的同名包装器（逐个判存在） |
| `MPI_INCLUDE_PATH`、`MPI_LIBRARY_PATH` | `include`、`lib` |
| `OMPI_CC`、`OMPI_CXX`、`OMPI_FC` | 前缀里的 conda 编译器包装（`x86_64-conda-linux-gnu-*`，缺失回退 `gcc`/`g++`/`gfortran`） |
| `OMPI_ALLOW_RUN_AS_ROOT`、`OMPI_ALLOW_RUN_AS_ROOT_CONFIRM`、`MPI_ALLOW_RUN_AS_ROOT` | `1`（与 `docker-*` 快照一致） |

HDF5 与编译器：

| 变量 | 值 |
|---|---|
| `HDF5_DIR`、`HDF5_ROOT` | 前缀根（存在 `include/hdf5.h` 或 `include/hdf5/` 时） |
| `HDF5_MPI`、`HDF5_INCLUDE_PATH`、`HDF5_LIBRARY_PATH` | `ON`、`include`、`lib` |
| `CC`、`CXX`、`CPP`、`FC`、`F77` | 前缀内的 `x86_64-conda-linux-gnu-*`（不可用时回退 `cc`/`c++`/`cpp`/`gfortran`）；已有值若已指向该前缀则保持不变 |
| `GCC_ROOT`、`NCURSES_ROOT`、`PYTHON_ROOT`、`HWLOC_ROOT`、`UCX_ROOT`、`PMIX_ROOT`、`LIBEVENT_ROOT` | 前缀根，各自按特征文件/目录做门禁（沿用 `lib/snsc-v20260817/env.sh` 的 `*_ROOT` 命名） |

说明：

- **不设 `CMAKE_ROOT`**：那是 CMake 自己由二进制位置推导的内部变量，写环境变量没有意义，
  真正生效的是 `CMAKE_PREFIX_PATH`。
- `targets/*` 是按架构目录（如 `x86_64-linux`），`nvcc`、CUDA 头与 stub 库都在这里；
  `CUDA_LIBRARY_PATH` 同时包含 `lib/stubs`，链接期才能在没有驱动的机器上解析 CUDA 符号。
- `CUDAToolkit_ROOT` 指向 `targets/<arch>` 时 CMake 能直接 `find_package(CUDAToolkit)`；
  实测 `CUDAToolkit_FOUND=TRUE VER=12.4.131`、`MPI_FOUND=TRUE`、`HDF5_FOUND=TRUE`。
- `OMPI_CC`/`OMPI_CXX`/`OMPI_FC` 显式指向 conda 编译器，避免 `mpicc` 落到系统 `gcc`
  造成"MPI 头来自 conda、C++ ABI 来自系统"的混编。
- `CC`/`CXX`/`FC` 只在当前值不指向该前缀时才改写：`conda activate` 已经设过
  `x86_64-conda-linux-gnu-cc` 时不会重复覆盖。
- `h5cc`/`h5pcc`/`h5fc`/`h5c++` 依赖 `pkg-config`；base 未装时它们会报
  `pkg-config: not found`。该包已列入 [`../_wsl/setup.md`](../_wsl/setup.md) 工具链的
  `mamba install` 清单，随 base 一起装；手工补装用 `mamba install pkg-config`
  （这几个是包装器，`h5py`、`find_package(HDF5)` 和 `zda` 都不需要它）。
- `_ZDA_SKIP_LIBPATH=1` 时跳过 `LD_LIBRARY_PATH`/`LIBRARY_PATH` 注入，其余变量照常。
  HPC 或 module 环境里 conda 的 `libstdc++` 可能遮蔽系统库时使用。
- 若旧 shell 里 `LD_LIBRARY_PATH` 以 `:` 结尾（空项表示"当前目录"），同步后仍保留该结尾。

### 别名清理

`zda` 会 `unalias` 下列会遮蔽 base 可执行文件的旧别名，并在有删除时打印名单：
`python`、`python3`、`pip`、`pip3`、`py`、`ipython`。其他别名（如 `mytool`）不受影响；
`unalias` 必须在当前 shell 执行，因此实现里没有把这一步放进 `$(...)` 子 shell。

### 前置条件

`zda` 假定 base 里已经装好开发工具链。完整清单（含 `mamba install`、CUDA/HDF5 导出、
源码编译的 mpi4py/h5py/tilelang/torch、TeX 与验证命令）在
[`../../bin/_zda-guide.txt`](../../bin/_zda-guide.txt)；环境缺失时 `zda` 会直接打印该文件。
这些包的安装顺序与 MPI/HDF5 变体约束见 [`../_wsl/setup.md`](../_wsl/setup.md) 的
「Miniforge 与 conda」和「源码编译 pip 依赖」。镜像地址见 [`../_mirror/setup.md`](../_mirror/setup.md)。

### 其他要点

- 目标路径固定为 `${HOME}/miniforge3`。装在其他位置（如 `/opt/miniforge3`）时 `zda` 会走缺失分支，需改用 `conda activate <路径>`。
- 别名只在交互式 shell 展开。脚本里直接调函数：`bash -c 'source ./env.sh; _zda_activate_base'`；bash 脚本需 `shopt -s expand_aliases`，zsh 需 `setopt aliases` 并用 `eval zda`。
- 指南文件路径由 `_ZDA_GUIDE_PATH` 给出，默认 `${仓库根}/bin/_zda-guide.txt`；文件缺失时会明确报出路径而不是静默跳过。
- 与 `conda init` 共存：`zda` 只负责激活与变量同步，不替代 `conda init` 写入的自动加载。重复 source `conda.sh` 不会再次前置 `condabin`（由 `CONDA_SHLVL` 保护），已激活其他环境时调用 `zda` 会正常切回 base。
- 别名与函数都出现在 `@ALIAS@` 段的探测输出里，冲突预检恢复后会照常把用户同名的 `zda` 报为冲突。

验证：

```bash
bash --noprofile --norc -c 'source ./env.sh; _zda_activate_base; printf "%s\n" "$CONDA_PREFIX" "$CUDA_PATH"'
bash env.test.sh
```

## 加载前冲突闸门（暂停）

`lib/_env_conflicts.sh` 保留以下检查能力，但 `env.sh` 中的调用与告警已注释暂停：

- 与仓库 alias 同名的现有 alias。
- 与仓库公开 function 同名的现有 function，包括 `git_current_branch` 等条件兜底函数。
- 与仓库 `bin/` 中可执行文件同名，且已由原 PATH、alias 或 function 占用的命令名。
- 指向其他指南的 `_SCREEN_GUIDE_PATH`。

导出的 `_CONFIGURE_ENV_LOADED_PATH` 用于同一路径的重复加载判断；路径完全一致即跳过。

恢复时取消 `env.sh` 中 `@CONFLICT_GUARD_PAUSED@` 标记后的整段注释。恢复后命中任一冲突会返回非零、
列出冲突项，并且不修改 PATH、`LD_LIBRARY_PATH`、locale、alias 或 function。

检查多次 source 是否稳定：

```bash
bash --noprofile --norc -c '
  source ./env.sh
  first_path=$PATH
  source ./env.sh
  test "$first_path" = "$PATH"
  printf "PATH stable\n"
'
```

## 选择版本化配置

先列出可用快照：

```bash
find lib -mindepth 1 -maxdepth 1 -type d -name '*-v[0-9]*' -print | sort
```

查看某个环境的实际动作：

```bash
sed -n '1,240p' lib/<name>-vYYYYMMDD/env.sh
grep -nE '^(module|conda|source|pushd|export|alias|cp|ln) ' lib/<name>-vYYYYMMDD/env.sh
```

确认后，可把机器入口链接或复制到 `~/env.sh`：

```bash
if [ -e ~/env.sh ] || [ -L ~/env.sh ]; then
  mv ~/env.sh ~/env.sh.bak.$(date +%Y%m%d-%H%M%S)
fi
cp lib/<name>-vYYYYMMDD/env.sh ~/env.sh
```

版本化配置通常包含硬编码用户目录、module 名称、conda 环境、网络代理或共享集群路径。不要在没有对应机器和软件栈时直接 source。

如果机器配置需要跟随仓库更新，可使用符号链接；但仓库路径移动或历史目录切换会使链接失效：

```bash
ln -s "$PWD/lib/<name>-vYYYYMMDD/env.sh" ~/env.sh
```

## 版本化快照索引

稳定入口吸收跨机器可复用的模式；机器专属路径、版本号和一次性命令保留在快照中。

| 快照家族 | 稳定入口 | 说明 |
|---|---|---|
| `wsl-v*` | [`../_wsl/setup.md`](../_wsl/setup.md) | WSL 2 宿主生命周期与发行版内开发环境 |
| `docker-v*`、`computer-v*` | [`../_docker/setup.md`](../_docker/setup.md) | 容器环境变量、镜像构建与推送记录 |
| `snsc-v*` | [`../_snsc/setup.md`](../_snsc/setup.md) | SNSC module、conda 激活与 VS Code Server 兼容 |
| `mac-v*` | [`../_mac/setup.md`](../_mac/setup.md) | macOS arm64 开发环境模式 |
| `claude-code-v*` | [`../_claude-code/setup.md`](../_claude-code/setup.md) | Claude Code 离线安装与卸载 |
| `zerotier-v*` | [`../_zerotier/setup.md`](../_zerotier/setup.md) | ZeroTier 安装、授权与组网 |
| `dcu-v*`、`bscc-v*`、`lingsheng-v*` | [`../_slurm/setup.md`](../_slurm/setup.md) | 集群作业模板、DCU/GPU 资源与 DSUB |
| `x99-v*` | [`../_ssh/setup.md`](../_ssh/setup.md)、[`../_docker/setup.md`](../_docker/setup.md) | Windows 工作站 SSH 入口与容器镜像构建记录 |
| `aistudio-v*`、`laptop-v*`、`npu-v*`、`phone-v*`、`usb-v*` | 无独立稳定入口 | 机器/平台专属快照，按目录内 `AGENTS.md` 使用 |

版本化目录是历史快照，不是跨机器模板；需要在新机器复用时，先复制为新的 `{name}-vYYYYMMDD`，再逐项替换路径、账号、module 和分区。

## 新增或更新机器配置

按照仓库约定，更新时新建当天日期目录：

```bash
mkdir -p lib/<name>-v$(date +%Y%m%d)
cp lib/<name>-v<旧日期>/env.sh lib/<name>-v$(date +%Y%m%d)/env.sh
${EDITOR:-vim} lib/<name>-v$(date +%Y%m%d)/env.sh
bash -n lib/<name>-v$(date +%Y%m%d)/env.sh
```

不要直接修改旧日期目录。旧目录用于历史对照、机器回退和差异分析。

## 分节标记

| 标记 | 含义 |
|---|---|
| `@SECTION@` | 激活块 |
| `@@SECTION@@` | 注释掉的备选块 |

常见分节：

```text
@MODULE@
@EXPORT@
@CONDA@
@ENV@
@ALIAS@
@SOURCE@
```

安装或构建命令首次运行后可保留为注释，只保留生效的 export 和环境加载。这样既能复现，也不会在每次 source 时重新安装。

## `lib/set-env.sh`

```bash
source lib/set-env.sh
```

该脚本必须 source，直接执行只影响子进程，当前终端不会获得变量。

当前顺序：

1. Bash 会话 source `~/.bashrc`；Zsh 会话跳过。
2. source `~/.env.sh`。
3. `~/.env.sh` 不存在时，在 `$HOME` 调用 `bin/save-env.sh` 自动生成。
4. source `~/configure/env.sh`。
5. source `~/env.sh`。

三个限制：

1. `set-env.sh` 把配置根硬编码为 `~/configure`，即使脚本位于其他部署目录也不会自动改向。
2. 自动生成的 `~/.env.sh` 会包含大量当前环境变量，可能含 API key、令牌和代理凭据。
3. 被调用的 `save-env.sh` 依赖 Bash 4+ 的 `mapfile` 和 GNU `sort -z`，macOS 默认 Bash 3.2 + BSD `sort` 下无法正常工作。

因此执行前应先检查：

```bash
test -f ~/.env.sh || echo '将自动生成 ~/.env.sh'
umask
bash --version | head -1
sort --version 2>&1 | head -1
```

更安全的做法是手工创建最小 `~/.env.sh`，只包含确实需要恢复的变量。

## 环境快照

```bash
umask 077
bash bin/save-env.sh ~/.env.sh TERM DISPLAY
chmod 600 ~/.env.sh
```

生成后检查文件和值：

```bash
sed -nE 's/^(export )?([A-Za-z_][A-Za-z0-9_]*)=.*/\2/p' ~/.env.sh 2>/dev/null |
  grep -Ei 'KEY|TOKEN|SECRET|PASSWORD|PASS|PROXY' || true
```

该命令只显示变量名，不打印真实值。发现凭据时应重新生成、删除敏感变量或改用 `~/env-key.sh`。

## 验证

```bash
bash -n env.sh
bash -n lib/set-env.sh
bash -n <版本目录>/env.sh
bash --noprofile --norc -c 'source ./env.sh; command -v git; printf "%s\n" "$LANG"'
```

机器级 module、conda 和编译器只能在对应主机验证。验证时使用子 Shell，避免错误配置污染当前会话。

## 回滚

```bash
ls -l ~/env.sh ~/env-key.sh ~/.env.sh 2>/dev/null
cp ~/env.sh ~/env.sh.bak.$(date +%Y%m%d-%H%M%S)
cp lib/<name>-v<旧日期>/env.sh ~/env.sh
```

恢复后打开新终端或重新 source。密钥文件不进入 Git 回滚流程，应使用受控的本机备份。
