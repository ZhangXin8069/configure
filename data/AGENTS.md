# AGENTS.md — agent 运行时数据

`data/` 保存 `bin/agent.sh`、`bin/agent.bat`、hook 适配层和诊断探针产生的本地运行数据，不保存业务源码。

- `runs/<run-id>/` 保存单次运行的 `manifest.env`、`state.env`、`events.jsonl`、`context.txt`、`agent.log` 和 `inputs.txt`
- `hooks/` 保存 hook 事件；路径可由 `CODEX_HOOK_DATA_DIR` 或 `CODEX_HOOK_EVENT_FILE` 覆盖
- `cache/` 保存模型目录、隔离 HOME、会话、SQLite/WAL、shell 快照和其他探针产物，可能含凭据与隐私
- 运行数据不应被 `source`、`eval`、打包、上传或提交到 Git；验证时使用 `agent-status.sh` 或结构化解析
- 默认数据根为 `${HOME}/configure/data`，测试可设置 `AGENT_DATA_DIR` 隔离临时目录

## Git 入库白名单

`data/` 仅允许跟踪 `.gitignore`、`AGENTS.md` 和 `README.md`。根目录与本地双层忽略规则必须保持有效，
禁止用 `git add -f` 强制加入 cache、runs、hooks、会话、数据库、日志或 shell 快照。提交前运行：

```bash
bash skills/form/scripts/form-data-tracking-check.sh --root . --quiet
```

一旦发现敏感数据已经进入 Git，先轮换/吊销暴露凭据，再移除当前索引并评估远端历史清理；历史改写属于
破坏性操作，必须显式授权，且不能替代凭据轮换。

协议和生命周期说明见 `README.md`；运行脚本见 `../bin/agent-runtime.sh`、`../bin/agent-status.sh` 和 `../hooks/codex-event.sh`。
