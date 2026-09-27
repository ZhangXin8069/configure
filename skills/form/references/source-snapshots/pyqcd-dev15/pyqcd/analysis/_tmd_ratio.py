"""
核子胶子 TMD-PDF 裸矩阵元提取：不相连 ratio（code_1.py 算法，b⊥ 扩展）
====================================================================

梯度流重整化方案中，核子中胶子 TMD 算符矩阵元 <N|O(z,b⊥)|N> 通过
不相连因子化三点函数计算（照抄 docker-v20260805 analyze.py 的
code_1.py 算法，扩展 b⊥ 维度）：

    C3(dt, dtau, z, b) = C2(dt) · OPE(dtau, z, b)        （不相连因子化）
    C3_disc = C3 − C2·⟨OPE⟩                               （真空扣除）
    R(dt, dtau, z, b) = ⟨C3_disc / C2⟩_ti
    逐 (z, b) 相关拟合：R = c0 + c1·e^{−dE·dtau} + c1·e^{−dE·(dt−dtau)}

其中 OPE(dtau, z, b) 为梯度流涂抹后的胶子 TMD staple 算符
O(z,b⊥) = M^{tx;tx} + M^{ty;ty} − 2M^{xy;xy} 在时间片 dtau 的
空间求和值（形状 (nz, nb, Nt)），C2 为核子 2pt 关联函数。

输出：裸矩阵元 c0(z,b)（逐样本：jackknife）→ 供 Z_R / 混合方案
自重整化链使用。
"""
from __future__ import annotations

import os
import time

import numpy as np

from ._disconnected import (aggregate_fit_statuses, fit_status_from_samples,
                            model_ratio, model_ratio_jacobian, resample, sem)


def _plateau_points(ratio, dt_max, dt_start, dt_end, cut):
    front = cut // 2
    back = cut - front
    dt_stop = min(dt_end, dt_max - 1, ratio.shape[1] - 1)
    points = []
    for dt in range(dt_start, dt_stop + 1):
        dtau_stop = min(dt - back, ratio.shape[2] - 1)
        points.extend((dt, dtau) for dtau in range(front, dtau_stop + 1))
    return points


def _aggregate_status(status_by_channel):
    return aggregate_fit_statuses(np.asarray(status_by_channel).ravel())[0]


def _plateau_status_metadata(
        ratio, c0_plateau, dt_max, dt_start, dt_end, cut):
    status = np.full(
        c0_plateau.shape[1:],
        "statistically_unidentifiable",
        dtype="<U32",
    )
    sample_rank = np.zeros(c0_plateau.shape[1:], dtype=np.int64)
    reason = np.full(c0_plateau.shape[1:], "", dtype="<U128")

    if c0_plateau.shape[0] < 2:
        reason[...] = (
            f"Nsample={c0_plateau.shape[0]} cannot identify plateau variance"
        )
    elif not _plateau_points(ratio, dt_max, dt_start, dt_end, cut):
        reason[...] = "empty plateau window"
    else:
        identifiable = np.all(np.isfinite(c0_plateau), axis=0)
        status[identifiable] = "identifiable"
        sample_rank[identifiable] = 1
        reason[identifiable] = "identifiable"
        reason[~identifiable] = "plateau sample has no fluctuating mode"

    return {
        "plateau_status": np.asarray(_aggregate_status(status)),
        "plateau_status_by_channel": status,
        "plateau_sample_rank": sample_rank,
        "plateau_reason": reason,
    }


