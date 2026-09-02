---
name: report
description: |
  当用户要求制作面向学者、导师、同行或课题组的科研工作汇报、阶段性研究进展汇报、周报/月报幻灯片，
  或把科研代码、物理模型、实验数据、算法结果整理成高质量横板 PDF、Beamer 或 PPT 时使用；
  用户只说“给导师汇报”“给同行展示”“组会 PPT”“研究进展 slides”等，也应触发本技能；已有
  TeX/PDF 出现内容重叠、截断、列边界或页脚侵入等展示问题，需要调试/优化时同样触发。
metadata:
  openclaw:
    emoji: 📽️
---

# report — 面向学者的科研成果展示技能

## 执行前置

遵循当前目录 `AGENTS.md` 的「技能执行公共契约」；首步建立任务清单（TODO），按需读取本技能 reference，
验证后再声明完成。普通模式生成正文前完整读取 `references/report-guide.md`，生成 `.tex` 前完整读取
`references/latex-template.md`。普通模式的交付物是当前项目 `docs/` 下同名的横板 `.tex` 与 `.pdf`；
fast Markdown 模式按本文件的 Markdown 工作流交付 `.md`，不把 Markdown 当作未完成的提纲。

### fast_context 分支

收到 `fast_context.active=true` 且其 `effective_format=Markdown` 时，进入轻量 Markdown 分支；
`format_default` 仅是 fast 的默认元数据，不参与分支判断：
默认交付 `docs/report_<主题slug>_<YYYYMMDD>.md`，保留结论—证据—含义—下一步主线、来源行号和未验证项，
执行 Markdown 结构、公式分隔符、链接、表格和证据可追溯性检查；不执行下方普通模式的 LaTeX 生成、PDF 编译和
逐页版式验收步骤。用户明确指定 PDF/LaTeX/幻灯片时，按用户约束返回普通 LaTeX/PDF 分支。该分支选择是 fast
对本技能默认交付载体的明确覆盖。

本技能是分析链的**展示层**：优先消费 `analy` 的整体参考、`pure` 的细节参考和 `test` 的实测证据，
把它们转换为学者可独立阅读、可直接汇报、结论与来源一一对应的完整展示。它不重新承担 analy 的全库
建模或 pure 的逐符号深挖；材料缺口必须显式标为“未验证”，不能用排版掩盖证据不足。

这里的“完美展示”以四项可验收标准定义：受众能独立理解，主张能追溯到证据，视觉能突出判断；普通 PDF 还须无溢出/遮挡；
不以增加页数、装饰或缩小字号代替内容质量。页面布局在写 LaTeX 前先形成可复查的“版式账本”：每页主视觉、
宽高预算、不可拆单元、拆页边界和高风险对象均有记录。

## 核心原则

1. **学者判断优先**：每张主体页回答“本周/本阶段改变了什么、证据是什么、对研究意味着什么、受众需要判断或决定什么”；背景只保留支撑当前判断所必需的部分。
2. **一条主线**：从问题/假设出发，经方法与验证到结果、缺口、下一步；每张页只有一个主结论，页标题直接写结论而非泛化栏目名。
3. **视觉承载信息**：算法、公式推导、编程思路和其他工作流用统一的单列表格，跨模块关系用流程图或框图，比较用表格，定量关系用公式或图表；文字只负责解释视觉证据和做判断。
4. **完整叙事单元**：一张页应同时包含结论、关键证据和含义。内容放不下时按语义边界拆页并重复必要上下文，不能把同一表格、公式推导或流程节点任意截断。
5. **证据分级**：实测、由实测推出的判断、尚未验证的假设必须显式区分；数据、代码行为和结论均保留可追溯来源，不用漂亮的假数据填空。
6. **适度密度**：优先删掉装饰、重复背景和无决策价值的细节，再调整布局；正文保持可投影阅读，不能用极小字号掩盖结构失控。
7. **编译即验收**：普通模式的 16:9、页边安全区、图表尺寸和分页通过实际编译与 PDF 检查确认；`Overfull` 或 `Float too large` 非零时，不得宣称交付；fast Markdown 分支改做 Markdown 结构与证据闭环检查；普通模式警告为零仍需逐页渲染检查，因为 TikZ 外框、彩色框内距和列间侵入不一定触发 TeX 警告。
8. **结论落到行动并可复用**：结尾给出已完成、未解决风险、下一阶段可验收产物、时间节点和需要导师拍板/提供的资源，使缺席本次汇报的后续学者也能据此理解状态，避免以口号收尾。

