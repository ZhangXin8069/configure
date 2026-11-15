# `monitor_command` 模板与参数说明

本文件是 `monitor` 技能的模板层：`monitor_command` 到底传什么、参数怎么定、怎么读、怎么停。
模板优先使用通用目标（进程/服务/数据/CI）；djob 只是其中一个适配器示例。

## 1. 参数

| 参数 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `command` | 是 | — | 要跑的监控命令；复杂 shell 用 `bash` + `args` |
| `args` | 否 | — | `command` 的参数数组，逐项 shell-quote 后执行 |
| `directory` | 否 | 当前工作区 | 工作目录；相对路径按工作区解析，必须留在允许的工作区内 |
| `description` | 否 | — | 人读的一句话（会出现在 `shell_tasks` 列表里），写清“盯什么” |
| `checkAfterMs` | 否 | `45000` | `notify:"scheduled"` 时，多久后发一次隐藏 check due ping（毫秒） |
| `maxDurationMs` | 否 | 无 | 最长运行时间；到点自动 `SIGTERM` 停止（毫秒） |
| `notify` | 否 | `"scheduled"` | `"scheduled"`=到期 ping + 退出时 ping；`"never"`=纯静默记录 |

返回：monitor task id（`m…`）、PID、cwd、output log 路径。之后用 `shell_tasks` 查状态、
`shell_output` 读输出、`task_stop`/`kill_shell` 停止。

**check due 的 ping 不带输出**（常见文案 “No monitor output included”），它只是提醒去读；
不要把它当作状态更新。

## 2. 三个参数的关系

```text
checkAfterMs  ≈ interval × 1000        # 每次轮询后醒来一次
maxDurationMs ≈ 预计目标时长 × 1.5      # 到点必须自动停，避免永久挂起
checkAfterMs  ≤ maxDurationMs          # 否则还没醒就被停掉
```

`monitor_command` 本身没有 `interval` 参数：轮询间隔是命令循环里的 `sleep`；`checkAfterMs` 只是
唤醒/check due 的节奏，通常取 `interval × 1000`，但不会强制命令的 sleep。两者要在同一条命令里
显式对齐，避免“醒来频率”和“实际轮询频率”漂移。

**短目标**：如果目标可能在首次 `checkAfterMs` 之前结束，优先用
`shell_command run_in_background` + `shell_output(wait="exit")`；确需周期观察时，`interval` 必须
小于目标预计剩余寿命，并在目标启动前/紧接着启动 monitor。

经验值：

| 场景 | interval | checkAfterMs | maxDurationMs |
|---|---|---|---|
| 短目标（10–60s） | 2–5s | 2000–5000 | 30–120s |
| 本地长进程/构建 | 30–60s | 30000–60000 | 预计时长 × 1.5 |
| 调度器作业（批量） | 150–300s | 150000–300000 | 4h 或预计时长 × 1.5 |
| 调度器单作业（短） | 60s | 60000 | 1h |
| 服务/HTTP 就绪 | 10–30s | 10000–30000 | 10–30min |
| 数据进度（rows/CSV） | 180s | 180000 | 2h |
| CI 流水线 | 30–60s | 30000–60000 | 预计时长 × 1.5 |

## 3. 模板 A：all-targets（一批目标 → 哨兵）

通用进程示例：

```text
monitor_command(
  command     = "bash",
  args        = ["-lc", "<循环：pgrep -f TARGET_PATTERN → 空则 echo ALL_TARGETS_DONE; break → 否则打印计数并 sleep 60>"],
  directory   = "<项目根>",
  description = "Wait all <target> processes; excludes <EXCLUDE_RE>",
  checkAfterMs = 60000,
  maxDurationMs = 3600000,
  notify      = "scheduled")
```

循环骨架：

```bash
while :; do
  active=$(pgrep -af "$TARGET_PATTERN" || true)
  if [ -z "$active" ]; then echo "ALL_TARGETS_DONE"; break; fi
  echo "[$(date +%H:%M:%S)] active=$(printf '%s\n' "$active" | wc -l)"
  printf '%s\n' "$active"
  sleep "$INTERVAL"
done
```

调度器示例（djob）的等价写法见 `../references/djob.md` 与 `../scripts/poll_jobs.sh`。
要点：探针 rc 与“空结果”分开；排除无关长期挂起项；每轮打印时间戳和计数。

## 4. 模板 B：single-target（单目标 → 状态转移）

通用进程示例（PID + 退出码文件）：

