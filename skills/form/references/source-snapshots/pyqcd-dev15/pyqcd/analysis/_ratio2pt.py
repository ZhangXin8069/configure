"""
02_ratio 功能：3pt/2pt 比值 R(z) 计算 + 逐 z 多参数拟合 + 画图（独立实现）
============================================================================

功能对齐 refer/huangcl/02_ratio/code.py：

- Part 1 compute：读 2pt 切片（twopt_slice_pp_*）与 3 个 OPE（ops_mu0_nu1 /
  ops_mu3_nu0 / ops_mu3_nu1）→ 组合 O = −O30 − O31 + 2·O01 → 平移不变相对
  时间构造 C3 = C2×OPE（不相连因子化）→ jackknife/bootstrap 重采样 →
  真空扣除 ratio = ⟨(C3 − C2·⟨OPE⟩)/C2⟩_ti → 保存 ratio_Pz*_Nsam*_dtmax*.npy。
- Part 2 fit：模型 R = c0 + c1·e^{−dE·dtau} + c1·e^{−dE·(dt−dtau)}，逐 z、
  逐样本 lsqfit 拟合（prior 优先）→ 0_fit_data.npz + 1_fit_report.txt。
- Part 3 plot：ratio.png（逐 z 子图 + Fit c0 色带）、c0.png、chi2.png。

数据读取路径模板可注入（data_root 下按 conf_id 组织），核心计算自包含。
"""
from __future__ import annotations

import gc
import os
import time
from dataclasses import dataclass, field, replace

import numpy as np

from ._disconnected import (aggregate_fit_statuses, cov_mat,
                            fit_status_from_samples, model_ratio,
                            model_ratio_jacobian, resample, sem)
from ._fitter import (FitParams, covariance_effective_rank,
                      covariance_sample_rank, fit, fit_identifiability,
                      fit_report_lines, make_summary_table)
from ..tools import get_backend


def _xp_to_np(x):
    """后端数组 → numpy（cupy/torch/numpy 兼容），供 resample/gvar 下游使用。"""
    try:
        return np.asarray(x)
    except Exception:
        import torch as _th
        return _th.as_tensor(x).detach().cpu().numpy()


@dataclass
class SampleParams2pt:
    """样本与系综参数。"""

    conf_short: str
    conf_name: str
    conf_ids: list
    Nt: int
    Nx: int
    Px: int
    Py: int
    Pz: int
    Nsample: int
    dt_max: int

    @property
    def Nconf(self):
        return len(self.conf_ids)


@dataclass
class PlotParamsRatio:
    """ratio/c0/chi2 画图参数。"""

    plot_z: int = 2
    dt_list: list = field(default_factory=lambda: list(range(6, 13)))
    z_list: list = field(default_factory=lambda: list(range(0, 24, 4)))
    xlim: list = field(default_factory=lambda: [-7, 7])
    ylim: list = field(default_factory=lambda: [-0.1, 1.0])
    c0_ylim: list = field(default_factory=lambda: [-0.2, 1.0])
    colors: list = field(default_factory=lambda: [
        "#b3d9ff", "#c7e9c0", "#fdd49e", "#d4b9da", "#99d8c9",
        "#6baed6", "#41ab5d", "#ef6548", "#8856a7", "#08306b",
    ])


def ope_combine(ope01, ope30, ope31):
    """组合胶子 OPE：O = −O30 − O31 + 2·O01，转置到 (conf, tau, z)。"""
    return (-ope30 - ope31 + 2 * ope01).transpose(0, 2, 1)


