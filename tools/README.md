# 推荐工具项目

本目录用于放置仓库维护工具。第三方工具只记录推荐来源，不把二进制或上游源码 vendoring 进配置仓库；实际安装由用户按机器和发行版自行决定。

## 本地项目

### `configure-check.sh`

只读检查当前配置仓库的四棵 agent 配置树（`skills/`、`tools/`、`hooks/`、`plugins/`）：检查技能 frontmatter、技能目录说明和技能表登记，检查 `skills/`、`tools/` 与 `hooks/` 中 Shell 脚本的语法和执行权限，以及已有 Codex 插件 manifest 的基本 JSON/name/version/path 完整性。
技能表和互鉴表检查会忽略 Markdown 转义竖线 `\|`，并要求各自表头与每个数据行列数一致。

`skills/form/references/source-snapshots/` 保留上游快照的文件权限和 shebang 状态，
因此该子树不参与本库 Shell 脚本语法、执行权限和 shebang 检查。

```bash
tools/configure-check.sh
tools/configure-check.sh --root /path/to/configure
tools/configure-check.sh --strict
```

退出码为 `0` 表示没有发现问题，`1` 表示发现结构或语法问题，`2` 表示命令行参数错误。`--strict` 将“没有可直接加载插件 manifest”等警告也提升为失败，适合 CI 门禁。工具不执行 hook、plugin 或安装命令；存在插件 manifest 时使用 Python 3 的标准库解析 JSON，并使用系统临时目录保存 NUL 路径清单后自动清理。

回归测试：

```bash
bash tools/configure-check.test.sh
```

### `coverage-report.sh`

只读汇总当前仓库四棵配置树的覆盖状况，输出 `skills/`、`tools/`、`hooks/`、`plugins/` 的摘要、`skills/` 与 `.opencode/skills/` 的镜像一致性线索，以及缺口提示。它复用 `configure-check.sh` 的发现思路，但不做门禁判定：数据缺口只会出现在报告里，不会把脚本本身变成失败入口。

```bash
tools/coverage-report.sh
tools/coverage-report.sh --root /path/to/configure
```

退出码为 `0` 表示报表成功生成，`2` 表示命令行参数错误。插件 manifest 仍会按 `configure-check.sh` 的规则做 JSON/路径诊断，因此需要 `python3` 可用；其余部分只依赖 Bash、`find`、`sort`、`cmp`、`grep` 和 `sed`。

回归测试：

```bash
bash tools/coverage-report.test.sh
```

### `task-scope.sh`

只读任务分流入口：把自然语言任务分类为合适的技能组合，并给出可并行拆分建议。它不读仓库、不改仓库，也不执行子技能，只输出分类、推荐技能链、拆分建议和依据。

```bash
tools/task-scope.sh "创建 coverage-report.sh、task-scope.sh，并更新 README"
printf '%s\n' "排查 coverage-report 在缺少 AGENTS.md 时的报错，并修复后回归测试" | tools/task-scope.sh
tools/task-scope.sh --task "先帮我评估这个分类器的可行性，再给出实现计划"
```

退出码为 `0` 表示成功分类，`2` 表示参数错误或缺少任务文本。脚本依赖 Bash、`sed`、`tr` 等基础命令，不依赖仓库状态。

回归测试：

```bash
bash tools/task-scope.test.sh
```

### `agent-resume.sh`

检测 agent 因瞬时服务故障意外退出的 run，并在默认等待 10 秒后通过原统一 launcher 执行
`--resume RUN_ID --once`。当前识别 429、重试上限、限流、服务不可用、网关错误、连接重置/超时
和流中断；认证失败、任务正常结束、用户停止、仍在运行的 run 不会恢复。

工具直接消费 `data/runs/<run-id>/manifest.env`，因此普通 agent 与 `agent-dispatch.sh` 派发的
子 agent 使用同一恢复路径。若 Codex 在首个回合失败前已写入 `thread.started` 但 manifest 尚无
`thread_id`，工具会从 `agent.log` 回填；Claude/OpenCode 分别恢复 `session_id`。每个 run 使用
`.auto-resume-attempted` 限制为一次自动尝试，持续 429 不会形成重试风暴。

```bash
tools/agent-resume.sh --check --run-id RUN_ID
tools/agent-resume.sh --run-id RUN_ID
tools/agent-resume.sh                 # 自动选择最新可恢复 run
tools/agent-resume.sh --force --run-id RUN_ID
```

退出码：`0` 恢复成功，`1` 已恢复但 agent 失败，`2` 参数错误，`3` 不可恢复，`4` 正在运行/
已停止/已尝试自动恢复，`5` manifest 或会话标识无效，`6` 找不到 run，`7` launcher 不可用，
`73` 工作目录或写权限不可用，`124` 恢复超时。恢复子进程默认硬超时 1800 秒，可用
`--timeout`、`AGENT_RESUME_DELAY`、`AGENT_RESUME_TIMEOUT` 调整；`AGENT_AUTO_RESUME=0`
可关闭 runtime 自动调度。

