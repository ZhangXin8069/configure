"""
04_proton_energy 功能：质子有效能量提取 + 平台拟合 + eff_mass 图（独立实现）
============================================================================

功能对齐 refer/huangcl/04_proton_energy/code.py：

- Part 1 compute：读 2pt 切片 → 平移不变相对时间 → ti 平均 → 重采样 →
  0_corr2.npy（(Nsample, dt_max+1)）。
- Part 2 fit：模型 C(t) = c0·e^{−E0·t}·(1 + c1·e^{−dE·t})，
  lsqfit 逐样本拟合（p0，svdcut=1e-6）→ 1_fit_data.npz + 2_fit_report.txt。
- Part 3 plot：eff_mass.png —— meff(t) = log(C(t)/C(t+1))·unit 误差棒
  + E0 平台色带（unit = 0.197/a GeV，a 为格距 fm）。

统计/拟合/图表全部复用 pyqcd.analysis 既有模块。
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import numpy as np

from ._disconnected import (cov_mat, fit_status_from_samples,
                            resample, sem)
from ._fitter import (FitParams, covariance_effective_rank,
                      covariance_sample_rank, fit, fit_identifiability,
                      fit_report_lines, make_summary_table)


@dataclass
class EnergyParams:
    """04 参数。

    dir: 方向（'z' 默认；'x'/'y' 时按 dir_momentum 置换动量并读
         momsmear{Pz}{dir} 子目录——test6 三方向能量链整合项，
         消除驱动层自行置换的重复实现）。
    """

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
    a: float = 0.1053            # 格距 (fm)
    fm_to_GeV: float = 0.197
    dir: str = 'z'
    p0: dict = field(default_factory=lambda: {
        "c0": 0.6, "c1": 0.6, "E0": 1.5, "dE": 0.4})
    model_selection: str = "aicc"
    dt_start: int = 6
    dt_end: int = 12
    xlim: list = field(default_factory=lambda: [2.5, 19.5])
    ylim: list = field(default_factory=lambda: [0.5, 2.0])

    @property
    def Nconf(self):
        return len(self.conf_ids)

    @property
    def unit(self):
        """格点能 → GeV。"""
        return self.fm_to_GeV / self.a

    @property
    def mom_tag(self):
        """当前方向的动量标签 (Px,Py,Pz)（dir_momentum 置换）。"""
        from ._bare_matrix import dir_momentum
        return dir_momentum(self.Px, self.Py, self.Pz, self.dir)


def load_raw_corr(data_root, conf_id, params: EnergyParams) -> np.ndarray:
    """读取单组态 2pt 切片 (Nt, Nt)（方向感知：momsmear{Pz}{dir}）。"""
    Px, Py, Pz = params.mom_tag
    mom = f"Px{Px}Py{Py}Pz{Pz}"
    return np.load(os.path.join(
        data_root, params.conf_name, f"momsmear{params.Pz}{params.dir}",
        str(conf_id),
        f"twopt_slice_pp_{mom}_eginphase2_Cg5g4_nopol_ss_conf{conf_id}.npy"))


def compute_corr2(data_root, params: EnergyParams, jack: bool,
                  verbose=True) -> np.ndarray:
    """读 2pt → 相对时间 → ti 平均 → 重采样 → corr2 (Nsample, dt_max+1)。"""
    if verbose:
        print("==================== compute corr2 start ====================")

    _corr = np.zeros((params.Nconf, params.Nt, params.Nt), dtype=complex)
    for i, conf_id in enumerate(params.conf_ids):
        _corr[i] = load_raw_corr(data_root, conf_id, params)
    if verbose:
        print("load finish")
        print("2pt shape:", _corr.shape)

    _corr2_rel = np.zeros((params.Nconf, params.Nt, params.dt_max),
                          dtype=complex)
    for ti in range(params.Nt):
        corr2_shift = np.roll(_corr[:, :, ti], shift=-ti, axis=1)
        _corr2_rel[:, ti, :] = corr2_shift[:, :params.dt_max]

    _corr2_ave = _corr2_rel.mean(1)[:, :params.dt_max + 1]
    corr2 = resample(_corr2_ave, jack, params.Nsample).real

    if verbose:
        print("==================== compute corr2 end ====================")
    return corr2


def energy_model(x, p):
    """C(t) = c0·e^{−E0·t}·(1 + c1·e^{−dE·t})。"""
    dt = np.asarray(x, dtype=np.float64)
    return p["c0"] * np.exp(-p["E0"] * dt) * (1 + p["c1"] * np.exp(-p["dE"] * dt))


def energy_model_jacobian(x, p):
    """Closed-form real-parameter Jacobian of :func:`energy_model`."""
    dt = np.asarray(x, dtype=np.float64)
    ground = np.exp(-p["E0"] * dt)
    excited = np.exp(-p["dE"] * dt)
    corr = p["c0"] * ground * (1.0 + p["c1"] * excited)
    return {
        "c0": ground * (1.0 + p["c1"] * excited),
        "c1": p["c0"] * ground * excited,
        "E0": -dt * corr,
        "dE": -dt * p["c0"] * p["c1"] * ground * excited,
    }


def one_state_energy_model(x, p):
    """Single-state candidate ``C(t)=c0*exp(-E0*t)``."""
    dt = np.asarray(x, dtype=np.float64)
    return p["c0"] * np.exp(-p["E0"] * dt)


def one_state_energy_model_jacobian(x, p):
    """Closed-form Jacobian of :func:`one_state_energy_model`."""
    dt = np.asarray(x, dtype=np.float64)
    exponential = np.exp(-p["E0"] * dt)
    corr = p["c0"] * exponential
    return {"c0": exponential, "E0": -dt * corr}


def _aicc_from_reduced_chi2(reduced_chi2, dof, n_observations, n_params):
    """Return per-sample AICc without treating resample count as ``n``."""
    reduced_chi2 = np.asarray(reduced_chi2, dtype=np.float64)
    result = np.full(reduced_chi2.shape, np.nan, dtype=np.float64)
    denominator = int(n_observations) - int(n_params) - 1
    if denominator <= 0 or dof <= 0:
        return result
    finite = np.isfinite(reduced_chi2)
    result[finite] = (
        reduced_chi2[finite] * float(dof)
        + 2.0 * float(n_params)
        + 2.0 * float(n_params) * (float(n_params) + 1.0)
        / float(denominator)
    )
    return result


def _akaike_weights(aicc_one, aicc_two):
    """Return normalized per-sample Akaike weights for two candidates."""
    one = np.asarray(aicc_one, dtype=np.float64)
    two = np.asarray(aicc_two, dtype=np.float64)
    if one.shape != two.shape:
        raise ValueError("AICc candidate arrays must have the same shape")
    weight_one = np.full(one.shape, np.nan, dtype=np.float64)
    weight_two = np.full(two.shape, np.nan, dtype=np.float64)
    finite_one = np.isfinite(one)
    finite_two = np.isfinite(two)
    only_one = finite_one & ~finite_two
    only_two = finite_two & ~finite_one
    weight_one[only_one], weight_two[only_one] = 1.0, 0.0
    weight_one[only_two], weight_two[only_two] = 0.0, 1.0
    both = finite_one & finite_two
    if np.any(both):
        minimum = np.minimum(one[both], two[both])
        raw_one = np.exp(-0.5 * (one[both] - minimum))
        raw_two = np.exp(-0.5 * (two[both] - minimum))
        normalization = raw_one + raw_two
        weight_one[both] = raw_one / normalization
        weight_two[both] = raw_two / normalization
    return weight_one, weight_two


def _finite_median(values):
    values = np.asarray(values, dtype=np.float64)
    finite = values[np.isfinite(values)]
    return float(np.median(finite)) if finite.size else np.inf


def do_fit(corr2: np.ndarray, params: EnergyParams, out_dir: str, jack: bool,
           verbose=True) -> dict:
    """逐样本 lsqfit 拟合（p0，svdcut=1e-6）→ 1_fit_data.npz + 2_fit_report.txt。"""
    if verbose:
        print("==================== do_fit start ====================")

    corr2 = np.asarray(corr2)
    if corr2.ndim != 2:
        raise ValueError("corr2 必须为 (Nsample, dt) 二维数组")
    if corr2.shape[0] != params.Nsample:
        raise ValueError("corr2 的样本轴必须等于 params.Nsample")
    for name, value in (("dt_start", params.dt_start),
                        ("dt_end", params.dt_end)):
        if (isinstance(value, (bool, np.bool_))
                or not isinstance(value, (int, np.integer))):
            raise ValueError(f"{name} 必须是非布尔整数")
    if params.dt_start < 0 or params.dt_end < params.dt_start:
        raise ValueError("须满足 0 <= dt_start <= dt_end")
    if params.dt_end >= corr2.shape[1]:
        raise ValueError("dt_end 超出 corr2 的 dt 轴")
    x_coor = list(range(params.dt_start, params.dt_end + 1))
    Ndata = len(x_coor)
    param_names = list(params.p0.keys())

    fit_result = {name: np.full(params.Nsample, np.nan)
                  for name in param_names}
    fit_result["chi2"] = np.full(params.Nsample, np.nan)

    report_lines = fit_report_lines(
        f"Fit Report  : {params.conf_short}", {
            "dt range": f"[{params.dt_start}, {params.dt_end}]",
            "Nsample": params.Nsample,
            "jackknife": jack,
        })

    sub_sample = np.zeros((params.Nsample, Ndata))
    for i, dt in enumerate(x_coor):
        sub_sample[:, i] = corr2[:, dt]

    if params.model_selection not in ("aicc", "two_state"):
        raise ValueError("model_selection must be 'aicc' or 'two_state'")
    expected_params = {"c0", "c1", "E0", "dE"}
    if set(param_names) != expected_params:
        raise ValueError(
            "energy p0 must contain exactly c0, c1, E0, and dE")

    two_state_required_rank = len(param_names)
    two_state_fitpa = FitParams(
        p0=params.p0,
        dt_start=params.dt_start,
        dt_end=params.dt_end,
        svdcut=1.0e-6,
        jacobian=energy_model_jacobian,
    )
    one_state_fitpa = FitParams(
        p0={"c0": params.p0["c0"], "E0": params.p0["E0"]},
        dt_start=params.dt_start,
        dt_end=params.dt_end,
        svdcut=two_state_fitpa.svdcut,
        jacobian=one_state_energy_model_jacobian,
    )
    one_state_required_rank = len(one_state_fitpa.p0)
    selected_model = "unavailable"
    ground_state_status = "statistically_unidentifiable"
    excited_state_status = "statistically_unidentifiable"
    two_state_fit_status = "statistically_unidentifiable"
    one_state_fit_status = "statistically_unidentifiable"
    aicc_one_state = np.full(params.Nsample, np.nan)
    aicc_two_state = np.full(params.Nsample, np.nan)
    weight_one_state = np.full(params.Nsample, np.nan)
    weight_two_state = np.full(params.Nsample, np.nan)
    median_one = np.inf
    median_two = np.inf
    one_state_reason = "one-state fit was not attempted"
    two_state_reason = "two-state fit was not attempted"
    if jack and params.Nconf < 2:
        cov = np.zeros((Ndata, Ndata), dtype=np.float64)
        cond = np.inf
        effective_rank = 0
        sample_rank = 0
        fit_reason = (
            f"Nconf={params.Nconf} cannot support delete-one jackknife "
            "covariance")
        fit_status, fit_reason, _ = fit_status_from_samples(
            fit_result, None, failure_reason=fit_reason)
        one_state_reason = fit_reason
        two_state_reason = fit_reason
        _fit = None
    else:
        two_state_result, cov, cond, two_state_fit = fit(
            sub_sample, x_coor, energy_model, two_state_fitpa,
            jackknife=jack)
        effective_rank = covariance_effective_rank(
            cov, two_state_fitpa.svdcut)
        sample_rank = covariance_sample_rank(cov)
        two_gate_ok, two_gate_reason = fit_identifiability(
            Ndata, two_state_required_rank, effective_rank,
            sample_rank=sample_rank)
        two_state_fit_status, two_state_reason, _ = fit_status_from_samples(
            two_state_result, two_state_fit,
            failure_reason=None if two_gate_ok else two_gate_reason)

        one_state_result, one_cov, _, one_state_fit = fit(
            sub_sample, x_coor, one_state_energy_model,
            one_state_fitpa, jackknife=jack)
        if not np.allclose(one_cov, cov, rtol=0.0, atol=0.0):
            raise RuntimeError("one- and two-state fits must share covariance")
        one_gate_ok, one_gate_reason = fit_identifiability(
            Ndata, one_state_required_rank, effective_rank,
            sample_rank=sample_rank)
        one_state_fit_status, one_state_reason, _ = fit_status_from_samples(
            one_state_result, one_state_fit,
            failure_reason=None if one_gate_ok else one_gate_reason)

        two_dof = effective_rank - two_state_required_rank
        one_dof = effective_rank - one_state_required_rank
        aicc_two_state = _aicc_from_reduced_chi2(
            two_state_result["chi2"], two_dof, Ndata,
            two_state_required_rank)
        aicc_one_state = _aicc_from_reduced_chi2(
            one_state_result["chi2"], one_dof, Ndata,
            one_state_required_rank)
        weight_one_state, weight_two_state = _akaike_weights(
            aicc_one_state, aicc_two_state)
        median_one = _finite_median(aicc_one_state)
        median_two = _finite_median(aicc_two_state)

        if params.model_selection == "two_state":
            selected_model = "two_state" if np.isfinite(median_two) else "unavailable"
        elif median_one < median_two:
            selected_model = "one_state"
        elif median_two < median_one:
            selected_model = "two_state"
        elif np.isfinite(median_one):
            selected_model = "ambiguous"

        if selected_model == "one_state":
            fit_result["c0"][:] = one_state_result["c0"]
            fit_result["E0"][:] = one_state_result["E0"]
            fit_result["chi2"][:] = one_state_result["chi2"]
            fit_status = one_state_fit_status
            fit_reason = (
                "AICc selected one_state; excited-state amplitude and gap "
                "are not supported by this window"
            )
            ground_state_status = one_state_fit_status
            excited_state_status = "practically_unidentifiable"
            _fit = one_state_fit
            if two_state_fit_status in (
                    "identifiable", "prior_constrained",
                    "practically_unidentifiable"):
                two_state_fit_status = "practically_unidentifiable"
                two_state_reason = fit_reason
        elif selected_model == "two_state":
            for name in param_names + ["chi2"]:
                fit_result[name][:] = two_state_result[name]
            fit_status = two_state_fit_status
            fit_reason = two_state_reason
            ground_state_status = two_state_fit_status
            excited_state_status = two_state_fit_status
            _fit = two_state_fit
        elif selected_model == "ambiguous":
            fit_status = "practically_unidentifiable"
            fit_reason = "one- and two-state AICc medians are exactly tied"
            ground_state_status = one_state_fit_status
            excited_state_status = "practically_unidentifiable"
            _fit = None
        else:
            fit_status = "statistically_unidentifiable"
            fit_reason = (
                "neither one- nor two-state candidate has finite AICc; "
                f"one_state={one_state_reason}; two_state={two_state_reason}"
            )
            _fit = None

    if verbose:
        print(f"fit status = {fit_status} ({fit_reason})")
        if fit_status in ("identifiable", "prior_constrained"):
            for name in param_names:
                if np.isfinite(fit_result[name]).all():
                    print(f"{name} = {fit_result[name].mean():.3g} "
                          f"+- {sem(fit_result[name], jack):.3g}")
                else:
                    print(f"{name} = unavailable ({excited_state_status})")
            print(f"chi2 = {fit_result['chi2'].mean():.3g}")
        print(f"two_state_fit_status = {two_state_fit_status} "
              f"({two_state_reason})")
        print(f"fit time: ...")

    report_lines.append("-" * 72)
    report_lines.append(f"condition number = {cond:.3g}")
    report_lines.append(f"fit status = {fit_status}")
    report_lines.append(f"fit reason = {fit_reason}")
    report_lines.append(f"AICc selected model = {selected_model}")
    report_lines.append(
        f"AICc median one-state = {_finite_median(aicc_one_state):.6g}")
    report_lines.append(
        f"AICc median two-state = {_finite_median(aicc_two_state):.6g}")
    report_lines.append(f"ground-state status = {ground_state_status}")
    report_lines.append(f"excited-state status = {excited_state_status}")
    report_lines.append(f"two-state fit status = {two_state_fit_status}")
    report_lines.append(f"two-state fit reason = {two_state_reason}")
    report_lines.append(f"effective covariance rank = {effective_rank}")
    report_lines.append(f"sample covariance rank = {sample_rank}")
    selected_required_rank = (
        one_state_required_rank if selected_model == "one_state"
        else two_state_required_rank)
    report_lines.append(f"required parameter rank = {selected_required_rank}")
    report_lines.append(
        f"candidate parameter ranks = one:{one_state_required_rank}, "
        f"two:{two_state_required_rank}")
    if fit_status not in ("identifiable", "prior_constrained"):
        report_lines.append(f"fit skipped: {fit_reason}")
    report_lines.append("")
    if _fit is not None:
        report_lines.append(_fit.format(maxline=True))
    report_lines.append("")

    report_lines.append("=" * 72)
    report_lines.append("  Summary Table")
    report_lines.append("=" * 72)
    row = []
    if fit_status in ("identifiable", "prior_constrained"):
        for name in param_names:
            if np.isfinite(fit_result[name]).all():
                row.append(f"{fit_result[name].mean():.3f}"
                           f"({sem(fit_result[name], jack) * 1e3:.0f})")
            else:
                row.append("N/A")
        row.append(f"{fit_result['chi2'].mean():.2g}")
    else:
        row.extend(["N/A"] * (len(param_names) + 1))
    report_lines.append(make_summary_table(param_names + ["chi2/dof"], [row]))
    report_lines.append("")

    parameter_status_by_name = {
        "c0": ground_state_status,
        "c1": excited_state_status,
        "E0": ground_state_status,
        "dE": excited_state_status,
    }
    parameter_reason_by_name = {
        "c0": fit_reason,
        "E0": fit_reason,
        "c1": (
            "selected one-state model has no resolved excited amplitude"
            if selected_model == "one_state" else fit_reason
        ),
        "dE": (
            "selected one-state model has no resolved excited-state gap"
            if selected_model == "one_state" else fit_reason
        ),
    }
    fit_result.update({
        "status_schema_version": np.asarray(2, dtype=np.int64),
        "fit_status": fit_status,
        "fit_reason": fit_reason,
        "selected_model": selected_model,
        "one_state_fit_status": one_state_fit_status,
        "two_state_fit_status": two_state_fit_status,
        "one_state_fit_reason": one_state_reason if not (
            jack and params.Nconf < 2) else fit_reason,
        "two_state_fit_reason": two_state_reason if not (
            jack and params.Nconf < 2) else fit_reason,
        "ground_state_status": ground_state_status,
        "excited_state_status": excited_state_status,
        "parameter_names": np.asarray(param_names),
        "parameter_status": np.asarray([
            parameter_status_by_name[name] for name in param_names
        ]),
        "parameter_reason": np.asarray([
            parameter_reason_by_name[name] for name in param_names
        ]),
        "aicc_n_observations": np.asarray(Ndata, dtype=np.int64),
        "aicc_one_state": np.asarray(median_one, dtype=np.float64),
        "aicc_two_state": np.asarray(median_two, dtype=np.float64),
        "aicc_one_state_samples": aicc_one_state,
        "aicc_two_state_samples": aicc_two_state,
        "akaike_weight_one_state": weight_one_state,
        "akaike_weight_two_state": weight_two_state,
        "condition_number": np.asarray(cond, dtype=np.float64),
        "effective_rank": np.asarray(effective_rank, dtype=np.int64),
        "sample_rank": np.asarray(sample_rank, dtype=np.int64),
        "required_rank": np.asarray(selected_required_rank, dtype=np.int64),
        "one_state_required_rank": np.asarray(
            one_state_required_rank, dtype=np.int64),
        "two_state_required_rank": np.asarray(
            two_state_required_rank, dtype=np.int64),
    })
    with open(os.path.join(out_dir, "2_fit_report.txt"), "w") as f:
        f.write("\n".join(report_lines))
    np.savez(
        os.path.join(out_dir, "1_fit_data.npz"),
        **fit_result,
    )
    if verbose:
        print(f"report saved to {out_dir}/2_fit_report.txt")
        print(f"fit result saved to {out_dir}/1_fit_data.npz")
        print("==================== do_fit end ====================")
    return fit_result


def _fit_status_text(fit_result):
    """读取中心拟合状态；旧 numeric-only 结果不推断为可辨识。"""
    value = fit_result.get("fit_status")
    if value is None:
        return "unavailable"
    value = np.asarray(value).reshape(-1)
    if value.size != 1:
        return "unavailable"
    return str(value[0])


def _fit_reason_text(fit_result):
    """读取中心拟合原因，兼容旧 numeric-only 产物。"""
    value = fit_result.get("fit_reason")
    if value is None:
        return "central fit status is unavailable"
    value = np.asarray(value).reshape(-1)
    if value.size != 1:
        return "central fit status is unavailable"
    return str(value[0])


def plot_eff_mass(corr2: np.ndarray, fit_result: dict, params: EnergyParams,
                  out_dir: str, jack: bool, verbose=True) -> str:
    """eff_mass.png：meff(t)·unit 误差棒 + E0 平台色带。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ._plots import DEFAULT_PLOT_COLORS

    if verbose:
        print("==================== plot_corr2 start ====================")
    time0 = time.perf_counter()

    para_E0 = fit_result["E0"] * params.unit
    chi2 = fit_result["chi2"]
    fit_status = _fit_status_text(fit_result)

    mass = np.log(corr2 / np.roll(corr2, shift=-1, axis=1)) * params.unit
    mass_mean = mass.mean(0)
    mass_err = sem(mass, jack)

    fit_valid = (fit_status in ("identifiable", "prior_constrained")
                 and np.isfinite(para_E0).all()
                 and np.isfinite(chi2).all())
    if fit_valid:
        E0_mean = para_E0.mean(0)
        E0_err = sem(para_E0, jack)
        chi2_mean = chi2.mean(0)
    else:
        E0_mean = E0_err = chi2_mean = np.nan

    band_down = E0_mean - E0_err
    band_up = E0_mean + E0_err

    fig, ax = plt.subplots(figsize=(6.4, 4.8), dpi=150)
    color = DEFAULT_PLOT_COLORS[0]
    x_vals = np.arange(params.dt_max)
    ax.errorbar(x_vals, mass_mean, yerr=mass_err,
                fmt="x", color=color, ecolor=color, capsize=0,
                markersize=7, markeredgewidth=1.8, linewidth=1.2, zorder=3)

    x_band = np.array([params.dt_start, params.dt_end])
    Px, Py, Pz = params.mom_tag
    if fit_valid:
        ax.fill_between(x_band, [band_down, band_down], [band_up, band_up],
                        color="gray", alpha=0.35, linewidth=0, zorder=1,
                        label="Fit E0")
        E0_str = f"{E0_mean:.3f}({E0_err * 1e3:.0f})"
        title = (f"P=({Px},{Py},{Pz}) [{params.dir}], E0={E0_str}, "
                 f"chi2={chi2_mean:.2f} [{fit_status}]")
    else:
        title = (f"P=({Px},{Py},{Pz}) [{params.dir}], "
                 f"fit={fit_status}")
        ax.text(0.5, 0.08, f"fit unavailable: {_fit_reason_text(fit_result)}",
                transform=ax.transAxes, ha="center", va="bottom",
                fontsize=9, color="darkred")
    ax.set_title(title, fontsize=12)
    ax.set_xlim(params.xlim[0], params.xlim[1])
    ax.set_ylim(params.ylim[0], params.ylim[1])
    ax.set_box_aspect(3 / 4)
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(handles, labels, loc="upper right", fontsize=8)

    fig.supxlabel("t/a", fontsize=16)
    fig.supylabel("eff mass (GeV)", fontsize=16)

    plt.tight_layout()
    save_path = os.path.join(out_dir, "eff_mass.png")
    fig.savefig(save_path, bbox_inches="tight")
    plt.close(fig)

    if verbose:
        print(f"plot saved to {save_path}")
        print(f"plot done, time: {time.perf_counter() - time0:.2f}s")
        print("==================== plot_corr2 end ====================")
    return save_path


