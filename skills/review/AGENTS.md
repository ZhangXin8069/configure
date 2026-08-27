# AGENTS.md — review 技能

本目录为实现 `review` 技能的 `SKILL.md`（代码审查：早审查常审查、子代理审查+
精确上下文裁剪、问题分级 Critical/Important/Minor 与处理决策，吸收 superpowers
requesting-code-review 方法论）。SKILL.md 为唯一权威内容，勿复制改动。
执行 review 技能时在终端输出审查区间、问题清单与处理决策；有 Git 改动时按上级 `AGENTS.md` 公共契约检查、只暂存本次文件并创建本地 commit，不 push；无 Git 或无改动立即跳过。
