# analy 报告 LaTeX 规范模板（references）

本文件为 analy 技能生成 `.tex` 报告的**唯一权威模板**。SKILL.md 的「报告模板与生成要点」
只保留要点与引用指引，细节以本文件为准。生成报告时**复制本模板骨架**，按报告内容填充
（颜色、宏包、节结构均不可自行增删，保证全部 analy 报告形式规范统一）。

## 0. 编译与验证命令（每次必用）

```bash
cd docs
xelatex -interaction=nonstopmode -halt-on-error -file-line-error "analy_<slug>_<YYYYMMDD>.tex"
xelatex -interaction=nonstopmode -halt-on-error -file-line-error "analy_<slug>_<YYYYMMDD>.tex"
# 溢出检查：Overfull（行宽溢出）与 Float too large（图表溢出页面）计数均为 0 才交付
# （>0 按第 4 节定位修复后重编）
grep -c "Overfull" "analy_<slug>_<YYYYMMDD>.log"
grep -c "Float too large" "analy_<slug>_<YYYYMMDD>.log"
```

## 1. 模板骨架（复制即用）

```latex
% ============================================================
% analy 报告 — 规范模板 v2（xelatex + ctex）
% 用途: 仓库分析报告（主体结构 / 各部分关系 / 项目思路 / 主题分析）
% 编译: 见本文件第 0 节；交付前 Overfull 计数必须为 0
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
\usepackage{longtable}            % 长表自动跨页（参考源清单必用）
\usepackage{xltabular}            % 跨页+自动换行合体（longtable+tabularx，参考源清单用）
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
% —— analy 场景色（三视角 + 状态）——
\definecolor{struct}{HTML}{3B3B98}        % 主体结构(靛蓝): 架构分层/层级表
\definecolor{relation}{HTML}{0E7C7B}      % 各部分关系(青): 依赖链/关系表
\definecolor{idea}{HTML}{B03A2E}          % 项目思路(砖红): 设计意图/演进脉络
\definecolor{warn}{HTML}{D35400}          % 未验证/局限(橙红): 风险与缺口
\definecolor{hl}{HTML}{FDF6E3}            % 重点强调(浅黄底): 关键句底色

% ===== 全局防溢出设置 =====
\setlength{\emergencystretch}{3em}        % 长词/URL 断行缓冲
\hypersetup{colorlinks=true,linkcolor=accent,urlcolor=relation} % 链接着色

% ===== 层次分明的标题 =====
\titleformat{\section}{\Large\bfseries\color{accent}}{\thesection}{1em}{}
\titleformat{\subsection}{\large\bfseries\color{struct}}{\thesubsection}{1em}{}
\titleformat{\subsubsection}{\normalsize\bfseries\color{struct!70!black}}{\thesubsubsection}{1em}{}

% ===== 彩色标识框（均带 breakable 防跨页溢出）=====
\newtcolorbox{conclbox}{breakable,colback=conclusion!6,colframe=conclusion,title=结论}
\newtcolorbox{refbox}{breakable,colback=reference!6,colframe=reference,title=参考背景}
\newtcolorbox{ideabox}{breakable,colback=idea!6,colframe=idea,title=项目思路}
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
  stringstyle=\color{struct},
  breaklines=true,            % 长行自动断行
  breakatwhitespace=false,    % 任意位置断行（防超长 token 溢出）
  postbreak=\mbox{\textcolor{accent}{$\hookrightarrow$}\space}, % 断行箭头
  keepspaces=true,            % 断行保留缩进
  columns=flexible,           % 可变宽度字形，缓解等宽溢出
  numbers=left,numberstyle=\tiny\color{struct!60!black},
}

% ===== 正文元素样式约定 =====
% 1) 参考源: 路径 token 首选 \texttt{\nolinkurl{bin/xxx.sh:12-18}}（hyperref 提供，
%    允许在 . : / _ 后断行，X 列内不溢出——实测验证）；短 token（≤20 字符）可退化用
%    \texttt{\detokenize{...}}；证据绿可加强调 \textcolor{evidence}{...}
% 2) 结论分级: 确证=\textcolor{struct}{确证} / 推断=\textcolor{relation}{推断}
%    / 未验证=\textcolor{warn}{未验证}（科研严谨：不明说即默认确证，说则必须标）
% 3) 结构词: 主体结构相关用 \textcolor{struct}{...}，关系用 \textcolor{relation}{...}，
%    思路用 \textcolor{idea}{...}；避免在同一句内混用两级颜色
% 4) URL: 一律 \url{...} 包裹（hyperref），裸 URL 中 & % 等字符会报错（实测验证）

\title{<报告主题标题>}
\author{opencode analy}
\date{\today}

\begin{document}
\maketitle

\begin{abstract}
<摘要: 主题 / 分析范围(覆盖目录与文件数) / 核心结论 / 三视角概览(结构-关系-思路)>
\end{abstract}

\tableofcontents

% ================= 1 仓库概览 =================
\section{仓库概览}
\subsection{目录结构}
\lstinputlisting[language=bash]{<目录树文件或内联>}   % 结构树实测生成
\subsection{规模统计与 git 信息}
\begin{table}[htbp]\centering
\begin{tabular}{ll}
\toprule
指标 & 实测值 \\
\midrule
文档数 & <N> \\
代码文件数 & <N> \\
总行数 & <N> \\
提交数 & <N> \\
标签数 & <N> \\
\bottomrule
\end{tabular}
\caption{仓库实测统计（数据来源: find/wc/git 实测）}
\end{table}

% ================= 2 主体结构（核心目的一）=================
\section{主体结构}
<分层架构: 入口层/核心层/工具层/配置层/文档层/参考层，每层职责一句话>
% 注意: 一律用 xltabular（跨页）——table 环境不能跨页，表超一页会溢出页面底部
\begin{xltabular}{\textwidth}{llX}
\toprule
\textcolor{struct}{层次} & 目录 & \textcolor{struct}{职责} \\
\midrule
\endhead
入口层 & <路径> & <一句话> \\
核心层 & <路径> & <一句话> \\
\bottomrule
\caption{主体结构分层（数据来源: 全库索引实测）}
\end{xltabular}

% ================= 3 各部分关系（核心目的二）=================
\section{各部分关系}
<依赖链: A → B → C 文本链；引用/包含/生成/配置配对关系>
\begin{keybox}
\textbf{依赖主链:} \textcolor{relation}{env.sh → lib/_git_aliases.sh → lib/name-v{YYYYMMDD}/}
（各环节参考源附证据色标注）
\end{keybox}

% ================= 4 项目思路（核心目的三）=================
\section{项目思路}
\subsection{设计意图}
<为什么这样组织：可移植性/版本可追溯/防重复加载……每条附参考源>
\subsection{演进脉络}
<git 历史 → 结构变化的理由: 新增目录的原因、归档动机>
\subsection{典型工作流}
<一次典型任务如何走遍各部分（入口→配置→核心→产物）>
\begin{ideabox}
<项目思路核心总结：一句"这个仓库为什么长这样">
\end{ideabox}

% ================= 5 主题分析 =================
\section{主题分析}
% 分小节; 层次分明: 整体→部分→细节; 每结论附参考源与分级
\subsection{<子主题 1>}
% 主题句先行 → 分析 → 证据(\textcolor{evidence}{\texttt{\detokenize{...}}}) → 小结
% 多资料主题必含"联系与层次"子节（层级表/依赖链）; 代码主题必含"对象映射"子节（映射表）

% ---- 主题为"一项具体工作"时: 本节约占正文一半以上篇幅, 按 15 步框架组织 ----
% 先判定工作性质再选 A/B 框架（A 代码工作 / B 物理工作）; 编号小节齐全, 缺证据步骤标注
% \textcolor{warn}{未验证}或"无相关依据", 不跳过编号; 每步附参考源（evidence 绿）
\subsection{工作全流程重现（A 代码工作框架）}
% A1 目的与前期准备: 为什么做、前置条件/环境准备
% A2 输入: 数据/参数/配置/依赖（表或列表 + 参考源）
% A3 输出（应是什么）: 预期产物与结果形式
% A4 整体框架: 模块/文件组织、主流程（层级表或依赖链）
% A5 关键细节: 关键函数/算法/数据结构、易错点（\lstinputlisting 直引片段）
% A6 任务如何正确执行: 步骤/命令（\textcolor{evidence}{\texttt{\detokenize{...}}}）
% A7 实际执行情况: 实测命令与输出（记录于日志的实测结果）
% A8 实际输出情况: 实测产物清单与关键数值
% A9 结果分析: 结合生成的图表（\includegraphics 限宽高）、日志与其他文件逐项解读
% A10 综合分析: 与仓库整体联系、对象映射、深层原因
% A11 结尾总结: 结论框（conclbox）收束
% A12 结尾评价: 优缺点、可改进处
% A13 补充说明: 假设/局限/未覆盖项（warnbox）
% A14 参考源: 本步全部证据汇总（见第 7 节参考源清单）
% A15 附录与附件（如有）: 原始日志/配置/数据引用

% ---- B 物理工作框架（被分析对象为物理推导/理论/计算/实验）----
\subsection{工作全流程重现（B 物理工作框架）}
% B1 目的与前期准备
% B2 输入: 公理、定理、假设、假说、模型（逐项列出 + 参考源）
% B3 输出（应是什么）: 公式、定理、假说、理论预言、判断
% B4 整体推理框架: 推导/论证主线（推理链 A→B→C）
% B5 推导关键细节: 关键步骤、近似、边界条件（公式 \label/\eqref 编号）
% B6 任务如何正确执行: 推导/计算/实验的正确步骤
% B7 实际执行情况: 实测过程与记录
% B8 实际输出情况: 实测公式/数据结果
% B9 结果分析: 结合图表/日志/文件解读（含量纲检查与极限校验）
% B10 综合分析: 与物理图像/模型联系、自洽性
% B11 结尾总结: 结论框收束
% B12 结尾评价: 理论价值与局限
% B13 补充说明: 适用范围、未验证预言
% B14 参考源
% B15 附录与附件（如有）

% ================= 6 关键代码/文档片段 =================
\section{关键代码/文档片段}
% 一律 \lstinputlisting[firstline=,lastline=]{绝对路径} 直引原文件
% 每段 ≤40 行（防页面溢出）；长文件按关键段分多次引用
\lstinputlisting[firstline=10,lastline=25]{/绝对/路径/文件.sh}

% ================= 7 参考源清单 =================
\section{参考源清单}
% xltabular 跨页防溢出; X 列放"内容/作用"文本列
\begin{xltabular}{\textwidth}{llX}
\toprule
\textcolor{evidence}{参考源} & 类型 & 内容/作用 \\
\midrule
\endhead
\texttt{\nolinkurl{env.sh:1-30}} & 仓库 & <作用> \\
\texttt{\nolinkurl{books/xx.pdf:12}} & 参考 & <作用> \\
\bottomrule
\end{xltabular}

% ================= 8 结论与局限 =================
\section{结论与局限}
\begin{conclbox}
<核心结论汇总: 结构-关系-思路三视角各一句 + 主题结论>
\end{conclbox}
\begin{refbox}
<知识库/参考书的结论性旁证>
\end{refbox}
\begin{warnbox}
<未覆盖项/证据不足/未验证项——每个风险点标 \textcolor{warn}{未验证}>
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
| `struct` 靛蓝 | 主体结构 | 第二节标题元素、层级表头、结构词 |
| `relation` 青 | 各部分关系 | 依赖链、关系表头、关系词 |
| `idea` 砖红 | 项目思路 | ideabox、演进脉络、思路词 |
| `warn` 橙红 | 未验证/局限 | warnbox、未验证标注 |
| `hl` 浅黄底 | 重点强调 | keybox 底色 |

规则：同一颜色在全文只表达同一类含义；新增颜色必须写进本表与宏定义；
色彩仅增强可读性，去除后不影响信息完整。

## 3. 科研严谨规范

1. **数据分级**：每个统计数字后标来源（`\texttt{\detokenize{...}}`）；表格 caption 注明"数据来源: 实测"；
2. **结论分级**：确证（直接证据）/ 推断（由证据推出）/ 未验证（标注 `\textcolor{warn}{未验证}`），
   每句结论必须可归入一级；不确定时不写确证口吻；
3. **公式**：涉及公式一律 `\begin{equation}\label{eq:xxx}` + 正文 `\eqref{eq:xxx}` 引用，
   推导每步注明依据（定义/对称性/近似/量纲检查）；
4. **不编造**：无证据结论明确写"未找到相关依据"；行号引用前必须 read/grep 核实；
5. **局限性**：warnbox 必须如实列出未覆盖目录、未解析文件（图片/二进制）、推断性结论。

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
| 长路径 token | `\texttt{\detokenize{...}}` 无断点，超列宽即溢出（实测 97pt）——**路径 token 用 `\texttt{\nolinkurl{...}}`**（可在 `.:/_` 后断行，实测 X 列内无溢出）且**长 token（>20 字符）只能放 X 列**：l 列不换行，34 字符等宽 token 放 l 列实测溢出 10pt 量级；短路径可用 `\detokenize` | Overfull 计数 |
| 无空格畸形超长行 | 单个 token 超 120 字符且无空格时 listings 断行失效（实测：178 字符行溢出无法用参数消除）——**该行从引用范围剔除并在正文注明**（"第 N 行为 M 字符无空格赋值行，超出 listings 安全断行能力，略去；全文见 文件:N"），报告附注如实声明 | Overfull 计数 |

编译后必须运行 `grep -c "Overfull" <file>.log` 与 `grep -c "Float too large" <file>.log`：
**两个计数都为 0 才可交付**（Overfull=行宽溢出，Float too large=图表溢出页面，分开定位）；
>0 时按 `.log` 中 `file-line-error` 行号定位修复（Overfull 优先缩减代码片段行数/
表格列文本/公式换行；Float too large 优先检查表格跨页与图片宽高），修复后重编直至为 0。

## 5. 内容丰富度要求（逻辑通顺 + 内容充实）

1. **一条主线**：摘要（点题）→ 概览（背景）→ 主体结构（骨架）→ 各部分关系（织网）→
   项目思路（灵魂）→ 主题分析（深入）→ 关键片段（证据）→ 参考源清单 → 结论（收束）；
   每节主题句先行、节末小结并自然引出下节；
2. **三视角必齐**：结构/关系/思路三节任何报告都不可缺（核心目的）；
3. **具体工作必走 15 步框架**：主题为"一项具体工作"时，主题分析节按
   「分析思路框架」A（代码）/B（物理）15 步编号小节完整组织，每步至少
   **一段分析 + 一个证据（文件:行号/图表/日志）**，该节篇幅占正文一半以上；
   第 9 步（结果分析）必须实际查看生成的图表、日志与其他文件后撰写；
4. **每层都要有**：整体→部分→细节 逐层展开，不跳跃；
5. **表格密度**：统计表、层级表、关系表、映射表、参考源表齐全；每表 caption + 数据来源；
6. **语句过渡**：节间用过渡句衔接（"上一节回答了结构，这一节回答关系"），避免各节孤立；
7. **参考源密度**：参考源清单条数 ≥ 报告小节数，正文每节均有 evidence 绿参考源标注。
