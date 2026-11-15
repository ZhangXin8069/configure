# Patterns — 四类监控范式与它们的证据

本文件给可直接复用的监控“形状”。每个形状都标明：适用场景、必须要素、本次会话的实测证据。
SKILL.md 里是摘要，这里是完整版本。

## 1. All-jobs sentinel（全部作业 → 一次结束）

**适用**：一批作业已提交，要等它们**全部**离开队列才开始下一步（对齐数据、合并 CSV、出报告）。

**必须要素**：

```text
active_set = RUNNING PENDING WAITING STOPPED SSTOPPED
exclude    = 无关的长期 PENDING（本次 qcu_opt_base / 2108699）
sentinel   = 打印一行固定文本后 break（本次 ALL_TEST_JOBS_DONE）
interval   = 150–300s（作业级，不要 20s）
budget     = maxDurationMs ≈ 预计总时长 × 1.5（本次 4h）
```

**形状**（本次 `m21zy0uf7` 的实际形态，参数已参数化）：

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

**实测时间线**（`m21zy0uf7`，300s 间隔，17:37:43 启动，`maxDurationMs=4h`）：

| 时刻 | active | 内容 |
|---|---|---|
| 17:37:48 | 3 | `2133325 kall_mgr10_* RUNNING`、`2133322 kall_mgr10_* RUNNING`、`2133326 kall_mg1_r5* PENDING` |
| 17:42:50 | 2 | `2133326 kall_mg1_r5* RUNNING`、`2133322 kall_mgr10_* RUNNING` |
| 17:47:51 | 1 | `2133326 kall_mg1_r5* RUNNING` |
| 17:52:52 / 17:57:54 / 18:02:55 | 1 | 同上（长作业仍在跑） |

**踩过的坑**：

- `|| true` 包住 ssh 会让“SSH 失败”也变成空 `active` → **假哨兵**。正确做法是把 ssh 的 rc 与
  “空结果”分开处理（`scripts/poll_jobs.sh` 已实现：连续 N 次 ssh 失败就 abort）。
- 不排除 `qcu_opt_base` 这类长期 PENDING，哨兵**永不**触发。
- 用 name 做过滤会被截断名坑（`kall_mgr10_*`）→ 用 ID 白名单或 `-J`。

## 2. Single-job transition（单作业 → 只在变化时打印）

**适用**：只关心一个作业什么时候进 `RUNNING`、什么时候终止；不想被每轮重复状态刷屏。

**必须要素**：

```text
只看 state 字段（djob -ll → $1=="state"）
只在 state 变化时打印一行（带时间戳与 elapsed）
终止态 SUCCEEDED|FAILED|CANCELLED|KILLED → 退出（STOPPED/SSTOPPED 是挂起，继续观察）
超时 → 退出码 9；连续空输出/通信失败 → 退出码 3
```

**实测证据**：

- `2133396`（`m1xa22tu4`）：`16:41:21 job=2133396 state=PENDING` → `17:01:36 job=2133396 state=FAILED`，
  两行日志、20 分钟、monitor `completed exit 0`。→ 作业失败但监控正常结束。
- `2133327`（`s1oldb7up`）：PENDING 连续 53 行（16:35:34 → 17:01:19），`17:02:50 FAILED` 后 `DONE`。
  → 27 分钟 PENDING 是正常的排队，不要因为“太久没动”就重提。
- `2133416`（`s20idck26`）：`JOB_DONE after 870s`，最后一行是空的——作业**从列表消失**而没有显式终态。
  → 监控要能处理“消失”这种完成形态。

**变体**：需要“先等它开始再等它结束”时，加一个 `SEEN=1` 标记（本次 `s20idck26` 用过）：
先观察到 `RUNNING`，之后 `! RUNNING|PENDING` 才算完成；否则会把“还没开始”误判成“已结束”。

## 3. Data progress（数据侧：rows / CSV / newrows）

**适用**：作业在写数据（`rows/*.json`、CSV），要用**数据增长**而不是作业状态判断“真的在进展”。

**必须要素**：

```text
rows 计数  = ls rows/*.json | wc -l（或用 find）
CSV 行数   = wc -l < file（表头占 1 行）
newrows    = 本轮 rows 计数 - 上轮（增量比绝对值有信息量）
最新文件   = ls -t rows/*.json | head -3（看是不是刚写）
```

