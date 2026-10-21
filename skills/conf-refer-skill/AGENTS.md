# AGENTS.md — conf-refer-skill 技能

本目录实现 `conf-refer-skill`：以 `discover` 模式在用户未限定仅本地时自动盘点本地与 `$CONFIGURE_ROOT/refer/git-rep` 中可用于某能力/领域的技能，以 `execute` 模式从外部技能目录原地选择并直调技能；处理同名、镜像、符号链接、打开文件描述符 TOCTOU 边界、frontmatter/路径控制字符、占位符、工具与本地安全规则的最小适配。`SKILL.md` 是执行流程权威；`scripts/find-refer-skills.py` 只读索引候选，`scripts/find-refer-skills.test.sh` 作为回归入口调用 `scripts/find_refer_skills_cases.py`；`evals/evals.json` 保存有/无技能期望，`evals/trigger-queries.json` 保存 11 个正触发和 11 个负触发查询。外部参考目录保持只读；有 Git 改动时执行 `git diff --check` 与定向复查，未经明确授权不暂存、提交或推送。
