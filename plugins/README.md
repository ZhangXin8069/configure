# 推荐插件项目

本目录记录经过初步核对的 Codex 插件项目，并提供用户显式执行的
[`install-recommended.sh`](./install-recommended.sh) 安装器。仓库加载或 shell 启动时不会自动安装插件；安装器也不复制第三方源码、不创建个人 marketplace，只调用 Codex 的 marketplace 接口。

选型依据是 2026-09-08 的公开仓库与官方插件页面：先用 GitHub/GitLab/Gitee/Codeberg 热榜发现候选，再核对实际 manifest、许可证、兼容性、安装入口和与本库技能的职责重叠。star 仅用于发现候选，不代表安全或质量批准。

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
| `research-workbench` | `nvidia`、`zotero`、`hugging-face`、`notion`、`google-drive`、`build-web-data-visualization` | 物理/ML 研究、文献、模型和报告 |
| `workspace` | `notion`、`google-drive`、`airtable` | 日常协作、知识库、文件和台账 |
| `app-dev` | `figma`、`build-web-apps`、`build-ios-apps`、`build-macos-apps`、`expo`、`netlify` | 前端、移动端、设计联动和发布 |
| `gpu-research` | `nvidia`、`zotero` | GPU/HPC 与文献检索 |
| `bioinformatics` | `life-science-research`、`ngs-analysis` | 生命科学和测序分析 |
| `engineering` | `ecc`、`agent-skills`、`compound-engineering` | 外部工程工作流；重复能力较多 |
| `orchestration` | `babysitter`、`omx` | OMX worker 编排与 babysitter 审批/长流程 |
| `all` | 安装器登记的全部项目 | 仅在逐项审查后使用 |

```bash
bash install-recommended.sh --profile gpu-research
bash install-recommended.sh --profile research-workbench
bash install-recommended.sh --profile workspace
bash install-recommended.sh --profile app-dev
bash install-recommended.sh --ref 90606c8315ee09cafc303515c5f33024db6b9882 ecc
bash install-recommended.sh --ref-policy commit --ref 90606c8315ee09cafc303515c5f33024db6b9882 ecc
bash install-recommended.sh --audit-manifest refer/git-rep/ecc-skills/.codex-plugin/plugin.json
```

`--audit-manifest` 使用 strict 静态审计；ECC/OMX 当前因 hook timeout、Node eval 或 MCP runtime
会按设计返回非零并列出发现，不会执行 marketplace 写入。

安装前可只读检查当前 Codex 状态，不会调用安装命令：

```bash
bash install-recommended.sh --status --profile recommended
bash install-recommended.sh --audit superpowers nvidia
```

状态会区分“已安装”“可用但未安装”“marketplace 已配置但未列出”“marketplace 未配置”和“状态未知”；
查询失败时保持 fail-closed，Codex JSON 解析或 schema 异常返回状态 2 且不执行写入。社区 ref 默认直接
接受完整 40/64 位十六进制 commit，其他值必须能通过
`git ls-remote --exit-code --tags <repo-url> refs/tags/<ref>` 验证；`main`、`master`、`HEAD` 等
浮动分支会被拒绝。dry-run 同样执行该验证，缺少 `git`、tag 不存在或网络失败都会停止。需要只接受提交
哈希时使用 `--ref-policy commit --ref <40-or-64-hex-sha>`。
多社区插件 profile 默认使用每项内建的完整 commit；显式 `--ref` 只能覆盖单个社区目标，避免把一个
仓库的 tag/commit 错配到另一个仓库。

`recommended` 仍然是最小平衡包；`research-workbench` 偏物理/ML 和报告，`workspace` 偏日常协作，`app-dev` 偏工程交付和端侧应用。需要更细的组合时，直接按插件名指定更透明。