def load_raw(data_root, conf_id, sampa: SampleParams2pt, tdir=(0, 1),
             dz=None):
    """读取单个组态的 2pt 切片与 OPE。

    数据布局（参考集群约定，可参数化）:
        {data_root}/{conf_name}/momsmear2z/{conf_id}/twopt_slice_pp_*_{conf_id}.npy
        {data_root}/{conf_short}/zdir/{conf_id}/ops_mu{a}_nu{b}_dz{dz}_conf{id}.npz["ops"]
    """
    dz = dz or sampa.Nx
    mom = f"Px{sampa.Px}Py{sampa.Py}Pz{sampa.Pz}"
    corr_path = os.path.join(
        data_root, sampa.conf_name, "momsmear2z", str(conf_id),
        f"twopt_slice_pp_{mom}_eginphase2_Cg5g4_nopol_ss_conf{conf_id}.npy")
    ope_dir = os.path.join(data_root, sampa.conf_short, "zdir", str(conf_id))
    mu1, nu1 = tdir
    ope01 = np.load(os.path.join(
        ope_dir, f"ops_mu{mu1}_nu{nu1}_dz{dz}_conf{conf_id}.npz"))["ops"]
    ope30 = np.load(os.path.join(
        ope_dir, f"ops_mu3_nu{mu1}_dz{dz}_conf{conf_id}.npz"))["ops"]
    ope31 = np.load(os.path.join(
        ope_dir, f"ops_mu3_nu{nu1}_dz{dz}_conf{conf_id}.npz"))["ops"]
    return np.load(corr_path), ope01, ope30, ope31


def compute_ratio(data_root, sampa: SampleParams2pt, jack: bool,
                  verbose=True) -> np.ndarray:
    """加载 2pt + OPE 计算 ratio 数组。

    Returns
    -------
    ratio : (Nsample, dt_max, dt_max, Nx)，real。
    """
    if verbose:
        print("==================== compute ratio start ====================")

    _corr = np.zeros((sampa.Nconf, sampa.Nt, sampa.Nt), dtype=complex)
    _ope_01 = np.zeros((sampa.Nconf, sampa.Nx, sampa.Nt), dtype=complex)
    _ope_30 = np.zeros((sampa.Nconf, sampa.Nx, sampa.Nt), dtype=complex)
    _ope_31 = np.zeros((sampa.Nconf, sampa.Nx, sampa.Nt), dtype=complex)

    for i, conf_id in enumerate(sampa.conf_ids):
        c, o01, o30, o31 = load_raw(data_root, conf_id, sampa)
        _corr[i] = c
        _ope_01[i] = o01
        _ope_30[i] = o30
        _ope_31[i] = o31
    if verbose:
        print("load finish")
        print("2pt shape:", _corr.shape)
        print("ope shape:", _ope_01.shape)

    if jack and sampa.Nconf < 2:
        if verbose:
            print("Nconf<2: delete-one jackknife is statistically unidentifiable")
            print("==================== compute ratio end ====================")
        return np.full(
            (sampa.Nconf, sampa.dt_max, sampa.dt_max, sampa.Nx),
            np.nan,
            dtype=np.float64,
        )

    _ope = ope_combine(_ope_01, _ope_30, _ope_31)   # (Nconf, tau, z)

    _corr2_rel = np.zeros((sampa.Nconf, sampa.Nt, sampa.dt_max), dtype=complex)
    _ope_rel = np.zeros((sampa.Nconf, sampa.Nt, sampa.dt_max, sampa.Nx),
                        dtype=complex)
    for ti in range(sampa.Nt):
        corr2_shift = np.roll(_corr[:, :, ti], shift=-ti, axis=1)
        _corr2_rel[:, ti, :] = corr2_shift[:, :sampa.dt_max]
        ope_shift = np.roll(_ope, shift=-ti, axis=1)
        _ope_rel[:, ti, :, :] = ope_shift[:, :sampa.dt_max, :]

    # C3 = C2×OPE（不相连因子化）：_corr3[Nconf,Nt,dt_max(_dt),dt_max(_dtau),Nx]，
    # 仅 _dtau<=_dt 非零（与原双循环一致）。该中间数组在 Nconf=405 时约 4.5 GB，
    # 是分析链唯一的大计算/内存热点：经 pyqcd 后端切换上 GPU。
    #   - CPU(numpy)：保留原双循环（实测比全广播更快，避免 4.5GB 大广播分配开销）
    #   - GPU(cupy/torch)：向量化单核广播（一次大核，远优于 400 次小核启动）
    xp = get_backend()
    if xp is np:
        _corr3 = np.zeros((sampa.Nconf, sampa.Nt, sampa.dt_max,
                           sampa.dt_max, sampa.Nx), dtype=complex)
        for _dt in range(sampa.dt_max):
            for _dtau in range(_dt + 1):
                _corr3[:, :, _dt, _dtau, :] = (
                    _ope_rel[:, :, _dtau, :] * _corr2_rel[:, :, _dt][:, :, None])
    else:
        mask = xp.tril(xp.ones((sampa.dt_max, sampa.dt_max)))  # 下三角：_dtau<=_dt
        _corr3 = (xp.asarray(_ope_rel)[:, :, None, :, :]
                  * xp.asarray(_corr2_rel)[:, :, :, None, None]) \
            * mask[None, None, :, :, None]
        _corr3 = _xp_to_np(_corr3)

    del _corr, _ope, _ope_30, _ope_31, _ope_01
    gc.collect()

    corr2 = resample(_corr2_rel, jack, sampa.Nsample)
    ope = resample(_ope_rel, jack, sampa.Nsample)
    corr3 = resample(_corr3, jack, sampa.Nsample)

    del _corr2_rel, _ope_rel, _corr3
    gc.collect()

    corr3_disc = corr3 - corr2[:, :, :, None, None] * ope[:, :, None, :, :]
    eps = 1e-30   # 除零保护（与 _disconnected.py 一致）
    ratio = np.mean(corr3_disc / (corr2[:, :, :, None, None] + eps), axis=1)
    ratio = ratio.real
    if verbose:
        print("ratio shape:", ratio.shape)
        print("==================== compute ratio end ====================")
    return ratio


