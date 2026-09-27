#!/usr/bin/env python3
"""
LaTeX Physics Report Generator — docker-v20260805
=================================================

Reads the analysis outputs (meff, ratios, OPE, timing) from a run directory
and produces ``physics_report.tex``, compiled to ``physics_report.pdf`` with
xelatex (two passes, Chinese ctex support).

Usage:
    python report.py --run-dir output/output_YYYYMMDD_HHMMSS
    python report.py --run-dir <dir> --out /root/PyQCD/logs
"""

from __future__ import annotations

import argparse, glob, json, os, subprocess, sys
from datetime import datetime
import numpy as np

from config import NT, NX, ALttc, FM2GEV, CONF_IDS

_CHANNELS = [('proton', 'P0'), ('proton', 'P2'), ('pion', 'P0'), ('pion', 'P2')]


def _fmt(v, e):
    """Format a value ± error, both in the report table."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return '—'
    if e is None or (isinstance(e, float) and np.isnan(e)):
        return f'{v:.3f}'
    return f'{v:.3f} ± {e:.3f}'


def _load_meff(an_dir):
    """Load all meff/corr analysis arrays into a dict."""
    d = {}
    for had, mom in _CHANNELS:
        key = f'{had}_{mom}'
        d[key] = {}
        for q in ('meff_mean', 'meff_err', 'corr_mean', 'corr_err'):
            f = os.path.join(an_dir, f'{q.replace("_", "_").replace("corr", "corr")}.npy')
        for base, q in [('meff', 'meff_mean'), ('meff', 'meff_err'),
                        ('corr', 'corr_mean'), ('corr', 'corr_err')]:
            f = os.path.join(an_dir, f'{base}_{had}_{mom}_{"mean" if "mean" in q else "err"}.npy')
            d[key][q] = np.load(f) if os.path.exists(f) else None
    return d


def build_tex(summary, run_dir, meff_vals, connected_ratio, disconn, conf_corrs):
    """Assemble the LaTeX document body from the analysis results."""
    conf_ids = summary.get('conf_ids', CONF_IDS)
    precision = summary.get('precision', 'complex64')
    nev1 = summary.get('nev1', 100)

    # ── meff table rows ──
    meff_rows = []
    for had, mom in _CHANNELS:
        key = f'{had}_{mom}'
        m = meff_vals.get(key, {})
        e0 = m.get('E0'); e0e = m.get('E0_err'); ee = m.get('E_exp')
        ps, pe = m.get('plateau', (0, 0)); npts = m.get('npts', 0)
        meff_rows.append(
            f"    {had} & $P={{{mom}}}$ & {_fmt(e0, e0e)} & {_fmt(ee, None)}"
            f" & $[{ps},{pe}]$ & {npts} \\\\")

    # ── connected ratio rows (R at mid-τ) ──
    ratio_rows = []
    for had, mom in _CHANNELS:
        key = f'{had}_{mom}'
        r = connected_ratio.get(key, {})
        R = r.get('R'); Re = r.get('R_err')
        if R is not None:
            t_mid = min(len(R) - 1, 4)
            ratio_rows.append(
                f"    {had} & $P={{{mom}}}$ & ${R[t_mid]:+.4f} \\pm {Re[t_mid]:.4f}$ \\\\")

    # ── disconnected fit rows (proton, Pz=2, a few z) ──
    disc_rows = []
    disc = disconn.get('proton') if isinstance(disconn, dict) else None
    if disc:
        c0, c1, dE = disc['c0'], disc['c1'], disc['dE']
        chi2 = disc['chi2']
        for z in [0, 4, 8, 12, 16, 20]:
            def s(arr):
                return f"{arr[:, z].mean():.3f}"
            disc_rows.append(
                f"    {z} & ${s(c0)}$ & ${s(c1)}$ & ${s(dE)}$ & ${chi2[:, z].mean():.2g}$ \\\\")

    timing = summary.get('timing_s', {})
    timing_rows = "\n".join(
        f"    {step} & {t:.1f} s \\\\" for step, t in sorted(timing.items()))

    # ── per-config C(0) consistency table ──
    cfg_rows = []
    if conf_corrs:
        for had, mom in _CHANNELS:
            vals = []
            for cid in conf_ids:
                c = conf_corrs.get(cid, {}).get(f'corr_pp' if had == 'proton' else 'corr_pi')
                if c is not None and mom in c and len(c[mom]):
                    vals.append(c[mom][0])
            if vals:
                mean, std = np.mean(vals), np.std(vals)
                cfg_rows.append(
                    f"    {had} P{mom} & {mean:.4e} & {std/abs(mean)*100:.1f}\\% \\\\")

    tex = r"""% ===========================================================================
