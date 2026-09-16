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
| 启动器 | `agent.sh`（统一 agent 启动器，cpupower.sh 模式按 `$_NAME` 分发 cl/cls/op/co/ops/cos；直接调用打印 usage）、`agent-runtime.sh`（Unix 共享 run/session/context/event 状态层）、`agent-status.sh`（只读查看持久运行状态）、`agent-statusline.sh`（cl 状态栏渲染器，Claude Code statusLine 命令调用）、`agent.bat`（Windows 入口，按 `%~nx0` 分发 cl/cls/op/ops/co/cos）、`agent-runtime.ps1`（Windows 共享 run/session/context/event 状态层）、`agent-statusline.ps1`（Windows 状态栏渲染器）、`agent-config.json`（通用配置）、`agent-custom.json.refer`（个性化配置模板）、`ddocker.sh`、`ccloudmusic.sh`、`zipython.sh`、`zjulab.sh`、`vscode_unset.sh` |
| 初始化 | `sh_init.sh`（引导 shell：`-b` 仅部署 _bashrc，`-z` 部署 _zshrc+_oh-my-zsh（默认），`-a` 全部；备份旧点文件带时间戳；zsh/oh-my-zsh 缺失时警告）、`vim_init.sh`、`zerotier_init.sh` |
| 工具 | `wwa.sh`、`ddu.sh`、`llog.sh`、`zsearch.sh`、`zlog.sh`、`cp-small.sh`（cp 包装：跳过 >1MB 文件并记录清单到目标目录）、`mv-small.sh`（mv 包装，同规则） |
| 平台 | `xxattr.sh`（macOS）、`xx99.sh`（X99 工作站） |
| 游戏 | `ttetris.sh`、`ssnake.sh`、`z2048.sh`、`zasciiquarium.sh`、`aaclock.sh` |

`cl`、`cls`、`op`、`co`、`ops`、`cos` 为符号链接（→ `agent.sh`）；`cl.bat`/`op.bat`/`co.bat` 为符号链接（→ `agent.bat`，Windows 检出时符号链接不可用则复制或 `mklink /H`）。

## 平台与注意事项