回归测试：

```bash
bash tools/agent-resume.test.sh
```

### `agent-resources.py`

只读输出 agent 规划所需的保守资源快照，区分 host CPU/内存、当前进程 affinity、cgroup v2 hard
limit、Slurm allocation、工作盘和 accelerator 可见性。工具不运行 benchmark/stress、不写系统状态，
也不输出 hostname、绝对路径、job ID、device UUID 或原始环境变量值。容器或调度环境中缺失 cgroup
限制时保持 `review_required=true`，不会把 host 可见资源写成 unlimited。

```bash
python3 tools/agent-resources.py
python3 tools/agent-resources.py --no-accelerators --compact
python3 tools/agent-resources.py --proc-root /proc --cgroup-root /sys/fs/cgroup
```

输出为 JSON schema 1，关键字段包括 `cpu.effective_capacity_cores`、`cpu.worker_ceiling`、
`memory.effective_limit_bytes`、`memory.available_estimate_bytes`、`scheduler`、`disk`、
`accelerators`、`completeness`、`warnings` 和 `provenance`。accelerator 管理查询可见只表示候选，
`runtime_usable_devices` 仍为 `null`，不能在未做目标环境验证时宣称框架可用。

回归测试：

```bash
python3 tools/agent-resources.test.py
```

## 上游推荐

| 项目 | 来源 | 推荐用途 | 本库定位 |
|---|---|---|---|
| ripgrep (`rg`) | [BurntSushi/ripgrep](https://github.com/BurntSushi/ripgrep) | 快速、可递归、默认尊重 ignore 规则的文本搜索；也是 `up` 流程优先使用的搜索器 | 基础依赖，缺失时按技能中的回退方案处理 |
| ShellCheck | [koalaman/shellcheck](https://github.com/koalaman/shellcheck) | shell 静态分析，补充 `bash -n` 只能发现语法错误的局限 | 推荐用于提交前人工检查，不作为脚本运行时硬依赖 |
| shfmt | [mvdan/sh](https://github.com/mvdan/sh) | 统一 POSIX shell、bash、mksh 等脚本格式 | 推荐用于格式化变更后的 shell 文件，不自动改写仓库 |
| fd | [sharkdp/fd](https://github.com/sharkdp/fd) | 更易读的文件查找，适合交互式定位配置文件 | 可选交互工具，不参与检查器正确性 |
| fzf | [junegunn/fzf](https://github.com/junegunn/fzf) | 交互式筛选日志、技能和配置路径 | 可选交互工具，不作为 agent 自动流程依赖 |
| Agent Skills 参考实现 | [agentskills/agentskills](https://github.com/agentskills/agentskills) | 需要对外发布标准 Agent Skills 时，核对规范和参考校验工具 | 参考工具；本库仍以本地 `skills/AGENTS.md` 约定为准 |

### 固定 SHA 外部只读技能候选

以下技能来自
[`Shubhamsaboo/awesome-llm-apps@40b16b66`](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/40b16b66e5257c528059bb93ca9410b55d39278a/agent_skills)
（Apache-2.0，核验日期 2026-10-16）。仅在确有对应诊断需求时按固定 SHA 外链使用，不复制到本库，
也不加入默认技能链：

| 技能 | 用途 | 安全边界 | 内容 SHA256 |
|---|---|---|---|
| [`commit-archaeologist`](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/40b16b66e5257c528059bb93ca9410b55d39278a/agent_skills/commit-archaeologist) | 从本地 Git 历史重建代码存在原因、后续改动与共变文件 | 完全离线、只读，不扫描兄弟仓库 | `8f21eb5ff270b4f4d403494fe606aa23b7faa73232dfe8ab0aed4fba1f94dfe5` |
| [`scope-creep-detector`](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/40b16b66e5257c528059bb93ca9410b55d39278a/agent_skills/scope-creep-detector) | 对照声明意图分析 diff 的范围漂移并给出保留/拆分/说明建议 | 完全离线，不改工作树、索引、提交或分支 | `a21a28ce59694554c16ddc19cb3b27620b1e3e5040803df0e40b22f6a34da159` |
| [`dependency-doctor`](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/40b16b66e5257c528059bb93ca9410b55d39278a/agent_skills/dependency-doctor) | 检查依赖清单中的直接依赖坑位与可选 PyPI yank | 默认离线；只有显式 `--online` 才访问 PyPI，修改依赖前需用户确认 | `3b9a4728a8ec7daae2a82723d01c7a4c18cd2cf5851ea24faa5fdc3a779c6d09` |

## 选择原则

优先采用发行版或上游正式发布的可验证版本；安装前核对许可证、架构、更新日期和来源校验。`configure-check.sh` 仍是本目录唯一的门禁入口；`coverage-report.sh` 和 `task-scope.sh` 是只读诊断/建议入口，第三方工具均为可选能力，不会被它们自动下载或调用。
