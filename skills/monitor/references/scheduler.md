# Scheduler specifics — `djob` / `dsub` / `dkill`

本文件是 `monitor` 技能的调度器细节层。SKILL.md 只给“最小必要知识”，这里给可执行命令、
字段语义、已知坑和本次会话证据。所有示例用占位变量（`$HOST`/`$REMOTE_USER`/`$JOB`），
不把会话里的具体作业 ID 当成唯一路径。

## 1. 远端环境：PATH 是最常见的“假故障”

`djob` 不在默认非登录 shell 的 PATH 里。三种实际可用的写法（本次会话都出现过）：

```bash
# A. 登录 shell（最省事，依赖远端 shell 配置）
ssh -o BatchMode=yes "$HOST" 'bash -lc "djob -u '"$REMOTE_USER"'"'

# B. 显式 source + PATH（推荐写进监控脚本，行为最稳定）
ssh -o BatchMode=yes "$HOST" \
  'source /etc/profile >/dev/null 2>&1 || true; export PATH=/opt/batch/cli/bin:$PATH; djob -u '"$REMOTE_USER"' 2>/dev/null'

# C. 显式 CLI_HOME（部分版本需要）
ssh -o BatchMode=yes "$HOST" \
  'export CCS_CLI_HOME=/opt/batch/cli; export PATH=/opt/batch/cli/bin:$PATH; djob -l '"$JOB"
```

- `source /opt/batch/cli/envs/profile.env` 也是可行的等价入口（本次 `poll_job.sh` 用过）。
- `|| true` 只能包住“可选的 profile 加载”，**不要**把整条 `djob` 管道包成 `|| true`：
  那会把 SSH 失败伪装成“空队列”（见 `troubleshooting.md` 第 1 条）。
- 一律加 `-o BatchMode=yes -o ConnectTimeout=10`，避免监控因为等待密码/指纹而挂死。

## 2. 命令矩阵

| 用途 | 命令 | 输出形态 |
|---|---|---|
| 本用户作业列表 | `djob -u "$REMOTE_USER"` | 表：首行表头，其后每行一个作业 |
| 更宽列 | `djob -u "$REMOTE_USER" -w` | 仍是表；本次实测 NAME 仍被截断 |
| 单作业表格行 | `djob "$JOB"` | 表（含表头），可用 `awk '$1=="'"$JOB"'" {print $3}'` 取状态 |
| 单作业详情 | `djob -ll "$JOB"` | `key<tab>value` 块：`state`、`mainStateReasonCode`、`mainStateReasonMsg`、`nodeStateReasons`… |
| 单作业详情（短） | `djob -l "$JOB"` | 同上更短；可用 `grep -m1 -A0 ' *state '` 取值 |
| JSONL（最稳的解析入口） | `djob -u "$REMOTE_USER" -J` | 每行一个 JSON：`{"data":[{"jobId","state","execNodes",…}]}` |
| 按名字过滤 | `djob -w -n "$NAME"` | 表 |
| 按节点看作业 | `djob -en "$NODE"` | 表 |
| 节点状态 | `dnode "$NODE"` | 节点行（负载/核数等） |
| 提交 / 终止 | `dsub …` / `dkill "$JOB"` | 见第 6 节 |

取值示例（本次会话验证过的两种写法）：

```bash
# 表格行：第二行是作业（$1=ID, $2=NAME, $3=STATE）
ssh "$HOST" '… djob '"$JOB"' 2>/dev/null' | awk '$1=="'"$JOB"'" {print $3}'

# 详情块：字段名在 $1，值在 $2
ssh "$HOST" '… djob -ll '"$JOB"' 2>/dev/null' | awk '$1=="state" {print $2; exit}'
```

`-J` 的 JSON 解析（避免截断名与列漂移）：

```bash
ssh "$HOST" '… djob -u '"$REMOTE_USER"' -J 2>/dev/null' | python3 -c '
import json,sys
want={"<job-id-1>","<job-id-2>"}
for line in sys.stdin:
    line=line.strip()
    if not line: continue
    try: j=json.loads(line)
    except Exception: continue
    for job in j.get("data",[]):
        if job.get("jobId") in want:
            print(job["jobId"], job["state"], job.get("execNodes"))
'
```

## 3. 列与截断名（最容易写错匹配的地方）

`djob -u` 的表头与列序：

```text
ID           NAME         STATE      USER         ACCOUNT      QUEUE                START_TIME           END_TIME             EXEC_NODES
2132717      kall_l24_c6* RUNNING    nsls_yangyb  common       q_hpcapp             2026/11/15 14:41:23  -                    cn19650
2108699      qcu_opt_base PENDING    nsls_yangyb  common       q_hpcapp             -                    -                    -
```

