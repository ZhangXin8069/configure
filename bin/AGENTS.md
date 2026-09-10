# AGENTS.md — bin 工具脚本

工具 shell 脚本目录。`bin/` 由 `env.sh` 前置到 `PATH`，所有 `.sh`（含 `cl`/`cls`/`op`/`co`/`ops`/`cos` 等符号链接）可直接按名调用（`gpush.sh`、`ssub.sh`）。脚本必须可执行且带 shebang。

## 脚本骨架约定

```bash
#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
# ... 逻辑 ...
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
```

- 必须用 `${BASH_SOURCE[0]:-$0}`（不能用裸 `$0`，登录 shell 下 `$0` 为 `-bash` 会报错）
- 执行首尾打印带时间戳标记
- 严格模式 `set -euo pipefail` 仅部分新脚本使用
- **所有 `.sh` 脚本必须有可执行权限**（新建/编辑脚本后执行 `chmod +x <script>`）

## 脚本分类

| 类别 | 脚本 |
|---|---|
| Git | `gpush.sh`（add -A + 时间戳提交 + push 分支与标签）、`gpull.sh`、`gback.sh`、`dgtag.sh`、`gls.sh`、`git_init.sh` |
| 跨仓库批量 | pull 系列 `zg<Repo>pull.sh`（进目标仓库 `git stash push` + `gpull.sh`）与 push 系列 `gz<Repo>push.sh`（进目标仓库 `gpush.sh`），`<Repo>`∈CONFIGURE/PyQCD/PYQCU/MyQCD，路径相对脚本自身 `../../<repo-name>`；`zgALLpull.sh` 聚合 pull：先逐仓探测，缺失则自动从 gitee `zhangxin8069/<Repo>` clone（ssh 失败回退 https），仅对已存在仓库条件调用各 pull；`gzALLpush.sh` 聚合 push：顺序链接各仓 push |
| HPC/Slurm | `ssub.sh`（内嵌模板：gpu-debug 分区、2 GPU）、`ssqueue.sh`、`zsqueue.sh`、`ssrun.sh`、`sstop.sh`、`ssnake.sh`、`ssnsc.sh`、`ssjtu.sh` |
| 系统 | `cpupower.sh`（按 `$_NAME` 分发，`conservative/ondemand/performance/powersave.sh` 为符号链接）、`swap.sh`（64GB /var/swapfile）、`apt_install.sh`、`pip_install.sh`、`poweroff.sh`、`reboot.sh` |
| 启动器 | `agent.sh`（统一 agent 启动器，cpupower.sh 模式按 `$_NAME` 分发 cl/cls/op/co/ops/cos；直接调用打印 usage）、`agent-runtime.sh`（Unix 共享 run/session/context/event 状态层）、`agent-status.sh`（只读查看持久运行状态）、`agent.bat`（Windows 入口，按 `%~nx0` 分发 cl/cls/op/ops/co/cos）、`agent-runtime.ps1`（Windows 共享 run/session/context/event 状态层）、`ddocker.sh`、`ccloudmusic.sh`、`zipython.sh`、`zjulab.sh`、`vscode_unset.sh` |
| 初始化 | `sh_init.sh`（引导 shell：`-b` 仅部署 _bashrc，`-z` 部署 _zshrc+_oh-my-zsh（默认），`-a` 全部；备份旧点文件带时间戳；zsh/oh-my-zsh 缺失时警告）、`vim_init.sh`、`zerotier_init.sh` |
| 工具 | `wwa.sh`、`ddu.sh`、`llog.sh`、`zsearch.sh`、`zlog.sh`、`cp-small.sh`（cp 包装：跳过 >1MB 文件并记录清单到目标目录）、`mv-small.sh`（mv 包装，同规则） |
| 平台 | `xxattr.sh`（macOS）、`xx99.sh`（X99 工作站） |
| 游戏 | `ttetris.sh`、`ssnake.sh`、`z2048.sh`、`zasciiquarium.sh`、`aaclock.sh` |

`cl`、`cls`、`op`、`co`、`ops`、`cos` 为符号链接（→ `agent.sh`）；`cl.bat`/`op.bat`/`co.bat` 为符号链接（→ `agent.bat`，Windows 检出时符号链接不可用则复制或 `mklink /H`）。

## 平台与注意事项

