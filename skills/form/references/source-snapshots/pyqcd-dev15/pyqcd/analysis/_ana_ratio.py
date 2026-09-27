"""
03_ana_ratio 功能：纯画图（独立实现）
======================================

功能对齐 refer/huangcl/03_ana_ratio/code.py（从 02_ratio 输出只读画图）：

- Part 1 单次 fit 图：每个拟合窗口子目录 tsep{}_{}_nex{} 下
  ratio_z{z}.png（单 z 大图 + Fit c0 色带）、c0.png、dE.png、chi2.png。
- Part 2 对比图：所有拟合窗口画在一起 cmp_c0.png / cmp_dE.png / cmp_chi2.png
  （z 按 z_step 抽样）。
- Part 3 整体 ratio 图（无色带）：ratio_z{z}_nofit.png。

统计基元复用 pyqcd.analysis；图表全部走 pyqcd.analysis._plots（独立实现）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np

from ._disconnected import sem
from ._plots import (DEFAULT_PLOT_COLORS, plot_multi_chi2, plot_multi_errbars,
                     plot_single_chi2, plot_single_errbar)


@dataclass
class AnaRatioParams:
    """03_ana_ratio 参数。"""

    conf_short: str
    Pz: int
    Nsample: int
    dt_max: int
    Nx: int
    jack: bool
    dt_list: list = field(default_factory=lambda: list(range(5, 14)))
    ratio_xlim: list = field(default_factory=lambda: [-7, 7])
    ratio_z_ylim: list = field(default_factory=lambda: [
        (0, [-0.1, 0.8]), (4, [-0.1, 0.6]), (8, [-0.1, 0.4]),
        (12, [-0.3, 0.2]), (16, [-0.3, 0.2]), (20, [-0.3, 0.2]),
    ])
    zval_xlim: list = field(default_factory=lambda: [-1, 24])
    c0_ylim: list = field(default_factory=lambda: [-0.2, 1.0])
    cmp_ylim: dict = field(default_factory=lambda: {
        "c0": [-0.2, 0.8], "dE": [0.5, 1.8], "chi2": [0, 2]})
    z_step: int = 3

    @property
    def zval(self) -> np.ndarray:
        """c0/chi2 vs z 图横坐标。"""
        return np.arange(self.Nx)


def ratio_file_name(Pz, Nsample, dt_max) -> str:
    """02_ratio 输出文件名（读端契约）。"""
    return f"ratio_Pz{Pz}_Nsam{Nsample}_dtmax{dt_max}.npy"


def fit_dir_name(Pz, Nsample, dt_max, fitpa, tag="fit") -> str:
    """02_ratio 拟合目录名（读端契约）。"""
    return (f"{tag}_Pz{Pz}_Nsam{Nsample}_dtmax{dt_max}"
            f"_tsep{fitpa.dt_start}_{fitpa.dt_end}_nex{fitpa.nex}")


def load_ratio(ratio_dir: str, conf_short: str, Pz: int, Nsample: int,
               dt_max: int) -> np.ndarray:
    """读取 02_ratio 输出的 ratio 数组 (Nsample, dt, dtau, z)。"""
    path = os.path.join(ratio_dir, conf_short, ratio_file_name(Pz, Nsample, dt_max))
    if not os.path.exists(path):
        raise FileNotFoundError(f"ratio file not found: {path}")
    return np.load(path)


def load_fit_result(ratio_dir: str, conf_short: str, Pz: int, Nsample: int,
                    dt_max: int, fitpa):
    """读取 02_ratio 输出的拟合结果 {c0,c1,dE,chi2: (Nsample, Nx)}。"""
    path = os.path.join(ratio_dir, conf_short,
                        fit_dir_name(Pz, Nsample, dt_max, fitpa),
                        "0_fit_data.npz")
    if not os.path.exists(path):
        raise FileNotFoundError(f"fit file not found: {path}")
    fit_npz = np.load(path)
    return {"c0": fit_npz["c0"], "c1": fit_npz["c1"],
            "dE": fit_npz["dE"], "chi2": fit_npz["chi2"]}


def plot_ratio_one_z(ratio_mean, ratio_err, c0_mean, c0_err, z, _ylim,
                     save_path, params: AnaRatioParams, fitpa,
                     colors=None):
    """单个 z 的 ratio 散点图（含 Fit c0 色带）。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    if colors is None:
        colors = DEFAULT_PLOT_COLORS

    fig, ax = plt.subplots(figsize=(8, 6), dpi=150)

    dt_max_fit = fitpa.dt_end
    dt_list_fit = [dt for dt in params.dt_list if dt <= dt_max_fit]
    for i, dt in enumerate(dt_list_fit):
        tau_vals = np.arange(0, dt + 1)
        x_vals = tau_vals - dt / 2.0
        color = colors[i % len(colors)]
        ax.errorbar(x_vals, ratio_mean[dt, tau_vals],
                    yerr=ratio_err[dt, tau_vals],
                    fmt="x", color=color, ecolor=color,
                    capsize=0, markeredgewidth=1.8,
                    linewidth=1.2, zorder=3, label=f"tsep={dt}")

    x_band = np.array(params.ratio_xlim)
    ax.fill_between(x_band, [c0_mean - c0_err, c0_mean - c0_err],
                    [c0_mean + c0_err, c0_mean + c0_err],
                    color="gray", alpha=0.35, linewidth=0,
                    zorder=1, label="Fit c0")

    if _ylim is not None:
        ax.set_ylim(_ylim[0], _ylim[1])
    ax.set_xlim(params.ratio_xlim[0], params.ratio_xlim[1])
    ax.set_xlabel("t_ins - t_sep/2", fontsize=16, labelpad=8)
    ax.set_ylabel("C3 / C2", fontsize=16, labelpad=8)
    ax.set_title(
        f"Unpolarized, Pz={params.Pz}, z={z}, Nconf={params.Nsample}, "
        f"Nsample={params.Nsample}\n"
        f"fit: tsep=[{fitpa.dt_start},{fitpa.dt_end}], nex={fitpa.nex}",
        fontsize=13, pad=12)
    ax.legend(loc="upper right", fontsize=9)

    plt.tight_layout()
    fig.savefig(save_path, bbox_inches="tight")
    plt.close(fig)
    return save_path