**本次 k9 的形态**（`k9_status.sh`，被 `m1klvg1ys` / `m1ylmbo0y` 每 150/180s 调用）：

```text
# 每轮打印：newrows=<n> running=[<job names>] pending=<n>
# 以及 3 个最新 rows/*.json、每个 CSV 的行数
[16:43:21] k9_16x9_c64 RUNNING 16:44:57 ... 其余 PENDING
--- csv lines:
  kupl_kunpeng_l24_c64_16x9.csv 2
--- newest row files:
rows/2f2380f75138b934.json
```

CSV 行数从 2 → 4 → 5 增长，同时 `rows/` 最新文件每轮都在变——这才是“在进展”的证据；
只看作业 `RUNNING` 不足以说明它在产出。

**纪律**：

- 监控阶段**只读**：不做 `merge`、不覆盖 CSV、不删中间文件。
- 作业 `SUCCEEDED` ≠ 行级完整：本次 thread9 只写了 7 行部分数据；必须独立核对行数/列/重复。
- 全部结束后才做：rsync 摘要 → merge CSV → 核对 → `known_skips`/quarantine → docs/logs/skills → 审计。

## 4. Replacement / handover（换监控，不留空窗也不重叠）

**适用**：目标变了（从“等 4 个作业”换成“等全部作业”）、旧监控间隔不合适、脚本要换。

**正确顺序**：

```text
1) 先确认新监控命令可用（手工跑一次，看到正确输出）
2) 起新 monitor（拿到新 m… id 与 output path）
3) 立刻停旧 monitor（task_stop / kill_shell({taskId})）
4) shell_tasks 复核：只剩一个权威观察者
```

本次实测的换班是**干净**的：`09:37:36Z` 停掉当时仍在跑的两个旧任务（`m1ylmbo0y`、`s1m3twhhb`；
`m1klvg1ys` 更早在 `08:51:05Z` 已停）→ `09:37:43Z` 起 `m21zy0uf7`，间隔 7 秒，无重叠、无空窗。
（本地时间 17:37:36 → 17:37:43。）

对照：本次也出现过**重叠**——`s1m3twhhb`（45s，自建 wait_jobs.sh）与 `m1klvg1ys`（150s）
同时在轮询同一批作业，产生两份不一致的时间线。后者才是要避免的形态。

## 5. Anti-pattern：重复监控

| 症状 | 代价 | 处理 |
|---|---|---|
| 同一目标两个 monitor | 双倍 SSH、双份日志、时间线冲突、停机时容易漏停 | 保留一个；另一个立即停 |
| 旧 monitor 还盯着已结束作业 | 无意义输出、误导“还在跑” | `shell_tasks` 找出 → `task_stop` |
| monitor + 前台 `sleep` 轮询并行 | 主循环被阻塞、token 浪费 | 删掉 sleep，只留 monitor |
| 每个数据文件一个 monitor | 观察者爆炸、难以收尾 | 一个 monitor 覆盖一个数据目录 |

本次会话的旧任务清理清单（作为“要停哪些”的例子）：`m1klvg1ys`（150s×90）、`m1ylmbo0y`（180s×120）、
`s1m3twhhb`（45s×240）、`m1vqx5c24`（被 `m1xa22tu4` 替换）、`magwlwwt`、`m4modbn3` 等——
它们都应该在目标结束或换班时停掉，而不是留在 `shell_tasks` 里。

## 6. 监控退出码与目标结果分离

```text
monitor 层：started → running → completed/stopped/failed(exit code 是观测者的)
目标层    ：PENDING → RUNNING → SUCCEEDED/FAILED/CANCELLED/KILLED（或从列表消失）
            STOPPED/SSTOPPED = 挂起，仍属 active
数据层    ：rows/CSV 行数、完整性、重复、known_skips
```

三层结论必须分别写。把 `completed exit 0` 写成“作业成功”是最常见的错误
（本次 `m1xa22tu4` 就是反例：exit 0，作业 FAILED）。

## 7. 什么时候**不要**监控

- 一次 `djob -u` 就能回答的问题（“现在有几个在跑”）——前台跑，别起 monitor。
- 作业预计 <1 分钟——直接 `shell_output(wait:"exit")` 等结果。
- 需要人判断的交互式调试——用 `screen` 回读，不要用监控代替观察。
- 目标已经结束——不要为了“再看看”而起监控；直接查最终状态。
