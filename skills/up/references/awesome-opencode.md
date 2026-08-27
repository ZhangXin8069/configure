# references/awesome-opencode.md — opencode 生态精选参考

来源：**awesome-opencode/awesome-opencode**（CC0-1.0）
URL：<https://github.com/awesome-opencode/awesome-opencode>
抓取日期：2026-08-27（GitHub API stars ≈ 9.9k，最近更新 2026-08-27）

用途：up 技能做 opencode 生态差距分析、插件/主题/agent 候选发现时的**精选索引**；
候选仍须逐一核对仓库 README、manifest、许可证与近期兼容性后才登记（不因 star 高而直接采纳）。

## 官方仓库

| 项目 | 用途 | URL |
|---|---|---|
| opencode | 官方 AI 编码代理本体 | https://github.com/anomalyco/opencode |
| opencode-sdk-js / -go / -python | 官方 SDK（JS/Go/Python） | https://github.com/anomalyco/opencode-sdk-js 等 |

## 配置/安装相关（与一键配置脚本最相关）

| 项目 | 一句话 | URL |
|---|---|---|
| kickstart.opencode | 深度注释的入门配置，每个决策有解释（免费模型+MCP、plan/execute 工作流） | https://github.com/orionpax1997/kickstart.opencode |
| Opencode Config Starter | 配置起点：agents、commands、rules、skills、预配置 MCP | https://github.com/jjmartres/opencode |
| Opencode Models Discovery | 可配置模型发现与过滤，免冗长手工配置 | https://github.com/yuhp/opencode-models-discovery |
| OpenCode Provider Alias | 用 models.dev 元数据别名化/整理 providers | https://github.com/baranwang/opencode-provider-alias |
| Opencode Synced | 跨机器同步配置 | https://github.com/iHildy/opencode-synced |
| Claude Code Switch Sync | 读 CCS 配置自动同步 providers | https://github.com/JasonLandbridge/opencode-ccs-sync |
| Oh My Opencode | 仿 oh-my-zsh 的成套 agents+工具配置 | https://github.com/code-yeongyu/oh-my-opencode |
| hiai-opencode | 12-agent 规范配置（bundled skills/MCP/LSP） | https://github.com/HiAi-gg/hiai-opencode |
| Opencode Profile Router | 按路径选 profile，隔离登录/配置/数据根 | https://github.com/leolaurindo/opencode-profile-router |
| OCX | opencode 扩展的包管理器 | https://github.com/kdcokenny/ocx |
| Opencode Actions | 可复用 GitHub Actions：CI/CD 中安装运行 opencode | https://github.com/Svtter/opencode-actions |
| Plugin Template | 插件 CI/CD 搭建模板 | https://github.com/zenobi-us/opencode-plugin-template |

## 插件（精选，非全量 135）

| 项目 | 一句话 | URL |
|---|---|---|
| opencode-arise | 轻量编排层，并行后台任务 | https://github.com/bluelovers/opencode-arise |
| opencode-autotitle | AI 自动会话命名（零配置，自动选最便宜模型） | https://github.com/pawelma/opencode-autotitle |
| opencode-background | 后台进程管理 | https://github.com/zenobi-us/opencode-background |
| Dynamic Context Pruning | 剪裁过期工具输出、优化 token | https://github.com/Tarquinen/opencode-dynamic-context-pruning |
| Magic Context | 后台压缩的无损上下文管理 | https://github.com/cortexkit/opencode-magic-context |
| Envsitter Guard | 防止 .env 文件泄漏（只读指纹，不读值） | https://github.com/boxpositron/envsitter-guard |
| Command Inject | 启动时注入 Makefile targets/npm scripts/本地技能 | https://github.com/shihyuho/opencode-command-inject |
| Context Analysis | 会话 token 用量分析 | https://github.com/IgorWarzocha/Opencode-Context-Analysis-Plugin |
| Direnv | 会话开始时加载 direnv 环境变量 | https://github.com/simonwjackson/opencode-direnv |
| Handoff | 生成续接新会话的交接提示 | https://github.com/joshuadavidthomas/opencode-handoff |
| Manage Skills | 向导式技能管理（modal，避免 ANSI 提示） | https://github.com/Randroids-Dojo/ManageSkills |
| Update Notifier | 插件更新通知 | https://github.com/tim-hilde/opencode-update-notifier |

