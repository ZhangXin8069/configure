# report 横板 Beamer LaTeX 模板

本文件是 `report` 生成 `.tex` 的唯一形式模板。它继承 `analy`/`pure` 的证据、公式和溢出纪律，
但把 `ctexart` 竖版报告改为 16:9 `beamer` 幻灯片。先检查宏包，再复制骨架；不要把长报告的 `table`、
`figure`、目录和自动跨页机制直接搬到主体页。

## 0. 工具链检查与编译

中文优先使用 `xelatex`。模板首选 `ctexbeamer`；若它不存在但 `beamer.cls` 与 `ctex.sty` 都存在，
可改为 `beamer` + `\usepackage[UTF8]{ctex}`，仍必须保留 `aspectratio=169`。

```bash
command -v xelatex
kpsewhich ctexbeamer.cls || kpsewhich beamer.cls
kpsewhich tikz.sty
kpsewhich booktabs.sty
kpsewhich tabularx.sty
# 只有确认成功时才打开 pgfplots
kpsewhich pgfplots.sty
```

在 `docs/` 执行两遍编译并从内存中的输出检查警告：

```bash
compile_output="$(xelatex -interaction=nonstopmode -halt-on-error -file-line-error \
  "report_<slug>_<YYYYMMDD>.tex" 2>&1 && \
  xelatex -interaction=nonstopmode -halt-on-error -file-line-error \
  "report_<slug>_<YYYYMMDD>.tex" 2>&1)" || {
  printf '%s\n' "$compile_output"
  exit 1
}
printf '%s\n' "$compile_output"
overfull_count=$(printf '%s\n' "$compile_output" | grep -c 'Overfull' || true)
float_count=$(printf '%s\n' "$compile_output" | grep -c 'Float too large' || true)
printf 'Overfull=%s\nFloat too large=%s\n' "$overfull_count" "$float_count"
test "$overfull_count" -eq 0
test "$float_count" -eq 0
```

若 `pdftoppm` 可用，渲染少量页面做投影检查：

```bash
render_dir=$(mktemp -d)
trap 'rm -rf "$render_dir"' EXIT
pdftoppm -png -r 100 "report_<slug>_<YYYYMMDD>.pdf" "$render_dir/page" >/dev/null
# 检查首页、中间页、结尾页；检查结束后由 trap 清理
```

## 1. 可复制的模板骨架

