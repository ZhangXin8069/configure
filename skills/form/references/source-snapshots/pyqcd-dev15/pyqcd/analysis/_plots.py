"""
通用图表工具（独立实现，功能对齐 refer/huangcl/98_tools/analysis_tools.py 图表全集）
====================================================================================

覆盖 98_tools 全部图表生成能力：

- `DEFAULT_PLOT_COLORS`：10 色默认配色（与 98_tools 一致）。
- `plot_errbar`：误差棒图（dict 输入，多组自动横坐标错开 x_offset，可选色带）。
- `plot_scatter`：散点图（dict 输入，可选 chi2/dof=1 水平参考线）。
- `plot_hist`：直方图（dict 输入，mean±sem 标注，统一横轴范围）。
- `plot_single_errbar` / `plot_single_chi2`：单组数据封装。
- `plot_multi_errbars` / `plot_multi_chi2` / `plot_multi_scatter`：多组对比封装。
- `get_peak_memory_gb`：进程峰值内存（GB）。

约定：matplotlib 函数内延迟导入并使用 Agg 后端（与 pyqcd 全库一致）；
所有画图函数返回保存路径，出错不吞异常。
"""
from __future__ import annotations

import os
import resource
from typing import Dict, List, Optional, Tuple

import numpy as np

# 默认画图配色（与 refer/huangcl/98_tools 一致）
DEFAULT_PLOT_COLORS = [
    "#4ba3e3",  # 1. 鲜亮浅蓝
    "#58b368",  # 2. 鲜亮草绿
    "#f29e38",  # 3. 暖橙
    "#a569bd",  # 4. 中紫
    "#2075bc",  # 5. 深蓝
    "#196f3d",  # 6. 深绿
    "#d9534f",  # 7. 砖红
    "#6c3483",  # 8. 暗紫
    "#21618c",  # 9. 藏青
    "#117864",  # 10. 深墨绿
]


def _backend():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _offsets(n: int, x_offset: float) -> np.ndarray:
    """多组数据横坐标左右对称错开。"""
    if n <= 1:
        return np.zeros(1)
    return np.linspace(-(n - 1) * x_offset / 2, (n - 1) * x_offset / 2, n)


def plot_errbar(
    x: np.ndarray,
    y_data: Dict[str, Tuple[np.ndarray, np.ndarray]],
    save_path: str,
    *,
    xlabel: str = "x",
    ylabel: str = "y",
    xlim: Optional[List[float]] = None,
    ylim: Optional[List[float]] = None,
    title: Optional[str] = None,
    x_offset: float = 0.3,
    legend_loc: str = "upper right",
    figsize: Tuple[float, float] = (10, 6),
    dpi: float = 150,
    plot_colors: Optional[List[str]] = None,
    show_band: bool = False,
    band_x: Optional[np.ndarray] = None,
    band_y_down: Optional[np.ndarray] = None,
    band_y_up: Optional[np.ndarray] = None,
    band_color: str = "gray",
    band_alpha: float = 0.35,
    band_label: str = "Fit band",
):
    """误差棒图：dict 输入，兼容一组或多组数据。

    y_data: {label: (y_mean, y_err)}；多组时同一横坐标左右错开 x_offset；
    show_band=True 时在 [band_y_down, band_y_up] 之间填充色带。
    """
    if plot_colors is None:
        plot_colors = DEFAULT_PLOT_COLORS
    plt = _backend()

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    labels = list(y_data.keys())
    xa = np.asarray(x, dtype=np.float64)
    for i, label in enumerate(labels):
        y_mean, y_err = y_data[label]
        color = plot_colors[i % len(plot_colors)]
        ax.errorbar(xa + _offsets(len(labels), x_offset)[i],
                    y_mean, yerr=y_err,
                    fmt="x", color=color, ecolor=color,
                    capsize=0, label=label)

    if show_band:
        ax.fill_between(band_x, band_y_down, band_y_up,
                        color=band_color, alpha=band_alpha,
                        linewidth=0, zorder=1, label=band_label)

    if xlim is not None:
        ax.set_xlim(xlim[0], xlim[1])
    if ylim is not None:
        ax.set_ylim(ylim[0], ylim[1])
    ax.set_xlabel(xlabel, fontsize=16, labelpad=8)
    ax.set_ylabel(ylabel, fontsize=16, labelpad=8)
    if title is not None:
        ax.set_title(title, fontsize=14, pad=12)
    ax.legend(loc=legend_loc)

    plt.tight_layout()
    fig.savefig(save_path, bbox_inches="tight")
    plt.close(fig)
    return save_path


