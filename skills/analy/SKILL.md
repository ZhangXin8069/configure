---
name: analy
description: |
  当用户要求分析、解析、解读或梳理仓库结构、代码与文档关系、项目思路，或要求生成可追溯
  的分析报告/PDF，或要为后续 agent 建立仓库整体参考时使用；输入 `{~analy ...}` 或 `{$...}`
  时也使用。用户虽未说“分析”但目标是理解仓库全貌、代码对象或配置加载链时同样使用；
  分析报告或其下游展示出现版式溢出、内容遮挡、页脚/列边界侵入时也使用。
metadata:
  openclaw:
    emoji: 📊
---

# analy — 仓库整体分析与 agent 参考技能

## 执行前置

遵循当前目录 `AGENTS.md`「技能执行公共契约」；仅按需读取技能正文与 reference。


对当前 git 仓库中的**全部文档与代码**进行只读分析，解析用户输入（`{$用户输入}`，即分析主题/问题），
以证据驱动的方式产出分析结论，**每个结论附参考源（`文件:行号`）**；普通模式最后用 LaTeX 生成 PDF 文档，
输出到**当前工作目录的 `docs/` 文件夹**。本技能是分析链的**整体参考层**：产物必须让没有本次会话
上下文的后续 agent 能快速理解仓库边界、入口、依赖、工作流、证据位置与未决问题，再决定调用
`pure`、`debug`、`test` 或其他技能。

### fast_context 分支

收到 `fast_context.active=true` 且其 `effective_format=Markdown` 时，进入本技能的轻量 Markdown 分支；
`format_default` 仅是 fast 的默认元数据，不参与分支判断：
默认交付 `docs/analy_<主题slug>_<YYYYMMDD>.md`，执行 Markdown 结构、公式分隔符、链接、证据行号和内容完整性检查；
不执行下方普通模式的 LaTeX 源文件生成、PDF 编译和 PDF 版式验收步骤。用户明确指定 PDF/LaTeX/幻灯片时，
按用户约束返回普通 LaTeX/PDF 分支。该分支选择是 fast 对本技能默认交付载体的明确覆盖。

**核心目的（三视角，任何报告必齐）**：① **主体结构**——仓库如何分层组织（入口/核心/工具/
配置/文档/参考）；② **各部分关系**——各部分之间如何联系（引用/依赖/包含/生成/演进）；
③ **项目思路**——为什么这样设计（设计意图、演进脉络、典型工作流）。三视角回答
"仓库是什么 → 各部分怎么连 → 为什么长这样"，即**掌握项目思路**。

**饱和与深度**：分析区间**饱和**（每个文件都有归宿：精读/浏览/仅索引，无覆盖死角）；整体层的深度
以结构、关系、设计意图和证据入口闭合为准，做到整体→部分→细节可导航，不替代 `pure` 对核心对象、
算法或公式的逐符号穷尽解析。

本技能的价值在于让"分析结论"可追溯、可复用：每个说法都有据可查（文件:行号），代码片段与仓库
逐字节一致，多份资料的关系呈现为"织网"而非"堆砌"，并提供稳定的后续 agent 交接入口。分析全程只读，
唯一写操作是 docs/ 下的产物。凡是可能交给 `report` 的密集公式、表格、流程图或代码片段，还要在交接
信息中标明视觉类型、占用等级、合法拆分边界和已知版式风险，避免展示层只能凭正文猜页面布局。

## 核心原则

1. **只读分析**：分析阶段不修改源代码、不暂存；普通模式唯一写操作是向 `docs/` 输出 `.tex` 与 `.pdf`，
   fast Markdown 分支只写对应 `.md` 交付物；产物在收尾按公共契约处理。
2. **解析用户输入**：把 `{$用户输入}` 解析为分析主题——提取问题焦点、限定范围与期望输出；
   输入为明确主题时直接执行；输入含糊时**先提问**（所有问题一次全部列出，用户一次回答），不臆断主题。
3. **全库饱和调查**：先建立仓库全景，再按主题收敛；全景不只是索引——每个文件都要有归宿
   （**精读/浏览/仅索引**三态，登记进覆盖表），用四条遍历路径（按目录、按类型、按 git 历史、
   按入口引用链）交叉走遍全库，收尾时无"未分类"文件——**覆盖表闭合才可聚焦**；
   全景索引是防止遗漏关联证据的保险，先广后深。
4. **三视角核心目的**：任何报告必含三节——**主体结构**（分层架构与职责）、**各部分关系**
   （依赖链/引用/演进）、**项目思路**（设计意图/演进脉络/典型工作流）；缺一即未达本技能
   核心目的（"掌握项目思路"）；主题聚焦章节置于三视角之后。
5. **整体层追问**：围绕架构、依赖和工作流回答是什么（what）→ 怎么连接（how）→ **为什么这样设计**
   （why，动机/权衡/演进）；核心算法、物理公式和逐符号实现细节只建立入口并交给 `pure` 深挖。
   每句结论可归入 **确证**（直接证据）/ **推断**（由证据推出）/ **未验证**（显式标注）三级，不写无凭口吻。
6. **证据驱动，参考源可追溯**：每个分析结论必须对应真实存在的内容，附 `文件:行号` 参考源；
   代码片段**用 `\lstinputlisting[firstline,lastline]` 直接引用仓库原文件**，不做转写、不手抄，
   保证普通 PDF 中片段与仓库实际内容逐字节一致；Markdown 分支同样保留原文证据与行号；统计数字实测，量纲与边界情形校验；收尾形成可检索的
   证据索引，方便后续 agent 定位原文；对拟进入图表/公式/代码视觉的证据同步记录内容边界和版式风险。
   主题在仓库中找不到证据时明确报告"未找到相关依据"，绝不编造文件路径、代码或数据。
