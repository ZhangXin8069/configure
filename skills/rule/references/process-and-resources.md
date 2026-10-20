# 进程预算、共享环境与调度资源

本参考把 `rule` 的时间与资源门控落成可执行判断。具体阈值应来自基线、试跑、历史数据或任务截止时间；
没有证据时先做有界探测，不能把省略限制当成“使用默认值”。

## 1. 进程预算

每个命令、后台任务、子 agent 和调度作业至少记录：

| 字段 | 作用 | 缺失时 |
|---|---|---|
| `label` | 唯一标识进程及日志 | 自动生成稳定名称 |
| `environment` | 独占、共享、调度或远程 worker | 按共享环境处理 |
| `estimated_duration` | 估算依据与量级 | 先做有界试跑 |
| `soft_deadline` | 超过后开始判断异常 | 由估算上界与截止时间推导 |
| `hard_timeout` | 必须终止的上限 | 不启动 |
| `heartbeat` | 心跳输出间隔 | 长任务默认不超过 60 秒 |
| `progress_signal` | 真实进展指标 | 不启动超过 10 分钟的任务 |
| `stale_after` | 无进展异常阈值 | 默认 3 个心跳周期 |
| `cpu/memory/gpu/disk` | 资源上限 | 使用最小充分值或阻塞 |
| `concurrency` | 子进程、worker 或作业上限 | 默认串行 |
| `cleanup` | 终止后清理范围 | 启动前补齐 |

时间预算可表示为：

```text
hard_timeout = min(task_deadline_remaining, p95_estimate * safety_factor)
soft_deadline = min(hard_timeout * 0.75, baseline_upper_bound)
```

安全系数按波动性选择，并在运行后根据实测修正。第一次运行没有基线时，使用小输入、短步数或只读探测建立
量级；不得用无限超时等待答案。

## 2. 长任务进度协议

推荐事件格式：

```text
[rule] event=start ts=<ISO-8601> label=<label> pid=<pid> timeout_s=<n> heartbeat_s=<n>
[rule] event=progress ts=<ISO-8601> label=<label> phase=<phase> completed=<n> total=<m> unit=<unit>
[rule] event=resource ts=<ISO-8601> label=<label> elapsed_s=<n> cpu_pct=<n> rss_kb=<n> disk_bytes=<n>
[rule] event=checkpoint ts=<ISO-8601> label=<label> path=<path> completed=<n>
[rule] event=exit ts=<ISO-8601> label=<label> status=<code> elapsed_s=<n>
```

真实进度优先使用完成项、迭代数、字节数、样本数、检查点序号或已验证阶段；无法直接量化的任务使用“当前阶段
开始/完成”事件。心跳不能替代真实进度，日志刷屏也不能替代有效进度。

健康阈值：

- `无进度时长 > stale_after`：进入异常调查；
- 当前耗时超过 `soft_deadline` 且 ETA 无法由实际速率解释：进入异常调查；
- RSS 持续增长且没有已知缓存上限：检查泄漏；
- 子进程数超过预算、出现重复重试或错误风暴：限流并调查；
- 输出磁盘接近配额：暂停写入并清理或迁移；
- 进程退出码非零、被信号终止或没有结束事件：按失败处理。

## 3. `run-guarded.sh`

基本用法：

```bash
skills/rule/scripts/run-guarded.sh \
  --label pytest-full \
  --timeout 45m \
  --heartbeat 60 \
  --stale-after 180 \
  --output-log .agent.rule-process.log \
  --event-log .agent.rule-events.log \
  -- pytest -q
```

参数：

- `--timeout`：必填，支持整数秒或 `s/m/h/d` 后缀；
- `--heartbeat`：事件日志中的存活与资源采样间隔；
- `--stale-after`：监视文件在该时长内未更新则终止；
- `--watch-file`：由任务主动更新的进度或检查点文件；
- `--output-log`：子进程标准输出与错误输出日志，也作为默认监视文件；
- `--event-log`：独立结构化事件日志；事件同时输出到 stderr；
- `--kill-after`：TERM 后等待强制 KILL 的秒数。

