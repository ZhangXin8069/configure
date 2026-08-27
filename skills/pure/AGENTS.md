# AGENTS.md — pure 技能

本目录为实现 `pure` 技能的 `SKILL.md`（细节解析参考层：优先消费 analy 的整体参考，穷尽剖析当前 git 库的
核心部分——纯代码向为独特算法、纯物理向为物理图像与公式推导、交叉向为代码-物理一一对应，
以逐符号/逐公式证据形成供后续 agent 使用的细节 PDF 到工作目录 docs/，含 frontmatter 与完整工作流）。
SKILL.md 为唯一权威内容，勿复制改动；LaTeX 模板规范见 `references/latex-template.md`。
执行 pure 技能时在终端输出任务定义、核心清单、证据与编译结果；有 Git 改动时按上级 `AGENTS.md` 公共契约执行 `git diff --check` 与定向复查；未经用户明确要求不自动暂存、提交或推送；无 Git 条件立即跳过。