安装器要求 Codex CLI 支持 `codex plugin marketplace` 与 `codex plugin add`，并要求已有
`jq` 或 `python3` 解析 JSON；使用 tag 时还需要 `git` 与网络访问，脚本不会自动安装这些依赖。
它会优先复用已配置的官方 marketplace，必要时注册 `openai/plugins`。安装后用
`codex plugin list --json` 同时验证插件名和目标 `marketplaceName`，任一不匹配都不算成功。
不同 CLI/账户可能将官方 marketplace 显示为 `openai-curated` 或 `openai-api-curated`，安装器会从
`codex plugin list --available --json` 读取实际名称，但只接受这两个精确受信别名；其他
`openai-*` 或相似名称均不视为官方来源。
社区插件默认使用每项内建完整 commit；`--ref <tag-or-commit>` 或 `CODEX_PLUGIN_REF` 只用于覆盖
单个社区目标，不默认跟踪浮动分支。Codex JSON 不提供已配置社区 marketplace 的 source/ref，
因此无法证明现有登记与本次目标 ref 一致；安装器会 fail-closed，要求用户先移除该 marketplace，
再用目标 ref 重新登记，不会直接复用。官方 marketplace 的 ref 可选，dry-run 即使本机没有
`codex` 也会打印完整的 `codex plugin marketplace add openai/plugins` 注册命令。
带 hooks、MCP 或大量技能的插件不会被自动信任；重启 Codex 后可用 `/plugins` 检查启用状态。

### 新增官方候选

- 研究/知识：`hugging-face` 适合模型和数据集工作，`build-web-data-visualization` 适合报告、PDF、图表和幻灯片自动化，`notion` 和 `google-drive` 适合笔记、文档和检索。
- 工程/产品：`figma` 适合设计联动，`build-web-apps` 适合前端与全栈 Web，`build-ios-apps` / `build-macos-apps` / `expo` 适合端侧应用，`netlify` 适合发布和托管。
- 日常协作：`airtable` 适合结构化台账、看板和流程跟踪，和 `workspace` profile 配套。

## 推荐项目

### 官方 Codex marketplace：openai/plugins

