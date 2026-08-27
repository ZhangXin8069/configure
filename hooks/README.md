# Codex agent hooks

本目录提供一个显式的 Codex agent hook 适配层。由于当前无法从官方 OpenAI 文档核实统一的 Codex 生命周期 hook API，脚本不依赖某个版本的自动发现规则；调用方将事件映射到 `codex-hook.sh` 即可。

## 事件

| 事件 | 行为 | 默认退出语义 |
|---|---|---|
| `session-start` | 输出仓库根、分支、`AGENTS.md`/`CODEX.md` 和 `skills/` 的只读上下文 | 检查失败时非零 |
| `before-edit` | 校验待编辑路径在仓库内，拒绝仓库根、`.git/`、技能会话日志和仓库外路径 | 拒绝路径时非零 |
| `after-edit` | 检查工作树改动的空白、Shell 语法和会话日志 | 检查失败时非零 |
| `stop` | 与 `after-edit` 相同，用于停止前复查 | 检查失败时非零 |
| `notify` | 使用 `notify-send`（若存在）发送通知，否则输出到终端 | 始终尽量返回 0 |

## 调用示例

```bash
# 统一入口
hooks/codex-hook.sh session-start
hooks/codex-hook.sh before-edit -- hooks/codex-hook.sh skills/all/SKILL.md
hooks/codex-hook.sh after-edit
hooks/codex-hook.sh stop

# 通知：纯文本、环境变量或 JSON 均可
hooks/codex-hook.sh notify '任务已完成'
CODEX_HOOK_MESSAGE='任务已完成' hooks/codex-hook.sh notify
CODEX_HOOK_PAYLOAD='{"message":"任务已完成"}' hooks/codex-hook.sh notify
```

`before-edit` 无命令行路径时可从 stdin 接收逐行路径，也可接收含 `path`、`paths`、`file` 或 `files` 字段的 JSON payload。`after-edit` 默认检查当前工作树全部新增/修改文件；仅验证指定文件时使用：

```bash
hooks/codex-verify.sh --paths hooks/codex-hook.sh skills/all/SKILL.md
```

## 安全与依赖

- 所有输入只作为数据处理，不 `source`、不 `eval`、不执行仓库脚本；Shell 文件只运行 `bash -n` 或 `zsh -n`。
- 必需：`bash`、`git`；检查 zsh 文件时需要 `zsh`。
- `realpath` 用于路径边界规范化；`python3` 仅用于解析通知 JSON；`notify-send` 不存在时自动降级为终端输出。
- 这些脚本不会自动修改 `core.hooksPath`、Codex 配置或工作树。启用方式取决于调用方的 Codex/agent runner 配置。

当前目录已有的 `pre-commit`/`pre-push` 是独立的 Git 质量门禁，不与本适配层混用。
