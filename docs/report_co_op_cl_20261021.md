# co / op / cl 三系启动器对比分析报告

- **日期**：2026-10-21
- **分析身份**：{代码}（软件工程与系统集成视角）
- **分析对象**：`bin/cl`、`bin/op`、`bin/co`（均为 `bin/agent.sh` 的软链接，按调用名分发；`bin/agent.sh:44-51`）
- **运行环境快照**：`claude 2.1.270`、`codex-cli 0.154.0`、`opencode 1.19.3`；个性化配置回退 `agent-custom.json.refer`（三系默认 `opencode-go` / `deepseek-v4.1-flash` / `max`，`bin/agent-custom.json.refer:42-45,78-96`）
- **证据来源**：启动器与运行时源码（给出 `文件:行号`）、`{cl,op,co} --help` 实测、两次低副作用探针（`cl gpt`、`cl go glm-5.3-flash`）
- **未做**：吞吐/延迟/成本基准、长稳测试、逐模型协议矩阵重测。文中工程判断均标注依据，推断项单独标注。

---

## 0. 结论摘要

三者的**启动器工程质量基本同源**：共用 run 目录、manifest/state/events、文件锁、`--once/--max-turns/--max-runtime/--stop-file/--resume`、TUI 瞬时中断自动恢复、secure/HPC 变体、自动安装与 `agent-dispatch.sh` 派发。真正的差异来自**三个 CLI 的协议能力与自身功能边界**。

| 维度 | cl（Claude Code） | op（OpenCode） | co（Codex） |
|---|---|---|---|
| 上游协议 | Anthropic Messages | 按模型原生选择（Chat/Responses/Messages） | Responses |
| 模型覆盖 | **最窄**（受 `/messages` 路由限制） | **最宽**（几乎全部目录模型） | 较宽（Chat-only 模型靠本地桥） |
| 交互 TUI | 生态最完整，权限/ hooks / skills 体系成熟 | LSP 集成，V1/V2 双兼容 | 状态栏 + 沙箱/审批，事件流清晰 |
| 驱动续链 | 已修复（首轮 stdout JSON 取 session id） | 稳（V2 JSON 最稳；本机为 V1） | 稳（JSONL `thread_id`） |
| 文件首指令 `--file` | 支持 | 支持 | **不支持** |
| 驱动强度旗标 | 无（仅位置参数/配置） | `--variant` | `--reasoning-effort` |
| 默认权限姿态 | `permission-mode auto` | `--auto` | `danger-full-access` + `never` |
| 自定义状态栏 | 支持（14 段渲染器） | **不支持**（内置） | 支持（14 段原生） |
| 自动化多轮 | **不推荐**（当前版本） | **首选** | 可用（但无文件指令） |
| 一句话定位 | 交互与权限体验最好，模型面最窄 | 多模型与自动化首选 | Codex 原生能力与可观测性最好 |

**选型速记**：

- 要 **GLM / 多供应商 / 原生多协议 / 稳定的多轮无人值守** → `op`
- 要 **最强交互、权限门控、hooks/skills 生态、Anthropic 原生模型** → `cl`
- 要 **Responses 原生、沙箱与审批可控、结构化事件与状态栏、Codex goal 预算** → `co`
- **一次性子任务派发**：三者都可用；多轮驱动优先 `op`/`co`，`cl` 的缺陷已修复但仅经 fake 验证，真实 API 两轮复验前仍建议保守使用。

---

## 1. 共同底座：三者共享的能力

以下能力与 launcher 无关，由 `agent-runtime.sh` 与 `agent.sh` 公共段提供，因此**不构成选型差异**，但决定了三者的运维一致性：

