# Agent 数据目录

`bin/agent.sh`/`bin/agent.bat` 的运行时数据默认写入 `${HOME}/configure/data`，Windows
优先使用 `HOME`，未设置时回退 `USERPROFILE`；也可用
`AGENT_DATA_DIR` 或 `CONFIGURE_AGENT_DATA_DIR` 覆盖。

## 运行记录

- `runs/<run-id>/manifest.env`：不执行的键值 manifest，记录 agent、模型、状态、会话 ID、回合计数和路径。
- `runs/<run-id>/state.env`：较小的当前状态快照，便于外部监视。
- `runs/<run-id>/events.jsonl`：统一 `schema_version=1` 的生命周期事件 envelope。
- `runs/<run-id>/context.txt`：本次运行发现的层级说明文件路径清单，不是说明文件正文。
- `runs/<run-id>/agent.log`：对应 CLI 的原始输出或错误日志。
- `runs/<run-id>/inputs.txt`：OpenCode 会话输入的补录清单；其他 agent 保留为空文件以统一布局。

`agent-status.sh` 只读解析 manifest，不会 `source` 运行产物。驱动模式支持
`--once`、`--max-turns`、`--max-runtime`、`--stop-file` 和 `--resume RUN_ID`；
未指定 `--max-turns` 时默认最多 100 次继续回合，传 `0` 可显式恢复无回合上限。
恢复会校验 schema、agent、launcher 与 workspace 身份，并默认复用原 run 的模型、
推理等级和 variant；显式命令行覆盖仍优先。运行目录中的 `.lock` 防止同一会话被并发恢复，
Unix 会原子回收确认 owner 已退出的旧锁，Windows 使用独占文件句柄处理进程异常退出。

## Hook 事件

`hooks/codex-hook.sh --json <event>` 会将适配器输出转换为统一 JSONL envelope，
默认写入 `hooks/events.jsonl`；路径可用 `CODEX_HOOK_DATA_DIR` 或
`CODEX_HOOK_EVENT_FILE` 覆盖。运行日志、状态和 hook 事件均不应提交到 Git。

## 缓存与隔离 HOME

`cache/` 可能包含 Codex/OpenCode 隔离 HOME、模型目录、会话 rollout、SQLite/WAL、历史记录、
shell 快照及其他测试探针产物。这些文件可能同时包含 API 密钥、会话标识和隐私内容，必须始终留在本地。

## Git 边界

本目录只跟踪 `.gitignore`、`AGENTS.md` 和 `README.md`。需要入库的对比报告或测试证据应先脱敏，
再写入 `docs/` 或 `logs/`，不得把 `data/` 当作公开附件目录。发现泄露时先吊销/轮换凭据，再处理当前树和
远端历史。
