# AGENTS.md — fast 技能

本目录实现 `fast` 修饰技能：传播 fast 上下文，压缩重复工作，默认将 analy/pure/report 轻量化为 Markdown，
并把全局默认迭代上限设为 3、auto/all 的默认边际收益停止阈值设为 `<25%`；用户明确例外优先。
`SKILL.md` 是唯一权威内容；显式用户约束、正确性、安全性和关键证据优先于提速策略。
执行 fast 技能时保留实际效率/质量证据；有 Git 改动时按上级 `AGENTS.md` 执行 `git diff --check`，不自动提交或推送。