- **NAME 被截断**为约 11 个字符并追加 `*`。本次实测：`kall_l24_c6*`（全名 `kall_l24_c64_…`）、
  `kall_l32_c1*`、`kall_mgr10_*`、`kall_mg1_r5*`、`ym_probe_in*`。`-w` 也没有解决截断。
- 后果：用完整作业名做 `grep` 会**匹配不到**，用前缀做 `grep` 会**误伤同名族**。
  正确做法：用 ID 白名单，或 `-J` 的 JSON 字段（`jobId` 完整）。
- `EXEC_NODES` 是 `-` 表示尚未分配（PENDING）；RUNNING 后才有节点名（如 `cn12090`）。
- `START_TIME`/`END_TIME` 为 `-` 表示还没开始/还在跑。

## 4. 状态词与 active set

| 状态 | 含义 | 是否在 active set |
|---|---|---|
| `PENDING` | 排队中（可能因资源限制长期停留） | 是 |
| `RUNNING` | 正在跑 | 是 |
| `WAITING` | 等待依赖/资源 | 是 |
| `STOPPED` / `SSTOPPED` | 被挂起 | 是 |
| `SUCCEEDED` | 正常结束（**不等于行级/数值 PASS**） | 否（终止态） |
| `FAILED` | 失败结束 | 否（终止态） |
| `CANCELLED` / `KILLED` | 被取消/被杀 | 否（终止态） |

监控脚本的默认 active set 用前 5 个；终止态集合固定为
`SUCCEEDED|FAILED|CANCELLED|KILLED|STOPPED`。**不要把 `SUCCEEDED` 当“结果正确”**：本次会话里
作业成功退出但 CSV 只有部分行（thread9 的 7 行）的情况真实发生过，行级核对是独立步骤。

## 5. 排除项：长期 PENDING 的无关作业

本次 `djob -u` 的每一张快照里都有：

```text
2108699      qcu_opt_base PENDING    nsls_yangyb  common  q_hpcapp  -  -  -
```

它从 14:40 一直 PENDING 到 17:37（跨 3 小时），不属于测试作业。若按“本用户所有作业”做哨兵，
它会**永远**让 `active` 非空，哨兵永不触发。同理还有 `ym_probe_in*` 这类探测作业。

规则：

1. 能列 ID 白名单就列 ID（最可靠）；
2. 否则用 name 前缀匹配自己的作业族，并把已知无关项写进 `exclude`
   （本次 `exclude` 用 `qcu_opt_base`，ID `2108699`）；
3. `exclude` 是**观测过滤**，不是权限：不要因为“排除了”就去 kill 它。

## 6. 资源限制与失败原因（`testusers_rebuild`）

`djob -ll "$JOB"` 的详情块里，长期 PENDING 的原因通常在这里：

```text
    state                               PENDING
    mainStateReasonCode                 20618
    mainStateReasonMsg                  The limit <testusers_rebuild> has been exceeded
    nodeStateReasons                    The node has been closed and cannot be scheduled(16279 of 23552 nodes) : …
                                        The minimum resource allocation requirements cannot be met(2965 of 23552 nodes) : …
                                        No node can meet the requirement of execution nodes preference(2488 of 23552 nodes) : …
                                        No node meets the requirements the exclusive job(1819 of 23552 nodes) : …
                                        The node skipped or else allocation limit <testusers_rebuild> would exceed(1 of 23552 nodes) : cn19699, code=30021
```

读法：

- `mainStateReasonCode`/`mainStateReasonMsg` 是**作业级**原因；`testusers_rebuild` 是账号/资源池的
  配额限制，不是我们代码的 bug。
- `nodeStateReasons` 是**节点级**原因（节点关闭、最小资源不满足、execution-node 偏好、独占作业），
  行很长、会被截断，只取前 200 字符与第一个节点名即可。
- 结局通常是：长时间 PENDING → `FAILED`（本次 2133396 16:41:21 PENDING → 17:01:36 FAILED；
  2133327 16:35:34 PENDING → 17:02:50 FAILED），且**没有数据产出**。
- 处理：报告用户配额/资源限制 + 证据；不要反复重提（重提只会排队再失败），不要 `dkill` 别人的作业。

## 7. `dkill` / `dsub` 的行为边界

- `dkill "$JOB"` 返回“已受理/已提交”只代表命令被接受，**状态会滞后**：紧接着的 `djob -ll` 可能仍显示
  `PENDING`/`RUNNING`，要过一段时间才变 `KILLED`/`CANCELLED`/消失。判定必须用后续 `djob` 复核，
  不能拿“命令返回 0”当“已终止”。