def plot_scatter(
    x: np.ndarray,
    y_data: Dict[str, np.ndarray],
    save_path: str,
    *,
    xlabel: str = "x",
    ylabel: str = "y",
    xlim: Optional[List[float]] = None,
    ylim: Optional[List[float]] = None,
    title: Optional[str] = None,
    x_offset: float = 0.3,
    legend_loc: str = "upper right",
    figsize: Tuple[float, float] = (10, 6),
    dpi: float = 150,
    plot_colors: Optional[List[str]] = None,
    show_hline: bool = False,
    hline_y: float = 1.0,
    hline_label: Optional[str] = None,
    hline_color: Optional[str] = None,
    hline_style: str = "--",
    hline_width: float = 1.5,
):
    """散点图：dict 输入，兼容一组或多组数据；可选水平参考线（如 chi2/dof=1）。"""
    if plot_colors is None:
        plot_colors = DEFAULT_PLOT_COLORS
    plt = _backend()

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)

    if show_hline:
        _hline_color = hline_color if hline_color is not None else plot_colors[0]
        ax.axhline(y=hline_y, color=_hline_color, linestyle=hline_style,
                   linewidth=hline_width, label=hline_label)

    labels = list(y_data.keys())
    xa = np.asarray(x, dtype=np.float64)
    for i, label in enumerate(labels):
        color = plot_colors[(i + 1) % len(plot_colors)]
        ax.scatter(xa + _offsets(len(labels), x_offset)[i], y_data[label],
                   marker="x", color=color, s=40,
                   linewidths=1.5, label=label, zorder=3)

    if xlim is not None:
        ax.set_xlim(xlim[0], xlim[1])
    if ylim is not None:
        ax.set_ylim(ylim[0], ylim[1])
    ax.set_xlabel(xlabel, fontsize=16, labelpad=8)
    ax.set_ylabel(ylabel, fontsize=16, labelpad=8)
    if title is not None:
        ax.set_title(title, fontsize=14, pad=12)
    ax.legend(loc=legend_loc)

    plt.tight_layout()
    fig.savefig(save_path, bbox_inches="tight")
    plt.close(fig)
    return save_path


def plot_hist(
    data_dict: Dict[str, np.ndarray],
    save_path: str,
    *,
    xlabel: str = "value",
    ylabel: str = "frequency",
    title: Optional[str] = None,
    jackknife: bool = False,
    figsize: Tuple[float, float] = (10, 6),
    dpi: float = 150,
    plot_colors: Optional[List[str]] = None,
    sem_fn=None,
):
    """直方图：dict 输入，兼容一组或多组数据；label 含 mean(sem) 标注。"""
    from ._disconnected import sem
    if sem_fn is None:
        sem_fn = sem
    if plot_colors is None:
        plot_colors = DEFAULT_PLOT_COLORS
    plt = _backend()

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)

    all_vals = [np.asarray(v, dtype=np.float64) for v in data_dict.values()]
    summaries = [(v.mean(), sem_fn(v, jackknife=jackknife)) for v in all_vals]

    vmin = min(v.min() for v in all_vals)
    vmax = max(v.max() for v in all_vals)
    margin = (vmax - vmin) * 0.15 if vmax > vmin else 0.5
    x_range = (vmin - margin, vmax + margin)
    n_bins = int(np.sqrt(len(all_vals[0])))

    for i, (label, vals) in enumerate(data_dict.items()):
        color = plot_colors[i % len(plot_colors)]
        _mean, _sem = summaries[i]
        label_text = f"{label} {_mean:.3g}({_sem:.3g})"
        ax.hist(vals, bins=n_bins, range=x_range,
                color=color, alpha=0.35, edgecolor=color,
                linewidth=0.8, label=label_text)

    ax.set_xlabel(xlabel, fontsize=14)
    ax.set_ylabel(ylabel, fontsize=14)
    if title is not None:
        ax.set_title(title, fontsize=13)
    ax.legend(loc="upper right", fontsize=10)

    plt.tight_layout()
    fig.savefig(save_path, bbox_inches="tight")
    plt.close(fig)
    return save_path


