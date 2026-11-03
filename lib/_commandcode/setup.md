# Command Code 安装与配置

本文对应官方 [Quickstart](https://commandcode.ai/docs/quickstart)、
[Settings & Config](https://commandcode.ai/docs/settings)、
[Permissions](https://commandcode.ai/docs/permissions) 与
[BYOK](https://commandcode.ai/docs/byok)、
[Provider API](https://commandcode.ai/docs/provider)。参考实现日期为 2026-11-03。

## 前提

- Node.js 22 或更新版本；Node.js 20 及以下会被 Command Code 拒绝。未安装或版本过旧时，
  见下文「Node.js 安装指南」，其中包含 HPC 无 root 场景的做法。
- `config.sh` 与回归测试另需 Bash 和 Python 3；配置器不会自动安装依赖。
- Linux、macOS、WSL 使用 `command-code` 或短别名 `cmd`。
- 原生 Windows 使用 `command-code` 或 `cmdc`；`cmd` 已被 Windows 命令解释器占用。

## Node.js 安装指南

Command Code 要求 Node.js 22 或更新版本，npm 随官方 Node.js 一并提供。HPC 登录节点通常没有
root 权限，优先复用集群已有环境，其次安装到 `$HOME`。

### 1. 先检查是否已提供 Node.js

```bash
command -v node && node --version
command -v npm && npm --version
```

HPC 常通过 environment modules 或 conda 管理 Node.js：

```bash
module avail node 2>/dev/null || module avail nodejs 2>/dev/null || true
module load nodejs        # 模块名以 module avail 的实际输出为准
node --version
```

```bash
conda create -n node22 -c conda-forge nodejs=22
conda activate node22
node --version
```

`node --version` 显示 `v22` 或更高即可直接运行 `install.sh`。登录节点与计算节点的环境可能不同，
请在真正运行 Command Code 的节点上检查。

### 2. 官方预编译二进制（Linux/macOS，无需 root）

以下脚本下载官方 Node.js 22.x 预编译包并解压到 `$HOME/.local/node`，不会修改系统目录：

```bash
installer="$(mktemp "${TMPDIR:-/tmp}/install-node.XXXXXX")"
cat > "$installer" <<'NODE_INSTALL'
#!/usr/bin/env bash
set -euo pipefail

node_root="$HOME/.local/node"

case "$(uname -s)" in
    Linux)  node_os=linux ;;
    Darwin) node_os=darwin ;;
    *) echo "不支持的系统: $(uname -s)" >&2; exit 1 ;;
esac
case "$(uname -m)" in
    x86_64|amd64)  node_arch=x64 ;;
    aarch64|arm64) node_arch=arm64 ;;
    *) echo "不支持的架构: $(uname -m)；请从 https://nodejs.org/dist/latest-v22.x/ 手动选择" >&2; exit 1 ;;
esac

node_version="$(curl -fsSL https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt |
    sed -n "s/.*node-v\([0-9][0-9.]*\)-${node_os}-${node_arch}\.tar\.xz/\1/p" |
    head -n 1 || true)"
[ -n "$node_version" ] || { echo '无法获取 Node.js 版本，请检查网络或代理设置' >&2; exit 1; }

archive="$(mktemp "${TMPDIR:-/tmp}/node.XXXXXX")"
trap 'rm -f "$archive"' EXIT
curl -fsSLo "$archive" "https://nodejs.org/dist/v${node_version}/node-v${node_version}-${node_os}-${node_arch}.tar.xz"
mkdir -p "$node_root"
tar -xJf "$archive" -C "$node_root" --strip-components=1
printf 'Node.js %s 已安装到 %s\n' "$node_version" "$node_root"
NODE_INSTALL
bash "$installer"
rm -f "$installer"
```

把 Node.js 加入登录 shell（幂等；zsh 用户把 `~/.bashrc` 换成 `~/.zshrc`）：

```bash
node_bin="$HOME/.local/node/bin"
grep -Fqs "$node_bin" "$HOME/.bashrc" 2>/dev/null || \
    printf '\n# Node.js\nexport PATH="%s:$PATH"\n' "$node_bin" >> "$HOME/.bashrc"
export PATH="$node_bin:$PATH"
node --version
npm --version
```

网络受限时，可在可联网机器下载同版本的 `node-v*-<os>-<arch>.tar.xz` 后复制到 `$HOME`，
再执行 `mkdir -p "$HOME/.local/node" && tar -xJf <包名>.tar.xz -C "$HOME/.local/node" --strip-components=1`。
没有 `curl` 时可将 `curl -fsSLo <文件> <URL>` 换成 `wget -qO <文件> <URL>`；需要代理时先设置
`https_proxy`。

官方 Node.js 22 二进制要求 glibc 2.28+。CentOS 7 等较老系统若报
`GLIBC_2.28 not found`，改用 conda-forge 的 `nodejs`、集群模块或自行编译。

### 3. nvm（可选，多版本切换）

nvm 同样安装到 `$HOME`，适合需要在多个 Node.js 版本间切换的场景。按
<https://github.com/nvm-sh/nvm#installing-and-updating> 完成安装后：

```bash
export NVM_DIR="$HOME/.nvm"
. "$NVM_DIR/nvm.sh"
nvm install 22
nvm alias default 22
node --version
```

### 4. 桌面环境

- macOS（Homebrew）：`brew install node@22`，并按 Homebrew 提示把该版本加入 `PATH`。
- Windows：从 <https://nodejs.org/en/download> 安装 LTS，或运行
  `winget install OpenJS.NodeJS.LTS`；随后在 `cmd.exe` 中执行 `install.bat`。

### 5. 验证并重新安装 Command Code

```bash
node --version   # 必须为 v22 或更高
npm --version
bash lib/_commandcode/install.sh   # 在仓库根目录
# 若当前就在 lib/_commandcode 目录，直接运行：bash install.sh
```

若安装器仍提示版本过低，检查 `command -v node` 与 `node --version` 是否指向同一路径，
并确认 `PATH` 在 `module load` 之后仍然生效。npm 访问 registry 受限时，按集群文档配置
`https_proxy` 或 npm 镜像后再运行安装器。

## 安装

Linux、macOS、WSL：

```bash
bash lib/_commandcode/install.sh
bash lib/_commandcode/install.sh 1.88.2
bash lib/_commandcode/install.sh --new
```

Windows：

```bat
lib\_commandcode\install.bat
lib\_commandcode\install.bat 1.88.2
lib\_commandcode\install.bat --new
```

安装器调用官方 npm 包 `command-code`。默认固定 `1.88.2`，`--new` 安装 `latest`，
显式版本参数可复现实验环境。Unix 安装器使用 npm 的 `--prefix "$HOME/.local"`，
最终入口固定为 `$HOME/.local/bin/command-code`，与 Codex、OpenCode 等 agent 共用
`$HOME/.local/bin`；Windows 对应目录为 `%USERPROFILE%\.local\bin`。

需要覆盖目录时设置 `COMMAND_CODE_INSTALL_DIR`：

```bash
COMMAND_CODE_INSTALL_DIR="$HOME/.local/bin" bash lib/_commandcode/install.sh
```

找不到入口时，使用与其他 agent 一致的 PATH 写法；不要写死具体 Node 版本目录：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

安装器只在安装目录不在当前 `PATH` 时把该行幂等写入当前 shell 配置，不会修改 Node
安装目录或系统级 PATH。

等价的官方原生命令：

```bash
npm i -g command-code@latest
cmd --version
```

直接使用 npm 默认全局前缀时，入口位置由本机 Node 安装方式决定；仓库安装器显式使用
`$HOME/.local`，因此不依赖具体 Node 版本的全局目录。

## 登录与认证

```bash
command-code login
command-code status --json
```

原生 Windows 将入口换成 `cmdc`。浏览器不可用时：

```bash
export COMMAND_CODE_API_KEY='<从安全环境注入>'
command-code -p "explain this repository"
```

不要把真实 key 写进本目录脚本、`config.json`、`providers.json`、`AGENTS.md` 或 Git。
登录凭据由 Command Code 写入 `~/.commandcode/auth.json`，权限应为 `0600`，不应手工编辑。

## Agent 系列集成

`bin/cm`（以及 secure 变体 `bin/cms`）默认使用：

| 项 | 值 |
|---|---|
| 供应商快捷词 | `gt` |
| 供应商 | `commandcode-goat` |
| Provider API | `https://api.commandcode.ai/provider/v1` |
| 默认模型 | `deepseek/deepseek-v4.1-flash` |
| 推理强度 | `max` |
| 上下文 | `1000000` |
| 权限模式 | `yolo` |
| Goal 预算 | `--max-turns`，默认 100 |

使用前在当前 shell 激活环境变量，不要回显 key：

```bash
source ~/env-key.sh
cm
cm --once --max-turns 1
cm --goal 'get the test suite green'
cm goal status
```

`cm` 会把 `COMMANDCODE_GOAT_API_KEY` 仅在本进程映射为 Command Code CLI 使用的
`COMMAND_CODE_API_KEY`。`cl gt`、`op gt`、`co gt` 复用同一 Provider API；其中
`cl gt` 默认 Claude Sonnet 4.6，`op/co gt` 默认 DeepSeek V4.1 Flash。Command Code
的原生 statusline 由 `bin/agent-config.json` 的 `agents.commandcode.statusline` 幂等合并到
`~/.commandcode/config.json`。`cm` 默认 `yolo`，headless 同时显式传 `--yolo`；原生 goal
恢复后默认是 idle，`cm --resume RUN_ID --goal <objective> --once` 会重新启动目标。

## 快速开始

首次在项目中使用时，可先信任当前目录并跳过重复确认：

```bash
cd /path/to/project
command-code --trust
```

交互启动后按 quickstart 完成 taste 引导。已有 Claude Code、Codex、Cursor、OpenCode
等配置时，可在会话中使用 `/import claude`、`/import codex`、`/import opencode`；
要从历史会话学习偏好，可运行：

```bash
command-code learn-taste
```

升级与检查：

```bash
command-code update --check-only
command-code update
```

## 用户级配置

先检查：

```bash
bash lib/_commandcode/config.sh --check
bash lib/_commandcode/config.sh --help
```

默认 dry-run，仅预览将合并的 JSON：

```bash
bash lib/_commandcode/config.sh \
  --model <provider/model> \
  --theme auto \
  --compact-mode fast \
  --effort high \
  --permission-mode default \
  --allow 'Shell(git status:*)' \
  --ask 'Shell(git push:*)' \
  --deny 'Read(secrets/**)'
```

确认后加 `--apply`。配置器会：

1. 合并 `~/.commandcode/config.json`：`provider`、`model`、`theme`、`compactMode`、
   `reasoningEffort`、taste/artifact/local-only 等个人偏好。
2. 合并 `~/.commandcode/settings.json`：全局 `effort`、权限模式、allow/ask/deny 规则、
   额外目录和额外技能目录。
3. 保留未知字段，对重复规则去重；修改现有文件前创建 `.bak.YYYYMMDD-HHMMSS`。
4. 以原子替换写入，并把文件权限设为 `0600`。

支持的常用选项：

| 选项 | 配置位置 | 用途 |
|---|---|---|
| `--model` | `config.json` | 新会话默认模型 |
| `--provider` | `config.json` | `command-code`、`anthropic`、`github-copilot` 或 `codex` |
| `--theme` | `config.json` | `auto`、`dark`、`light` |
| `--compact-mode` | `config.json` | `default` 或 `fast` |
| `--reasoning-effort MODEL=LEVEL` | `config.json` | 按模型设置推理强度 |
| `--effort` | `settings.json` | 全局推理强度 |
| `--permission-mode` | `settings.json` | 默认权限模式 |
| `--allow/--ask/--deny` | `settings.json` | 添加权限规则 |
| `--extra-dir` | `settings.json` | 扩展工作区目录 |
| `--skill` | `settings.json` | 添加额外技能目录 |

## 权限

规则优先级固定为 `deny > ask > allow`。推荐最小放行：

```json
{
  "permissions": {
    "defaultMode": "default",
    "allow": ["Shell(git status:*)", "Shell(git diff:*)", "Shell(git log:*)"],
    "ask": ["Shell(git push:*)"],
    "deny": ["Shell(git reset --hard*)", "Read(secrets/**)", "Edit(.git/**)"]
  }
}
```

不要默认启用 `yolo`。无人值守场景优先使用 `dont-ask` 和显式 allow 列表，形成失败关闭策略；
普通交互开发保持 `default`。可用 `--disable-bypass on` 全局禁止 yolo。

## BYOK 与密钥边界

优先在 Command Code 中执行 `/connect`。交互式输入的自定义 provider key 保存在
`~/.commandcode/auth.json`。手工维护 `~/.commandcode/providers.json` 时，`apiKey` 只能是：

```json
{
  "provider": {
    "example": {
      "name": "Example Gateway",
      "baseURL": "https://gateway.example.com/v1",
      "apiKey": "$EXAMPLE_API_KEY",
      "models": {
        "vendor/model-id": {
          "contextWindow": 200000,
          "maxOutput": 32768,
          "reasoningEfforts": ["low", "medium", "high"]
        }
      }
    }
  }
}
```

可接受的引用形式是 `$ENV_VAR`、`{env:VAR}`、`!command`；无认证本地端点使用
`"apiKey": false`。Command Code 会拒绝 `providers.json` 中的原始 secret。

## 项目级配置

项目规则位于代码仓库，不属于本目录的自动配置范围：

| 路径 | 用途 | Git |
|---|---|---|
| `<project>/.commandcode/settings.json` | 团队共享权限、hooks、MCP | 应提交 |
| `<project>/.commandcode/settings.local.json` | 本机审批和覆盖 | 应忽略 |
| `<project>/.mcp.json` | 项目 MCP | 应提交 |
| `<project>/AGENTS.md` | 项目指令 | 应提交 |
| `<project>/.commandcode/skills/` | 项目技能 | 按团队策略提交 |
| `<project>/.commandcode/taste/` | 本地 taste 配置与学习结果 | 按共享策略处理 |

`~/.commandcode/AGENTS.md` 是用户级指令文件；`~/.commandcode/config.json` 和
`~/.commandcode/settings.json` 不应复制到项目仓库。

## 验证

```bash
bash -n lib/_commandcode/install.sh
bash -n lib/_commandcode/config.sh
bash -n lib/_commandcode/install.test.sh
bash -n lib/_commandcode/config.test.sh
bash lib/_commandcode/install.test.sh
bash lib/_commandcode/config.test.sh
bash lib/_commandcode/config.sh --check
command-code --version
command-code status --json
```

`config.test.sh` 使用隔离 `HOME` 和假 `command-code`，不会读取或修改真实
`~/.commandcode`。Windows 批处理可在 `cmd.exe` 中运行 `install.bat --help` 做静态入口检查。

## 回滚与排障

- 配置回滚：选择目标 `.bak.YYYYMMDD-HHMMSS`，确认内容后替换对应 JSON 文件。
- 登录异常：先运行 `command-code status --json`，再按官方 Troubleshooting 检查；不要删除或粘贴
  `auth.json` 内容。
- 找不到命令：确认 `test -x "$HOME/.local/bin/command-code"` 成功，并检查
  `$HOME/.local/bin` 是否位于 `PATH`；不要依赖 `npm prefix --global` 返回的版本化目录。
- Node 版本过旧或找不到 `node`：按「Node.js 安装指南」升级到 Node.js 22+ 后重新运行安装器。
- 配置 JSON 损坏：配置器会在写盘前失败并保留原文件；修复 JSON 后重试。
