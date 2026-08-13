---
name: analy
description: |
  仓库分析技能：只读分析当前 git 仓库中的所有文档与代码，解析用户的输入（主题/问题），
  侧重讲明多份资料之间的联系与层次逻辑，解析代码时结合其对应对象（如格点代码与粒子物理图像），
  每个结论附精确参考源（文件:行号），生成逻辑连贯、层次分明、多色彩标识的 LaTeX/PDF 文档
  输出到当前工作目录的 docs/ 文件夹。
  当用户要求"分析"、"analy"、"解析"、"分析仓库"、"分析一下"、"解读这个仓库"、"生成分析报告"、
  "把分析做成PDF"、"输出分析文档" 时使用此技能；输入形式 `{~analy 用户输入}` 或 `{$用户输入}`，
  `{...}` 内为用户给定的分析主题/问题，技能将其解析为分析任务。
  只读分析、证据驱动、参考源可追溯；定位/修复 bug 用 debug 技能，性能优化用 optim 技能。
metadata:
  openclaw:
    emoji: 📊
---

# analy — 仓库分析 + LaTeX PDF 报告生成技能

对当前 git 仓库中的**全部文档与代码**进行只读分析，解析用户输入（`{$用户输入}`，即分析主题/问题），
以证据驱动的方式产出分析结论，**每个结论附参考源（`文件:行号`）**，最后用 LaTeX 生成 PDF 文档，
输出到**当前工作目录的 `docs/` 文件夹**。

## 核心原则

1. **只读分析**：分析阶段不改动仓库任何内容（不修改、不暂存、不提交、不删除）；
   唯一写操作是向 `docs/` 输出 `.tex` 源文件与编译产物 `.pdf`。
2. **解析用户输入**：把 `{$用户输入}` 解析为分析主题——提取问题焦点、限定范围与期望输出；
   输入为明确主题时直接执行；输入含糊（如"分析一下"无焦点）时**先提问**，不臆断主题。
3. **先全库调查，后主题聚焦**：先建立仓库全景（目录结构、git 历史、文档与代码索引），
   再按主题收敛到相关文件，避免遗漏关联证据。
4. **证据驱动，参考源可追溯**：每个分析结论必须对应真实存在的内容，附 `文件:行号` 参考源；
   代码片段**用 `\lstinputlisting[firstline,lastline]` 直接引用仓库原文件**，不做转写、不手抄，
   保证 PDF 中片段与仓库实际内容逐字节一致。
5. **诚实原则**：主题在仓库中找不到证据时明确报告"未找到相关依据"，绝不编造文件路径、代码或数据；
   分析范围受限（如只看了部分目录）时如实声明覆盖范围。
6. **量纲与边界校验**：统计数字（文件数、行数、commit 数）必须实测；空仓库、无 docs 目录、
   路径含空格/中文、LaTeX 特殊字符等边界情形逐一处理。
7. **编译闭环**：生成 `.tex` → 编译 → 验证 PDF 产物存在且内容正确；编译失败读 `.log` 定位修复，
   循环尝试直至成功或用户终止。
8. **默认引入参考知识库**：git 家目录（被分析仓库根）下的 `docs`、`books`、`refer` 等
   参考类目录视为参考知识库，**默认自动引入，不依赖主题**；存在即建全量索引并阅读说明类文件
   建立背景认知，主题聚焦时在其中检索相关内容并入证据链，使解析更全面深入（"解析越多越好"）；
   目录不存在或文件不可解析时静默跳过并在覆盖范围中如实注明；全程只读。
9. **多资料联系与层次逻辑**：分析涉及多份资料（文档/代码/配置/参考书）时，必须讲明各部分
   之间的联系——引用/依赖/包含关系、层级归属（入口层/核心层/工具层/文档层）与共同主题线，
   报告以"联系与层次"呈现，**重联系轻罗列**，避免资料堆砌。
10. **代码-对象对应**：解析代码时先识别代码所描述的对象（物理图像/业务实体/系统组件，
    如格点 QCD 代码对应粒子物理图像），建立"代码符号 ↔ 对象概念"映射，用对象语言解释
    代码行为与动机，再落到实现细节。

## 会话日志

每次 analy 会话必须在**当前工作目录（仓库根）**生成详细日志：