## 主题（全部 7 个）

| 主题 | 一句话 | URL |
|---|---|---|
| Ayu Dark | Ayu 配色移植 | https://github.com/postrednik/opencode-ayu-theme |
| Charcoal | 纯灰度深黑（56 键全灰阶） | https://github.com/VyomJain6904/charcoal-theme |
| Lavi | 柔和暗紫，15+ 应用同族，含 Nix | https://github.com/b0o/lavi/tree/main/contrib/opencode |
| Moonlight | 冷色调暗色 | https://github.com/brunogabriel/opencode-moonlight-theme |
| OpenCode Light Themes | 21 个浅色主题合集，**含一键安装脚本** | https://github.com/fatihtoprakk/opencode-light-themes |
| Poimandres | Poimandres 移植 | https://github.com/ajaxdude/opencode-ai-poimandres-theme |
| VS Code Themes | 内置 VS Code 主题全移植，**一行安装脚本** | https://github.com/regen45t/opencode-vscode-themes |

## AGENTS 社区配置（9 个全列）

| 项目 | 一句话 | URL |
|---|---|---|
| Agentic | 模块化 agents+命令，结构化软件开发 | https://github.com/Cluster444/agentic |
| Claude Subagents | Claude Code subagents 综合参考库（可移植） | https://github.com/VoltAgent/awesome-claude-code-subagents |
| deliberation | 7 专家子代理（架构/计划/范围/代码/安全/研究/调试）+ask-all | https://github.com/antonbabenko/deliberation |
| Gem Team | 自学习多代理编排，spec 驱动 | https://github.com/mubaidr/gem-team |
| NERV | SDD 流水线、A2A 委派、语义记忆、9 子代理 | https://github.com/juanmanueldaza/nerv |
| Opencode Agents | 配置/提示词/代理/插件集合 | https://github.com/darrenhinde/opencode-agents |
| Python Expert Agent | Python 专家主代理+子代理+按需技能 | https://github.com/amrahman90/python-expert-agent |
| Redstone | Minecraft 插件开发代理 | https://github.com/BackGwa/Redstone |
| server-manager | 非阻塞后台服务器管理（JSON 状态、健康检查） | https://github.com/workdocyeye/server-manager |

## 资源（文档/教程）

| 项目 | 一句话 | URL |
|---|---|---|
| Coding Agent Orchestration | 把 AI 编码工具当可组合多代理系统的实用手册 | https://github.com/evermeer/CodingAgentOrchestration |
| Debug Log to Text File | opencode 调试日志输出到文本文件的排障指南 | https://github.com/awesome-opencode/awesome-opencode/discussions/19 |
| Akephalos | 本地优先可移植 agent 偏好/规则/记忆 | https://github.com/sunnja69/akephalos |
| agent-dotfiles | 一次编写规则同步到 Command Code/Claude/Cursor/Copilot/Codex/OpenCode | https://github.com/saqibameen/agent-dotfiles |

## 与 up 流程的对接点

1. **插件推荐与安装器（Step 5.3）**：opencode 插件入口为
   `opencode plugin <npm模块>`（`lib/_opencode/config.sh --plugin` 已包装写入
   `plugin` 数组）；opencode 无 marketplace 命令，与 Codex 的 marketplace 模型不同，
   安装器设计不能照搬 plugins/install-recommended.sh。
2. **主题登记**：opencode 主题写入 `tui.json` 的 `theme` 键（TUI 设置已从
   opencode.json 迁出）；外部主题插件按仓库说明安装。
3. **差距分析对照**：本库 opencode 一键配置能力（config.sh）对照上表
   「配置/安装相关」条目逐项核验，避免重复实现已验证功能。
4. **未采纳示例**：`Dodo Payments`、`CrewBee`、`FlowDeck` 等大而全的工作流套装
   与本库 skills（make/all/dispatch）职责重叠，需用户明确要求才引入；
   只按 star 高采纳属于不充分证据。