7. **编译闭环与防溢出**：普通模式生成 `.tex` → 编译 → 验证 PDF 产物存在且内容正确；fast Markdown 分支改做 Markdown 结构与证据闭环检查；
   交付前从编译终端输出确认 `Overfull` 与 `Float too large` 均为 **0**
   （行宽溢出/图表溢出页面两类；长代码/长表/长词/公式/图片均按模板防溢出规则处理，
   见 `references/latex-template.md`）；再逐页渲染检查边界、框体、列间和页脚是否可见遮挡，
   因为“无 Overfull”不能证明 TikZ 节点或彩色框没有侵入邻接区域；TikZ 的节点、路径标签、独立标签
   和箭头须分别按包围盒检查，标签优先使用带显式安全间距的 `above/below/left/right`；编译失败依据终端
   错误定位修复，循环尝试直至成功或用户终止。
8. **默认引入参考知识库**：git 家目录（被分析仓库根）下的参考类目录
   （`docs`、`books`、`refer`、`references`、`examples`、`reports`、`补充`、`代码`、`文档`、`汇报`
   及同类命名的目录，清单可扩展，以本原则为准，Step 3/4 命令与之一致）视为参考知识库，
   **默认自动引入，不依赖主题**；存在即建全量索引并阅读说明类文件
   建立背景认知，主题聚焦时在其中检索相关内容并入证据链，使解析更全面深入（"解析越多越好"）；
   目录不存在或文件不可解析时静默跳过并在覆盖范围中如实注明；全程只读。
9. **多资料联系与层次逻辑 + 代码-对象对应**：分析涉及多份资料（文档/代码/配置/参考书）时，
   必须讲明各部分之间的联系——引用/依赖/包含关系、层级归属（入口层/核心层/工具层/文档层）
   与共同主题线，报告以"联系与层次"呈现，**重联系轻罗列**，避免资料堆砌；
   解析代码时先识别代码所描述的对象（物理图像/业务实体/系统组件），建立
   "代码符号 ↔ 对象概念"映射，用对象语言解释代码行为与动机，再落到实现细节；大任务中产生的全部图表与运行输出须列清单并逐项解读，说明来源、含义、结论关联与局限，确保结果分析、综合分析和附录无遗漏。

## 工作流的统一 LaTeX 表达（普通模式）

凡是算法、伪代码、公式推导、编程思路、数据处理或验证过程等具有顺序、迭代或分支关系的内容，
在生成报告中统一用下列单列 `table[htbp]` 结构承载；它是工作流的主表达，流程图只补充跨模块关系。
每行只写一个动作或推导转移，`\quad`/`\quad\quad` 表示层级。算法按“输入→初始化→循环→分支/更新→
收敛→输出”组织，公式推导在每行写出等式或箭头并标注定义、对称性、近似、量纲或边界条件，编程思路按
“输入→状态/数据结构→核心处理→校验/错误分支→输出”组织。真实报告中的公式、符号、数据和证据必须替换为
本次核验内容；长流程按语义拆成多个表格，不能靠缩小字号解决溢出。

```latex
\begin{table}[htbp]
  \centering
  \caption*{Workflow. Algorithm, derivation, and implementation}
  \small
  \begin{tabular}{@{}l@{}}
    $\text{Input: } D,\; x^{(0)},\; \varepsilon$ \\
    $\text{Initialize: } \mathrm{state}\gets(D,x^{(0)},\varepsilon)$ \\
    $\text{for } k=0,1,\ldots\ \text{ iterate:}$ \\
    \quad $\text{derive/update } F_{k+1}=T(F_k)\quad(\text{definition/symmetry/approximation})$ \\
    \quad $\text{implement } \mathrm{state}\gets\mathrm{update}(\mathrm{state},D)$ \\
    \quad $\text{if } \lVert r_{k+1}\rVert\le\varepsilon\ \text{ then stop}$ \\
    \quad $\text{else } k\gets k+1$ \\
    $\text{end for}$ \\
    $\text{Output: } F_{\mathrm{out}},\;\mathrm{state},\;\text{verified evidence}$ \\
  \end{tabular}
\end{table}
```

表格标题注明算法/推导主题及“示意”或数据来源；表格下方保留必要的 `文件:行号`、命令或参考源。

## 触发时机

**使用本技能**：

- 用户要求分析仓库："分析"、"analy"、"解析"、"分析一下"、"解读"、"总结仓库"、"梳理"
- 用户输入 `{~analy <用户输入>}` 或 `{$用户输入}`：`{...}` 内即分析主题/问题
- 用户要求生成分析文档："生成分析报告"、"输出 PDF"、"把分析写成文档"、"latex 输出"
- 用户需要理解仓库结构、资料联系、代码对象（即使未出现"分析"字样），例如
  "这个仓库是干嘛的"、"env.sh 加载链怎么走的"、"这段代码对应什么物理图像"
- 用户要求为后续 agent 提供整体参考：仓库地图、入口/依赖链、模块职责、典型工作流、证据索引和未决问题
- 与其他技能配合：tag 前评估仓库结构、diff 后解释改动意义、debug 前梳理代码依赖、
  `analy` 产物作为后续 `pure` 细节解析和 `report` 学者展示的整体输入，先 analy 掌握全貌再进入下游技能；
  多目录/多主题独立调查 → dispatch 并行子代理收集证据（整合时回填覆盖表）