def ratio_file_name(sampa: SampleParams2pt) -> str:
    """ratio 保存文件名（参考约定，含 Pz/Nsample/dt_max）。"""
    return (f"ratio_Pz{sampa.Pz}_Nsam{sampa.Nsample}"
            f"_dtmax{sampa.dt_max}.npy")


def fit_dir_name(sampa: SampleParams2pt, fitpa: FitParams, tag: str = "fit") -> str:
    """拟合目录名：fit_Pz*_Nsam*_dtmax*_tsep{}_{}_nex{}。"""
    return (f"{tag}_Pz{sampa.Pz}_Nsam{sampa.Nsample}_dtmax{sampa.dt_max}"
            f"_tsep{fitpa.dt_start}_{fitpa.dt_end}_nex{fitpa.nex}")


def fit_x_coor(fitpa: FitParams) -> list:
    """拟合坐标 (dt, dtau) 列表：dtau ∈ [nex, dt−nex]。"""
    for name, value in (("dt_start", fitpa.dt_start),
                        ("dt_end", fitpa.dt_end), ("nex", fitpa.nex)):
        if (isinstance(value, (bool, np.bool_))
                or not isinstance(value, (int, np.integer))):
            raise ValueError(f"{name} 必须是非布尔整数")
    if fitpa.dt_start < 0 or fitpa.dt_end < fitpa.dt_start:
        raise ValueError("须满足 0 <= dt_start <= dt_end")
    if fitpa.nex < 0:
        raise ValueError("nex 必须非负")
    if fitpa.dt_start < 2 * fitpa.nex:
        raise ValueError("dt_start 必须满足 dt_start >= 2*nex")
    return [(dt, dtau)
            for dt in range(fitpa.dt_start, fitpa.dt_end + 1)
            for dtau in range(fitpa.nex, dt - fitpa.nex + 1)]


