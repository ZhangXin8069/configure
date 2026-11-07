# AGENTS.md — tools 工具目录

本目录保存配置仓库维护工具和上游工具推荐信息。

- `configure-check.sh` 是只读检查入口，必须保持可执行、带 Bash shebang，并通过 `bash -n`；
  技能表与互鉴表同时核验登记完整性和 Markdown 列数一致性；`.opencode/skills/` 存在时逐项核对
  其与 `skills/` 的普通文件内容及软链接目标，不存在时以 `skills/` 为唯一权威源。
- `configure-check.sh --strict` 将警告提升为失败，供需要零警告的 CI 门禁使用；默认模式仍区分警告与错误。
- `coverage-report.sh` 是只读诊断入口，复用 `configure-check.sh` 的发现思路输出四树覆盖摘要、镜像一致性线索和缺口提示；允许缺口存在，但必须保持可执行、带 Bash shebang，并配套测试。其插件 manifest 诊断依赖 `python3`，其余部分只用 Bash/常见文本工具。
- `task-scope.sh` 是只读任务分流入口，把自然语言任务映射到技能组合与拆分建议；保持可执行，并同步 `README.md` 里的用途、参数和测试入口。
- `agent-resume.sh` 检测 agent run 的意外中断，默认等待 10 秒后通过原统一 launcher 执行
  `--resume`；除用户停止、正常结束或仍有存活锁的 run 外，failed/blocked/stale-running 等状态均会恢复。
  普通瞬时失败默认无限重试，`AGENT_RESUME_MAX_ATTEMPTS=0` 表示不限次数；模型上下文超限属于不可原 thread
  重试状态，改为生成脱敏、限长的 `resume-handoff.md`，用原 launcher 启动一次新 run/thread，并把
  `handoff_run_id` / `handoff_thread_id` 写回源 manifest。交接尝试由 `.context-overflow-handoff-attempted`
  去重，后续调用返回 `reason=handoff_already_started`，不会重复烧资源。调度锁防止同一 run 出现并行恢复链，
  每次 launcher 仍受硬超时和心跳约束。检测范围包含上下文窗口/`context_length_exceeded`、429、并发上限
  中英文变体、连接中断和 `upstream_error` / `reasoning_content ... passed back` 等错误。配套
  `agent-resume.test.sh`，并覆盖派发子 agent 的同构 manifest。
- `agent-session-state.py` 是 Codex、Claude Code、OpenCode 共用的只读会话解析器：按 manifest 的
  `run_id + cwd + created_at` 分别查询 Codex state DB/rollout、Claude 项目 JSONL、OpenCode V1/V2
  SQLite，并只依据最后一个完整 turn 输出 `failure_found`、`context_overflow` 与瞬时性分类；不修改各 agent
  状态、不输出消息正文或凭据。
  `agent-codex-state.py` 保留为 Codex 兼容入口。配套 `agent-session-state.test.py` 与
  `agent-codex-state.test.py`。
- `agent-tui-watch.py` 是 TUI 的同生命周期旁路监控器：复用会话解析器的最新 `turn_state` 与
  `failure_found`，只要进程仍存活、当前 turn 已失败且宽限期复查未变化就执行启动器预构造的
  原生恢复命令；TUI 不退出。Codex 由 `agent-codex-resume.py` 使用标准库 WebSocket 执行
  `thread/resume → thread/queue/add → thread/queue/start`；Claude 使用 `--bg --resume`，OpenCode 使用
  固定端口的 `run -s --attach`。恢复成功后继续监控，新失败按状态指纹再次恢复；默认宽限 10 秒，
  `AGENT_TUI_WATCH_MAX_RUNTIME=0` 表示跟随 TUI 生命周期而非固定小时数。恢复中的 run 与
  `AGENT_AUTO_RESUME=0` 自动停用；配套 `agent-tui-watch.test.py`。