- 文件名格式：`.analy.<时间戳>.log`（例如 `.analy.2026-08-13-09-15-30.log`）
- 时间戳格式：`%Y-%m-%d-%H-%M-%S`：`TS=$(date +%Y-%m-%d-%H-%M-%S)`
- 日志**不入库**（与仓库 `.agent.*.log`、`.debug.*.log` 等约定一致），全程**追加**写入（`>>`）
- 记录内容（**会话头**）：
  1. 开始时间、工作目录、git 分支与 HEAD（`git rev-parse --abbrev-ref HEAD`、`git log -1 --oneline`）、
     解析出的分析主题（任务定义）；
- 记录内容（**过程**）：
  2. 全库调查命令与索引统计（命令、文件数/类型分布、退出码 `exit=N`）；
  3. 证据清单（逐条 `文件:行号` + 用途说明）；grep/read 定位命令与实际输出（过长截断并注明）；
  4. `.tex` 生成情况（节结构、引用片段数）；编译结果（成功/失败、失败原因与重试命令）；
- 记录内容（**会话尾**）：
  5. PDF 验证结果（大小、页数、抽检文本）；参考源总数；结束时间与总耗时；遗留项与下一步建议。

**记录规范**：关键事件以分隔行标记 `---- [YYYY-MM-DD HH:MM:SS] 事件描述 ----`；
命令统一记作 `$ <命令>` 并在结果行标注退出码；全程不覆盖、只追加。

## 历史日志预读（快速上手与对照参考）

会话**第一步**先只读预读本技能的历史会话日志，快速了解仓库状态、提供对照参考：

```bash
ls -1t .analy.*.log 2>/dev/null | head -3                 # 按时间倒序列出最近日志(优先较新, 最多3份)
tail -80 "$(ls -1t .analy.*.log 2>/dev/null | head -1)"   # 预读最新一份的尾部（结论区）
```

- 默认预读**最新一份**日志的尾部（上次主题、调查索引统计、编译结果、遗留项）；
  需更多对照时按时间倒序逐份追加读取，不一次全读
- 目的：① **快速上手**——从上次汇总直接掌握已分析主题与产物、仓库索引统计，新主题的
  全库调查基线直接沿用，避免重复扫描；② **对照参考**——上次编译失败原因与修复记录、
  证据清单供本次对照，防止重复踩坑
- 约束：**只读不改**历史日志；无历史日志（首次运行）时正常跳过，不视为错误
- 耗时控制：**优先较新日志**——默认仅预读最新一份的尾部汇总区（`tail -80` 上限）；日志过大时仍只取尾部并注明截断；需更多对照时按时间倒序逐份追加，单份有行数限额，预读总耗时以秒级为限，不逐份全文读取

## 触发时机

- 用户要求分析仓库："分析"、"analy"、"解析"、"分析一下"、"解读"、"总结仓库"
- 用户输入 `{~analy <用户输入>}` 或 `{$用户输入}`：`{...}` 内即分析主题/问题
- 用户要求生成分析文档："生成分析报告"、"输出 PDF"、"把分析写成文档"、"latex 输出"
- 与其他技能配合：tag 前评估仓库结构、diff 后解释改动意义、debug 前梳理代码依赖

## 输入解析规则

| 输入形式 | 解析方式 |
|---|---|
| `{$主题或问题}` | 直接作为分析主题；含问句时按问题展开分析 |
| `{~analy 主题}` | 同上，`analy` 之后的部分为主题 |
| 主题含糊（无焦点词） | 提问确认：分析整个仓库结构，还是针对某主题/文件/功能？ |
| 主题含范围限定 | 尊重限定（如"只看 bin/ 下的脚本"），并说明分析范围 |

主题解析后输出一句**任务定义**（如"分析主题：环境加载链 env.sh 的模块构成"）并记录到日志，
避免歧义。

## 输出命名约定

- 输出目录：**当前工作目录（被分析仓库根）下的 `docs/`**；不存在则创建
- PDF 文件名：`analy_<主题slug>_<YYYYMMDD>.pdf`（slug 用拼音/英文短词，不用中文字符；
  如 `analy_env_20260813.pdf`）
- `.tex` 源文件同目录同名：`analy_<主题slug>_<YYYYMMDD>.tex`
- 同日重复输出同一主题：文件名追加序号（`_2`、`_3`），不覆盖已有产物

