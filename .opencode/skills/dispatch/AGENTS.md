# AGENTS.md — dispatch 技能

本目录为实现 `dispatch` 技能的 `SKILL.md`（并行子代理派发：2+ 个独立子任务
拆域并行、精确构造代理上下文（问题域/目标/约束/预期输出）、同消息派发=并行、
返回后整合验证，吸收 obra/superpowers dispatching-parallel-agents 方法论）。
SKILL.md 为唯一权威内容，勿复制改动。
执行 dispatch 技能时在当前工作目录生成 `.dispatch.<时间戳>.log` 会话日志
（拆域方案、派发指令、代理摘要与整合验证全程追加记录），不入库。
