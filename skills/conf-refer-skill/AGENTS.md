# AGENTS.md — conf-refer-skill 技能

本目录实现 `conf-refer-skill`：从 `$CONFIGURE_ROOT/refer/git-rep` 的嵌套 `skills/` 中原地发现并直调外部技能，处理同名、镜像、符号链接、占位符、工具与本地安全规则的最小适配。`SKILL.md` 是执行流程权威；`scripts/find_refer_skills.py` 只读索引候选，`scripts/find-refer-skills.test.sh` 作为回归入口调用 `scripts/find_refer_skills_cases.py`，覆盖嵌套目录、链接边界、异常告警、去重、查询和路径校验。外部参考目录保持只读；有 Git 改动时执行 `git diff --check` 与定向复查，未经明确授权不暂存、提交、推送或打标。