def run_energy(data_root, out_root, params: EnergyParams, jack: bool = True,
               parts=(1, 3), verbose=True) -> dict:
    """04 全链：compute corr2 → fit → eff_mass 图（方向感知）。

    out_dir：dir='z' 时保持 `_Pz{Pz}`（向后兼容）；非 z 方向追加
    `_{dir}` 后缀以区分三方向产物。
    """
    suffix = f"_{params.dir}" if params.dir != 'z' else ""
    out_dir = os.path.join(out_root, params.conf_short,
                           f"_Pz{params.Pz}{suffix}")
    os.makedirs(out_dir, exist_ok=True)
    result = {}

    if parts[0] <= 1:
        time0 = time.perf_counter()
        corr2 = compute_corr2(data_root, params, jack, verbose=verbose)
        np.save(os.path.join(out_dir, "0_corr2.npy"), corr2)
        if verbose:
            print(f"corr2 saved to {out_dir}/0_corr2.npy")
            from ._plots import get_peak_memory_gb
            print(f"Peak Memory: {get_peak_memory_gb():.3f} GB")
            print(f"spend time: {time.perf_counter() - time0:.2f}s\n")
    else:
        corr2 = np.load(os.path.join(out_dir, "0_corr2.npy"))
        if verbose:
            print("===== skip compute corr2, loading corr2 from file =====")
            print(f"corr2 loaded, shape: {corr2.shape}")
    result["corr2"] = corr2

    if parts[0] <= 2:
        time0 = time.perf_counter()
        fit_result = do_fit(corr2, params, out_dir, jack, verbose=verbose)
        if verbose:
            print(f"spend time: {time.perf_counter() - time0:.2f}s\n")
    else:
        fit_result = dict(np.load(os.path.join(out_dir, "1_fit_data.npz")))
    result["fit"] = fit_result

    if parts[0] <= 3:
        result["saved"] = [plot_eff_mass(corr2, fit_result, params, out_dir,
                                         jack, verbose=verbose)]
    return result
