# AGENTS.md — init 技能

本目录为实现 `init` 技能的 `SKILL.md`（仓库/目录初始化，含 frontmatter 与完整工作流）。SKILL.md 为唯一权威内容，勿复制改动。执行 init 技能时在终端输出扫描、执行与验证摘要；有 Git 改动时按上级 `AGENTS.md` 公共契约检查、只暂存本次文件并创建本地 commit，不 push；无 Git 或无改动立即跳过。
