# SNSC 集群环境与 VS Code Server 兼容配置

## 用途

SNSC CentOS 7 节点的 glibc 版本过旧，新版 VS Code Server 或其子进程可能无法直接启动。`lib/_snsc/` 提供预编译 sysroot 和 `patchelf`，用于设置自定义动态链接器和库路径。

## 集群环境快照参考

`snsc-v*` 是 SNSC 登录/计算节点的环境快照。2026 年后的多个版本共用同一套 module 组合：

```bash
module purge
module use /public/soft/modulefiles/linux-centos7-x86_64
module load gcc/10.3.0-gcc-4.8.5
module load cuda/11.4.4-gcc-10.3.0
module load git/2.40.0-gcc-10.3.0
module load openmpi/4.1.5-gcc-10.3.0
module load ncurses/6.2-intel-2022.0.2
module load cmake/3.22.2-gcc-10.3.0
module load python/3.9.10-gcc-10.3.0
module use /public/soft/modulefiles/apps
module load intel-oneapi/compiler/2024.0.0
module list
```

版本演进中值得复用的结论：

1. 不要用 `alias python=python3.9` / `alias pip=pip3.9` 伪装版本。alias 只在交互式 shell 展开，脚本和非交互 SSH 会落回系统旧版本；应使用 conda 环境或显式绝对路径。
2. 工具链变量（`CC`/`CXX`/`FC`/`CUDA_HOME`/`OPENMPI_ROOT`/`CMAKE_ROOT` 等）应在 `env.sh` 中保持单一来源；`etc/conda/activate.d/env_vars.sh` 只引用这些变量，并用 `ZHANGXIN_SNSC_READY` 防止重复加载。
3. `PATH`、`LD_LIBRARY_PATH`、`PYTHONPATH` 追加前用 `case ":$PATH:" in *":$dir:"*) ;; *) export ... ;; esac` 做幂等判断，避免重复 source 膨胀。
4. 版本摘要只在交互式 shell 输出（`[[ $- == *i* ]]`），避免污染管道、作业日志和自动化输出。
5. `.local/bin` 需要显式追加到 `PATH`，否则 `jupyter-lab` 等用户级入口不可见。
6. `snsc-v20260705` 的模块化 env 文件（conda、crosstool-ng、sysroot、VS Code Server）适合拆分复用；`snsc-v20260817` 是工具链单一来源和 conda 激活的完整示例。

| 版本目录 | 关键内容 |
|---|---|
| `snsc-v20231220` | 初始 module 组合、PyQCU source、python/pip alias |
| `snsc-v20260705` | 模块化 env 文件、crosstool-ng/sysroot、CentOS 7 VS Code Server |
| `snsc-v20260815` | 单文件 `env.sh`，基础 module 与 PyQCU |
| `snsc-v20260816` | 增加 TexLive `PATH` |
| `snsc-v20260817` | conda 激活替代 alias、工具链单一来源、幂等 PATH、交互摘要 |
| `snsc-v20260823`、`v20260825` | 恢复 alias 写法；`v20260823` 可选 clash 加载，`v20260825` 仅 PyQCU |
| `snsc-v20260908` | env-key + PyQCU 加载；目录名与 `AGENTS.md` 标注日期不一致，引用时以目录名为准 |

SNSC 的 module 名称和 `/public/soft/...` 路径只适用于该集群；其他集群应先 `module avail` 核对，不要直接套用。

## 资源

| 文件 | 用途 |
|---|---|
| `vscode-sysroot-x86_64-linux-gnu.tgz` | x86_64 Linux 预编译 sysroot |
| `sysroot.sh` | 导出 `VSCODE_SERVER_CUSTOM_GLIBC_*` |
| `vscode-sysroot-ursetto-env.sh` | 原始一次性安装脚本 |

## 可移植安装

原始 `vscode-sysroot-ursetto-env.sh` 含 `/public/home/zhangxin/configure/...` 硬编码路径，只适用于该共享部署。其他位置使用下面的等价流程：

```bash
repo_root="$HOME/configure"
test -f "$repo_root/lib/_snsc/vscode-sysroot-x86_64-linux-gnu.tgz"

mkdir -p "$HOME/.vscode-server"
tar -xzf "$repo_root/lib/_snsc/vscode-sysroot-x86_64-linux-gnu.tgz" \
  -C "$HOME/.vscode-server"
install -m 0644 "$repo_root/lib/_snsc/sysroot.sh" \
  "$HOME/.vscode-server/sysroot.sh"
```

检查关键路径：

```bash
test -x "$HOME/.vscode-server/sysroot/usr/bin/patchelf"
test -f "$HOME/.vscode-server/sysroot/lib/ld-linux-x86-64.so.2"
```

## 启用

只在需要兼容层的远程 Shell 中 source：

```bash
source "$HOME/.vscode-server/sysroot.sh"
```

如需写入 `.bashrc`，使用幂等检查，避免重复追加：

```bash
line='source "$HOME/.vscode-server/sysroot.sh"'
grep -Fqx "$line" "$HOME/.bashrc" 2>/dev/null || printf '%s\n' "$line" >> "$HOME/.bashrc"
```

原始安装脚本会无条件追加，重复执行会产生多行 source。

## 验证

```bash
bash -n lib/_snsc/sysroot.sh
bash -n lib/_snsc/vscode-sysroot-ursetto-env.sh
bash -c 'source "$HOME/.vscode-server/sysroot.sh"; printf "%s\n" "$VSCODE_SERVER_CUSTOM_GLIBC_LINKER"'
"$HOME/.vscode-server/sysroot/usr/bin/patchelf" --version
```

随后从本机重新连接 VS Code Remote。失败时检查远程日志中实际启动的 server 路径和动态链接器错误。

## Agent 二进制

sysroot 只解决 VS Code Server。由它启动的 `claude`、`opencode` 或 `codex` 仍可能因 glibc 版本失败。优先使用经过兼容处理的 secure 入口，或设置：

```bash
export CLAUDE_BIN=/absolute/path/to/claude
export OPENCODE_BIN=/absolute/path/to/opencode
export CODEX_BIN=/absolute/path/to/codex
```

## 回滚

先停止 Remote Server，再移动兼容目录，保留恢复副本：

```bash
mv "$HOME/.vscode-server/sysroot" "$HOME/.vscode-server/sysroot.bak.$(date +%Y%m%d-%H%M%S)"
mv "$HOME/.vscode-server/sysroot.sh" "$HOME/.vscode-server/sysroot.sh.bak.$(date +%Y%m%d-%H%M%S)"
```

同时移除 `.bashrc` 中对应 source 行。不要删除整个 `~/.vscode-server`，除非已确认不需要远程扩展、设置和缓存。