1. **统一 run 状态层**：`data/runs/<run-id>/` 下的 `manifest.env`、`state.env`、`context.txt`、`events.jsonl`、`agent.log`、`inputs.txt`、`stop`；文件锁与恢复身份校验见 `bin/agent-runtime.sh:733-910`。
2. **分层项目上下文发现**：从当前目录到 Git 根收集 `AGENTS.md`/`CODEX.md`/`CLAUDE.md`/`OPENCODE.md`，按由近及远注入 prompt（`bin/agent-runtime.sh:652-721`）。三系行为一致，不存在“只有 op 收集上下文”的差异。
3. **Prompt 单一来源**：`bin/agent-prompt.txt`，运行时替换 `${HOME}`/`${_PWD}`；三系共用（`bin/AGENTS.md:42`）。
4. **两层模型/强度默认**：显式选途径时 `providers.<途径>.default_models|default_strengths.<agent>` 优先，否则 `agents.<agent>.model|strength` 优先，缺值回退另一层；`--model`/`--variant`/`--reasoning-effort` 与环境变量恒为最高（`bin/AGENTS.md:44`）。
5. **供应商快捷词与位置语法**：`pay|go|zen|gpt` 可出现在任意参数位置；位置参数为 `[供应商] [模型] [强度]`，均不可传提示词。
6. **无人值守控制面**：`--once`、`--max-turns`、`--max-runtime`、`--stop-file`、`--resume RUN_ID`；三系解析逻辑一致。
7. **TUI 瞬时中断自动恢复**：cl 用 `--bg --resume`，op 用 `run -s … --attach`，co 用独立 app-server + `thread/resume`；触发条件是 turn 异常结束而非 TUI 退出（`bin/AGENTS.md:51`）。
8. **secure/HPC 变体**：`cls`/`ops`/`cos`，优先 `*_BIN`，其次 `agents.<agent>.secure_binary`，缺失时完整复制而非软链（`bin/AGENTS.md:60`）。
9. **缺二进制自动安装**：`lib/_claude-code`/`_opencode`/`_codex` 的安装脚本，失败只尝试一次（`bin/AGENTS.md:62`）。
10. **子 agent 派发**：`agent-dispatch.sh --task/--task-file` 默认继承父 launcher/provider/model/strength/cwd/secure/sandbox/approval，三系均有分支（`bin/agent-dispatch.sh:15-19,136-153`）。

> 因此，把三者的优劣简单归结为“启动器实现好坏”是不准确的：共享底座一致，差异主要在**协议层与 CLI 能力**。

---

## 2. 核心差异一：协议与模型路由

### 2.1 协议矩阵

| Launcher | CLI 唯一会说的协议 | 直连条件 | 本地协议桥 | 桥接方向 |
|---|---|---|---|---|
| `cl` | Anthropic Messages | 途径必须提供 `anthropic_base_url`，模型必须在 `/v1/messages` 可用 | 仅 `opencode-zen` 配置了 `claude.bridge_models`（`bin/agent-config.json:131-145`） | Messages → Chat Completions（`bin/agent.sh:1096-1106`） |
| `op` | 按模型原生选择 | OpenCode 自己按模型元数据选 `/chat/completions` 或 `/messages` | **不需要** | — |
| `co` | Responses（Codex ≥0.154 只认 Responses） | 模型必须在 `/responses` 可用，或被桥接 | `opencode-go` 桥接 `deepseek-*`（`:64-68`）；`opencode-zen` 桥接 7 类（`:113-130`） | Responses → Chat Completions（`bin/agent.sh:2492-2500`） |

关键事实：

- **cl 的 `custom-gpt` 途径完全不可用**：配置无 `anthropic_base_url`，启动即退出 64。本次实测：
  `cl gpt` → `ERROR: 途径 'custom-gpt' 未定义 anthropic_base_url`（rc=64）。
- **cl 在 `opencode-go` 上没有桥接**：`opencode-go` 只配置了 `codex.bridge_models`，没有 `claude` 块（`bin/agent-config.json:51-68`）。因此 GLM 家族只能走 `/chat/completions`，cl 无法使用。本次实测：
  `cl go glm-5.3-flash` → 启动后请求返回 `API Error: 400 Model does not support this protocol.`（rc=1）。
- **co 在 `opencode-go` 上对 GLM 也不可用**：桥接列表只有 `deepseek-*`，GLM 直连 `/responses` 会快速失败（`ModelProtocolUnsupported`，见历史实测记录）。deepseek 则已被桥接，绕开上游 responses 适配器“200 但零事件”的假死缺陷。
- **op 是唯一无需桥接即可覆盖全部协议形态的入口**：这既是它模型覆盖最宽的原因，也是其实现最“薄”的原因——协议适配交给 OpenCode 自身。

### 2.2 有效模型覆盖（按当前配置目录）