- `.bat`/`.ps1` 为 Windows 对应版，**不**被别名生成器扫描（只扫 `.sh`）
- `agent.bat` 只负责识别 launcher 名称和转交 PowerShell；`agent-runtime.ps1` 实现与 Unix 版一致的 `data/runs/<run-id>/` manifest/state/context/events、文件锁、session/thread 恢复、`--once`/`--max-turns`/`--max-runtime`/`--stop-file`/`--resume` 和三系 headless 驱动。恢复前会校验 schema、agent、launcher 与 workspace 身份；Windows 需要 `powershell.exe`（或 `pwsh.exe`）；本机 Unix 测试只能做静态检查
- `agent-prompt.txt` 为 cl/op/co 三系（Unix `agent.sh` + Windows `agent.bat`）的 **prompt 单一来源**（`oopencode-prompt.txt`/`ccodex-prompt.txt` 为指向它的符号链接）；保留 `${HOME}`/`${_PWD}` 占位符（op 另支持 `${LIST_FILE}`），运行时替换；**修改 prompt 只改此文件**，勿在脚本内再内嵌
- **agent 驱动模式**（Unix/Windows 语义一致）：`-file/--file PATH` 指定指令文件（cl/op 支持，co 不支持），`-time/--time DUR` 指定「继续」间隔（默认 30s；支持 `30`/`30s`/`5m`/`2h`）。`--once` 执行一次 prompt（及可选文件指令）后结束；`--max-turns N`、`--max-runtime DUR`、`--stop-file PATH` 提供显式上限与外部停止；`--resume RUN_ID` 从 data manifest 复用已有 session/thread。给出任一驱动选项即进入无人值守驱动，按 agent 使用不同 headless 链：op=`opencode run --agent build --auto`（从持久日志提取 `session.id=`，`run -s` 续链）、co=`codex exec --json`（从 `thread.started.thread_id` 提取会话 ID，`exec resume` 续链）、cl=`claude -p`（从 stderr 日志提取 `session_id=`，`-p --resume` 续链）——先发 prompt 并等其回合完成，再将文件内容作为首条指令（若有），之后每间隔发送「继续」，默认最多 100 次继续回合；仅给模型旗标时保持各 agent 原生 TUI。驱动期间后台 `tail -F` 实时监视 data run 日志，将关键活动行以 `[HH:MM:SS] [LEVEL]` 紧凑行输出到终端
- 模型旗标与覆盖：`-h/-o/-p/-f/-q/-k/-g/-m` 选模型（默认 op=`-f` DeepSeek V4 Flash 2x、co=`-q` gpt-6-astra/medium、cl=`-m` claude-sonnet-4-5，cl 默认 slug 可用 `CLAUDE_MODEL_*` 覆盖；co 默认旗标可由 `CODEX_DEFAULT_MODEL_FLAG` 覆盖）；`{OPENCODE|CODEX|CLAUDE}_BIN` 指定二进制（未指定回退 PATH）、`{OPENCODE|CODEX|CLAUDE}_MODEL`/`--model MODEL` 直接覆盖模型；op 另支持 `--variant LEVEL`（默认 max，`-m`=xhigh、`-h`=high，经 `OPENCODE_CONFIG_CONTENT` 注入）、co 另默认注入 `lqcd` provider 与 TUI 配置（`model_provider=lqcd`、`forced_login_method=api`、`features.fast_mode=false`，Fast 默认关闭；设置 `CODEX_FAST_MODE=true` 并配合 `CODEX_SERVICE_TIER=fast` 可显式开启）、`personality=pragmatic`、`approvals_reviewer=auto_review`、`model_context_window=1000000`、`model_auto_compact_token_limit=900000`、`tui.status_line=[\"model-with-reasoning\", \"current-dir\", \"hostname\", \"branch-changes\", \"run-state\", \"permissions\", \"approval-mode\", \"context-used\", \"weekly-limit\", \"estimated-thread-cost\", \"thread-id\", \"fast-mode\", \"task-progress\"]`、`tui.status_line_use_colors=true`，key 读 `LQCD_API_KEY`）；co 仍支持 `--reasoning-effort/--sandbox/--ask-for-approval`（默认 `danger-full-access`/`never`，经 `--config` 注入）、cl 固定 `--permission-mode auto`
- 运行时统一发现当前目录到仓库根的 `AGENTS.md`/`CODEX.md`/`CLAUDE.md`/`OPENCODE.md` 层级清单，并把相关路径按近到远注入 prompt；正文仍由 agent 按需读取。每次会话在 `${HOME}/configure/data/runs/<run-id>/` 生成日志、manifest、state、context 和 JSONL 事件，不再把 `.agent.*` 写入工作目录；同一 run 的 Unix 恢复会回收确认已退出进程留下的旧锁，Windows 依赖独占文件句柄；`agent-status.sh --all --json` 只读查看运行状态。OpenCode 仍保留用户输入兜底补录；Codex/Claude 也使用统一布局
- `cls`/`ops`/`cos` 为 HPC/snsc 变体软链接：cls 使用 `CLAUDE_BIN` 或 PATH 中的 `claude`；ops 默认 `OPENCODE_BIN` 指向 vscode-server 内部署路径（升级后路径会变，请更新该默认值或设 `OPENCODE_BIN`）；cos 不硬编码二进制路径，优先读取 `CODEX_BIN`，否则使用 PATH 中的 `codex`；三者均显示 `launcher: snsc/HPC` 标记
- `cctag` 二进制与 `claude_code-skill4git-tag.md` 已删除，git 标签管理技能移至 `../skills/tag/`
- `.agent.*` 仅作为旧版工作目录运行产物保留忽略规则；新版运行日志、manifest、state、context、事件和输入清单统一位于 data run 目录，不入库
- 新增脚本后 `chmod +x <script>` 并在新 shell（或 `source ~/.zshrc`）中直接按名调用；校验语法 `bash -n <script>`
