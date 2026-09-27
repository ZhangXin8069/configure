"""
三方向差异分析（输入数据路径 → 分析 → 作图，独立实现）
========================================================

功能对齐 refer/huangcl/05_ana_3dir_diff_sem/code_ana_3dir_diff_sem.py：
给定数据根目录与系综标识（conf_short），读取三方向（x/y/z）与平均（ave）的
ratio（3pt/2pt 比值）与 corr2（2pt 关联函数）数据，计算有效质量、方向间
归一化协方差（相关系数），并输出 ratio / corr2 / eff_mass 三类直方图
（mean ± sem 标注）。

数据目录结构（约定）::

    <data_root>/<conf_short>/Pz<Pz>/{x,y,z,ave}_dir/ratio.npy   shape (Nsample, Ntsep, Ntins, Nz)
    <data_root>/<conf_short>/Pz<Pz>/corr2_{x,y,z,ave}.npy       shape (Nsample, Ntsep)

    axis=0: 样本维度（bootstrap/jackknife）
    axis=1: t_sep (dt) 维度
    axis=2: t_ins (dtau) 维度, 0 <= dtau <= dt
    axis=3: z 维度 (0 ~ Nx-1)

统计约定：sem 采用 jackknife 标准误（`pyqcd.analysis.sem`），
协方差/条件数采用 jackknife 公式（`pyqcd.analysis.cov_mat`）。

顶层入口：`analyze_3dir(data_root, out_root, params, jackknife, verbose)`。
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import numpy as np

from ._disconnected import sem, cov_mat

# 默认画图配色（三方向 + 平均）
DEFAULT_PLOT_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd"]

DIRS = ["x", "y", "z", "ave"]
DIRS_3 = ["x", "y", "z"]


@dataclass
class AnaParams:
    """分析参数：系综标识与切片坐标。"""

    conf_short: str
    Px: int
    Py: int
    Pz: int
    dt: int          # t_sep
    dtau: int        # t_ins (0 <= dtau <= dt)
    z: int           # z 坐标


@dataclass
class DirParams:
    """路径管理：区分读取路径与输出路径。

    data_root 为输入数据根目录（包含 <conf_short>/Pz<Pz>/ 子结构），
    out_root 为输出根目录（保存 <conf_short>/ratio|corr2|eff_mass/ 产物）。
    """

    data_root: str
    out_root: str
    conf_short: str
    Pz: int

    @property
    def read_base(self):
        """输入数据基目录。"""
        return os.path.join(self.data_root, self.conf_short, f"Pz{self.Pz}")

    @property
    def ratio_read_dir(self):
        """ratio 数据读取路径。"""
        return self.read_base

    @property
    def corr2_read_dir(self):
        """corr2 数据读取路径。"""
        return self.read_base

    @property
    def _save_base(self):
        d = os.path.join(self.out_root, self.conf_short)
        os.makedirs(d, exist_ok=True)
        return d

    @property
    def ratio_save_dir(self):
        """ratio 直方图输出目录。"""
        d = os.path.join(self._save_base, "ratio")
        os.makedirs(d, exist_ok=True)
        return d

    @property
    def corr2_save_dir(self):
        """corr2 直方图输出目录。"""
        d = os.path.join(self._save_base, "corr2")
        os.makedirs(d, exist_ok=True)
        return d

    @property
    def eff_mass_save_dir(self):
        """eff_mass 直方图输出目录。"""
        d = os.path.join(self._save_base, "eff_mass")
        os.makedirs(d, exist_ok=True)
        return d


def load_ratio(dirpa: DirParams, verbose=True):
    """读取三方向与平均的 ratio 数据。

    Returns
    -------
    dict
        key 为方向 ("x", "y", "z", "ave")，
        value 为 ratio 数组，shape (Nsample, Ntsep, Ntins, Nz)。
    """
    ratio_data = {}
    for _dir in DIRS:
        load_path = os.path.join(dirpa.ratio_read_dir, f"{_dir}_dir", "ratio.npy")
        ratio = np.load(load_path)
        if verbose:
            print(f"===== loading ratio ({_dir}) from: {load_path} =====")
            print(f"  ratio ({_dir}) loaded, shape: {ratio.shape}")
        ratio_data[_dir] = ratio
    return ratio_data


def load_corr2(dirpa: DirParams, verbose=True):
    """读取四个方向 (x, y, z, ave) 的 corr2 (2pt) 数据。

    Returns
    -------
    dict
        key 为方向 ("x", "y", "z", "ave")，
        value 为 corr2 数组，shape (Nsample, Ntsep)。
    """
    corr2_data = {}
    for _dir in DIRS:
        load_path = os.path.join(dirpa.corr2_read_dir, f"corr2_{_dir}.npy")
        corr2 = np.load(load_path)
        if verbose:
            print(f"===== loading corr2 ({_dir}) from: {load_path} =====")
            print(f"  corr2 ({_dir}) loaded, shape: {corr2.shape}")
        corr2_data[_dir] = corr2
    return corr2_data


def compute_eff_mass(corr2_data: dict, verbose=True) -> dict:
    """从 corr2 数据计算有效质量（effective mass）。

    mass = log( C(t) / C(t+1) )，使用 np.roll 向量化计算。
    边界点（最后一列）为周期卷绕值，无物理意义，保留以保持 shape 一致。

    Returns
    -------
    dict
        key 为方向，value 为 eff_mass 数组，shape (Nsample, Ntsep)。
    """
    if verbose:
        print("===== computing effective mass =====")
    eff_mass_data = {}
    for _dir in DIRS:
        _corr2 = corr2_data[_dir]
        mass = np.log(_corr2 / np.roll(_corr2, shift=-1, axis=1))
        eff_mass_data[_dir] = mass
        if verbose:
            print(f"  eff_mass ({_dir}) computed, shape: {mass.shape}")
    if verbose:
        print("===== eff mass computation end =====")
    return eff_mass_data


def normalized_cov(eff_mass_data: dict, dt: int, jackknife: bool = False):
    """计算 eff_mass 在指定 dt 下，不同方向 (x/y/z) 两两之间的归一化协方差。

    归一化协方差: corr = cov[i,j] / sqrt(cov[i,i] * cov[j,j])。

    Returns
    -------
    (corr_mat, cov_mat, cond)
        corr_mat : (3, 3) 相关系数矩阵；cov_mat : (3, 3) 协方差矩阵；
        cond : 协方差矩阵特征值条件数。
    """
    arr = np.column_stack([eff_mass_data[_dir][:, dt] for _dir in DIRS_3])
    cov, cond = cov_mat(arr, jackknife=jackknife)
    diag_std = np.sqrt(np.diag(cov))
    corr = cov / np.outer(diag_std, diag_std)
    return corr, cov, cond


def _summarize_slice(vals, jackknife: bool):
    """单个样本切片的 {mean, sem, n}。"""
    return {"mean": float(vals.mean()),
            "sem": float(sem(vals, jackknife=jackknife)),
            "n": int(vals.shape[0])}


def plot_histogram(data_dict: dict, save_dir: str, jackknife: bool,
                   xlabel: str = "value", title_prefix: str = "",
                   filename_prefix: str = "hist", verbose=True) -> dict:
    """通用直方图画图函数。

    Parameters
    ----------
    data_dict : dict
        key 为 label 字符串（如 "x_dir", "y_dir"），value 为 1D 样本数组。
    save_dir : str
        图片保存目录。
    jackknife : bool
        是否使用 jackknife SEM。
    xlabel / title_prefix / filename_prefix : str
        横轴标签 / 标题前缀（附加 Nsample 等信息）/ 文件名前缀。

    Returns
    -------
    dict
        汇总统计: {label: {"mean": float, "sem": float, "n": int}}。
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if verbose:
        print(f"===== plotting histogram: {filename_prefix} =====")

    colors = DEFAULT_PLOT_COLORS
    labels = list(data_dict.keys())

    all_vals = [np.asarray(v, dtype=np.float64) for v in data_dict.values()]
    summaries = {label: _summarize_slice(vals, jackknife)
                 for label, vals in zip(labels, all_vals)}

    vmin = min(v.min() for v in all_vals)
    vmax = max(v.max() for v in all_vals)
    margin = (vmax - vmin) * 0.15 if vmax > vmin else 0.5
    x_range = (vmin - margin, vmax + margin)
    n_bins = int(np.sqrt(len(all_vals[0])))

    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
    for i, label in enumerate(labels):
        color = colors[i % len(colors)]
        _mean = summaries[label]["mean"]
        _sem = summaries[label]["sem"]
        label_text = f"{label} {_mean:.3g}({_sem:.3g})"
        ax.hist(all_vals[i], bins=n_bins, range=x_range,
                color=color, alpha=0.35, edgecolor=color,
                linewidth=0.8, label=label_text)

    ax.set_xlabel(xlabel, fontsize=14)
    ax.set_ylabel("frequency", fontsize=14)
    ax.set_title(f"{title_prefix}, Nsample={len(all_vals[0])}", fontsize=13)
    ax.legend(loc="upper right", fontsize=10)
    plt.tight_layout()

    save_path = os.path.join(save_dir, f"{filename_prefix}.png")
    fig.savefig(save_path, bbox_inches="tight")
    if verbose:
        print(f"  saved: {save_path}")
    plt.close(fig)

    if verbose:
        print("  Summary (mean(sem)):")
        for _label, _s in summaries.items():
            print(f"    {_label}: {_s['mean']:.3g}({_s['sem']:.3g})")
        print(f"===== {filename_prefix} plot end =====")
    return summaries