| 途径 | 目录模型数 | `cl` | `op` | `co` |
|---|---:|---|---|---|
| `deepseek-pay` | 5 | **2/5**（2026-09-16 实测仅 `deepseek-flash`、`deepseek-v4-pro` 支持 `/messages`） | 全部 | 全部（Responses 直连） |
| `opencode-go` | 28 | 仅 `/messages` 子集；GLM 4 款不可用（本次复验 `glm-5.3-flash` 400） | **全部 28** | 除 GLM 4 款外可用；`deepseek-*` 走桥，其余直连 |
| `opencode-zen` | 24 | 桥接 7 款 + `claude-*` 4 款直连 + `qwen*` 2 款（后两者为配置推断）；`gpt/grok/gemini/muse` 共 11 款明确不支持 | **全部 24** | 桥接 7 款 + Responses 直连 10 款；`claude-*`/`gemini-*`/`qwen*` 共 7 款不支持 |
| `custom-gpt` | 端点决定（默认 `gpt-5.6-luna`） | **不可用**（无 Anthropic 端点，rc=64） | 可用 | 可用 |

> 覆盖数字的边界：
> - 表中的“全部”指**配置层允许**，不代表已对每个模型逐一发请求验证；本报告只对 `cl` 的两处限制做了实测。
> - `opencode-go` 的 “14/37 可用” 来自 2026-09-16 对当时端点全量探测；当前配置目录为 28 个模型，**未重测比例**。
> - GLM 家族本次只复验了 `glm-5.3-flash` 一款，其余 3 款按同一 `endpoint` 元数据推断，未逐一发请求。
> - `opencode-zen` 的 `claude-*`/`qwen*` 归类由配置的 `unsupported_models` 与 `bridge_models` 差集推得，非逐模型实测。

### 2.3 强度（strength）支持

- `deepseek-pay` 只声明 `high`/`max`（`bin/agent-config.json:42`），过高强度会按模型目录顺延（如 `ultra → max`）；三系一致。
- `op` 把强度落到 OpenCode `variant`（V2 合并为 `provider/model#variant`）；`co` 落到 `reasoning effort`；`cl` 落到 `CLAUDE_CODE_EFFORT_LEVEL`。
- **CLI 入口不对称**：`op` 有 `--variant`，`co` 有 `--reasoning-effort`，`cl` **没有独立强度旗标**，只能靠第二位置参数或配置（`bin/agent.sh:901-911,971-974,1052-1065`）。脚本化切换强度时，cl 的可读性和显式性最差。

---

## 3. 核心差异二：交互与自动化链路

### 3.1 TUI 形态

| 能力 | `cl` | `op` | `co` |
|---|---|---|---|
| CLI 本体 | Claude Code | OpenCode（本机 V1 1.19.3） | Codex 0.154 |
| 首条 prompt 注入 | `-- "${PROMPT}"`（`bin/agent.sh:1269-1272`） | `--prompt "${PROMPT}"`（`:1863` 附近） | `-- "${PROMPT}"`（`:2690`） |
| 自定义状态栏 | `agent-statusline.sh`，可显示模型/effort、cwd、context、限流、cost、session（`bin/AGENTS.md:53`） | **不支持**（保持内置状态栏） | 原生 `status_line` 14 段（`bin/AGENTS.md:53`） |
| 权限/沙箱 | `permission-mode auto`（配置）；无 CLI 沙箱旗标 | `--auto`；权限由 OpenCode 配置控制 | `--sandbox` / `--ask-for-approval` 可覆盖，默认 `danger-full-access`/`never` |
| 独有机制 | hooks / skills / 子代理生态；`--settings` 私有配置与 `apiKeyHelper` 认证兜底（`bin/AGENTS.md:56,58`） | LSP 默认开启（`bin/agent-config.json:210`）；V2 `default_agent` 兼容层（`bin/AGENTS.md:45`） | app-server 原地恢复；goal 预算工具；模型元数据目录注入（`bin/AGENTS.md:49,51,55`） |

### 3.2 驱动模式（无人值守）

| 项目 | `cl` | `op` | `co` |
|---|---|---|---|
| 首轮 | `claude -p` | `opencode run`（V1）/ `run --standalone --format json`（V2） | `codex exec --json` |
| 续链 | `claude -p --resume <session>` | `opencode run -s <session>` | `codex exec resume <thread>` |
| 会话标识来源 | stdout JSON `session_id`（`bin/agent.sh:1327-1337`），解析失败回退 stderr 正则 | V1 日志 `session.id`；V2 JSON `sessionID`（`:351-363,1909-1916`） | JSONL `thread.started.thread_id`（`:2627-2655`） |
| 首指令文件 | `--file` 支持 | `--file` 支持 | **不支持**（`bin/AGENTS.md:43`） |
| 单次模式 | `--once` 可用；无会话 ID 时直接标记 finished（`:1339-1349`） | `--once` 可用 | `--once` 可用 |
| 多轮稳定性 | 已修复（fake 验证，见 3.3） | **好** | **好** |