%  格点QCD GPU蒸馏计算管线 — 物理分析报告 (docker-v20260805)
%  Physical Analysis Report — docker-v20260805
% ===========================================================================
\documentclass[11pt,a4paper]{article}
\usepackage[UTF8]{ctex}
\setCJKmainfont{AR PL SungtiL GB}[BoldFont=AR PL UMing CN]
\setCJKsansfont{AR PL KaitiM GB}[BoldFont=AR PL UMing CN]
\setCJKmonofont{AR PL UMing CN}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{physics}
\usepackage{braket}
\usepackage{bm}
\usepackage[margin=2.5cm]{geometry}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage[colorlinks=true,linkcolor=blue,citecolor=blue,urlcolor=blue]{hyperref}
\usepackage{enumitem}
\usepackage{caption}
\usepackage{subcaption}
\usepackage{multirow}
\usepackage{array}

\newcommand{\gev}{\;\mathrm{GeV}}
\newcommand{\fm}{\;\mathrm{fm}}
\newcommand{\fmto}{\;\mathrm{fm}^{-1}}
\newcommand{\meff}{m_{\mathrm{eff}}}
\newcommand{\Nconf}{N_{\mathrm{conf}}}
\newcommand{\Nev}{N_{\mathrm{ev}}}
\newcommand{\Nt}{N_t}
\newcommand{\Nx}{N_x}
\newcommand{\tsep}{t_{\mathrm{sep}}}
\newcommand{\Ctwo}{C^{(2)}}
\newcommand{\Cthree}{C^{(3)}}
\newcommand{\Em}{E^{(0)}}
\newcommand{\pmom}{p_z}
\newcommand{\apm}{a^{-1}}
\newcommand{\jack}{\mathrm{JK}}
\newcommand{\gmu}{\gamma_\mu}

\title{\textbf{格点QCD GPU蒸馏计算管线物理分析报告}\\[0.3em]
       \large 顶点函数、Wick收缩、动态收缩与关联函数分析 (docker-v20260805)}
\author{张鑫\thanks{中国科学院近代物理研究所 (IMP, CAS)}}
\date{""" + datetime.now().strftime('%Y年%m月%d日') + r"""}

\begin{document}
\maketitle

\begin{abstract}
本报告基于格点QCD蒸馏(Distillation)框架，在GPU (CUDA) 上实现了完整的关联函数计算管线：
顶点函数($VdV$/$VVV$)、Wick收缩分析、动态收缩、以及两点($pp$/$pn$)、OPE、三点($PJN$)、
四点($PJNNJNp$)关联函数，并进行Jackknife/有效质量/三点比值($ratio_{3p}$)统计分析。
计算使用CLQCD合作组的规范组态
($\beta=6.20$, $24^3\times72$, $a\approx0.1053\;\fm$, $\apm\approx1.874\;\gev$)，
共 """ + str(len(conf_ids)) + r""" 个组态（""" + ', '.join(map(str, conf_ids)) + r"""），
计算精度 """ + precision + r"""。
\end{abstract}

\tableofcontents
\newpage

