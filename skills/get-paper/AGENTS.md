# AGENTS.md — get-paper 技能目录

本目录实现 `get-paper`：围绕主任务跨 arXiv、OpenAlex、Crossref、Semantic Scholar 检索论文，
优先安全获取 arXiv LaTeX 源码，并以相关性、来源、许可和哈希留下可追溯证据。
`SKILL.md` 是流程权威；`scripts/get-paper.py` 是标准库 CLI，`scripts/test_get_paper.py` 覆盖
标识符解析、相关性排序、去重、主 TeX 识别、路径穿越拒绝、OA/HTTPS 边界、事务解包、缓存树哈希和
跨源故障隔离。
`references/sources.md` 记录官方 API、候选项目审计、固定 ref 与拒绝/采纳理由。
有 Git 改动时执行 `git diff --check` 与定向复查；未授权不提交、不推送，未确认许可不并入或再分发论文附件。
