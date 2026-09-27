#!/usr/bin/env python3
"""
基于已有收缩结果生成有效质量谱与 ratio 链图表
===============================================

该流程在有效质量谱链基础上增加 02_ratio 链：

1. 组态清单按实际存在扫描（数据目录可能被外部删减，
   全树 mtime <=2026-08-18；不假设网格，缺失即缺，如实记录）。
2. 生成 ratio_3pt_all_channels.png：输入含 ops_mu*_nu*_dz24
   (Nz,Nt) 与 corr_pp (Nt,)——正是 pyqcd.analysis.run_ratio2pt（02 链）的
   输入类型。构造平移不变切片矩阵 -> 真空扣除比值 R(t_sep, tau, z) -> 逐 z 拟合
   c0 -> 2x2 面板 R(tau)。物理语义为 disconnected 胶子 OPE / 2pt 比值
   （组合 O = -O30 - O31 + 2*O01），非连通 perambulator 3pt——图题与
   summary 明注，绝不混淆。
3. Part A/B（双通道汇总 2 图 + 每通道 7 图）与基础谱链共享实现。

输入：${HOME}/data/beta6.20_mu-0.2770_ms-0.2400_L24x72/conf<cid>/ 下的
      tag-test8 管线产物：
        corr_pp_P0_<cid>.npy / corr_pp_P2_<cid>.npy    —— 质子 2pt（P=(0,0,0)/(0,0,2)）
        ops_mu0_nu1/mu3_nu0/mu3_nu1_dz24_<cid>.npz     —— 胶子 OPE 单分量（Part C）
        ope_combined_conf<cid>.h5 / VdV/VVV_mom.npy    —— 本任务不消费

输出（`artifacts/run_<ts>/` 或 --outdir）：
  test0 型 3 图：correlators/meff/ratio_3pt_all_channels.png（10 型齐全）
  test6 型 7 图：corr2_raw eff_mass sem_comparison eff_mass_GeV
                 eff_mass_fit_dirs meff_corr meff_hist
  02 链产物：<out>/L24x72/ratio_Pz2_Nsam*_dtmax20.npy +
             fit_Pz2_*_tsep{a}_{b}_nex{c}/{0_fit_data.npz,1_fit_report.txt,
             ratio.png,c0.png,chi2.png}
  数据：corr2_{P0,P2}.npy + 1_fit_data.npz + 2_fit_report.txt + analysis_summary.json
  暂存：<out>/input_stage/（02 链布局，小文件，可删）

用法：
    python -m pyqcd.testing.spectrum.effective_mass_ratio \
        [--data-root PATH] [--n-conf N] [--conf-ids a,b,...]
        [--outdir DIR] [--debug] [--skip-ratio]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

OUTPUT_ROOT = Path(__file__).resolve().parent / "artifacts"

from pyqcd.analysis._disconnected import cov_mat, sem  # noqa: E402
from pyqcd.analysis._fitter import fit_report_lines, make_summary_table  # noqa: E402
from pyqcd.analysis._plots import (  # noqa: E402
    DEFAULT_PLOT_COLORS,
    get_peak_memory_gb,
    plot_errbar,
    plot_scatter,
)
from pyqcd.analysis import (  # noqa: E402
    FitParams,
    PlotParamsRatio,
    SampleParams2pt,
    run_meff_jackknife,
    run_ratio2pt,
)

# ===== 参数块（对齐 logs/v20260820.txt 与 pyqcd/pipeline/_config.py 约定）=====
DATA_ROOT = os.path.join(
    os.environ.get("HOME", "/public/home/zhangxin"), "data",
    "beta6.20_mu-0.2770_ms-0.2400_L24x72")
NT = 72
NX = 24
ALTTc = 0.1053                      # 格距 fm（_config.py）
UNIT = 0.197 / ALTTc                # 格点能 -> GeV（test6 约定，约 1.8708）
CHANNELS = ("P0", "P2")             # 动量标签：(0,0,0) 与 (0,0,2)
DT_MAX = 20                         # 分析窗长（test6/test8 约定）
FIT_START, FIT_END = 6, 12          # 平台拟合窗（对齐 run_meff_jackknife 质子窗）
DT_REF = (FIT_START + FIT_END) // 2
SVD_CUT = 1e-6
XLIM = [-0.5, 15.5]
YLIM_AE = [0.4, 1.05]               # aE（P0 约 0.60 / P2 约 0.83）
SEM_YLIM = [-0.005, 0.05]
YLIM_GEV = [0.8, 2.0]
X_OFFSET = 0.2

MOM_LABEL = {"P0": "(0,0,0)", "P2": "(0,0,2)"}

# ===== Part C 参数（照抄 logs/test8/main.py SYNTH/FIT_* 与 run_02_ratio）=====
CONF_SHORT = "L24x72"
CONF_NAME = "beta6.20_mu-0.2770_ms-0.2400_L24x72"
RATIO_PZ = 2                        # 02 链动量（test8 正式配置）
RATIO_DT_MAX = 20                   # test8 正式配置
# 拟合窗口：test8 用 6 窗；资源约束下取 3 代表窗（覆盖 nex=2/3/4 与窗起点变化）
FIT_WINDOWS = [(6, 11, 2), (7, 11, 3), (9, 11, 4)]
FIT_P0 = {"c0": 10.0, "c1": -5.0, "dE": 1.0}
FIT_PRIOR = {"c0": (10.0, 5.0), "c1": (-5.0, 10.0), "dE": (1.0, 1.0)}
PLOT_Z = 2                          # 02 链主图 z（test8 约定）
T_SEP_SUM = 10                      # ratio_3pt 汇总图固定 t_sep（窗 [6,11] 内）
Z_PANELS = (0, 2, 4, 6)             # ratio_3pt 汇总图四通道（算符长度 z）


# ===== 输入扫描与加载 =====

def scan_conf_ids(data_root):
    """扫描同时具备 corr_pp_P0/P2 与三个 ops npz 的组态（排序去重，按实际存在）。"""
    ids = set()
    for f in glob.glob(os.path.join(data_root, "conf*", "corr_pp_P0_*.npy")):
        cid = int(os.path.basename(f).split("_")[-1].split(".")[0])
        base = os.path.join(data_root, f"conf{cid}")
        need = [os.path.join(base, f"corr_pp_P2_{cid}.npy")] + [
            os.path.join(base,
                         f"ops_mu{mu}_nu{nu}_dz{NX}_conf{cid}.npz")
            for mu, nu in [(0, 1), (3, 0), (3, 1)]]
        if all(os.path.exists(p) for p in need):
            ids.add(cid)
    return sorted(ids)


def load_raw(data_root, conf_ids):
    """读两通道 2pt -> {ch: (Nconf, Nt) 实数组}。"""
    raw = {}
    for ch in CHANNELS:
        arr = np.zeros((len(conf_ids), NT))
        for i, cid in enumerate(conf_ids):
            arr[i] = np.load(os.path.join(
                data_root, f"conf{cid}", f"corr_pp_{ch}_{cid}.npy"))
        raw[ch] = arr
    return raw


# ===== Part B：能量链（test6 型，与 dev6 同逻辑）=====

def energy_model(x, p):
    """C(t) = c0*e^(-E0*t)*(1 + c1*e^(-dE*t))。"""
    dt = np.asarray(x, dtype=np.float64)
    return (p["c0"] * np.exp(-p["E0"] * dt)
            * (1 + p["c1"] * np.exp(-p["dE"] * dt)))


def make_p0(corr_mean):
    """由平台数据构造拟合初值（避免硬编码先验）。"""
    tw = slice(FIT_START, FIT_END + 1)
    e_est = np.log(np.abs(corr_mean[FIT_START])
                   / np.abs(corr_mean[FIT_END - 1])) / max(FIT_END - 1 - FIT_START, 1)
    c_est = np.mean(np.abs(corr_mean[tw])
                    / np.exp(-e_est * np.arange(FIT_START, FIT_END + 1)))
    return {"c0": float(max(c_est, 1e-8)), "c1": 0.1, "E0": float(e_est),
            "dE": 0.3}


def do_fit(corr2, sgn=1.0, verbose=False):
    """逐样本 lsqfit 平台拟合 -> ({name: 样本数组}, cond)。坏样本 NaN 不中断。

    sgn：全局符号约定（本输入两通道窗口内 C<0，相位残留 pi；拟合 sgn*C 使
    c0>0 落入物理盆地——全局符号不可观测量，不影响 E0）。
    """
    import gvar as gv
    import lsqfit

    n_sample = corr2.shape[0]
    x_coor = list(range(FIT_START, FIT_END + 1))
    names = ["c0", "c1", "E0", "dE"]
    sub_sample = corr2[:, FIT_START:FIT_END + 1] * sgn
    cov, cond = cov_mat(sub_sample, True)
    p0 = make_p0(np.abs(corr2.mean(0)))

    result = {name: np.full(n_sample, np.nan) for name in names}
    result["chi2"] = np.full(n_sample, np.nan)
    n_bad = 0
    for i in range(n_sample):
        try:
            y_coor = gv.gvar(sub_sample[i], cov)
            fit = lsqfit.nonlinear_fit(data=(x_coor, y_coor), p0=p0,
                                       fcn=energy_model, svdcut=SVD_CUT)
            for name in names:
                result[name][i] = fit.pmean[name]
            result["chi2"][i] = fit.chi2 / fit.dof
        except Exception:
            n_bad += 1
        if verbose and (i + 1) % 100 == 0:
            print(f"  fit {i + 1}/{n_sample}")
    if n_bad:
        print(f"[warn] 拟合失败 {n_bad}/{n_sample} 个样本（NaN 填充）")
    return result, cond


def part_b(raw, out_dir):
    """B 型：resample -> meff -> 逐样本拟合 -> 7 图 + npz/report。"""
    print("==================== Part B（test6 型能量链）====================")
    from pyqcd.analysis._disconnected import resample
    corr2 = {ch: resample(raw[ch][:, :DT_MAX], jackknife=True).real
             for ch in CHANNELS}
    mass = {ch: np.log(np.abs(corr2[ch]) / np.abs(np.roll(corr2[ch], -1, axis=1)))
            for ch in CHANNELS}
    fits, conds, signs = {}, {}, {}
    for ch in CHANNELS:
        t0 = time.perf_counter()
        sgn = float(np.sign(corr2[ch][:, FIT_START:FIT_END + 1].mean())) or 1.0
        signs[ch] = sgn
        fits[ch], conds[ch] = do_fit(corr2[ch], sgn=sgn)
        r = fits[ch]
        m = np.nanmean(r["E0"]) * UNIT
        e = sem(r["E0"][np.isfinite(r["E0"])], True) * UNIT
        print(f"{ch}: E0={m:.4f}({e * 1e3:.0f}) GeV  "
              f"chi2/dof={np.nanmean(r['chi2']):.2f}  "
              f"cond={conds[ch]:.3g}  ({time.perf_counter() - t0:.1f}s)")
        np.save(os.path.join(out_dir, f"corr2_{ch}.npy"), corr2[ch])

    np.savez(os.path.join(out_dir, "1_fit_data.npz"),
             **{f"{k}_{ch}": v for ch in CHANNELS for k, v in fits[ch].items()})
    write_report(fits, conds, signs, out_dir)
    plot_part_b(corr2, mass, fits, out_dir)
    return corr2, mass, fits


def write_report(fits, conds, signs, out_dir):
    rows = []
    report = fit_report_lines("Fit Report  : dev7 L24x72 (proton P0/P2)", {
        "dt range": f"[{FIT_START}, {FIT_END}]",
        "unit": f"{UNIT:.4f} GeV (a={ALTTc} fm)",
        "svdcut": SVD_CUT,
        "jackknife": True,
        "sign convention": "fit sgn*C（窗口内 C<0，全局符号不可观测）",
    })
    for ch in CHANNELS:
        r = fits[ch]
        ok = np.isfinite(r["E0"])
        e0m = np.nanmean(r["E0"])
        e0e = sem(r["E0"][ok], True)
        report.append("-" * 72)
        report.append(f"channel = {ch}, condition number = {conds[ch]:.3g}, "
                      f"Nfit = {int(ok.sum())}/{r['E0'].size}, "
                      f"sgn = {signs[ch]:+.0f}")
        report.append("")
        report.append(f"  {ch}  c0={np.nanmean(r['c0']):.3g}"
                      f"({sem(r['c0'][ok], True) * 1e3:.0f})  "
                      f"E0={e0m:.3g}({e0e * 1e3:.0f})  "
                      f"chi2/dof={np.nanmean(r['chi2']):.2g}")
        rows.append([ch, f"{e0m:.3f}({e0e * 1e3:.0f})",
                     f"{e0m * UNIT:.3f}({e0e * UNIT * 1e3:.0f})",
                     f"{np.nanmean(r['c0']):.3g}",
                     f"{np.nanmean(r['chi2']):.2g}"])
    report.append("=" * 72)
    report.append("  Summary Table (E0 in lattice & GeV)")
    report.append("=" * 72)
    report.append(make_summary_table(
        ["channel", "E0(a^-1)", "E0(GeV)", "c0", "chi2/dof"], rows))
    with open(os.path.join(out_dir, "2_fit_report.txt"), "w") as f:
        f.write("\n".join(report))
    print(f"report saved to {out_dir}/2_fit_report.txt")


def plot_part_b(corr2, mass, fits, out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x_vals = np.arange(DT_MAX)
    title = (f"L24x72 proton P0/P2, Nconf={corr2['P0'].shape[0]}, "
             f"jackknife, fit window [{FIT_START},{FIT_END}]")

    # 图 B2: eff_mass.png（aE 对比）
    eff_data = {ch: (mass[ch].mean(0), sem(mass[ch], True)) for ch in CHANNELS}
    plot_errbar(x_vals, eff_data, save_path=os.path.join(out_dir, "eff_mass.png"),
                xlabel="t/a", ylabel="aE", xlim=XLIM, ylim=YLIM_AE,
                x_offset=X_OFFSET, title=title)

    # 图 B3: sem_comparison.png
    t_sem = 15
    plot_scatter(np.arange(t_sem),
                 {ch: sem(mass[ch], True)[:t_sem] for ch in CHANNELS},
                 save_path=os.path.join(out_dir, "sem_comparison.png"),
                 xlabel="t/a", ylabel="SEM(aE)", xlim=XLIM, ylim=SEM_YLIM,
                 x_offset=X_OFFSET, title=title)

    # 图 B4: eff_mass_GeV.png（GeV + 双通道各自 E0 色带）
    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
    band_x = np.array([FIT_START, FIT_END])
    for k, ch in enumerate(CHANNELS):
        r = fits[ch]
        ok = np.isfinite(r["E0"])
        e0 = np.nanmean(r["E0"]) * UNIT
        e0e = sem(r["E0"][ok], True) * UNIT
        c = DEFAULT_PLOT_COLORS[k]
        ax.errorbar(x_vals + k * X_OFFSET, mass[ch].mean(0) * UNIT,
                    yerr=sem(mass[ch], True) * UNIT, fmt="x", color=c,
                    ecolor=c, capsize=0, label=f"{ch}")
        ax.fill_between(band_x, [e0 - e0e] * 2, [e0 + e0e] * 2,
                        color="gray", alpha=0.35, linewidth=0,
                        label=f"E0[{ch}]={e0:.3f}")
        ax.axhline(e0, color=c, ls="--", lw=0.8)
    chi2s = ", ".join(
        f"{ch}={np.nanmean(fits[ch]['chi2']):.2f}" for ch in CHANNELS)
    ax.set_xlim(XLIM)
    ax.set_ylim(YLIM_GEV)
    ax.set_xlabel("t/a")
    ax.set_ylabel("eff mass (GeV)")
    ax.set_title(f"{title}\nchi2/dof: {chi2s}")
    ax.legend(loc="upper right", fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "eff_mass_GeV.png"), bbox_inches="tight")
    plt.close(fig)
    print("eff_mass_GeV.png done")

    # 图 B5: eff_mass_fit_dirs.png（逐通道面板 + 各自色带；2 通道，1x2 版式）
    fig, axes = plt.subplots(1, len(CHANNELS), figsize=(12, 5), dpi=150)
    for k, (ch, ax) in enumerate(zip(CHANNELS, np.atleast_1d(axes))):
        r = fits[ch]
        ok = np.isfinite(r["E0"])
        e0 = np.nanmean(r["E0"]) * UNIT
        e0e = sem(r["E0"][ok], True) * UNIT
        c = DEFAULT_PLOT_COLORS[k]
        ax.errorbar(x_vals, mass[ch].mean(0) * UNIT,
                    yerr=sem(mass[ch], True) * UNIT, fmt="x", color=c,
                    ecolor=c, capsize=0, markersize=6, label=f"{ch} ch")
        ax.fill_between(band_x, [e0 - e0e] * 2, [e0 + e0e] * 2,
                        color="gray", alpha=0.35, linewidth=0,
                        label=f"Fit E0={e0:.3f}")
        ax.set_xlim(XLIM)
        ax.set_ylim(YLIM_GEV)
        ax.set_xlabel("t/a")
        ax.set_ylabel("eff mass (GeV)")
        ax.set_title(f"{ch} channel (P={MOM_LABEL[ch]})")
        ax.legend(fontsize=8)
    fig.suptitle(title, fontsize=13)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "eff_mass_fit_dirs.png"),
                bbox_inches="tight")
    plt.close(fig)
    print("eff_mass_fit_dirs.png done")

    # 图 B1: corr2_raw.png（log|C| 对比）
    logc = {ch: (np.log(np.abs(corr2[ch])).mean(0),
                 sem(np.log(np.abs(corr2[ch])), True)) for ch in CHANNELS}
    plot_errbar(x_vals, logc, save_path=os.path.join(out_dir, "corr2_raw.png"),
                xlabel="t/a", ylabel="log|C(t)|", xlim=XLIM,
                x_offset=X_OFFSET, title=title)
    print("corr2_raw.png done")

    # 图 B6: meff_corr.png（通道间 meff 相关系数矩阵 @ dt_ref，参考 05_ana_3dir）
    arr = np.column_stack([mass[ch][:, DT_REF] for ch in CHANNELS])
    cov, cond = cov_mat(arr, True)
    diag = np.sqrt(np.diag(cov))
    corr = cov / np.outer(diag, diag)
    n = len(CHANNELS)
    fig, ax = plt.subplots(figsize=(5.5, 4.8), dpi=150)
    im = ax.imshow(corr, cmap="coolwarm", vmin=-1, vmax=1)
    for i in range(n):
        for j in range(n):
            ax.text(j, i, f"{corr[i, j]:.3f}", ha="center", va="center",
                    color="white" if abs(corr[i, j]) > 0.5 else "black")
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(CHANNELS)
    ax.set_yticklabels(CHANNELS)
    ax.set_title(f"meff corr matrix @ t={DT_REF}\ncond={cond:.1f}")
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "meff_corr.png"), bbox_inches="tight")
    plt.close(fig)
    print("meff_corr.png done")

    # 图 B7: meff_hist.png（各通道直方图 @ dt_ref，mean+/-sem 标注）
    fig, axes = plt.subplots(1, len(CHANNELS), figsize=(12, 5), dpi=150)
    for k, (ch, ax) in enumerate(zip(CHANNELS, np.atleast_1d(axes))):
        vals = mass[ch][:, DT_REF]
        ax.hist(vals, bins=min(30, vals.size), color=DEFAULT_PLOT_COLORS[k],
                alpha=0.7)
        ax.axvline(vals.mean(), color="black", ls="--", lw=1)
        ax.set_title(f"{ch}: {vals.mean():.3f}"
                     f"({sem(vals, True) * 1e3:.0f})")
        ax.set_xlabel("aE")
    fig.suptitle(f"meff @ t={DT_REF} (mean+/-sem)", fontsize=13)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "meff_hist.png"), bbox_inches="tight")
    plt.close(fig)
    print("meff_hist.png done")


# ===== Part A：docker/test0 型 all_channels 图（与 dev6 同逻辑）=====

def part_a(raw, conf_ids, out_dir):
    """run_meff_jackknife -> correlators/meff all_channels（docker 风格）。"""
    print("==================== Part A（test0 型 all_channels）====================")
    corr_2pt_all = {cid: {"corr_pp_P0": raw["P0"][i],
                          "corr_pp_P2": raw["P2"][i]}
                    for i, cid in enumerate(conf_ids)}
    t0 = time.perf_counter()
    meff_res = run_meff_jackknife(corr_2pt_all, conf_ids, NT=NT, ALttc=ALTTc)
    print(f"run_meff_jackknife done ({time.perf_counter() - t0:.1f}s)")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    grid = [("proton", "P0"), ("proton", "P2"),
            ("pion", "P0"), ("pion", "P2")]
    have = {f"{particle}_{mom}" for particle, mom in grid} & set(meff_res)

    # A1: correlators_all_channels.png（|C| log-y，docker 风格 2x2）
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    for ax, (particle, mom) in zip(axes.ravel(), grid):
        res = meff_res.get(f"{particle}_{mom}")
        if res is None:
            ax.text(0.5, 0.5, f"{particle} {mom}\nno data\n(channel absent in input)",
                    ha="center", va="center", transform=ax.transAxes,
                    fontsize=11, color="gray")
            continue
        c, ce = res["corr_mean"], res["corr_err"]
        t = np.arange(len(c))
        ax.errorbar(t, np.abs(c), yerr=ce, fmt=".", ms=4, capsize=0)
        ax.set_yscale("log")
        ax.set_title(f'{particle} P={mom}  C(0)={c[0]:.4e}')
        ax.set_xlabel("t")
        ax.set_ylabel("|C(t)|")
        ax.grid(alpha=0.3, which="both")
    fig.suptitle(f"2pt correlators (Jackknife mean, {len(conf_ids)} configs)")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "correlators_all_channels.png"), dpi=150)
    plt.close(fig)
    print("correlators_all_channels.png done")

    # A2: meff_all_channels.png（平台窗 + E0/E_exp 参考线，docker 风格）
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    for ax, (particle, mom) in zip(axes.ravel(), grid):
        res = meff_res.get(f"{particle}_{mom}")
        if res is None:
            ax.text(0.5, 0.5, f"{particle} {mom}\nno data\n(channel absent in input)",
                    ha="center", va="center", transform=ax.transAxes,
                    fontsize=11, color="gray")
            continue
        m, e = res["meff_mean"], res["meff_err"]
        t = np.arange(len(m))
        ps, pe = res["plateau"]
        ax.errorbar(t, m, yerr=e, fmt="o", ms=4, capsize=2)
        ax.axvspan(ps, pe - 1, alpha=0.15, color="C1")
        ax.axhline(res["E0"], color="C3", ls="--", lw=1)
        ax.axhline(res.get("E_exp", 0), color="C4", ls=":", lw=1)
        ax.set_title(f'{particle} P={mom}  E0={res["E0"]:.3f}'
                     f'+/-{res["E0_err"]:.3f} (exp {res.get("E_exp", 0):.2f})')
        ax.set_xlabel("t")
        ax.set_ylabel(r"$m_{\rm eff}$ [GeV]")
        ax.grid(alpha=0.3)
    fig.suptitle(f"Effective masses (Jackknife, {len(conf_ids)} configs)")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "meff_all_channels.png"), dpi=150)
    plt.close(fig)
    print("meff_all_channels.png done")
    return meff_res, sorted(have)


# ===== Part C：02_ratio 链 -> ratio_3pt 型图（dev7 新增，补 dev6 缺口）=====

def stage_ratio_input(data_root, stage_root, conf_ids):
    """整理 run_ratio2pt 所需布局（照抄 logs/test8/main.py make_data L3 整理段）：

    {stage}/{CONF_NAME}/momsmear2z/{cid}/twopt_slice_pp_Px0Py0Pz2_*.npy
        —— corr_pp_P2 (Nt,) -> 平移不变切片矩阵 C[sink,src]=C((sink-src) mod Nt)
    {stage}/{CONF_SHORT}/zdir/{cid}/ops_mu{a}_nu{b}_dz24_conf{cid}.npz
        —— 数据源已有同名 npz，符号链接复用（零拷贝）
    """
    t0 = time.perf_counter()
    for i, cid in enumerate(conf_ids):
        corr = np.load(os.path.join(
            data_root, f"conf{cid}", f"corr_pp_P{RATIO_PZ}_{cid}.npy"))
        assert corr.shape == (NT,), f"corr shape {corr.shape}"
        full = np.empty((NT, NT), dtype=np.float64)
        idx = np.arange(NT)
        for src_t in range(NT):
            full[:, src_t] = corr[(idx - src_t) % NT]
        d = os.path.join(stage_root, CONF_NAME, "momsmear2z", str(cid))
        os.makedirs(d, exist_ok=True)
        np.save(os.path.join(
            d, f"twopt_slice_pp_Px0Py0Pz{RATIO_PZ}"
               f"_eginphase2_Cg5g4_nopol_ss_conf{cid}.npy"), full)

        d = os.path.join(stage_root, CONF_SHORT, "zdir", str(cid))
        os.makedirs(d, exist_ok=True)
        for mu, nu in [(0, 1), (3, 0), (3, 1)]:
            src = os.path.join(
                data_root, f"conf{cid}",
                f"ops_mu{mu}_nu{nu}_dz{NX}_conf{cid}.npz")
            dst = os.path.join(
                d, f"ops_mu{mu}_nu{nu}_dz{NX}_conf{cid}.npz")
            if not os.path.exists(dst):
                os.symlink(os.path.abspath(src), dst)
        if (i + 1) % 100 == 0 or i + 1 == len(conf_ids):
            print(f"  stage {i + 1}/{len(conf_ids)} "
                  f"({time.perf_counter() - t0:.1f}s)")
    return stage_root


def part_c(data_root, conf_ids, out_dir):
    """02_ratio 链（run_ratio2pt）-> ratio 数组/逐 z 拟合/ratio_3pt 汇总图。"""
    print("==================== Part C（02_ratio 链 -> ratio_3pt 型）====================")
    import gvar as gv
    stage_root = os.path.join(out_dir, "input_stage")
    stage_ratio_input(data_root, stage_root, conf_ids)

    sampa = SampleParams2pt(
        conf_short=CONF_SHORT, conf_name=CONF_NAME, conf_ids=list(conf_ids),
        Nt=NT, Nx=NX, Px=0, Py=0, Pz=RATIO_PZ,
        Nsample=len(conf_ids), dt_max=RATIO_DT_MAX)
    prior = {k: gv.gvar(*v) for k, v in FIT_PRIOR.items()}
    fitpa_list = [FitParams(p0=dict(FIT_P0), prior=dict(prior),
                            dt_start=a, dt_end=b, nex=c, svdcut=SVD_CUT)
                  for a, b, c in FIT_WINDOWS]
    plotpa = PlotParamsRatio(
        plot_z=PLOT_Z, dt_list=list(range(5, 14)),
        z_list=list(range(0, NX, 4)),
        xlim=[-7, 7], ylim=[-0.5, 1.0], c0_ylim=[-0.3, 1.0])

    t0 = time.perf_counter()
    res = run_ratio2pt(stage_root, out_dir, sampa, fitpa_list, plotpa,
                       jack=True, parts=(1, 3), verbose=True)
    ratio = res["ratio"]
    print(f"run_ratio2pt done ({time.perf_counter() - t0:.1f}s), "
          f"ratio shape {ratio.shape}")

    primary_key = fit_dir_name_local(sampa, fitpa_list[0])
    fr = res["fit_results"][primary_key]
    plot_ratio_summary(ratio, fr, sampa, out_dir)
    c0m, c0e = ratio_c0_stats(fr)
    return {
        "ratio_shape": list(ratio.shape),
        "windows": [list(w) for w in FIT_WINDOWS],
        "primary_fit_dir": primary_key,
        "c0_mean_z": c0m.tolist(),
        "c0_err_z": c0e.tolist(),
        "chi2_mean_z": fr["chi2"].mean(0).tolist(),
    }


def fit_dir_name_local(sampa, fitpa):
    """fit 目录名（与 _ratio2pt.fit_dir_name 一致，避免私有依赖）。"""
    return (f"fit_Pz{sampa.Pz}_Nsam{sampa.Nsample}_dtmax{sampa.dt_max}"
            f"_tsep{fitpa.dt_start}_{fitpa.dt_end}_nex{fitpa.nex}")


def ratio_c0_stats(fr):
    """主窗口 c0 的 mean/sem（对样本轴，与 02 链 plot 路径同口径）。"""
    c0 = fr["c0"]
    return c0.mean(0), sem(c0, True)


def plot_ratio_summary(ratio, fr, sampa, out_dir):
    """test0 型 ratio_3pt_all_channels.png：2x2 面板 R(tau) @ t_sep=T_SEP_SUM。

    面板通道 = 算符长度 z in  Z_PANELS（docker 版为 hadronxmomentum 通道；
    本数据为单强子单动量的 disconnected OPE 比值，以 z 为通道索引——
    物理语义在图题明注）。
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rmean = ratio.mean(0)
    rerr = sem(ratio, True)
    c0m, c0e = ratio_c0_stats(fr)
    chi2m = fr["chi2"].mean(0)

    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    dt = T_SEP_SUM
    tau = np.arange(dt + 1)
    x_vals = tau - dt / 2.0
    for ax, z in zip(axes.ravel(), Z_PANELS):
        ax.errorbar(x_vals, rmean[dt, tau, z], yerr=rerr[dt, tau, z],
                    fmt="o", ms=4, capsize=2, label=f"z={z}")
        ax.fill_between([-dt / 2, dt / 2],
                        [c0m[z] - c0e[z]] * 2, [c0m[z] + c0e[z]] * 2,
                        color="gray", alpha=0.35, linewidth=0,
                        label=f"c0={c0m[z]:.3f}({c0e[z] * 1e3:.0f})")
        ax.axhline(0, color="gray", lw=0.8)
        ax.axhline(1, color="k", ls="--", lw=0.8)
        ax.set_title(f"z={z}  c0={c0m[z]:.3f}({c0e[z] * 1e3:.0f})  "
                     f"chi2/dof={chi2m[z]:.2f}")
        ax.set_xlabel(r"$\tau - t_{sep}/2$")
        ax.set_ylabel(r"$R(\tau) = C_{\rm OPE}/C_{2pt}$")
        ax.set_xlim(-dt / 2 - 0.5, dt / 2 + 0.5)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle(
        "Disconnected gluon-OPE/2pt ratios R(tau) "
        "(O=-O30-O31+2*O01, no perambulators)\n"
        f"L24x72 proton P=(0,0,{sampa.Pz}), Nconf={sampa.Nconf}, "
        f"t_sep={dt}, vacuum-subtracted (pyqcd 02_ratio chain)")
    fig.tight_layout()
    fp = os.path.join(out_dir, "ratio_3pt_all_channels.png")
    fig.savefig(fp, dpi=150)
    plt.close(fig)
    print(f"ratio_3pt_all_channels.png done -> {fp}")


