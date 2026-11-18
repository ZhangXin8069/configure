# AGENTS.md — agent 运行时数据

`data/` 保存 `bin/agent.sh`、`bin/agent.bat`、hook 适配层和诊断探针产生的本地运行数据，不保存业务源码。

## 两处落点唯一（硬约定）

1. **运行时信息**：`AGENT_DATA_DIR`（默认 `<configure 部署根>/data`）是 run、manifest、state、事件、
   会话索引、模型目录缓存等 agent 运行时信息的**唯一**缓存与保存路径。默认解析顺序为
   `AGENT_DATA_DIR`（旧名 `CONFIGURE_AGENT_DATA_DIR` 仍兼容）> `<configure 部署根>/data` >
   `${HOME}/configure/data`；不得在这些位置之外另建运行时状态目录。
2. **临时产物**：当前工作目录 Git 根下的 `data/` 是 agent 临时文档、日志、代码、脚本与数据缓存的
   **唯一**路径，默认落在该目录的 `tmp/` 子目录（运行时 `AGENT_SCRATCH_ROOT` / manifest
   `scratch_root=`；`AGENT_SCRATCH_DIR` 可覆盖）。它地位等同 `/tmp`，目的正是避免 `/tmp`
   容量上限或系统重启清空 `/tmp` 造成 agent 进度丢失。除进程内一次性文件外，不得用 `/tmp`、
   `$TMPDIR` 或会话级临时目录保存需要跨回合、跨进程或跨重启保留的中间产物。

本仓库的 `.gitignore` 已忽略 `data/`，因此工作区 `data/` 中的临时产物不会进入 Git；在其他工作区中，
启动器会把 `data/tmp/` 追加到 `.git/info/exclude`（幂等、本地生效），保证临时产物不出现在 `git status`。

- `runs/<run-id>/` 保存单次运行的 `manifest.env`、`state.env`、`events.jsonl`、`context.txt`、`agent.log` 和 `inputs.txt`
- `hooks/` 保存 hook 事件；路径可由 `CODEX_HOOK_DATA_DIR` 或 `CODEX_HOOK_EVENT_FILE` 覆盖
- `tmp/` 保存 agent 临时产物（`claude --settings` 临时文件、协议桥工作目录、派发与 hook 临时文件等）；
  工作区不是 Git 仓库时才回退到数据根 `tmp/` 或系统临时目录
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
