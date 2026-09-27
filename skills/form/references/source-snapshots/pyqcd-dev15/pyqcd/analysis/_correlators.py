"""
连通关联函数分析编排：meff 与 3pt/2pt 比值（analyze.py 逻辑规范化）
====================================================================

等价实现冻结蒸馏基线 analyze.py 的 Analysis 1/2：

    1. Jackknife 有效质量（cosh/log 型，平台窗 + 误差加权平均 + fallback 窗）
    2. 连通 3pt/2pt 比值 R(τ)（γ₃ 分量，ratio_3pt）

已通过 verify_consistency.py 对照 output_20260802_120104 参考值（0 差异）。
"""
from __future__ import annotations

import numpy as np

from ._analyse import Jackknife, meff, ratio_3pt
from ..pipeline._config import ANALYSIS_MOMENTA, FM2GEV, NX


def run_meff_jackknife(corr_2pt_all, conf_ids, NT=72, ALttc=0.1053,
                       meff_types=None, logger=print):
    """Jackknife 有效质量（analyze.py run_meff_jackknife 等价，含 E_exp/dev）。

    Args:
        corr_2pt_all: {conf_id: {'corr_pp_P0': (Nt,), 'corr_pion_P2': (Nt,), ...}}
        conf_ids: 组态列表
    Returns:
        results: {particle_mom: {'E0', 'E0_err', 'E_exp', 'dev', 'plateau',
                                 'npts', 'meff_mean', 'meff_err', 'corr_mean', 'corr_err'}}
    """
    if meff_types is None:
        meff_types = {'proton': 'cosh', 'pion': 'log'}
    channels = [
        ('proton', 'P0', 'corr_pp_P0'), ('proton', 'P2', 'corr_pp_P2'),
        ('pion', 'P0', 'corr_pion_P0'), ('pion', 'P2', 'corr_pion_P2'),
    ]
    results = {}
    for particle, mom, key in channels:
        if key not in corr_2pt_all[conf_ids[0]]:
            logger(f"{particle} {mom}: 输入缺少 {key} —— 跳过该通道")
            continue
        ml = f"P{list(ANALYSIS_MOMENTA[particle].values())[0 if mom == 'P0' else 1]}"
        stack = np.stack([np.real(corr_2pt_all[cid][key]) for cid in conf_ids])
        jk = Jackknife(stack, Nconf_axes=0)
        mf = meff(jk['data_sample'], ALttc, Nconf_axes=0, Nt_axes=1,
                  meff_type=meff_types[particle])
        cmean, cerr = np.real(jk['data_mean']), np.real(jk['data_err'])
        mmean, merr = np.real(mf['data_mean']), np.real(mf['data_err'])

        if particle == 'proton':
            ps, pe = 6, min(NT - 2, 12)
        else:
            ps, pe = 5, min(NT - 2, 18)
        mask = np.isfinite(mmean[ps:pe]) & (merr[ps:pe] > 0) & (mmean[ps:pe] > 0.01)
        if np.sum(mask) < 2:
            ps, pe = 2, min(8, NT - 1)
            mask = np.isfinite(mmean[ps:pe]) & (merr[ps:pe] > 0)
        w = 1.0 / (merr[ps:pe][mask] ** 2 + 1e-10)
        E0 = float(np.sum(mmean[ps:pe][mask] * w) / np.sum(w))
        E0_err = float(1.0 / np.sqrt(np.sum(w)))

        # ── 期望能量与色散检查（与 docker-v20260805 analyze.py 一致）──
        if mom == 'P0':
            E_exp = 1.0 if particle == 'proton' else 0.30
        else:
            m0 = results.get(f'{particle}_P0', {}).get('E0', E0)
            p_phys = (2 * np.pi * 2 / NX) * (FM2GEV / ALttc)   # ≈ 0.981 GeV
            E_exp = np.sqrt(m0 ** 2 + p_phys ** 2)
        dev = abs(E0 - E_exp) / (E0_err + 1e-10)
        status = '✓' if dev < 2 else ('⚠' if dev < 4 else '✗')

        results[f'{particle}_{mom}'] = {
            'E0': E0, 'E0_err': E0_err, 'E_exp': E_exp, 'dev': dev,
            'plateau': (ps, pe), 'npts': int(np.sum(mask)),
            'meff_mean': mmean, 'meff_err': merr,
            'corr_mean': cmean, 'corr_err': cerr,
        }
        logger(f"{particle} {ml}: E0 = {E0:.4f} ± {E0_err:.4f} GeV  "
               f"(expected {E_exp:.3f}, {status} dev={dev:.1f}σ, "
               f"plateau t∈[{ps},{pe}], {int(np.sum(mask))} pts)")
    return results


def run_3pt_ratio(corr_2pt_all, corr_3pt_all, conf_ids, t_sep=None,
                  NT=72, logger=print):
    """连通 3pt/2pt 比值 R(τ)（analyze.py run_3pt_ratio 等价，γ₃ 分量）。

    Args:
        corr_2pt_all: {conf_id: {'corr_pp_P0': (Nt,), ...}}
        corr_3pt_all: {conf_id: {'proton_P0_3pt': (Ntau, 4), ...}}
    Returns:
        results: {hadron_mom: {'R', 'R_err', 't_sep'}}
    """
    pairs = [
        ('proton', 'P0', 'corr_pp_P0', 'proton_P0_3pt'),
        ('proton', 'P2', 'corr_pp_P2', 'proton_P2_3pt'),
        ('pion', 'P0', 'corr_pion_P0', 'pion_P0_3pt'),
        ('pion', 'P2', 'corr_pion_P2', 'pion_P2_3pt'),
    ]
    results = {}
    for had, mom, k2, k3 in pairs:
        s3 = np.stack([np.real(corr_3pt_all[cid][k3][:, 3]) for cid in conf_ids])
        s2 = np.stack([np.real(corr_2pt_all[cid][k2]) for cid in conf_ids])
        ts = s3.shape[1] - 1 if t_sep is None else t_sep
        jk3 = Jackknife(s3, Nconf_axes=0)
        jk2 = Jackknife(s2, Nconf_axes=0)
        ratio = ratio_3pt(jk3['data_sample'], jk2['data_sample'],
                          data_2ptF_sample=None, t_sep=ts,
                          Nconf_axes=0, tau_axes=1, t_sink_axes=1)
        rm, re_ = np.real(ratio['data_mean']), np.real(ratio['data_err'])
        results[f'{had}_{mom}'] = {'R': rm, 'R_err': re_, 't_sep': ts}
        logger(f"{had} {mom}: R(0..{min(len(rm), ts + 1) - 1}) t_sep={ts}")
    return results
