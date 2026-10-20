# AGENTS.md — rule 技能

本目录实现 `rule` 常驻辅助技能：在进程启动、长任务监控、共享/调度资源分配和阶段 Git 交付门控点，
执行时间、资源、可观测性、终止与条件式自动交付规则。`SKILL.md` 为流程权威。
`references/` 分别保存进程与资源、条件式交付、其他技能规则抽取映射；`scripts/run-guarded.sh`
提供硬超时、心跳和进度新鲜度检查，修改后必须运行 `bash scripts/run-guarded.test.sh`。
有 Git 且本次产生文件改动时执行 `git diff --check` 与定向复查；条件式提交、推送和标签必须完整通过
`SKILL.md` 的交付闸门。闸门通过后的本地提交和本次新标签必须继续完成 push 闭环，只有用户明确要求仅本地时
例外；破坏性 Git 操作始终需要用户明确确认。
