# AGENTS.md — test 技能

本目录为实现 `test` 技能的 `SKILL.md`（系统化测试：默认测试对象为上次 agent 生成的工作，
参考 `.agent.*.list` 用户输入清单格式；含 debug 循环修复、optim 循环优化、设备与多精度切换）。
SKILL.md 为唯一权威内容，勿复制改动。执行 test 技能时将中间、最终结果与图表写入 `test_out/`
（intermediate/results/figures），并在终端输出验证摘要；有 Git 改动时按上级 `AGENTS.md` 公共契约执行 `git diff --check` 与定向复查；未经用户明确要求不自动暂存、提交或推送；无 Git 条件立即跳过。