## Git 检查

有 Git 且本次产生文件改动时，收尾执行 `git diff --check`，并定向复查 `report/`、相关 `docs/` 与
`AGENTS.md` 的 diff；不自动暂存、提交或推送。无 Git 或无本次改动时立即跳过。

## 工作流的统一 LaTeX 表达（普通模式）

凡是算法、伪代码、公式推导、编程思路、数据处理或验证过程等具有顺序、迭代或分支关系的内容，
统一采用“单列行”的内容形状；`analy`/`pure` 的文章报告可用 `table[htbp]`，Beamer 汇报稿必须在
`frame` 内直接放置 `tabular`/`tabularx`，不得用浮动 `table`/`figure`；流程图只补充跨模块关系。每行只写一个动作或
推导转移，`\quad`/`\quad\quad` 表示层级。算法按“输入→初始化→循环→分支/更新→收敛→输出”组织，
公式推导在每行写出等式或箭头并标注定义、对称性、近似、量纲或边界条件，编程思路按
“输入→状态/数据结构→核心处理→校验/错误分支→输出”组织。长流程按语义拆为多张固定 frame，不能用
整体缩放或极小字号掩盖溢出。

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

使用本技能的场景包括：

- “做一份给导师看的组会 PPT”“整理本周研究进展”“输出横板 PDF 幻灯片”；
- “给同行或学者展示研究成果”“做一份可直接汇报的科研 slides”“把阶段成果讲清楚”；
- 需要把代码实现、物理模型、实验/模拟结果、算法流程或阶段计划讲清楚并支持学者判断或导师决策；
- 已有长报告、笔记、日志或结果文件，需要压缩成信息密度适中的演示稿；
- 用户未说“PPT”，但明确目标是组会汇报、阶段汇报、周报/月报或向导师答辩式汇报。

与其他技能配合：

- 标准输入链为 `analy`（整体参考）→ `pure`（细节参考）→ `report`（学者展示）；缺少前置产物时只补充展示所需证据，不伪造继承关系；
- 需要仓库全景和依赖关系时先调用 `analy`；需要深挖核心算法、物理图像或代码—物理映射时调用 `pure`；
- 结果必须复现或含数值比较时调用 `test`，性能结论调用 `optim`，证据链异常调用 `debug`；
- 内容复杂且有多个独立证据域时可用 `dispatch` 并行收集，成稿后用 `review` 做早审查；
- 生成/修改完成后可用 `diff` 复查改动；本技能自身的创建或优化由 `skill-creator` 负责。

## 工作流程

### Step 1. 定义汇报任务与受众

1. 提取主题、汇报对象、日期/阶段、汇报时长、语言、已有材料、期望产物和受众需要判断的事项；普通模式缺少时采用“中文、16:9、10–15 分钟、8–12 张主体页、面向导师/同行研究者、附录承载细节”的默认值，
   Markdown 模式改用“中文、结论优先、无页数目标、面向导师/同行研究者”的默认值，并在终端说明。
2. 写出一句任务定义，例如“面向学者展示某算法本周进展，证明当前结果是否支持下一步实验，并提出一个资源请求”。
3. 确认本次汇报的**主问题、阶段目标、验收指标和当前状态**。不能从材料中找到的内容标为 `未验证`，不凭经验补齐。

### Markdown 工作流（仅 `fast_context.effective_format=Markdown`）

完成 Step 1 后，若 `fast_context.active=true` 且 `effective_format=Markdown`，只执行 M1–M5，
随后结束本技能；不得继续执行下方普通模式的 Step 2–Step 7。Markdown 分支保留结论—证据—含义—下一步主线、
受众决策信息、来源行号和未验证项，只移除与 PDF 版式相关的准备和验收。

