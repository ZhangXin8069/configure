# Patterns — 通用监控范式与适配器案例

本文件给适配器无关的监控“形状”。`djob` 只是最后附录里的一个案例；通用适配器契约见
`adapters.md`，djob 细节见 `djob.md`。SKILL.md 里是摘要，这里是完整版本。

## 1. All-targets sentinel（一批目标 → 全部结束）

**适用**：一批目标已经启动，要等它们**全部**结束才开始下一步（合并数据、出报告、切流量）。

**必须要素**：

```text
target_probe = 一条只读探针，返回当前 active 目标列表（或可直接判空的结构化输出）
active       = 什么行算“仍在进行”
exclude      = 明确排除的无关目标（别人的作业、长期挂起项、性能基线）
sentinel     = 打印一行固定文本后 break（例：ALL_TARGETS_DONE）
budget       = interval + maxDurationMs，且 interval 不小于目标的最小状态变化粒度
```

**通用形状**：

```bash
target_probe() {
  # 替换为适配器探针：pgrep、squeue、curl、find、djob ...
  pgrep -af "$TARGET_PATTERN" || true
}

while :; do
  out=$(target_probe)
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "PROBE_ERROR rc=$rc"
    exit 3
  fi
  if [ -n "$EXCLUDE_RE" ]; then
    active=$(printf '%s\n' "$out" | grep -Ev "$EXCLUDE_RE" || true)
  else
    active=$out
  fi
  if [ -z "$active" ]; then
    echo "$SENTINEL"
    break
  fi
  echo "[$(date +%H:%M:%S)] active=$(printf '%s\n' "$active" | wc -l)"
  printf '%s\n' "$active"
  sleep "$INTERVAL"
done
```

**本地进程实例**：

```bash
while :; do
  pids=$(pgrep -f "$TARGET_PATTERN" || true)
  if [ -z "$pids" ]; then echo "ALL_TARGETS_DONE"; break; fi
  echo "[$(date +%H:%M:%S)] active=$(printf '%s\n' "$pids" | wc -l)"
  printf '%s\n' "$pids"
  sleep "$INTERVAL"
done
```

调度器/服务/数据适配器的探针写法见 `adapters.md`；djob 的完整循环见 `djob.md` 与
`../scripts/poll_jobs.sh`。形状相同，只替换 `target_probe` 与 active 判定。

**踩过的坑**：

- `|| true` 包住整条探针会让“连接失败”也变成空 `active` → **假哨兵**。只把预期的
  “无匹配/无行”包成 `|| true`，探针 rc 单独判断。
- 不排除无关的长期挂起项，哨兵可能**永不**触发。
- 用显示名/截断名做匹配会漏判或误伤；用 ID、PID、URL 或 JSON 字段。
- 探针返回成功但过滤为空，不等于目标结束；先确认过滤条件在手工命令上能选出预期目标。

## 2. Single-target transition（单目标 → 只在变化时打印）

**适用**：只关心一个目标什么时候进入运行、什么时候结束/失败；不想被每轮重复状态刷屏。

**必须要素**：

```text
state_probe   = 只返回一个可解析状态字段的探针
state_changes = 只在状态变化时打印一行（带时间戳与 elapsed）
terminal      = 适配器定义的终态集合；挂起态保持 active
budget        = interval + maxDuration；超时退出码要可区分
```

**通用形状**：

```bash
last=
start=$(date +%s)
while :; do
  st=$(state_probe)
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "PROBE_ERROR rc=$rc"
    exit 3
  fi
  if [ "$st" != "$last" ]; then
    echo "[$(date +%H:%M:%S) +$(( $(date +%s) - start ))s] state=$st"
    last=$st
  fi
  case "$st" in
    SUCCEEDED|FAILED|CANCELLED|KILLED) echo "TARGET_DONE state=$st"; break ;;
  esac
  sleep "$INTERVAL"
done
```

把终态集合换成适配器的真实语义；例如 djob 的 `STOPPED/SSTOPPED` 是挂起，仍属 active
（见 `djob.md`）。调度器的 `squeue`/`sacct`、服务的 health 字段、进程的退出码文件都可以作为
`state_probe`。

**变体：monitor 先于目标启动（SEEN / WAITING_FOR_TARGET）**：如果需要“先等它开始再等它结束”，
探针的 `UNKNOWN`/空 PID 表示“尚未开始”，不是终态。加 `SEEN=1` 标记：先观察到 RUNNING
（或目标出现），之后才接受终止态；否则会把“还没开始”误判成“已结束”。

