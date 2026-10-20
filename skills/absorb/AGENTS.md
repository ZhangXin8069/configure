# AGENTS.md — absorb 技能目录

本目录实现 `absorb`：自动盘点 Git 库中新加入的外来内容，固定来源与许可，隔离分析缺陷和价值，
通过吸收矩阵选择 `keep/adapt/reference-only/reject`，再以最小改动、测试、审查和实测优化完成闭环。
`SKILL.md` 是流程权威；`scripts/absorb_inventory.py` 生成覆盖清单和风险信号，
`scripts/test_absorb_inventory.py` 覆盖提交/暂存/工作树分版本、单根提交、gitlink、类型变化、
符号链接脱敏、ignored 开关、许可证、秘密和截断扫描边界。
`references/sources.md` 记录 SPDX、OpenSSF、GitHub dependency review 与 Git 对象模型依据。
有 Git 改动时执行 `git diff --check` 与定向复查；未授权不暂存、提交、推送，外来内容默认不执行、不删除。
