"""
06_FH_bare_matele 功能：FH 变换 + 常数拟合 + 全套图（独立实现）
===============================================================

功能对齐 refer/huangcl/06_FH_bare_matele/code_FH_bare_matele.py：

- Part 1 FH：读取 6 个方向（pos_x/pos_y/pos_z/neg_x/neg_y/neg_z）的 ratio
  并平均 → FH 变换 FH(t) = Σ_{τ=nex}^{t+1−nex} R(t+1,τ) − Σ_{τ=nex}^{t−nex} R(t,τ)
  → 保存 FH_nex{n}.npy → 画 FH 图（多 nex 对比，z{iz}.png）。
- Part 2 fit：模型 FH(t) = c0（常数），逐 z 拟合 → fit_nex{N}/dt{}_{}/
  report_dt{}_{}.txt + fit_dt{}_{}.npz。
- Part 3 plot：每窗口参数 vs z（c0.png/chi2.png）、多窗口对比图
  （参数+chi2.png）、bestfit FH + c0 色带图（bestfit/）。

数据布局（参考约定）: <data_root>/<conf>/P{4}/{pos_x,...}/ratio.npy。
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field, replace

import numpy as np

from ._disconnected import (aggregate_fit_statuses, fit_status_from_samples,
                            sem)
from ._fitter import (FitParams, fit, fit_report_lines, make_summary_table)
from ._plots import plot_errbar, plot_scatter


@dataclass
class FHParams:
    """06 参数。"""

    conf_short: str
    P: int                       # 动量大小
    nexmax: int = 2              # FH 时 τ 两端去掉点数循环上限
    ave_dirs: list = field(default_factory=lambda: [
        "pos_x", "pos_y", "pos_z", "neg_x", "neg_y", "neg_z"])
    z_list: list = field(default_factory=lambda: list(range(8)))
    z_step: int = 3
    xoffset: float = 0.2
    fh_xlim: list = field(default_factory=lambda: [2.5, 11.5])
    fh_ylim: list = field(default_factory=lambda: [-0.1, 1.1])
    para_xlim: list = field(default_factory=lambda: [-0.5, 24.5])
    param_ylim: dict = field(default_factory=lambda: {
        "c0": [-0.1, 1.0], "c1": [-0.5, 0.5],
        "c2": [-0.1, 0.1], "dE": [0.0, 1.0]})


def load_one_ratio(data_root: str, conf_short: str, P: int, dir: str) -> np.ndarray:
    """读取单方向 ratio (Nsample, dt, dtau, z)。"""
    path = os.path.join(data_root, conf_short, f"P{P}", dir, "ratio.npy")
    if not os.path.exists(path):
        raise FileNotFoundError(f"ratio file not found: {path}")
    return np.load(path)


def compute_fh(ratio: np.ndarray, save_path: str, nex: int = 0,
               verbose=True) -> np.ndarray:
    """FH 变换：FH(t) = Σ_{τ=nex}^{t+1−nex} R(t+1,τ) − Σ_{τ=nex}^{t−nex} R(t,τ)。

    Returns
    -------
    fh : (Nsample, dt, z)
    """
    if verbose:
        print(f"  computing FH (nex={nex}) ")

    Nsample, dtmax, _, Nz = ratio.shape
    temp = np.zeros((Nsample, dtmax, Nz))
    for dt in range(2 * nex, dtmax):
        temp[:, dt] = ratio[:, dt, nex:dt - nex + 1, :].sum(axis=1)
    fh = temp - np.roll(temp, 1, axis=1)

    if verbose:
        print(f"    FH shape: (Nsample, dt, z) = {fh.shape}")
    np.save(save_path, fh)
    if verbose:
        print(f"    FH saved to: {save_path}")
    return fh


def fh_model(t, p):
    """FH(t) ≈ c0（常数模型）。"""
    return p["c0"] * np.ones_like(np.asarray(t, dtype=np.float64))


def fh_model_jacobian(t, p):
    """Closed-form real-parameter Jacobian of :func:`fh_model`."""
    del p
    return {
        "c0": np.ones_like(np.asarray(t, dtype=np.float64)),
    }


def plot_fh(all_fh: dict, save_dir: str, params: FHParams,
            c0_data: dict = None, band_t_range: tuple = None,
            verbose=True) -> list:
    """画 FH 图：每个 z 一张，多 nex 对比 errorbar；可选 c0 色带。"""
    saved = []
    _first_nex = next(iter(all_fh.keys()))
    _, dt_max, Nz = all_fh[_first_nex].shape
    t_vals = np.arange(dt_max)

    for _iz in params.z_list:
        if _iz >= Nz:
            if verbose:
                print(f"    Warning: z={_iz} exceeds Nz={Nz}, skipping")
            continue

        _data = {}
        for _nex, _fh in sorted(all_fh.items()):
            _data[f"nex={_nex}"] = (_fh.mean(0)[:, _iz],
                                    sem(_fh, jackknife=False)[:, _iz])

        _show_band = False
        _band_x = _band_down = _band_up = _band_label = None
        if c0_data is not None and _iz in c0_data:
            c0_mean, c0_err = c0_data[_iz]
            _show_band = True
            if band_t_range is not None:
                _band_x = np.arange(band_t_range[0], band_t_range[1] + 1,
                                    dtype=float)
            else:
                _band_x = t_vals
            _band_down = np.full_like(_band_x, c0_mean - c0_err, dtype=float)
            _band_up = np.full_like(_band_x, c0_mean + c0_err, dtype=float)
            _band_label = f"c0 = {c0_mean:.3f} ± {c0_err:.3f}"

        sp = os.path.join(save_dir, f"z{_iz}.png")
        plot_errbar(t_vals, _data, sp,
                    xlabel="t", ylabel="FH",
                    xlim=params.fh_xlim, ylim=params.fh_ylim,
                    x_offset=params.xoffset,
                    title=f"{params.conf_short}, P={params.P}, z={_iz}",
                    show_band=_show_band, band_x=_band_x,
                    band_y_down=_band_down, band_y_up=_band_up,
                    band_label=_band_label)
        saved.append(sp)
    return saved


def do_fit_and_report(fh: np.ndarray, save_dir: str, fitpa: FitParams,
                      params: FHParams, debug: bool = False,
                      debugsample: int = 20, verbose=True):
    """对 FH 数据逐 z 拟合（常数模型），输出报告与 npz。"""
    Nsample, _, Nz = fh.shape
    dt_start, dt_end = fitpa.dt_start, fitpa.dt_end
    param_names = list(fitpa.p0.keys())
    window_tag = f"dt{dt_start}_{dt_end}"
    t_vals = np.arange(dt_start, dt_end + 1, dtype=int)
    model_fitpa = (
        fitpa if fitpa.jacobian is not None
        else replace(fitpa, jacobian=fh_model_jacobian)
    )

    Nfit = min(debugsample, Nsample) if debug else Nsample
    if verbose:
        print(f"\n    fitting window: t = [{dt_start}, {dt_end}], "
              f"Nfit = {Nfit}/{Nsample}")

    all_fit_result = {name: np.full((Nfit, Nz), np.nan)
                      for name in param_names + ["chi2"]}
    all_cond = np.zeros(Nz)
    fit_status_by_z = np.full(
        Nz, "statistically_unidentifiable", dtype="<U32")
    fit_reason_by_z = np.full(Nz, "", dtype="<U256")
    effective_rank_by_z = np.zeros(Nz, dtype=np.int64)
    sample_rank_by_z = np.zeros(Nz, dtype=np.int64)

    lines = fit_report_lines(
        f"Fit Report, {window_tag}, nex={fitpa.nex}", {
            "model": "FH(t) = c0",
            "fitpa": f"p0={fitpa.p0}, t=[{dt_start},{dt_end}]",
        })

    for _iz in range(Nz):
        _tz = time.perf_counter()
        y_data = fh[:, t_vals, _iz]

        _fit_result, _cov, _cond, _last_fit = fit(
            y_coor=y_data, x_coor=t_vals, model=fh_model, fitpa=model_fitpa,
            jackknife=False, debug=debug, debugNfit=debugsample)
        fit_status, fit_reason, _finite_mask = fit_status_from_samples(
            _fit_result, _last_fit,
            has_prior=fitpa.prior is not None and len(fitpa.prior) > 0)
        if verbose:
            print(f"z = {_iz}, time = {time.perf_counter() - _tz:.2f}s")

        for name in param_names + ["chi2"]:
            all_fit_result[name][:, _iz] = _fit_result[name][:Nfit]
        all_cond[_iz] = _cond
        fit_status_by_z[_iz] = fit_status
        fit_reason_by_z[_iz] = fit_reason
        from ._fitter import covariance_effective_rank, covariance_sample_rank
        effective_rank_by_z[_iz] = covariance_effective_rank(
            _cov, fitpa.svdcut)
        sample_rank_by_z[_iz] = covariance_sample_rank(_cov)

        lines.append(f"  z = {_iz}: condition number = {_cond:.3g}")
        lines.append(f"  fit status = {fit_status}")
        lines.append(f"  effective covariance rank = {effective_rank_by_z[_iz]}")
        lines.append(f"  sample covariance rank = {sample_rank_by_z[_iz]}")
        if fit_status not in ("identifiable", "prior_constrained"):
            lines.append(f"  fit skipped: {fit_reason}")
        if _last_fit is not None:
            lines.append(_last_fit.format(maxline=True))
        lines.append("")

    lines.append("=" * 72)
    lines.append(f"  Summary Table, {window_tag}, nex={fitpa.nex}")
    lines.append("=" * 72)
    summary_rows = []
    for _iz in range(Nz):
        row = [str(_iz)]
        valid = (fit_status_by_z[_iz] in ("identifiable", "prior_constrained")
                 and all(np.isfinite(all_fit_result[name][:, _iz]).all()
                         for name in param_names + ["chi2"]))
        if valid:
            for name in param_names:
                mean = all_fit_result[name][:, _iz].mean()
                err = sem(all_fit_result[name][:, _iz], False)
                row.append(f"{mean:.3f}({err * 1e3:.0f})")
            row.append(f"{all_fit_result['chi2'][:, _iz].mean():.2g}")
        else:
            row.extend(["N/A"] * (len(param_names) + 1))
        summary_rows.append(row)
    lines.append(make_summary_table(["z"] + param_names + ["chi2/dof"],
                                    summary_rows))
    lines.append("")

    aggregate_status, aggregate_reason = aggregate_fit_statuses(
        fit_status_by_z, fit_reason_by_z)
    lines.insert(6, f"  fit status      : {aggregate_status}")
    lines.insert(7, f"  fit reason      : {aggregate_reason}")
    with open(os.path.join(save_dir, f"report_{window_tag}.txt"), "w") as f:
        f.write("\n".join(lines))
    np.savez(os.path.join(save_dir, f"fit_{window_tag}.npz"),
             **all_fit_result,
             fit_status=np.asarray(aggregate_status),
             fit_status_by_z=fit_status_by_z,
             fit_reason=np.asarray(aggregate_reason),
             fit_reason_by_z=fit_reason_by_z,
             condition_number=all_cond,
             effective_rank=effective_rank_by_z,
             sample_rank=sample_rank_by_z)
    if verbose:
        print(f"    report saved to: {save_dir}/report_{window_tag}.txt")
        print(f"    fit result saved to: {save_dir}/fit_{window_tag}.npz")


_PLOT_FIT_STATUSES = frozenset(("identifiable", "prior_constrained"))


def _mapping_value(mapping, name):
    """Read a field from a dict-like result without inventing defaults."""
    try:
        value = mapping.get(name)
    except AttributeError:
        try:
            value = mapping[name]
        except (KeyError, IndexError, TypeError):
            return None
    except (KeyError, IndexError, TypeError):
        return None
    return value


def _status_by_z(fit_result, nz):
    """Return strict per-z statuses; absent or malformed metadata is invalid."""
    raw = _mapping_value(fit_result, "fit_status_by_z")
    if raw is None:
        return np.full(nz, "unavailable", dtype=object), \
            "fit_status_by_z is missing"
    try:
        raw = np.asarray(raw)
    except (TypeError, ValueError):
        return np.full(nz, "unavailable", dtype=object), \
            "fit_status_by_z is not an array"
    if raw.ndim != 1 or raw.size != nz:
        return np.full(nz, "unavailable", dtype=object), \
            f"fit_status_by_z shape {raw.shape} does not match ({nz},)"

    statuses = np.full(nz, "unavailable", dtype=object)
    for iz, value in enumerate(raw):
        if isinstance(value, (bytes, np.bytes_)):
            value = value.decode("utf-8", errors="replace")
        else:
            value = str(value)
        if value in _PLOT_FIT_STATUSES:
            statuses[iz] = value
    if not np.any(np.isin(statuses, list(_PLOT_FIT_STATUSES))):
        return statuses, "fit_status_by_z has no explicit usable status"
    return statuses, "fit_status_by_z contains unavailable or unknown z statuses"


def _valid_fit_z(fit_result, param_names, nz):
    """Mask z columns with explicit status and complete finite fit arrays."""
    statuses, status_reason = _status_by_z(fit_result, nz)
    valid = np.isin(statuses, list(_PLOT_FIT_STATUSES))
    sample_size = None
    for name in list(param_names) + ["chi2"]:
        value = _mapping_value(fit_result, name)
        if value is None:
            return np.zeros(nz, dtype=bool), f"fit field {name} is missing"
        try:
            array = np.asarray(value)
        except (TypeError, ValueError):
            return np.zeros(nz, dtype=bool), f"fit field {name} is invalid"
        if array.ndim != 2 or array.shape[1] != nz:
            return (np.zeros(nz, dtype=bool),
                    f"fit field {name} shape {array.shape} is not "
                    f"(n_sample, {nz})")
        if sample_size is None:
            sample_size = array.shape[0]
        elif array.shape[0] != sample_size:
            return (np.zeros(nz, dtype=bool),
                    "fit fields do not share the sample axis")
        try:
            valid &= np.isfinite(array).all(axis=0)
        except TypeError:
            return np.zeros(nz, dtype=bool), f"fit field {name} is non-numeric"
    if sample_size == 0:
        return np.zeros(nz, dtype=bool), "fit fields have no samples"
    if not np.any(valid):
        return valid, status_reason
    return valid, status_reason


def _log_plot_skip(path, reason, verbose):
    if verbose:
        print(f"    skip plot: {path} (fit status unavailable: {reason})")


def plot_para(all_fit_result: dict, save_dir: str, fitpa: FitParams,
              params: FHParams, verbose=True) -> list:
    """单窗口参数 vs z：参数 errorbar 图 + chi2 散点图。"""
    saved = []
    param_names = list(fitpa.p0.keys())
    if not param_names:
        _log_plot_skip(save_dir, "no fit parameters", verbose)
        return saved
    first = _mapping_value(all_fit_result, param_names[0])
    try:
        first = np.asarray(first)
    except (TypeError, ValueError):
        first = np.empty(0)
    if first.ndim != 2:
        _log_plot_skip(save_dir, "fit parameter shape is invalid", verbose)
        return saved
    Nz = first.shape[1]
    z_vals = np.arange(Nz)
    status_valid, status_reason = _valid_fit_z(
        all_fit_result, param_names, Nz)

    for _name in param_names:
        _arr = np.asarray(_mapping_value(all_fit_result, _name))
        if not np.any(status_valid):
            sp = os.path.join(save_dir, f"{_name}.png")
            _log_plot_skip(sp, status_reason, verbose)
            continue
        means = np.full(Nz, np.nan)
        errors = np.full(Nz, np.nan)
        for _iz in range(Nz):
            if status_valid[_iz]:
                means[_iz] = _arr[:, _iz].mean()
                errors[_iz] = sem(_arr[:, _iz], jackknife=False)
        sp = os.path.join(save_dir, f"{_name}.png")
        plot_errbar(z_vals, {_name: (means, errors)},
                    sp, xlabel="z", ylabel=_name,
                    xlim=params.para_xlim, ylim=params.param_ylim.get(_name),
                    title=f"{params.conf_short}, P={params.P}, "
                          f"fit: tsep=[{fitpa.dt_start},{fitpa.dt_end}]",
                    x_offset=0.3, figsize=(10, 6), dpi=150)
        saved.append(sp)

    _chi2_arr = _mapping_value(all_fit_result, "chi2")
    if _chi2_arr is None or not np.any(status_valid):
        sp = os.path.join(save_dir, "chi2.png")
        _log_plot_skip(sp, status_reason, verbose)
        return saved
    _chi2_arr = np.asarray(_chi2_arr)
    chi2_mean = np.full(Nz, np.nan)
    for _iz in range(Nz):
        if status_valid[_iz]:
            chi2_mean[_iz] = _chi2_arr[:, _iz].mean()
    sp = os.path.join(save_dir, "chi2.png")
    plot_scatter(z_vals, {"chi2/dof": chi2_mean}, sp,
                 xlabel="z", ylabel="chi2/dof",
                 xlim=params.para_xlim, ylim=[0, 2],
                 title=f"{params.conf_short}, P={params.P}, "
                       f"fit: tsep=[{fitpa.dt_start},{fitpa.dt_end}]",
                 x_offset=0.3, figsize=(10, 6), dpi=150,
                 show_hline=True, hline_y=1.0, hline_label="chi2/dof=1")
    saved.append(sp)
    return saved


def plot_para_cmp(fit_data: dict, save_dir: str, params: FHParams,
                  fitpa_list, verbose=True) -> list:
    """多窗口参数对比图：不同拟合窗口叠加（z 按 z_step 抽样）。"""
    saved = []
    if not fitpa_list or not fit_data:
        _log_plot_skip(save_dir, "no fit windows", verbose)
        return saved
    param_names = list(fitpa_list[0].p0.keys())

    Nz = None
    for _fitpa in fitpa_list:
        _tag = f"dt{_fitpa.dt_start}_{_fitpa.dt_end}"
        entry = _mapping_value(fit_data, _tag)
        first = _mapping_value(entry, param_names[0]) \
            if entry is not None else None
        try:
            first = np.asarray(first)
        except (TypeError, ValueError):
            continue
        if first.ndim == 2:
            Nz = first.shape[1]
            break
    if Nz is None:
        _log_plot_skip(save_dir, "fit parameter shapes are invalid", verbose)
        return saved
    z_vals = np.arange(Nz)[::params.z_step]
    window_data = {}
    for _fitpa in fitpa_list:
        _tag = f"dt{_fitpa.dt_start}_{_fitpa.dt_end}"
        entry = _mapping_value(fit_data, _tag)
        if entry is None:
            window_data[_tag] = (None, "fit window result is missing")
        else:
            window_data[_tag] = _valid_fit_z(entry, param_names, Nz)

    for _name in param_names:
        _data = {}
        for _fitpa in fitpa_list:
            _tag = f"dt{_fitpa.dt_start}_{_fitpa.dt_end}"
            entry = _mapping_value(fit_data, _tag)
            valid_z, _reason = window_data[_tag]
            if entry is None or not np.any(valid_z[::params.z_step]):
                continue
            _arr = np.asarray(_mapping_value(entry, _name))
            means = np.full(Nz, np.nan)
            errors = np.full(Nz, np.nan)
            for _iz in range(Nz):
                if valid_z[_iz]:
                    values = _arr[:, _iz]
                    means[_iz] = values.mean()
                    errors[_iz] = sem(values, jackknife=False)
            sampled_mean = means[::params.z_step]
            if np.isfinite(sampled_mean).any():
                _data[f"dt: {_fitpa.dt_start}~{_fitpa.dt_end}"] = (
                    sampled_mean, errors[::params.z_step])
        sp = os.path.join(save_dir, f"{_name}.png")
        if not _data:
            _log_plot_skip(
                sp,
                "no z has explicit identifiable/prior_constrained status "
                "and finite values",
                verbose,
            )
            continue
        plot_errbar(z_vals, _data, sp, xlabel="z", ylabel=_name,
                    xlim=params.para_xlim, ylim=params.param_ylim.get(_name),
                    title=f"{params.conf_short}, P={params.P}, {_name}",
                    x_offset=0.3, figsize=(10, 6), dpi=150)
        saved.append(sp)

    _chi2_data = {}
    for _fitpa in fitpa_list:
        _tag = f"dt{_fitpa.dt_start}_{_fitpa.dt_end}"
        entry = _mapping_value(fit_data, _tag)
        valid_z, _reason = window_data[_tag]
        if entry is None or not np.any(valid_z[::params.z_step]):
            continue
        _arr = np.asarray(_mapping_value(entry, "chi2"))
        means = np.full(Nz, np.nan)
        for _iz in range(Nz):
            if valid_z[_iz]:
                means[_iz] = _arr[:, _iz].mean()
        sampled_mean = means[::params.z_step]
        if np.isfinite(sampled_mean).any():
            _chi2_data[f"dt: {_fitpa.dt_start}~{_fitpa.dt_end}"] = (
                sampled_mean)
    sp = os.path.join(save_dir, "chi2.png")
    if not _chi2_data:
        _log_plot_skip(
            sp,
            "no z has explicit identifiable/prior_constrained status "
            "and finite values",
            verbose,
        )
        return saved
    plot_scatter(z_vals, _chi2_data, sp, xlabel="z", ylabel="chi2/dof",
                 xlim=params.para_xlim, ylim=[0, 2],
                 title=f"{params.conf_short}, P={params.P}, chi2/dof",
                 x_offset=0.3, figsize=(10, 6), dpi=150,
                 show_hline=True, hline_y=1.0, hline_label="chi2/dof=1")
    saved.append(sp)
    return saved


def run_fh(data_root, out_root, params: FHParams, fitpa_list,
           bestfit_params: dict = None, parts=(1, 3), verbose=True) -> dict:
    """06 全链：FH → fit（多窗口）→ plot（含 bestfit 色带图）。"""
    out_dir = os.path.join(out_root, params.conf_short, f"P{params.P}")
    os.makedirs(os.path.join(out_dir, "fh"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "bestfit"), exist_ok=True)
    result = {"saved": []}

    # ---- Part 1: FH ----
    if parts[0] <= 1:
        _t0 = time.perf_counter()
        _ratios = [load_one_ratio(data_root, params.conf_short, params.P, d)
                   for d in params.ave_dirs]
        ratio_ave = np.mean(_ratios, axis=0)
        if verbose:
            print(f"ratio_ave shape: {ratio_ave.shape}")

        fh_dir = os.path.join(out_dir, "fh")
        all_fh = {}
        for _nex in range(params.nexmax + 1):
            _fh_path = os.path.join(fh_dir, f"FH_nex{_nex}.npy")
            fh = compute_fh(ratio_ave, _fh_path, nex=_nex, verbose=verbose)
            all_fh[_nex] = fh
        result["saved"] += plot_fh(all_fh, fh_dir, params, verbose=verbose)
        result["fh"] = all_fh
        if verbose:
            print(f"    FH time: {time.perf_counter() - _t0:.2f}s\n")

    # ---- Part 2: fit ----
    _nex_fit = fitpa_list[0].nex
    fh = np.load(os.path.join(out_dir, "fh", f"FH_nex{_nex_fit}.npy"))
    if verbose:
        print(f"  loading FH (nex={_nex_fit}) shape: {fh.shape}")

    _fit_dir = os.path.join(out_dir, f"fit_nex{_nex_fit}")
    os.makedirs(_fit_dir, exist_ok=True)
    for _fitpa in fitpa_list:
        _tag = f"dt{_fitpa.dt_start}_{_fitpa.dt_end}"
        _window_dir = os.path.join(_fit_dir, _tag)
        os.makedirs(_window_dir, exist_ok=True)
        if parts[0] <= 2:
            do_fit_and_report(fh, _window_dir, _fitpa, params,
                              verbose=verbose)
        else:
            if verbose:
                print(f"  ==== skip fit ({_tag}) ====")

    # ---- Part 3: plot ----
    if parts[0] <= 3:
        fit_data = {}
        for _fitpa in fitpa_list:
            _tag = f"dt{_fitpa.dt_start}_{_fitpa.dt_end}"
            with np.load(os.path.join(
                    _fit_dir, _tag, f"fit_{_tag}.npz")) as _fit_file:
                fit_data[_tag] = {
                    _name: _fit_file[_name] for _name in _fit_file.files
                }

        for _fitpa in fitpa_list:
            _tag = f"dt{_fitpa.dt_start}_{_fitpa.dt_end}"
            result["saved"] += plot_para(fit_data[_tag],
                                         os.path.join(_fit_dir, _tag),
                                         _fitpa, params, verbose=verbose)
        result["saved"] += plot_para_cmp(fit_data, _fit_dir, params,
                                         fitpa_list, verbose=verbose)

        # bestfit: FH + c0 色带
        if bestfit_params:
            _bf = bestfit_params
            _bf_tag = f"dt{_bf['dt_start']}_{_bf['dt_end']}"
            _c0_data = {}
            _bf_path = os.path.join(
                _fit_dir, _bf_tag, f"fit_{_bf_tag}.npz")
            _bestfit_reason = "fit status is unavailable"
            try:
                with np.load(_bf_path) as _bf_fit:
                    _bf_c0 = np.asarray(_mapping_value(_bf_fit, "c0"))
                    if _bf_c0.ndim != 2:
                        _bestfit_reason = "c0 shape is invalid"
                    else:
                        _valid_z, _bestfit_reason = _valid_fit_z(
                            _bf_fit, ["c0"], _bf_c0.shape[1])
                        for _iz in params.z_list:
                            if _iz < _bf_c0.shape[1] and _valid_z[_iz]:
                                _mean = _bf_c0[:, _iz].mean()
                                _error = sem(_bf_c0[:, _iz],
                                             jackknife=False)
                                if np.isfinite(_mean) and np.isfinite(_error):
                                    _c0_data[_iz] = (_mean, _error)
            except (OSError, KeyError, TypeError, ValueError):
                _bestfit_reason = "bestfit NPZ state is missing or malformed"

            if not _c0_data:
                _log_plot_skip(
                    os.path.join(out_dir, "bestfit"),
                    _bestfit_reason,
                    verbose,
                )
            else:
                _bf_fh = np.load(os.path.join(
                    out_dir, "fh", f"FH_nex{_bf['nex']}.npy"))
                result["saved"] += plot_fh(
                    {_bf["nex"]: _bf_fh}, os.path.join(out_dir, "bestfit"),
                    params, c0_data=_c0_data,
                    band_t_range=(_bf["dt_start"], _bf["dt_end"]),
                    verbose=verbose)
    return result