```bash
seen=0
while :; do
  st=$(state_probe) || { echo "PROBE_ERROR"; exit 3; }
  case "$st" in
    RUNNING) seen=1 ;;
    UNKNOWN|WAITING_FOR_TARGET)
      [ "$seen" -eq 1 ] || { echo "WAITING_FOR_TARGET"; sleep "$INTERVAL"; continue; }
      ;;
  esac
  case "$st" in
    SUCCEEDED|FAILED|CANCELLED|KILLED) echo "TARGET_DONE state=$st"; break ;;
  esac
  sleep "$INTERVAL"
done
```

## 3. Data progress（数据侧：文件 / 行数 / 增量）

**适用**：目标在写数据（`rows/*.json`、CSV、日志），要用**数据增长**而不是状态词判断
“真的在进展”。

**必须要素**：

```text
rows 计数  = find <dir> -type f -name '*.json' | wc -l
CSV 行数   = wc -l < <file>（表头占 1 行）
newrows    = 本轮 rows 计数 - 上轮（增量比绝对值有信息量）
最新文件   = find/ls -t 看 mtime，确认还在写
```

**纪律**：

- 监控阶段**只读**：不做 merge、不覆盖 CSV、不删中间文件。
- 目标 `SUCCEEDED`/`exit 0` ≠ 数据完整；必须独立核对行数、列、重复、`known_skips`。
- 全部目标结束后才做：摘要 → 合并 → 核对 → 记录跳过/quarantine → docs/logs/skills → 审计。
- 数据增长可以为空但目标仍在跑（缓冲/批处理）；结合目标状态和 mtime 判断。

## 4. Replacement / handover（换监控，不留空窗也不重叠）

**适用**：目标变了、旧监控间隔不合适、脚本要换、旧 monitor 已到预算。

**正确顺序**：

```text
1) 先手工确认新探针可用，输出能被解析
2) 起新 monitor（拿到新 m…/s… id 与 output path）
3) 停旧 monitor（task_stop / kill_shell({taskId})）
4) shell_tasks 复核：只剩一个权威观察者
```

先起新的再停旧的，间隔几秒即可；不要长期并存，也不要在目标切换时留下空窗。
如果旧 monitor 已经自动停止（`maxDurationMs`），按“超时 ≠ 完成”处理，先查目标状态再决定是否重启。

## 5. Anti-pattern：重复监控

| 症状 | 代价 | 处理 |
|---|---|---|
| 同一目标两个 monitor | 双倍连接、双份日志、时间线冲突 | 保留一个；另一个立即停 |
| 旧 monitor 还盯着已结束目标 | 无意义输出、误导“还在跑” | `shell_tasks` 找出 → `task_stop` |
| monitor + 前台 `sleep` 轮询并行 | 主循环被阻塞、token 浪费 | 删掉 sleep，只留 monitor |
| 每个数据文件一个 monitor | 观察者爆炸、难以收尾 | 一个 monitor 覆盖一个数据目录 |
| 用 monitor 代替一次性查询 | 多出生命周期和清理成本 | 直接前台跑一次探针 |

## 6. 监控退出码与目标结果分离

```text
observer 层：started → running → completed/stopped/failed（exit code 是观察者的）
target 层  ：active → terminal（成功/失败/取消/消失；挂起仍属 active）
data 层    ：数量、完整性、重复、known_skips（独立于 target 状态）
```

三层结论必须分别写。`monitor completed exit 0` 只表示观察者正常结束；目标可能 `FAILED`，
数据也可能不完整。报告里分别写“monitor 结束方式”“目标最终状态”“数据核对结果”。

## 7. 什么时候**不要**监控

- 一次探针就能回答的问题（“现在有几个在跑”）——前台跑，别起 monitor。
- 目标预计 <1 分钟——直接 `shell_output(wait:"exit")` 等结果；确需周期观察时，`interval` 必须
  小于目标预计寿命，否则首轮就可能已经结束。
- 需要人判断的交互式调试——用 `screen`/`tmux` 回读，不要用监控代替观察。
- 目标已经结束——不要为了“再看看”而起监控；直接查最终状态。
- 只需要“进程是否还活着”——`kill -0`/`pgrep` 一次即可，不需要周期哨兵。

## Appendix — djob 案例（一个适配器的实测证据）

以下只作为“形状如何落地”的案例，不是通用流程的要求；完整命令、状态词与证据见 `djob.md`。

- 一批 djob 作业的 all-jobs 监控使用 300s 间隔、4h 上限、`ALL_TEST_JOBS_DONE` 哨兵；
  时间线显示 active 从 3 → 2 → 1，最终只剩长作业。
- 无关的长期 PENDING 作业必须加入 `exclude`，否则哨兵永不触发。
- `djob` 的 NAME 列会截断（`kall_mgr10_*`），匹配应使用作业 ID 或 `-J` JSON。
- 监控脚本看到 `FAILED` 后正常退出是 `exit 0`；目标失败必须从状态字段读，不能从观察者退出码读。