def do_fit_and_report(ratio, fitpa: FitParams, sampa: SampleParams2pt,
                      fit_dir: str, jack: bool, verbose=True) -> dict:
    """逐 z、逐样本拟合，输出 0_fit_data.npz + 1_fit_report.txt。

    Returns
    -------
    fit_result : 数值结果以及 ``fit_status``/``fit_reason`` 和秩诊断元数据。
    """
    if verbose:
        print("==================== do_fit start ====================")

    ratio = np.asarray(ratio)
    if ratio.ndim != 4:
        raise ValueError("ratio 必须为 (Nsample, dt, dtau, z) 四维数组")
    if ratio.shape[0] != sampa.Nsample:
        raise ValueError("ratio 的样本轴必须等于 sampa.Nsample")
    if ratio.shape[3] < sampa.Nx:
        raise ValueError("ratio 的 z 轴短于 sampa.Nx")
    x_coor = fit_x_coor(fitpa)
    if fitpa.dt_end >= ratio.shape[1]:
        raise ValueError("dt_end 超出 ratio 的 dt 轴")
    if any(dtau < 0 or dtau >= ratio.shape[2]
           for _dt, dtau in x_coor):
        raise ValueError("拟合窗口的 dtau 超出 ratio 轴范围")
    Ndata = len(x_coor)
    param_names = list(fitpa.p0.keys())

    all_fit_result = {name: np.full((sampa.Nsample, sampa.Nx), np.nan)
                      for name in param_names + ["chi2"]}
    all_cond = np.zeros(sampa.Nx)
    fit_status_by_z = ["statistically_unidentifiable"] * sampa.Nx
    # Keep reasons as Python strings until serialization so a future
    # practical-identifiability diagnostic is not silently truncated.
    fit_reason_by_z = [""] * sampa.Nx
    effective_rank_by_z = np.zeros(sampa.Nx, dtype=np.int64)
    sample_rank_by_z = np.zeros(sampa.Nx, dtype=np.int64)
    required_rank = len(param_names)
    model_fitpa = (
        fitpa if fitpa.jacobian is not None
        else replace(fitpa, jacobian=model_ratio_jacobian)
    )

    report_lines = fit_report_lines(
        f"Fit Report: {sampa.conf_short}", {
            "t_sep range": f"[{fitpa.dt_start}, {fitpa.dt_end}]",
            "nex": fitpa.nex,
            "Nsample": sampa.Nsample,
            "jackknife": jack,
        })

    for _z in range(sampa.Nx):
        t0_fit = time.perf_counter()
        sub_sample = np.zeros((sampa.Nsample, Ndata))
        for i, (dt, dtau) in enumerate(x_coor):
            sub_sample[:, i] = ratio[:, dt, dtau, _z]

        has_prior = fitpa.prior is not None and len(fitpa.prior) > 0
        _fit_result = {
            name: np.full(sampa.Nsample, np.nan)
            for name in param_names + ["chi2"]
        }
        if jack and sampa.Nconf < 2:
            # ``compute_ratio`` intentionally emits NaN for this statistical
            # boundary.  Preserve that status artifact without passing an
            # intentionally non-finite sample through the strict fit API.
            _cov = np.zeros((Ndata, Ndata), dtype=np.float64)
            _cond = np.inf
            _last_fit = None
            effective_rank = 0
            sample_rank = 0
            fit_reason = (
                f"Nconf={sampa.Nconf} cannot support delete-one "
                "jackknife covariance"
            )
            fit_status, fit_reason, _ = fit_status_from_samples(
                _fit_result, _last_fit, has_prior=has_prior,
                failure_reason=fit_reason)
        else:
            _fit_result, _cov, _cond, _last_fit = fit(
                sub_sample, x_coor, model_ratio, model_fitpa, jack)
            effective_rank = covariance_effective_rank(_cov, fitpa.svdcut)
            sample_rank = covariance_sample_rank(_cov)
            gate_ok, gate_reason = fit_identifiability(
                Ndata, required_rank, effective_rank,
                sample_rank=sample_rank, has_prior=has_prior)
            fit_status, fit_reason, _ = fit_status_from_samples(
                _fit_result, _last_fit, has_prior=has_prior,
                failure_reason=None if gate_ok else gate_reason)
        for name in param_names + ["chi2"]:
            all_fit_result[name][:, _z] = _fit_result[name]
        all_cond[_z] = _cond
        fit_status_by_z[_z] = fit_status
        fit_reason_by_z[_z] = fit_reason
        effective_rank_by_z[_z] = effective_rank
        sample_rank_by_z[_z] = sample_rank

        if verbose:
            print(f"z={_z}")
            if fit_status in ("identifiable", "prior_constrained"):
                for name in param_names:
                    print(f"{name} = {all_fit_result[name][:, _z].mean():.3g} "
                          f"+- {sem(all_fit_result[name][:, _z], jack):.3g}")
                print(f"chi2 = {all_fit_result['chi2'][:, _z].mean():.3g}")
            else:
                print(f"fit status = {fit_status} "
                      f"({fit_reason})")
            print(f"fit z = {_z}, time: {time.perf_counter() - t0_fit:.2f}s\n")

        report_lines.append(f"z = {_z}")
        report_lines.append("-" * 72)
        report_lines.append(f"condition number = {_cond:.3g}")
        report_lines.append(
            f"fit status = {fit_status}")
        report_lines.append(
            f"effective covariance rank = {effective_rank}")
        report_lines.append(f"sample covariance rank = {sample_rank}")
        report_lines.append(f"required parameter rank = {required_rank}")
        if fit_status not in ("identifiable", "prior_constrained"):
            report_lines.append(f"fit skipped: {fit_reason}")
        report_lines.append("")
        if _last_fit is not None:
            report_lines.append(_last_fit.format(maxline=True))
        report_lines.append("")

    # ---- Summary Table ----
    report_lines.append("=" * 72)
    report_lines.append("  Summary Table")
    report_lines.append("=" * 72)
    summary_rows = []
    for _z in range(sampa.Nx):
        row = [str(_z)]
        valid = (fit_status_by_z[_z] in ("identifiable", "prior_constrained")
                 and np.isfinite(all_fit_result["chi2"][:, _z]).all())
        if valid:
            for name in param_names:
                mean = all_fit_result[name][:, _z].mean()
                err = sem(all_fit_result[name][:, _z], jack)
                row.append(f"{mean:.3f}({err * 1e3:.0f})")
            row.append(f"{all_fit_result['chi2'][:, _z].mean():.2g}")
        else:
            row.extend(["N/A"] * (len(param_names) + 1))
        summary_rows.append(row)
    report_lines.append(make_summary_table(
        ["z"] + param_names + ["chi2/dof"], summary_rows))
    report_lines.append("")

    aggregate_status, aggregate_reason = aggregate_fit_statuses(
        fit_status_by_z, fit_reason_by_z)
    report_lines.insert(5, f"  fit status      : {aggregate_status}")
    report_lines.insert(6, f"  fit reason      : {aggregate_reason}")
    fit_metadata = {
        "fit_status": aggregate_status,
        "fit_status_by_z": np.asarray(fit_status_by_z),
        "fit_reason": aggregate_reason,
        "fit_reason_by_z": np.asarray(fit_reason_by_z),
        "condition_number": all_cond,
        "effective_rank": effective_rank_by_z,
        "sample_rank": sample_rank_by_z,
        "required_rank": np.asarray(required_rank, dtype=np.int64),
    }
    all_fit_result.update(fit_metadata)
    with open(os.path.join(fit_dir, "1_fit_report.txt"), "w") as f:
        f.write("\n".join(report_lines))
    np.savez(
        os.path.join(fit_dir, "0_fit_data.npz"),
        **all_fit_result,
    )
    if verbose:
        print(f"report saved to {fit_dir}/1_fit_report.txt")
        print(f"fit result saved to {fit_dir}/0_fit_data.npz")
        print("==================== do_fit end ====================")
    return all_fit_result


