# Troubleshooting — 监控自身的故障排查

顺序原则：**先怀疑观测链路（SSH / PATH / 过滤 / 读取），再怀疑被观测目标。**
监控出错的最常见形态是“安静地给出错误结论”，而不是报错。

## 1. active 一直为空（但作业明显在跑）

**症状**：monitor 每轮输出 `active jobs:` 后面什么都没有，或第一轮就打印哨兵。

**可能原因**（按发生概率排序）：

1. `ssh` 失败被 `|| true` 吞掉 → `out` 为空 → `active` 为空 → **假哨兵**；
2. `djob` 不在 PATH（非登录 shell）→ 命令 not found（stderr 被 `2>/dev/null` 丢掉）；
3. 用户/主机写错（`$REMOTE_USER` 为空、`$HOST` 拼错）；
4. 过滤过严（`grep -v` 把整行都排掉、`-D` 服务端过滤返回空）。

**判定**：

```bash
# 手工跑同一条命令，看 rc 与 stderr，不要吞
ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST" \
  'source /etc/profile >/dev/null 2>&1 || true; export PATH=/opt/batch/cli/bin:$PATH; djob -u '"$REMOTE_USER"; echo "rc=$?"
```

**处理**：脚本里把“ssh 失败”和“空 active”分成两个分支；连续 N 次（默认 3）失败就
`POLL_ABORT`，而不是打印哨兵。`scripts/poll_jobs.sh` 已是这个结构。

## 2. `PENDING` 长时间不动

**症状**：几十分钟都是 PENDING，`EXEC_NODES` 一直是 `-`。

**可能原因**：

- 账号/资源池配额限制：`mainStateReasonMsg: The limit <testusers_rebuild> has been exceeded`
  （`mainStateReasonCode 20618`，节点行 `… allocation limit <testusers_rebuild> would exceed …
  : <node>, code=30021`）；
- 节点被关闭 / 最小资源不满足 / 独占作业 / execution-node 偏好不满足（都在 `nodeStateReasons`）；
- 队列拥塞（正常排队）。

**判定**：

```bash
ssh "$HOST" '… djob -ll '"$JOB"' 2>/dev/null' | grep -E '^ *(state|mainStateReasonCode|mainStateReasonMsg)'
```

**处理**：把原因字段原文贴给用户，判断是“等”还是“换资源/改队列”；**不要**重提作业、不要 `dkill`
别人的作业。本次 2133396（16:41 PENDING → 17:01 FAILED）与 2133327（16:35 PENDING → 17:02 FAILED）
都是这条路径：排队很久 → 直接 FAILED → 没有数据产出。

## 3. `maxDurationMs` 到点自动停止

**症状**：`shell_tasks` 显示 monitor `stopped, signal SIGTERM`，日志最后一行不是哨兵。

**含义**：监控超时，**不是**目标完成。目标可能还在跑。

**处理**：

1. 手工查一次目标状态（`djob -u` / `djob -ll`）；
2. 仍在跑 → 按新预算重启监控（必要时把间隔调大、预算覆盖真实作业时长）；
3. 已结束 → 不需要重启，直接进入数据/结论阶段；
4. 报告里写“监控到 maxDuration 自动停止，目标状态为 X”，不要写“跑完了”。

## 4. 重复监控

**症状**：`shell_tasks` 里有两个以上 monitor 的输出都在更新；两份时间线对不上；SSH 连接数翻倍。

**原因**：换目标/换脚本时忘记停旧的；或者“怕漏”又起了一个。

**处理**：

```text
1) shell_tasks(includeStopped:false) 列出所有在跑的 monitor
2) 确认哪个是权威观察者（最新的、覆盖当前目标的）
3) 其余全部 task_stop / kill_shell({taskId})
4) 用权威 monitor 的输出写结论；不要把两份日志拼在一起
```

**预防**：起监控前查重；把“停旧”写进换班流程（`references/patterns.md` 第 4 节）。

## 5. 输出被 stderr 污染

**症状**：每轮输出都有 4 行 `[stderr]`：post-quantum 警告 + `Authorized users only…`；
真正的数据被淹没，`grep state` 之类还可能误命中警告文本。