```latex
% ============================================================
% report 组会汇报 — 16:9 Beamer 模板
% 编译: xelatex 两遍；交付前 Overfull=0, Float too large=0
% ============================================================
\documentclass[UTF8,aspectratio=169,11pt]{ctexbeamer}
% 若没有 ctexbeamer.cls，改用：
% \documentclass[aspectratio=169,11pt]{beamer}
% \usepackage[UTF8]{ctex}

\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{tabularx}
\usepackage{array}
\usepackage{tikz}
\usetikzlibrary{arrows.meta,positioning,calc,fit,shapes.geometric}
\usepackage{listings}
\usepackage{xcolor}
\usepackage{microtype}
\usepackage{hyperref}
% 确认 kpsewhich pgfplots.sty 成功后，才加入：
% \usepackage{pgfplots}
% \pgfplotsset{compat=1.18}

% ===== 色板：颜色只增强层次，不承载唯一信息 =====
\definecolor{primary}{HTML}{17365D}       % 主色：标题/主结论
\definecolor{accent}{HTML}{1F77B4}        % 强调：流程/关键对象
\definecolor{evidence}{HTML}{1E8449}      % 证据：来源/实测
\definecolor{warning}{HTML}{C55A11}       % 风险：未验证/阻塞
\definecolor{muted}{HTML}{5B6573}         % 辅助：来源/脚注
\definecolor{panel}{HTML}{F4F7FA}         % 面板底色
\definecolor{linegray}{HTML}{CBD5E1}      % 边界线
\definecolor{good}{HTML}{EAF5EE}           % 已完成/正向
\definecolor{warnbg}{HTML}{FFF4E8}         % 风险底色

% ===== 横板安全区与投影可读性 =====
\setbeamersize{text margin left=0.55cm,text margin right=0.55cm}
\setlength{\emergencystretch}{2em}
\setbeamertemplate{navigation symbols}{}
\setbeamertemplate{blocks}[rounded][shadow=false]
\setbeamercolor{normal text}{fg=black!86,bg=white}
\setbeamercolor{structure}{fg=primary}
\setbeamercolor{frametitle}{fg=primary,bg=white}
\setbeamercolor{block title}{fg=primary,bg=panel}
\setbeamercolor{block body}{fg=black!86,bg=panel}
\setbeamerfont{frametitle}{size=\large,series=\bfseries}
\setbeamerfont{normal text}{size=\normalsize}
\setbeamertemplate{frametitle}{%
  \vskip0.12cm\insertframetitle\par\vskip0.08cm}
\setbeamertemplate{footline}{%
  \hbox{\begin{beamercolorbox}[wd=\paperwidth,ht=2.3ex,dp=0.9ex,
    leftskip=0.55cm,rightskip=0.55cm]{author in head/foot}%
    \scriptsize\color{muted}\insertshortauthor\hfill
    \insertshorttitle\hfill\insertframenumber/\inserttotalframenumber
  \end{beamercolorbox}}

% ===== 来源与状态 =====
\newcommand{\source}[1]{%
  \vspace{0.06em}\par{\raggedright\scriptsize\color{muted}来源：#1\par}}
\newcommand{\verified}{\textcolor{evidence}{确证}}
\newcommand{\inferred}{\textcolor{accent}{推断}}
\newcommand{\unverified}{\textcolor{warning}{未验证}}

% ===== TikZ 流程/算法/框图样式 =====
\tikzset{
  flow/.style={draw=accent,fill=accent!8,rounded corners=2pt,align=center,
    minimum height=0.72cm,text width=2.35cm,font=\small},
  state/.style={draw=primary,fill=primary!7,rounded corners=2pt,align=center,
    minimum height=0.72cm,text width=2.55cm,font=\small},
  decision/.style={draw=warning,fill=warning!10,diamond,aspect=2,align=center,
    inner sep=1.5pt,font=\small},
  arrow/.style={-{Latex[length=2mm]},draw=primary,semithick},
  relation/.style={-{Latex[length=1.7mm]},draw=muted,thin,dashed}
}

% ===== 代码片段：短、直引、可断行 =====
\lstset{
  basicstyle=\ttfamily\scriptsize,
  backgroundcolor=\color{panel},frame=single,
  breaklines=true,breakatwhitespace=false,keepspaces=true,
  columns=flexible,firstnumber=auto,
  keywordstyle=\color{primary}\bfseries,
  commentstyle=\color{evidence!70!black},
  stringstyle=\color{accent},
  numbers=left,numberstyle=\tiny\color{muted}
}

\title[组会工作汇报]{<一句话汇报主题>}
\author[汇报人]{<姓名>}
\institute{<课题组/单位>}
\date{<日期>}

\begin{document}

% 标题页：只放题目、阶段和汇报人，不放大段背景
\begin{frame}[plain]
  \titlepage
\end{frame}

% 结论先行：三栏状态卡，内容必须来自证据清单
\begin{frame}[t]{<结论标题：本阶段最重要的判断>}
  \begin{columns}[T,totalwidth=\textwidth]
    \begin{column}{0.31\textwidth}
      \begin{block}{已完成}
        <可验收产物与状态>
      \end{block}
    \end{column}
    \begin{column}{0.31\textwidth}
      \begin{block}{关键证据}
        <指标、单位、基线与来源>
      \end{block}
    \end{column}
    \begin{column}{0.31\textwidth}
      \begin{block}{需要决策}
        <选项、风险或资源请求>
      \end{block}
    \end{column}
  \end{columns}
  \source{E1；完整来源见附录/参考页}
\end{frame}

% 流程图：主流程 4--7 个节点，细节另页
\begin{frame}[t]{<方法如何把输入变成可验证输出>}
  \centering
  \begin{tikzpicture}[node distance=0.48cm and 0.35cm]
    \node[flow] (input) {输入\\数据与假设};
    \node[flow,right=of input] (method) {方法/算法\\关键状态};
    \node[decision,right=of method] (check) {验证\\是否通过？};
    \node[flow,right=of check] (output) {输出\\指标与结论};
    \draw[arrow] (input) -- (method);
    \draw[arrow] (method) -- (check);
    \draw[arrow] (check) -- node[above,font=\scriptsize]{通过} (output);
    \draw[relation] (check.south) |- ++(0,-0.55) -| node[below,font=\scriptsize]{不通过：定位误差}
      (method.south);
  \end{tikzpicture}
  \vfill
  \source{来源：<文件:行号/实验命令>；图为结构示意}
\end{frame}

% 算法/伪代码图：输入、状态、停止条件和验证必须可见
\begin{frame}[t]{<算法标题：更新规则为何支持当前目标>}
  \begin{columns}[T,totalwidth=\textwidth]
    \begin{column}{0.58\textwidth}
      \centering
      \begin{tikzpicture}[node distance=0.34cm]
        \node[state] (a) {输入与约束};
        \node[state,below=of a] (b) {初始化状态 $S_0$};
        \node[state,below=of b] (c) {计算候选并更新 $S_k$};
        \node[decision,below=of c] (d) {满足停止\\判据？};
        \node[state,below=of d] (e) {输出并验证};
        \draw[arrow] (a) -- (b);
        \draw[arrow] (b) -- (c);
        \draw[arrow] (c) -- (d);
        \draw[arrow] (d) -- node[right,font=\scriptsize]{是} (e);
        \draw[relation] (d.west) |- ++(-0.6,0) |- node[left,font=\scriptsize]{否：继续迭代} (c.west);
      \end{tikzpicture}
    \end{column}
    \begin{column}{0.38\textwidth}
      \begin{block}{本页判断}
        <状态变量、停止判据、复杂度/误差对结论的影响>
      \end{block}
      \begin{block}{证据等级}
        \verified：<实测>；\inferred：<推断>；\unverified：<缺口>
      \end{block}
    \end{column}
  \end{columns}
  \source{实现：<文件:行号>；伪代码图是实现逻辑的抽象}
\end{frame}

% 表格/公式：解释性长句移到表外；公式分行并定义符号
\begin{frame}[t]{<结果标题：关键量相对基线发生了什么变化>}
  \begin{columns}[T,totalwidth=\textwidth]
    \begin{column}{0.53\textwidth}
      \small
      \begin{tabularx}{\linewidth}{@{}lccX@{}}
        \toprule
        指标 & 基线 & 当前 & 判断 \\
        \midrule
        $Q_1$ & <...> & <...> & <单位/方向> \\
        $Q_2$ & <...> & <...> & <单位/方向> \\
        \bottomrule
      \end{tabularx}
      \source{数据：<结果文件/命令>；表中数值均带单位}
    \end{column}
    \begin{column}{0.43\textwidth}
      \begin{equation}
        \label{eq:report-metric}
        \Delta Q = \frac{Q_{\rm new}-Q_{\rm base}}{Q_{\rm base}}.
      \end{equation}
      \begin{align}
        Q_{\rm new} &= <定义/测量式> \\
        \Delta Q &= <代入后的结果>.
      \end{align}
      <一句话解释符号、单位和基线。>
    \end{column}
  \end{columns}
\end{frame}

% 下一步：每一项都有可验收产物、日期和阻塞/请求
\begin{frame}[t]{<下一步标题：用什么实验消除当前最大不确定性>}
  \begin{center}
    \begin{tabularx}{0.96\textwidth}{@{}l l X l@{}}
      \toprule
      任务 & 截止 & 可验收产物/判据 & 请求/阻塞 \\
      \midrule
      <任务 A> & <日期> & <文件、指标或通过条件> & <无/选项> \\
      <任务 B> & <日期> & <文件、指标或通过条件> & <无/选项> \\
      \bottomrule
    \end{tabularx}
  \end{center}
  \source{计划来源：<会议决定/实验排期>；日期为可执行节点}
\end{frame}

\appendix
\begin{frame}[t]{附录：<完整参数/推导/代码证据>}
  % 主体未放下的细节手动拆分为独立 frame；不使用 allowframebreaks
  <附录内容>
  \source{<完整来源>}
\end{frame}

\end{document}
```

