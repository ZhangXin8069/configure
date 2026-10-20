# AGENTS.md — configure 仓库总览

个人 shell/点文件配置仓库（ZhangXin）。为多台机器（工作站、笔记本、HPC 集群、容器、云端）提供版本化 shell 配置、工具脚本与环境引导。

## 入口与加载链

`env.sh` 被 **source**（不可直接执行），由 `~/.zshrc` 与 `~/.bashrc` 引入（`[ -r ]` 存在才 source，避免缺失报错），负责：

1. 将 `bin/`、`~/.local/bin` 等前置到 `PATH`（**防重复**：已含仓库 `bin` 前缀则跳过，可安全多次 source）
2. 设置 `LD_LIBRARY_PATH`（仓库 `lib/` 优先，防重复规则同 PATH）
3. 检测 UTF-8 locale：`LANG` 已是 UTF-8 时跳过；否则单 `grep -im1` 查 `C.UTF-8`/`en_US.UTF-8`
4. source `lib/_git_aliases.sh`（git 别名；zsh 专有别名 `gk/gke/globurl/gtl/gup*` 按 `$ZSH_VERSION` 分支定义，bash 下自动补 `git_current_branch`/`git_main_branch`/`git_develop_branch` 与 `ggu` 函数兜底）
5. 定义两 shell 通用别名（导航/grep/ls 系/常用工具；`history=omz_history`、`which-command=whence` 仅 zsh 下定义，按 `$ZSH_VERSION` 分支）

点文件部署：`bin/sh_init.sh [-b|-z|-a]`——`-b` 仅部署 bashrc；`-z` 部署 zshrc 与 oh-my-zsh（默认）；`-a` 全部；旧文件备份带时间戳。

## 目录结构

| 路径 | 用途 |
|---|---|
| `env.sh` | 环境主入口（shell 启动时被 source）：PATH/LD_LIBRARY_PATH（防重复）、locale、git 别名、两 shell 通用别名 |
| `bin/` | 工具脚本，`env.sh` 将其加入 PATH 后直接按名调用；统一启动器 `agent.sh`（软链接 cl/op/co/ops/cos 分发，Windows 版 `agent.bat` 按 `%~nx0` 分发）支持 cl（Claude Code）/op（OpenCode）/co（Codex）三系无人值守驱动模式，供应商快捷词包含 `pay/go/zen/gpt`，模型途径与各供应商/各 agent 默认模型/强度见 `bin/agent-config.json` 与 `bin/agent-custom.json.refer`（用户 `bin/agent-custom.json` 优先）；`bin/agent-dispatch.sh` 提供默认继承父 agent 设置的一次任务 JSON 派发接口；模型目录自动刷新、模糊匹配与强度顺延由 `bin/agent-model-catalog.py` 及 Windows runtime 对应实现，Chat-only 模型的 Responses/Messages 协议转换由 Unix `bin/agent-protocol-bridge.py` 提供，Codex 原生 goal 的预算查看与修复由 `bin/agent-goal.sh` 提供，详见 `bin/AGENTS.md` |
| `lib/` | 版本化环境配置与基础模板；`lib/requirements/` 保存 APT/PIP 功能依赖清单 |
| `lib/{name}-v{YYYYMMDD}/` | 带版本日期的环境配置 |
| `skills/` | agent 技能（init、tag、debug、optim、diff、auto、all、analy、make、plan、review、skill-creator、tdd、test、up、brainstorm、form、log、rule），`{~skill-name}` 触发；具体索引与公共契约见 `skills/AGENTS.md` |
| `docs/` | 参考文档、分析资料、图片素材；功能输入不放此目录 |
| `logs/` | 任务需求单与 agent 阶段/完成日志；需求单沿用 `v{YYYYMMDD}.txt`，`log` 技能按紧凑时间戳生成日志并维护 `logs/AGENTS.md` 批次索引 |
| `refer/` | 外部参考项目拷贝（如 `git-rep/oh-my-codex`），只读对照，不属于本库维护范围 |
| `data/` | agent 运行时本地数据：runs manifest/state/events/context/log/inputs，`cache/` 为 Codex 模型元数据目录缓存；默认不入库 |
| `hooks/` | Codex agent hook 适配层与独立 Git 质量门禁；不会自动修改 Codex 配置或 `core.hooksPath` |
| `plugins/` | Codex 插件推荐索引与显式安装器；不自动安装第三方插件 |
| `tools/` | 配置仓库维护工具与上游工具推荐信息 |
| `lib/_clash/` | Clash 代理环境安装包包装目录；`setup.sh --check` 仅检查，默认执行会解压覆盖子目录 |

## 外部组件边界

`lib/_clash/clash-for-linux` 是 Git 索引中的外来 gitlink，上游自身的实现细节不属于本仓库维护范围；本仓库只通过父目录的 `lib/_clash/setup.sh` 解压和检查它。父脚本使用 `BASH_SOURCE` 与 Git 根目录动态定位，检查入口为 `bash lib/_clash/setup.sh --check`；需要代理环境时由子目录的 `env.sh` 提供 `source env.sh --status` 检查。

