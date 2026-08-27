# AGENTS.md — go-on 技能

本目录为实现 `go-on` 技能的 `SKILL.md`（继续上次任务：孤儿进程治理 → 多源查找上次
任务信息（`.***.list`/git 改动/项目与全局 AGENTS.md/opencode 会话）→
确认{上次任务信息} → 无缝继续——优先 opencode 原生会话继续（-c/-s/--fork/run -c，
继承消息历史与 Todo），备选手动重建，并循环补查至信息收敛）。
SKILL.md 为唯一权威内容，勿复制改动。执行 go-on 技能时在当前工作目录生成
只使用输入清单、Git 状态/提交和原生会话信息；有 Git 改动时按上级 `AGENTS.md` 公共契约执行 `git diff --check` 与定向复查；未经用户明确要求不自动暂存、提交或推送；无 Git 条件立即跳过。