- `agent-tui-watch.py` 的空闲自续跑：当 `--idle-nudge-command-json` 与 `--idle-nudge-markers`
  同时给出、回合已完成且 `.idle-nudge-enabled` 存在时，以“最新真实用户输入或上次注入时间”
  为活动基准；超过 `--idle-seconds`（默认 300）无活动就以用户身份执行注入命令
  （`{message}` 替换为汇报阶段进度并继续下一轮的指令）。`--idle-min-turn-seconds`
  （默认 30）避免回合刚结束即注入，`--idle-max-nudges` 可设注入上限（0 不限），
  `.goal-complete` 与停止文件立即终止注入；失败恢复优先于注入，二者互斥。
  注入次数与最后触发时间记录在 `.idle-nudge-attempted`，动作写入 tui-watch.log 与 events.jsonl。
  配套 `agent-tui-watch-idle.test.py`。
- `agent-idle-nudge.sh` 是 auto 技能的空闲注入标记入口：`enable --goal TEXT` 写入
  `.idle-nudge-enabled` 并清除旧完成标记，`complete` 写入 `.goal-complete` 并撤销启用，
  `disable` 撤销启用，`status` 只读报告；运行上下文取 `--manifest/--run-dir/--run-id`
  或 `AGENT_MANIFEST_FILE/AGENT_RUN_DIR/AGENT_RUN_ID`，只写运行目录、不启动 agent。
  `enable` 会检查 `.tui-watch.pid`，无存活看门狗时输出 `watch=inactive` 供调用方如实报告。
- `agent-tui-watch-idle-runtime.test.sh` 校验 `bin/agent-runtime.sh` 把空闲注入命令、
  阈值与轮询参数转发给 watcher，并写入 `.tui-watch.pid`。
- `agent-codex-resume.py` 是 Codex 运行中 thread 的原生恢复客户端：只用 Python 标准库完成 Unix
  WebSocket 握手与 JSON-RPC，显式执行 thread resume、队列追加和队列启动，并校验返回的 turn id；
  不读取消息正文之外的会话内容，不修改 Codex 配置。配套 `agent-codex-resume.test.py`。
- `agent-resources.py` 是只读资源快照入口，分离 host inventory、process affinity、cgroup v2、
  Slurm allowlist 和 accelerator management visibility；不得运行 benchmark/stress、写系统状态、
  输出 hostname、绝对路径、job/device ID 或未脱敏环境变量。未知值保持 `null`，配套
  `agent-resources.test.py`。
- `agent-config-benchmark.py` 是配对 HumanEval 基准入口：固定官方数据集 commit 与 SHA256，
  在相同 launcher/provider/model/strength 下比较完整 configure prompt 与 `agent-dispatch` 最小提示，
  从 Codex JSONL 提取 provider token usage 和工具动作，并用隐藏测试计算 pass@1。它只写指定
  `data/cache/` 或调用方给定的仓库内输出目录；发现子 agent 文件写入超出任务工作区时立即中止。
  支持 `--download-dataset`、断点复用、Wilson 区间、配对 bootstrap 和 McNemar 精确检验；
  配套 `agent-config-benchmark.test.py`。
- `plugin-audit.py` 是只读 plugin/hook/MCP 静态审计入口：校验 `.codex-plugin/plugin.json`、
  相对路径边界、hook event/schema、重复 id、命令风险、timeout、远程 hook 与 MCP runtime；
  拒绝重复 JSON 键与非有限数值，检查 hook/MCP 命令的父目录穿越和符号链接逃逸，并对输出中的已知
  凭据赋值脱敏；`--root` 达到发现上限时 fail-closed。不执行插件、hook、MCP 或外部二进制。
  配套 `plugin-audit.test.py`。
- 工具不得自动安装依赖、执行 hook/plugin 或修改仓库；第三方项目只记录在 `README.md`。
- 新增 shell 工具后同步说明用途、参数、退出码和依赖，并做权限、语法和边界参数验证；只读诊断工具的“成功”指报表或建议成功生成，不要求仓库被修改。
- `configure-check.sh` 的路径枚举失败必须 fail-closed；其临时 NUL 清单仅用于检查过程并在退出时清理。
- `skills/form/references/source-snapshots/` 是保留上游名称、权限和 shebang 状态的只读
  明文快照；`configure-check.sh` 必须排除该目录，不把 vendored 脚本当作本库维护脚本。
