# AGENTS.md — pure 技能

本目录为实现 `pure` 技能的 `SKILL.md`（穷尽剖析核心部分 + LaTeX PDF 报告：只读分析当前 git 库的
核心部分——纯代码向为独特算法、纯物理向为物理图像与公式推导、交叉向为代码-物理一一对应，
结论附 `文件:行号` 参考源，输出 PDF 到工作目录 docs/，含 frontmatter 与完整工作流）。
SKILL.md 为唯一权威内容，勿复制改动；LaTeX 模板规范见 `references/latex-template.md`。
执行 pure 技能时在终端输出任务定义、核心清单、证据与编译结果；有 Git 改动时按上级 `AGENTS.md` 公共契约检查、只暂存本次文件并创建本地 commit，不 push；无 Git 或无改动立即跳过。