def _fit_status_by_z(fit_result, nz):
    """读取拟合状态；旧 numeric-only 产物显式标为 unavailable。"""
    status_by_z = fit_result.get("fit_status_by_z")
    if status_by_z is not None:
        status_by_z = np.asarray(status_by_z).reshape(-1)
        if status_by_z.size == nz:
            return status_by_z.astype(str)
        return np.full(nz, "unavailable", dtype="<U32")

    aggregate = fit_result.get("fit_status")
    if aggregate is None:
        return np.full(nz, "unavailable", dtype="<U32")
    aggregate = np.asarray(aggregate).reshape(-1)
    if aggregate.size != 1:
        return np.full(nz, "unavailable", dtype="<U32")
    return np.full(nz, str(aggregate[0]), dtype="<U32")


def _fit_reason_for_z(fit_result, z):
    """返回指定 z 的状态原因，兼容旧 numeric-only 结果。"""
    reasons = fit_result.get("fit_reason_by_z")
    if reasons is not None:
        reasons = np.asarray(reasons).reshape(-1)
        if z < reasons.size and str(reasons[z]):
            return str(reasons[z])
    reason = fit_result.get("fit_reason")
    if reason is None:
        return "central fit status is unavailable"
    reason = np.asarray(reason).reshape(-1)
    if reason.size != 1:
        return "central fit status is unavailable"
    return str(reason[0])


