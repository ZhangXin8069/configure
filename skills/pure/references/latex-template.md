# pure 报告 LaTeX 规范模板（references）

本文件为 pure 技能生成 `.tex` 报告的**唯一权威模板**，与 analy 模板**形式完全一致**
（同一 documentclass/宏包序/防溢出机制/严谨规范），仅**场景色板与报告骨架**按 pure 定位
（穷尽核心部分：算法/物理图像/代码-物理映射）调整。SKILL.md 只保留要点与引用指引。

## 0. 编译与验证命令（每次必用）

```bash
cd docs
# 将两次编译的终端输出保存在内存变量中检查，不创建或读取技能过程记录文件
compile_output="$(xelatex -interaction=nonstopmode -halt-on-error -file-line-error "pure_<slug>_<YYYYMMDD>.tex" 2>&1 &&
  xelatex -interaction=nonstopmode -halt-on-error -file-line-error "pure_<slug>_<YYYYMMDD>.tex" 2>&1)" || {
  printf '%s\n' "$compile_output"
  exit 1
}
printf '%s\n' "$compile_output"
printf '%s\n' "$compile_output" | grep -c "Overfull"
printf '%s\n' "$compile_output" | grep -c "Float too large"
```

## 1. 模板骨架（复制即用）

```latex
% ============================================================
% pure 报告 — 规范模板 v2（xelatex + ctex）
% 用途: 穷尽剖析项目核心部分（算法 / 物理图像与公式 / 代码-物理映射）
% 编译: 见本文件第 0 节；交付前 Overfull 与 Float too large 计数必须为 0
% ============================================================
\documentclass[UTF8]{ctexart}
% 宏包顺序固定，不可调整（存在依赖：tcolorbox 依赖 xcolor 等）
\usepackage[margin=2.5cm]{geometry}
\usepackage{graphicx}             % 图片（必须限宽高，见防溢出第 4 节）
\usepackage{amsmath}              % 公式编号 \label/\eqref 交叉引用
\usepackage{microtype}            % 微排版，缓解长词/URL 溢出
\usepackage{listings}             % 代码直引 \lstinputlisting
\usepackage{xcolor}
\usepackage{booktabs}             % 表格粗线规范
\usepackage{longtable}            % 长表自动跨页（核心部分清单必用）
\usepackage{xltabular}            % 跨页+自动换行合体（longtable+tabularx，长表用）
\usepackage{tabularx}             % X 列自动换行（防表格溢出）
\usepackage{hyperref}             % 书签/链接（最后加载，避免与其它宏包冲突）
\usepackage{fancyhdr}             % 页眉页脚
\usepackage[most]{tcolorbox}      % most = 含 breakable（彩色框可跨页）
\usepackage{titlesec}             % 章节标题着色

% ===== 色板（语义化；全文档同一颜色只表达同一类含义）=====
% —— 基础五色（analy 与 pure 通用，同义）——
\definecolor{accent}{HTML}{1F4E79}        % 主色(深蓝): 章节标题/强调主色
\definecolor{evidence}{HTML}{1E8449}      % 仓库证据(绿): 参考源/证据句/代码注释
\definecolor{reference}{HTML}{8C6D1F}     % 参考背景(棕): 知识库/书籍旁证
\definecolor{conclusion}{HTML}{8B1A1A}    % 结论(深红): 结论框
\definecolor{codebg}{HTML}{F4F6F7}        % 代码块底色(浅灰)
% —— pure 场景色（三类核心 + 状态）——
\definecolor{algo}{HTML}{E67E22}          % 算法(橙): 核心算法/数据结构/复杂度
\definecolor{phys}{HTML}{6C3483}          % 物理(紫): 物理图像/公式/推导链
\definecolor{map}{HTML}{C2185B}           % 映射(玫红): 代码符号↔物理对象
\definecolor{warn}{HTML}{D35400}          % 未验证/局限(橙红): 风险与缺口
\definecolor{hl}{HTML}{FDF6E3}            % 重点强调(浅黄底): 关键句底色

% ===== 全局防溢出设置 =====
\setlength{\emergencystretch}{3em}        % 长词/URL 断行缓冲
\hypersetup{colorlinks=true,linkcolor=accent,urlcolor=phys} % 链接着色

% ===== 层次分明的标题 =====
\titleformat{\section}{\Large\bfseries\color{accent}}{\thesection}{1em}{}
\titleformat{\subsection}{\large\bfseries\color{phys}}{\thesubsection}{1em}{}
\titleformat{\subsubsection}{\normalsize\bfseries\color{phys!70!black}}{\thesubsubsection}{1em}{}

% ===== 彩色标识框（均带 breakable 防跨页溢出）=====
\newtcolorbox{conclbox}{breakable,colback=conclusion!6,colframe=conclusion,title=结论}
\newtcolorbox{refbox}{breakable,colback=reference!6,colframe=reference,title=参考背景}
\newtcolorbox{algobox}{breakable,colback=algo!6,colframe=algo,title=核心算法}
\newtcolorbox{physbox}{breakable,colback=phys!6,colframe=phys,title=物理图像}
\newtcolorbox{mapbox}{breakable,colback=map!6,colframe=map,title=代码-物理映射}
\newtcolorbox{warnbox}{breakable,colback=warn!6,colframe=warn,title=局限与风险}
\newtcolorbox{keybox}{breakable,colback=hl,colframe=accent,title=要点}

% ===== 代码样式（防溢出关键）=====
\lstset{
  basicstyle=\ttfamily\footnotesize,
  backgroundcolor=\color{codebg},
  frame=single,
  language=bash,              % 按实际内容调整（python/fortran/c++...）
  firstnumber=auto,
  keywordstyle=\color{accent}\bfseries,
  commentstyle=\color{evidence!70!black},
  stringstyle=\color{map},
  breaklines=true,            % 长行自动断行
  breakatwhitespace=false,    % 任意位置断行（防超长 token 溢出）
  postbreak=\mbox{\textcolor{accent}{$\hookrightarrow$}\space}, % 断行箭头
  keepspaces=true,            % 断行保留缩进
  columns=flexible,           % 可变宽度字形，缓解等宽溢出
  numbers=left,numberstyle=\tiny\color{phys!60!black},
}

% ===== 正文元素样式约定 =====
% 1) 参考源: 路径 token 首选 \texttt{\nolinkurl{bin/xxx.sh:12-18}}（hyperref 提供，
%    允许在 . : / _ 后断行，X 列内不溢出——实测验证）；短 token（≤20 字符）可退化用
%    \texttt{\detokenize{...}}；证据绿可加强调 \textcolor{evidence}{...}
% 2) 结论分级: 确证=\textcolor{accent}{确证} / 推断=\textcolor{phys}{推断}
%    / 未验证=\textcolor{warn}{未验证}（科研严谨：不明说即默认确证，说则必须标）
% 3) 场景词: 算法相关用 \textcolor{algo}{...}，物理用 \textcolor{phys}{...}，
%    映射用 \textcolor{map}{...}；避免在同一句内混用两级颜色
% 4) URL: 一律 \url{...} 包裹（hyperref），裸 URL 中 & % 等字符会报错（实测验证）

\title{<报告主题标题>}
\author{opencode pure}
\date{\today}

\begin{document}
\maketitle

\begin{abstract}
<摘要: 项目性质判定(纯代码/纯物理/交叉) / 核心部分总数与清单概览 / 最深剖析结论>
\end{abstract}

\tableofcontents

% ================= 1 项目定位与核心部分清单 =================
\section{项目定位与核心部分清单}
\subsection{项目性质判定}
% 判定依据: 代码/公式/映射内容占比（实测统计）→ 纯代码/纯物理/交叉
\begin{keybox}
\textbf{项目性质:} \textcolor{phys}{<纯代码 / 纯物理 / 代码-物理交叉>}（依据: <统计与证据>）
\end{keybox}
\subsection{核心部分总清单（穷尽枚举）}
% xltabular 跨页防溢出; 三态必须填满: 深挖/浅析/排除(附理由)，不留"未处理"
\begin{xltabular}{\textwidth}{lllX}
\toprule
\textcolor{algo}{编号} & 核心部分 & 处理态 & 独特性概述 \\
\midrule
\endhead
C1 & <部分名> & 深挖 & <一句话独特性> \\
C2 & <部分名> & 排除 & <排除理由> \\
\bottomrule
\end{xltabular}

% ================= 2 核心部分深度剖析 =================
\section{核心部分深度剖析}
% 每个"深挖"部分一节（subsection），按项目性质选用以下三类剖析框架：

\subsection{<核心部分 1>}
% —— 纯代码框架（15 步全流程重现: 目的与准备 → 输入/输出 → 整体框架 → 关键细节 →
%    正确执行 → 实际执行 → 实际输出 → 结果分析(图表/终端输出) → 综合分析 →
%    总结/评价/补充 → 参考源/附录；每步附参考源，缺证据标注未验证）——
% 算法原理(输入/输出/步骤) → 复杂度分析(时间/空间) → 正确性论证(不变量/边界) →
% 独特竞争力(与朴素实现/通用库的差异与优势量化)
\begin{algobox}
\textbf{核心算法:} <算法名与一句原理>；复杂度 <O(n log n) 等，实测或推导并注明>
\end{algobox}

% —— 纯物理框架（15 步全流程重现: 目的与准备 → 输入(公理/定理/假设/模型) →
%    输出(公式/定理/预言/判断) → 整体推理框架 → 推导关键细节 → 正确执行 →
%    实际执行 → 实际输出 → 结果分析(图表/终端输出) → 综合分析 → 总结/评价/补充 →
%    参考源/附录）——
% 物理图像(一句话图像+直观理解) → 模型设定(自由度/参数/几何/边界条件) →
% 公式推导链(方程编号 \label{eq:xxx}，每步注明依据: 定义/对称性/近似/量纲) →
% 极限与退化校验(极端参数下公式行为是否合理)
\begin{physbox}
\textbf{物理图像:} <一句话图像>；对应公式 \eqref{eq:<xxx>} 的直观含义
\end{physbox}
\begin{equation}\label{eq:<xxx>}
<核心公式>
\end{equation}

% —— 交叉框架 ——
% 代码-物理映射表(双向): 代码符号 | 物理对象 | 物理含义与参考源
%   注意: 长路径 token 只能放 X 列（nolinkurl 可断行）；l 列禁长 token（实测 34 字符
%   等宽 token 放 l 列会溢出 10pt 量级）
\begin{mapbox}
\textbf{映射原则:} 每个关键代码符号必有物理对象，双向可查，无孤儿符号
\end{mapbox}
\begin{xltabular}{\textwidth}{llX}
\toprule
\textcolor{map}{代码符号} & 物理对象 & 物理含义与参考源 \\
\midrule
\endhead
<符号> & <对象> & <物理含义>；\texttt{\nolinkurl{file:line}} \\
\bottomrule
\end{xltabular}
% 映射后逐符号解释: 代码段用 \lstinputlisting 直引，物理含义用对象语言讲清
% "为什么这样做"再讲"怎么实现"

% ================= 3 独特性与竞争力评估 =================
\section{独特性与竞争力评估}
% 逐项评估: 独特点 | 对比基准 | 优势证据(实测数据/推导结果) | 局限
% 一律用 xltabular 跨页（table 环境不可跨页，长表溢出页面底部）
\begin{xltabular}{\textwidth}{lXX}
\toprule
\textcolor{algo}{独特点} & 对比基准 & 优势与证据 \\
\midrule
\endhead
<独特点> & <基准> & <证据/数据> \\
\bottomrule
\caption{独特性评估（数据来源: 实测/推导）}
\end{xltabular}

% ================= 4 关键片段与公式 =================
\section{关键片段与公式}
% 代码片段一律 \lstinputlisting[firstline=,lastline=]{绝对路径} 直引（每段 ≤40 行）
\lstinputlisting[firstline=10,lastline=25]{/绝对/路径/文件.sh}
% 核心公式集中呈现（带编号与推导依据标注）

% ================= 5 本次大任务图表详览（必须穷尽，图表清单闭合） =================
\section{本次大任务图表详览}
% 本次大任务产生的全部图表必须在此集中清单并逐项详介；每项含来源与生成方式、数据含义、逐项解读、与核心结论关联、局限；置于结果分析中详述后本节集中原始图与清单
\begin{xltabular}{\textwidth}{llX}
\toprule
编号 & 图表文件/数据来源 & 详尽介绍（生成方式/含义/解读/关联） \\
\midrule
\endhead
F1 & \texttt{<基准数据表或命令输出>} & 头部开销等实测对比；来源与生成方式在正文说明；解读见第2节A9；关联：支撑核心竞争力结论 \\
\bottomrule
\caption{本次大任务图表清单（穷尽，数据来源：实测）}
\end{xltabular}
\begin{figure}[htbp]\centering
\includegraphics[width=0.9\textwidth,height=0.6\textheight,keepaspectratio]{<图表路径>}
\caption{<图表标题>（来源与生成方式详述）}
\end{figure}

% ================= 6 参考源清单 =================
\section{参考源清单}
\begin{xltabular}{\textwidth}{llX}
\toprule
\textcolor{evidence}{参考源} & 类型 & 内容/作用 \\
\midrule
\endhead
\texttt{\detokenize{src/xxx.py:12-40}} & 仓库 & <作用> \\
\bottomrule
\end{xltabular}

% ================= 7 结论 =================
\section{结论}
\begin{conclbox}
<穷尽剖析结论: 核心部分总数(N 深挖/M 浅析/K 排除) + 最强竞争力总结>
\end{conclbox}
\begin{warnbox}
<未验证/未覆盖的核心部分、排除项理由、推导中的近似与适用范围>
</warnbox>

\end{document}
```

