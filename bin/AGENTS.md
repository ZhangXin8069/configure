# AGENTS.md — bin 工具脚本

工具 shell 脚本目录。`bin/` 由 `env.sh` 前置到 `PATH`，所有 `.sh`（含 `cl`/`op`/`co`/`cos` 等符号链接）可直接按名调用（`gpush.sh`、`ssub.sh`）。脚本必须可执行且带 shebang。

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
| 启动器 | `cclaude.sh`（Claude Code）、`oopencode.sh`（opencode build agent，prompt 取自同目录 `oopencode-prompt.txt` 单一来源；每次会话生成 `.agent.<TS>.log` 运行日志与 `.agent.<TS>.list` 用户输入清单；`-h/-o/-p/-f/-q/-k/-g/-m` 选模型，默认 `-m`=Build auto·Muse Spark 1.2 Contributor OpenCode Go·xhigh（Build auto·Muse Spark 1.2 Contributor OpenCode Go xhigh）；`-o`=Build auto · Ox Alpha Free (Unlimited) OpenCode Go·max、`-h`=Hy3 high 仍可显式指定；支持 `-file/-–file PATH` 与 `-time/-–time DUR` 驱动模式，见下方「op 系列驱动模式」）、`oopencode.bat`（Windows 对应版，同一 prompt 模板，默认 `-m`=Build auto·Muse Spark 1.2 Contributor OpenCode Go·xhigh，同样支持驱动模式选项）、`oopencode-snsc.sh`（HPC/snsc 变体：自动收集工作目录 AGENTS.md/.opencode 项目上下文注入 prompt，硬编码调用 vscode-server 内手动部署的 debug 二进制；`-h/-o/-p/-f/-q/-k/-g/-m` 选模型，默认 `-f`=DeepSeek V4 Flash，`-o`=Build auto · Ox Alpha Free (Unlimited) OpenCode Go·max、`-m`=Build auto·Muse Spark 1.2 Contributor OpenCode Go·xhigh 仍可显式指定；同样支持驱动模式选项；经 `ops` 软链接调用）、`ddocker.sh`、`ccloudmusic.sh`、`zipython.sh`、`zjulab.sh`、`vscode_unset.sh` |
| 启动器 | `ccodex.sh`（Codex build agent：prompt 取自同目录 `ccodex-prompt.txt`；默认 `-m`=`gpt-5.6-luna`/`max`，默认权限为 Full Access（`danger-full-access`），`-o`=`max`，`-f`=`low`，其余旗标选择 Codex 模型；支持 `--model`、`--reasoning-effort` 与 `-file/--file`、`-time/--time` 驱动模式）、`ccodex.bat`（Windows 对应版，同一 prompt 模板）、`ccodex-snsc.sh`（HPC/snsc 入口：复用 `ccodex.sh`，默认 `-f`，可用 `CODEX_BIN` 指定手动部署的 Codex 二进制；经 `cos` 软链接调用） |
| 初始化 | `sh_init.sh`（引导 shell：`-b` 仅部署 _bashrc，`-z` 部署 _zshrc+_oh-my-zsh（默认），`-a` 全部；备份旧点文件带时间戳；zsh/oh-my-zsh 缺失时警告）、`vim_init.sh`、`zerotier_init.sh` |
| 工具 | `wwa.sh`、`ddu.sh`、`llog.sh`、`zsearch.sh`、`zlog.sh`、`cp-small.sh`（cp 包装：跳过 >1MB 文件并记录清单到目标目录）、`mv-small.sh`（mv 包装，同规则） |
| 平台 | `xxattr.sh`（macOS）、`xx99.sh`（X99 工作站） |
| 游戏 | `ttetris.sh`、`ssnake.sh`、`z2048.sh`、`zasciiquarium.sh`、`aaclock.sh` |

`cl`、`op`、`ops`、`co` 与 `cos` 为符号链接（→ cclaude.sh / oopencode.sh / oopencode-snsc.sh / ccodex.sh / ccodex-snsc.sh）。

## 平台与注意事项

- `.bat`/`.ps1` 为 Windows 对应版，**不**被别名生成器扫描（只扫 `.sh`）
- `oopencode-prompt.txt` 为 op 系列（`oopencode.sh`/`oopencode.bat`）的 **prompt 单一来源**（保留 `${HOME}`/`${_PWD}`/`${LIST_FILE}` 占位符，运行时替换）：`oopencode.sh` 经 bash 参数展开替换、`oopencode.bat` 经 PowerShell 替换；**修改 prompt 只改此文件**，勿在脚本内再内嵌
- **op 系列驱动模式**（三脚本一致）：`-file/--file PATH` 指定指令文件，`-time/--time DUR` 指定「继续」间隔（默认 30s；支持 `30`/`30s`/`5m`/`2h`）。给出任一即进入无人值守驱动：headless `run --agent build --auto` 链——先发 prompt 并等其回合完成，从 `.agent` 日志提取 `session.id=`，再将文件内容作为第一条指令发送，之后每间隔发送「继续」，直至 Ctrl+C 或连续 3 次失败终止；仅给模型旗标时保持原 TUI 交互。驱动期间后台 `tail -F` 实时监视 `.agent` 日志，将工具调用/权限评估/错误以 `[HH:MM:SS] [LEVEL]` 紧凑行输出到终端（`opencode run` 的文本与 json 事件均在回合完成时批量到达，唯一实时流是 DEBUG 日志）。示例：`op -o -file /root/PyQCU/logs/v20260824.txt --time 30s`
- `ccodex-prompt.txt` 为 co 系列（`ccodex.sh`/`ccodex.bat`）的 **prompt 单一来源**（保留 `${HOME}`/`${_PWD}`/`${LIST_FILE}` 占位符，运行时替换）：Unix 经 bash 参数展开替换，Windows 经 PowerShell 替换；**修改 Codex prompt 只改此文件**，勿在脚本内再内嵌
- **co 系列驱动模式**（Unix/Windows 语义一致）：`-file/--file PATH` 指定指令文件，`-time/--time DUR` 指定「继续」间隔（默认 30s；支持 `30`/`30s`/`5m`/`2h`）。给出任一即进入无人值守驱动：先用 `codex exec --json` 发送 prompt，从 `thread.started.thread_id` 提取会话 ID，再用 `codex exec resume` 发送文件内容和后续「继续」，直至 Ctrl+C 或连续 3 次失败；仅给模型旗标时保持 Codex TUI。驱动期间 Unix 后台 `tail -F` 监视 JSONL，筛出工具调用/权限评估/错误/最终消息；`approval_policy`、`sandbox_mode`、`model_reasoning_effort` 通过 `--config` 注入，以兼容 `exec resume`。示例：`co -o -file /root/PyQCU/logs/v20260824.txt --time 30s`
- `ccodex-snsc.sh` 是 co 系列的 HPC/snsc 薄入口，默认使用 `-f`；不硬编码二进制路径，优先读取 `CODEX_BIN`，否则使用 PATH 中的 `codex`。Codex 没有 OpenCode `export` 等价接口，驱动模式的文件指令和「继续」消息由包装器写入 `.agent.<TS>.list`，TUI 中直接输入仍依赖 prompt 约定记录
- `cctag` 二进制与 `claude_code-skill4git-tag.md` 已删除，git 标签管理技能移至 `../skills/tag/`
- `.agent.*.log`（opencode/Codex 运行日志）与 `.agent.*.list`（会话用户输入清单）为运行产物，不入库
- 新增脚本后 `chmod +x <script>` 并在新 shell（或 `source ~/.zshrc`）中直接按名调用；校验语法 `bash -n <script>`