def plot_ratio_fits(ratio, fit_result, sampa: SampleParams2pt,
                    fitpa: FitParams, plotpa: PlotParamsRatio,
                    out_dir: str, jack: bool, verbose=True) -> list:
    """绘制 ratio.png（逐 z 子图 + Fit c0 色带）、c0.png、chi2.png。

    Returns
    -------
    list: 保存的图片路径列表。
    """
    from ._plots import plot_single_chi2, plot_single_errbar
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if verbose:
        print("==================== plot_ratio start ====================")
    time0 = time.perf_counter()

    para_c0 = fit_result["c0"]
    chi2 = fit_result["chi2"]
    ratio_mean = ratio.mean(0)
    ratio_err = sem(ratio, jack)
    status_by_z = _fit_status_by_z(fit_result, para_c0.shape[1])
    unique_status = np.unique(status_by_z)
    fit_status_label = (str(unique_status[0]) if unique_status.size == 1
                        else "mixed")
    status_valid = np.isin(status_by_z, ["identifiable", "prior_constrained"])
    valid_z = (status_valid
               & np.isfinite(para_c0).all(axis=0)
               & np.isfinite(chi2).all(axis=0))
    c0_mean = np.full(para_c0.shape[1], np.nan)
    c0_err = np.full(para_c0.shape[1], np.nan)
    chi2_mean = np.full(chi2.shape[1], np.nan)
    if np.any(valid_z):
        c0_mean[valid_z] = para_c0[:, valid_z].mean(0)
        c0_err[valid_z] = sem(para_c0[:, valid_z], jack)
        chi2_mean[valid_z] = chi2[:, valid_z].mean(0)

    n_z = len(plotpa.z_list)
    n_cols = 3
    n_rows = int(np.ceil(n_z / n_cols))

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(10.5, 4 * n_rows),
                             sharex=True, sharey=True, dpi=150)
    axes_flat = np.atleast_1d(axes).ravel()

    for idx, _z in enumerate(plotpa.z_list):
        ax = axes_flat[idx]
        band_down = c0_mean[_z] - c0_err[_z]
        band_up = c0_mean[_z] + c0_err[_z]

        for i, dt in enumerate(plotpa.dt_list):
            tau_vals = np.arange(0, dt + 1)
            x_vals = tau_vals - dt / 2.0
            color = plotpa.colors[i % len(plotpa.colors)]
            ax.errorbar(x_vals, ratio_mean[dt, tau_vals, _z],
                        yerr=ratio_err[dt, tau_vals, _z],
                        fmt="x", color=color, ecolor=color, capsize=0,
                        markersize=7, markeredgewidth=1.8, linewidth=1.2,
                        zorder=3, label=f"dt={dt}")

        x_band = np.array(plotpa.xlim)
        if valid_z[_z]:
            ax.fill_between(x_band, [band_down, band_down], [band_up, band_up],
                            color="gray", alpha=0.35, linewidth=0, zorder=1,
                            label="Fit c0")
            c0_str = (f"{para_c0[:, _z].mean():.3f}"
                      f"({sem(para_c0[:, _z], jack) * 1e3:.0f})")
            title = (f"z={_z}, c0={c0_str}, chi2={chi2_mean[_z]:.2f}"
                     f" [{status_by_z[_z]}]")
        else:
            title = f"z={_z}, fit={status_by_z[_z]}"
            ax.text(0.5, 0.08,
                    f"fit unavailable: {_fit_reason_for_z(fit_result, _z)}",
                    transform=ax.transAxes, ha="center", va="bottom",
                    fontsize=8, color="darkred")
        ax.set_title(title, fontsize=12)
        ax.set_xlim(plotpa.xlim[0], plotpa.xlim[1])
        ax.set_ylim(plotpa.ylim[0], plotpa.ylim[1])
        ax.set_box_aspect(3 / 4)
        ax.legend(loc="upper right", fontsize=8)

    for idx in range(n_z, n_rows * n_cols):
        axes_flat[idx].set_visible(False)

    fig.supxlabel("t_ins - t_sep/2", fontsize=16)
    fig.supylabel("C3 / C2", fontsize=16)
    fig.suptitle(
        f"Unpolarized, P({sampa.Px},{sampa.Py},{sampa.Pz}), "
        f"Nconf={sampa.Nconf}, Nsample = {sampa.Nsample}\n"
        f"fit: tsep = [{fitpa.dt_start}, {fitpa.dt_end}], nex = {fitpa.nex}",
        fontsize=13, y=1.02)
    plt.tight_layout()
    saved = [os.path.join(out_dir, "ratio.png")]
    fig.savefig(saved[0], bbox_inches="tight")
    plt.close(fig)

    # ---- c0 vs z ----
    z_vals = np.arange(sampa.Nx)
    title = (f"Unpolarized, P({sampa.Px},{sampa.Py},{sampa.Pz}), "
             f"Nconf={sampa.Nconf}, Nsample = {sampa.Nsample}\n"
             f"fit: tsep = [{fitpa.dt_start}, {fitpa.dt_end}], nex = {fitpa.nex}\n"
             f"fit status = {fit_status_label}")
    saved.append(os.path.join(out_dir, "c0.png"))
    plot_single_errbar(z_vals, c0_mean, c0_err, saved[-1],
                       xlabel="z", ylabel="c0",
                       xlim=[-0.5, sampa.Nx - 0.5], ylim=plotpa.c0_ylim,
                       title=title, label="c0")

    # ---- chi2 vs z ----
    saved.append(os.path.join(out_dir, "chi2.png"))
    plot_single_chi2(z_vals, chi2_mean, saved[-1],
                     xlabel="z", title=title, label="chi2/dof")

    if verbose:
        print(f"plot saved to {out_dir}/ratio.png")
        print(f"plot saved to {out_dir}/c0.png")
        print(f"plot saved to {out_dir}/chi2.png")
        print(f"plot done, time: {time.perf_counter() - time0:.2f}s")
        print("==================== plot_ratio end ====================")
    return saved