## 版本化配置约定（lib/{name}-v{YYYYMMDD}/）

- 更新配置时**新建**带当天日期的目录，不改旧目录（旧版保留作历史参考）
- `env.sh` 用 `@SECTION@`（单@，激活块）/ `@@SECTION@@`（双@，注释块）标记分节
- 安装命令首次运行后保留为注释，只留生效的 export，保证可复现

## Agent 进程、资源与条件式交付规则

- `rule` 与 `log` 都是常驻辅助技能；用户未明确关闭时，随任一技能在对应门控点执行。`rule` 管进程时限、
  长任务进度、共享/调度资源与阶段交付，`log` 管阶段/最终日志归档。
- agent 发起的命令、后台任务、子 agent 和调度作业必须有有限超时；预计运行超过 10 分钟时必须有真实进度、
  周期心跳和停滞判据，异常进程先取证再中断并进入 debug/optim。
- 共享登录节点和工作站使用最小充分资源；不明确时按共享环境处理。Slurm 等作业必须显式声明 queue/partition、
  time、nodes、CPU、内存、GPU、输出与清理边界；真实大任务按证据分配足量资源，不以降规模或降质量省成本。
- 阶段验收全部通过、改动范围清楚、日志已归档、无敏感信息或超限文件且远程可 fast-forward 时，`rule` 的
  条件式授权允许自动本地提交、正常 push 和创建非破坏性标签，无需再次请求确认。
- force push、删除/改写已推送标签、破坏性清理、系统配置、凭据操作、仓库外写入和用户明确禁止的动作不在
  自动授权范围内。

<!-- form-skill:start -->
## form 格式约定

> 本节由 form 技能同步维护；本文件其他原有约定与本节冲突时，以其他原有约定为准，
> 用户明确指令优先于两者。

- 库类型：simple；主导语言：bash，辅助语言为 python/json/other。
- 文件名：代码文件全小写；多词命令用 `-` 连接，内部函数脚本用 `_`，测试用
  `*.test.sh`；不得重新引入大小写混排的文件名。
- 函数名：`snake_case`；脚本内部函数使用 `_snake_case`；入口函数使用 `main`。
- 变量名：普通变量使用 `snake_case`，环境变量和短脚本状态可使用 `_UPPER_CASE` 或
  `_snake_case`，例如 `_SRC`、`_PATH`、`_NAME`。
- 命名质量：所有名称必须清晰、无歧义，在简短的同时承载最大实际意义；不得使用标签名替代业务语义。
- Agent 规则文件：所有目录统一使用 `AGENTS.md`；`AGENT.md` 是历史输入错误，不是兼容别名。
  同目录两者并存时，以 `AGENTS.md` 为主文件合并双方有效内容并去重，确认后再删除单数文件。
- 目录：顶层白名单为 `bin/data/docs/hooks/lib/logs/plugins/refer/skills/tools`；
  功能输入不得放入 `docs/`，包依赖清单存放在 `lib/requirements/`。
- 文档：`docs/` 只放当前任务文档和图片，允许 `md/tex/pdf/png/jpg/jpeg/gif/svg/webp`。
- 日志与数据：日志放 `logs/`；agent 日志使用 `vYYYYMMDD[HH[MM[SS]]].txt` 或对应连字符
  格式，批次索引为 `logs/AGENTS.md`；数据放 `data/`，仅跟踪 `.gitignore`、`AGENTS.md`、
  `README.md`。
- 测试与验收：shell 至少执行 `bash -n`；结构检查运行
  `skills/form/scripts/form-audit.sh --root . --strict --quiet`；快照检查运行
  `skills/form/scripts/form-snapshot-verify.sh --quiet`。
- Git 收尾：普通改动执行 `git diff --check`，未获明确授权不暂存、提交、推送或打标；
  完整 `~form` 交付流程可按其 Step 8 执行提交、推送和 `dev` 标签。
- Git 大文件：除用户明确要求外，禁止提交单个大于 `10,000,000` 字节的文件；每批暂存后
  运行 `skills/form/scripts/form-large-files-check.sh --root .`，命中时立即停止该批提交
  与推送并提醒用户。5 分钟无回复时只继续推进不依赖超限文件的工作，静默不授权覆盖限制。
- 例外：`refer/**`、`skills/form/references/source-snapshots/**`、vendored/generated
  文件保留上游名称；本库自身新增文件不得据此随意申请例外。
- 标签名只用于版本定位，可在更新说明、提交说明、注释和日志中作为版本引用，但不得进入
  文件、目录、对象、函数、变量等名称；发现违规时由 form 整批纠正全部受影响引用。
<!-- form-skill:end -->

## 命令

- 无构建/lint/测试框架（纯 shell 脚本），校验脚本语法用 `bash -n <script>`
- 修改 `skills/rule/scripts/` 后运行 `bash skills/rule/scripts/run-guarded.test.sh`
- 仓库未安装自动 Git hook；任何 agent 提交前都必须执行上述大文件闸门；
  `.agent.*.log` 为 opencode/Codex 运行日志，不入库
