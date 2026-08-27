# 推荐插件项目

本目录记录经过初步核对的 Codex 插件项目。这里只保存推荐信息，不复制第三方源码、不自动安装插件，也不创建个人 marketplace；这样不会把外部项目未经审查地加入本仓库的加载路径。

选型依据是 2026-08-27 的公开仓库内容：先用 GitHub/GitLab/Gitee/Codeberg 热榜发现候选，再核对实际 manifest、许可证、兼容性和与本库技能的职责重叠。star 仅用于发现候选，不代表安全或质量批准。

## 推荐项目

### EveryInc/compound-engineering-plugin

- 来源：[GitHub](https://github.com/EveryInc/compound-engineering-plugin)
- 许可证：MIT；仓库提供原生 `.codex-plugin/plugin.json`，README 标注包含 33 个技能并支持 Codex CLI。
- 适用场景：需要独立的 brainstorm → plan → work → simplify → review → compound 工程闭环时，按需作为外部插件安装。
- 本库处理：推荐但不 vendoring。它与本库的 `brainstorm`、`plan`、`debug`、`review`、`test`、`optim` 和 `all` 存在明显职责重叠，默认同时加载会增加触发歧义和上下文开销。
- 使用前：先阅读上游 manifest 与技能内容，按版本或提交固定来源；确认项目目录中的本地技能优先级后再安装。

### wshobson/agents

- 来源：[GitHub](https://github.com/wshobson/agents)
- 许可证：MIT；上游 README 声明包含多个按领域拆分的插件，并提供 Codex CLI 兼容路径；例如 `python-development` 与 `backend-development` 均有独立 `.codex-plugin/plugin.json`。
- 适用场景：Python、后端、基础设施等具体领域需要专门技能时，只选择单个领域插件。
- 本库处理：推荐按需外部安装，不复制整个 marketplace。其规模较大，与本库通用的 `review`、`test`、`debug`、`plan` 等能力有重叠，不能把全量插件作为默认依赖。
- 使用前：只引入当前项目所需领域，检查该领域插件的 manifest、技能路径、外部脚本和更新提交。

## 调研来源

- GitHub 热榜：[agent tools plugins 搜索](https://github.com/search?q=agent+tools+plugins&type=repositories&s=stars&o=desc)；用于发现高关注候选，再逐项核对仓库内容。
- GitLab 热榜：[Projects API 查询](https://gitlab.com/api/v4/projects?search=agent%20tools%20plugins&order_by=star_count&sort=desc&per_page=10)；本轮仅返回两个 0 star 项目，没有发现适合本库的插件。
- Gitee：[Gitee 搜索](https://so.gitee.com/?q=agent%20tools%20plugins)；本轮未得到可用的直接候选。
- Codeberg：[Forgejo repository search API](https://codeberg.org/api/v1/repos/search?q=agent%20tools%20plugins&sort=stars&order=desc&limit=10)；本轮返回空结果。
- 规范与实践：[Agent Skills specification](https://agentskills.io/specification)、[Anthropic skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator)、[obra/superpowers writing-skills](https://github.com/obra/superpowers/tree/main/skills/writing-skills)。它们用于核对分级披露、触发描述和验证边界，不直接复制到本目录。

## 暂不纳入

- [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc)：它是“在 Claude Code 中调用 Codex”的 Claude Code 插件，依赖 Node.js 和 Claude Code；不是本仓库所需的 Codex 原生插件。
- [anthropics/skills](https://github.com/anthropics/skills)：适合作为技能写作参考来源，但不是本目录要直接加载的插件项目；本库已有自己的技能规范和登记表。

## 安装边界

本目录的推荐项目不会因写入此文件而自动安装。确需使用时，在用户确认版本、权限和职责不重叠后，按上游文档执行安装；插件涉及的写入、外部命令、网络访问和新增上下文都应单独审查。