def run_disconnected_tmd_ratio(corr_2pt_all, ope_all, conf_ids,
                               run_dir, logger=print,
                               NT=72, nz=24, nb=1,
                               dt_max=20, dt_start=7, dt_end=10,
                               cut=6, p0=None, momentum='P200',
                               z_s=0):
    """不相连胶子 TMD ratio + 逐 (z,b) 拟合（code_1.py 算法，b⊥ 扩展）。

    Args:
        corr_2pt_all: {conf_id: {f'corr_pp_{mom}': (Nt,)}} 核子 2pt。
        ope_all:      {conf_id: {'tmd': (nz, nb, Nt)}} 梯度流 TMD 算符
                      逐时间片空间求和（实数）。
        conf_ids:     组态列表（jackknife 重采样轴）。
        run_dir:      输出目录（analysis/tmd_ratio/）。
        nz:           z 方向格点数（OPE 的 z 维长度）。
        nb:           b⊥ 维长度。
        momentum:     动量标签（'P200' 等，用于命名输出文件）。
        z_s:          比值参考 z 索引（保留参数，备用）。
    Returns:
        ch_results: {hadron: {'ratio', 'c0', 'c1', 'dE', 'chi2', 'x_coor'}}
            c0/c1/dE/chi2 形状 (Nsample, nz, nb)。
    """
    from ._fitter import (FitParams, covariance_effective_rank,
                          covariance_sample_rank, fit, fit_identifiability)

    if p0 is None:
        p0 = {"c0": 0.6, "c1": -2, "dE": 1}

    Nconf = len(conf_ids)
    Nsample = max(Nconf, 1)
    # 重采样方式选择：delete-one jackknife 需样本数显著大于数据点数；
    # 小样本用 bootstrap（Nsample=200 满秩协方差，svdcut 下拟合稳定）。
    # 守卫：Nconf<2 禁用 jackknife（n−1=0 除零 → 全 NaN）
    front_remove = cut // 2
    back_remove = cut - front_remove
    # 真实数据点计数（与下方 x_coor 同式）：Σ_dt max(dt−front−back+1, 0)
    Ndata_est = sum(max(dt - front_remove - back_remove + 1, 0)
                    for dt in range(dt_start, dt_end + 1))
    jack = (Nconf >= 2) and (Nconf > Ndata_est)
    if not jack:
        Nsample = 200   # bootstrap 重采样 200 次（协方差满秩）
    if Nconf < 2:
        Nsample = 1     # 单组态：重采样无统计意义，走下方直通分支
    out_dir = os.path.join(run_dir, 'analysis', 'tmd_ratio')
    os.makedirs(out_dir, exist_ok=True)

    channels = [('proton', 'corr_pp', 'proton')]
    ch_results = {}

    for ch_key, k2, had_name in channels:
        logger(f"\n  Channel: {had_name} at {momentum} (TMD, b⊥={nb} vals)")

        key2 = f'{k2}_{momentum}'
        _corr = np.stack([np.real(corr_2pt_all[cid][key2]) for cid in conf_ids])
        full = np.zeros((Nconf, NT, NT), dtype=np.float64)
        for ti in range(NT):
            full[:, :, ti] = np.roll(_corr, -ti, axis=1)

        # OPE tmd: (Nconf, nz, nb, Nt) → (Nconf, tau, z, b)
        _ope = np.stack([np.real(ope_all[cid]['tmd']) for cid in conf_ids])
        _ope = _ope.transpose(0, 3, 1, 2)   # (Nconf, Nt, nz, nb)

        # 相对时间构造
        _corr2_rel = np.zeros((Nconf, NT, dt_max), dtype=np.float64)
        _ope_rel = np.zeros((Nconf, NT, dt_max, nz, nb), dtype=np.float64)
        for ti in range(NT):
            corr2_shift = np.roll(full[:, :, ti], -ti, axis=1)
            _corr2_rel[:, ti, :] = corr2_shift[:, :dt_max]
            ope_shift = np.roll(_ope, -ti, axis=1)
            _ope_rel[:, ti, :, :, :] = ope_shift[:, :dt_max, :, :]

        # 不相连 3pt = C2 × OPE（因子化）
        _corr3 = np.zeros((Nconf, NT, dt_max, dt_max, nz, nb), dtype=np.float64)
        for _dt in range(dt_max):
            for _dtau in range(_dt + 1):
                _corr3[:, :, _dt, _dtau, :, :] = (
                    _ope_rel[:, :, _dtau, :, :]
                    * _corr2_rel[:, :, _dt][:, :, None, None])

        if Nconf < 2:
            # 单组态直通：不重采样（bootstrap 复制亦无意义），保形状 (1, ...)
            corr2, ope, corr3 = _corr2_rel, _ope_rel, _corr3
        else:
            corr2 = resample(_corr2_rel, jack, Nsample)
            ope = resample(_ope_rel, jack, Nsample)
            corr3 = resample(_corr3, jack, Nsample)

        # 真空扣除 + ratio
        corr3_disc = corr3 - corr2[:, :, :, None, None, None] * ope[:, :, None, :, :, :]
        eps = 1e-30
        ratio = np.mean(corr3_disc / (corr2[:, :, :, None, None, None] + eps), axis=1)
        ratio = ratio.real   # (Nsample, dt, dtau, nz, nb)
        if Nconf < 2:
            ratio = np.full(ratio.shape, np.nan, dtype=np.float64)
        np.save(os.path.join(out_dir, f'ratio_{had_name}_{momentum}.npy'), ratio)

        # 逐 (z,b) 相关拟合（Nconf<2 时跳过——协方差奇异，统计无意义）
        if Nconf < 2:
            fit_reason = (
                f"Nconf={Nconf} cannot support delete-one jackknife covariance"
            )
            required_rank = len(p0)
            fit_status_by_channel = np.full(
                (nz, nb), "statistically_unidentifiable", dtype="<U32")
            effective_rank_by_channel = np.zeros(
                (nz, nb), dtype=np.int64)
            sample_rank_by_channel = np.zeros((nz, nb), dtype=np.int64)
            required_rank_by_channel = np.full(
                (nz, nb), required_rank, dtype=np.int64)
            fit_reason_by_channel = np.full(
                (nz, nb), fit_reason, dtype="<U128")
            para_c0 = np.full((1, nz, nb), np.nan)
            para_c1 = np.full((1, nz, nb), np.nan)
            para_dE = np.full((1, nz, nb), np.nan)
            chi2 = np.full((1, nz, nb), np.nan)
            c0_plateau = np.full((1, nz, nb), np.nan)
            report_lines = [
                "=" * 70,
                f"  TMD Fit Report: {had_name}, {momentum}, Nconf={Nconf}",
                "=" * 70,
                "fit status = statistically_unidentifiable",
                "effective covariance rank = 0",
                "sample covariance rank = 0",
                f"required parameter rank = {required_rank}",
                f"fit skipped: {fit_reason}",
                "",
            ]
            with open(os.path.join(
                    out_dir, f'1_fit_report_{momentum}.txt'), 'w') as f:
                f.write("\n".join(report_lines))
            np.savez(
                os.path.join(out_dir, f'0_fit_data_{momentum}.npz'),
                c0=para_c0,
                c1=para_c1,
                dE=para_dE,
                chi2=chi2,
                fit_status=np.asarray("statistically_unidentifiable"),
                effective_rank=np.asarray(0, dtype=np.int64),
                sample_rank=np.asarray(0, dtype=np.int64),
                required_rank=np.asarray(required_rank, dtype=np.int64),
                fit_reason=np.asarray(fit_reason),
                fit_status_by_channel=fit_status_by_channel,
                effective_rank_by_channel=effective_rank_by_channel,
                sample_rank_by_channel=sample_rank_by_channel,
                required_rank_by_channel=required_rank_by_channel,
                fit_reason_by_channel=fit_reason_by_channel,
            )
            np.save(
                os.path.join(out_dir, f'c0_plateau_{momentum}.npy'),
                c0_plateau,
            )
            plateau_metadata = _plateau_status_metadata(
                ratio, c0_plateau, dt_max, dt_start, dt_end, cut)
            np.savez(
                os.path.join(
                    out_dir, f'c0_plateau_status_{momentum}.npz'),
                **plateau_metadata,
            )
            logger(f"  fit skipped: {fit_reason}; saved NaN fit artifacts")
            ch_results[had_name] = {
                'ratio': ratio, 'c0': para_c0, 'c1': para_c1,
                'dE': para_dE, 'chi2': chi2, 'x_coor': [],
                'c0_plateau': c0_plateau,
                'fit_status': 'statistically_unidentifiable',
                'plateau_status': str(plateau_metadata['plateau_status']),
                'effective_rank': 0, 'sample_rank': 0,
                'required_rank': required_rank, 'fit_reason': fit_reason,
                'fit_status_by_channel': fit_status_by_channel,
                'effective_rank_by_channel': effective_rank_by_channel,
                'sample_rank_by_channel': sample_rank_by_channel,
                'required_rank_by_channel': required_rank_by_channel,
                'fit_reason_by_channel': fit_reason_by_channel,
            }
            continue

        # 逐 (z,b) 相关拟合（front/back_remove 已在重采样选择处计算）
        x_coor = [(dt, dtau)
                  for dt in range(dt_start, dt_end + 1)
                  for dtau in range(front_remove, dt - back_remove + 1)]
        Ndata = len(x_coor)

        para_c0 = np.full((Nsample, nz, nb), np.nan)
        para_c1 = np.full((Nsample, nz, nb), np.nan)
        para_dE = np.full((Nsample, nz, nb), np.nan)
        chi2 = np.full((Nsample, nz, nb), np.nan)
        fit_status_by_channel = np.full(
            (nz, nb), "statistically_unidentifiable", dtype="<U32")
        effective_rank_by_channel = np.zeros((nz, nb), dtype=np.int64)
        sample_rank_by_channel = np.zeros((nz, nb), dtype=np.int64)
        required_rank_by_channel = np.full(
            (nz, nb), len(p0), dtype=np.int64)
        fit_reason_by_channel = np.full((nz, nb), "", dtype="<U128")

        report_lines = [
            "=" * 70,
            f"  TMD Fit Report: {had_name}, {momentum}, Nconf={Nconf}",
            "=" * 70,
            f"  t_sep range : [{dt_start}, {dt_end}]",
            f"  cut         : {cut}",
            f"  Nsample     : {Nsample}",
            f"  jackknife   : {jack}",
            f"  nz x nb     : {nz} x {nb}",
            "=" * 70, "",
        ]

        t0_fit = time.perf_counter()
        fitpa = FitParams(
            p0=dict(p0), dt_start=dt_start, dt_end=dt_end,
            svdcut=1.0e-6, jacobian=model_ratio_jacobian)
        for _z in range(nz):
            for _b in range(nb):
                sub_sample = np.zeros((Nsample, Ndata))
                for i, (dt, dtau) in enumerate(x_coor):
                    sub_sample[:, i] = ratio[:, dt, dtau, _z, _b]
                _fit_result, cov, cond, _last_fit = fit(
                    sub_sample, x_coor, model_ratio, fitpa,
                    jackknife=jack)
                effective_rank = covariance_effective_rank(
                    cov, svdcut=fitpa.svdcut)
                sample_rank = covariance_sample_rank(cov)
                required_rank = len(p0)
                gate_ok, gate_reason = fit_identifiability(
                    Ndata, required_rank, effective_rank,
                    sample_rank=sample_rank)
                fit_status, fit_reason, _ = fit_status_from_samples(
                    _fit_result, _last_fit,
                    failure_reason=None if gate_ok else gate_reason)
                fit_status_by_channel[_z, _b] = fit_status
                effective_rank_by_channel[_z, _b] = effective_rank
                sample_rank_by_channel[_z, _b] = sample_rank
                fit_reason_by_channel[_z, _b] = fit_reason
                para_c0[:, _z, _b] = _fit_result["c0"]
                para_c1[:, _z, _b] = _fit_result["c1"]
                para_dE[:, _z, _b] = _fit_result["dE"]
                chi2[:, _z, _b] = _fit_result["chi2"]
                report_lines += [
                    f"z={_z} b={_b} cond={cond:.3g}", "-" * 56,
                    f"fit status = {fit_status}",
                    f"effective covariance rank = {effective_rank}",
                    f"sample covariance rank = {sample_rank}",
                    f"required parameter rank = {required_rank}", "",
                ]

                if fit_status not in ("identifiable", "prior_constrained"):
                    report_lines += [f"fit skipped: {fit_reason}", ""]
                    logger(
                        f"  z={_z} b={_b}: fit skipped "
                        f"({fit_reason})")
                    continue

                if _last_fit is not None:
                    report_lines.append(_last_fit.format(maxline=True))
                report_lines += ["", ""]

                finite = np.isfinite(para_c0[:, _z, _b])
                if np.any(finite):
                    values = para_c0[finite, _z, _b]
                    error = sem(values, jack) if values.size > 1 else np.nan
                    logger(
                        f"  z={_z} b={_b}: c0={values.mean():.4g} ± "
                        f"{error:.4g}  status={fit_status}")

        fit_status, fit_reason = aggregate_fit_statuses(
            fit_status_by_channel.ravel(), fit_reason_by_channel.ravel())
        report_lines.insert(
            7, f"fit status = {fit_status}; fit reason = {fit_reason}")
        report = "\n".join(report_lines)
        with open(os.path.join(out_dir, f'1_fit_report_{momentum}.txt'), 'w') as f:
            f.write(report)
        np.savez(
            os.path.join(out_dir, f'0_fit_data_{momentum}.npz'),
            c0=para_c0,
            c1=para_c1,
            dE=para_dE,
            chi2=chi2,
            fit_status=np.asarray(fit_status),
            fit_status_by_channel=fit_status_by_channel,
            effective_rank=np.asarray(
                np.min(effective_rank_by_channel), dtype=np.int64),
            effective_rank_by_channel=effective_rank_by_channel,
            sample_rank=np.asarray(
                np.min(sample_rank_by_channel), dtype=np.int64),
            sample_rank_by_channel=sample_rank_by_channel,
            required_rank=np.asarray(len(p0), dtype=np.int64),
            required_rank_by_channel=required_rank_by_channel,
            fit_reason=np.asarray(fit_reason),
            fit_reason_by_channel=fit_reason_by_channel,
        )
        # plateau 均值版（fit 窗口内直接平均，抗奇异协方差；test9 整合项）
        c0_plateau = plateau_c0(ratio, dt_max=dt_max, dt_start=dt_start,
                                dt_end=dt_end, cut=cut)
        np.save(os.path.join(out_dir, f'c0_plateau_{momentum}.npy'),
                c0_plateau)
        plateau_metadata = _plateau_status_metadata(
            ratio, c0_plateau, dt_max, dt_start, dt_end, cut)
        np.savez(
            os.path.join(out_dir, f'c0_plateau_status_{momentum}.npz'),
            **plateau_metadata,
        )
        logger(f"  Saved ratio + fit + c0_plateau to {out_dir} "
               f"({time.perf_counter()-t0_fit:.1f}s)")

        ch_results[had_name] = {
            'ratio': ratio, 'c0': para_c0, 'c1': para_c1,
            'dE': para_dE, 'chi2': chi2, 'x_coor': x_coor,
            'c0_plateau': c0_plateau,
            'fit_status': fit_status,
            'fit_status_by_channel': fit_status_by_channel,
            'effective_rank_by_channel': effective_rank_by_channel,
            'sample_rank_by_channel': sample_rank_by_channel,
            'required_rank_by_channel': required_rank_by_channel,
            'fit_reason_by_channel': fit_reason_by_channel,
            'plateau_status': str(plateau_metadata['plateau_status']),
            'plateau_status_by_channel': (
                plateau_metadata['plateau_status_by_channel']),
            'plateau_sample_rank': plateau_metadata['plateau_sample_rank'],
            'plateau_reason': plateau_metadata['plateau_reason'],
        }

    return ch_results


