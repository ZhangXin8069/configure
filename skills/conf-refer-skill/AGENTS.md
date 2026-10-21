# AGENTS.md — conf-refer-skill 技能

本目录实现 `conf-refer-skill`：从 `$CONFIGURE_ROOT/refer/git-rep` 中以 `skills` 结尾的技能目录原地发现并直调外部技能，处理同名、镜像、符号链接、打开文件描述符 TOCTOU 边界、frontmatter/路径控制字符、占位符、工具与本地安全规则的最小适配。`SKILL.md` 是执行流程权威；`scripts/find-refer-skills.py` 只读索引候选，`scripts/find-refer-skills.test.sh` 作为回归入口调用 `scripts/find_refer_skills_cases.py`；`evals/evals.json` 保存有/无技能期望，`evals/trigger-queries.json` 保存 10 个正触发和 10 个负触发查询。外部参考目录保持只读；有 Git 改动时执行 `git diff --check` 与定向复查，未经明确授权不暂存、提交或推送。
