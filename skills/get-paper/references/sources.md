# get-paper 参考依据与采纳决策

本技能只复用公开 API、协议与安全模式，不复制第三方实现。核验时间：2026-10-21 CST。

## 官方接口

- arXiv API User Manual：<https://info.arxiv.org/help/api/user-manual.html>。采用 Atom 查询、
  `id_list`、分页和请求间隔原则；实测 HTTP 200。arXiv 源码入口使用
  `https://arxiv.org/src/<id>`；示例 `2601.01205` 返回 `application/gzip`、HTTP 200。
- OpenAlex Works API：<https://api.openalex.org/works>。采用 works 检索、OA 位置、许可证和
  `abstract_inverted_index`；本次实测检索 HTTP 200。
- Crossref REST API：<https://api.crossref.org/swagger-docs>。采用元数据、作者、年份、引用数与
  许可证字段；本次实测 Swagger HTTP 200。Crossref 的 PDF link 不自动视为 OA。
- Semantic Scholar Graph API：<https://api.semanticscholar.org/api-docs/>。采用搜索与
  `openAccessPdf` 字段；文档 HTTP 200，搜索端点本次遇到 HTTP 429，因此实现为可降级来源而不是硬依赖。

## 候选项目审计

- `liuyixin-louis/arxiv2latex`，固定提交
  `5ab54490693acde320bb26162f1d947509908121`，<https://github.com/liuyixin-louis/arxiv2latex>。
  主题匹配且提供批量下载思路，但仓库未声明许可证且维护时间较早；拒绝复制代码，只保留
  “多论文批量获取”为独立设计需求。
- `LaZoark/arxiv-src-crawler`，固定提交
  `e044595a654bfc8484425e09cdd6847a72b10310`，<https://github.com/LaZoark/arxiv-src-crawler>。
  MIT 许可，但 README 明确处于开发中且入口依赖 notebook；拒绝引入其不完整工程，只采纳官方 API
  与源码下载这一已由上游文档验证的思路。
- 多源热榜同查询 `arxiv latex source download`：GitHub 8 条、GitLab 1 条、Gitee/Codeberg
  空结果；星数只用于发现，未作为质量或安全结论。

## 本库实现决策

脚本使用 Python 标准库重新实现多源适配、相关性排序、HTTPS/私网边界、事务解包、Git/abs 元数据
降级、许可记录和缓存树哈希；没有复制上述候选项目的代码。这样避免继承未声明许可、notebook
入口或过时依赖。