#### M1. 最小环境与证据输入

确认/创建 `docs/`，回显 `fast_context.active`、`global_rounds_max`、`optimization_gain_stop`、
`quality_ratio_min`、`format_override` 和 `effective_format`；优先消费 `analy`、`pure` 和 `test` 的现有证据，
缺失时只补查支撑本次汇报的直接材料。此分支不读取 `references/latex-template.md`，不检查或调用
`xelatex`、`pdflatex`、`pdfinfo` 或 `pdftoppm`。

#### M2. 合并叙事编排与来源登记

建立精简的 `section_manifest`（`section_id | claim_id | evidence_ids | heading | audience_decision |
status | source | next_action`），按以下顺序组织且每节有来源或明确的“未验证”：

1. 结论摘要：本阶段改变、证据、当前判断；
2. 主问题与验收标准：假设、输入、成功判据和受众需要决定的事项；
3. 方法/工作流与关键设置：算法、公式、参数、设备、基线和可复现条件；
4. 关键结果与误差：数字、单位、比较对象、误差/不确定度和证据状态；
5. 风险、阶段结论、下一步与请求：影响、截止时间、阻塞项和决策选项；
6. 附加细节：只有能回答追问的公式、表格、代码或补充结果。

每个主张绑定真实的 `文件:行号`、命令或结果文件；公式使用 `$...$`/`$$...$$`，代码使用带语言标记的
fenced code block，表格使用 Markdown 表格，链接使用可点击相对路径。删除重复背景和装饰，但不得删除关键证据、
单位、基线、误差或未验证标识。

#### M3. 写入 Markdown 交付物

写入 `docs/report_<slug>_<YYYYMMDD>.md`（同名时追加 `_2`、`_3`，不覆盖已有产物），至少包含以下标题：

```text
# <结论式标题>
## 任务与受众
## 结论摘要
## 主问题与验收标准
## 方法、设置与证据
## 关键结果与误差
## 风险与未验证项
## 下一步与请求
## 来源与附录
```

标题应直接表达判断；每个关键数字、代码行为和结论在同节或来源表中绑定证据与状态，附录不能替代主体结论。

#### M4. Markdown 验证与交付闸门

```bash
md_file="docs/report_<slug>_<YYYYMMDD>.md"
test -s "$md_file"
rg -n '^# |^## (任务与受众|结论摘要|主问题与验收标准|方法、设置与证据|关键结果与误差|风险与未验证项|下一步与请求|来源与附录)' "$md_file"
fence_count=$(awk '/^```/{n++} END{print n+0}' "$md_file")
test $((fence_count % 2)) -eq 0
rg -n '[^[:space:]]+:[0-9]+(-[0-9]+)?' "$md_file"
```

另行检查 `$...$`/`$$...$$` 成对、Markdown 链接可解析、表格列闭合、每个主张均有
`确证/推断/未验证` 状态，且 `section_manifest` 与正文章节一一对应；只填写实际执行的 Markdown 验证，
不填写 PDF 页数、16:9、溢出、遮挡或逐页渲染指标。

#### M5. Markdown 总结

```text
✓ report Markdown 创建完成
   fast:   active=true；global_rounds_max=<...>；optimization_gain_stop=<...>；quality_ratio_min=<...>；effective_format=Markdown
   任务:   <一句任务定义>
   受众:   <学者/导师/同行/课题组；阶段/时长；需要作出的判断>
   产物:   docs/report_<slug>_<YYYYMMDD>.md
   内容:   <主问题、关键证据、结论、风险、下一步/请求>
   验证:   <章节、围栏、公式、链接、表格和来源可追溯性结果>
   局限:   <未验证数据或未完成项；无则省略>