**结论**：`op`/`co` 是长时多轮驱动的首选；`cl` 的 session 提取缺陷已于 2026-10-21 修复，但只有 fake 测试证据，真实 API 两轮复验前建议保守使用。派发接口 `agent-dispatch.sh` 使用 `--once`，修复后可直接从 JSON `result` 取回文本（`bin/agent-dispatch.sh:129`）。

### 3.3 `cl` 驱动缺陷与修复（2026-10-21）

- **原缺陷**：首轮 `claude -p` 后从 `agent.log`（stderr）用正则提取 session id；Claude Code 2.1.270 的 `-p` 文本模式不再向 stderr 打印 `session_id`，成功回合也没有。任何 `-file`/多轮驱动都会在首轮后报
  `无法从 <run>/agent.log 提取 session id，驱动终止`。
- **修复**：首轮改为 `claude -p --output-format json`，由 `_run_claude_json_command` 从 stdout JSON 同时取 `session_id` 与 `result`（`bin/agent.sh:250-318,1327`）；JSON 解析失败时保留原始输出，并回退原有 stderr 正则（`:1335-1337`）。
- **兼容性**：TUI 路径、`--resume` 续链、`--once` 无会话 ID 的降级语义均未改变；终端只看到 `result` 文本，派发接口写入 `AGENT_DISPATCH_OUTPUT_FILE` 的也只有该文本。
- **验证**：`bin/agent.test.sh` 新增 fake-claude JSON 主路径、非 JSON 回退路径、`max-turns=1` 两次调用、`session-bound` 事件与派发文本断言；全量 77 项通过，`bash -n` 与 `git diff --check` 通过。
- **未验证**：未对真实 Claude API 发起两轮请求，仅以 fake 覆盖；JSON 字段格式取自本机 2.1.270 的 `--output-format json`。

### 3.4 位置参数陷阱（三系共有，co 最易踩）

三系的位置参数只有 `[供应商] [模型] [强度]`，**没有提示词位**。把提示词塞进第三位会被当作强度：

- `co go deepseek-v4.1-flash 'Say ok.'` → 强度变成 `"Say ok."`，直传上游后报 `400002 reasoning_effort invalid`（历史实测）。
- `cl`/`op` 在出现第三个位置参数时直接报“位置参数过多”并退出 64（`bin/agent.sh:962` 等），至少是快速失败；`co` 的强度不会做合法性拦截，症状离原因更远。
- 需要脚本化喂任务时，应使用 `AGENT_DISPATCH_TASK`/`agent-dispatch.sh`，而不是位置参数。

---

## 4. 权限与安全姿态

| 项目 | `cl` | `op` | `co` |
|---|---|---|---|
| 默认 | `permission_mode=auto`（`bin/agent-config.json:202`） | 启动即 `--auto` | `sandbox=danger-full-access`、`approval=never`（`:220-221`） |
| 可调入口 | 配置文件；无 CLI 旗标 | OpenCode 配置；launcher 未暴露审批旗标 | `--sandbox`、`--ask-for-approval` 显式覆盖 |
| 风险画像 | 中：仍受 Claude Code 权限模型约束 | 中高：默认自动执行 | **最高**：默认无沙箱、无审批，且 `approvals_reviewer=auto_review`（`:236`） |
| 适用 | 交互式开发、需要逐步确认 | 受控容器/订阅环境中的自动化 | 已隔离的工作区、需要完全自主的长任务 |

**判断**：`co` 的默认姿态最激进，优势是长任务不被打断，劣势是误操作成本最高；若工作区不是一次性容器，应显式收紧 `--sandbox` 或 `--ask-for-approval`。`cl` 的权限语义最丰富，但 launcher 没提供 CLI 快捷开关，调参要走配置。`op` 的 `--auto` 固定写入启动参数，安全边界更多依赖 OpenCode 自身配置与外部隔离。

---

## 5. 可观测性与运维