\section{引言}
LaMET (Large Momentum Effective Theory) 通过计算大动量下的准分布(quasi-distribution)
关联函数并做微扰匹配，得到光锥 parton 分布函数。胶子 PDF 涉及不相连(disconnected)图，
其中三点函数可分解为质子两点函数与胶子算符 (OPE) 两部分的乘积。本报告实现的
docker-v20260805 管线以 sush 的 lqcddb 蒸馏收缩框架为蓝本（照抄而不 import），
并参考 docker-v20260803 的集中式配置与 LaTeX 报告架构，扩展至完整的关联函数集。

\section{理论框架}
\subsection{格点系综参数}
\begin{table}[h]
\centering
\caption{格点系综参数 (表~\ref{tab:ensemble})}
\label{tab:ensemble}
\begin{tabular}{ll}
\toprule
参数 & 值 \\
\midrule
$\beta$ & 6.20 (Clover Wilson) \\
格点 & $24^3\times72$ \\
格距 $a$ & 0.1053 fm \\
逆格距 $\apm$ & $\approx 1.874$ GeV \\
本征矢数 $\Nev$ / $N_{\mathrm{ev,1}}$ & 100 / """ + str(nev1) + r""" \\
动量 & $P=(0,0,0)$, $P=(0,0,2)$ \\
组态数 $\Nconf$ & """ + str(len(conf_ids)) + r""" \\
精度 & """ + precision + r""" \\
\bottomrule
\end{tabular}
\end{table}

\subsection{蒸馏方法与顶点函数}
蒸馏 (distillation) 方法把夸克传播子投影到拉普拉斯算符的低模空间：
\[ \tau_{ij}(t_s,t_f) = v^\dagger_i(t_s)\, M^{-1}(t_s,t_f)\, v_j(t_f). \]
两点关联函数所需的顶点函数为
\begin{equation}
V^{VdV}_{mn}(\mathbf{p}) = \sum_{\mathbf{x}} e^{-i\mathbf{p}\cdot\mathbf{x}}\,
    v^\dagger_m(\mathbf{x})\, v_n(\mathbf{x}),
\label{eq:VdV}
\end{equation}
\begin{equation}
V^{VVV}_{m n l}(\mathbf{p}) = \sum_{\mathbf{x}} e^{-i\mathbf{p}\cdot\mathbf{x}}\,
    \varepsilon_{abc}\, v^a_m(\mathbf{x})\, v^b_n(\mathbf{x})\, v^c_l(\mathbf{x}),
\label{eq:VVV}
\end{equation}
其中 $VdV$ 用于介子，$VVV$ 用于重子（质子/中子）。

\subsection{两点关联函数与有效质量}
源平均后的两点函数为
\[ C(t) = \frac{1}{\Nt}\sum_{t_s} C(t_s,\, t_s + t). \]
有效质量的对数形式与双曲余弦形式为
\begin{equation}
\meff(t) = \ln\frac{C(t)}{C(t+1)}\cdot\frac{\hbar c}{a}, \qquad
\meff(t) = \operatorname{arccosh}\frac{C(t+2)+C(t)}{2C(t+1)}\cdot\frac{\hbar c}{a}.
\label{eq:meff}
\end{equation}

\subsection{三点/两点比值}
连通的三点函数 $C^{(3)}(\tau)$（质子-矢量流-核子）与两点函数 $C^{(2)}$ 的比值采用
lqcddb 的 $ratio_{3p}$ 公式，包含 $\sqrt{\cdots}$ 因子。不相连胶子比值则按
huangcl 的 code\_1.py 算法构造：
\begin{equation}
C^{(3)}(t, \tau, z) = C^{(2)}(t)\, O(z,\tau),
\qquad R(t,\tau,z) = \frac{C^{(3)} - C^{(2)}\braket{O}}{C^{(2)}},
\end{equation}
并对每个 $z$ 做关联拟合 $R(t,\tau) = c_0 + c_1 e^{-dE\,\tau} + c_1 e^{-dE\,(t-\tau)}$。

