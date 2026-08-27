# AGENTS.md — review 技能

本目录为实现 `review` 技能的 `SKILL.md`（代码审查：早审查常审查、子代理审查+
精确上下文裁剪、问题分级 Critical/Important/Minor 与处理决策，吸收 superpowers
requesting-code-review 方法论）。SKILL.md 为唯一权威内容，勿复制改动。
执行 review 技能时在终端输出审查区间、问题清单与处理决策；有 Git 改动时按上级 `AGENTS.md` 公共契约执行 `git diff --check` 与定向复查；未经用户明确要求不自动暂存、提交或推送；无 Git 条件立即跳过。