| 项目 | `cl` | `op` | `co` |
|---|---|---|---|
| run 日志/事件 | 共用 `agent.log`、`events.jsonl` | 同左 | 同左 |
| 结构化程度 | 低：stderr 只有零星告警，驱动监视器靠关键字过滤 | 中：`--print-logs --log-level DEBUG`；V2 `--format json` | **高**：`codex exec --json` 的 JSONL 含 tool/file/approval/agent_message 事件 |
| 状态栏 | 自定义渲染器，支持 context/cost/限流/session | 内置，不可定制 | 原生 14 段，可配置 |
| 额外诊断 | 桥 `bridge.log`、私有 `--settings` | 项目上下文提示、V1/V2 版本行 | 模型目录注入提示、桥日志、goal 状态工具 |
| 版本兼容风险 | Claude Code 行为变更直接影响驱动链（已发生） | V1/V2 双路径，本机 V1 未覆盖 V2 实测 | Codex ≥0.154 只认 Responses，需桥接 Chat-only 模型 |

**判断**：`co` 最适合“事后审计/自动解析”；`op` 居中；`cl` 的日志最不结构化，且恰好其驱动链依赖日志文本，形成“弱可观测性 + 强依赖”的耦合风险。

---

## 6. 逐系优劣

### 6.1 `cl`（Claude Code）

**优势**

1. 交互体验与权限模型最成熟：hooks、skills、子代理、`--permission-mode` 语义完整。
2. 自定义状态栏信息密度最高：模型/effort、context 使用率、周限额、cost、session 一屏可见。
3. 认证兜底最细：`apiKeyHelper` + 双认证变量清理，避免 OAuth/Keychain 回退导致的 “Not logged in”（`bin/AGENTS.md:56,58`）。
4. Anthropic 原生模型（zen 的 `claude-*`）无需桥接，协议链路最短。
5. 与现有 `agent-prompt.txt`/skills 清单/分层 AGENTS.md 的集成完全一致。

**劣势**

1. **模型覆盖最窄**：仅 Messages 协议；`opencode-go` 无桥接，GLM 不可用；`custom-gpt` 完全不可用（本次实测 rc=64/400）。
2. **多轮驱动缺陷已修复但仅经 fake 验证**：原实现依赖 stderr `session_id`，2.1.270 下多轮/文件指令链失败；现改为首轮 `--output-format json` 取会话标识，回退路径保留，真实 API 两轮复验尚未执行。
3. 无独立强度旗标，脚本化调强度只能靠位置参数或改配置。
4. 日志结构化程度最低，故障定位依赖关键字与桥日志。
5. 当前代码路径对该缺陷没有预检或降级提示（只有失败后的报错）。

**最适合**：日常交互式开发、需要权限门控与 hooks/skills 生态、以 deepseek/minimax/qwen/kimi 或 zen 的 claude 系为主的场景；一次性派发。

### 6.2 `op`（OpenCode）

**优势**

1. **模型覆盖最宽**：原生按模型选协议，GLM/DeepSeek/Kimi/MiniMax/Qwen/GPT/Grok 等无需桥接。
2. **自动化链路最稳**：V2 `--format json` 从结构化事件取 `sessionID`；V1 也有日志兜底。
3. 支持 `--file` 首指令与 `--variant` 强度旗标，脚本表达力最完整。
4. LSP 默认开启，项目上下文与代码理解体验较好。
5. 支持全部四个途径（含 `custom-gpt`），是唯一“全途径可用”的入口。
6. V1/V2 兼容层设计清晰，升级路径明确。

**劣势**

1. 本机为 V1 1.19.3，V2 的结构化优势**尚未在本机验证**；V1 的 session 解析仍依赖日志文本（弱于 V2）。
2. 无自定义状态栏，context/cost 等运行信息不如 cl/co 直观。
3. 启动器固定 `--auto`，权限收紧入口不如 co 显式。
4. 多一层 `OPENCODE_CONFIG_CONTENT` 配置生成，排障时需要同时理解 OpenCode 自身配置语义。
5. 对 OpenCode 版本行为（V1/V2 字段差异）有持续维护成本。

**最适合**：多模型切换（尤其 GLM）、长时无人值守、脚本化多轮、需要 LSP 与全途径覆盖的日常主力。

### 6.3 `co`（Codex）

**优势**

