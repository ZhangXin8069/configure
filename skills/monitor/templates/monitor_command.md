# `monitor_command` 模板与参数说明

本文件是 `monitor` 技能的模板层：`monitor_command` 到底传什么、参数怎么定、怎么读、怎么停。

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
maxDurationMs ≈ 预计作业时长 × 1.5      # 到点必须自动停，避免永久挂起
checkAfterMs  ≤ maxDurationMs          # 否则还没醒就被停掉
```

经验值：

| 场景 | interval | checkAfterMs | maxDurationMs |
|---|---|---|---|
| 作业级 all-jobs | 300s | 300000 | 4h（14400000） |
| 作业级单作业（短） | 60s | 60000 | 1h（3600000） |
| 提交后确认进入 RUNNING | 15–30s | 30000 | 10min（600000） |
| 数据进度（rows/CSV） | 180s | 180000 | 2h（7200000） |

## 3. 模板 A：all-jobs（全部作业 → 哨兵）

```text
monitor_command(
  command     = "bash",
  args        = ["-lc", "<循环：取 active → 空则 echo ALL_TEST_JOBS_DONE; break → 否则打印并 sleep 300>"],
  directory   = "<项目根>",
  description = "Wait all current test jobs; excludes <EXCLUDE_PATTERN>",
  checkAfterMs = 300000,
  maxDurationMs = 14400000,
  notify      = "scheduled")
```

`<循环>` 的完整形态（与 `scripts/poll_jobs.sh` 等价，可先用脚本验证再内联）：

```bash
while :; do
  out=$(ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes "$HOST" \
        'source /etc/profile >/dev/null 2>&1; export PATH=/opt/batch/cli/bin:$PATH; djob -u '"$REMOTE_USER"' 2>/dev/null' || true)
  active=$(printf '%s\n' "$out" \
    | awk 'NR>1 && ($3=="RUNNING" || $3=="PENDING" || $3=="WAITING" || $3=="STOPPED" || $3=="SSTOPPED") {print $1, $2, $3}' \
    | grep -v "$EXCLUDE_PATTERN" || true)
  if [ -z "$active" ]; then echo "ALL_TEST_JOBS_DONE"; break; fi
  echo "[$(date +%H:%M:%S)] active test jobs:"
  printf '%s\n' "$active"
  sleep 300
done
```

本次实际使用的就是这条（`m21zy0uf7`，300s、4h 自动停止、排除 `qcu_opt_base`）。
读它的输出会看到：每轮 4 行 `[stderr]` SSH 警告 + 1 行时间戳 + active 列表。

## 4. 模板 B：single-job（单作业 → 状态转移）

优先用脚本模板（语义固定、退出码明确）：

```text
monitor_command(
  command     = "bash",
  args        = ["<scratchpad>/watch_job.sh", "--host", "<host>", "--user", "<user>",
                 "--job", "<job-id>", "--interval", "60", "--max-duration", "3600"],
  directory   = "<scratchpad>",
  description = "Watch <job-id> until terminal",
  checkAfterMs = 60000,
  maxDurationMs = 3600000,
  notify      = "scheduled")
```

需要内联时的最小循环：

```bash
while :; do
  st=$(ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST" \
       'source /etc/profile >/dev/null 2>&1; export PATH=/opt/batch/cli/bin:$PATH; djob -ll '"$JOB"' 2>/dev/null' \
       | awk '$1=="state" {print $2; exit}')
  case "$st" in SUCCEEDED|FAILED|CANCELLED|KILLED|STOPPED) echo "WATCH_DONE $JOB $st"; break ;; esac
  sleep 60
done
```

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

## 6. 读与停

```text
# 读（首次快照）
shell_output({ id: "m…" })
# 读（增量续读，用上次返回的 next offset）
shell_output({ id: "m…", from_offset: <next_offset>, max_chars: 4000 })
# 等结论（一次性任务）
shell_output({ id: "m…", wait: "exit", timeout_ms: 600000 })
# 停（推荐）
task_stop({ taskId: "m…" })
# 停（等价，本次会话用过）
kill_shell({ taskId: "m…" })
```

- 停止后任务状态变为 `stopped, signal SIGTERM`；日志不会再增长。
- `maxDurationMs` 到点也是 `SIGTERM` 自动停——**不是**任务完成。
- 不要用循环 `shell_output` 轮询；用 `wait` 或等 check due。

## 7. Do / Don't

| Do | Don't |
|---|---|
| 一个目标一个 monitor，起前 `shell_tasks` 查重 | 同一目标并存两个 monitor |
| 每轮打印时间戳 + 状态 + 计数 | 只打印 `active` 不打印时间，事后无法对齐 |
| 空结果前先区分 ssh 失败 | `\|\| true` 吞掉 ssh 错误后直接打印哨兵 |
| 排除无关的长期 PENDING（`qcu_opt_base`） | 把“本用户所有作业”当成本任务作业 |
| 用 ID 白名单或 `-J` JSON 匹配 | 用完整作业名 grep（NAME 被截断） |
| 预算内自动停 + 收尾手动停 | 无限期挂着，任务结束后还在跑 |
| 报告“monitor 结束方式 + 目标状态 + 数据核对” | 把 monitor `exit 0` 写成“作业成功” |