# ============================================================
# 单组/多组封装（03_ana_ratio / 03_bare_matrix 调用方契约）
# ============================================================

def plot_single_errbar(x, y, yerr, save_path, *,
                       xlabel="x", ylabel="y", xlim=None, ylim=None,
                       title=None, label="data", legend_loc="upper right",
                       figsize=(6.4, 4.8), dpi=150):
    """单组误差棒图（c0/dE vs z 等）。"""
    return plot_errbar(np.asarray(x, dtype=np.float64),
                       {label: (y, yerr)}, save_path,
                       xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim,
                       title=title, legend_loc=legend_loc,
                       figsize=figsize, dpi=dpi)


def plot_single_chi2(x, y, save_path, *,
                     xlabel="x", ylabel="chi2/dof", xlim=None, ylim=(0, 2),
                     title=None, label="chi2/dof", legend_loc="upper right",
                     figsize=(6.4, 4.8), dpi=150):
    """单组 chi2/dof 散点图（含 y=1 参考线）。"""
    return plot_scatter(np.asarray(x, dtype=np.float64), {label: y}, save_path,
                        xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim,
                        title=title, legend_loc=legend_loc,
                        figsize=figsize, dpi=dpi,
                        show_hline=True, hline_y=1.0, hline_label="chi2/dof = 1")


def plot_multi_errbars(x, y_data, save_path, *,
                       xlabel="x", ylabel="y", xlim=None, ylim=None,
                       title=None, x_offset=0.3, legend_loc="upper right",
                       figsize=(10, 6), dpi=150):
    """多组误差棒对比图（y_data: {label: (mean, err)}）。"""
    return plot_errbar(np.asarray(x, dtype=np.float64), y_data, save_path,
                       xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim,
                       title=title, x_offset=x_offset, legend_loc=legend_loc,
                       figsize=figsize, dpi=dpi)


def plot_multi_chi2(x, y_data, save_path, *,
                    xlabel="x", ylabel="chi2/dof", xlim=None, ylim=(0, 2),
                    title=None, x_offset=0.3, legend_loc="upper right",
                    figsize=(10, 6), dpi=150):
    """多组 chi2/dof 对比散点图（含 y=1 参考线）。"""
    return plot_scatter(np.asarray(x, dtype=np.float64), y_data, save_path,
                        xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim,
                        title=title, x_offset=x_offset, legend_loc=legend_loc,
                        figsize=figsize, dpi=dpi,
                        show_hline=True, hline_y=1.0, hline_label="chi2/dof = 1")


def plot_multi_scatter(x, y_data, save_path, *,
                       xlabel="x", ylabel="y", xlim=None, ylim=None,
                       title=None, x_offset=0.3, legend_loc="upper right",
                       figsize=(10, 6), dpi=150):
    """多组散点对比图（y_data: {label: y}）。"""
    return plot_scatter(np.asarray(x, dtype=np.float64), y_data, save_path,
                        xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim,
                        title=title, x_offset=x_offset, legend_loc=legend_loc,
                        figsize=figsize, dpi=dpi)


def get_peak_memory_gb() -> float:
    """返回当前进程峰值内存占用（GB）。"""
    max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return max_rss / (1024 ** 2)