## 2. 色彩使用规范（语义唯一，禁止混用）

| 颜色 | 含义（唯一） | 使用位置 |
|---|---|---|
| `accent` 深蓝 | 主色/章节标题 | section 标题、lstset 关键字、链接 |
| `evidence` 绿 | 仓库证据 | 参考源 `\detokenize`、代码注释 |
| `reference` 棕 | 参考背景 | refbox、知识库来源内容 |
| `conclusion` 深红 | 结论 | conclbox 框 |
| `codebg` 浅灰 | 代码底 | lstset 背景 |
| `algo` 橙 | 核心算法 | algobox、算法复杂度、算法词 |
| `phys` 紫 | 物理图像与公式 | physbox、公式、物理词、subsection 标题 |
| `map` 玫红 | 代码-物理映射 | mapbox、映射表、映射词 |
| `warn` 橙红 | 未验证/局限 | warnbox、未验证标注 |
| `hl` 浅黄底 | 重点强调 | keybox 底色 |

规则：同一颜色在全文只表达同一类含义；新增颜色必须写进本表与宏定义；
色彩仅增强可读性，去除后不影响信息完整。

## 3. 科研严谨规范

1. **数据分级**：每个统计数字后标来源（`\texttt{\detokenize{...}}`）；表格 caption 注明"数据来源: 实测"；
2. **结论分级**：确证（直接证据）/ 推断（由证据推出）/ 未验证（标注 `\textcolor{warn}{未验证}`），
   每句结论必须可归入一级；不确定时不写确证口吻；