# ===== 主流程 =====

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", default=DATA_ROOT)
    ap.add_argument("--n-conf", type=int, default=0, help="取前 N 个组态")
    ap.add_argument("--conf-ids", default="", help="逗号分隔覆盖组态")
    ap.add_argument("--outdir", default="", help="输出目录（默认 run_<ts>）")
    ap.add_argument("--debug", action="store_true", help="前 5 组态 -> debug/")
    ap.add_argument("--skip-ratio", action="store_true",
                    help="跳过 Part C（02_ratio 链，调试用）")
    args = ap.parse_args()

    conf_ids = ([int(x) for x in args.conf_ids.split(",")] if args.conf_ids
                else scan_conf_ids(args.data_root))
    if args.debug:
        conf_ids = conf_ids[:5]
    elif args.n_conf > 0:
        conf_ids = conf_ids[:args.n_conf]
    if not conf_ids:
        print("[error] 输入目录未发现 corr_pp_P0/P2+ops 齐全组态")
        return 1

    base = "debug" if args.debug else (
        args.outdir or f"run_{time.strftime('%Y%m%d%H%M')}")
    out_dir = os.path.join(OUTPUT_ROOT, base)
    os.makedirs(out_dir, exist_ok=True)

    print(f"data_root: {args.data_root}")
    print(f"Nconf: {len(conf_ids)}  range: [{conf_ids[0]}, {conf_ids[-1]}]")
    print(f"out_dir: {out_dir}")

    t_all = time.perf_counter()
    raw = load_raw(args.data_root, conf_ids)
    print(f"load done ({time.perf_counter() - t_all:.1f}s), "
          f"shapes: {{ch: {raw['P0'].shape}}}")

    _, _, fits_b = part_b(raw, out_dir)
    meff_res, have = part_a(raw, conf_ids, out_dir)

    part_c_res = None
    if not args.skip_ratio:
        part_c_res = part_c(args.data_root, conf_ids, out_dir)

    p_phys = (2 * np.pi * RATIO_PZ / NX) * UNIT
    summary = {
        "task": "effective-mass spectrum and OPE ratio plots",
        "data_root": args.data_root,
        "Nconf": len(conf_ids),
        "conf_range": [conf_ids[0], conf_ids[-1]],
        "nconf_note": (
            "组态按实际存在扫描（corr_pp_P0/P2+ops 三分量齐全）；"
            "数据目录可能在历史运行后被外部删减，"
            "本运行不假设网格"),
        "channels": {ch: MOM_LABEL[ch] for ch in CHANNELS},
        "unit_GeV": UNIT,
        "part_a": {k: {"E0_GeV": v["E0"], "E0_err": v["E0_err"],
                       "E_exp": v.get("E_exp"), "dev": v.get("dev"),
                       "plateau": v.get("plateau")}
                   for k, v in meff_res.items()},
        "part_b": {ch: {"E0_lattice": float(np.nanmean(fits_b[ch]["E0"])),
                        "E0_GeV": float(np.nanmean(fits_b[ch]["E0"]) * UNIT),
                        "chi2_dof": float(np.nanmean(fits_b[ch]["chi2"]))}
                   for ch in CHANNELS},
        "part_c": part_c_res,
        "p_phys_P2_GeV": p_phys,
        "plots_expected_missing": [],
        "channels_analyzed": have,
    }
    with open(os.path.join(out_dir, "analysis_summary.json"), "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\nPeak Memory: {get_peak_memory_gb():.3f} GB")
    print(f"total time: {time.perf_counter() - t_all:.1f}s")
    print(f"job finish -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