## 2. 布局安全规则

### 2.1 页面与字号

- `aspectratio=169` 是横板硬约束；不使用 `a4paper`、`ctexart` 或 `geometry` 把页面改成报告页。
- 正文使用模板默认字号或 `\small`；`\scriptsize` 只用于来源、代码编号和不承担主信息的脚注；主体不使用 `\tiny`。
- 左右文本安全边距为约 `0.55 cm`；列宽总和不超过 `0.96\textwidth`，列间距预留在预算中。
- 标题尽量一行，最长不超过两行；标题超过两行先压缩措辞，而不是减小标题字号。

### 2.2 图、表、公式和代码

- 主体不使用浮动 `figure`/`table`；直接在 `frame` 中放 `tikzpicture`、`tabularx`、公式和图片，保证位置稳定。
- 外部图片统一限制：
  `\includegraphics[width=0.96\linewidth,height=0.62\textheight,keepaspectratio]{...}`；在 columns 内使用当前 `\linewidth`。
- 表格优先 `tabularx` + `X` 列 + `booktabs`；移出长句、缩短字段，超出安全高度就按语义拆页，不整体缩放到不可读。
- 长公式用 `align`/`aligned` 分行；公式行内不要放未经定义的长路径、长文本或大段说明。
- 代码证据用 `\lstinputlisting[firstline=...,lastline=...]` 直引，主体每段建议不超过 12 行；代码之外的路径用 `\nolinkurl` 或 `\detokenize`。