**不使用本技能**（转用对应技能）：

| 场景 | 改用技能 |
|---|---|
| 定位/修复 bug、排错 | `debug` |
| 性能/启动/资源优化 | `optim` |
| 查看改动差异、版本对比 | `diff` |
| 初始化/归档目录与 agent 配置 | `init` |
| 系统化测试与验证 | `test` |
| 穷尽剖析核心部分（独特算法/物理图像/代码-物理映射） | `pure` |
| 生成全新项目 | `make` |

主题含糊（如只说"分析一下"）时**先提问**确认范围，不擅自定义主题；
所有问题在**第一次交互一次性全部提出**（编号列表），用户一次回答，不逐次追问。

## 分析思路框架

主题涉及一次运行、模拟、计算、项目任务或完整实现时，先判断对象性质，再选择代码/软件、
物理/理论或交叉框架，并按 15 步展开。详细步骤表、证据要求与代码-物理交叉规则见
`references/analysis-framework.md`，使用该参考文件前先完整读取。

## 输入解析规则

| 输入形式 | 解析方式 |
|---|---|
| `{$主题或问题}` | 直接作为分析主题；含问句时按问题展开 |
| `{~analy 主题}` | 同上，`analy` 之后的部分为主题 |
| 主题含糊（无焦点词） | **一次性列出候选**（全仓库概览/某主题/某文件/某功能）提问确认，不逐次追问 |
| 主题含范围限定 | 尊重限定（如"只看 bin/ 下的脚本"），并说明分析范围 |

主题解析后输出一句**任务定义**（如"分析主题：环境加载链 env.sh 的模块构成"）并在终端摘要中说明，
避免歧义——任务定义是后续调查与报告结构的锚点。

## 输出命名约定

- 输出目录：**当前工作目录（被分析仓库根）下的 `docs/`**；不存在则创建
- fast Markdown 文件名：`analy_<主题slug>_<YYYYMMDD>.md`
- PDF 文件名：`analy_<主题slug>_<YYYYMMDD>.pdf`（slug 用拼音/英文短词，不用中文字符；
  如 `analy_env_20260813.pdf`）
- `.tex` 源文件同目录同名：`analy_<主题slug>_<YYYYMMDD>.tex`
- 同日重复输出同一主题：文件名追加序号（`_2`、`_3`），不覆盖已有产物
- 命名一致性是有意的：同目录的 `.tex`/`.pdf` 同名便于追踪与清理

## 工作流程

### Step 1. 解析用户输入（主题）

1. 从 `{$用户输入}` / `{~analy ...}` 提取主题，按「输入解析规则」确认任务定义；
2. 主题不明确时**向用户提问**（所有问题一次全部列出，用户一次回答），不擅自定义；
3. 在终端摘要中说明任务定义。

### Markdown 工作流（仅 `fast_context.effective_format=Markdown`）

完成 Step 1 后，若 `fast_context.active=true` 且 `effective_format=Markdown`，只执行 M1–M5，
随后结束本技能；不得继续执行下方普通模式的 Step 2–Step 8。Markdown 分支仍保持全库覆盖、三视角、
证据行号和后续 agent 交接，只合并重复的遍历与排版准备。

#### M1. 最小环境准备

执行 `git rev-parse --is-inside-work-tree`（失败时在产物中注明非 git 目录），确认/创建 `docs/`，
并回显 `fast_context.active`、`global_rounds_max`、`optimization_gain_stop`、`quality_ratio_min`、
`format_override` 和 `effective_format`。此分支不检查或调用 LaTeX 工具链，不读取
`references/latex-template.md`。

#### M2. 合并只读调查与主题取证

用一次覆盖登记表合并目录、文件类型、近期 Git 历史和入口引用链的交叉结果；每个文件标为
**精读/浏览/仅索引**，表格必须闭合。围绕主题收集三视角证据：主体结构、各部分关系、项目思路，
并记录真实的 `文件:行号`、命令输出、参考资料命中和确证/推断/未验证状态。代码证据在 Markdown 中使用
带语言标记的 fenced code block，并注明原文件路径与行号；不得把手抄片段当作来源。

#### M3. 写入 Markdown 交付物

写入 `docs/analy_<slug>_<YYYYMMDD>.md`（同名时追加 `_2`、`_3`，不覆盖已有产物），至少按以下顺序组织：

1. **任务与范围**：任务定义、覆盖/未覆盖范围、参考知识库状态；
2. **主体结构**：分层职责与关键入口；
3. **各部分关系**：依赖/引用/包含/生成链与版本演进；
4. **项目思路**：设计动机、权衡、演进脉络和典型工作流；
5. **主题分析**：围绕用户问题的证据化结论；
6. **证据索引与交接**：`文件:行号`、状态、下游动作，以及每个密集对象的
   `content_id | claim_id | evidence_ids | visual_type | width_budget | height_budget | min_font_pt |
   item_count | split_allowed | split_boundary | risks | mitigation`；
7. **结论、局限与下一步**：区分确证/推断/未验证，不把未执行的 PDF 检查写成通过。

行内公式使用 `$...$`，独立公式使用 `$$...$$`；表格使用 Markdown 表格，链接使用可点击相对路径，
代码围栏必须保留原文语义和来源行号。

#### M4. Markdown 验证

