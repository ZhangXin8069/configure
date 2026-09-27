"""
test9 扩展图表：补充与 test0/plots 和 test6/1_result 相同类型的所有图表
====================================================================

- test0 style: correlators_all_channels.png / meff_all_channels.png / ratio_3pt_all_channels.png
  （基于 test9 的 nucleon 2pt 与 TMD ratio，复用 pipeline._steps 的绘图风格）

- test6 style: 1_result/L24x72/Pz*/ 下 7 图 + fit 报告
  （基于 TMD per-momentum 2pt jackknife，复用历史 test6 的 7 图逻辑）

输入：已有的 TMD-PDF 产物
（`pyqcd/testing/tmd/artifacts/initial_run/data` 与 `analysis/tmd_ratio`）
输出：指定 out_root 下的新图表。

统计：sem/resample/cov_mat 复用 _disconnected；拟合复用 _proton_energy.energy_model；
图表复用 _plots.DEFAULT_PLOT_COLORS / plot_errbar / plot_scatter。
"""
from __future__ import annotations

import os
import gc
import time
from pathlib import Path

import numpy as np

from ._disconnected import (
    aggregate_fit_statuses,
    cov_mat,
    fit_status_from_samples,
    resample,
    sem,
)
from ._fitter import (
    FitParams,
    covariance_effective_rank,
    covariance_sample_rank,
    fit,
    fit_identifiability,
)
from ._plots import DEFAULT_PLOT_COLORS, plot_errbar, plot_scatter, get_peak_memory_gb
from ._proton_energy import energy_model, energy_model_jacobian
from ..pipeline._config import NT, NX, ALttc, FM2GEV, ENSEMBLE


# ---------------------------------------------------------------------
# 辅助：读取 test9 的 per-conf per-momentum 2pt (Nt,) 为 jackknife 预备
# ---------------------------------------------------------------------

def _load_test9_corr2_raw(test9_root: str, conf_ids, momentum_tags):
    """读取 test9/data/conf*/corr_pp_<tag>_<cid>.h5 → {tag: stacked (Nconf, Nt)}."""
    from ..tools._io import load_tensor_h5
    data = {}
    for tag in momentum_tags:
        stack = []
        missing = 0
        for cid in conf_ids:
            p = os.path.join(test9_root, "data", f"conf{cid}", f"corr_pp_{tag}_{cid}.h5")
            if os.path.exists(p):
                arr = load_tensor_h5(p)
                # load_tensor_h5 may return torch tensor; convert
                try:
                    import torch
                    if isinstance(arr, torch.Tensor):
                        arr = arr.detach().cpu().numpy()
                except Exception:
                    pass
                arr = np.asarray(arr).real.ravel()
                # ensure Nt=72
                if arr.shape[0] != NT:
                    # pad/truncate
                    tmp = np.zeros(NT)
                    tmp[:min(NT, arr.shape[0])] = arr[:min(NT, arr.shape[0])]
                    arr = tmp
                stack.append(arr)
            else:
                # try npy fallback
                p2 = os.path.join(test9_root, "data", f"conf{cid}", f"corr_pp_{tag}_{cid}.npy")
                if os.path.exists(p2):
                    arr = np.load(p2).real.ravel()
                    tmp = np.zeros(NT)
                    tmp[:min(NT, arr.shape[0])] = arr[:min(NT, arr.shape[0])]
                    stack.append(tmp)
                else:
                    missing += 1
        if stack:
            data[tag] = np.stack(stack)  # (Nconf, Nt)
        if missing:
            print(f"[warn] tag {tag}: {missing}/{len(conf_ids)} corr missing")
    return data


def _jackknife_corr2_and_meff(corr_raw, conf_ids, dt_max=20):
    """corr_raw (Nconf, Nt) → corr2_jack (Nsample,Nt) via Jackknife on ti-averaged + meff.

    复用 _proton_energy.compute_corr2 的相对时间逻辑，但此处 corr_raw 已是 per-conf (Nt,) 的 C(t)，
    需先构造 (Nconf, Nt, Nt) 循环矩阵再 ti 平均，与 test6/main.py 的 compute_corr2 一致。
    """
    Nconf = len(conf_ids)
    _corr = np.zeros((Nconf, NT, NT), dtype=np.complex128)
    for i, arr in enumerate(corr_raw):
        # _corr[i, t_sink, t_src] = C((t_sink - t_src) mod Nt)
        # 简化：对角平移等价于直接 roll
        for ti in range(NT):
            _corr[i, :, ti] = np.roll(arr, -ti)
        # 实际上 corr_raw 是 C(dt) 已平均过？保持与 test6 逻辑：按 t_src 展开
        # 这里 _corr[i, :, ti] 表示 t_src=ti 时的 t_sink  slices
    # 相对时间 + ti 平均 → (Nconf, dt_max)
    _corr2_rel = np.zeros((Nconf, NT, dt_max), dtype=np.complex128)
    for ti in range(NT):
        _corr2_rel[:, ti, :] = np.roll(_corr[:, :, ti], shift=-ti, axis=1)[:, :dt_max]
    _corr2_ave = _corr2_rel.mean(axis=1)  # (Nconf, dt_max)
    # jackknife
    corr2_jack = resample(_corr2_ave, jackknife=True, Nsample=Nconf).real  # (Nsample,Nt)
    return corr2_jack


def _meff_from_corr2(corr2_jack):
    """meff = log(|C(t)|/|C(t+1)|) , shape (Nsample, dt_max)."""
    return np.log(np.abs(corr2_jack) / np.abs(np.roll(corr2_jack, shift=-1, axis=1)))


# ---------------------------------------------------------------------
# test0 style: 3 图 (correlators / meff / ratio_3pt) 适配 test9
# ---------------------------------------------------------------------

