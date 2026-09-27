# AGENTS.md — form 技能

本目录实现 `form` 技能：审计并整改 Git 库的语言框架、命名、目录职责、文档/日志/数据/测试
布局和 Git 交付格式，并生成目标库特化规则。`SKILL.md` 为执行入口，`references/` 仅在对应
审计、目录整理或 Git 交付阶段按需读取；`references/source-snapshots/` 是四个参考 URL 的
固定提交明文快照，不是运行时依赖。

调用 `~form` 默认授予较高权限，覆盖计划内仓库清理及常规提交、推送和标签；force push、
改写已推送标签、系统配置和凭据操作仍须单独确认。其他情况下遵循上级 `AGENTS.md` 公共契约。
