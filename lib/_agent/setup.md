# Agent 启动器配置操作

## 适用范围

`bin/agent.sh` 通过调用名分发以下入口：

| 入口 | Agent | 模式 |
|---|---|---|
| `cl` | Claude Code | 普通 TUI 或驱动模式 |
| `cls` | Claude Code | secure/HPC 二进制路径 |
| `op` | OpenCode | 普通 TUI 或驱动模式 |
| `ops` | OpenCode | secure/HPC 二进制路径 |
| `co` | Codex | 普通 TUI 或驱动模式 |
| `cos` | Codex | secure/HPC 二进制路径 |

Windows 对应入口为 `bin/agent.bat` 及 `cl.bat`、`op.bat`、`co.bat`。

## 配置分层

配置按以下顺序合并：

```text
bin/agent-config.json
  + bin/agent-custom.json（存在且非空时）
  或 bin/agent-custom.json.refer（用户配置缺失时）
```

个性化文件优先，但不会替代通用文件中的未覆盖键。`bin/agent-custom.json` 已按仓库规则忽略，不应提交。

创建本机配置：

```bash
cd ~/configure
cp bin/agent-custom.json.refer bin/agent-custom.json
chmod 600 bin/agent-custom.json
python3 -m json.tool bin/agent-custom.json >/dev/null
```

模板中可能包含针对当前工作站生成的 `secure_binary` 绝对路径或版本路径。首次使用时应逐项检查 `agents.<agent>.secure_binary`；路径随 VS Code Server 或远程扩展升级会失效。临时覆盖可设置：

```bash
export CLAUDE_BIN="$(command -v claude)"
export OPENCODE_BIN="$(command -v opencode)"
export CODEX_BIN="$(command -v codex)"
```

## API key

密钥只放在权限受控的本机文件中：

```bash
umask 077
touch ~/env-key.sh
chmod 600 ~/env-key.sh
```

在 `~/env-key.sh` 中按需设置一个或多个变量：

```bash
export DEEPSEEK_PAY_API_KEY='<真实密钥>'
export OPENCODE_GO_API_KEY='<真实密钥>'
export OPENCODE_ZEN_API_KEY='<真实密钥>'
export CUSTOM_GPT_API_KEY='<真实密钥>'
```

不要把真实值写入 `agent-config.json`、`agent-custom.json`、Markdown 或 Git 提交。

`OPENCODE_API_KEY`、`OPENCODE_ZEN_API_KEY` 和 `OPENCODE_GO_API_KEY` 是兼容入口，但不同途径有不同优先级。需要可预测行为时直接设置目标途径的专名变量。

## 安装 Agent

启动器在目标二进制缺失时会尝试运行对应稳定目录的安装脚本：

| Agent | 稳定目录 | 安装脚本 |
|---|---|---|
| Claude Code | `lib/_claude-code/` | Linux/macOS 自动安装使用 `install.sh`；Windows 的 `cc-v20260706.ps1` 需手动运行 |
| OpenCode | `lib/_opencode/` | `install.sh` / `install.bat` |
| Codex | `lib/_codex/` | `install.sh` / `install.bat` |

关闭自动安装：

```bash
export AGENT_AUTO_INSTALL=0
```

启动器查找目录：

```bash
export AGENT_INSTALL_DIR="$HOME/.local/bin"
```

`AGENT_INSTALL_DIR` 只控制启动器搜索和前置到 PATH 的目录，不会传给底层安装器。实际自定义安装目录时还需设置对应变量：

```bash
export CODEX_INSTALL_DIR="$HOME/.local/tools/bin"
export OPENCODE_INSTALL_DIR="$HOME/.local/tools/bin"
export AGENT_INSTALL_DIR="$HOME/.local/tools/bin"
```

Claude Code 的 `install.sh` 当前固定安装到 `~/.local/bin`，没有同类目录覆盖变量；需要其他位置时应手工安装并设置 `CLAUDE_BIN`。

安装成功后先运行：

```bash
claude --version 2>/dev/null || true
opencode --version 2>/dev/null || true
codex --version 2>/dev/null || true
```

认证仍由各 CLI 自己完成，例如 `codex login`。启动器不代替登录流程。

## 启动语法

显式选择供应商、模型和强度：

```bash
co go deepseek-v4.1-flash max
co zen gpt-5.6-luna max
cl pay 'deepseek-pro[1m]'
op gpt
```

传统参数仍具有最高优先级：

```bash
co --model <模型> --reasoning-effort max
op --model <provider/model> --variant max
cl --model <模型>
```

包含 `[1m]` 的模型名必须加引号，避免被 Zsh 当作通配符。

## 无人值守驱动

```bash
co --once
co -time 30s --max-turns 10 --stop-file ./STOP
cl --once -file task.txt
op --once -file task.txt
```

`-file` 只由 `cl` 和 `op` 支持，`co` 不接受文件指令参数。`-time` 支持 `30`、`30s`、`5m`、`2h`。持续运行前应设置 `--max-turns`、`--max-runtime` 或 `--stop-file` 之一，避免无界执行。

## 子任务派发

优先使用：

```bash
bash bin/agent-dispatch.sh --task '子任务说明' --json
bash bin/agent-dispatch.sh --task-file ./task.txt --json
```

该接口默认继承父启动器的 provider、模型、强度、工作目录、secure、sandbox/approval 与数据根。只有确实需要异构路由时才显式使用 `--agent`、`--provider`、`--model` 或 `--strength`。

## 运行状态

运行数据默认写入配置根下的 `data/runs/<run-id>/`：

```bash
bash bin/agent-status.sh
bash bin/agent-status.sh --all
bash bin/agent-status.sh --json
```

`agent-status.sh` 是只读查看工具，不接受恢复参数。恢复会话时由具体启动器使用 `--resume <run-id>`。使用 `data/` 前先确认目录可写，共享只读部署可通过 `AGENT_DATA_DIR` 指向用户可写目录。

## Codex 协议限制

当前 Codex 主版本只接受 Responses API。需要访问仅支持 Chat Completions 的三方模型时，应使用统一启动器自动启用的协议桥，不要手工把 `wire_api` 改成 `chat`。

## 验证

```bash
bash -n bin/agent.sh
bash -n bin/agent-runtime.sh
bash -n bin/agent-dispatch.sh
python3 -m json.tool bin/agent-config.json >/dev/null
python3 -m json.tool bin/agent-custom.json.refer >/dev/null
bash bin/co --help
bash bin/cl --help
bash bin/op --help
```

Windows 只能在 PowerShell/cmd 环境做真实运行验证；Unix 主机可对 `agent-runtime.ps1` 和 `agent.bat` 做静态检查。

部分状态栏与配置辅助脚本使用 Bash 4+ 特性或在 Bash 3.2 下存在空数组 `set -u` 兼容问题。macOS 默认 `/bin/bash` 3.2 不应作为完整验证环境；建议使用 Bash 5 或在目标 Shell 中直接回归实际启动链。

## 排障顺序

1. 运行 `command -v claude opencode codex`。
2. 检查目标 key 是否在当前 Shell 中可见，但不要在日志中打印值。
3. 运行 `python3 -m json.tool bin/agent-custom.json`。
4. 用 `co go --once` 等最小组合验证单个途径。
5. 查看 `data/runs/<run-id>/manifest.env` 与 `events.jsonl`。
6. secure 入口失败时设置对应的 `*_BIN` 覆盖过期路径。
