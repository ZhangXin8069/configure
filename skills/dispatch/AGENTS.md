# AGENTS.md — dispatch 技能

本目录为实现 `dispatch` 技能的 `SKILL.md`（并行子代理派发：2+ 个独立子任务
拆域并行、精确构造代理上下文（问题域/目标/约束/预期输出）、同消息派发=并行、
返回后整合验证，吸收 obra/superpowers dispatching-parallel-agents 方法论）。
SKILL.md 为唯一权威内容，勿复制改动。
执行 dispatch 技能时在终端输出拆域、代理摘要与整合验证结果；有 Git 改动时按上级 `AGENTS.md` 公共契约执行 `git diff --check` 与定向复查；未经用户明确要求不自动暂存、提交或推送；无 Git 条件立即跳过。