## 工作流程

### Step 1. 解析用户输入（主题）

1. 从 `{$用户输入}` / `{~analy ...}` 提取主题，按「输入解析规则」确认任务定义；
2. 主题不明确时**向用户提问**，不擅自定义；
3. 记录任务定义到会话日志。

### Step 2. 环境准备

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

**参考知识库索引**（默认引入，不依赖主题）：

```bash
# 参考目录清单：git 家目录下 docs/books/refer/references 等，存在即引入，缺者跳过并注明
for d in docs books refer references; do
  [ -d "$d" ] && { echo "== $d =="; find "$d" -type f | sort; }
done
# 可检索文本规模统计（md/txt/tex 等可直接 grep；pdf 用 pdftotext 提取文本后检索）
find docs books refer references -type f \
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
grep -n "关键函数名\|关键变量" <文件>

# 参考知识库主题检索（命中文件纳入参考证据，读取相关段落）
grep -rni "主题关键词" docs/ books/ refer/ --include="*.md" --include="*.txt" \
  --include="*.tex" -l 2>/dev/null
# 参考书籍文本检索（pdf 先提取文本，仅检索不落盘）
for f in books/*.pdf; do pdftotext "$f" - 2>/dev/null | grep -ni "主题关键词" | head -5; done
```

1. **每个结论收集证据**：相关 `文件:行号`、代码段、文档段落；
2. **证据必须真实存在**：引用前用 read/grep 核实行号与实际内容；
3. **代码片段**：记录 `文件 + firstline + lastline`，后续用 `\lstinputlisting` 直接引用，
   **不复制转写**；
4. **关联追踪**：入口文件 → 被引用的模块 → 数据/配置，形成依赖链证据；
5. **参考知识库引入**：检索命中的参考文件用 read 读相关段落，作为背景资料/旁证
   纳入证据链；参考源清单中类型标注为"参考"；参考内容与仓库主题无关联时注明"未命中"，不强行引用；
6. 主题在仓库中无依据时：记录"未找到相关证据"，报告阶段如实说明。

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
   会话日志并在报告"对象映射"小节呈现为表格（代码符号 | 对象概念 | 物理/业务含义）；
3. **对象语言解释**：代码片段后附对象说明（如"该函数构造 $F_{\mu\nu}$ 场强张量，对应
   $\bar\psi\gamma^\mu D_\mu\psi$ 中的规范场"），用物理图像讲清"为什么这样做"再讲"怎么实现"；
4. **纯工程代码**：无明确物理/业务对象时，说明其工程角色（构建、部署、校验、统计），不强行造对象。

### Step 5. 生成 LaTeX 源文件

生成 `docs/analy_<slug>_<YYYYMMDD>.tex`，遵循以下模板结构：

