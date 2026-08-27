# AGENTS.md — plan 技能

本目录为实现 `plan` 技能的 `SKILL.md`（实现计划编写：文件结构设计→任务分解→无占位符计划→自审，吸收 obra/superpowers writing-plans 方法论：bite-sized 任务粒度、每任务独立测试周期、Consumes/Produces 接口声明）。SKILL.md 为唯一权威内容，勿复制改动。执行 plan 技能时生成 `docs/plans/YYYY-MM-DD-<feature>.md` 计划文档，并在终端输出自审结果；有 Git 改动时按上级 `AGENTS.md` 公共契约执行 `git diff --check` 与定向复查；未经用户明确要求不自动暂存、提交或推送；无 Git 条件立即跳过。
