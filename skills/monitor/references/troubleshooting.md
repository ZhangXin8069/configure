# Troubleshooting — 监控自身的故障排查

顺序原则：**先怀疑观测链路（探针 / 连接 / PATH / 过滤 / 读取），再怀疑被观测目标。**
监控出错的最常见形态是“安静地给出错误结论”，而不是报错。

## 1. 探针一直为空（但目标明显在跑）

**症状**：monitor 每轮输出 `active=` 后面什么都没有，或第一轮就打印哨兵。

**可能原因**（按发生概率排序）：

1. 探针失败被 `|| true` 吞掉 → 输出为空 → **假哨兵**；
2. 命令不在 PATH（非登录 shell、远端环境未初始化）；
3. 目标/主机/用户/URL 写错；
4. 过滤过严（`grep -v` 把整行都排掉、服务端过滤返回空）。

**判定**：手工跑同一条探针，保留 rc 与 stderr：

```bash
# 把 <PROBE> 换成实际探针
<PROBE>; echo "rc=$?"
```

**处理**：脚本里把“探针失败”和“空结果”分成两个分支；连续 N 次失败就
`POLL_ABORT`/`PROBE_ERROR`，而不是打印哨兵。djob 适配器脚本 `../scripts/poll_jobs.sh`
已实现这种结构；其他适配器按同样原则处理。

## 2. 目标长时间 pending/waiting

**症状**：几十分钟都是 pending/waiting，没有进入运行。

**可能原因**：

- 资源配额/队列拥塞/节点关闭/依赖未满足；
- 目标请求的资源超过当前可用；
- 服务启动慢、健康检查未通过；
- 调度器/服务端的过滤或权限导致状态不可见。

**判定**：读适配器的原因字段（调度器的 reason/state message、服务的 error/health 字段、
进程的日志），而不是只看状态词。

**处理**：把原因原文贴给用户，判断是“等”还是“换资源/改队列/修依赖”；**不要**自动重提、
重试或取消别人的目标。不要因为“一直 pending”就断定卡死。

## 3. `maxDurationMs` 到点自动停止

**症状**：`shell_tasks` 显示 monitor `stopped, signal SIGTERM`，日志最后一行不是哨兵。

**含义**：监控超时，**不是**目标完成。目标可能还在跑。

**处理**：

1. 手工查一次目标状态（按适配器探针）；
2. 仍在跑 → 按新预算重启监控（必要时把间隔调大、预算覆盖真实目标时长）；
3. 已结束 → 不需要重启，直接进入数据/结论阶段；
4. 报告里写“监控到 maxDuration 自动停止，目标状态为 X”，不要写“跑完了”。

## 4. 重复监控

**症状**：`shell_tasks` 里有两个以上 monitor 的输出都在更新；两份时间线对不上；连接数翻倍。

**原因**：换目标/换脚本时忘记停旧的；或者“怕漏”又起了一个。

**处理**：

```text
1) shell_tasks(includeStopped:false) 列出所有在跑的 monitor
2) 确认哪个是权威观察者（最新的、覆盖当前目标的）
3) 其余全部 task_stop / kill_shell({taskId})
4) 用权威 monitor 的输出写结论；不要把两份日志拼在一起
```

**预防**：起监控前查重；把“先停旧、再起新”写进换班流程（`patterns.md` 第 4 节）。

## 5. 输出被 stderr 污染

**症状**：每轮输出都有连接工具的警告（SSH post-quantum、认证提示、服务端 warning）；
真正的数据被淹没，`grep state` 之类还可能误命中警告文本。

**处理**：

```bash
… 2>&1 | grep -v -E 'WARNING|post-quantum|store now|openssh\.com|Authorized users'
```

- 只过滤已知噪音；`Permission denied`、`Connection refused`、`Host key verification failed`
  必须保留。
- 不要把 `2>/dev/null` 用在“会失败的关键命令”上：那等于把故障变成静默。
- stderr 是噪音还是错误，要看 rc 和内容；只有噪音才过滤。

## 6. 探针命令输出为空

**症状**：命令返回 0，但没有任何行（连表头/JSON 都没有）。

**排查顺序**：