def plot_ratio_histogram(ratio_data: dict, anapa: AnaParams,
                         save_dir: str, jackknife: bool, verbose=True) -> dict:
    """从 ratio_data 提取指定 (dt, dtau, z) 切片，画三方向直方图。"""
    data_dict = {f"{_dir}_dir": ratio_data[_dir][:, anapa.dt, anapa.dtau, anapa.z]
                 for _dir in DIRS_3}
    title = (f"P=({anapa.Px},{anapa.Py},{anapa.Pz}), "
             f"tsep={anapa.dt}, tins={anapa.dtau}, z={anapa.z}")
    filename = (f"hist_ratio_P{anapa.Pz}_z{anapa.z}"
                f"_tsep{anapa.dt}_tins{anapa.dtau}")
    return plot_histogram(data_dict, save_dir, jackknife,
                          xlabel="ratio value", title_prefix=title,
                          filename_prefix=filename, verbose=verbose)


def plot_corr2_histogram(corr2_data: dict, anapa: AnaParams,
                         save_dir: str, jackknife: bool, verbose=True) -> dict:
    """从 corr2_data 提取指定 dt (tsep) 切片，画三方向直方图。"""
    data_dict = {f"{_dir}_dir": corr2_data[_dir][:, anapa.dt]
                 for _dir in DIRS_3}
    title = f"corr2, Pz={anapa.Pz}, tsep={anapa.dt}"
    filename = f"hist_corr2_P{anapa.Pz}_tsep{anapa.dt}"
    return plot_histogram(data_dict, save_dir, jackknife,
                          xlabel="corr2 value", title_prefix=title,
                          filename_prefix=filename, verbose=verbose)


