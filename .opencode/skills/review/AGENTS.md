# AGENTS.md — review 技能

本目录为实现 `review` 技能的 `SKILL.md`（代码审查：早审查常审查、子代理审查+
精确上下文裁剪、问题分级 Critical/Important/Minor 与处理决策，吸收 superpowers
requesting-code-review 方法论）。SKILL.md 为唯一权威内容，勿复制改动。
执行 review 技能时在当前工作目录生成 `.review.<时间戳>.log` 会话日志
（审查区间、子代理上下文、问题清单与处理决策全程追加记录），不入库。
