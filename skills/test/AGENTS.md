# AGENTS.md — test 技能

本目录为实现 `test` 技能的 `SKILL.md`（系统化测试：默认测试对象为上次 agent 生成的工作，
参考 `.agent.*.list` 用户输入清单格式；含 debug 循环修复、optim 循环优化、设备与多精度切换）。
SKILL.md 为唯一权威内容，勿复制改动。执行 test 技能时在当前工作目录生成 `.test.<时间戳>.log`
会话日志与 `test_out/` 产物目录（intermediate/results/figures），不入库。
