# VS Code 配置操作

## 可处理内容

| 场景 | 入口 |
|---|---|
| 清理损坏的 Remote Server 状态 | `bin/vscode_unset.sh` |
| CentOS 7 等旧系统运行 VS Code Server | [`../_snsc/setup.md`](../_snsc/setup.md) |
| secure/HPC agent 二进制路径失效 | `bin/agent-custom.json` 的 `agents.<agent>.secure_binary` 或 `*_BIN` |

## 清理 Remote Server

`bin/vscode_unset.sh` 在 `$HOME` 下移动以下目录：

```text
~/.vscode
~/.vscode-server
~/.vscode-remote-containers
```

每次移动的目标名格式为 `<目录>.<YYYY-MM-DD-HH-MM-SS>.bak`。

先手工检查占用空间和当前状态：

```bash
du -sh ~/.vscode ~/.vscode-server ~/.vscode-remote-containers 2>/dev/null || true
ps aux | grep -E '[c]ode-server|[v]scode-server' || true
```

确认后执行：

```bash
bash bin/vscode_unset.sh
```

重要限制：

1. 脚本没有 `set -e`；某个目录不存在时 `mv` 会报错，但后续目录仍会继续处理。
2. 脚本不删除文件，但备份目录可能占用数 GB。
3. 脚本不会迁移扩展、设置或登录信息。
4. 重新连接后 VS Code 会重新安装 Server 与扩展。

恢复指定目录：

```bash
ls -1dt ~/.vscode-server.*.bak 2>/dev/null
mv ~/.vscode-server ~/.vscode-server.failed 2>/dev/null || true
mv ~/.vscode-server.<时间戳>.bak ~/.vscode-server
```

## 旧 Linux 兼容

CentOS 7 或 glibc 过旧时，VS Code Server 可能因动态链接器版本失败。SNSC 兼容方案位于 `lib/_snsc/`，操作见 [`../_snsc/setup.md`](../_snsc/setup.md)。

兼容层只解决 VS Code Server 进程。由 VS Code Server 启动的 agent 二进制仍可能因 glibc 或文件被覆盖而失效，此时使用 secure 入口或设置：

```bash
export CLAUDE_BIN=/absolute/path/to/claude
export OPENCODE_BIN=/absolute/path/to/opencode
export CODEX_BIN=/absolute/path/to/codex
```

## 验证

```bash
bash -n bin/vscode_unset.sh
code --version 2>/dev/null || true
code --list-extensions 2>/dev/null | head -20 || true
```

远程连接日志通常位于本机 `~/.vscode-server/data/logs/` 或远端对应目录。排障时只读取当前失败会话相关日志，不要在日志中暴露令牌。