1. PATH/环境：`command -v <probe>`；远端是否需要 `source`/`export PATH`；
2. 参数：目标 ID/用户/URL/过滤条件是否正确；
3. 选项：是否有无效短选项或服务端过滤导致空结果；
4. 传输：连接是否真的成功（rc、stderr）；
5. 目标：只有以上全部排除后，空输出才等于“没有目标”。

**结论**：空输出是“可能没有目标”，不是“目标成功结束”。

## 7. 目标成功但数据不完整

**症状**：目标状态 `SUCCEEDED`/`exit 0`，但 CSV 行数没变或只有几行。

**原因**：目标级成功只表示进程正常退出；行级失败、跳过的用例、写盘异常都可能不体现在状态里。

**处理**：以数据核对为准（行数、列数、重复、`known_skips`），不要用 `SUCCEEDED` 代替核对；
把差异写进 quarantine/known_skips 并留给用户确认。

## 8. 目标“消失”而不是变成终态

**症状**：上一轮还在 active，下一轮整行没了。

**含义**：目标离开队列/进程表/服务注册（完成、被清理、崩溃）。**不能**据此判定成功。

**处理**：用适配器的历史/详情复核最后一次已知状态；查数据/日志产出；报告写
“已离开 + 最后已知状态”，不要臆断为成功。

## 9. 监控读不到新内容（stale check）

**症状**：check due 到了，读出来的还是上一次的内容。

**原因**：没有用 `from_offset` 续读；或读的是另一个 task id；或监控本身卡在连接超时里。

**处理**：

1. 用上次结果返回的 next offset 续读；
2. `shell_tasks` 核对 id 与状态（别用旧 id）；
3. 看监控日志最后一行的时间戳：如果几分钟没更新，监控本身可能卡住 → 停止并重启。

## 10. 目标匹配错了

**症状**：脚本 grep 一个显示名，匹配不到或匹配到同名族；PID 匹配到监控脚本自身。

**原因**：显示名被截断；同名目标；`pgrep -f` 匹配过宽；URL/ID 写错。

**处理**：用唯一 ID、JSON 字段、PID 文件或完整 URL；不要用截断名做精确匹配。
djob 的 NAME 截断案例见 `djob.md`。

## 11. 监控被停掉但状态没同步

**症状**：`shell_tasks` 里 `stopped, signal SIGTERM`，但你还在读它的输出。

**含义**：监控已停，输出不会再增长；最后一段可能停在半行。

**处理**：把它当作“历史日志”读一次最终片段，然后用新 monitor 继续；不要等它再写。

## 12. 快速自检清单（监控异常时逐条过）

```text
[ ] 探针手工能跑、rc=0、能看到预期字段/表头
[ ] 目标 ID/URL/PID/用户/主机/路径都没写错
[ ] 过滤条件在手工命令上能选出预期目标
[ ] exclude 里没有把自己的目标排掉
[ ] 同一目标只有一个 monitor
[ ] monitor 状态是 running（不是 stopped/expired）
[ ] 读输出用的是正确的 id + 递增 offset
[ ] 目标状态与 monitor 退出码分开判断
```

## Appendix — djob 适配器补充

以下仅适用于 djob；通用规则以上文为准，完整细节见 `djob.md`。

- `djob` 不在默认非登录 shell 的 PATH；远端命令先用 `source /etc/profile` +
  `export PATH=/opt/batch/cli/bin:$PATH`。
- `djob -c`/`dsub -c` 是无效短选项；不确定先 `djob -h`，不要猜参数。
- 长期 PENDING 的无关作业（如 `qcu_opt_base`）加入 `exclude`，否则 all-jobs 哨兵永不触发。
- 资源限制（`testusers_rebuild`）会让作业排队很久后 `FAILED`；原因在 `djob -ll` 的
  `mainStateReasonMsg`/`nodeStateReasons`。
- `STOPPED`/`SSTOPPED` 是挂起，仍属 active；djob 适配器脚本不会因它们退出。
- 队列里“作业消失”是常见完成形态；用 `djob -ll` 复核最后状态，不要自动判定成功。
- djob 适配器脚本：`../scripts/poll_jobs.sh`、`../scripts/wait_all_jobs.sh`、
  `../scripts/watch_job.sh`；离线回归 `../scripts/monitor-scripts.test.sh`。