\section{计算方法 (GPU管线)}
管线步骤：
\begin{enumerate}
    \item 顶点函数：$VdV$/$VVV$（GPU，按时间片流式计算）
    \item Wick收缩分析 + 动态收缩（lqcddb 引擎，注册表 + einsum 计划缓存）
    \item 关联函数：2pt ($pp$/$pn$/pion)、OPE (胶子算符)、3pt ($PJN$)、4pt ($PJNNJNp$)
    \item 统计分析：Jackknife、有效质量、$ratio_{3p}$（code\_1.py 形式）
    \item 绘图与 LaTeX 报告
\end{enumerate}
全部中间结果与日志均保存（日志同时写入 \texttt{/root/PyQCD/logs}）。

\section{结果与分析}
\subsection{两点关联函数与有效质量}
表~\ref{tab:meff} 给出各道的有效质量（Jackknife，加权平台）。
\begin{table}[h]
\centering
\caption{有效质量 (加权平台) (表~\ref{tab:meff})}
\label{tab:meff}
\begin{tabular}{llccccl}
\toprule
粒子 & 动量 & $E_0$ [GeV] & 期望 [GeV] & 平台 & 点数 \\
\midrule
""" + '\n'.join(meff_rows) + r"""
\bottomrule
\end{tabular}
\end{table}

\subsection{三点/两点连通比值}
表~\ref{tab:ratio} 给出 $\gamma_3$（$z$方向）分量的比值 $R(\tau)$。
\begin{table}[h]
\centering
\caption{连通三点/两点比值 (表~\ref{tab:ratio})}
\label{tab:ratio}
\begin{tabular}{llc}
\toprule
粒子 & 动量 & $R(\tau{\approx}4)$ \\
\midrule
""" + '\n'.join(ratio_rows) + r"""
\bottomrule
\end{tabular}
\end{table}

\subsection{不相连胶子比值与拟合}
表~\ref{tab:disc} 给出质子 $P_z=2$ 道不相连比值按 code\_1.py 拟合的参数。
\begin{table}[h]
\centering
\caption{不相连比值拟合参数 $R=c_0+c_1e^{-dE\,\tau}+c_1e^{-dE\,(t-\tau)}$ (表~\ref{tab:disc})}
\label{tab:disc}
\begin{tabular}{lcccc}
\toprule
$z$ & $c_0$ & $c_1$ & $dE$ & $\chi^2/\mathrm{dof}$ \\
\midrule
""" + '\n'.join(disc_rows) + r"""
\bottomrule
\end{tabular}
\end{table}

\subsection{组态一致性}
表~\ref{tab:config} 给出各道 $C(0)$ 的组态间离散程度。
\begin{table}[h]
\centering
\caption{各道 $C(0)$ 组态一致性 (表~\ref{tab:config})}
\label{tab:config}
\begin{tabular}{lcc}
\toprule
道 & $\braket{C(0)}$ & 相对离散度 \\
\midrule
""" + '\n'.join(cfg_rows) + r"""
\bottomrule
\end{tabular}
\end{table}

\subsection{计算耗时}
\begin{table}[h]
\centering
\caption{分步耗时 (表~\ref{tab:timing})}
\label{tab:timing}
\begin{tabular}{lr}
\toprule
步骤 & 耗时 \\
\midrule
""" + timing_rows + r"""
\bottomrule
\end{tabular}
\end{table}

\section{讨论与展望}
当前运行使用单精度 (complex64)、$\Nev=100$、$\Nconf=""" + str(len(conf_ids)) + r"""$。
$pn$（质子-中子）两点函数因味守恒而恒为零（质子 $uud$ 与中子 $udd$ 味结构不同），
这与理论预期一致。动量 $P=(0,0,2)$ 对应物理动量
$p_z = \frac{2\pi\cdot 2}{24\,a}\approx 0.981\;\gev$。后续工作可增加本征矢数目、
组态数目、动量涂抹、多源与 GEVP 以改善激发态污染。

\section{结论}
\begin{enumerate}
    \item 完整实现了从顶点函数到四点关联函数的 GPU 蒸馏管线。
    \item 两点函数与有效质量分析通过 Jackknife 获得统计误差。
    \item 三点 ($PJN$) 与四点 ($PJNNJNp$) 关联函数及比值分析完成。
    \item OPE 胶子算符按 donghx 算法计算并与两点函数组合成不相连比值。