### 2.3 分页与完整性

- 主体页禁止 `allowframebreaks`；Beamer 的自动拆页会破坏“结论—证据—含义”闭环。
- 不在表格行、公式等号链、流程箭头或伪代码循环中间断页。若必须多页，按完整语义分组，页标题明确 `(1/2)`、`(2/2)` 并重复列头/符号定义。
- 内容超载时按“删装饰 → 删重复 → 细节下沉附录 → 语义拆页 → 微调间距”顺序处理；不以缩小字体和删除来源为第一方案。

## 3. 来源、颜色和文本约定

- 颜色只表达层次：`primary` 标题/主结论，`accent` 关键对象/流程，`evidence` 来源/实测，`warning` 风险/未验证，`muted` 页脚。
- 每页至少有一个可追溯来源或明确的“示意”；实测结果页必须有数据文件/命令/配置来源。
- 正文结论按 `\verified`、`\inferred`、`\unverified` 标识；颜色去掉后，文字仍要能读出状态。
- `$ % # & _ { }` 等正文特殊字符正确转义；URL 用 `\url{}` 或 `\nolinkurl{}`，禁止裸 URL。

## 4. 编译后验收清单

- [ ] `xelatex` 两遍退出码为 0，交叉引用无未定义警告。
- [ ] 编译输出中 `Overfull` 次数为 0，`Float too large` 次数为 0；严重 `Underfull` 已人工处理。
- [ ] PDF 存在且非空；`pdfinfo` 页数与逐页 map 一致，主体页数没有因自动分页悄悄增加。
- [ ] `pdftotext` 能抽出标题、关键结论、下一步和来源；中文没有明显乱码。
- [ ] 首页、中间页、结果页、结尾页渲染后检查边界、图例、表格、公式、箭头和页脚是否遮挡。
- [ ] 所有主张均可回到证据清单；没有 `TODO`、`TBD`、`<待填>` 等占位符留在交付 PDF 中。
- [ ] 主体页中视觉表达占主导；无目录、背景、装饰或重复页等无决策价值内容。