- 来源：[openai/plugins](https://github.com/openai/plugins)；仓库的
  [marketplace manifest](https://github.com/openai/plugins/blob/main/.agents/plugins/marketplace.json)
  声明官方 Codex 插件目录。
- `superpowers`：MIT；官方 marketplace 当前提供版本 6.3.0。上游
  [obra/superpowers@bb92a77](https://github.com/obra/superpowers/tree/bb92a77741419a4ab5f06e711a283343f1ada0c3)
  的原生 `.codex-plugin/plugin.json` 已到 7.0.0（SHA256
  `58c36fd4185719c9bee12fab1a03ce6cce48051c36ee9bdd9492235dd7ab2cfd`），且 `hooks` 为空；
  适合通用工程流程，但与本库 `brainstorm`、`plan`、`debug`、`review`、`test`、`all` 重叠。
- `nvidia`：Apache-2.0 与 CC-BY-4.0，版本 1.0.4；CUDA、GPU 加速、推理、机器人、物理仿真和
  Omniverse，适合 HPC/GPU 工作流；上游技能仓库为 [NVIDIA/skills](https://github.com/NVIDIA/skills)。详情见其
  [manifest](https://github.com/openai/plugins/blob/main/plugins/nvidia/.codex-plugin/plugin.json)。
- `zotero`：MIT，版本 0.1.2；连接 Zotero 桌面应用，检索个人文献库、导出 BibTeX 和插入引用。
- `notion`：官方条目，适合会议记录、知识库和项目笔记。
- `google-drive`：官方条目，适合文档、表格、幻灯片和文件检索。
- `airtable`：官方条目，适合结构化看板、表格和流程跟踪。
- `hugging-face`：官方条目，适合模型、数据集和 Spaces。
- `build-web-data-visualization`：官方条目，适合报告、PDF、图表和幻灯片自动化。
- `figma`：官方条目，适合设计资源和代码联动。
- `build-web-apps`：官方条目，适合前端与全栈 Web 构建。
- `build-ios-apps`：官方条目，适合 iOS / SwiftUI 构建。
- `build-macos-apps`：官方条目，适合 macOS / SwiftUI 构建。
- `expo`：官方条目，适合 React Native / Expo 工作流。
- `netlify`：官方条目，适合 Web 部署和发布。
- `ngs-analysis`：MIT，版本 1.0.3；BCL、FASTQ、DNA/RNA-seq、单细胞和表观组学分析路由与本地
  执行验证，适合需要明确 QC/产物索引的测序流程。
- `life-science-research`：Proprietary，版本 1.0.3；生命科学数据库检索和证据综合。使用前必须
  重新核对账号可用性与许可证，不把它与 MIT 项目混同。

官方项目由 Codex marketplace 管理，安装器不会把这些插件源码 vendoring 到本目录。

### EveryInc/compound-engineering-plugin

- 来源：[GitHub](https://github.com/EveryInc/compound-engineering-plugin)
- 许可证元数据：`.codex-plugin/plugin.json`、`package.json` 与 README 均声明 MIT，但仓库未发现
  `LICENSE`/`COPYING` 正文，使用前需再次复核；固定
  [commit `fac349c`](https://github.com/EveryInc/compound-engineering-plugin/tree/fac349c0c31a543d497fd4825af9b44bdb7e7dfe)
  的版本为 3.30.5，提供原生 `.codex-plugin/plugin.json`；manifest SHA256 为
  `77a986beb5395e1fd96f4065dd5d3b7d73bf6374d88454d25af08527d09ecf60`。
- 适用场景：需要独立的 brainstorm → plan → work → simplify → review → compound 工程闭环时，按需作为外部插件安装。
- 本库处理：推荐但不 vendoring。它与本库的 `brainstorm`、`plan`、`debug`、`review`、`test`、`optim` 和 `all` 存在明显职责重叠，默认同时加载会增加触发歧义和上下文开销。
- 安装入口：`codex plugin marketplace add EveryInc/compound-engineering-plugin --ref <tag-or-commit>`，然后
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
- 许可证：MIT；固定
  [commit `90606c`](https://github.com/affaan-m/ECC/tree/90606c8315ee09cafc303515c5f33024db6b9882)
  的版本为 2.2.3，提供原生 `.codex-plugin/plugin.json`、Codex marketplace manifest、技能、MCP 配置和
  Codex hooks；manifest SHA256 为
  `09d1f838f55e4463aa9da6673f812edc33952572e3425eb77dee9ec31280d424`。
- 适用场景：需要较完整的 TDD、安全审查、代码审查、持续验证和自主开发工作流时按需选择。
- 安装入口：`codex plugin marketplace add affaan-m/ECC --ref <tag-or-commit>`，然后
  `codex plugin add ecc --marketplace ecc`。
- 风险与重叠：内容规模大（固定 ref 下登记约 281 个 Codex 技能），且显式加载 hooks 与
  Chrome DevTools MCP；与本库 `all`、`debug`、`review`、`test`、`up` 等能力有重叠。不要与旧版手工
  sync 流程叠加，安装后另行审查并信任 hooks/MCP。

### Yeachan-Heo/oh-my-codex

- 来源：[GitHub](https://github.com/Yeachan-Heo/oh-my-codex)
- 许可证：MIT；固定
  [commit `304fb3b`](https://github.com/Yeachan-Heo/oh-my-codex/tree/304fb3b4825c4132c273732b14d2d5e86b54f8e3)
  的版本为 0.21.4，提供原生 `.codex-plugin/plugin.json`、本地 marketplace manifest、skills、hooks、
  MCP 和 apps；manifest SHA256 为
  `e494fa956511b3cba28614b4261ff10ceaaa7adf3ad3ea37a3fc9754aeff4873`。
- 适用场景：需要 OMX 的多 agent、worker mailbox、HUD、持久 goal 和事件状态编排时按需安装。
- 安装入口：`codex plugin marketplace add Yeachan-Heo/oh-my-codex --ref 304fb3b4825c4132c273732b14d2d5e86b54f8e3`，
  然后 `codex plugin add oh-my-codex --marketplace oh-my-codex-local`。
- 风险与重叠：hooks 覆盖 SessionStart、PreToolUse、PostToolUse、UserPromptSubmit、Compact 和 Stop；
  多个 command hook 未声明 timeout，MCP 中包含 OMX 运行时命令；与本库 `team`、`all`、`auto`、`plan`
  和 `go-on` 有明显重叠。默认不安装，安装器也不会隐式安装或启用 omx runtime；安装后必须审查
  hooks/MCP 并确认触发优先级。

### addyosmani/agent-skills

- 来源：[GitHub](https://github.com/addyosmani/agent-skills)
- 许可证：MIT；固定
  [commit `aeac41d`](https://github.com/addyosmani/agent-skills/tree/aeac41d4d005999432bb7312f7ff06383a91d59d)
  的版本为 0.6.13，提供原生 `.codex-plugin/plugin.json` 和 25 个生命周期工程技能，覆盖
  spec、plan、build、test、review、ship；manifest SHA256 为
  `7476c2cb57371bbf5900a37bc9f6cf53e62ccb110a2e948349889615d49e9773`。
- 适用场景：希望使用较小、可组合的工程生命周期技能，而不是引入完整运行时或 hooks 时按需选择。
- 安装入口：`codex plugin marketplace add addyosmani/agent-skills --ref <tag-or-commit>`，然后
  `codex plugin add agent-skills --marketplace agent-skills`。
- 风险与重叠：与本库 `plan`、`tdd`、`test`、`review`、`all` 有明显重叠；建议二选一并先检查触发优先级。

### a5c-ai/babysitter-codex

- 来源：[GitHub](https://github.com/a5c-ai/babysitter-codex)
- 许可证：MIT；固定
  [commit `6940285`](https://github.com/a5c-ai/babysitter-codex/tree/694028503ae14a1111d4e32eaa5279752bc2194c)
  的版本为 6.0.3，提供原生 `.codex-plugin/plugin.json`、`skills/`、`hooks.json` 和
  Codex marketplace manifest；manifest SHA256 为
  `8b6dd6a8a41469e4c9d2b64906f6899531fc684303fe9fc235dccb5f2ceff017`；上游将 Codex 支持标为 Beta。
- 适用场景：需要事件溯源状态、可恢复的长流程、质量闸门和人工审批断点时使用。
- 安装入口：`codex plugin marketplace add a5c-ai/babysitter-codex --ref <tag-or-commit>`，然后
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

本轮统一查询词为 `agent skills`，各平台保留自己的原生 star 字段，不能跨平台直接比较：

| 来源 | 结构化请求与状态 | 本轮结果 | 处理 |
|---|---|---|---|
| GitHub | [Repositories API](https://api.github.com/search/repositories?q=agent%20skills&sort=stars&order=desc&per_page=10)，HTTP 200 | 前 10 项中核对了 `obra/superpowers`、`mattpocock/skills`、`affaan-m/ECC`、`anthropics/skills`、`addyosmani/agent-skills` 等；其余为通用项目或工具 | 只吸收已核对的 manifest/实践；`mattpocock/skills` 因无原生 Codex manifest 且职责重叠暂不纳入 |
| GitLab | [Projects API](https://gitlab.com/api/v4/projects?search=agent%20skills&order_by=star_count&sort=desc&per_page=10)，HTTP 200 | 前 10 项为 5、3、3、2、2、2、1、1、1、1 star；发现 `ska-telescope/ska-ai-skills` 等有 Codex 目录的候选 | 许可证、兼容性和实际能力不足以超过现有推荐，暂不纳入一键 profile |
| Gitee | [API](https://gitee.com/api/v5/search/repositories?q=agent%20skills&sort=stars_count&order=desc&page=1&per_page=10)，HTTP 200、结构化结果 0；[搜索页](https://so.gitee.com/?q=agent%20skills)，HTTP 200 | 未取得可用的结构化排名 | 如实保留空结果，不虚构候选 |
| Codeberg | [Forgejo API](https://codeberg.org/api/v1/repos/search?q=agent%20skills&sort=stars&order=desc&limit=10)，HTTP 200、结构化结果 0；[Explore](https://codeberg.org/explore/repos?sort=stars&order=desc)，HTTP 200 | 未取得可用的结构化排名 | 如实保留空结果，不虚构候选 |

GitHub API 首次请求曾收到 HTTP 504，重试第 1 次（30 秒超时）即恢复为 HTTP 200；前述四个平台的结果均为本轮只读获取。网页回退页面可访问但未取得结构化排名，未用于伪造排序。

### 2026-10-16 复核

同一查询词 `agent skills` 的复核结果如下；各平台 star 字段仍不可直接跨源比较：

- GitHub API HTTP 200：前列仍为 `obra/superpowers`、`mattpocock/skills`、`affaan-m/ECC`、
  `anthropics/skills`、`addyosmani/agent-skills`；`obra/superpowers`、`affaan-m/ECC` 和
  `addyosmani/agent-skills` 均为 MIT 且 `.codex-plugin/plugin.json` HTTP 200，
  `anthropics/skills` 保持参考定位，`mattpocock/skills` 的 manifest 为 HTTP 404，继续暂不纳入。
- GitLab Projects API HTTP 200：前 10 名最高仅 6 star，主要是 GitLab 内部效能与低 star
  技能库；未发现超过现有推荐证据门槛的新插件。
- Gitee API HTTP 200 但结构化结果为 0；网页入口 HTTP 200 仅为前端壳，未取得可复现排序。
- Codeberg API 使用 `sort=stars&order=desc&includeDesc=true` 后 HTTP 200，取得 10 条结构化
  结果；前列为 3 star 的 `leeg/chiron-codex-agent-skills` 及 1 star 的
  `hanlho/skills-primer`、`ky64/agent-skills`，未见许可证或兼容性证据足以纳入。

本轮完整核对 GitHub、GitLab、Codeberg 各前 10 项（Gitee 为结构化空结果），没有新增默认采纳项；
现有推荐和“暂不纳入”决策保持不变。三个已推荐插件项的核验证据更新为 `superpowers@bb92a77`、
`ECC@90606c`、`agent-skills@aeac41d`，其中前两项的官方/上游版本差异和 hooks/MCP 风险已在上文标注。

- 本轮重点核对的原生入口：[openai/plugins marketplace](https://github.com/openai/plugins/tree/main/.agents/plugins)、
  [ECC Codex manifest](https://github.com/affaan-m/ECC/tree/main/.codex-plugin)、
  [Agent Skills Codex manifest](https://github.com/addyosmani/agent-skills/tree/main/.codex-plugin)、
  [Compound Engineering Codex manifest](https://github.com/EveryInc/compound-engineering-plugin/tree/main/.codex-plugin)、
  [Babysitter Codex manifest](https://github.com/a5c-ai/babysitter-codex/tree/main/.codex-plugin)。
- 规范与实践：[Agent Skills specification](https://agentskills.io/specification)、[Anthropic skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator)、[obra/superpowers writing-skills](https://github.com/obra/superpowers/tree/main/skills/writing-skills)。它们用于核对分级披露、触发描述和验证边界，不直接复制到本目录。

## 暂不纳入

- [mattpocock/skills](https://github.com/mattpocock/skills)：GitHub 本轮 `agent skills` 热榜前列、MIT；实际仓库含 Agent Skills 集合但未发现原生 `.codex-plugin/plugin.json`，且与本库 `plan`、`test`、`review` 等职责重叠，因此不登记为 Codex marketplace 插件。
- [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc)：它是“在 Claude Code 中调用 Codex”的 Claude Code 插件，依赖 Node.js 和 Claude Code；不是本仓库所需的 Codex 原生插件。
- [anthropics/skills](https://github.com/anthropics/skills)：适合作为技能写作参考来源，但不是本目录要直接加载的插件项目；本库已有自己的技能规范和登记表。
- [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman)：Apache-2.0、原生 Codex manifest，但完整插件含会发送文件、
  覆盖原文件并创建外部备份的 compressor；上游自身标注高风险。拒绝作为默认插件，最多按固定 ref 单独审阅无副作用的
  风格技能，不启用 root hook/MCP。
- [Shubhamsaboo/awesome-llm-apps](https://github.com/Shubhamsaboo/awesome-llm-apps)：整个仓库包含多种网络、凭据和写盘型技能；
  仅将 `commit-archaeologist`、`scope-creep-detector`、`dependency-doctor` 三个离线优先的只读技能按固定 SHA 登记到
  `tools/README.md`，不整体安装。
- [farion1231/cc-switch](https://github.com/farion1231/cc-switch)：适配多 harness 的桌面配置管理器，与本库 provider/配置文件管理链重叠，
  且可运行非 loopback 代理；不登记为插件，仅建议需要 GUI 的用户自行备份配置后评估。
- [langgenius/dify](https://github.com/langgenius/dify)：技能与 Dify monorepo/远程 API 强绑定，许可证含附加限制，
  且 `difyctl` 包含无二次确认的删除/撤销路径；不纳入本库。
- [wshobson/agents](https://github.com/wshobson/agents) 的全量安装：它仍是推荐项目，但上游 Codex 路径使用
  `npx codex-marketplace add wshobson/agents` 后再选择单个插件；为避免引入额外 npm 工具和 93 个插件，
  不纳入本脚本的一键全量 profile。请只按领域手工选择。

## 安装边界

本目录的推荐项目不会因写入此文件或 source shell 而自动安装。`install-recommended.sh` 只有在用户显式执行时才会写入当前 `CODEX_HOME` 的 marketplace/plugin 状态；它不删除插件、不执行 legacy sync、不安装 npm 依赖、不自动信任 hooks。确需使用时，仍应确认版本、许可证、权限、外部命令、网络访问、新增上下文以及与本库技能的职责重叠。
