# AGENTS.md — make 技能

本目录为实现 `make` 技能的 `SKILL.md`（项目生成：编排调用本目录全部技能
init/tag/debug/optim/diff/analy/test 完成生成全过程，细节要求为其汇总）。
SKILL.md 为唯一权威内容，勿复制改动。
执行 make 技能时在终端输出任务定义、计划、验证和收尾摘要；有 Git 改动时按上级 `AGENTS.md` 公共契约执行 `git diff --check` 与定向复查；未经用户明确要求不自动暂存、提交或推送；无 Git 条件立即跳过。
