# AGENTS.md — hooks

通用 agent hook 适配层与独立 Git 质量门禁。`agent-hook.sh` 是统一入口，按事件转发到预检、路径保护、plugin/hook 审计、工作树验证或通知脚本；`pre-commit`/`pre-push` 是独立门禁，不依赖自动启用的 `core.hooksPath`。

## 事件与边界

- `session-start`：只读输出仓库根、分支、说明文件和技能目录。
- `session-summary` / `handoff`：只读输出仓库根、分支、HEAD、最近提交和改动统计，用于收尾/交接。
- `before-edit`：只接受仓库内路径，拒绝仓库根、`.git/`、agent 会话日志和仓库外路径。
- `after-edit`/`stop`：检查相对 `HEAD` 的工作树空白、Shell 语法和会话日志，包含仅暂存与未跟踪文件；`--paths` 可收窄验证范围。
- `notify`：优先使用 `notify-send`，不可用时回退到终端，通知失败不阻塞任务。
- `agent-resume`：对 `failed`/`blocked` run 做快速预检；仅当日志或 Codex/Claude/OpenCode
  本地会话终态命中 429、重试上限、连接中断、`upstream_error` / `reasoning_content ... passed back`
  等瞬时故障且原进程已退出、session/thread 可恢复时，脱离当前 agent 调度
  `tools/agent-resume.sh`。默认等待 10 秒，每个 run 只自动尝试一次。
- `plugin-audit`：委托 `tools/plugin-audit.py` 静态审计 plugin/hook/MCP manifest，不执行插件代码。
- 每次 hook 都有覆盖目标执行与 JSON 事件写入的默认总硬超时，可由 `AGENT_HOOK_TIMEOUT` 或 `--timeout`
  覆盖；超时终止整个受控进程组并返回 124。普通事件成功返回时会清理遗留后台子进程，`agent-resume`
  是唯一允许成功后退出的 detached 事件。`--list` 可查看事件、默认超时和阻塞语义。

脚本只把输入当作数据处理，不 `source`、不 `eval`、不执行目标仓库代码；统一入口会执行本目录受信的 hook 实现，Shell 文件仅用 `bash -n` 或 `zsh -n` 校验。

## 验证

```bash
bash -n hooks/*.sh hooks/pre-commit hooks/pre-push
hooks/agent-hook.sh session-start
hooks/agent-hook.sh session-summary
hooks/agent-hook.sh after-edit
hooks/agent-hook.sh plugin-audit --manifest refer/git-rep/ecc-skills/.codex-plugin/plugin.json
bash hooks/hooks.test.sh
```

必需依赖为 `bash`、`git`；路径规范化需要 `realpath`，`before-edit` JSON payload 解析和
`plugin-audit` 需要 `python3`；
事件 JSONL 编码优先使用 `python3`、缺失时回退 `jq`，通知 JSON 解析也可选用 `python3`。
测试中的 JSON envelope 断言需要 `jq` 或 `python3` 任一解析器。
恢复事件复用 `tools/agent-resume.sh` 的检测与 launcher 解析，不直接调用 codex/claude/opencode。
Git 门禁覆盖 `hooks/`、`skills/`、`tools/`、`plugins/`，并检查暂存 Python AST、plugin/tool JSON
和 Shell/Python 入口权限。