def plot_eff_mass_histogram(eff_mass_data: dict, anapa: AnaParams,
                            save_dir: str, jackknife: bool, verbose=True) -> dict:
    """从 eff_mass_data 提取指定 dt (tsep) 切片，画三方向直方图。"""
    data_dict = {f"{_dir}_dir": eff_mass_data[_dir][:, anapa.dt]
                 for _dir in DIRS_3}
    title = f"eff_mass, Pz={anapa.Pz}, tsep={anapa.dt}"
    filename = f"hist_eff_mass_P{anapa.Pz}_tsep{anapa.dt}"
    return plot_histogram(data_dict, save_dir, jackknife,
                          xlabel="effective mass", title_prefix=title,
                          filename_prefix=filename, verbose=verbose)


def analyze_3dir(data_root: str, out_root: str, params: AnaParams,
                 jackknife: bool = False, verbose=True) -> dict:
    """三方向差异分析顶层入口：加载 → 分析 → 作图 → 汇总。

    Parameters
    ----------
    data_root : str
        输入数据根目录（包含 <conf_short>/Pz<Pz>/ 子结构）。
    out_root : str
        输出根目录（保存 <conf_short>/ratio|corr2|eff_mass/ 直方图与
        ana_3dir_summary.json 汇总）。
    params : AnaParams
        分析参数（conf_short / 动量 / dt / dtau / z）。
    jackknife : bool
        是否使用 jackknife SEM。

    Returns
    -------
    dict
        汇总统计: 直方图 mean/sem、eff_mass 均值、相关系数矩阵等。
    """
    time0 = time.perf_counter()
    dirpa = DirParams(data_root=data_root, out_root=out_root,
                      conf_short=params.conf_short, Pz=params.Pz)
    if verbose:
        print(f"ratio_read_dir: {dirpa.ratio_read_dir}")
        print(f"corr2_read_dir: {dirpa.corr2_read_dir}")
        print(f"ratio_save_dir: {dirpa.ratio_save_dir}")
        print(f"corr2_save_dir: {dirpa.corr2_save_dir}")
        print(f"eff_mass_save_dir: {dirpa.eff_mass_save_dir}")
        print("jackknife:", jackknife)

    ratio_data = load_ratio(dirpa, verbose=verbose)
    corr2_data = load_corr2(dirpa, verbose=verbose)
    eff_mass_data = compute_eff_mass(corr2_data, verbose=verbose)

    ratio_summary = plot_ratio_histogram(ratio_data, params,
                                         dirpa.ratio_save_dir, jackknife,
                                         verbose=verbose)
    corr2_summary = plot_corr2_histogram(corr2_data, params,
                                         dirpa.corr2_save_dir, jackknife,
                                         verbose=verbose)
    eff_mass_summary = plot_eff_mass_histogram(eff_mass_data, params,
                                               dirpa.eff_mass_save_dir,
                                               jackknife, verbose=verbose)

    corr_mat, cov, cond = normalized_cov(eff_mass_data, params.dt, jackknife)
    if verbose:
        print("===== normalized covariance (correlation) of eff_mass =====")
        print(f"  Pz={params.Pz}, tsep={params.dt}")
        print(f"  covariance matrix (shape={cov.shape}):")
        print(cov)
        print(f"  condition number: {cond:.3f}")
        print("  correlation matrix:")
        print(corr_mat)
        for i in range(3):
            for j in range(i + 1, 3):
                print(f"    corr({DIRS_3[i]}_dir, {DIRS_3[j]}_dir) = {corr_mat[i, j]:.4f}")
        print("===== normalized cov end =====\n")

    summary = {
        "params": {
            "conf_short": params.conf_short,
            "Px": params.Px, "Py": params.Py, "Pz": params.Pz,
            "dt": params.dt, "dtau": params.dtau, "z": params.z,
        },
        "jackknife": bool(jackknife),
        "histograms": {
            "ratio": ratio_summary,
            "corr2": corr2_summary,
            "eff_mass": eff_mass_summary,
        },
        "eff_mass_mean": {d: eff_mass_data[d].mean(0).tolist()
                          for d in DIRS},
        "eff_mass_sem": {d: sem(eff_mass_data[d], jackknife=jackknife)
                         .tolist() for d in DIRS},
        "correlation": {
            "matrix": corr_mat.tolist(),
            "cov": cov.tolist(),
            "cond": float(cond),
        },
        "time_s": float(time.perf_counter() - time0),
    }
    summary_path = os.path.join(dirpa._save_base, "ana_3dir_summary.json")
    import json
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    if verbose:
        print(f"summary saved: {summary_path}")
        print(f"total time: {summary['time_s']:.2f}s")
        print("job finish")
    return summary
