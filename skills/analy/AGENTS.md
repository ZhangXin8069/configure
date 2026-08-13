# AGENTS.md — analy 技能

本目录为实现 `analy` 技能的 `SKILL.md`（仓库分析 + LaTeX PDF 报告：只读分析当前 git 库全部文档与代码，
解析 `{$用户输入}` 主题，结论附 `文件:行号` 参考源，输出 PDF 到工作目录 docs/，
含 frontmatter 与完整工作流）。SKILL.md 为唯一权威内容，勿复制改动。
执行 analy 技能时在当前工作目录生成 `.analy.<时间戳>.log` 会话日志
（解析主题、调查索引、证据清单与编译结果全程追加记录），不入库。