- `.bat`/`.ps1` 为 Windows 对应版，**不**被别名生成器扫描（只扫 `.sh`）
- `agent.bat` 只负责识别 launcher 名称和转交 PowerShell；`agent-runtime.ps1` 实现与 Unix 版一致的 `data/runs/<run-id>/` manifest/state/context/events、文件锁、session/thread 恢复、`--once`/`--max-turns`/`--max-runtime`/`--stop-file`/`--resume` 和三系 headless 驱动。恢复前会校验 schema、agent、launcher 与 workspace 身份；Windows 需要 `powershell.exe`（或 `pwsh.exe`）；本机 Unix 测试只能做静态检查
- `agent-prompt.txt` 为 cl/op/co 三系（Unix `agent.sh` + Windows `agent.bat`）的 **prompt 单一来源**（`oopencode-prompt.txt`/`ccodex-prompt.txt` 为指向它的符号链接）；保留 `${HOME}`/`${_PWD}` 占位符（op 另支持 `${LIST_FILE}`），运行时替换；**修改 prompt 只改此文件**，勿在脚本内再内嵌
- **agent 驱动模式**（Unix/Windows 语义一致）：`-file/--file PATH` 指定指令文件（cl/op 支持，co 不支持），`-time/--time DUR` 指定「继续」间隔（默认 30s；支持 `30`/`30s`/`5m`/`2h`）。`--once` 执行一次 prompt（及可选文件指令）后结束；`--max-turns N`、`--max-runtime DUR`、`--stop-file PATH` 提供显式上限与外部停止；`--resume RUN_ID` 从 data manifest 复用已有 session/thread。给出任一驱动选项即进入无人值守驱动，按 agent 使用不同 headless 链：op=`opencode run --agent build --auto`（从持久日志提取 `session.id=`，`run -s` 续链）、co=`codex exec --json`（从 `thread.started.thread_id` 提取会话 ID，`exec resume` 续链）、cl=`claude -p`（从 stderr 日志提取 `session_id=`，`-p --resume` 续链）——先发 prompt 并等其回合完成，再将文件内容作为首条指令（若有），之后每间隔发送「继续」，默认最多 100 次继续回合；不给驱动选项时保持各 agent 原生 TUI（TUI 启动同样注入提示词：cl 作为初始消息、op 经 `--prompt`、co 经位置参数，含全局/工作区技能清单与分层上下文）。驱动期间后台 `tail -F` 实时监视 data run 日志，将关键活动行以 `[HH:MM:SS] [LEVEL]` 紧凑行输出到终端
- 模型与覆盖（两层默认相互独立，agent 层优先）：解析顺序为 命令行/环境变量 > `agents.<agent>.model`（agent 自身默认模型，不随途径切换变化）> `providers.<途径>.default_models.<agent>`（当前途径默认模型）；强度同序：`--variant`/`--reasoning-effort`/环境变量 > `agents.<agent>.strength` > 旧键（`agents.opencode.variant`/`agents.codex.reasoning`/`agents.claude.env.CLAUDE_CODE_EFFORT_LEVEL`）> `providers.<途径>.default_strengths.<agent>` > `max`；途径由供应商快捷词、`{CLAUDE,OPENCODE}_PROVIDER`/`CODEX_PROVIDER_ID` 环境变量或 `agents.<agent>.provider` 决定；**供应商快捷词** `pay`/`go`/`gpt`（或完整名 `deepseek-pay`/`opencode-go`/`custom-gpt`）可出现在任意参数位置（如 `cl go`、`op gpt`、`co pay`），切换该 agent 使用的途径；`{OPENCODE|CODEX|CLAUDE}_BIN` 指定二进制（未指定回退 PATH）、`{OPENCODE|CODEX|CLAUDE}_MODEL`/`--model MODEL` 直接覆盖模型；op 另支持 `--variant LEVEL`（经 `OPENCODE_CONFIG_CONTENT` 注入）、co 支持 `--reasoning-effort LEVEL`/`--sandbox`/`--ask-for-approval`（默认 `danger-full-access`/`never`）；co 的 provider/TUI 配置、op 的 agent 名或 cl 的权限模式等默认值见下条配置来源（**原短旗标 `-m/-o/-p/-q/-k/-g/-f/-h` 及 `*_DEFAULT_MODEL_FLAG`、`*_MODEL_M/O/P/Q/K/G/F/H` 已移除**）
- **agent 配置来源**：同目录 `agent-config.json`（通用：模型提供途径——`deepseek-pay`/`opencode-go`/`custom-gpt` 的端点、key 环境变量名与 `wire_api`/`supports_websockets`/`anthropic_auth`，各 agent 机制参数如上下文窗口/TUI 配置/权限/沙箱/审批；`wire_api` 供 co 使用，Codex ≥0.154 只接受 `responses`（`chat` 会在启动时报 `Error loading config.toml`），deepseek 与 opencode-go 端点均已验证支持 `/responses`）+ `agent-custom.json`（个性化两层：`providers.<途径>.default_models`/`default_strengths.<agent>` 定义各供应商下各 agent 的默认模型与强度；`agents.<agent>.provider`/`model`/`strength` 定义 agent 自身默认，与前者相互独立且优先，留空则用当前途径默认值）深度合并后生效；`agent-custom.json` 缺失或为空时回退 `agent-custom.json.refer`（参考模板，可复制后修改；`agent-custom.json` 不入库）。途径 key 依次读 `DEEPSEEK_PAY_API_KEY`/`OPENCODE_GO_API_KEY`/`CUSTOM_GPT_API_KEY`（原 `lqcd`/`LQCD_API_KEY` 已更名 `custom-gpt`/`CUSTOM_GPT_API_KEY`；op 仅注入 key 已设置的途径，custom-gpt 另经 `custom-gpt` provider 注册端点与模型）。供应商快捷词切换途径时，未显式指定 `--model`/`{AGENT}_MODEL` 且 `agents.<agent>.model` 留空，则取该途径的 `providers.<途径>.default_models.<agent>`（未配置则该途径下启动报错，不再回退旧模型）；强度按同一优先级取 `agents.<agent>.strength` 或途径 `default_strengths.<agent>`。`agents.opencode.provider` 仅决定「未指定模型时用哪个途径的默认模型」，opencode 实际注册的途径仍是 `agents.opencode.key_providers` 中 key 已设置者。Unix 端用 python3 解析（可用 `AGENT_CONFIG_PYTHON` 指定解释器），Windows 端用 `ConvertFrom-Json`
- **状态栏（/statusline 同款）**：通用配置 `statusline.segments`/`statusline.use_colors` 为三系共同来源。co 据此生成 `tui.status_line=[...]`（13 段全量）；cl 在私有 `--settings` 中注入 `statusLine` 命令（`agent-statusline.sh`/`agent-statusline.ps1` 按 Claude Code 官方状态 JSON 渲染：`model.display_name`+`effort.level`、`workspace.current_dir`、`context_window.used_percentage`+`total_input_tokens`/`context_window_size`、`rate_limits.seven_day.used_percentage`、`fast_mode`、`cost.total_cost_usd`、`session_id`；无数据源的段自动省略），并覆盖用户/项目级 `settings.json` 里的旧 statusLine（如字面 `\033` 转义导致的乱码）；命令路径带引号，Windows 用正斜杠（Git Bash 会吞反斜杠）。op（opencode）TUI 暂不支持自定义状态栏（`tui.json` 无该配置、插件无 TUI 渲染钩子），保持内置状态栏。`statusline.segments` 可在 agent-custom.json 中按需覆盖
- **自动更新默认关闭**：cl 经 `DISABLE_AUTOUPDATER=1`（`agents.claude.env`，进程环境与 `--settings` 双保险）；op 经 `OPENCODE_CONFIG_CONTENT` 的 `"autoupdate":false`（`agents.opencode.autoupdate`）；co 经 `--config check_for_update_on_startup=false`（`agents.codex.config.check_for_update_on_startup`）。恢复自动更新：改对应通用配置，或用 `OPENCODE_AUTOUPDATE=true`/`CODEX_CHECK_FOR_UPDATE_ON_STARTUP=true`；cl 移除 `DISABLE_AUTOUPDATER` 键
- 旧 key 环境变量名自动过渡：新名缺失且旧名存在时自动导出新名并告警——`DEEPSEEK_API_KEY`→`DEEPSEEK_PAY_API_KEY`、`LQCD_API_KEY`→`CUSTOM_GPT_API_KEY`
- cl/cls 默认 `deepseek-pay` 途径的 Anthropic 兼容端点初始设置（Unix `agent.sh` 与 Windows `agent-runtime.ps1` 一致，仅在启动器进程内导出，端点与 baseline 环境变量无条件覆盖外部同名变量）：`ANTHROPIC_BASE_URL` 取自途径定义；`ANTHROPIC_MODEL` 与 `ANTHROPIC_DEFAULT_{OPUS,SONNET}_MODEL` 跟随模型解析链（默认 `deepseek-pay` → `deepseek-flash[1m]`，别名未在 `agents.claude.env` 显式配置时自动派生），`CLAUDE_CODE_EFFORT_LEVEL` 跟随强度解析链（默认 `max`），`ANTHROPIC_DEFAULT_HAIKU_MODEL`/`CLAUDE_CODE_SUBAGENT_MODEL`/`CLAUDE_CODE_AUTO_COMPACT_WINDOW`/`DISABLE_AUTOUPDATER` 取自 `agents.claude.env`（默认 `deepseek-flash`/`deepseek-flash`/`786432`/`1`）；key 值取自该途径 `env_key` 变量（默认 `DEEPSEEK_PAY_API_KEY`），写入哪个认证变量由途径的 `anthropic_auth` 决定：`auth_token`（缺省）→ `ANTHROPIC_AUTH_TOKEN`（`Authorization: Bearer`），`api_key` → `ANTHROPIC_API_KEY`（`x-api-key`，opencode-go 端点只认这种，用 Bearer 会返回 `401 Missing API key`）；另一认证变量与 settings 文件中对应键一律显式置空以免旧值抢占，key 缺失时两者均清除并告警。用户/项目 `settings.json` 的 `env` 块优先级高于进程环境变量（如 cc-switch 遗留的 `ANTHROPIC_BASE_URL`），故同时生成权限 600 的私有临时设置文件并经 CLI `--settings` 注入（优先级更高，Unix 退出时删除，Windows 在 finally 删除）
- 运行时统一发现当前目录到仓库根的 `AGENTS.md`/`CODEX.md`/`CLAUDE.md`/`OPENCODE.md` 层级清单，并把相关路径按近到远注入 prompt；正文仍由 agent 按需读取。每次会话在 `${HOME}/configure/data/runs/<run-id>/` 生成日志、manifest、state、context 和 JSONL 事件，不再把 `.agent.*` 写入工作目录；同一 run 的 Unix 恢复会回收确认已退出进程留下的旧锁，Windows 依赖独占文件句柄；`agent-status.sh --all --json` 只读查看运行状态。OpenCode 仍保留用户输入兜底补录；Codex/Claude 也使用统一布局
- `cls`/`ops`/`cos` 为 HPC/secure 变体软链接：cls 使用 `CLAUDE_BIN` 或 PATH 中的 `claude`；ops 的 `OPENCODE_BIN` 默认取 `agent-custom.json` 的 `agents.opencode.secure_binary`（vscode-server 内部署路径，升级后会变，可直接设 `OPENCODE_BIN` 覆盖）；cos 不硬编码二进制路径，优先读取 `CODEX_BIN`，否则使用 PATH 中的 `codex`；三者均显示 `launcher: secure/HPC` 标记
- `cctag` 二进制与 `claude_code-skill4git-tag.md` 已删除，git 标签管理技能移至 `../skills/tag/`
- `.agent.*` 仅作为旧版工作目录运行产物保留忽略规则；新版运行日志、manifest、state、context、事件和输入清单统一位于 data run 目录，不入库
- 新增脚本后 `chmod +x <script>` 并在新 shell（或 `source ~/.zshrc`）中直接按名调用；校验语法 `bash -n <script>`