\end{enumerate}

\begin{thebibliography}{9}
\bibitem{zhang2019} J.-H. Zhang et al., PRL 122, 142001 (2019).
\bibitem{fan2021} Z. Fan et al., PRD 104, 074502 (2021).
\bibitem{ji2013} X. Ji, PRL 110, 262002 (2013).
\bibitem{peardon2009} M. Peardon et al., PRD 80, 054506 (2009).
\end{thebibliography}

\end{document}
"""
    return tex


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run-dir', required=True)
    p.add_argument('--out', default=None, help='output directory for the PDF')
    args = p.parse_args()

    run_dir = args.run_dir
    an_dir = os.path.join(run_dir, 'data', 'analysis')
    summary_path = os.path.join(run_dir, 'analysis_summary.json')
    if not os.path.exists(summary_path):
        print(f"analysis_summary.json not found in {run_dir}")
        return 1
    with open(summary_path) as f:
        summary = json.load(f)

    # meff plateau values are stored in the summary; re-load arrays for the tables
    meff_vals = {f'{had}_{mom}': {
        'E0': summary['meff'].get(f'{had}_{mom}', {}).get('E0'),
        'E0_err': summary['meff'].get(f'{had}_{mom}', {}).get('E0_err'),
        'E_exp': summary['meff'].get(f'{had}_{mom}', {}).get('E_exp'),
        'plateau': summary['meff'].get(f'{had}_{mom}', {}).get('plateau'),
        'npts': summary['meff'].get(f'{had}_{mom}', {}).get('npts'),
    } for had, mom in _CHANNELS}

    # connected ratios
    connected_ratio = {}
    for had, mom in _CHANNELS:
        fm = os.path.join(an_dir, f'ratio_{had}_{mom}_mean.npy')
        fe = os.path.join(an_dir, f'ratio_{had}_{mom}_err.npy')
        if os.path.exists(fm):
            connected_ratio[f'{had}_{mom}'] = {'R': np.load(fm),
                                               'R_err': np.load(fe)}

    # disconnected fits (proton Pz=2)
    disconn = {}
    disc_dir = os.path.join(run_dir, 'analysis', 'disconnected')
    fp = os.path.join(disc_dir, '0_fit_data.npz')
    if os.path.exists(fp):
        d = np.load(fp)
        disconn['proton'] = {'c0': d['c0'], 'c1': d['c1'], 'dE': d['dE'],
                             'chi2': d['chi2']}

    # per-config C(0)
    conf_corrs = {}
    for cid in summary['conf_ids']:
        cdir = os.path.join(run_dir, 'data', f'conf{cid}')
        entry = {}
        for f in os.listdir(cdir) if os.path.isdir(cdir) else []:
            if f.startswith('corr_') and f.endswith('.npy'):
                key = f[5:-4]
                entry[key] = np.load(os.path.join(cdir, f))
        if entry:
            conf_corrs[cid] = entry

    tex = build_tex(summary, run_dir, meff_vals, connected_ratio,
                    disconn, conf_corrs)
    tex_path = os.path.join(run_dir, 'physics_report.tex')
    with open(tex_path, 'w') as f:
        f.write(tex)
    print(f"Wrote {tex_path}")

    # Compile with xelatex (two passes)
    for i in range(2):
        subprocess.run(['xelatex', '-interaction=nonstopmode',
                        '-halt-on-error', 'physics_report.tex'],
                       cwd=run_dir, capture_output=True)
    pdf = os.path.join(run_dir, 'physics_report.pdf')
    if not os.path.exists(pdf):
        print("WARNING: PDF not produced — check xelatex output")
        return 1
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        dst = os.path.join(args.out, 'docker-v20260805_physics_report.pdf')
        subprocess.run(['cp', pdf, dst])
        print(f"PDF copied to {dst}")
    print(f"PDF: {pdf}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
