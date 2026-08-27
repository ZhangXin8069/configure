# 推荐插件项目

本目录记录经过初步核对的 Codex 插件项目，并提供用户显式执行的
[`install-recommended.sh`](./install-recommended.sh) 安装器。仓库加载或 shell 启动时不会自动安装插件；安装器也不复制第三方源码、不创建个人 marketplace，只调用 Codex 的 marketplace 接口。

选型依据是 2026-08-27 的公开仓库内容：先用 GitHub/GitLab/Gitee/Codeberg 热榜发现候选，再核对实际 manifest、许可证、兼容性、安装入口和与本库技能的职责重叠。star 仅用于发现候选，不代表安全或质量批准。

## 一键安装

先预览将要执行的命令：

```bash
bash install-recommended.sh --dry-run
```

确认后执行默认的 `recommended` profile（`superpowers`、`nvidia`、`zotero`）：

```bash
bash install-recommended.sh
```

也可以按场景安装或逐个指定：

| profile | 插件 | 适用场景 |
|---|---|---|
| `core` | `superpowers` | 通用规划、TDD、调试和交付 |
| `recommended` | `superpowers`、`nvidia`、`zotero` | 默认的开发、GPU 与文献工作组合 |
| `gpu-research` | `nvidia`、`zotero` | GPU/HPC 与文献检索 |
| `bioinformatics` | `life-science-research`、`ngs-analysis` | 生命科学和测序分析 |
| `engineering` | `ecc`、`agent-skills`、`compound-engineering` | 外部工程工作流；重复能力较多 |
| `orchestration` | `babysitter` | 事件溯源、审批和长流程编排 |
| `all` | 安装器登记的全部项目 | 仅在逐项审查后使用 |

```bash
bash install-recommended.sh --profile gpu-research
bash install-recommended.sh ecc agent-skills
bash install-recommended.sh --ref v2.1.0 ecc
```

安装器要求 Codex CLI 支持 `codex plugin marketplace` 与 `codex plugin add`，并要求已有
`jq` 或 `python3` 解析 JSON；不会自动安装这些依赖。它会优先复用已配置的官方
marketplace，必要时注册 `openai/plugins`，安装后用 `codex plugin list --json` 验证插件注册。
不同 CLI/账户可能将官方 marketplace 显示为 `openai-curated` 或 `openai-api-curated`，安装器会从
`codex plugin list --available --json` 读取实际名称，不硬编码当前环境的别名。
带 hooks、MCP 或大量技能的插件不会被自动信任；重启 Codex 后可用 `/plugins` 检查启用状态。

## 推荐项目

### 官方 Codex marketplace：openai/plugins