```bash
md_file="docs/analy_<slug>_<YYYYMMDD>.md"
test -s "$md_file"
rg -n '^# |^## (任务与范围|主体结构|各部分关系|项目思路|主题分析|证据索引|结论)' "$md_file"
fence_count=$(awk '/^```/{n++} END{print n+0}' "$md_file")
test $((fence_count % 2)) -eq 0
rg -n '[^[:space:]]+:[0-9]+(-[0-9]+)?' "$md_file"
```

另行检查 Markdown 链接可解析、公式分隔符成对、覆盖表闭合、每个关键主张都有来源和状态；不运行
`xelatex`、`pdflatex`、`pdfinfo` 或 `pdftoppm`，因此总结中不填写 PDF 页数、溢出或逐页渲染指标。

#### M5. Markdown 总结

```text
✓ analy Markdown 分析完成
  fast:   active=true；global_rounds_max=<...>；optimization_gain_stop=<...>；quality_ratio_min=<...>；effective_format=Markdown
  主题:   <解析出的任务定义>
  覆盖:   <目录/文件范围、精读/浏览/仅索引计数；是否闭合>
  证据:   <文件:行号、命令、参考背景及确证/推断/未验证状态>
  入口:   <关键入口、依赖链、后续 agent 可从何处继续>
  交接:   <content_payload 与推荐下游技能>
  产物:   docs/analy_<slug>_<YYYYMMDD>.md
  验证:   <Markdown 结构、围栏、公式、链接、来源可追溯性结果>
  局限:   <未覆盖项/证据不足处；无则省略>
```

### Step 2. 环境准备（普通 LaTeX/PDF 模式；`effective_format != Markdown`）

```bash
# 1) 确认 git 仓库（在仓库根执行本技能）
git rev-parse --is-inside-work-tree

# 2) 确认/创建 docs 输出目录
mkdir -p docs

# 3) 确认 LaTeX 工具链（缺项则向用户报告，不静默降级）
command -v xelatex || command -v pdflatex || echo "NO_LATEX"
# 中文内容（主题含中文或仓库含中文文档）必须 xelatex + ctex；缺 ctex 时报错重试或告知用户
```

### Step 3. 全库只读调查（建立全景索引）

```bash
# 仓库元信息
git log --oneline -20          # 最近提交
git tag -l --sort=-v:refname | head -10   # 版本里程碑

# 目录结构（排除 .git/构建产物）
find . -type f -not -path "./.git/*" -not -path "*/node_modules/*" \
  -not -path "*/__pycache__/*" -not -path "./tmp/*" | sort