- 没有用户明确授权，不对任何作业执行 `dkill`；本技能默认**只观察**。
- `djob -c` / `dsub -c` 是**无效短选项**（本次会话踩过）。不要凭印象猜参数：
  先 `djob -h` / `dsub -h`，再写监控命令。本次验证可用的短选项：`-u`、`-l`、`-ll`、`-w`、`-n`、
  `-J`、`-D`、`-en`。
- `djob -D`（服务端过滤）在本次会话出现过“过滤后为空、但作业确实存在”的情况：**空结果不可信**，
  要用不带过滤的 `djob -u` 交叉验证。

## 8. SSH 噪音：stderr 会混进输出

远端 OpenSSH 每次连接都会打：

```text
** WARNING: connection is not using a post-quantum key exchange algorithm.
** This session may be vulnerable to "store now, decrypt later" attacks.
** The server may need to be upgraded. See https://openssh.com/pq.html

Authorized users only. All activities may be monitored and reported.
```

这些是 **stderr**；未重定向时会以 `[stderr]` 前缀出现在任务输出里（本次 all-jobs monitor 的日志
每个周期都有 4 行这种噪音）。处理：

```bash
… 2>&1 | grep -v -E 'WARNING|post-quantum|store now|openssh\.com|Authorized users'
```

- 过滤是“降噪”，不是“隐藏错误”：真正的 SSH 错误（`Permission denied`、`Connection timed out`）
  必须保留并让脚本以非零退出了解。
- 不要把 stderr 重定向到 `/dev/null` 后就宣布“队列为空”；先看 rc。

## 9. 本次会话证据（作为案例，不是唯一路径）

时间均为本地 CST（日志文件名是 UTC，`09:03Z = 17:03 CST`）。

| 时间 | 观察 | 出处 |
|---|---|---|
| 14:40:25–14:40:45 | `djob -u` 每 20s：`2132717 kall_l24_c6* RUNNING cn19650`、`2132711 kall_l32_c6* RUNNING cn19699`、`2132724 ym_probe_in* PENDING`、`2108699 qcu_opt_base PENDING` | `s2fd4r83` |
| 16:18:51 | `2133202` 已从列表消失（`GONE`），剩 `2133209 kall_l32_c1* RUNNING cn19699` + `2108699` | `s1ar9jh67` |
| 16:31:36–17:37:19 | 四个 ID（2133322/2133324/2133325/2133326）45s 轮询 87 次：全程 PENDING；17:23:34 `2133322 RUNNING cn12067`；17:24:19 `2133324 RUNNING cn12090`；17:33:30 2133324 消失；17:37:19 剩 `2133325 RUNNING cn12090`、`2133322 RUNNING cn12067`、`2133326 PENDING` | `s1m3twhhb` |
| 16:35:34–17:02:50 | `2133327` 在 PENDING 停 27 分钟后 `FAILED` | `s1oldb7up` |
| 16:41:21–17:01:36 | `2133396` PENDING → FAILED（monitor 自身 completed exit 0） | `m1xa22tu4` |
| 17:03:41 | 一次 `djob -ll` 详情：`state PENDING` + `mainStateReasonMsg The limit <testusers_rebuild> has been exceeded` + `cn19699, code=30021` | `fg-fiep9b` |
| 17:37:48 | all-jobs 第一轮：active 3 —— `2133325 kall_mgr10_* RUNNING`、`2133322 kall_mgr10_* RUNNING`、`2133326 kall_mg1_r5* PENDING` | `m21zy0uf7` |
| 17:42:50 | active 2 —— `2133326 kall_mg1_r5* RUNNING`、`2133322 kall_mgr10_* RUNNING`（2133325 已离队） | `m21zy0uf7` |
| 17:47:51–18:02:55 | active 1 —— 只剩 `2133326 kall_mg1_r5* RUNNING`（2133322 已离队，即 `kall_mgr10_*` 完成） | `m21zy0uf7` |

结论（可直接复用）：

1. 名称截断真实存在（`kall_mgr10_*`、`kall_mg1_r5*`），按 ID 或 `-J` 匹配；
2. 无关的长期 PENDING（`qcu_opt_base`）必须排除，否则 all-jobs 哨兵永不触发；
3. PENDING 可以持续几十分钟，最后可能是 `FAILED` 而不是 `SUCCEEDED`——监控要覆盖这条路径；
4. “作业从列表消失”是常见的完成形态（2133202、2133324、2133325、2133322），
   报告里要写“已离开队列/最后已知状态”，不要臆断为成功。