**处理**：

```bash
… 2>&1 | grep -v -E 'WARNING|post-quantum|store now|openssh\.com|Authorized users'
```

- 只过滤已知噪音；`Permission denied`、`Connection refused`、`Host key verification failed`
  必须保留。
- 不要把 `2>/dev/null` 用在“会失败的关键命令”上：那等于把故障变成静默。
- 本次 `m21zy0uf7` 的日志就是标准形态：每轮 4 行 `[stderr]` + 1 行时间戳 + active 列表。

## 6. `djob` 输出为空

**症状**：命令返回 0，但没有任何行（连表头都没有）。

**排查顺序**：

1. PATH：`command -v djob`；用 `source /etc/profile` + `export PATH=/opt/batch/cli/bin:$PATH`；
2. 用户：`djob -u "$REMOTE_USER"` 的 `$REMOTE_USER` 是否为空/拼错；
3. 选项：`djob -c`/`dsub -c` 这类**无效短选项**会让命令直接失败——先 `djob -h`；
4. 过滤：`-D`/`-n` 服务端过滤可能返回空，去掉后交叉验证；
5. 传输：`ssh` 是否真的连上（rc、stderr）。

**结论**：只有以上全部排除后，空输出才等于“没有作业”。

## 7. 作业 `SUCCEEDED` 但没有数据 / 只有部分数据

**症状**：状态 `SUCCEEDED`，CSV 行数没变或只有几行。

**原因**：作业级成功只表示进程正常退出；行级失败、跳过的用例、写盘异常都可能不体现在状态里。
本次 thread9 的 7 行就是部分数据。

**处理**：以数据核对为准（行数、列数、重复、`known_skips`），不要用 `SUCCEEDED` 代替核对；
把差异写进 quarantine/known_skips 并留给用户确认。

## 8. 作业“消失”而不是变成终态

**症状**：上一轮还在 active，下一轮整行没了（本次 2133202、2133324、2133325、2133322 都是这样）。

**含义**：作业离开队列（完成/被清掉）。**不能**据此判定成功。

**处理**：用 `djob -ll "$JOB"` 复核最后一次已知状态；查数据产出；报告写“已离开队列 + 最后已知状态”。

## 9. 监控读不到新内容（stale check）

**症状**：check due 到了，读出来的还是上一次的内容。

**原因**：没有用 `from_offset` 续读；或读的是另一个 task id；或监控本身卡在 SSH 超时里。

**处理**：

1. 用上次结果返回的 next offset 续读；
2. `shell_tasks` 核对 id 与状态（别用旧 id）；
3. 看监控日志最后一行的时间戳：如果几分钟没更新，监控本身可能卡住 → 停止并重启。

## 10. 监控脚本指向了错误的作业/名称

**症状**：脚本 grep 一个完整作业名，永远匹配不到。

**原因**：`djob` 的 NAME 列截断（`kall_l24_c6*`、`kall_mgr10_*`、`kall_mg1_r5*`）。

**处理**：用作业 ID 白名单，或 `djob -u … -J` 的 `jobId` 字段；不要用完整名字做精确匹配。

## 11. 监控被停掉但状态没同步

**症状**：`shell_tasks` 里 `stopped, signal SIGTERM`，但你还在读它的输出。

**含义**：监控已停，输出不会再增长；最后一段可能停在半行。

**处理**：把它当作“历史日志”读一次最终片段，然后用新 monitor 继续；不要等它再写。

## 12. 快速自检清单（监控异常时逐条过）

```text
[ ] ssh 手工能连、rc=0、能看到 djob 表头
[ ] PATH/_USER/_HOST 三个变量都没写错
[ ] 过滤条件在手工命令上能选出预期作业
[ ] exclude 里没有把自己的作业排掉
[ ] 同一目标只有一个 monitor
[ ] monitor 状态是 running（不是 stopped/expired）
[ ] 读输出用的是正确的 id + 递增 offset
[ ] 目标状态与 monitor 退出码分开判断
```