def plot_all(ratio_dir: str, pic_dir: str, params: AnaRatioParams,
             fitpa_list, plot_mode: int = 1, verbose=True) -> list:
    """03_ana_ratio 全量画图。

    plot_mode=1: 单次 fit 图 + 对比图 + nofit 图；
    plot_mode=2: 只画对比图。
    """
    saved = []
    os.makedirs(pic_dir, exist_ok=True)

    ratio = load_ratio(ratio_dir, params.conf_short, params.Pz,
                       params.Nsample, params.dt_max)
    ratio_mean = ratio.mean(0)
    ratio_err = sem(ratio, params.jack)

    all_results = []
    for fitpa in fitpa_list:
        fit_result = load_fit_result(ratio_dir, params.conf_short, params.Pz,
                                     params.Nsample, params.dt_max, fitpa)
        all_results.append({"fitpa": fitpa,
                            "c0": fit_result["c0"],
                            "dE": fit_result["dE"],
                            "chi2": fit_result["chi2"]})

    if plot_mode == 1:
        for res in all_results:
            fitpa = res["fitpa"]
            c0, dE, chi2 = res["c0"], res["dE"], res["chi2"]
            save_dir = os.path.join(
                pic_dir, f"tsep{fitpa.dt_start}_{fitpa.dt_end}_nex{fitpa.nex}")
            os.makedirs(save_dir, exist_ok=True)

            # 1. 每个 z 一张 ratio 大图（含 bestfit 色带）
            for z, _ylim in params.ratio_z_ylim:
                sp = os.path.join(save_dir, f"ratio_z{z}.png")
                plot_ratio_one_z(ratio_mean[:, :, z], ratio_err[:, :, z],
                                 c0[:, z].mean(), sem(c0[:, z], params.jack),
                                 z, _ylim, sp, params, fitpa)
                saved.append(sp)

            # 2-4. c0 / dE / chi2 vs z
            title = (f"Unpolarized, Pz={params.Pz}, Nconf={params.Nsample}, "
                     f"Nsample={params.Nsample}\n"
                     f"fit: tsep=[{fitpa.dt_start},{fitpa.dt_end}], "
                     f"nex={fitpa.nex}")
            sp = os.path.join(save_dir, "c0.png")
            plot_single_errbar(params.zval, c0.mean(0), sem(c0, params.jack), sp,
                               xlabel="z", ylabel="c0", ylim=params.c0_ylim,
                               xlim=params.zval_xlim, title=title, label="c0")
            saved.append(sp)
            sp = os.path.join(save_dir, "dE.png")
            plot_single_errbar(params.zval, dE.mean(0), sem(dE, params.jack), sp,
                               xlabel="z", ylabel="dE",
                               ylim=params.cmp_ylim.get("dE"),
                               xlim=params.zval_xlim, title=title, label="dE")
            saved.append(sp)
            sp = os.path.join(save_dir, "chi2.png")
            plot_single_chi2(params.zval, chi2.mean(0), sp,
                             xlabel="z", xlim=params.zval_xlim,
                             title=title, label="chi2/dof")
            saved.append(sp)

    # ---- Part 2: 对比图 ----
    cmp_z_vals = np.arange(0, params.Nx, params.z_step)
    for qty in ["c0", "dE", "chi2"]:
        y_data = {}
        for res in all_results:
            data = res[qty]
            label = (f"tsep={res['fitpa'].dt_start}~{res['fitpa'].dt_end}, "
                     f"nex={res['fitpa'].nex}")
            if qty == "chi2":
                y_data[label] = data.mean(0)[cmp_z_vals]
            else:
                y_data[label] = (data.mean(0)[cmp_z_vals],
                                 sem(data, params.jack)[cmp_z_vals])
        sp = os.path.join(pic_dir, f"cmp_{qty}.png")
        title = f"Unpolarized, Pz={params.Pz}, Nconf={params.Nsample}"
        if qty == "chi2":
            plot_multi_chi2(cmp_z_vals, y_data, sp, xlabel="z",
                            xlim=params.zval_xlim, title=title)
        else:
            plot_multi_errbars(cmp_z_vals, y_data, sp, xlabel="z", ylabel=qty,
                               ylim=params.cmp_ylim.get(qty),
                               xlim=params.zval_xlim, title=title)
        saved.append(sp)

    # ---- Part 3: 整体 ratio 散点图（无 bestfit 色带）----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for z, _ylim in params.ratio_z_ylim:
        fig, ax = plt.subplots(figsize=(8, 6), dpi=150)
        for i, dt in enumerate(params.dt_list):
            tau_vals = np.arange(0, dt + 1)
            x_vals = tau_vals - dt / 2.0
            color = DEFAULT_PLOT_COLORS[i % len(DEFAULT_PLOT_COLORS)]
            ax.errorbar(x_vals, ratio_mean[dt, tau_vals, z],
                        yerr=ratio_err[dt, tau_vals, z],
                        fmt="x", color=color, ecolor=color,
                        capsize=0, markeredgewidth=1.8,
                        linewidth=1.2, zorder=3, label=f"tsep={dt}")
        if _ylim is not None:
            ax.set_ylim(_ylim[0], _ylim[1])
        ax.set_xlim(params.ratio_xlim[0], params.ratio_xlim[1])
        ax.set_xlabel("t_ins - t_sep/2", fontsize=16, labelpad=8)
        ax.set_ylabel("C3 / C2", fontsize=16, labelpad=8)
        ax.set_title(
            f"Unpolarized, Pz={params.Pz}, z={z}, Nconf={params.Nsample}, "
            f"Nsample={params.Nsample}", fontsize=13, pad=12)
        ax.legend(loc="upper right", fontsize=9)
        plt.tight_layout()
        sp = os.path.join(pic_dir, f"ratio_z{z}_nofit.png")
        fig.savefig(sp, bbox_inches="tight")
        plt.close(fig)
        saved.append(sp)

    if verbose:
        print(f"plot all done, {len(saved)} images → {pic_dir}")
    return saved
