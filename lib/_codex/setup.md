# Codex CLI 安装与配置

## 安装

### Linux / macOS

```bash
bash lib/_codex/install.sh
bash lib/_codex/install.sh 0.154.0
bash lib/_codex/install.sh --new
```

版本选择规则：

| 参数 | 行为 |
|---|---|
| 无参数 | 安装脚本默认版本，当前为 `0.154.0` |
| `<VERSION>` | 安装指定版本，优先级最高 |
| `--new` | 从 GitHub Releases 解析最新版 |

默认安装到 `$HOME/.local/bin/codex`，可用 `CODEX_INSTALL_DIR` 覆盖。脚本会验证二进制版本，并且仅在当前 Shell 的 `PATH` 不包含安装目录时尝试写入 shell 配置。

### Windows

```bat
lib\_codex\install.bat
lib\_codex\install.bat 0.154.0
lib\_codex\install.bat --new
```

Windows 使用 npm 安装 `@openai/codex` 到 `%USERPROFILE%\.local\bin`，并写入 `HKCU\Environment` 的用户 PATH。需要先安装 Node.js/npm。

## 配置脚本

先查看状态和帮助：

```bash
command -v codex
codex --version
bash lib/_codex/config.sh --check
bash lib/_codex/config.sh --help
```

在 macOS 默认 Bash 3.2 中，帮助文本里的 `$CONFIG_FILE（` 会被错误解析为变量名并触发 `unbound variable`；`--check` 不受该问题影响。完整帮助和脚本回归应使用 Bash 4+。

默认行为是 dry-run：

```bash
bash lib/_codex/config.sh \
  --model <模型> \
  --approval-policy never \
  --sandbox-mode danger-full-access \
  --theme dark
```

确认差异后写盘：

```bash
bash lib/_codex/config.sh \
  --apply \
  --model <模型> \
  --approval-policy never \
  --sandbox-mode danger-full-access \
  --theme dark
```

配置写入 `$CODEX_HOME/config.toml` 或 `~/.codex/config.toml`。已有顶层键在原位置更新，但该行会被重写，行尾注释可能丢失；已有 provider 块不会覆盖，旧文件会先备份。

Windows 安装器只检查当前进程的 PATH，不能可靠判断 `HKCU\Environment` 中是否已有安装目录。安装后应检查用户 PATH，避免重复追加：

```bat
reg query "HKCU\Environment" /v Path
```

## Provider 协议

当前 Codex 主版本只接受 Responses API。`config.sh --list-providers` 中仍有把三方 provider 标成 `wire_api=chat` 的推荐项，不能直接照抄到当前 Codex。

显式添加 provider 时应传入 `responses`：

```bash
bash lib/_codex/config.sh \
  --provider 'custom=https://example.invalid/v1=CUSTOM_API_KEY=responses'
```

上面的示例故意使用无效地址，只用于展示 `NAME=base_url=ENV_KEY=wire_api` 格式。真实端点、认证方式和模型支持范围必须按供应商文档确认。

对于仓库已有的 DeepSeek、OpenCode Go/Zen 等路由，优先使用统一启动器：

```bash
co pay
co go
co zen
```

启动器会选择合适的端点、模型和必要的本地协议桥，避免手工维护重复 TOML。

## Codex ≥0.165 standalone 兼容

standalone 安装只有主二进制，没有 `CODEX_HOME/packages/app-server-daemon` 完整包；
TUI 默认自动启动共享 daemon 时会报 `this CLI has no complete local package`。
统一启动器已注入 `features.daemon_auto_start=false`，裸 `codex` 需在
`~/.codex/config.toml` 中同样关闭（或每次加 `--no-daemon`）：

```toml
[features]
daemon_auto_start = false
```

`codex-code-mode-host` 是 Code Mode 的可选伴生二进制，`install.sh` 会从同一 release
尝试安装；缺失时启动器自动关闭 `features.code_mode_host`，普通会话不受影响。

## 认证

```bash
codex login
codex login status
```

`config.sh` 不保存登录凭据。第三方 provider 使用 `env_key` 指向的环境变量，不要把密钥直接写进 TOML。

## 验证

```bash
bash -n lib/_codex/install.sh
bash -n lib/_codex/config.sh
bash lib/_codex/config.sh --check
codex --version
```

Windows 静态检查可在 Unix 完成，但 PATH 注册、npm prefix 和 `codex.cmd` 必须在本机 Windows 终端验证。