```

### Step 2. 建立证据清单（普通 LaTeX/PDF 模式；`effective_format != Markdown`）

按用户限定范围优先读取 `analy` 整体参考、`pure` 细节参考和 `test` 实测结果，再补查相关文档、代码、实验输出、图表和日志；不为凑页数扫描无关目录。建立内部清单：

| ID | 要表达的主张 | 证据/来源 | 状态 | 适合的视觉 | 占用/拆分 |
|---|---|---|---|---|---|
| E1 | 一个可检验的结论 | 文件:行号、命令或结果文件 | 确证/推断/未验证 | 图/表/公式/流程 | 宽度、高度、拆分点 |

每个数字记录原始值、单位、计算方式、基线和来源；派生量注明公式。代码片段引用原文件的实测行号，
不要手抄后把转写当作证据。结果图必须能回答“比较了什么、基线是什么、误差/不确定度是什么”。
若输入来自 `analy`/`pure`，优先消费其 `content_payload`；缺少时为每个密集对象补齐统一字段
`content_id | claim_id | evidence_ids | visual_type | width_budget | height_budget | min_font_pt |
item_count | split_allowed | split_boundary | risks | mitigation`，不让页面布局依赖猜测。
其中 `risks` 必须明确区分节点外框、路径标签、独立标签、箭头、彩色框内距、列间距和页脚安全区。

### Step 3. 先做逐页结构，再写 LaTeX（普通模式）

根据已有参考、证据清单、时长和材料生成逐页 map；只做证据选择、叙事编排和视觉转译，不在 report 中重新发明 analy/pure 的分析结论。主体页按下列信息链取舍，不强行填满所有类型：

1. 标题页：题目、阶段、汇报人；
2. 结论先行：已完成、关键证据、当前判断、受众需判断或导师需决策事项；
3. 问题与验收标准：研究问题/假设、输入、成功判据；
4. 总体流程：输入 → 方法/算法 → 验证 → 输出，用 frame 内直接放置的单列工作流表格；跨模块关系再用流程图或框图补充；
5. 核心方法：用 frame 内直接放置的单列工作流表格承载算法、伪代码、物理模型或公式链；
6. 实验/计算设置：数据、参数、设备、基线和可复现条件，用表格；
7. 关键结果：图表或结果表，标题写出结论；
8. 验证、误差与未解决问题：对照、消融、边界情形、风险；
9. 阶段结论：主张—证据—置信度—影响；
10. 下一步与请求：任务、产物、截止时间、阻塞项和需要受众判断/导师拍板的选项；
11. 附录：只放回答追问所需的推导、完整参数、额外结果或代码证据。

把每页预先写成 `frame_manifest`：
`frame_id | claim_id | 主视觉 | evidence_ids | width_budget | height_budget | min_font_pt |
split_allowed | expected_page | risks`，并同时写“结论标题 / 一句含义 / 演讲补充”。删除不能服务于主问题、
证据、风险或下一步的页；不添加无意义目录页、泛泛背景页、装饰性大图或重复总结页。

### Step 4. 为主张选择视觉表达

主体页（标题页和纯行动页除外）至少约 80% 使用一个主视觉，按场景选择：

- **流程/工作流**：优先使用“工作流的统一 LaTeX 表达”中的单列行，在 Beamer `frame` 内直接放置 `tabular`/`tabularx`，逐行标明输入、处理、判断、更新、停止条件和输出；TikZ 只补充跨模块关系；
- **算法/伪代码**：使用同一单列表格写输入—初始化—循环/分支—停止条件—输出，并把关键状态和判据写进对应行；
- **模块/物理结构**：框图、层级图、代码符号—物理对象映射表；
- **比较/配置/误差**：`booktabs` + `tabularx` 表格，列只保留影响判断的字段；
- **定量关系**：编号公式、`aligned` 推导链、带单位的曲线/柱状图；公式旁给出符号定义和极限/误差解释；
- **计划/决策**：时间线、简化甘特图或分支决策图，节点对应可验收产物。

图形必须表达关系或证据，不能只是把文字换成彩色框。图、表、公式下方用一行 `来源：...` 或 `数据：...`，
需要追溯时写 `文件:行号`；无来源的示意图明确标注“示意”。

版式账本是实现前的硬闸门，不是编译后的补记：

- `columns` 的宽度预算按 `\sum_i w_i+(n-1)\columnsep\le0.96\linewidth` 计算，不能只看百分比之和；
- 每页高度预算要单独扣除 frametitle、来源行、footline 安全区和盒体内距；不以 `\vfill` 把超载推到页底；
- TikZ 要按节点外框、箭头和文字标签的实际包围盒估算，最右/最下对象必须留安全边距；彩色框在列内优先使用
  `wd\le0.98\linewidth` 或不显式指定宽度；表格文本列使用 `\raggedright\arraybackslash`；
- TikZ 的 `\node`、路径上的 `node{...}` 标签、独立文字标签和箭头都是独立包围盒；标签优先写成
  `node[above=<安全间距>,labelstyle]{...}`/`node[below=<安全间距>,labelstyle]{...}`，或用独立节点的
  `above/below/left/right` 定位，禁止把标签坐标压进节点外框或箭头端点；长标签必须设 `text width` 并换行；
- 主体正文/表格/主视觉不得用 `\tiny` 逃避布局；每页记录 `min_font_pt`，`\tiny` 只可出现在不承担主信息的图内标签，且仍须目测可读。

### Step 5. 生成横板 LaTeX/PDF（普通模式；`effective_format != Markdown`）

1. 完整读取 `references/latex-template.md`；按模板使用 `ctexbeamer`/`beamer` 的 `aspectratio=169`，不改成 portrait 文档。
2. 输出 `docs/report_<slug>_<YYYYMMDD>.tex` 和同名 `.pdf`；同日同主题已有文件时追加 `_2`、`_3`，不覆盖旧产物。
3. 使用标准 LaTeX 图表：工作流采用上面的单列行结构（Beamer 内不使用浮动 `table`），模块关系使用 TikZ 框图，比较使用 `tabularx`，定量关系使用 `amsmath` 公式；`pgfplots` 只有在 `kpsewhich pgfplots.sty` 检查通过后才启用，否则使用 TikZ 或已有矢量图。
4. 每页用 `frame` 固定布局，不使用 `allowframebreaks`；工作流单列 `tabular`/`tabularx`、长表、长公式和长流程按语义拆成独立页，页标题标明“1/2、2/2”，不截断一行表格或一段推导。
5. 代码证据用 `\lstinputlisting[firstline=...,lastline=...]` 直引，单段建议不超过 12 行；路径和来源使用 `\url`/`\nolinkurl` 或 `\detokenize`，正文特殊字符正确转义。

### Step 6. 编译、查溢出并目测 PDF（普通模式；`effective_format != Markdown`）

先检查工具链与可选宏包：

```bash
command -v xelatex
kpsewhich ctexbeamer.cls || kpsewhich beamer.cls
kpsewhich tikz.sty
kpsewhich booktabs.sty
kpsewhich tabularx.sty
```

在 `docs/` 中将两次编译输出放在内存变量；构建文件和渲染图放临时目录，不创建技能过程日志：

```bash
tex_name="report_<slug>_<YYYYMMDD>.tex"
pdf_stem="${tex_name%.tex}"
build_dir=$(mktemp -d)
render_dir=$(mktemp -d)
trap 'rm -rf "$build_dir" "$render_dir"' EXIT
compile_output="$(xelatex -interaction=nonstopmode -halt-on-error -file-line-error \
  -output-directory "$build_dir" "$tex_name" 2>&1 && \
  xelatex -interaction=nonstopmode -halt-on-error -file-line-error \
  -output-directory "$build_dir" "$tex_name" 2>&1)" || {
  printf '%s\n' "$compile_output"
  exit 1
}
pdf_file="$build_dir/$pdf_stem.pdf"
test -s "$pdf_file"
pages_actual=$(pdfinfo "$pdf_file" | awk '$1 == "Pages:" {print $2}')
overfull_count=$(printf '%s\n' "$compile_output" | grep -c 'Overfull' || true)
float_count=$(printf '%s\n' "$compile_output" | grep -c 'Float too large' || true)
underfull_count=$(printf '%s\n' "$compile_output" | grep -c 'Underfull' || true)
overfull_hbox=$(printf '%s\n' "$compile_output" | grep -c 'Overfull \\hbox' || true)
overfull_vbox=$(printf '%s\n' "$compile_output" | grep -c 'Overfull \\vbox' || true)
printf 'Overfull=%s Float_too_large=%s overfull_hbox=%s overfull_vbox=%s Underfull=%s\n' \
  "$overfull_count" "$float_count" "$overfull_hbox" "$overfull_vbox" "$underfull_count"