- 来源：[openai/plugins](https://github.com/openai/plugins)；仓库的
  [marketplace manifest](https://github.com/openai/plugins/blob/main/.agents/plugins/marketplace.json)
  声明官方 Codex 插件目录。
- `superpowers`：MIT，版本 6.3.0；规划、TDD、系统调试、并行协作和代码审查。其上游项目
  [obra/superpowers](https://github.com/obra/superpowers) 提供原生 `.codex-plugin/plugin.json`，
  适合通用工程流程，但与本库 `brainstorm`、`plan`、`debug`、`review`、`test`、`all` 重叠。
- `nvidia`：Apache-2.0 与 CC-BY-4.0，版本 1.0.4；CUDA、GPU 加速、推理、机器人、物理仿真和
  Omniverse，适合 HPC/GPU 工作流。详情见其
  [manifest](https://github.com/openai/plugins/blob/main/plugins/nvidia/.codex-plugin/plugin.json)。
- `zotero`：MIT，版本 0.1.2；连接 Zotero 桌面应用，检索个人文献库、导出 BibTeX 和插入引用。
- `ngs-analysis`：MIT，版本 1.0.3；BCL、FASTQ、DNA/RNA-seq、单细胞和表观组学分析路由与本地
  执行验证，适合需要明确 QC/产物索引的测序流程。
- `life-science-research`：Proprietary，版本 1.0.3；生命科学数据库检索和证据综合。使用前必须
  重新核对账号可用性与许可证，不把它与 MIT 项目混同。

官方项目由 Codex marketplace 管理，安装器不会把这些插件源码 vendoring 到本目录。

### EveryInc/compound-engineering-plugin

- 来源：[GitHub](https://github.com/EveryInc/compound-engineering-plugin)
- 许可证：MIT；仓库提供原生 `.codex-plugin/plugin.json` 和 `.agents/plugins/marketplace.json`，README 标注包含 33 个技能并支持 Codex CLI。
- 适用场景：需要独立的 brainstorm → plan → work → simplify → review → compound 工程闭环时，按需作为外部插件安装。
- 本库处理：推荐但不 vendoring。它与本库的 `brainstorm`、`plan`、`debug`、`review`、`test`、`optim` 和 `all` 存在明显职责重叠，默认同时加载会增加触发歧义和上下文开销。
- 安装入口：`codex plugin marketplace add EveryInc/compound-engineering-plugin`，然后
  `codex plugin add compound-engineering --marketplace compound-engineering-plugin`。
- 使用前：先阅读上游 manifest 与技能内容，按版本或提交固定来源；确认项目目录中的本地技能优先级后再安装。

### wshobson/agents

- 来源：[GitHub](https://github.com/wshobson/agents)
- 许可证：MIT；上游 README 声明包含多个按领域拆分的插件，并提供 Codex CLI 兼容路径；例如 `python-development` 与 `backend-development` 均有独立 `.codex-plugin/plugin.json`。
- 适用场景：Python、后端、基础设施等具体领域需要专门技能时，只选择单个领域插件。
- 本库处理：推荐按需外部安装，不复制整个 marketplace。其规模较大，与本库通用的 `review`、`test`、`debug`、`plan` 等能力有重叠，不能把全量插件作为默认依赖。
- 使用前：只引入当前项目所需领域，检查该领域插件的 manifest、技能路径、外部脚本和更新提交。

### affaan-m/ECC

- 来源：[GitHub](https://github.com/affaan-m/ECC)
- 许可证：MIT；版本 2.2.0，提供原生 `.codex-plugin/plugin.json`、Codex marketplace manifest、技能、MCP 配置和 Codex hooks。
- 适用场景：需要较完整的 TDD、安全审查、代码审查、持续验证和自主开发工作流时按需选择。
- 安装入口：`codex plugin marketplace add affaan-m/ECC`，然后
  `codex plugin add ecc --marketplace ecc`。
- 风险与重叠：内容规模大，且包含 hooks/MCP；与本库 `all`、`debug`、`review`、`test`、`up` 等能力
  有重叠。不要与旧版手工 sync 流程叠加，安装后另行审查并信任 hooks。

### addyosmani/agent-skills

- 来源：[GitHub](https://github.com/addyosmani/agent-skills)
- 许可证：MIT；版本 0.6.7，提供原生 `.codex-plugin/plugin.json` 和 24 个生命周期工程技能，覆盖
  spec、plan、build、test、review、ship。
- 适用场景：希望使用较小、可组合的工程生命周期技能，而不是引入完整运行时或 hooks 时按需选择。
- 安装入口：`codex plugin marketplace add addyosmani/agent-skills`，然后
  `codex plugin add agent-skills --marketplace agent-skills`。
- 风险与重叠：与本库 `plan`、`tdd`、`test`、`review`、`all` 有明显重叠；建议二选一并先检查触发优先级。

### a5c-ai/babysitter-codex

- 来源：[GitHub](https://github.com/a5c-ai/babysitter-codex)
- 许可证：MIT；版本 6.0.3，提供原生 `.codex-plugin/plugin.json`、`skills/`、`hooks.json` 和
  Codex marketplace manifest；上游将 Codex 支持标为 Beta。
- 适用场景：需要事件溯源状态、可恢复的长流程、质量闸门和人工审批断点时使用。
- 安装入口：`codex plugin marketplace add a5c-ai/babysitter-codex`，然后
  `codex plugin add babysitter --marketplace babysitter`。
- 前置条件：完整运行还需要按上游说明安装 `@a5c-ai/babysitter` CLI/SDK；本库安装器不会隐式执行
  npm 安装，也不会替用户信任 hooks。

### 相邻工具与技能集合（不是本脚本的原生插件目标）

- [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills)：MIT 的
  科学研究技能集合，覆盖数据库、化学、生物和科研分析；当前仓库以根目录 `plugin.json`/Agent
  Skills 方式发布，适合通过其 `npx skills add` 或官方说明安装，不纳入本脚本的 Codex marketplace
  目录。
- [nexu-io/open-design](https://github.com/nexu-io/open-design)：Apache-2.0 的本地设计和 artifact
  工作流，Codex 入口是 MCP（`od mcp install codex`），不是本目录定义的 Codex plugin marketplace
  安装对象。

## 调研来源

- GitHub 热榜：[agent tools plugins 搜索](https://github.com/search?q=agent+tools+plugins&type=repositories&s=stars&o=desc)；用于发现高关注候选，再逐项核对仓库内容。
- GitLab 热榜：[Projects API 查询](https://gitlab.com/api/v4/projects?search=agent%20tools%20plugins&order_by=star_count&sort=desc&per_page=10)；本轮仅返回两个 0 star 项目，没有发现适合本库的插件。
- Gitee：[Gitee 搜索](https://so.gitee.com/?q=agent%20tools%20plugins)；本轮未得到可用的直接候选。
- Codeberg：[Forgejo repository search API](https://codeberg.org/api/v1/repos/search?q=agent%20tools%20plugins&sort=stars&order=desc&limit=10)；本轮返回空结果。
- 本轮重点核对的原生入口：[openai/plugins marketplace](https://github.com/openai/plugins/tree/main/.agents/plugins)、
  [ECC Codex manifest](https://github.com/affaan-m/ECC/tree/main/.codex-plugin)、
  [Agent Skills Codex manifest](https://github.com/addyosmani/agent-skills/tree/main/.codex-plugin)、
  [Babysitter Codex manifest](https://github.com/a5c-ai/babysitter-codex/tree/main/.codex-plugin)。
- 规范与实践：[Agent Skills specification](https://agentskills.io/specification)、[Anthropic skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator)、[obra/superpowers writing-skills](https://github.com/obra/superpowers/tree/main/skills/writing-skills)。它们用于核对分级披露、触发描述和验证边界，不直接复制到本目录。

## 暂不纳入

- [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc)：它是“在 Claude Code 中调用 Codex”的 Claude Code 插件，依赖 Node.js 和 Claude Code；不是本仓库所需的 Codex 原生插件。
- [anthropics/skills](https://github.com/anthropics/skills)：适合作为技能写作参考来源，但不是本目录要直接加载的插件项目；本库已有自己的技能规范和登记表。
- [wshobson/agents](https://github.com/wshobson/agents) 的全量安装：它仍是推荐项目，但上游 Codex 路径使用
  `npx codex-marketplace add wshobson/agents` 后再选择单个插件；为避免引入额外 npm 工具和 93 个插件，
  不纳入本脚本的一键全量 profile。请只按领域手工选择。

## 安装边界

本目录的推荐项目不会因写入此文件或 source shell 而自动安装。`install-recommended.sh` 只有在用户显式执行时才会写入当前 `CODEX_HOME` 的 marketplace/plugin 状态；它不删除插件、不执行 legacy sync、不安装 npm 依赖、不自动信任 hooks。确需使用时，仍应确认版本、许可证、权限、外部命令、网络访问、新增上下文以及与本库技能的职责重叠。