def plot_tmd_c0(ch_results, run_dir, momentum, logger=print,
                nz=24, nb=1, out_name='c0_tmd'):
    """c0(z,b) 图表：逐 b 面板（z 横轴，errorbar）+ 3D 热图。"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    out_dir = os.path.join(run_dir, 'analysis', 'tmd_ratio')
    os.makedirs(out_dir, exist_ok=True)

    for had_name, res in ch_results.items():
        c0 = res['c0']               # (Nsample, nz, nb)
        c0m = c0.mean(0); c0e = sem(c0, True)
        z = np.arange(nz)

        # 逐 b 面板
        ncol = 2
        nrow = (nb + 1) // 2
        fig, axes = plt.subplots(nrow, ncol, figsize=(12, 3.5 * nrow),
                                 squeeze=False)
        for _b in range(nb):
            ax = axes[_b // ncol][_b % ncol]
            ax.errorbar(z, c0m[:, _b], yerr=c0e[:, _b], fmt='x-', capsize=3)
            ax.axhline(0, color='gray', lw=0.8)
            ax.set_xlabel('z'); ax.set_ylabel('c0')
            ax.set_title(f'{had_name} {momentum}: c0(z) b⊥={_b}')
            ax.grid(alpha=0.3)
        for _b in range(nb, nrow * ncol):
            axes[_b // ncol][_b % ncol].axis('off')
        fig.tight_layout()
        fig.savefig(os.path.join(out_dir, f'{out_name}_{had_name}_{momentum}.png'),
                    dpi=150)
        plt.close(fig)

        # 热图（nb≥2 时）
        if nb >= 2:
            fig, ax = plt.subplots(figsize=(8, 6))
            im = ax.imshow(c0m.T, aspect='auto', origin='lower',
                           extent=[0, nz - 1, 0, nb - 1])
            ax.set_xlabel('z'); ax.set_ylabel('b⊥')
            ax.set_title(f'{had_name} {momentum}: c0(z, b⊥)')
            fig.colorbar(im, ax=ax)
            fig.tight_layout()
            fig.savefig(os.path.join(out_dir,
                                     f'{out_name}_heatmap_{had_name}_{momentum}.png'),
                        dpi=150)
            plt.close(fig)

    logger(f"  TMD c0 plots saved to {out_dir}")


def plateau_c0(ratio, dt_max=20, dt_start=7, dt_end=10, cut=6):
    """fit 窗口内 ratio 的 plateau 均值 → c0(z,b)（抗奇异协方差）。

    整合自原 TMD 工作流的 plateau 均值实现：
    与 run_disconnected_tmd_ratio 的 x_coor 窗口一致
    （dt∈[dt_start,dt_end]，dtau∈[front,dt-back]），窗口内直接平均。
    10 组态统计下比 lsqfit 逐样本拟合更稳健（协方差奇异的绕行方案）。

    Args:
        ratio: (Nsample, dt_max, dtau_max, nz, nb)——不相连比值数组。
    Returns:
        (Nsample, nz, nb) plateau 均值。
    """
    r = np.asarray(ratio)
    Nsample, _, _, nz, nb = r.shape
    dtype = np.result_type(r.dtype, np.float64)
    if Nsample < 2:
        return np.full((Nsample, nz, nb), np.nan, dtype=dtype)
    points = _plateau_points(r, dt_max, dt_start, dt_end, cut)
    if not points:
        return np.full((Nsample, nz, nb), np.nan, dtype=dtype)

    window = np.stack([r[:, dt, dtau, :, :] for dt, dtau in points], axis=1)
    out = np.mean(window, axis=1, dtype=dtype)
    flat = out.reshape(Nsample, -1)
    finite = np.all(np.isfinite(flat), axis=0)
    centered = flat - np.mean(flat, axis=0)
    fluctuating = np.sum(np.abs(centered) ** 2, axis=0) > 0.0
    flat[:, ~(finite & fluctuating)] = np.nan
    return out


def plot_tmd_pdf(x_grid, xg_quasi, xg_matched, b_grid_fm, cs_kernel,
                 tag, out_dir, logger=print):
    """TMD-PDF 链成图（整合自 test9 示例 plot_pdf）。

    产出：quasi_tmd_pdf.png / matched_tmd_pdf.png / tmd_pdf_vs_b.png /
    cs_kernel.png（cs_kernel 非 None 时）。

    Args:
        x_grid: x 网格。
        xg_quasi: 准 TMD-PDF x·g̃(x, b⊥)，(nx, nb) 或 (nx,)。
        xg_matched: NLO 匹配后 x·g(x, b⊥)。
        b_grid_fm: b⊥ 网格（fm，标记用）。
        cs_kernel: K(b⊥) 数组或 None。
        tag: 动量标签（图题）。
        out_dir: 输出目录。
    Returns:
        生成的 png 路径列表。
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    os.makedirs(out_dir, exist_ok=True)
    xg = np.asarray(xg_quasi)
    xgm = np.asarray(xg_matched)
    if xg.ndim == 1:
        xg = xg[:, None]
    if xgm.ndim == 1:
        xgm = xgm[:, None]
    nb = xg.shape[1]
    ncol = 2
    nrow = (nb + 1) // 2
    saved = []

    # 准 TMD-PDF x·g̃(x, b⊥)
    fig, axes = plt.subplots(nrow, ncol, figsize=(12, 3.5 * nrow),
                             squeeze=False)
    for b in range(nb):
        ax = axes[b // ncol][b % ncol]
        ax.plot(x_grid, xg[:, b], 'o-', ms=3)
        ax.axhline(0, color='gray', lw=0.8)
        ax.set_xlabel('x'); ax.set_ylabel(r'$x\tilde{g}(x,b_\perp)$')
        ax.set_title(f'quasi TMD-PDF, b={b_grid_fm[b]:.3f} fm')
        ax.grid(alpha=0.3)
    for b in range(nb, nrow * ncol):
        axes[b // ncol][b % ncol].axis('off')
    fig.suptitle(f'{tag}: gradient-flow quasi gluon TMD-PDF')
    fig.tight_layout()
    p = os.path.join(out_dir, 'quasi_tmd_pdf.png')
    fig.savefig(p, dpi=150); plt.close(fig); saved.append(p)

    # 匹配前后对比
    fig, axes = plt.subplots(nrow, ncol, figsize=(12, 3.5 * nrow),
                             squeeze=False)
    for b in range(nb):
        ax = axes[b // ncol][b % ncol]
        ax.plot(x_grid, xg[:, b], 'o-', ms=3, label='quasi')
        ax.plot(x_grid, xgm[:, b], 's-', ms=3, label='NLO matched')
        ax.axhline(0, color='gray', lw=0.8)
        ax.set_xlabel('x'); ax.set_ylabel(r'$xg(x,b_\perp)$')
        ax.set_title(f'b={b_grid_fm[b]:.3f} fm')
        ax.legend(fontsize=8); ax.grid(alpha=0.3)
    for b in range(nb, nrow * ncol):
        axes[b // ncol][b % ncol].axis('off')
    fig.suptitle(f'{tag}: NLO-matched gluon TMD-PDF')
    fig.tight_layout()
    p = os.path.join(out_dir, 'matched_tmd_pdf.png')
    fig.savefig(p, dpi=150); plt.close(fig); saved.append(p)

    # 所有 b 叠加
    fig, ax = plt.subplots(figsize=(8, 5))
    for b in range(nb):
        ax.plot(x_grid, xgm[:, b], '-', lw=1.2,
                label=f'b={b_grid_fm[b]:.3f} fm')
    ax.axhline(0, color='gray', lw=0.8)
    ax.set_xlabel('x'); ax.set_ylabel(r'$xg(x,b_\perp)$')
    ax.set_title(f'{tag}: gluon TMD-PDF vs b-perp (NLO matched)')
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    fig.tight_layout()
    p = os.path.join(out_dir, 'tmd_pdf_vs_b.png')
    fig.savefig(p, dpi=150); plt.close(fig); saved.append(p)

    # CS 核
    if cs_kernel is not None:
        K = np.asarray(cs_kernel, dtype=float).ravel()
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.errorbar(b_grid_fm[:len(K)], K, fmt='o-', capsize=3)
        ax.set_xlabel(r'$b_\perp$ [fm]')
        ax.set_ylabel(r'$K(b_\perp)$')
        ax.set_title('Collins-Soper kernel (two-momentum ratio)')
        ax.grid(alpha=0.3)
        fig.tight_layout()
        p = os.path.join(out_dir, 'cs_kernel.png')
        fig.savefig(p, dpi=150); plt.close(fig); saved.append(p)

    logger(f"  TMD-PDF plots -> {out_dir} ({len(saved)} files)")
    return saved


def plot_tmd_ratio(ch_results, run_dir, momentum, logger=print,
                   nz=24, nb=1):
    """R(dt,dtau,z,b) 若干 (z,b) 点的比值曲线。"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    out_dir = os.path.join(run_dir, 'analysis', 'tmd_ratio')
    for had_name, res in ch_results.items():
        ratio = res['ratio']     # (Nsample, dt, dtau, nz, nb)
        rm = ratio.mean(0); re_ = sem(ratio, True)
        zs = [0, max(0, nz // 4), max(0, nz // 2), max(0, nz - 1)]
        bs = list(range(min(nb, 2)))
        fig, axes = plt.subplots(len(bs), len(zs),
                                 figsize=(4 * len(zs), 3.5 * len(bs)),
                                 squeeze=False)
        for _b in range(len(bs)):
            for _z in range(len(zs)):
                zz, bb = zs[_z], bs[_b]
                ax = axes[_b][_z]
                for dt in [8, 10, 12, 14]:
                    if dt >= rm.shape[0]:
                        continue
                    tau = np.arange(dt + 1)
                    xv = tau - dt / 2
                    yv = rm[dt, :dt + 1, zz, bb]
                    ye = re_[dt, :dt + 1, zz, bb]
                    ax.errorbar(xv, yv, yerr=ye, fmt='x', capsize=0, label=f'dt={dt}')
                ax.set_xlabel('tau - t_sep/2'); ax.set_ylabel('R')
                ax.set_title(f'z={zz} b⊥={bb}')
                ax.legend(fontsize=7); ax.grid(alpha=0.3)
        fig.suptitle(f'{had_name} {momentum}: Disconnected TMD ratio')
        fig.tight_layout()
        fig.savefig(os.path.join(out_dir, f'ratio_{had_name}_{momentum}.png'), dpi=150)
        plt.close(fig)
    logger(f"  TMD ratio plots saved to {out_dir}")
