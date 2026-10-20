# AGENTS.md — form 技能

本目录实现 `form` 技能：审计并整改 Git 库的语言框架、命名、目录职责、文档/日志/数据/测试
布局和 Git 交付格式，并生成目标库特化规则。`SKILL.md` 为执行入口，`references/` 仅在对应
审计、目录整理或 Git 交付阶段按需读取；`references/source-snapshots/` 是四个参考 URL 的
固定提交明文快照，不是运行时依赖。

参考 Git 库统一以 submodule 放在 `refer/git-rep/<upstream-name>`，来源与致谢写入
`refer/git-rep/README.md`；本库对这些子库的分析文档集中到 `refer/git-rep/docs/`。
普通拷贝不是最终状态，按 `SKILL.md` Step 5 的参考子库流程迁移；子库工作树只读。

调用 `~form` 默认授予较高权限，覆盖计划内仓库清理及常规提交、推送和标签；force push、
改写已推送标签、系统配置和凭据操作仍须单独确认。其他情况下遵循上级 `AGENTS.md` 公共契约。

`scripts/form-audit.sh`、`scripts/form-large-files-check.sh` 和
`scripts/form-snapshot-verify.sh` 必须保持只读；审计脚本报告路径/布局候选冲突（含
`refer/git-rep` 子库元数据、README 来源/致谢和分析文档位置），大文件脚本报告超限暂存
内容，快照脚本校验离线参考。`scripts/form-agents-sync.sh` 只更新根 `AGENTS.md` 的
`form-skill` 标记块，不改写块外本地约定。任何仓库修复都由 `SKILL.md` 的批准流程驱动。
所有目录的 agent 指令文件统一使用 `AGENTS.md`；`AGENT.md` 是历史输入错误。两者在同一
目录并存时，必须先合并有效规则到 `AGENTS.md`、确认无内容丢失，再删除单数文件。
修改脚本后运行 `scripts/form-scripts.test.sh`。