```latex
% 中文文档（主题或内容含中文时）：xelatex + ctex
\documentclass[UTF8]{ctexart}
% 纯英文文档：可退化为 article + xelatex
\usepackage[margin=2.5cm]{geometry}
\usepackage{listings}
\usepackage{xcolor}
\usepackage{booktabs}
\usepackage{hyperref}
\usepackage{fancyhdr}
\usepackage[most]{tcolorbox}      % 结论/要点彩色框
\usepackage{titlesec}             % 章节标题着色

% ===== 色彩体系（全文档统一标识，见生成要点第 5 条）=====
\definecolor{accent}{HTML}{1F4E79}        % 主色（深蓝）：章节标题
\definecolor{evidence}{HTML}{1E8449}      % 仓库证据（绿）：参考源/证据句
\definecolor{reference}{HTML}{8C6D1F}     % 参考背景（棕）：知识库/书籍
\definecolor{conclusion}{HTML}{8B1A1A}    % 结论（深红）：要点框
\definecolor{codebg}{HTML}{F4F6F7}        % 代码块底色（浅灰）

% ===== 层次分明的标题：主色着色 =====
\titleformat{\section}{\Large\bfseries\color{accent}}{\thesection}{1em}{}
\titleformat{\subsection}{\large\bfseries\color{accent!70!black}}{\thesubsection}{1em}{}

% ===== 彩色标识框 =====
\newtcolorbox{conclbox}{colback=conclusion!6,colframe=conclusion,title=结论}
\newtcolorbox{refbox}{colback=reference!6,colframe=reference,title=参考背景}

\title{主题标题}
\author{opencode analy}
\date{\today}

\lstset{
  basicstyle=\ttfamily\footnotesize,
  backgroundcolor=\color{codebg},
  frame=single,
  breaklines=true,
  language=bash,   % 按实际内容调整
  firstnumber=auto,
  keywordstyle=\color{accent}\bfseries,
  commentstyle=\color{evidence!70!black},
}

\begin{document}
\maketitle
\begin{abstract}
  摘要：主题、分析范围（覆盖的目录/文件）、核心结论、资料联系概览（N 份资料，层次与主线）。
\end{abstract}

\tableofcontents

\section{仓库概览}
  % 结构树、git 信息、统计数字（全部实测）

\section{主题分析}
  % 分小节；层次分明：整体→部分→细节
  % 每小节主题句先行；每个结论后紧跟参考源 \texttt{\detokenize{file:line}}
  % 多资料主题：本节的"联系与层次"子节呈现层级表/依赖链
  % 代码主题：本节的"对象映射"子节呈现代码符号↔对象概念表格

\section{关键代码/文档片段}
  % 代码片段一律直接引用仓库原文件，保真展示：
  \lstinputlisting[firstline=10,lastline=25]{/绝对/路径/文件.sh}

\section{参考源清单}
  % booktabs 表格：文件:行号 | 类型 | 内容/作用

\section{结论与局限}
  % 结论框 \begin{conclbox}...\end{conclbox} 汇总
  % 引用知识库结论放入 \begin{refbox}...\end{refbox}
  % + 分析覆盖范围与未覆盖项

\end{document}
```

生成要点：

1. **逻辑连贯**：全文一条主线——摘要（点题）→ 概览（背景）→ 主题分析（分层展开）→ 关键片段
   （证据）→ 参考清单 → 结论（收束）；每节主题句先行、节末小结并自然引出下节；
   小节的划分按层次（整体→部分→细节），同一主题的内容不散落多节。
2. **层次分明**：标题按层级组织（section → subsection → subsubsection），每层只承担一个
   逻辑角色（背景/分析/证据/结论）；同层内容用统一句式与标识；多资料主题必含
   "联系与层次"子节（层级表 + 依赖链），代码主题必含"对象映射"子节（映射表）。
3. **参考源格式**：正文引用统一用 `\texttt{\detokenize{bin/xxx.sh:12-18}}`，
   避免下划线/`#` 等字符逃逸问题；
4. **代码保真**：所有代码片段用 `\lstinputlisting[firstline=,lastline=]{绝对路径}`，
   其中 `firstline`/`lastline` 为实测行号；大片段整文件引用（省略 firstline/lastline）；
5. **色彩与标识（全文档统一）**：
   - 章节标题：accent 深蓝（`titlesec` 着色）；
   - 结论要点：conclusion 深红 `conclbox` 框（仅"结论与局限"节用）；
   - 参考背景：reference 棕色 `refbox` 框（知识库/书籍来源的旁证）；
   - 仓库证据与参考源：evidence 绿色 `\textcolor{evidence}{...}`；
   - 代码块：codebg 浅灰底色，关键字 accent 蓝、注释 evidence 绿；
   - 表头（参考源清单）用 booktabs 粗线分隔，类型列"仓库/参考"分色标注；
   - 色彩仅为增强可读性，去除后不影响信息完整；不使用除上述 5 色外的额外颜色。
6. **特殊字符**：正文中出现的 `$ % # & _ { }` 由 LaTeX 转义，路径与代码一律走
   `\detokenize` / `\lstinputlisting`，不做手工转写；
7. **表格数据**：参考源清单中的文件数、行号与 Step 4 实测一致，不臆造。
8. **参考资料声明**：报告"仓库概览"与"结论与局限"节中声明已引入的参考目录清单
   （如 `docs/(11 文件)`、`books/(无，未引入)`），命中主题的参考条目在"参考源清单"表中
   类型列标注"参考"，便于区分仓库证据与参考背景。

### Step 6. 编译 PDF 到 docs/

```bash
cd docs
# 中文文档：xelatex 编译两遍（目录/引用正确解析）
xelatex -interaction=nonstopmode -halt-on-error -file-line-error "analy_<slug>_<YYYYMMDD>.tex"
xelatex -interaction=nonstopmode -halt-on-error -file-line-error "analy_<slug>_<YYYYMMDD>.tex"
# 纯英文可退化为 pdflatex（同参数）
```