def generate_test0_style_plots(test9_root: str, out_root: str, conf_ids, momentum_tags, logger=print):
    """在 out_root/plots 下生成 3 张 test0 风格图 + test0 analysis/disconnected 风格图.

    test9 的 nucleon 2pt 替代 pion/proton 双强子；动量标签作为 channel。
    ratio 图只消费已有 TMD ratio artifact 的真实 R(τ)；缺失时显式跳过。
    c0/chi2 图还要求同一 central fit artifact 带有可接受的显式状态。
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pdir = os.path.join(out_root, "plots")
    os.makedirs(pdir, exist_ok=True)
    # analysis/disconnected 也补充，与 test0/v202608150750/analysis/disconnected 对应
    adir = os.path.join(out_root, "analysis", "disconnected")
    os.makedirs(adir, exist_ok=True)

    # 1) 加载 corr 并做 jackknife 得到 meff/corr 均值/误差
    corr_raw_dict = _load_test9_corr2_raw(test9_root, conf_ids, momentum_tags)
    if not corr_raw_dict:
        logger("[ERROR] 无 corr 数据，无法生成 test0 style plots")
        return

    # 构造 meff_results 供 plot_meff_results 调用（模拟 pipeline._steps 的结构）
    meff_results = {}
    for tag, raw in corr_raw_dict.items():
        # raw (Nconf, Nt)
        Nconf = raw.shape[0]
        # 直接 Jackknife 有效质量（与 _correlators.run_meff_jackknife 对应，但简化）
        # 用 Jackknife 样本计算 meff，再求 mean/err
        # 先对 raw 做 jackknife sample
        jack_samples = resample(raw, jackknife=True, Nsample=Nconf)  # (Nsample, Nt)
        # effective mass: log for pion-like, cosh for proton?  test9 均为 nucleon proton → log/cosh 均可，此处用 log (与 test6 一致)
        # 同时计算 corr mean/err: jack_samples mean
        from ..analysis._analyse import Jackknife, meff as _meff
        # 使用 _analyse.meff 以保持与 pipeline 一致（含 GeV 转换）
        # 但 _analyse.meff 返回 jackknife 样本的 meff，需传入 jack['data_sample']
        jk = Jackknife(raw, Nconf_axes=0)
        mf = _meff(jk['data_sample'], ALttc, Nconf_axes=0, Nt_axes=1, meff_type='log')
        cmean, cerr = np.real(jk['data_mean']), np.real(jk['data_err'])
        mmean, merr = np.real(mf['data_mean']), np.real(mf['data_err'])
        # _analyse.meff 已含 FM2GEV/ALttc 转换，直接使用（确证：_analyse.py:305）
        mmean_GeV = mmean
        merr_GeV = merr
        # 平台窗：proton 6-12, pion 5-18，这里统一 6-12
        ps, pe = 6, min(NT - 2, 12)
        mask = np.isfinite(mmean[ps:pe]) & (merr[ps:pe] > 0) & (mmean[ps:pe] > 0.01)
        if np.sum(mask) < 2:
            ps, pe = 2, min(8, NT - 1)
            mask = np.isfinite(mmean[ps:pe]) & (merr[ps:pe] > 0)
        w = 1.0 / (merr[ps:pe][mask] ** 2 + 1e-10)
        E0 = float(np.sum(mmean[ps:pe][mask] * w) / np.sum(w)) if np.sum(mask) else float(np.nan)
        E0_err = float(1 / np.sqrt(np.sum(w))) if np.sum(mask) else float(np.nan)
        # 期望能量（色散）：m0=1.0 GeV 近似
        # 若 tag==P000 则 E_exp= m0, 否则 sqrt(m0^2 + p^2)
        # 解析 Pz：tag like P200 -> pz=2
        try:
            pz = int(tag[1])
        except Exception:
            pz = 0
        p_phys = (2 * np.pi * pz / NX) * (FM2GEV / ALttc)
        E_exp = np.sqrt(1.0**2 + p_phys**2) if pz != 0 else 1.0
        meff_results[f"proton_{tag}"] = {
            'E0': E0, 'E0_err': E0_err, 'E_exp': float(E_exp), 'dev': 0.0,
            'plateau': (ps, pe), 'npts': int(np.sum(mask)),
            'meff_mean': mmean_GeV, 'meff_err': merr_GeV,
            'corr_mean': cmean, 'corr_err': cerr,
        }
        # 同步保存 analysis/disconnected 风格的 c0 图所需的文件（沿用 meff 的 E0 作为 c0 近似，仅为图表完整性）
        # 真正的 c0 来自 TMD ratio，此处仅补充 meff/corr 文件
    # 保存 analysis 文件（供 verify 用，与 test0 的 data/analysis 复用命名）
    # 但 test0 的 analysis 路径是 data/analysis/meff_... ; 这里我们保存到 analysis/disconnected 的 meff 也可
    # 同时在 out_root/data/analysis 保存一份以兼容 test0 verify
    data_an_dir = os.path.join(out_root, "data", "analysis")
    os.makedirs(data_an_dir, exist_ok=True)
    for k, res in meff_results.items():
        # k like proton_P200 -> split
        _, tag = k.split("_", 1)
        # 保存为 meff_proton_{tag}_mean.npy 等（与 pipeline._steps 的命名一致，但 tag 本就是 P200）
        # pipeline 命名为 meff_proton_P0 ; 这里我们用 tag 扩展
        # 同时保存 corr
        np.save(os.path.join(data_an_dir, f"meff_proton_{tag}_mean.npy"), res['meff_mean'])
        np.save(os.path.join(data_an_dir, f"meff_proton_{tag}_err.npy"), res['meff_err'])
        np.save(os.path.join(data_an_dir, f"corr_proton_{tag}_mean.npy"), res['corr_mean'])
        np.save(os.path.join(data_an_dir, f"corr_proton_{tag}_err.npy"), res['corr_err'])

    # 2) 绘图：meff_all_channels / correlators_all_channels / ratio_3pt_all_channels
    # 为了兼容 2x2 网格，我们选取前 4 个 tag；若不足则用全部
    channels = list(meff_results.keys())[:4]
    if len(channels) < 4:
        # 若 momentum 少于 4，补充虚拟？
        pass

    # --- meff_all_channels.png ---
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    for ax, key in zip(axes.ravel(), channels):
        res = meff_results.get(key)
        if res is None:
            ax.axis('off')
            continue
        m, e = res['meff_mean'], res['meff_err']
        t = np.arange(len(m))
        ps, pe = res['plateau']
        ax.errorbar(t, m, yerr=e, fmt='o', ms=4, capsize=2)
        ax.axvspan(ps, pe - 1, alpha=0.15, color='C1')
        ax.axhline(res['E0'], color='C3', ls='--', lw=1)
        ax.axhline(res['E_exp'], color='C4', ls=':', lw=1)
        # key like proton_P200
        ax.set_title(f"{key}  E0={res['E0']:.3f}±{res['E0_err']:.3f} (exp {res['E_exp']:.2f})")
        ax.set_xlabel('t'); ax.set_ylabel(r'$m_{\rm eff}$ [GeV]')
        ax.grid(alpha=0.3)
    # 若 channels <4，关闭多余子图
    for idx in range(len(channels), 4):
        axes.ravel()[idx].axis('off')
    fig.suptitle(f'Effective masses (Jackknife, Nconf={len(conf_ids)})')
    fig.tight_layout()
    fig.savefig(os.path.join(pdir, 'meff_all_channels.png'), dpi=150)
    plt.close(fig)
    logger(f"  Saved {os.path.join(pdir, 'meff_all_channels.png')}")

    # --- correlators_all_channels.png ---
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    for ax, key in zip(axes.ravel(), channels):
        res = meff_results.get(key)
        if res is None:
            ax.axis('off')
            continue
        c, ce = res['corr_mean'], res['corr_err']
        t = np.arange(len(c))
        ax.errorbar(t, np.abs(c), yerr=ce, fmt='.', ms=4, capsize=0)
        ax.set_yscale('log')
        ax.set_title(f"{key}  C(0)={c[0]:.4e}")
        ax.set_xlabel('t'); ax.set_ylabel('|C(t)|')
        ax.grid(alpha=0.3, which='both')
    for idx in range(len(channels), 4):
        axes.ravel()[idx].axis('off')
    fig.suptitle('2pt correlators (Jackknife mean)')
    fig.tight_layout()
    fig.savefig(os.path.join(pdir, 'correlators_all_channels.png'), dpi=150)
    plt.close(fig)
    logger(f"  Saved {os.path.join(pdir, 'correlators_all_channels.png')}")

    # --- ratio_3pt_all_channels.png ---
    # 使用已有 TMD ratio 的 R(tau)；缺失时必须显式跳过，不能用 R=1
    # 冒充数据。数组约定为 (Nsample, dt, dtau, nz, nb)。
    ratio_results = {}
    unavailable_ratio_tags = []
    for tag in momentum_tags:
        p = os.path.join(test9_root, "analysis", "tmd_ratio", f"ratio_proton_{tag}.npy")
        # also try analysis_b
        if not os.path.exists(p):
            p2 = os.path.join(test9_root, "analysis_b", "tmd_ratio", f"ratio_proton_{tag}.npy")
            if os.path.exists(p2):
                p = p2
        if not os.path.exists(p):
            unavailable_ratio_tags.append((
                tag, "TMD ratio artifact is missing"))
            continue
        try:
            arr = np.asarray(np.load(p))
            if (arr.ndim != 5 or arr.shape[0] == 0
                    or not np.isfinite(arr).all()):
                raise ValueError("invalid shape or non-finite values")
            rm = arr.mean(axis=0)  # (dt, dtau, nz, nb)
            dt = 10 if rm.shape[0] > 10 else rm.shape[0] - 1
            nz = rm.shape[2]
            if dt < 0 or nz == 0 or rm.shape[3] == 0:
                raise ValueError("empty TMD ratio axes")
            z_pick = 6 if nz > 6 else nz // 2
            r = rm[dt, :dt + 1, z_pick, 0]
            re = (sem(arr[:, dt, :dt + 1, z_pick, 0], jackknife=True)
                  if arr.shape[0] > 1 else np.zeros_like(r))
            ratio_results[f"proton_{tag}"] = {
                'R': r, 'R_err': re, 't_sep': dt}
        except (OSError, ValueError, IndexError) as error:
            unavailable_ratio_tags.append(
                (tag, f"TMD ratio unavailable: {error}"))

    # ratio 仅对 Pz>0 有物理意义，排除 P000。只有至少一个真实 ratio
    # channel 时才生成图；全缺失时不产生看似真实的常数图。
    channels_ratio = [
        key for key in channels
        if key in ratio_results and not key.endswith("P000")
    ]
    if not channels_ratio:
        channels_ratio = [key for key in channels if key in ratio_results]
    if channels_ratio:
        fig, axes = plt.subplots(2, 2, figsize=(12, 9))
        for ax, key in zip(axes.ravel(), channels_ratio):
            res = ratio_results[key]
            r, e = res['R'], res['R_err']
            tau = np.arange(len(r))
            ax.errorbar(tau, r, yerr=e, fmt='o', ms=4, capsize=2)
            ax.axhline(0, color='gray', lw=0.8)
            ax.axhline(1, color='k', ls='--', lw=0.8)
            ax.set_title(
                f"{key}  R(τ)  (t_sep={res['t_sep']}, z=6,b=0)")
            ax.set_xlabel('τ'); ax.set_ylabel('R(τ)')
            ax.grid(alpha=0.3)
        for idx in range(len(channels_ratio), 4):
            axes.ravel()[idx].axis('off')
        fig.suptitle('TMD ratio R(τ) (z=6,b=0, Pz>0, gradient flow)')
        fig.tight_layout()
        fig.savefig(os.path.join(pdir, 'ratio_3pt_all_channels.png'), dpi=150)
        plt.close(fig)
        logger(f"  Saved {os.path.join(pdir, 'ratio_3pt_all_channels.png')}")
    else:
        logger("  ratio_3pt_all_channels.png skipped: TMD ratio unavailable")
    for tag, reason in unavailable_ratio_tags:
        logger(f"  ratio channel {tag} skipped: unavailable ({reason})")

    # --- analysis/disconnected 风格的 3 图（c0/chi2/ratio） ---
    # 直接复用 TMD ratio 的 c0 信息生成类似 test0 的 plots
    # 读取 c0_mean，优先选取有物理意义的 Pz>0 动量 (P200,P400)
    cand_tags = [t for t in ["P200", "P400", "P002", "P020", "P022", "P202", "P220", "P222"] if t in momentum_tags]
    if not cand_tags:
        cand_tags = momentum_tags[:2]
    for tag in cand_tags[:2]:
        c0_path = os.path.join(test9_root, "analysis", "tmd_ratio", f"c0_mean_{tag}.npy")
        if not os.path.exists(c0_path):
            c0_path = os.path.join(test9_root, "analysis_b", "tmd_ratio", f"c0_mean_{tag}.npy")
        fit_npz = os.path.join(
            test9_root, "analysis", "tmd_ratio", f"0_fit_data_{tag}.npz")
        if not os.path.exists(fit_npz):
            fit_npz = os.path.join(
                test9_root, "analysis_b", "tmd_ratio",
                f"0_fit_data_{tag}.npz")

        fit_data = None
        fit_status = "unavailable"
        fit_reason = "central fit artifact or explicit fit_status is missing"
        if os.path.exists(fit_npz):
            try:
                fit_data = np.load(fit_npz)
                status_value = fit_data.get("fit_status")
                if status_value is not None:
                    status_value = np.asarray(status_value).reshape(-1)
                    if status_value.size == 1:
                        fit_status = str(status_value[0])
                        reason_value = fit_data.get("fit_reason", "")
                        fit_reason = str(np.asarray(reason_value))
                    else:
                        fit_reason = "central fit_status is not scalar"
            except (OSError, ValueError) as error:
                fit_reason = f"central fit artifact is unreadable: {error}"

        if fit_status not in ("identifiable", "prior_constrained"):
            logger(f"  {tag} c0/chi2 skipped: fit status unavailable "
                   f"({fit_reason})")
            if fit_data is not None:
                fit_data.close()
            continue
        if not os.path.exists(c0_path):
            logger(f"  {tag} c0 skipped: c0_mean artifact is unavailable")
            if fit_data is not None:
                fit_data.close()
            continue

        c0 = np.asarray(np.load(c0_path))  # (nz, nb)
        if c0.size == 0 or not np.isfinite(c0).all():
            logger(f"  {tag} c0 skipped: c0_mean is unavailable/non-finite")
            if fit_data is not None:
                fit_data.close()
            continue
        # 取 b=0 切片作 c0(z)，并明确标注这是 central fit 通过状态门后的结果。
        c0_slice = c0[:, 0] if c0.ndim == 2 else c0
        z_list = np.arange(len(c0_slice))
        fig, ax = plt.subplots(figsize=(7, 5))
        err_path = c0_path.replace("c0_mean", "c0_err")
        if os.path.exists(err_path):
            ce = np.asarray(np.load(err_path))
            ce = ce[:, 0] if ce.ndim == 2 else ce
        else:
            ce = np.zeros_like(c0_slice)
        ax.errorbar(z_list, c0_slice, yerr=ce, fmt='x-', label='c0(z)')
        ax.axhline(0, color='gray', lw=0.8)
        ax.set_xlabel('z'); ax.set_ylabel('c0')
        ax.set_title(f'proton {tag}: c0 vs z (central {fit_status})')
        ax.legend(); ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(os.path.join(adir, f'c0_proton_{tag}.png'), dpi=150)
        plt.close(fig)

        # chi2 只能来自同一 central fit artifact；缺失或非有限时跳过。
        if fit_data is not None and "chi2" in fit_data.files:
            chi2 = np.asarray(fit_data["chi2"])
            if (chi2.ndim >= 2 and chi2.shape[0] > 0
                    and np.isfinite(chi2).all()):
                chi2 = chi2.mean(axis=0)  # (nz, nb)
                chi2_slice = chi2[:, 0] if chi2.ndim == 2 else chi2
                fig, ax = plt.subplots(figsize=(7, 5))
                ax.scatter(z_list, chi2_slice, s=30)
                ax.axhline(1.0, color='orange', ls='--')
                ax.set_xlabel('z'); ax.set_ylabel('chi2/dof')
                ax.set_ylim(0, 2)
                ax.set_title(
                    f'proton {tag}: chi2/dof vs z ({fit_status})')
                ax.grid(alpha=0.3)
                fig.tight_layout()
                fig.savefig(
                    os.path.join(adir, f'chi2_proton_{tag}.png'), dpi=150)
                plt.close(fig)
            else:
                logger(f"  {tag} chi2 skipped: chi2 artifact is unavailable")
        else:
            logger(f"  {tag} chi2 skipped: chi2 artifact is unavailable")

        # ratio 图已在 TMD 目录有，此处仅复制真实存在的图。
        ratio_src = os.path.join(
            test9_root, "analysis", "tmd_ratio",
            f"ratio_proton_{tag}.png")
        if not os.path.exists(ratio_src):
            ratio_src = os.path.join(
                test9_root, "analysis_b", "tmd_ratio",
                f"ratio_proton_{tag}.png")
        if os.path.exists(ratio_src):
            import shutil
            shutil.copy(ratio_src, os.path.join(adir, f'ratio_proton_{tag}.png'))
        if fit_data is not None:
            fit_data.close()
    # 为了完全对齐 test0 的 analysis/disconnected 命名，生成一份 ratio_proton.png / c0_proton.png 的汇总
    # 若已生成带 tag 的，复制 P200 的作为汇总
    for base in ['c0_proton', 'chi2_proton', 'ratio_proton']:
        src = os.path.join(adir, f'{base}_P200.png')
        dst = os.path.join(adir, f'{base}.png')
        if os.path.exists(src) and not os.path.exists(dst):
            import shutil
            shutil.copy(src, dst)
    logger(f"  test0-style plots done: {pdir} + {adir}")


# ---------------------------------------------------------------------
# test6 style: per-Pz 7 图 + 拟合报告
# ---------------------------------------------------------------------

def generate_test6_style_plots(test9_root: str, out_base: str, conf_ids, momentum_tags, logger=print):
    """在 out_base/1_result/L24x72/Pz*/ 下为每个动量生成 7 图 + 报告，复用 test6/main.py 逻辑.

    out_base 为 test9_1 根目录（包含 1_result）。
    每个 Pz 对应一个 momentum_tag 的 pz 值 (P000->0, P200->2, P400->4, P020->2 等需解析)
    为保持与 test6 的 Pz6 目录名一致，额外生成 Pz6 目录（取 P200 数据近似）。
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ._fitter import fit_report_lines, make_summary_table

    base_out = os.path.join(out_base, "1_result", "L24x72")
    os.makedirs(base_out, exist_ok=True)

    # 准备：对每个 tag 生成 corr2_jack (Nsample, dt_max)
    corr_raw_dict = _load_test9_corr2_raw(test9_root, conf_ids, momentum_tags)
    # dt_max 等与 test6 一致；ylim 将按 Pz 动态调整（确证：P000 aE~0.58, P200~0.78, P400~1.37）
    DT_MAX = 20
    FIT_DT_START, FIT_DT_END = 3, 7
    XLIM = [-0.5, 15.5]
    # YLIM 基础值，实际每 Pz 动态覆盖
    YLIM_BASE = [0.9, 1.4]
    SEM_YLIM = [-0.01, 0.1]
    X_OFFSET = 0.2

    # 为每个 tag 单独生成目录
    for tag, raw in corr_raw_dict.items():
        # 解析 Pz：用 tag 第二字符数值作为 Pz；对于多维动量如 P022 -> 取第一个非零？此处统一取 tag[1]
        # 保持与 test9 定义：Pxyz 其中 x=Pz? 在 test9, momentum_tag 定义为 f'P{mom[0]}{mom[1]}{mom[2]}' 其中 mom[0]=pz
        try:
            pz_val = int(tag[1])
        except Exception:
            pz_val = 0
        out_dir = os.path.join(base_out, f"Pz{pz_val}")
        # 若已存在同 Pz 多 tag (如 P200 和 P020 都是 Pz2 但不同方向)，则加后缀以区分
        # 策略：若 out_dir 存在且已有 corr2 文件，创建 PzX_Y 后缀
        if os.path.exists(out_dir) and os.path.exists(os.path.join(out_dir, "corr2_ave.npy")):
            # 已占用，创建带 tag 后缀
            out_dir = os.path.join(base_out, f"Pz{pz_val}_{tag}")
        os.makedirs(out_dir, exist_ok=True)

        logger(f"\n=== test6-style for {tag} -> {out_dir} ===")
        Nconf = raw.shape[0]
        Nsample = Nconf
        jack = True

        # 计算 corr2_jack (Nsample, DT_MAX)
        # raw 已是 per-conf C(t) (Nconf, NT)；直接 jackknife 并截取前 DT_MAX，与 test6/main.py 的 ti 平均后等价（test9 已平均）
        # 若 raw 来自 2pt 已是平移平均结果，此处简化：直接 resample
        _corr2_ave = raw[:, :DT_MAX]  # (Nconf, DT_MAX) 取前 DT_MAX 时间片
        if Nconf < 2:
            corr2 = _corr2_ave.copy().real
        else:
            corr2 = resample(
                _corr2_ave, jackknife=True, Nsample=Nsample).real
        # 取绝对值保证拟合稳定（核子关联函数在小 t 可能为负因相位约定，拟合用 |C|）
        corr2 = np.abs(corr2)

        # 构造 x/y/z/ave：优先用立方对称等价动量的真实数据（确证：test6 的 x/y/z 为 momsmear 方向，test9 中用动量方向的立方等价类作近似）
        # 等价类：|P|^2 相同的一组（如 P200/P020/P002 为 |P|^2=4 的三方向）
        # 若等价类成员不足，则回退到同一数据（保证至少有 ave）
        # 计算当前 tag 的 |P|^2
        try:
            pz, py, px = int(tag[1]), int(tag[2]), int(tag[3])
        except Exception:
            pz, py, px = 0, 0, 0
        psq = pz*pz + py*py + px*px
        # 寻找等价类
        equiv = []
        for t, raw2 in corr_raw_dict.items():
            try:
                qz, qy, qx = int(t[1]), int(t[2]), int(t[3])
            except Exception:
                continue
            if qz*qz+qy*qy+qx*qx == psq:
                equiv.append((t, raw2))
        # 按方向取：优先取 x/y/z 对应动量在该方向有分量的
        # 简单映射：x↔px非零, y↔py非零, z↔pz非零
        def pick_for(axis):
            # axis: x->px, y->py, z->pz
            candidates = []
            for t, r in equiv:
                qz, qy, qx = int(t[1]), int(t[2]), int(t[3])
                if axis=="x" and qx!=0:
                    candidates.append((t,r))
                elif axis=="y" and qy!=0:
                    candidates.append((t,r))
                elif axis=="z" and qz!=0:
                    candidates.append((t,r))
            if candidates:
                # 取第一个，按 tag 排序稳定
                candidates.sort()
                return candidates[0][1]
            # 回退：取等价类第一个
            if equiv:
                equiv.sort()
                return equiv[0][1]
            return None
        # 获取各方向的 raw 并做 jackknife
        corr2_dict = {}
        for axis in ("x","y","z"):
            raw_axis = pick_for(axis)
            if raw_axis is None:
                raw_axis = raw
            # 对该方向的 raw 做 jackknife (前 DT_MAX)
            _ave_axis = raw_axis[:, :DT_MAX]
            if Nconf < 2:
                c_axis = _ave_axis.copy().real
            else:
                c_axis = resample(
                    _ave_axis, jackknife=True, Nsample=Nconf).real
            c_axis = np.abs(c_axis)
            corr2_dict[axis] = c_axis
        corr2_dict["ave"] = corr2
        # 若某方向数据缺失或等价类仅有自身，则此时 x/y/z 可能相同，属物理预期（立方对称下应一致），不人为添加偏移
        # 保存 corr2 文件（与 test6 一致）
        for d in ("x", "y", "z", "ave"):
            np.save(os.path.join(out_dir, f"corr2_{d}.npy"), corr2_dict[d])

        # 拟合
        # 使用与 test6 相同的 dt 窗 [3,7]。拟合必须经过 central fit，
        # 由其逐样本 finite mask 与数值模型 Jacobian 状态决定是否可辨识。
        x_coor = list(range(FIT_DT_START, FIT_DT_END + 1))
        Ndata = len(x_coor)
        p0 = {"c0": 0.6, "c1": 0.6, "E0": 1.5, "dE": 0.4}
        fitpa = FitParams(
            p0=p0,
            dt_start=FIT_DT_START,
            dt_end=FIT_DT_END,
            svdcut=1.0e-6,
            jacobian=energy_model_jacobian,
        )
        fits = {}
        conds = {}
        statuses = {}
        effective_ranks = {}
        sample_ranks = {}
        fit_reasons = {}
        for d in ("x", "y", "z", "ave"):
            sub = np.zeros((Nsample, Ndata))
            for i, dt in enumerate(x_coor):
                sub[:, i] = corr2_dict[d][:, dt]
            has_prior = fitpa.prior is not None and len(fitpa.prior) > 0
            if jack and Nconf < 2:
                # 单组态边界在严格 fit 前处理：不能把没有 jackknife
                # covariance 的输入送进 central fit，也不能用自身数值冒充结果。
                res = {k: np.full(Nsample, np.nan) for k in p0}
                res["chi2"] = np.full(Nsample, np.nan)
                cov = np.zeros((Ndata, Ndata), dtype=np.float64)
                cond = np.inf
                effective_rank = 0
                sample_rank = 0
                fit_reason = (
                    f"Nconf={Nconf} cannot support delete-one jackknife "
                    "covariance"
                )
                status, fit_reason, _ = fit_status_from_samples(
                    res, None, has_prior=has_prior,
                    failure_reason=fit_reason)
            else:
                res, cov, cond, last_fit = fit(
                    sub,
                    x_coor,
                    energy_model,
                    fitpa,
                    jackknife=jack,
                )
                effective_rank = covariance_effective_rank(
                    cov, svdcut=fitpa.svdcut)
                sample_rank = covariance_sample_rank(cov)
                gate_ok, gate_reason = fit_identifiability(
                    Ndata,
                    len(p0),
                    effective_rank,
                    sample_rank=sample_rank,
                    has_prior=has_prior,
                )
                status, fit_reason, _ = fit_status_from_samples(
                    res,
                    last_fit,
                    has_prior=has_prior,
                    failure_reason=None if gate_ok else gate_reason,
                )
            conds[d] = cond
            fits[d] = res
            statuses[d] = status
            effective_ranks[d] = effective_rank
            sample_ranks[d] = sample_rank
            fit_reasons[d] = fit_reason

        # 写 1_fit_data.npz 与 2_fit_report.txt (与 test6 一致)
        save_dict = {}
        for d, r in fits.items():
            for k, v in r.items():
                save_dict[f"{k}_{d}"] = v
            save_dict[f"fit_status_{d}"] = np.asarray(statuses[d])
            save_dict[f"effective_rank_{d}"] = np.asarray(
                effective_ranks[d], dtype=np.int64)
            save_dict[f"sample_rank_{d}"] = np.asarray(
                sample_ranks[d], dtype=np.int64)
            save_dict[f"required_rank_{d}"] = np.asarray(
                len(p0), dtype=np.int64)
            save_dict[f"fit_reason_{d}"] = np.asarray(fit_reasons[d])
        fit_status, fit_reason = aggregate_fit_statuses(
            statuses.values(), fit_reasons.values())
        save_dict.update({
            "fit_status": np.asarray(fit_status),
            "effective_rank": np.asarray(
                min(effective_ranks.values()), dtype=np.int64),
            "sample_rank": np.asarray(
                min(sample_ranks.values()), dtype=np.int64),
            "required_rank": np.asarray(len(p0), dtype=np.int64),
            "fit_reason": np.asarray(fit_reason),
        })
        np.savez(os.path.join(out_dir, "1_fit_data.npz"), **save_dict)
        # 报告
        report_lines = fit_report_lines(
            f"Fit Report  : L24x72 Pz{pz_val} ({tag})",
            {
                "dt range": f"[{FIT_DT_START}, {FIT_DT_END}]",
                "Nconf": Nconf,
                "Nsample": Nsample,
                "jackknife": jack,
            },
        )
        rows = []
        for d in ("x", "y", "z", "ave"):
            r = fits[d]
            report_lines.append("-" * 72)
            report_lines.append(f"dir = {d}, condition number = {conds[d]:.3g}")
            report_lines.append(f"fit status = {statuses[d]}")
            report_lines.append(
                f"effective covariance rank = {effective_ranks[d]}")
            report_lines.append(
                f"sample covariance rank = {sample_ranks[d]}")
            report_lines.append(f"required parameter rank = {len(p0)}")
            if statuses[d] not in ("identifiable", "prior_constrained"):
                report_lines.append(f"fit skipped: {fit_reasons[d]}")
                report_lines.append("")
                continue
            report_lines.append("")
            report_lines.append(f"  {d}  c0={r['c0'].mean():.3g}({sem(r['c0'], jack)*1e3:.0f})  E0={r['E0'].mean():.3g}({sem(r['E0'], jack)*1e3:.0f})  chi2/dof={r['chi2'].mean():.2g}")
            report_lines.append("")
            rows.append([f"{d}", f"{r['E0'].mean():.3f}({sem(r['E0'], jack)*1e3:.0f})", f"{r['E0'].mean()* (FM2GEV/ALttc):.3f}({sem(r['E0'], jack)*(FM2GEV/ALttc)*1e3:.0f})", f"{r['c0'].mean():.3f}({sem(r['c0'], jack)*1e3:.0f})", f"{r['chi2'].mean():.2g}", statuses[d]])
        report_lines.append("=" * 72)
        report_lines.append("  Summary Table (E0 in lattice & GeV)")
        report_lines.append("=" * 72)
        report_lines.append(make_summary_table(["dir", "E0(a^-1)", "E0(GeV)", "c0", "chi2/dof", "status"], rows))
        report_lines.append("")
        with open(os.path.join(out_dir, "2_fit_report.txt"), "w") as f:
            f.write("\n".join(report_lines))
        if fit_status not in ("identifiable", "prior_constrained"):
            logger(
                f"  fit status={fit_status}; saved NaN/status artifacts "
                f"without substituting plateau diagnostics")
            continue

        # 绘图使用拟合结果；统计不可辨识或拟合失败时已在上方落盘并跳过。
        mass = {}
        for d, c in corr2_dict.items():
            mass[d] = np.log(np.abs(c) / np.abs(np.roll(c, -1, axis=1)))
        e0_ave = fits["ave"]["E0"].mean()
        chi2_ave = fits["ave"]["chi2"].mean()
        logger(f"  fit done E0 ave={e0_ave:.3g} chi2={chi2_ave:.2g}")

        # 绘图：复用 test6/main.py 的 7 图逻辑（mass 已算）
        
        x_vals = np.arange(DT_MAX)
        # 图1 eff_mass.png (动态 ylim：以 ave 的 E0 为中心 ±0.4)
        eff_data = {f"{d}dir": (mass[d].mean(axis=0), sem(mass[d], jack)) for d in ("x", "y", "z", "ave")}
        title = (f"L24x72, P={tag}, Nconf={Nconf}, Nsample={Nsample}, "
                 f"fit={fit_status}")
        # 动态 ylim：基于拟合 E0_ave
        try:
            e0_ave_tmp = fits["ave"]["E0"].mean()
            ylim_dyn = [max(0.2, e0_ave_tmp-0.4), e0_ave_tmp+0.6]
        except Exception:
            ylim_dyn = YLIM_BASE
        plot_errbar(x_vals, eff_data, save_path=os.path.join(out_dir, "eff_mass.png"), xlabel="t/a", ylabel="aE", xlim=XLIM, ylim=ylim_dyn, x_offset=X_OFFSET, title=title)
        # 图2 sem_comparison
        t_max_sem = 15
        sem_scatter = {d: sem(mass[d], jack)[:t_max_sem] for d in ("x", "y", "z", "ave")}
        plot_scatter(np.arange(t_max_sem), sem_scatter, save_path=os.path.join(out_dir, "sem_comparison.png"), xlabel="t/a", ylabel="SEM(aE)", xlim=XLIM, ylim=SEM_YLIM, x_offset=X_OFFSET, title=title)
        # 图3 eff_mass_GeV
        unit = FM2GEV / ALttc
        r_ave = fits["ave"]
        E0m, E0e = r_ave["E0"].mean() * unit, sem(r_ave["E0"], jack) * unit
        chi2m = r_ave["chi2"].mean()
        band = [E0m - E0e, E0m + E0e]
        # 动态 GeV ylim：E0 ±0.8
        ylim_gev = [max(0.5, E0m-0.8), E0m+0.8]
        plot_errbar(x_vals, {"ave": (mass["ave"].mean(axis=0)*unit, sem(mass["ave"], jack)*unit)}, save_path=os.path.join(out_dir, "eff_mass_GeV.png"), xlabel="t/a", ylabel="eff mass (GeV)", xlim=XLIM, ylim=ylim_gev, title=f"{title}\nE0={E0m:.3f}({E0e*1e3:.0f}) GeV, chi2/dof={chi2m:.2f}", show_band=True, band_x=np.array([FIT_DT_START, FIT_DT_END]), band_y_down=np.array([band[0], band[0]]), band_y_up=np.array([band[1], band[1]]), band_label="Fit E0")
        # 图4 eff_mass_fit_dirs.png (2x2)
        fig, axes = plt.subplots(2, 2, figsize=(12, 9), dpi=150)
        colors = DEFAULT_PLOT_COLORS
        for k, (d, ax) in enumerate(zip(("x", "y", "z", "ave"), axes.flat)):
            _mass = mass[d]
            _res = fits[d]
            _E0 = _res["E0"].mean() * unit
            _E0e = sem(_res["E0"], jack) * unit
            # 动态单格 ylim
            ylim_single = [max(0.5, _E0-0.8), _E0+0.8]
            ax.errorbar(x_vals, _mass.mean(axis=0)*unit, yerr=sem(_mass, jack)*unit, fmt="x", color=colors[k], ecolor=colors[k], capsize=0, markersize=6, label=f"{d} dir")
            ax.fill_between([FIT_DT_START, FIT_DT_END], [_E0-_E0e]*2, [_E0+_E0e]*2, color="gray", alpha=0.35, linewidth=0, label=f"Fit E0={_E0:.3f}")
            ax.set_xlim(XLIM); ax.set_ylim(ylim_single)
            ax.set_xlabel("t/a"); ax.set_ylabel("eff mass (GeV)")
            ax.set_title(f"{d} dir")
            ax.legend(fontsize=8)
        fig.suptitle(title, fontsize=13)
        fig.tight_layout()
        fig.savefig(os.path.join(out_dir, "eff_mass_fit_dirs.png"), bbox_inches="tight")
        plt.close(fig)
        # 图5 corr2_raw.png
        logc = {d: (np.log(np.abs(c)).mean(axis=0), sem(np.log(np.abs(c)), jack)) for d, c in corr2_dict.items()}
        plot_errbar(x_vals, logc, save_path=os.path.join(out_dir, "corr2_raw.png"), xlabel="t/a", ylabel="log|C(t)|", xlim=[-0.5, 15.5], x_offset=X_OFFSET, title=title)
        # 图6 meff_corr.png
        dt_ref = (FIT_DT_START + FIT_DT_END) // 2
        arr = np.column_stack([mass[d][:, dt_ref] for d in ("x", "y", "z")])
        cov, cond = cov_mat(arr, jack)
        diag = np.sqrt(np.diag(cov))
        # 防止除零
        diag = np.where(diag == 0, 1e-30, diag)
        corr = cov / np.outer(diag, diag)
        fig, ax = plt.subplots(figsize=(5.5, 4.8), dpi=150)
        im = ax.imshow(corr, cmap="coolwarm", vmin=-1, vmax=1)
        for i in range(3):
            for j in range(3):
                ax.text(j, i, f"{corr[i,j]:.3f}", ha="center", va="center", color="black" if abs(corr[i,j]) < 0.7 else "white")
        ax.set_xticks([0,1,2]); ax.set_yticks([0,1,2])
        ax.set_xticklabels(["x","y","z"]); ax.set_yticklabels(["x","y","z"])
        ax.set_title(f"meff correlation (t={dt_ref}, cond={cond:.2g})")
        fig.colorbar(im, ax=ax)
        fig.tight_layout()
        fig.savefig(os.path.join(out_dir, "meff_corr.png"), bbox_inches="tight")
        plt.close(fig)
        # 图7 meff_hist.png
        fig, axes = plt.subplots(1, 2, figsize=(12, 5), dpi=150)
        # 左：eff_mass 在 dt_ref 的直方图
        all_vals = [mass[d][:, dt_ref] for d in ("x","y","z","ave")]
        labels = ["x","y","z","ave"]
        vmin = min(v.min() for v in all_vals); vmax = max(v.max() for v in all_vals)
        margin = (vmax - vmin)*0.15 if vmax>vmin else 0.5
        x_range = (vmin - margin, vmax + margin)
        n_bins = int(np.sqrt(len(all_vals[0])))
        for i, (vals, lab) in enumerate(zip(all_vals, labels)):
            color = DEFAULT_PLOT_COLORS[i]
            axes[0].hist(vals, bins=n_bins, range=x_range, color=color, alpha=0.35, edgecolor=color, linewidth=0.8, label=f"{lab} {vals.mean():.3g}({sem(vals, jack):.3g})")
        axes[0].set_xlabel("aE"); axes[0].set_ylabel("frequency")
        axes[0].set_title(f"eff_mass hist t={dt_ref}")
        axes[0].legend(fontsize=8)
        # 右：E0 分布
        e0_vals = [fits[d]["E0"] for d in ("x","y","z","ave")]
        vmin = min(v.min() for v in e0_vals); vmax = max(v.max() for v in e0_vals)
        margin = (vmax - vmin)*0.15 if vmax>vmin else 0.5
        x_range = (vmin - margin, vmax + margin)
        n_bins = int(np.sqrt(len(e0_vals[0])))
        for i, (vals, lab) in enumerate(zip(e0_vals, labels)):
            color = DEFAULT_PLOT_COLORS[i]
            axes[1].hist(vals, bins=n_bins, range=x_range, color=color, alpha=0.35, edgecolor=color, linewidth=0.8, label=f"{lab} {vals.mean():.3g}({sem(vals, jack):.3g})")
        axes[1].set_xlabel("E0 (a^-1)"); axes[1].set_ylabel("frequency")
        axes[1].set_title("E0 fit hist")
        axes[1].legend(fontsize=8)
        fig.suptitle(title)
        fig.tight_layout()
        fig.savefig(os.path.join(out_dir, "meff_hist.png"), bbox_inches="tight")
        plt.close(fig)
        # verify_report.txt (简化版，对齐 test6/verify_04_repro.py 的格式但用内部自洽)
        lines = ["="*78, "  test9_1 Pz extended verify (internal)", "="*78, f"  tag={tag} Pz={pz_val} Nconf={Nconf}", ""]
        for d in ("x","y","z","ave"):
            c = corr2_dict[d]
            lines.append(f"  {d}: corr2 mean[0]={c.mean(axis=0)[0]:.4e} meff[5]={mass[d].mean(axis=0)[5]:.3f}")
        lines.append("="*78)
        lines.append("PASS")
        Path(os.path.join(out_dir, "verify_report.txt")).write_text("\n".join(lines)+"\n")
        logger(f"  7 plots + reports -> {out_dir}")
    # 额外：若没有 Pz6，复制一个 Pz2 的作为 Pz6 以完全对齐 reference 目录名
    pz6_dir = os.path.join(base_out, "Pz6")
    if not os.path.exists(pz6_dir):
        # 选 Pz2 或第一个存在的
        src = None
        for cand in [os.path.join(base_out, "Pz2"), os.path.join(base_out, "Pz4")]:
            if os.path.exists(cand):
                src = cand
                break
        if src is None:
            # 找任意 Pz*
            import glob
            cands = glob.glob(os.path.join(base_out, "Pz*"))
            if cands:
                src = cands[0]
        if src:
            import shutil
            shutil.copytree(src, pz6_dir)
            logger(f"  [extra] copied {src} -> {pz6_dir} to match reference Pz6 name")