test "$overfull_count" -eq 0
test "$float_count" -eq 0
test "$overfull_hbox" -eq 0
test "$overfull_vbox" -eq 0
pdfinfo "$pdf_file" | rg 'Pages|Page size|File size'
pdftoppm -png -r 100 "$pdf_file" "$render_dir/page" >/dev/null
rendered_pages=$(rg --files "$render_dir" | rg -c '/page-[0-9]+\.png$' || true)
printf 'Rendered_pages=%s\n' "$rendered_pages"
printf 'pages_actual=%s pages_rendered=%s\n' "$pages_actual" "$rendered_pages"
test "$pages_actual" -eq "$rendered_pages"
# 全部渲染页经人工检查通过后，才写入 docs/ 的最终 PDF
cp "$pdf_file" "$pdf_stem.pdf"
```

`Overfull` 和 `Float too large` 必须均为 0；`Underfull` 只作诊断量，需判断它是否形成可见大空白或错位。
将 `frame_manifest` 的 `expected_page` 与 `pdfinfo` 的实际页数比较，并确认
`pages_expected=pages_actual=rendered_pages=pages_checked`；未逐页看完不能把 `pages_checked` 记为通过。
逐页检查页边安全区、列间、TikZ 节点/箭头、彩色框、公式、表格、代码和页脚，发现可疑页时在临时诊断
编译中加入 `\overfullrule=5pt` 定位盒体；同时记录 `occlusion_pairs=0`、`clipped_objects=0`、
`outside_safe_area=0`，三项只能在目测证据支持时填写为零。

### Step 7. 交付前闸门（普通模式）

- **内容**：主问题、阶段目标、关键方法、实测证据、当前结论、风险、下一步和受众请求均有归宿；没有无来源数字和空泛口号。
- **表达**：结论写在标题或首句；主体页以流程图、算法图、框图、表格、公式或图表为主，文字是辅助解释；图表标题能独立传达判断。
- **完整性**：一张页内叙事闭合，缺席本次汇报的学者也能理解上下文；长内容只在语义边界拆页；附录与主体之间有明确引用关系。
- **版式**：横向 16:9；`frame_manifest` 的页数与实际页数一致；正文不低于模板规定的可读字号；所有图表受宽高限制；
  `Overfull`、`Float too large`、`occlusion_pairs`、`clipped_objects` 和 `outside_safe_area` 均为 0；没有截断节点或页脚遮挡。
- **真实性**：逐项核对证据清单、数字单位、基线、代码行号和“确证/推断/未验证”标识；不把示意图当实测结果。
- **文件**：PDF 非空，页数合理，`pdftotext` 可提取主要文字，`.tex` 与 `.pdf` 同名；有 Git 改动时 `git diff --check` 通过。

## 错误处理

| 场景 | 处理 |
|---|---|
| `effective_format` 缺失或不是明确值 | fast 上下文缺少有效格式时不猜测；补齐 `format_override/effective_format` 后再路由，无法补齐则标注“未验证”并停止格式相关交付 |
| Markdown 分支缺少必需章节/来源 | 回到 M2–M3，补齐主线、`section_manifest`、来源行号和确证/推断/未验证状态；不以文件生成成功代替内容闭环 |
| Markdown 围栏/公式/链接/表格校验失败 | 定位未闭合的 fenced code、公式分隔符、失效链接或表格列并修复；通过 M4 后才交付，不执行 PDF 版式替代检查 |
| 材料不足或数据未测 | 不编造数据；把主张降为“未验证”，展示缺口、影响和补测计划；没有真实数据时不画结果曲线。 |
| 缺少 analy/pure 参考 | 记录缺失的前置参考，只补查支撑展示的直接证据；无法核实的整体或细节结论标为“未验证”，不把 report 变成隐性深度分析。 |
| 主题与受众不清 | 一次性列出所需的主题、时长、已有材料、输出格式和受众判断/导师决策项；可发现的信息先采用默认值并说明。 |
| 内容塞不进一页 | 先删装饰和重复说明，再按完整语义拆页；保留结论、证据、单位和来源，不靠 `\tiny` 或整体缩放解决。 |
| 表格过宽/过高 | 缩短单元格为关键词，移出解释性长句，改用 `tabularx` 或按列/主题拆页；不把关键字段挤到不可读。 |
| 流程图或算法图拥挤 | 减少非关键节点、把细节下沉到附录，保留输入/状态/判定/输出；必要时拆为“总览→关键步骤”两页。 |
| 公式溢出或推导过长 | 用 `aligned` 分行、另页给符号表和推导依据；不横向压缩公式，不删掉单位/极限校验。 |
| 编译无警告但出现遮挡/截断 | 用临时 `\overfullrule=5pt` 编译和逐页渲染定位；检查 TikZ 实际包围盒、列宽+`\columnsep`、彩色框内距、公式/代码盒及来源/页脚保留区，按语义拆分或收窄局部对象。 |
| TikZ 节点/标签相互遮挡 | 分别检查节点、路径标签、独立标签和箭头的包围盒；标签改用 `above/below/left/right` 加显式安全间距，长文字设 `text width` 换行，并以渲染结果复核 |
| `Underfull` 较多 | 区分 `\raggedright` 下可接受的短行与可见大空白/错位；只修复影响投影阅读的页面。 |
| `columns` 宽度超预算 | 计算 `\sum_i w_i+(n-1)\columnsep`；超出 `0.96\linewidth` 即回退重排，不能等 PDF 裁切后再猜。 |
| 页数或渲染检查不闭合 | 停止交付，补齐 `expected/actual/rendered/checked` 四项；只抽查首中尾页不能替代全页检查。 |
| 普通模式缺少 LaTeX 宏包 | 先用 `kpsewhich` 定位缺项；可替换时使用模板允许的标准方案，否则如实报告无法生成 PDF，不静默改成竖版。 |
| 编译失败或溢出警告 | 依据 `file-line-error` 定位；一次只改一个布局/转义假设，重新编译并记录新证据，直到通过或明确阻塞原因。 |
| 结果页缺基线或单位 | 暂停结论性措辞，补齐基线、单位、误差/样本数和来源；无法补齐则改为局限页。 |

## 注意事项

- 只为当前汇报问题保留内容；“相关但不影响判断”的资料放附录或删除。
- 流程图、算法图、表格、公式和框图优先承载信息，但不为满足形式强行添加不适用的图表。
- 普通模式主体页禁止自动分页；相对完整的模块必须作为完整 frame 交付，分页只能发生在明确的语义边界。
- Markdown 模式遵循 M3 的章节主线，不创建虚拟页数或版式指标；相对完整的证据单元按语义小节组织。
- 不修改用户源代码、不删除已有产物、不改变系统配置；不自动提交、推送或发布。
- 不把编译成功或零警告等同于版式成功：必须同时有警告计数、`frame_manifest` 页数核对、全页渲染和
  `occlusion_pairs/clipped_objects/outside_safe_area` 目测证据。

## 总结格式（普通模式）

```text
✓ report 创建完成
   任务:   <一句任务定义>
   受众:   <学者/导师/同行/课题组；时长；主体页数>
   产物:   docs/report_<slug>_<YYYYMMDD>.tex / .pdf
   内容:   <主问题、关键证据、结论、风险、下一步/请求>
   版式:   16:9；pages_expected=...=pages_checked；Overfull=0；Float too large=0；occlusion_pairs=0；clipped_objects=0；outside_safe_area=0
   验证:   <两遍编译、PDF 文本抽查、全页渲染目测、git diff --check>
   局限:   <未验证数据或未完成项；无则省略>
```

## 总结格式（fast Markdown 模式）

使用 M5 模板；至少回显 `effective_format=Markdown`、实际产物路径、主张—证据—状态闭环、Markdown
结构验证结果和未验证项，不填写 PDF 页数、16:9、溢出、遮挡或逐页渲染指标。
