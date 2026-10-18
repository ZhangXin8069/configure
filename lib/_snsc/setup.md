# SNSC VS Code Server 兼容配置

## 用途

SNSC CentOS 7 节点的 glibc 版本过旧，新版 VS Code Server 或其子进程可能无法直接启动。`lib/_snsc/` 提供预编译 sysroot 和 `patchelf`，用于设置自定义动态链接器和库路径。

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
