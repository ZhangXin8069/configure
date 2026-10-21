# Agent hooks

本目录提供一个显式的通用 agent hook 适配层，事件模型兼容 Codex-style runner，但不依赖特定版本的自动发现规则；调用方将事件映射到 `agent-hook.sh` 即可。

## 事件

| 事件 | 行为 | 默认退出语义 |
|---|---|---|
| `session-start` | 输出仓库根、分支、`AGENTS.md`/`CODEX.md` 和 `skills/` 的只读上下文 | 检查失败时非零 |
| `session-summary` / `handoff` | 输出仓库根、分支、HEAD、最近提交和改动统计的只读交接摘要 | 检查失败时非零 |
| `before-edit` | 校验待编辑路径在仓库内，拒绝仓库根、`.git/`、技能会话日志和仓库外路径 | 拒绝路径时非零 |
| `after-edit` | 检查工作树改动的空白、Shell 语法和会话日志 | 检查失败时非零 |
| `stop` | 与 `after-edit` 相同，用于停止前复查 | 检查失败时非零 |
| `agent-resume` | 检测 429/重试上限/连接中断/上游协议错误等瞬时故障，默认 10 秒后异步恢复原 run | 无候选时 0；调度失败时非零 |
| `plugin-audit` | 静态审计 plugin/hook/MCP manifest、路径、超时和命令风险 | 有 high/critical 问题时非零 |
| `notify` | 使用 `notify-send`（若存在）发送通知，否则输出到终端 | 始终尽量返回 0 |

## 调用示例

```bash
# 统一入口
hooks/agent-hook.sh session-start
hooks/agent-hook.sh session-summary
hooks/agent-hook.sh handoff
hooks/agent-hook.sh before-edit -- hooks/agent-hook.sh skills/all/SKILL.md
hooks/agent-hook.sh after-edit
hooks/agent-hook.sh stop
hooks/agent-hook.sh agent-resume --run-id 20261021T031022.dXBwYt
hooks/agent-hook.sh plugin-audit --manifest refer/git-rep/ecc-skills/.codex-plugin/plugin.json

# 通知：纯文本、环境变量或 JSON 均可
hooks/agent-hook.sh notify '任务已完成'
AGENT_HOOK_MESSAGE='任务已完成' hooks/agent-hook.sh notify
AGENT_HOOK_PAYLOAD='{"message":"任务已完成"}' hooks/agent-hook.sh notify
```

`before-edit` 无命令行路径时可从 stdin 接收逐行路径，也可接收含 `path`、`paths`、`file` 或 `files` 字段的 JSON payload。路径校验兼容 BSD/macOS 与 GNU `realpath`，对尚不存在的待创建路径会解析已有父目录后再做边界判断。`after-edit` 默认检查当前工作树相对 `HEAD` 的全部新增/修改文件（包含仅暂存的改动）以及未跟踪文件；仅验证指定文件时使用：

```bash
hooks/agent-verify.sh --paths hooks/agent-hook.sh skills/all/SKILL.md
```

`session-summary`/`handoff` 是只读的收尾事件：它不会修改工作树，只读取仓库根、分支、HEAD、最近提交和工作树状态，并按 `recent_path=` 输出最多 5 个上下文路径。

`agent-resume` 先调用 `tools/agent-resume.sh --check`，只有 manifest 为失败状态、没有存活
lock owner、错误属于瞬时服务故障且能从 Codex/Claude/OpenCode 本地状态恢复 session/thread 时才进入后台调度。后台工具默认等待
10 秒，通过原 manifest 的 launcher 执行 `--resume RUN_ID --once`，并用 run 目录中的
`.auto-resume-attempted` 保证每个 run 只自动恢复一次；持续 429 不会形成无界重试。手动重试可用
`tools/agent-resume.sh --force`。

所有事件默认带总硬超时：session-start 30 秒、summary 20 秒、before-edit 10 秒、after-edit/stop
120 秒、agent-resume 15 秒、plugin-audit 90 秒、notify 10 秒。该时限同时覆盖目标 hook 与 JSON 事件
落盘；`--timeout SECONDS` 或 `AGENT_HOOK_TIMEOUT` 可覆盖，超时返回 124 并终止受控进程组。
普通事件成功返回时会清理遗留后台子进程；`agent-resume` 是唯一允许成功退出后继续运行的 detached 事件。
连续 `TERM`/`INT` 不会中断清理阶段的 KILL 升级。`hooks/agent-hook.sh --list` 输出当前事件表。

## 安全与依赖

- 所有输入只作为数据处理，不 `source`、不 `eval`、不执行目标仓库代码；统一入口会执行本目录受信的 hook 实现，Shell 文件只运行 `bash -n` 或 `zsh -n`。
- 必需：`bash`、`git`；检查 zsh 文件时需要 `zsh`。
- `realpath` 用于路径边界规范化；`before-edit` 解析 JSON payload 和 `plugin-audit` 需要 `python3`；事件 JSONL 编码优先使用
  `python3`、缺失时回退 `jq`（二者至少一个）；通知 JSON 解析也使用 `python3`；`notify-send`
  不存在时自动降级为终端输出。
- 运行 `hooks.test.sh` 的 JSON 断言时，`jq` 与 `python3` 至少需要一个；两者都缺失时测试会明确失败。
- 这些脚本不会自动修改 `core.hooksPath`、Codex 配置或工作树。启用方式取决于调用方的 Codex/agent runner 配置。

回归测试：

```bash
bash hooks/hooks.test.sh
bash hooks/agent-resume.test.sh
```

当前目录已有的 `pre-commit`/`pre-push` 是独立的 Git 质量门禁，不与本适配层混用。门禁覆盖
`hooks/`、`skills/`、`tools/`、`plugins/`，检查 Shell 语法与入口权限、Python AST、plugin/tool JSON、
Skill frontmatter、空白和会话日志边界。