# 文档与代码规模（实测统计）
find . -name "*.md" -not -path "./.git/*" | wc -l        # 文档数
find . -name "*.sh" -not -path "./.git/*" | wc -l        # shell 脚本数
find . -name "*.py" -not -path "./.git/*" | wc -l        # python 文件数
wc -l $(find . -name "*.sh" -not -path "./.git/*") 2>/dev/null | tail -1   # 总行数
```

- 阅读 `AGENTS.md`、`README.md`、`docs/*.md` 建立仓库用途认知；
- 按主题相关性给文件打标签（入口、配置、脚本、文档、资源）；
- 记录索引统计（文件总数/类型分布）供报告"仓库概览"节使用。

**饱和覆盖登记表**（本技能核心机制，防覆盖死角）：

```bash
# 覆盖表格式（在终端摘要中说明，收尾时核对闭合）
# 路径 | 类型 | 分析状态(精读/浏览/仅索引) | 证据命中(文件:行号 或 "—")
```

1. **四条遍历路径交叉走遍全库**（任一遗漏即由另一条补上）：
   - 按目录：`find . -type f | sort` 逐目录清点；
   - 按类型：`.sh`/`.py`/`.md`/配置/数据分类型清点；
   - 按 git 历史：`git log --name-only -20` 中被修改的文件是否都进过覆盖表；
   - 按入口引用链：入口文件 → 被 source/import/include 的文件 → 引用的配置/数据，逐层追踪；
2. 每个文件分配三态之一：**精读**（进主题证据链）/ **浏览**（扫过确认用途）/
   **仅索引**（登记即跳过，如二进制/图片）；收尾时覆盖表必须闭合——
   全部文件都有状态且理由明确，无"未分类"；文件多时按目录汇总计数并注明抽查比例；
3. 覆盖表闭合后进入主题聚焦；聚焦中新发现的文件回填覆盖表。

**参考知识库索引**（默认引入，不依赖主题）：

```bash
# 参考目录清单（与核心原则第 8 条一致）：docs/books/refer/references/examples/reports/补充/代码/文档/汇报
# 存在即引入，缺者跳过并注明；新增同类目录时清单可扩展
for d in docs books refer references examples reports 补充 代码 文档 汇报; do
  [ -d "$d" ] && { echo "== $d =="; find "$d" -type f | sort; }
done
# 可检索文本规模统计（md/txt/tex 等可直接 grep；pdf 用 pdftotext 提取文本后检索）
find docs books refer references examples reports 补充 代码 文档 汇报 -type f \
  \( -name "*.md" -o -name "*.txt" -o -name "*.tex" -o -name "*.pdf" \) 2>/dev/null | wc -l
```

- 阅读参考目录中的说明类文件（如 `docs/AGENTS.md`、`*_settings.md`、`*_requirement.txt`）
  与书籍目录/前言，建立仓库背景认知——这些内容常解释仓库用途、环境依赖与配置动机；
- `.pdf` 书籍/文档用 `pdftotext <文件> -` 提取文本参与检索（仅检索不落盘）；
- 图片/二进制等不可解析文件仅列文件名，不读取、不参与检索，报告中注明；
- 参考目录不属于仓库时（如 books/ 尚未创建）如实记录"未引入"，不报错。

### Step 4. 主题聚焦（证据收集）

针对解析出的主题，用 grep/glob/read 定位相关文件与代码段：

```bash
# 主题关键词定位（示例：主题为"环境加载链"）
grep -rn "source\|PATH" env.sh lib/ --include="*.sh" -l
target_file="path/to/file"
grep -n "关键函数名\|关键变量" "$target_file"

# 参考知识库主题检索（目录清单同核心原则第 8 条/Step 3；命中文件纳入参考证据，读取相关段落）
grep -rni "主题关键词" docs/ books/ refer/ references/ examples/ reports/ 补充/ 代码/ 文档/ 汇报/ \
  --include="*.md" --include="*.txt" --include="*.tex" -l 2>/dev/null
# 参考书籍文本检索（pdf 先提取文本，仅检索不落盘）
for f in books/*.pdf; do pdftotext "$f" - 2>/dev/null | grep -ni "主题关键词" | head -5; done
```

1. **每个结论收集证据**：相关 `文件:行号`、代码段、文档段落；
2. **证据必须真实存在**：引用前用 read/grep 核实行号与实际内容——行号凭记忆写是分析报告
   最常见的事故源，引用前必须核实；
3. **代码片段**：记录 `文件 + firstline + lastline`，后续用 `\lstinputlisting` 直接引用，
   **不复制转写**；
4. **关联追踪**：入口文件 → 被引用的模块 → 数据/配置，形成依赖链证据；
5. **深度追问（三层）**：每个结论走完 what（是什么）→ how（怎么工作）→ why（为什么这样设计）
   三层追问；where/why 证据不足时标注推断级别（确证/推断/未验证），并记录"待补充证据"清单；
6. **三视角证据收集**（核心目的，收尾时逐项核对）：
   - **主体结构**：各层（入口/核心/工具/配置/文档/参考）的成员文件与职责一句话；
   - **各部分关系**：引用/依赖/包含/生成链（`A → B → C` 文本链）与版本演进关系；
   - **项目思路**：设计意图（为什么这样组织）、演进脉络（git 历史→结构变化的理由）、
     典型工作流（一次任务如何走遍各部分）；
7. **参考知识库引入**：检索命中的参考文件用 read 读相关段落，作为背景资料/旁证
   纳入证据链；参考源清单中类型标注为"参考"；参考内容与仓库主题无关联时注明"未命中"，不强行引用；
8. 主题在仓库中无依据时：记录"未找到相关证据"，报告阶段如实说明。

**多资料联系与层次梳理**（多份资料参与分析时必做）：

1. **角色定位**：为每份资料标定角色与层次——入口（启动/主流程）、核心实现（算法/逻辑）、
   工具支持（辅助脚本/库）、配置声明（参数/环境）、文档说明（README/AGENTS.md）、参考背景（知识库）；
2. **关系梳理**：找出资料间的真实联系——引用/依赖/包含链（如 `env.sh → tmp/scripts.sh` 生成链、
   `lib/` 版本化目录的演进关系、配置与脚本的配对），以及共同主题线（多份资料如何围绕主题分工协作）；
3. **层次呈现**：报告"联系与层次"小节输出——层级归属表（资料 | 层次 | 角色）、依赖链图
   （`A → B → C` 文本链）、分工说明；无直接联系时如实注明并列关系（同层协作）；
4. **重联系轻罗列**：每份资料既要单独解读（要点 + 参考源），又必须说明其与整体的位置关系，
   使多资料分析呈"织网"而非"堆砌"。

**代码-对象映射**（解析代码/脚本时必做）：

1. **识别对象**：先回答"这段代码在描述什么对象"——物理图像（如格点场、夸克传播子、Wilson 线、
   plaquette）、业务实体（配置项、任务、产物）或系统组件（模块、服务、数据流）；
2. **建立映射**：代码符号 ↔ 对象概念对照（如 `hopping 项 ↔ 夸克在相邻格点间跃迁`、
   `plaquette 变量 ↔ 最小格点环元`、`smeared 特征向量 ↔ 光滑化后的夸克场源`），映射关系记入
   终端摘要并在报告"对象映射"小节呈现为表格（代码符号 | 对象概念 | 物理/业务含义）；
3. **对象语言解释**：代码片段后附对象说明（如"该函数构造 $F_{\mu\nu}$ 场强张量，对应
   $\bar\psi\gamma^\mu D_\mu\psi$ 中的规范场"），用物理图像讲清"为什么这样做"再讲"怎么实现"；
4. **纯工程代码**：无明确物理/业务对象时，说明其工程角色（构建、部署、校验、统计），不强行造对象。

**后续 agent 交接索引（收尾必备）**：在报告摘要或结论前固定列出以下字段，作为无会话上下文
的后续 agent 的入口；字段内容必须与正文和实测证据一致：

| 字段 | 必须包含 |
|---|---|
| 任务与范围 | 一句话任务定义、分析边界、覆盖/未覆盖目录 |
| 结构与入口 | 层级职责、关键入口文件、主依赖/工作流链 |
| 证据与状态 | 关键 `文件:行号`、确证/推断/未验证标记 |
| 交接动作 | 可直接调用的下游技能（如 `pure`/`debug`/`test`/`report`）及其原因 |

**展示版式交接字段（存在 `report` 下游时必填）**：

| 字段 | 必须包含 |
|---|---|
| 视觉对象 | 证据 ID、主张、视觉类型（公式/表格/代码/流程/图）和来源 |
| 占用预算 | 宽度位置（行内/单列/整页）、高度等级（短/中/高）及行数/节点数/代码行数 |
| 拆分边界 | 不可拆单元、允许的语义分页点，以及下一页需重复的上下文 |
| 版式风险 | 长公式/路径/URL、表格列、TikZ 外框、彩色框或页脚冲突；对应的缓解动作 |

将上述交接内容整理为可被 `pure`/`report` 消费的 `content_payload`，每个密集对象至少使用同一组字段：
`content_id | claim_id | evidence_ids | visual_type | width_budget | height_budget | min_font_pt |
item_count | split_allowed | split_boundary | risks | mitigation`。其中 `item_count` 按对象记录公式行、表格行、代码行或 TikZ 节点数，
`width_budget` 必须说明行内/单列/整页及列间距约束，`risks` 要单列节点外框、路径标签、独立标签和箭头风险。

### Step 5. 生成 LaTeX 源文件（普通模式；`effective_format != Markdown`）

生成 `docs/analy_<slug>_<YYYYMMDD>.tex`，**必须遵循 `references/latex-template.md`**
（本技能目录下，唯一权威模板——形式规范/色板/防溢出/严谨规范全部以该文件为准）：

```bash
# 复制模板骨架后填充
# 模板路径: <本技能目录>/references/latex-template.md
```

**生成要点**：

1. **逻辑连贯**：全文一条主线——摘要（供后续 agent 快速读取的任务定义/范围/入口/状态）→ 概览（背景）→ 主体结构（骨架）→
   各部分关系（织网）→ 项目思路（灵魂）→ 主题分析（深入）→ 关键片段（证据）→ 参考清单 →
   结论（收束）；每节主题句先行、节末小结并自然引出下节；
   小节的划分按层次（整体→部分→细节），同一主题的内容不散落多节。
2. **三视角必齐**：主体结构/各部分关系/项目思路三节任何报告都不可缺（核心目的），
   每节必须有表格或框图支撑（层级表/依赖链/演进表）。
3. **层次分明**：标题按层级组织（section → subsection → subsubsection），每层只承担一个
   逻辑角色（背景/分析/证据/结论）；同层内容用统一句式与标识；多资料主题必含
   "联系与层次"子节（层级表 + 依赖链），代码主题必含"对象映射"子节（映射表）；
   主题为具体工作时，主题分析节必须按「分析思路框架」15 步组织（编号小节 A1..A15 或
   B1..B15），每步一小节、证据与参考源齐备——这是本技能内容密度与深度的主体。
4. **参考源格式**：正文引用统一用 `\texttt{\detokenize{bin/xxx.sh:12-18}}`，
   避免下划线/`#` 等字符逃逸问题。
5. **代码保真**：所有代码片段用 `\lstinputlisting[firstline=,lastline=]{绝对路径}`，
   其中 `firstline`/`lastline` 为实测行号；大片段整文件引用（省略 firstline/lastline）；
   每段 ≤40 行，长文件按关键段分多次引用（防页面溢出）。
6. **色彩与标识（全文档统一，语义唯一）**：基础五色 accent 深蓝（章节标题）/
   evidence 绿（仓库证据与参考源）/ reference 棕（参考背景框）/ conclusion 深红（结论框）/
   codebg 浅灰（代码底）；场景色 struct 靛蓝（主体结构）/ relation 青（各部分关系）/
   idea 砖红（项目思路）/ warn 橙红（未验证与局限）/ hl 浅黄底（要点框）；
   同一颜色在全文只表达同一类含义；色彩仅为增强可读性，去除后不影响信息完整。
7. **科研严谨**：结论分级标注（`确证`/`推断`/`未验证`）；统计数字后标来源；
   表格 caption 注明"数据来源: 实测"；公式编号 + `\eqref` 引用（若有）。
8. **防溢出与版式交接**：`grep -c Overfull` 与 `grep -c "Float too large"` 交付前必须均为 0——
   长表用 xltabular 跨页/X 列、图片限宽高
   （`width=0.9\textwidth,height=0.6\textheight,keepaspectratio`）、长词靠
   `\emergencystretch`+microtype、彩色框全部 breakable、公式用 align 分行；
   每个密集视觉同时登记视觉类型、宽高占用、拆分边界和风险；无警告时仍须渲染所有页面，
   高风险页面用 `\overfullrule=5pt` 诊断编译复核边界。全部措施与模板第 4 节一致，不自行删减。
9. **特殊字符**：正文中出现的 `$ % # & _ { }` 由 LaTeX 转义，路径与代码一律走
   `\detokenize` / `\lstinputlisting`，不做手工转写。
10. **表格数据**：参考源清单中的文件数、行号与 Step 4 实测一致，不臆造。
11. **参考资料声明**：报告"仓库概览"与"结论与局限"节中声明已引入的参考目录清单
    （如 `docs/(11 文件)`、`books/(无，未引入)`），命中主题的参考条目在"参考源清单"表中
    类型列标注"参考"，便于区分仓库证据与参考背景。
12. **图表与运行输出穷尽详览（大任务必备）**：每次大任务产生的全部图表与关键运行输出必须逐项落位——结果分析（A9/B9）中逐图逐项解读、综合分析中关联、附录中原始清单与 `\lstinputlisting` 片段；每项含来源、生成方式、数据含义、详尽解读与结论关联，配 `文件:行号` 参考源；以清单闭合为交付前提，缺一即返工。

### Step 6. 编译 PDF 到 docs/（普通模式；`effective_format != Markdown`）

```bash
cd docs
# 中文文档：在临时目录 xelatex 编译两遍，避免 aux/log 污染 docs/
tex_name="analy_<slug>_<YYYYMMDD>.tex"
pdf_stem="${tex_name%.tex}"
build_dir=$(mktemp -d)
render_dir=$(mktemp -d)
trap 'rm -rf "$build_dir" "$render_dir"' EXIT
compile_output="$(xelatex -interaction=nonstopmode -halt-on-error -file-line-error \
  -output-directory "$build_dir" "$tex_name" 2>&1 &&
  xelatex -interaction=nonstopmode -halt-on-error -file-line-error \
  -output-directory "$build_dir" "$tex_name" 2>&1)" || {
  printf '%s\n' "$compile_output"
  exit 1
}
pdf_file="$build_dir/$pdf_stem.pdf"
test -s "$pdf_file"
overfull_count=$(printf '%s\n' "$compile_output" | grep -c 'Overfull' || true)
float_count=$(printf '%s\n' "$compile_output" | grep -c 'Float too large' || true)
overfull_hbox=$(printf '%s\n' "$compile_output" | grep -c 'Overfull \\hbox' || true)
overfull_vbox=$(printf '%s\n' "$compile_output" | grep -c 'Overfull \\vbox' || true)
underfull_count=$(printf '%s\n' "$compile_output" | grep -c 'Underfull' || true)
printf 'Overfull=%s Float_too_large=%s overfull_hbox=%s overfull_vbox=%s underfull=%s\n' \
  "$overfull_count" "$float_count" "$overfull_hbox" "$overfull_vbox" "$underfull_count"
test "$overfull_count" -eq 0
test "$float_count" -eq 0
test "$overfull_hbox" -eq 0
test "$overfull_vbox" -eq 0
pdfinfo "$pdf_file" | rg 'Pages|Page size|File size'
pages_actual=$(pdfinfo "$pdf_file" | awk '$1 == "Pages:" {print $2}')
pdftoppm -png -r 100 "$pdf_file" "$render_dir/page" >/dev/null
rendered_pages=$(rg --files "$render_dir" | rg -c '/page-[0-9]+\.png$' || true)
printf 'pages_actual=%s pages_rendered=%s\n' "$pages_actual" "$rendered_pages"
test "$pages_actual" -eq "$rendered_pages"
# 全部页面人工检查通过后执行：记录 pages_expected=pages_actual=pages_rendered=pages_checked，再复制最终 PDF
cp "$pdf_file" "$pdf_stem.pdf"
# 纯英文可退化为 pdflatex，但仍须保留同样的临时目录、计数和全页检查
```

- 编译错误：依据终端 `file-line-error` 行号定位（宏错误/转义错误/缺宏包），修复后重编；
- 缺宏包（如 `ctex`）：先尝试 `tlmgr`/发行版包管理器安装；无法安装则改写模板避开该宏包；
- **Overfull > 0**：按 `references/latex-template.md` 第 4 节定位（优先缩减代码片段行数/
  表格列文本/公式换行），修复后重编直至为 0；
- **"Float too large" > 0**（图表溢出页面）：长表改 xltabular 跨页（table 环境不可跨页）、
  图片限宽高（`width=0.9\textwidth,height=0.6\textheight,keepaspectratio`），修复后重编直至为 0；
- 编译失败重试**循环进行**，每次失败原因在终端摘要中说明。

### Step 7. 验证普通模式产物（`effective_format != Markdown`）

```bash
ls -lh docs/analy_<slug>_<YYYYMMDD>.pdf        # 存在且非空
pdftotext docs/analy_<slug>_<YYYYMMDD>.pdf - | head -50   # 抽查文本内容（标题/结论/参考源出现）
```

- 用 `pdftoppm` 将 PDF 全部页面渲染到 `mktemp -d`，先逐页检查外框/页脚/表格/公式/代码块，
  再对有警告或高风险的页面提高分辨率复核；必要时在临时诊断编译中打开 `\overfullrule=5pt`，
  不把诊断标记版当作交付 PDF。重点检查“无警告但可见遮挡”的情况。
- PDF 页数、大小、抽检文本、页面边界与报告预期一致；命令已比较
  `pages_actual=pages_rendered`，人工检查后再记录
  `pages_expected=pages_actual=pages_rendered=pages_checked`，并给出
  `occlusion_pairs=0`、`clipped_objects=0`、`outside_safe_area=0` 的逐页证据；
- 验证失败（PDF 缺失/空白/乱码）→ 回到 Step 5/6 修复重编。

### Step 8. 总结（普通模式结构化输出）

```text
✓ 分析完成
  主题:   <解析出的任务定义>
  覆盖:   <调查的目录/文件范围，统计数字>
  参考:   <引入的参考知识库：docs(N 文件)/books(N 文件)/refer(N 文件)，未引入者注明>
  证据:   <参考源 N 处，其中代码片段 M 处（lstinputlisting 直引），参考背景 K 处>
  入口:   <关键入口/依赖链/后续 agent 可从何处继续>
  状态:   <确证/推断/未验证与未决问题>
  交接:   <推荐的下游技能及其依据>
  产物:   docs/analy_<slug>_<YYYYMMDD>.pdf (N 页, X KB, Overfull=0, Float_too_large=0, occlusion=0)
  源码:   docs/analy_<slug>_<YYYYMMDD>.tex
  结论:   <核心结论摘要>
  局限:   <未覆盖项/证据不足处，无则省略>

```

## 报告模板、示例与交付检查（普通模式）

普通模式生成 `.tex` 前先完整读取 `references/latex-template.md` 与 `references/report-guide.md`；前者是
唯一权威 LaTeX 模板，后者包含报告主线、色彩语义、防溢出规则、交付检查清单和典型示例。
参考文件采用渐进披露，不能只凭本节摘要跳过命名、证据、编译和 PDF 检查要求。

## 错误处理

| 场景 | 处理 |
|---|---|
| `effective_format` 缺失或不是明确值 | fast 上下文缺少有效格式时不猜测；补齐 `format_override/effective_format` 后再路由，无法补齐则标注“未验证”并停止格式相关交付 |
| Markdown 分支缺少必需章节/来源 | 回到 M3，补齐三视角、证据索引、`文件:行号` 和确证/推断/未验证状态；不以文件生成成功代替内容闭环 |
| Markdown 围栏/公式/链接校验失败 | 定位未闭合的 fenced code、`$...$`/`$$...$$` 或失效链接并修复；通过 M4 后才交付，不执行 PDF 版式替代检查 |
| 非 git 仓库 | `git rev-parse --is-inside-work-tree` 校验失败时报告；仍可按普通目录分析并注明 |
| 主题含糊 | **一次性列出候选**（全仓库概览 / 指定主题）提问确认，不逐次追问 |
| 覆盖表未闭合 | 聚焦前先补全"未分类"文件状态（精读/浏览/仅索引），不带着死角进主题分析 |
| 后续 agent 入口不完整 | 补齐任务/范围、结构/入口、证据/状态和交接动作四组字段；缺证据明确标注“未验证” |
| 视觉交接字段缺失 | 回到证据清单，为公式/表格/代码/流程补齐视觉类型、宽高占用、拆分边界和版式风险，不让 report 猜测 |
| TikZ 节点/标签相互遮挡 | 把节点、路径标签、独立标签和箭头分别计入包围盒；用 `above/below/left/right` 加显式安全间距，缩短或拆分标签，重新渲染核对，不以零 `Overfull` 作为通过依据 |
| 三视角证据不足 | 相应节如实呈现证据与推断级别，不强行填充；缺证据处标注 `未验证` 并列入局限 |
| 普通模式无 LaTeX 工具链 | 报告缺项；提供安装建议（`apt install texlive-xetex texlive-lang-chinese` 等），不静默跳过 |
| 缺 ctex/宏包 | 尝试安装；不可行则改用纯英文模板/替代方案并注明 |
| 缺 tcolorbox/titlesec | 尝试安装；不可行则退化——框用 `\textcolor`+粗体/斜体替代，标题不着色，其余模板不变并注明 |
| Overfull > 0 | 按 `references/latex-template.md` 第 4 节定位（缩减代码片段行数/表格列文本/公式换行）修复重编直至为 0 |
| "Float too large" 警告 | 表格/图片溢出页面：表格改 xltabular（table 环境不可跨页），图片限宽高（`width=0.9\textwidth,height=0.6\textheight,keepaspectratio`），修复重编直至警告为 0 |
| 警告为 0 但 PDF 仍遮挡/截断 | 用临时 `\overfullrule=5pt` 编译定位盒体，再逐页渲染；检查 TikZ 实际边界、`columns` 列宽+列间距、彩色框内边距和页脚保留区，按语义拆分或收窄局部对象 |
| `Underfull` 较多但无硬溢出 | 区分可接受的 `\raggedright`/短行与可见的大空白或断裂对齐；只修复影响阅读的页面，不用全局拉伸掩盖结构问题 |
| 主题无匹配证据 | 明确报告"未找到相关依据"，并附仓库结构概览供用户改题 |
| LaTeX 转义错误 | 正文特殊字符转义；代码/路径走 `\detokenize`/`\lstinputlisting` |
| 编译失败 | 依据终端错误定位行号并重编（循环尝试直至成功），失败原因在终端摘要中说明 |
| 路径含空格/中文 | `\lstinputlisting` 用绝对路径引号包裹；PDF 文件名用拼音 slug 规避 |
| 产物重名 | 追加序号（`_2`），不覆盖已有 PDF |
| docs/ 不存在 | `mkdir -p docs` 创建 |
| 参考目录不存在 | 静默跳过，覆盖范围/总结中注明（如"books/ 不存在，未引入"） |
| 参考文件不可解析 | 图片/二进制仅列文件名不参与检索，报告中注明 |
| 引用行号与实际不符 | 引用前用 read/grep 核实，绝不凭记忆写行号 |

## 注意事项

- 分析阶段对源代码只读；docs/ 下的 `.tex` 与 `.pdf` 仅作为交付产物，按公共 Git 契约检查，不自动提交或推送；
- 核心目的三视角（主体结构/各部分关系/项目思路）任何报告必齐，缺一即未完成；
- 饱和覆盖：覆盖登记表闭合后才进入主题聚焦，收尾时无"未分类"文件；
- 深度追问：每个结论至少一层 why（为什么这样设计），结论分级标注（确证/推断/未验证）；
- 所有结论、统计、行号必须实测，不编造证据；
- 代码片段用 `\lstinputlisting` 直引仓库原文件，保证 PDF 与仓库逐字节一致；
- 多资料分析重联系轻罗列：每份资料必须有角色定位与关系说明，报告含"联系与层次"呈现；
- 代码解析必做对象映射：先想"这段代码在描述什么对象/物理图像"，再讲"怎么实现"；
- 交给 `report` 的密集证据必须带视觉类型、宽高占用、拆分边界和风险；“编译成功/无警告”不替代逐页渲染检查；
- 报告用色规范统一（accent/evidence/reference/conclusion/codebg 五色 + struct/relation/idea/
  warn/hl 场景色），不引入额外颜色；新增颜色须同步更新 references 模板色板表；
- 交付前 `grep -c Overfull` 与 `grep -c "Float too large"` 均必须为 0
  （模板防溢出规则见 references/latex-template.md）；