3. **公式**：核心公式必须 `\begin{equation}\label{eq:xxx}` + 正文 `\eqref{eq:xxx}` 引用；
   推导每步注明依据（定义/对称性/近似/量纲检查/边界条件）；推导前后做**极限与退化校验**
   （极端参数下公式行为合理，如 $m\to 0$、$V\to\infty$、$L\to 0$）；
4. **不编造**：无证据结论明确写"未找到相关依据"；行号引用前必须 read/grep 核实；
   公式不可凭记忆转写——必须对照原文献/源码推导核验后写入；
5. **局限性**：warnbox 必须如实列出近似与适用范围（量纲与数量级说明）、排除项理由。

## 4. 防溢出规则清单（编译后逐一核对）

| 风险点 | 预防措施 | 验证 |
|---|---|---|
| 长代码行 | `breaklines=true` + `breakatwhitespace=false` + `postbreak` 箭头 | Overfull 计数 |
| 超长代码片段 | 每段 `\lstinputlisting` ≤40 行，长文件分多次引用 | 目测页边界 |
| 长表格 | 文本列用 `X` 列（tabularx）；跨页长表用 **`xltabular`**（实测验证：longtable 不支持 X 列会报错） | Overfull 计数 |
| 长词/URL | `\emergencystretch{3em}` + `microtype`；**URL 一律 `\url{...}` 包裹**（正文裸 URL 的 `&` 等字符会报错，实测验证） | Overfull 计数 |
| 彩色框跨页 | 全部 `breakable` | 目测分页处 |
| 超宽公式 | `align` 分行 + `&` 对齐，不写超长单行 | Overfull 计数 |
| 图片溢出页面 | 宽度统一 `\includegraphics[width=0.9\textwidth,height=0.6\textheight,keepaspectratio]`——宽高双重限制（长截图/大图高度同样受限），禁止裸 `\includegraphics{...}`；多图并排用 minipage | grep "Float too large" |
| 长表溢出页面底部 | `table` 环境**不可跨页**，表超一页即溢出页面（Float too large）——所有可能超一页的表一律用 `xltabular` 跨页（表头重复用 `\endhead`，标题用 `\caption`），短表（≤8 行）才可留在 table 环境 | grep "Float too large" |
| X 列内行内公式 | 数学模式断点少，超长行内公式会溢出（实测 6.6pt）——**表格 X 列避免超长行内公式**；长公式移入正文 `equation` 编号，表内只放短符号或引用编号 | Overfull 计数 |
| 长路径 token | `\texttt{\detokenize{...}}` 无断点，超列宽即溢出（实测 97pt）——**路径 token 用 `\texttt{\nolinkurl{...}}`**（可在 `.:/_` 后断行，实测 X 列内无溢出）且**只能放 X 列**：l 列不换行，34 字符等宽 token 放 l 列实测溢出 10pt 量级；中文/短路径可用 `\detokenize` | Overfull 计数 |
| 无空格畸形超长行 | 单个 token 超 120 字符且无空格时 listings 断行失效（实测：178 字符行溢出无法用参数消除）——**该行从引用范围剔除并在正文注明**（"第 N 行为 M 字符无空格赋值行，超出 listings 安全断行能力，略去；全文见 文件:N"），报告附注如实声明 | Overfull 计数 |