def run_ratio2pt(data_root, out_root, sampa: SampleParams2pt,
                 fitpa_list, plotpa: PlotParamsRatio, jack: bool = True,
                 parts=(1, 3), verbose=True) -> dict:
    """02_ratio 全链：compute → fit（多窗口）→ plot。

    parts: (start, end)，1=ratio 计算，2=拟合，3=画图；start>1 时从中间产物读取。
    """
    result = {"saved": []}
    ratio_dir = os.path.join(out_root, sampa.conf_short)
    os.makedirs(ratio_dir, exist_ok=True)
    ratio_path = os.path.join(ratio_dir, ratio_file_name(sampa))

    if parts[0] <= 1:
        time0 = time.perf_counter()
        ratio = compute_ratio(data_root, sampa, jack, verbose=verbose)
        np.save(ratio_path, ratio)
        if verbose:
            from ._plots import get_peak_memory_gb
            print(f"ratio saved to {ratio_path}")
            print(f"Peak Memory: {get_peak_memory_gb():.3f} GB")
            print(f"spend time: {time.perf_counter() - time0:.2f}s\n")
    else:
        ratio = np.load(ratio_path)
        if verbose:
            print(f"===== skip compute ratio, loading ratio from file =====")
            print(f"ratio loaded, shape: {ratio.shape}")

    result["ratio"] = ratio

    for _fitpa in fitpa_list:
        _fit_dir = os.path.join(ratio_dir, fit_dir_name(sampa, _fitpa))
        os.makedirs(_fit_dir, exist_ok=True)
        if parts[0] <= 2:
            time0 = time.perf_counter()
            fit_result = do_fit_and_report(ratio, _fitpa, sampa, _fit_dir,
                                           jack, verbose=verbose)
            if verbose:
                print(f"spend time: {time.perf_counter() - time0:.2f}s\n")
        else:
            if verbose:
                print(f"===== skip do_fit, loading from file =====")
            fit_result = dict(np.load(os.path.join(_fit_dir, "0_fit_data.npz")))
        result.setdefault("fit_results", {})[fit_dir_name(sampa, _fitpa)] = fit_result

        if parts[0] <= 3:
            result["saved"] += plot_ratio_fits(
                ratio, fit_result, sampa, _fitpa, plotpa, _fit_dir, jack,
                verbose=verbose)
    return result
