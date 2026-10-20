# absorb 参考依据与采纳决策

本技能复用供应链治理原则和 Git 原生对象模型，不复制外部项目实现。核验时间：2026-10-21 CST。

## 权威规范与实践

- SPDX license information：<https://spdx.dev/learn/handling-license-info/>，本次实测 HTTP 200。
  采用 SPDX 标识/许可证表达式、文件级来源和 NOTICE/署名应可追溯的原则。
- OpenSSF Scorecard：<https://github.com/ossf/scorecard>，本次实测 HTTP 200。采用对维护活跃度、
  依赖更新、危险工作流和供应链风险进行证据化检查的思路；不在本技能内自动执行外部评分器。
- GitHub dependency review 概念文档：
  <https://docs.github.com/en/code-security/concepts/supply-chain-security/dependency-review>，
  本次实测 HTTP 200。采用“依赖/来源变化必须显式审查，不能默认信任”的原则。
- Git 原生对象与 index/tree/blob 模型：以本地 `git ls-files --stage`、`git ls-tree`、
  `git cat-file` 行为为确定性证据；提交、暂存和工作树版本分开记录，不把工作树内容冒充已暂存内容。

## 热榜检索与采纳决策

- 查询 `vendored code audit dependencies`：GitHub 返回 2 条主题弱相关候选；Gitee、GitLab、
  Codeberg 均返回空结果。未发现可安全复用的高质量同类 skill，因此不采纳外部实现。
- 本技能按上述规范自行实现清单、来源信号、秘密/执行风险、gitlink/OID、符号链接哈希、
  type-change、ignored 开关、许可证命名和吸收矩阵。所有外部方法只作为原则来源，不复制代码。