编译后从内存中的终端输出统计 `Overfull` 与 `Float too large`：
**两个计数都为 0 才可交付**；出现警告时依据终端中的 `file-line-error` 行号定位修复
（Overfull 优先缩减代码片段行数/表格列文本/公式换行；Float too large 优先检查表格跨页与图片宽高），
修复后重编直至为 0。

## 5. 内容丰富度要求（逻辑通顺 + 内容充实）

1. **一条主线**：摘要（点题+性质判定）→ 项目定位与核心部分清单（穷尽枚举）→
   核心部分深度剖析（逐部分）→ 独特性评估（竞争力）→ 关键片段与公式（证据）→
   本次大任务图表详览（穷尽）→ 参考源清单 → 结论（收束）；每节主题句先行、节末小结并自然引出下节；
2. **穷尽性可见**：核心部分总清单三态（深挖/浅析/排除）必须填满，报告结尾重述
   "N 深挖 / M 浅析 / K 排除"，证明穷尽而非挑选；
3. **深挖部分必走 15 步框架**：每个"深挖"部分按 A（代码）/B（物理）15 步全流程重现
   （目的与准备/输入/输出/整体框架/关键细节/正确执行/实际执行/实际输出/
   结果分析（结合图表、终端输出、其他文件）/综合分析/总结/评价/补充/参考源/附录），
   每步至少一段分析 + 一个证据，缺证据步骤标注 `未验证` 不跳过编号；
4. **每层都要有**：每部分剖析遵循 原理→证据→独特点 三层，不跳跃；
5. **表格密度**：核心部分清单表、映射表、独特性评估表、参考源表齐全；
   纯物理报告公式密度高（推导链带编号），纯代码报告算法框图/复杂度表密度高；
6. **语句过渡**：节间用过渡句衔接，各核心部分剖析之间对照呼应（共同设计动机/递进关系）；
7. **参考源密度**：参考源清单条数 ≥ 深挖部分数 ×2，每个深挖部分至少 2 个证据。