- 编译错误：读 `.log` 中 `file-line-error` 给出的行号定位（宏错误/转义错误/缺宏包），修复后重编；
- 缺宏包（如 `ctex`）：先尝试 `tlmgr`/发行版包管理器安装；无法安装则改写模板避开该宏包；
- 编译失败重试**循环进行**，每次失败原因记入会话日志。

### Step 7. 验证产物

```bash
ls -lh docs/analy_<slug>_<YYYYMMDD>.pdf        # 存在且非空
pdftotext docs/analy_<slug>_<YYYYMMDD>.pdf - | head -50   # 抽查文本内容（标题/结论/参考源出现）
```

- PDF 页数、大小、抽检文本与报告预期一致；
- 验证失败（PDF 缺失/空白/乱码）→ 回到 Step 5/6 修复重编。

### Step 8. 总结（结构化输出）

```text
✓ 分析完成
  主题:   <解析出的任务定义>
  覆盖:   <调查的目录/文件范围，统计数字>
  参考:   <引入的参考知识库：docs(N 文件)/books(N 文件)/refer(N 文件)，未引入者注明>
  证据:   <参考源 N 处，其中代码片段 M 处（lstinputlisting 直引），参考背景 K 处>
  产物:   docs/analy_<slug>_<YYYYMMDD>.pdf (N 页, X KB)
  源码:   docs/analy_<slug>_<YYYYMMDD>.tex
  结论:   <核心结论摘要>
  局限:   <未覆盖项/证据不足处，无则省略>
  日志:   .analy.2026-08-13-09-15-30.log (编译重试 N 次)
```

## 错误处理

| 场景 | 处理 |
|---|---|
| 非 git 仓库 | `git rev-parse --is-inside-work-tree` 校验失败时报告；仍可按普通目录分析并注明 |
| 主题含糊 | 提问确认（全仓库概览 / 指定主题），不擅自定义 |
| 无 LaTeX 工具链 | 报告缺项；提供安装建议（`apt install texlive-xetex texlive-lang-chinese` 等），不静默跳过 |
| 缺 ctex/宏包 | 尝试安装；不可行则改用纯英文模板/替代方案并注明 |
| 缺 tcolorbox/titlesec | 尝试安装；不可行则退化——框用 `\textcolor`+粗体/斜体替代，标题不着色，其余模板不变并注明 |
| 主题无匹配证据 | 明确报告"未找到相关依据"，并附仓库结构概览供用户改题 |
| LaTeX 转义错误 | 正文特殊字符转义；代码/路径走 `\detokenize`/`\lstinputlisting` |
| 编译失败 | 读 `.log` 定位行号修复重编（循环尝试直至成功），失败原因记入日志 |
| 路径含空格/中文 | `\lstinputlisting` 用绝对路径引号包裹；PDF 文件名用拼音 slug 规避 |
| 产物重名 | 追加序号（`_2`），不覆盖已有 PDF |
| docs/ 不存在 | `mkdir -p docs` 创建 |
| 参考目录不存在 | 静默跳过，覆盖范围/总结中注明（如"books/ 不存在，未引入"） |
| 参考文件不可解析 | 图片/二进制仅列文件名不参与检索，报告中注明 |
| 引用行号与实际不符 | 引用前用 read/grep 核实，绝不凭记忆写行号 |

## 注意事项

- 分析全程只读：不改仓库文件、不暂存、不提交；唯一写操作是 docs/ 下的 `.tex` 与 `.pdf`；
- 所有结论、统计、行号必须实测，不编造证据；
- 代码片段用 `\lstinputlisting` 直引仓库原文件，保证 PDF 与仓库逐字节一致；
- 多资料分析重联系轻罗列：每份资料必须有角色定位与关系说明，报告含"联系与层次"呈现；
- 代码解析必做对象映射：先想"这段代码在描述什么对象/物理图像"，再讲"怎么实现"；
- 报告用色规范统一（accent/evidence/reference/conclusion/codebg 五色），不引入额外颜色；
- 涉及 git 跟踪内容时提示用户自行提交（不代提交）；
- 会话日志 `.analy.<时间戳>.log` 不入库，由用户决定保留或清理。
