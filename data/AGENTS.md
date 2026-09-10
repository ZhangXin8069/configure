# AGENTS.md — agent 运行时数据

`data/` 保存 `bin/agent.sh`、`bin/agent.bat` 和 hook 适配层产生的本地运行记录，不保存业务源码。

- `runs/<run-id>/` 保存单次运行的 `manifest.env`、`state.env`、`events.jsonl`、`context.txt`、`agent.log` 和 `inputs.txt`
- `hooks/` 保存 hook 事件；路径可由 `CODEX_HOOK_DATA_DIR` 或 `CODEX_HOOK_EVENT_FILE` 覆盖
- 运行数据不应被 `source`、`eval` 或提交到 Git；验证时使用 `agent-status.sh` 或结构化解析
- 默认数据根为 `${HOME}/configure/data`，测试可设置 `AGENT_DATA_DIR` 隔离临时目录

协议和生命周期说明见 `README.md`；运行脚本见 `../bin/agent-runtime.sh`、`../bin/agent-status.sh` 和 `../hooks/codex-event.sh`。