1. **可观测性最好**：JSONL 事件流含工具调用、文件变更、审批、最终消息，适合监视与自动解析。
2. 沙箱/审批可显式控制（`--sandbox`/`--ask-for-approval`），默认完全自主，适合隔离环境。
3. 原生状态栏 14 段，信息密度高；模型元数据目录注入消除了三方模型的告警。
4. 线程恢复走独立 app-server + `thread/resume`，不依赖 TUI 自动取队列，恢复路径明确。
5. 具备 goal 预算查看/修复工具，长任务成本控制有抓手。
6. Responses 原生，OpenAI 兼容端点（`custom-gpt`）体验最好。

**劣势**

1. **不支持 `--file`**，无法把文件作为首条指令；只能“prompt → 继续循环”，脚本化多步任务表达力弱于 cl/op。
2. **默认安全姿态最激进**：`danger-full-access` + `never`，误操作成本最高。
3. `opencode-go` 上 GLM 未桥接，直连 `/responses` 快速失败；deepseek 必须走本地桥（多一跳，排障面更大）。
4. `opencode-zen` 上 `claude-*`/`gemini-*`/`qwen*` 不支持，跨供应商一致性不如 op。
5. 三方模型元数据需启动时生成并缓存，首次启动有额外开销与 Python 依赖。
6. 位置参数对非法强度不拦截，错误症状远离根因（历史 400002 案例）。

**最适合**：Codex 原生/Responses 端点、需要结构化审计与沙箱控制、在隔离工作区跑长任务、使用 OpenAI 兼容自定义端点。

---

## 7. 选型建议（按场景）

| 场景 | 首选 | 备选 | 理由 |
|---|---|---|---|
| 日常交互式编码，需要权限确认与 hooks/skills | `cl` | `op` | cl 的权限模型与生态最成熟 |
| 使用 GLM / 多供应商频繁切换 | `op` | `co`（仅 zen 的 GLM 桥接） | op 原生多协议，覆盖最全 |
| 长时无人值守、多轮“继续” | `op` | `co` | op 会话解析最稳；co 也稳但缺文件指令 |
| 一次性子 agent 派发 | 任一 | `op`/`co` | 三者均支持 `--once`；op/co 结构化输出更好 |
| 需要 Responses 原生 / OpenAI 兼容端点 | `co` | `op` | co 直连 Responses，custom-gpt 可用 |
| 需要沙箱与审批策略可调 | `co` | `cl`（配置） | co 有显式 CLI 旗标 |
| 需要 context/cost/限流可视化 | `cl` | `co` | cl 状态栏信息最全；op 不支持自定义 |
| HPC/secure 部署 | `cls` | `ops`/`cos` | 三者能力等价，按协议需求选 |
| 审计与自动解析运行记录 | `co` | `op` | co 的 JSONL 事件最完整 |

**默认策略建议**：把 `op` 作为多模型与自动化的默认入口；`cl` 保留给需要权限门控与生态的交互场景；`co` 保留给 Responses/沙箱/审计场景。三者共用底座，切换成本主要是模型与协议约束，而非运维方式。

---

## 8. 风险、限制与未验证项

1. **`cl` 多轮驱动缺陷已修复**：根因是 Claude Code 2.1.270 的 `-p` 不再输出 `session_id`；首轮已改用 `--output-format json` 从 stdout 取会话标识（`bin/agent.sh:1327-1337`），并保留 stderr 回退。fake 测试覆盖主路径、回退路径与派发文本；**尚未对真实 API 做两轮复验**，上线前建议补一次低成本双轮探针。
2. **模型覆盖数字的时效性**：`opencode-go` 的 14/37 是 2026-09-16 实测；当前目录 28 个模型，比例未重测。GLM 仅复验 `glm-5.3-flash` 一款。
3. **本机 OpenCode 为 V1 1.19.3**：V2 的结构化 session 解析、`--standalone` 行为在本机未实测；报告中的 V2 结论来自代码与文档，不是本机运行证据。
4. **未做成本/延迟基准**：`opencode-go` 是订阅制（配置标签为 `$10/月`），`pay`/`zen` 为按量付费，但本报告不比较单价、吞吐或限流表现。
5. **探针副作用披露**：为验证协议边界，本次执行了 `cl gpt`（未发起模型请求，rc=64）和 `cl go glm-5.3-flash`（发起一次真实请求，返回 400；创建了 run 目录 `data/runs/20261021T234311.o3e30B`）。未修改任何配置或源码。
6. **安全默认值**：`co` 的 `danger-full-access` + `never` 来自通用配置，若本机 `agent-custom.json` 覆盖则不同；本报告以仓库内 `agent-config.json` + refer 模板为准。

