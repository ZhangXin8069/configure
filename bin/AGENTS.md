# AGENTS.md — bin 工具脚本

工具 shell 脚本目录。`bin/` 由 `env.sh` 前置到 `PATH`，所有 `.sh`（含 `cl`/`op`/`co`/`ops`/`cos` 等符号链接）可直接按名调用（`gpush.sh`、`ssub.sh`）。脚本必须可执行且带 shebang。

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
| 启动器 | `agent.sh`（统一 agent 启动器，cpupower.sh 模式按 `$_NAME` 分发 cl/op/co/ops/cos；直接调用打印 usage）、`agent.bat`（Windows 对应版，按 `%~nx0` 分发 `cl.bat`/`op.bat`/`co.bat`）、`ddocker.sh`、`ccloudmusic.sh`、`zipython.sh`、`zjulab.sh`、`vscode_unset.sh` |
| 初始化 | `sh_init.sh`（引导 shell：`-b` 仅部署 _bashrc，`-z` 部署 _zshrc+_oh-my-zsh（默认），`-a` 全部；备份旧点文件带时间戳；zsh/oh-my-zsh 缺失时警告）、`vim_init.sh`、`zerotier_init.sh` |
| 工具 | `wwa.sh`、`ddu.sh`、`llog.sh`、`zsearch.sh`、`zlog.sh`、`cp-small.sh`（cp 包装：跳过 >1MB 文件并记录清单到目标目录）、`mv-small.sh`（mv 包装，同规则） |
| 平台 | `xxattr.sh`（macOS）、`xx99.sh`（X99 工作站） |
| 游戏 | `ttetris.sh`、`ssnake.sh`、`z2048.sh`、`zasciiquarium.sh`、`aaclock.sh` |

`cl`、`op`、`co`、`ops`、`cos` 为符号链接（→ `agent.sh`）；`cl.bat`/`op.bat`/`co.bat` 为符号链接（→ `agent.bat`，Windows 检出时符号链接不可用则复制或 `mklink /H`）。

## 平台与注意事项

- `.bat`/`.ps1` 为 Windows 对应版，**不**被别名生成器扫描（只扫 `.sh`）
- `agent-prompt.txt` 为 cl/op/co 三系（Unix `agent.sh` + Windows `agent.bat`）的 **prompt 单一来源**（`oopencode-prompt.txt`/`ccodex-prompt.txt` 为指向它的符号链接）；保留 `${HOME}`/`${_PWD}` 占位符（op 另支持 `${LIST_FILE}`），运行时替换；**修改 prompt 只改此文件**，勿在脚本内再内嵌
- **agent 驱动模式**（Unix/Windows 语义一致）：`-file/--file PATH` 指定指令文件（cl/op 支持，co 不支持），`-time/--time DUR` 指定「继续」间隔（默认 30s；支持 `30`/`30s`/`5m`/`2h`）。给出任一即进入无人值守驱动，按 agent 使用不同 headless 链：op=`opencode run --agent build --auto`（从 `.agent` 日志提取 `session.id=`，`run -s` 续链）、co=`codex exec --json`（从 `thread.started.thread_id` 提取会话 ID，`exec resume` 续链）、cl=`claude -p`（从 stderr 日志提取 `session_id=`，`-p --resume` 续链）——先发 prompt 并等其回合完成，再将文件内容作为首条指令（若有），之后每间隔发送「继续」，直至 Ctrl+C 或连续 3 次失败终止；仅给模型旗标时保持各 agent 原生 TUI。驱动期间后台 `tail -F` 实时监视 `.agent` 日志，将关键活动行以 `[HH:MM:SS] [LEVEL]` 紧凑行输出到终端
- 模型旗标与覆盖：`-h/-o/-p/-f/-q/-k/-g/-m` 选模型（默认 op=`-f` DeepSeek V4 Flash 2x、co=`-m` gpt-5.6-luna/max、cl=`-m` claude-sonnet-4-5，cl 默认 slug 可用 `CLAUDE_MODEL_*` 覆盖）；`{OPENCODE|CODEX|CLAUDE}_BIN` 指定二进制（未指定回退 PATH）、`{OPENCODE|CODEX|CLAUDE}_MODEL`/`--model MODEL` 直接覆盖模型；op 另支持 `--variant LEVEL`（默认 max，`-m`=xhigh、`-h`=high，经 `OPENCODE_CONFIG_CONTENT` 注入）、co 另支持 `--reasoning-effort/--sandbox/--ask-for-approval`（默认 `danger-full-access`/`never`，经 `--config` 注入）、cl 固定 `--permission-mode auto`
- op 自动收集工作目录项目上下文（向上查找 AGENTS.md 与 .opencode 注入 prompt），每次会话生成 `.agent.<TS>.log` 运行日志与 `.agent.<TS>.list` 用户输入清单（退出时从会话导出兜底补录）；co/cl 注入全局 agent 配置目录（`${HOME}/configure/{skills,tools,hooks,plugins}`，co 默认以 `--add-dir` 开放已存在目录）与全局/工作区 `SKILL.md` 路径清单，不自动注入 `AGENTS.md` 或 `.codex` 其他上下文，不创建用户输入清单；`exec resume` 复用首次会话的目录上下文
- `ops`/`cos` 为 HPC/snsc 变体软链接：ops 默认 `OPENCODE_BIN` 指向 vscode-server 内部署路径（升级后路径会变，请更新该默认值或设 `OPENCODE_BIN`）；cos 不硬编码二进制路径，优先读取 `CODEX_BIN`，否则使用 PATH 中的 `codex`；二者均显示 `launcher: snsc/HPC` 标记
- `cctag` 二进制与 `claude_code-skill4git-tag.md` 已删除，git 标签管理技能移至 `../skills/tag/`
- `.agent.*.log`（claude/opencode/Codex 运行日志）与 op 系列 `.agent.*.list`（用户输入清单）为运行产物，不入库；co/cl 系列不创建用户输入清单
- 新增脚本后 `chmod +x <script>` 并在新 shell（或 `source ~/.zshrc`）中直接按名调用；校验语法 `bash -n <script>`
