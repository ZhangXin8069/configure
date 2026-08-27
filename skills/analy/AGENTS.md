# AGENTS.md — analy 技能

本目录为实现 `analy` 技能的 `SKILL.md`（仓库分析 + LaTeX PDF 报告：只读分析当前 git 库全部文档与代码，
解析 `{$用户输入}` 主题，结论附 `文件:行号` 参考源，输出 PDF 到工作目录 docs/，
含 frontmatter 与完整工作流）。SKILL.md 为唯一权威内容，勿复制改动。
执行 analy 技能时通过终端输出和报告文件保留证据；有 Git 改动时按上级 `AGENTS.md` 公共契约检查、只暂存本次文件并创建本地 commit，不 push；无 Git 或无改动立即跳过。