---

## 9. 证据索引

| 证据 | 位置 |
|---|---|
| launcher 名称分发 | `bin/agent.sh:44-51` |
| 三系 prompt/上下文注入 | `bin/agent.sh:1226-1230`（cl）、`1671-1675`（op）、`2469-2473`（co）；`bin/agent-runtime.sh:652-721` |
| cl 参数与 `--file` | `bin/agent.sh:901-985` |
| cl 驱动链与 session 提取 | `bin/agent.sh:1283-1350`（JSON 提取在 `:1327-1337`） |
| cl JSON 回合包装器 | `bin/agent.sh:250-318` |
| cl TUI 恢复 | `bin/agent.sh:1253-1272` |
| cl 模型/强度两层解析 | `bin/agent.sh:1050-1077` |
| cl 不支持模型的预检与提示 | `bin/agent.sh:1070-1097` |
| op 参数与 `--file`/`--variant` | `bin/agent.sh:1430-1560` |
| op 会话解析（V1/V2） | `bin/agent.sh:351-363,1774-1781,1909-1916` |
| op TUI/驱动 | `bin/agent.sh:1832-1975` |
| co 参数（无 `--file`） | `bin/agent.sh:2219-2340`；`bin/AGENTS.md:43` |
| co thread_id 提取 | `bin/agent.sh:2627-2655` |
| co app-server 恢复 | `bin/agent.sh:2661-2690` |
| 协议桥启动 | `bin/agent.sh:1096-1106`（cl）、`:2492-2500`（co）、`:2148`（实现） |
| 供应商与桥接配置 | `bin/agent-config.json:30-199` |
| 默认权限/沙箱/上下文窗口 | `bin/agent-config.json:200-240` |
| 两层默认模板 | `bin/agent-custom.json.refer:30-96` |
| 驱动/状态栏/安全变体说明 | `bin/AGENTS.md:43-63` |
| 派发接口 | `bin/agent-dispatch.sh:15-19,129-153` |
| 历史实测（cl session id） | `/root/.claude/projects/-root-configure/memory/cl-drive-session-id-missing.md` |
| 历史实测（go GLM/Anthropic 路由） | `/root/.claude/projects/-root-configure/memory/opencode-go-wire-api-split.md` |
| 历史实测（co deepseek 桥接/GLM 快速失败） | `/root/.claude/projects/-root-configure/memory/opencode-go-deepseek-res-hang.md` |
| 历史实测（co 位置参数陷阱） | `/root/.claude/projects/-root-configure/memory/co-cli-positional-args.md` |

---

## 10. 本次验证命令与结果

```text
$ claude --version
2.1.270 (Claude Code)
$ codex --version
codex-cli 0.154.0
$ opencode --version
1.19.3

$ bin/cl --help   # rc=0，输出 [供应商][模型][强度] + -file/-time
$ bin/op --help   # rc=0，输出 [供应商][模型][强度] + --variant/-file/-time
$ bin/co --help   # rc=0，输出 [供应商][模型][强度] + --reasoning-effort/-time/驱动控制

$ bin/cl gpt
###cl: ERROR: 途径 'custom-gpt' 未定义 anthropic_base_url ...   # rc=64

$ bin/cl go glm-5.3-flash
API Error: 400 Model does not support this protocol.            # rc=1
```

### 10.1 修复后验证（2026-10-21）

```text
$ bash -n bin/agent.sh && bash -n bin/agent.test.sh
SYNTAX_OK

$ bash bin/agent.test.sh
...（77 项 PASS）
RC=0

$ git diff --check
DIFF_CHECK_OK
```

新增断言覆盖：`claude -p --output-format json` 参数、JSON `session_id`/`result` 解析、`session-bound` 事件、`max-turns=1` 下两次调用、非 JSON 输出回退 stderr、`agent-dispatch.sh --agent cl --text` 返回 `result` 文本。

**终态**：报告已更新并写入 `docs/report_co_op_cl_20261021.md`；本次修复改动 `bin/agent.sh`、`bin/agent.test.sh`，未提交 Git，未修改配置。
