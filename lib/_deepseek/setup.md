# DeepSeek 配置操作

## 接入路径

| 客户端 | 入口 | 结果 |
|---|---|---|
| Claude Code | `claude-code-deepseek-env.sh` / `.ps1` | 设置 Anthropic 兼容端点与模型变量 |
| Codex CLI / 桌面端 | `codex-deepseek-setup.sh` / `.ps1` | 备份并修改 `~/.codex/config.toml` 与 `models.json` |
| 本仓库统一启动器 | `cl pay` | 由 `bin/agent.sh` 注入 provider、模型和密钥 |

优先使用统一启动器，避免同时维护多份端点、模型和认证变量。

安全提示：`codex-deepseek-setup.sh/.ps1` 会把输入的 API key 以明文写入 `~/.codex/config.toml` 的 `experimental_bearer_token`，而不是改用环境变量引用。备份目录中的配置也可能含凭据。执行后至少收紧权限：

```bash
chmod 600 ~/.codex/config.toml
chmod 700 ~/.codex/backup-deepseek 2>/dev/null || true
chmod 600 ~/.codex/backup-deepseek/config.toml 2>/dev/null || true
```

对密钥落盘有顾虑时使用 `co pay` 或 `cl pay`，由启动器从 `~/env-key.sh` 读取密钥。

## Claude Code 环境模板

`claude-code-deepseek-env.sh` 当前内容包含：

```text
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
ANTHROPIC_AUTH_TOKEN=<你的 DeepSeek API Key>
ANTHROPIC_MODEL=deepseek-flash[1m]
CLAUDE_CODE_EFFORT_LEVEL=max
```

该文件是模板，不能直接 source，否则占位符会覆盖现有认证。安全做法是只复制变量名到本机密钥文件，并填入真实值：

当前模板第 2 行的密钥占位符没有引号，因此对原文件执行 `bash -n` 会报语法错误。这是模板未填写状态，不是可执行安装脚本。

```bash
umask 077
touch ~/env-key.sh
chmod 600 ~/env-key.sh
```

在 `~/env-key.sh` 中维护：

```bash
export DEEPSEEK_PAY_API_KEY='<真实密钥>'
```

然后优先启动：

```bash
cl pay
```

只有不经过统一启动器时，才显式设置 `ANTHROPIC_AUTH_TOKEN` 等兼容变量。

## Codex 配置管理器

Linux / macOS：

```bash
bash lib/_deepseek/codex-deepseek-setup.sh
```

Windows PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\lib\_deepseek\codex-deepseek-setup.ps1
```

菜单操作：

| 选择 | 行为 |
|---|---|
| `1` | 改用 `deepseek-flash` |
| `2` | 改用 `deepseek-v4-pro` |
| `9` | 恢复安装前配置并删除备份 |

执行前条件：

1. `~/.codex/` 已存在，或通过 `CODEX_HOME` 指定现有 Codex 配置目录。
2. 已安装 Codex CLI、ChatGPT 桌面端或 Codex 编辑器扩展中的至少一种。
3. 知道 DeepSeek API key，或已设置 `DEEPSEEK_API_KEY`。

首次安装会写入：

```text
~/.codex/config.toml
~/.codex/models.json
~/.codex/backup-deepseek/config.toml
~/.codex/backup-deepseek/manifest.txt
```

切换已有安装时，快速路径只更新顶层 `model`、`web_search` 并重写 `models.json`；它不会自动调整已有的 `model_catalog_json`。恢复选项 `9` 会覆盖安装后对 `config.toml` 的所有后续修改，并删除 `models.json` 与备份目录，因此执行前应另存手工改动。

## 配置模板

`lib/_deepseek/.codex/config.toml` 是参考模板：

```toml
model = "deepseek-flash"
model_provider = "deepseek"
model_reasoning_effort = "high"
web_search = "disabled"

[model_providers.deepseek]
base_url = "https://api.deepseek.com/"
wire_api = "responses"
experimental_bearer_token = "<你的 DeepSeek API Key>"
```

不要把真实 token 写入仓库。统一启动器使用环境变量认证；手工配置也应优先使用 `env_key`，不要使用明文 `experimental_bearer_token`。

## 验证

```bash
bash -n lib/_deepseek/codex-deepseek-setup.sh
grep -nE '^(model|model_provider|wire_api)' lib/_deepseek/.codex/config.toml
```

环境模板应在复制并填入带引号的真实值后再做语法检查；不要把原模板当作可直接 source 的文件。配置管理器会自行校验 `models.json` 和 TOML 顶层键，Windows 端需在 PowerShell 中验证。

## 回滚

优先重新运行管理器并选择 `9`。手工回滚时先退出 Codex/桌面端：

```bash
test -f ~/.codex/backup-deepseek/config.toml
cp ~/.codex/backup-deepseek/config.toml ~/.codex/config.toml
rm -f ~/.codex/models.json
```

执行删除前确认 `models.json` 确实由本工具创建，否则可能删除其他 Codex 自定义模型目录。