```bash
# 启动时写 PID；目标结束时写退出码
( "$TARGET_CMD" >"$LOG" 2>&1; echo $? >"$EXIT_FILE" ) &
echo $! >"$PID_FILE"

# 监控循环
while :; do
  if [ -f "$EXIT_FILE" ]; then
    st="DONE rc=$(cat "$EXIT_FILE")"
  elif kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    st="RUNNING"
  else
    st="UNKNOWN"
  fi
  echo "[$(date +%H:%M:%S)] state=$st"
  case "$st" in DONE*) echo "TARGET_DONE state=$st"; break ;; esac
  sleep "$INTERVAL"
done
```

如果 monitor 必须先于目标启动，`UNKNOWN`/空 PID 表示“尚未开始”，不是终态；先接受
`WAITING_FOR_TARGET`，看到 `RUNNING` 后才接受终态（`SEEN=1`，见 `../references/patterns.md` §2）。

调度器/服务示例：把 `st=` 换成 `squeue`/`curl`/`gh` 的字段；终态集合按适配器语义。
djob 单作业脚本见 `../scripts/watch_job.sh`（适配器示例，不代执行）。

## 5. 模板 C：数据进度（rows / CSV）

```text
monitor_command(
  command     = "bash",
  args        = ["-lc", "<每轮打印 newrows、每 CSV 行数、最新 3 个 rows 文件>"],
  directory   = "<项目根>",
  description = "CSV/rows progress every 180s",
  checkAfterMs = 180000,
  maxDurationMs = 7200000,
  notify      = "scheduled")
```

数据进度只**观察**；不要在这个 monitor 里写/合并/删除数据。

## 6. 模板 D：服务/HTTP 就绪

```text
monitor_command(
  command     = "bash",
  args        = ["-lc", "while :; do body=$(curl -fsS --max-time 5 URL) || { echo PROBE_ERROR; exit 3; }; case \"$body\" in *'\"ready\":true'*) echo SERVICE_READY; break;; esac; echo \"[$(date +%H:%M:%S)] not ready\"; sleep 15; done"],
  directory   = "<项目根>",
  description = "Wait <service> health ready=true",
  checkAfterMs = 15000,
  maxDurationMs = 1800000,
  notify      = "scheduled")
```

连接失败/非 2xx 是探针失败，不是“尚未就绪”。

## 7. 模板 E：CI 流水线

```text
monitor_command(
  command     = "bash",
  args        = ["-lc", "while :; do out=$(gh run view RUN_ID --json status,conclusion) || exit 3; case \"$out\" in *'\"status\":\"completed\"'*) echo \"CI_DONE $out\"; break;; esac; echo \"[$(date +%H:%M:%S)] $out\"; sleep 30; done"],
  directory   = "<项目根>",
  description = "Wait CI run <id> completion",
  checkAfterMs = 30000,
  maxDurationMs = 3600000,
  notify      = "scheduled")
```

用 JSON 字段做判定，不解析终端装饰文本。

## 8. 读与停

```text
# 读（首次快照）
shell_output({ id: "m…" })
# 读（增量续读，用上次返回的 next offset）
shell_output({ id: "m…", from_offset: <next_offset>, max_chars: 4000 })
# 等结论（一次性任务）
shell_output({ id: "m…", wait: "exit", timeout_ms: 600000 })
# 停（推荐）
task_stop({ taskId: "m…" })
# 停（等价）
kill_shell({ taskId: "m…" })
```

- 停止后任务状态变为 `stopped, signal SIGTERM`；日志不会再增长。
- `maxDurationMs` 到点也是 `SIGTERM` 自动停——**不是**目标完成。
- 不要用循环 `shell_output` 轮询；用 `wait` 或等 check due。

## 9. Do / Don't

| Do | Don't |
|---|---|
| 一个目标一个 monitor，起前 `shell_tasks` 查重 | 同一目标并存两个 monitor |
| 每轮打印时间戳 + 状态 + 计数 | 只打印 `active` 不打印时间，事后无法对齐 |
| 空结果前先区分探针失败 | `\|\| true` 吞掉连接错误后直接打印哨兵 |
| 排除无关的长期挂起项 | 把“同用户所有目标”当成本任务目标 |
| 用 ID/JSON/PID/URL 匹配 | 用截断显示名 grep |
| 预算内自动停 + 收尾手动停 | 无限期挂着，目标结束后还在跑 |
| 报告“monitor 结束方式 + 目标状态 + 数据核对” | 把 monitor `exit 0` 写成“目标成功” |
| 按适配器替换 probe/状态映射 | 把 djob/某个调度器写进通用流程 |