预计超过 10 分钟时必须提供 `--output-log` 或 `--watch-file`。脚本使用系统 `timeout` 或 `gtimeout`，
两者都不存在时直接失败，而不是无界运行。

## 4. 共享交互环境

环境不明确时默认是共享环境。基本策略：

| 资源 | 默认动作 |
|---|---|
| CPU | 单线程；只有实测需要时提升，并设置线程库环境变量 |
| 进程 | 串行或小幅并行；避免 fork bomb、重试风暴和大批子进程 |
| 优先级 | `nice -n 10`；可用时 `ionice` 降低磁盘竞争 |
| GPU | 登录节点默认不用；需要时进入调度器 |
| 内存 | 设置任务级上限并监控 RSS；避免无界缓存 |
| 磁盘 | 输出前估算容量，使用任务工作区/scratch，结束时清理 |
| 网络 | 限制并发连接、重试次数和带宽突发 |
| 时长 | 交互命令保持短时有界；长任务转后台监控或调度器 |

登录节点适合查看状态、轻量 Git/文件操作、提交作业和监控。编译、测试矩阵、数据处理、模型训练和数值模拟等
重负载应进入调度器，除非用户明确说明当前节点可用于这些工作。

## 5. 调度器资源规格校准

提交前：

```bash
squeue -u "$USER"
sinfo -s
scontrol show partition '<partition>'
```

确认分区限制、允许时长、节点类型、GPU 规格、队列拥塞和当前同任务作业数。用最小规模试跑测 CPU 时间、
RSS、GPU 显存、IO、单迭代耗时和检查点大小，再外推到完整规模。

最小提交模板：

```bash
#!/usr/bin/env bash
#SBATCH --job-name=<job-name>
#SBATCH --partition=<partition>
#SBATCH --time=<days-hours:minutes:seconds>
#SBATCH --nodes=<nodes>
#SBATCH --ntasks-per-node=<tasks-per-node>
#SBATCH --cpus-per-task=<cpus-per-task>
#SBATCH --mem=<memory-per-node>
#SBATCH --gres=<gpu-resource-if-used>
#SBATCH --output=<job-output-log>
#SBATCH --error=<job-error-log>
#SBATCH --signal=B:TERM@300
set -euo pipefail
```

调度作业内部继续使用 `run-guarded.sh` 或等价机制，防止单个执行段失控。多阶段大任务使用检查点和可恢复的作业链；
每个阶段有单独预算、输出和验收点，避免一个超长作业失败后全部重算。

## 6. 终止与清理

推荐顺序：

1. 记录最后进度、PID/进程树、RSS、CPU、GPU、磁盘、日志尾部和检查点；
2. 对可暂停任务发送 `TERM`，等待检查点和清理；
3. 超过宽限期后终止进程组；
4. 核对父进程和子进程均已退出；
5. 清理锁、临时文件、未完成输出和调度作业，保留诊断证据；
6. 转入 `debug`，修复根因后由 `optim` 调整资源与性能；
7. 用修正后的预算重跑并验证结果，不只比较“这次没有报错”。

终止前先确认进程归属，避免误杀其他用户或本任务无关进程。调度任务使用精确 job id，不使用宽泛批量取消。

## 7. 资源充足性例外

节省资源不能改变验收结果。出现以下情况时，必须提高预算或报告阻塞，而不是缩小任务：

- 降低并发会超过可接受截止时间，且结果不可分片；
- 降精度会超出误差容差或改变物理结论；
- 减少采样、迭代或样本会破坏统计显著性或完整性；
- 减少内存/GPU 会导致换页、OOM 或无法运行；
- 截断测试矩阵会漏掉用户要求的覆盖范围；
- 删除中间结果导致不可复现或后续阶段无法继续。

资源需求应以试跑数据、复杂度、误差预算和任务截止时间说明。若配额不足，给出最小可完成任务预算与阻塞原因。
