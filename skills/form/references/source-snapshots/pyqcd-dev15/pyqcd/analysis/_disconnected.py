"""
不相连胶子 ratio 分析（code_1.py 算法移植，自包含）
=====================================================

移植冻结蒸馏基线 analyze.py 的 code_1.py 风格分析：

    C3(dt, dtau, z) = C2(dt) · OPE(dtau, z)         （不相连因子化）
    C3_disc = C3 − C2·⟨OPE⟩                         （真空扣除）
    R(dt, dtau, z) = ⟨C3_disc / C2⟩_ti
    逐 z 相关拟合：R = c0 + c1·e^{−dE·dtau} + c1·e^{−dE·(dt−dtau)}
    （lsqfit.nonlinear_fit，svdcut=1e-6，jackknife 协方差）

输出：ratio_{ch}.npy、(c0, c1, dE, chi2) 参数、拟合报告。
"""
from __future__ import annotations

import os
import operator
import time

import numpy as np


def sem(data, jackknife=True):
    """样本轴（axis 0）均值的标准误。"""
    data = _as_resample_array(data)
    if data.ndim == 0:
        raise ValueError("sem expects a sample axis")
    is_torch = type(data).__module__.split(".", 1)[0] == "torch"
    if is_torch:
        import torch
        dtype = data.dtype
        if not (dtype.is_floating_point or dtype.is_complex):
            data = data.to(dtype=torch.float64)
    n_sample = data.shape[0]
    if n_sample == 0:
        raise ValueError("sem requires at least one sample")
    if n_sample < 2:
        error = (data.std(0, correction=0) if is_torch
                 else data.std(0))
        output = _empty_resample_like(error, error.shape)
        output[...] = np.nan
        return output
    error = (data.std(0, correction=0) if is_torch
             else data.std(0))
    if jackknife:
        error = error * np.sqrt(n_sample - 1)
    return error


def _normalize_resample_axis(axis, ndim):
    """Return a validated non-negative sample axis."""
    if isinstance(axis, (bool, np.bool_)):
        raise TypeError("axis must be an integer, not bool")
    try:
        axis = operator.index(axis)
    except TypeError as error:
        raise TypeError("axis must be an integer") from error
    if axis < -ndim or axis >= ndim:
        raise ValueError(
            f"axis {axis} is out of bounds for an array of dimension {ndim}")
    return axis % ndim


def _positive_resample_integer(value, name):
    """Validate a positive integer option without accepting bool values."""
    if isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be a positive integer")
    try:
        value = operator.index(value)
    except TypeError as error:
        raise TypeError(f"{name} must be a positive integer") from error
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


_DEFAULT_RESAMPLE_SEED = object()


def _as_resample_array(data):
    """Keep array backends while accepting ordinary array-like input."""
    if (hasattr(data, "ndim") and hasattr(data, "shape")
            and hasattr(data, "mean")):
        return data
    return np.asarray(data)


def _promote_bool_observable(data):
    """Promote Bernoulli observables before backend resampling arithmetic."""
    if type(data).__module__.split(".", 1)[0] == "torch":
        import torch
        if data.dtype == torch.bool:
            return data.to(dtype=torch.float64)
        return data
    if isinstance(data, np.ndarray) and data.dtype == np.bool_:
        return data.astype(np.float64, copy=False)
    return data


def _resample_mean(data, axis):
    """Compute a mean while giving Torch integer inputs a NaN-capable dtype."""
    if type(data).__module__.split(".", 1)[0] == "torch":
        import torch
        dtype = data.dtype
        if not (dtype.is_floating_point or dtype.is_complex):
            return data.mean(axis, dtype=torch.float64)
    return data.mean(axis)


def _move_resample_axis_to_front(data, axis):
    """Move one sample axis without forcing a non-NumPy backend to host."""
    if axis == 0:
        return data
    order = (axis,) + tuple(index for index in range(data.ndim)
                            if index != axis)
    movedim = getattr(data, "movedim", None)
    if movedim is not None:
        return movedim(axis, 0)
    return data.transpose(order)


def _empty_resample_like(reference, shape):
    """Allocate an output on the backend and device of ``reference``."""
    if isinstance(reference, (np.ndarray, np.generic)):
        return np.empty(shape, dtype=reference.dtype)
    new_empty = getattr(reference, "new_empty", None)
    if new_empty is not None:
        return new_empty(shape)
    try:
        return type(reference)(shape, dtype=reference.dtype)
    except (TypeError, ValueError) as error:
        raise TypeError(
            "resample cannot allocate an output for this array backend"
        ) from error


def _resample_indices_for_array(data, indices):
    """Place Torch advanced-index arrays on the data device."""
    if type(data).__module__.split(".", 1)[0] == "torch":
        import torch
        return data.new_tensor(indices, dtype=torch.long)
    return indices


def resample(corr, jackknife=True, Nsample=None,
             seed=_DEFAULT_RESAMPLE_SEED, axis=0,
             chunk_size=None, rng=None):
    """Delete-one jackknife or bootstrap samples.

    ``axis`` identifies the configuration axis.  Bootstrap output always has
    its resample axis first; non-sample axes retain their original order.
    Bootstrap index generation can be bounded with ``chunk_size``.  A supplied
    ``numpy.random.Generator`` is consumed directly and is never reseeded.
    """
    seed_is_explicit = seed is not _DEFAULT_RESAMPLE_SEED
    if not seed_is_explicit:
        seed = 0

    corr = _promote_bool_observable(_as_resample_array(corr))
    if corr.ndim == 0:
        raise ValueError("resampling expects an array with a sample axis")
    axis = _normalize_resample_axis(axis, corr.ndim)

    if rng is not None and not isinstance(rng, np.random.Generator):
        raise TypeError("rng must be a numpy.random.Generator")
    if chunk_size is not None:
        chunk_size = _positive_resample_integer(chunk_size, "chunk_size")

    sample_first = _move_resample_axis_to_front(corr, axis)
    n_conf = sample_first.shape[0]
    if n_conf == 0:
        raise ValueError("resampling requires at least one configuration")

    if jackknife:
        if chunk_size is not None:
            raise ValueError("chunk_size is only valid for bootstrap")
        if rng is not None:
            raise ValueError("rng is only valid for bootstrap")
        if n_conf < 2:
            mean = _resample_mean(sample_first, 0)
            output = _empty_resample_like(mean, sample_first.shape)
            output[...] = np.nan
            return output
        return (n_conf * _resample_mean(sample_first, 0) - sample_first) / (
            n_conf - 1)

    if Nsample is not None:
        Nsample = _positive_resample_integer(Nsample, "Nsample")
    if Nsample is None:
        raise ValueError("bootstrap resampling requires Nsample")
    if rng is not None and seed_is_explicit:
        raise ValueError("seed cannot be combined with an explicit rng")
    if rng is None:
        rng = np.random.default_rng(seed=seed)
    if chunk_size is None:
        chunk_size = Nsample

    output = None
    for start in range(0, Nsample, chunk_size):
        stop = min(start + chunk_size, Nsample)
        indices = rng.integers(
            0, n_conf, size=(stop - start, n_conf))
        indices = _resample_indices_for_array(sample_first, indices)
        batch = _resample_mean(sample_first[indices], 1)
        if output is None:
            output = _empty_resample_like(
                batch, (Nsample,) + tuple(batch.shape[1:]))
        output[start:stop] = batch
        del indices
        del batch
    return output


def _repair_covariance_roundoff(cov):
    """Validate covariance on correlation scale and symmetrize roundoff.

    Roundoff-sized negative eigenvalues are accepted as a dense
    representation artifact but are not lifted here.  Statistical SVD
    regulation belongs to the fit layer; changing the numerical null space at
    covariance construction time would destroy exact covariance kernels.
    """
    matrix = np.asarray(cov)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("cov must be a square matrix")
    if not np.isfinite(matrix).all():
        raise ValueError("cov must contain only finite values")
    matrix = np.asarray(matrix, dtype=np.result_type(matrix.dtype, np.float64))
    original = matrix
    matrix_scale = float(np.max(np.abs(matrix), initial=0.0))
    hermitian_tolerance = (
        matrix_scale * max(matrix.shape[0], 1) * np.finfo(np.float64).eps
    )
    if np.max(
            np.abs(matrix - matrix.conj().T), initial=0.0
    ) > hermitian_tolerance:
        raise ValueError("cov must be Hermitian")
    matrix = (matrix + matrix.conj().T) * 0.5
    diagonal = np.real_if_close(np.diag(matrix))
    if np.iscomplexobj(diagonal):
        raise ValueError("cov diagonal must be real")
    diagonal = np.asarray(diagonal, dtype=np.float64)
    if np.any(diagonal < 0.0):
        raise ValueError("cov diagonal must be non-negative")

    active = diagonal > 0.0
    inactive = ~active
    if np.any(inactive) and (
            np.any(original[inactive, :] != 0.0)
            or np.any(original[:, inactive] != 0.0)):
        raise ValueError("cov must be positive semidefinite")
    if not np.any(active):
        return np.real_if_close(matrix)

    std = np.sqrt(diagonal[active])
    corr = matrix[np.ix_(active, active)] / std[:, None] / std[None, :]
    corr = (corr + corr.conj().T) * 0.5
    eigval = np.linalg.eigvalsh(corr)
    largest = max(float(eigval[-1]), 0.0)
    tolerance = largest * corr.shape[0] * np.finfo(np.float64).eps
    if eigval[0] < -tolerance:
        raise ValueError("cov must be positive semidefinite")
    return np.real_if_close(matrix)


def cov_mat(arr, jackknife=True):
    """Jackknife 协方差（均值）与特征值条件数。"""
    arr = np.asarray(arr)
    if arr.ndim != 2:
        raise ValueError("cov_mat expects a two-dimensional sample matrix")
    if arr.shape[1] == 0:
        raise ValueError("cov_mat requires at least one feature column")
    n = arr.shape[0]
    if n < 2:
        dtype = np.result_type(arr.dtype, np.float64)
        return np.zeros((arr.shape[1], arr.shape[1]), dtype=dtype), np.inf
    diff = arr - arr.mean(0)
    if jackknife:
        cov = np.matmul(diff.T, diff.conj()) / n * (n - 1)
    else:
        cov = np.matmul(diff.T, diff.conj()) / n
    cov = _repair_covariance_roundoff(cov)
    eig = np.linalg.eigvalsh(cov)
    rank_tolerance = max(float(eig[-1]), 0.0) * eig.size * np.finfo(np.float64).eps
    cond = eig[-1] / eig[0] if eig[0] > rank_tolerance else np.inf
    return cov, cond


def fit_status_from_samples(fit_result, last_fit=None, has_prior=False,
                            failure_reason=None):
    """Classify a central-fit result from its complete sample finite mask.

    Product layers must not infer identifiability from a finite-looking point
    estimate alone.  ``fit`` annotates the last successful solver result with
    ``pyqcd_fit_status``; this helper combines that annotation with the finite
    mask of every parameter and ``chi2`` sample.  The returned mask is useful
    to callers that need to keep the original sample axis while suppressing
    invalid summaries and plot bands.

    Returns
    -------
    status, reason, finite_mask
        ``status`` is one of ``identifiable``, ``prior_constrained``,
        ``practically_unidentifiable``, ``partially_identifiable`` or
        ``statistically_unidentifiable``.
    """
    if not fit_result:
        raise ValueError("fit_result must contain parameter and chi2 arrays")

    arrays = []
    n_sample = None
    for name, values in fit_result.items():
        array = np.asarray(values)
        if array.ndim != 1:
            raise ValueError(f"fit result {name} must be a one-dimensional array")
        if n_sample is None:
            n_sample = array.shape[0]
        elif array.shape[0] != n_sample:
            raise ValueError("fit result arrays must share the sample axis")
        arrays.append(array)

    if n_sample == 0:
        raise ValueError("fit result must contain at least one sample")

    finite_mask = np.ones(n_sample, dtype=bool)
    for array in arrays:
        try:
            finite_mask &= np.isfinite(array)
        except TypeError as error:
            raise ValueError("fit result arrays must be numeric") from error

    n_finite = int(np.count_nonzero(finite_mask))
    last_status = getattr(last_fit, "pyqcd_fit_status", None)
    annotated_reason = getattr(last_fit, "pyqcd_fit_reason", None)

    def _explicit_reason(default):
        # An explicit practical-identifiability annotation is more specific
        # than a generic covariance gate reason; retain it verbatim.
        for candidate in (annotated_reason, failure_reason):
            if candidate is not None and str(candidate):
                return str(candidate)
        return default

    if n_finite == 0:
        status = "statistically_unidentifiable"
        reason = failure_reason or (
            "all fit samples failed: model Jacobian/covariance did not "
            "establish identifiability")
        if "model Jacobian" not in reason and "covariance" not in reason:
            reason += "; model Jacobian/covariance did not establish identifiability"
        return status, reason, finite_mask

    if n_finite < n_sample:
        return (
            "partially_identifiable",
            f"{n_finite}/{n_sample} fit samples have finite parameters and chi2; "
            "remaining samples failed the model Jacobian/covariance status gate",
            finite_mask,
        )

    if last_status == "practically_unidentifiable":
        return (
            "practically_unidentifiable",
            _explicit_reason(
                "central fit marked practically_unidentifiable; data "
                "identifiability is not established"),
            finite_mask,
        )

    if has_prior or last_status == "prior_constrained":
        return (
            "prior_constrained",
            "prior_constrained: data identifiability is not established",
            finite_mask,
        )

    if last_status == "identifiable":
        return "identifiable", "identifiable", finite_mask

    return (
        "statistically_unidentifiable",
        failure_reason or (
            "finite fit samples lack central pyqcd_fit_status=identifiable; "
            "model Jacobian/covariance identifiability is unproven"),
        finite_mask,
    )


def aggregate_fit_statuses(statuses, reasons=()):
    """Aggregate independent product channels without upgrading evidence."""
    statuses = [str(status) for status in statuses]
    if not statuses:
        raise ValueError("at least one fit status is required")
    if all(status == "identifiable" for status in statuses):
        status = "identifiable"
    elif all(status == "prior_constrained" for status in statuses):
        status = "prior_constrained"
    elif all(status == "practically_unidentifiable" for status in statuses):
        status = "practically_unidentifiable"
    elif all(status == "statistically_unidentifiable" for status in statuses):
        status = "statistically_unidentifiable"
    else:
        status = "partially_identifiable"
    unique_reasons = list(dict.fromkeys(str(reason) for reason in reasons
                                        if str(reason)))
    if status == "identifiable":
        reason = "identifiable"
    elif status == "prior_constrained":
        reason = "prior_constrained: data identifiability is not established"
    elif status == "practically_unidentifiable":
        reason = "; ".join(unique_reasons) or (
            "practical identifiability was not established")
    elif status == "statistically_unidentifiable":
        reason = "; ".join(unique_reasons) or (
            "all channels failed: model Jacobian/covariance did not "
            "establish identifiability")
    else:
        reason = "; ".join(unique_reasons) or (
            "some channels passed and some failed the model "
            "Jacobian/covariance status gate")
    return status, reason


def model_ratio(x, p):
    """R(dt, dtau) = c0 + c1·e^{−dE·dtau} + c1·e^{−dE·(dt−dtau)}。"""
    dt = np.array([_x[0] for _x in x])
    dtau = np.array([_x[1] for _x in x])
    return (np.ones(len(x)) * p["c0"]
            + p["c1"] * np.exp(-p["dE"] * dtau)
            + p["c1"] * np.exp(-p["dE"] * (dt - dtau)))


def model_ratio_jacobian(x, p):
    """Closed-form real-parameter Jacobian of :func:`model_ratio`."""
    dt = np.asarray([point[0] for point in x], dtype=np.float64)
    dtau = np.asarray([point[1] for point in x], dtype=np.float64)
    left = np.exp(-p["dE"] * dtau)
    right_dt = dt - dtau
    right = np.exp(-p["dE"] * right_dt)
    return {
        "c0": np.ones(dt.shape, dtype=np.float64),
        "c1": left + right,
        "dE": -p["c1"] * (dtau * left + right_dt * right),
    }


def run_disconnected_ratio(corr_2pt_all, ope_all, conf_ids, run_dir, logger=print,
                           NT=72, NX=24, dt_max=20, dt_start=7, dt_end=10,
                           cut=6, p0=None, target_momentum='P2'):
    """不相连胶子 ratio + 逐 z 拟合（code_1.py 算法）。

    Args:
        corr_2pt_all: {conf_id: {'corr_pp_P2': (Nt,), 'corr_pion_P2': (Nt,), ...}}
        ope_all:      {conf_id: {'combined': (Nz, Nt)}}
        conf_ids:     组态列表
        run_dir:      输出目录（analysis/disconnected/）
        dt_max/dt_start/dt_end/cut: 拟合窗参数
        p0:           拟合初值（默认 {'c0':0.6,'c1':-2,'dE':1}）
        target_momentum: 'P2'
    Returns:
        ch_results: {hadron: {'ratio': ..., 'c0': ..., 'c1': ..., 'dE': ..., 'chi2': ...}}
    """
    from ._fitter import (FitParams, covariance_effective_rank,
                          covariance_sample_rank, fit, fit_identifiability)

    if p0 is None:
        p0 = {"c0": 0.6, "c1": -2, "dE": 1}

    Nconf = len(conf_ids)
    Nsample = Nconf
    jack = True
    out_dir = os.path.join(run_dir, 'analysis', 'disconnected')
    os.makedirs(out_dir, exist_ok=True)

    channels = [('proton', 'corr_pp', 'proton'), ('pion', 'corr_pion', 'pion')]
    ch_results = {}
    channel_reports = {}

    for ch_key, k2, had_name in channels:
        logger(f"\n  Channel: {had_name} at Pz=2")

        # 平移不变 2pt：C(t_sink, t_src) = C((t_sink − t_src) mod Nt)
        key2 = f'{k2}_P{target_momentum[-1]}'
        _corr = np.stack([np.real(corr_2pt_all[cid][key2]) for cid in conf_ids])
        full = np.zeros((Nconf, NT, NT), dtype=np.float64)
        for ti in range(NT):
            full[:, :, ti] = np.roll(_corr, -ti, axis=1)

        # OPE combined：(Nconf, Nz, Nt) → (Nconf, tau, z)
        _ope = np.stack([np.real(ope_all[cid]['combined']) for cid in conf_ids])
        _ope = _ope.transpose(0, 2, 1)

        # 相对时间构造
        _corr2_rel = np.zeros((Nconf, NT, dt_max), dtype=np.float64)
        _ope_rel = np.zeros((Nconf, NT, dt_max, NX), dtype=np.float64)
        for ti in range(NT):
            corr2_shift = np.roll(full[:, :, ti], -ti, axis=1)
            _corr2_rel[:, ti, :] = corr2_shift[:, :dt_max]
            ope_shift = np.roll(_ope, -ti, axis=1)
            _ope_rel[:, ti, :, :] = ope_shift[:, :dt_max, :]

        # 不相连 3pt = C2 × OPE（因子化）
        _corr3 = np.zeros((Nconf, NT, dt_max, dt_max, NX), dtype=np.float64)
        for _dt in range(dt_max):
            for _dtau in range(_dt + 1):
                _corr3[:, :, _dt, _dtau, :] = (
                    _ope_rel[:, :, _dtau, :] * _corr2_rel[:, :, _dt][:, :, None])

        corr2 = resample(_corr2_rel, jack, Nsample)
        ope = resample(_ope_rel, jack, Nsample)
        corr3 = resample(_corr3, jack, Nsample)

        # 真空扣除 + ratio
        corr3_disc = corr3 - corr2[:, :, :, None, None] * ope[:, :, None, :, :]
        eps = 1e-30
        ratio = np.mean(corr3_disc / (corr2[:, :, :, None, None] + eps), axis=1)
        ratio = ratio.real   # (Nsample, dt_max, dt_max, Nz)
        np.save(os.path.join(out_dir, f'ratio_{had_name}_P{target_momentum[-1]}.npy'),
                ratio)

        # 逐 z 相关拟合
        front_remove = cut // 2
        back_remove = cut - front_remove
        x_coor = [(dt, dtau)
                  for dt in range(dt_start, dt_end + 1)
                  for dtau in range(front_remove, dt - back_remove + 1)]
        Ndata = len(x_coor)

        para_c0 = np.full((Nsample, NX), np.nan)
        para_c1 = np.full((Nsample, NX), np.nan)
        para_dE = np.full((Nsample, NX), np.nan)
        chi2 = np.full((Nsample, NX), np.nan)
        fit_status_by_z = ["statistically_unidentifiable"] * NX
        # Serialize reasons only after all z points are classified; this
        # avoids truncating future practical-identifiability explanations.
        fit_reason_by_z = [""] * NX
        effective_rank_by_z = np.zeros(NX, dtype=np.int64)
        sample_rank_by_z = np.zeros(NX, dtype=np.int64)
        required_rank = len(p0)
        fitpa = FitParams(
            p0=dict(p0), dt_start=dt_start, dt_end=dt_end,
            svdcut=1.0e-6, jacobian=model_ratio_jacobian)

        report_lines = [
            "=" * 70,
            f"  Fit Report: {had_name}, Pz={target_momentum[-1]}, Nconf={Nconf}",
            "=" * 70,
            f"  t_sep range : [{dt_start}, {dt_end}]",
            f"  cut         : {cut}",
            f"  Nsample     : {Nsample}",
            f"  jackknife   : {jack}",
            "=" * 70, "",
        ]

        for _z in range(NX):
            sub_sample = np.zeros((Nsample, Ndata))
            for i, (dt, dtau) in enumerate(x_coor):
                sub_sample[:, i] = ratio[:, dt, dtau, _z]
            _fit_result = {
                name: np.full(Nsample, np.nan)
                for name in list(p0) + ["chi2"]
            }
            if Nconf < 2:
                cov = np.zeros((Ndata, Ndata), dtype=np.float64)
                cond = np.inf
                effective_rank = 0
                sample_rank = 0
                _last_fit = None
                gate_reason = (
                    f"Nconf={Nconf} cannot support delete-one jackknife "
                    "covariance")
                fit_status, fit_reason, _ = fit_status_from_samples(
                    _fit_result, _last_fit, failure_reason=gate_reason)
            else:
                _fit_result, cov, cond, _last_fit = fit(
                    sub_sample, x_coor, model_ratio, fitpa,
                    jackknife=jack)
                effective_rank = covariance_effective_rank(
                    cov, svdcut=fitpa.svdcut)
                sample_rank = covariance_sample_rank(cov)
                gate_ok, gate_reason = fit_identifiability(
                    Ndata, required_rank, effective_rank,
                    sample_rank=sample_rank)
                fit_status, fit_reason, _ = fit_status_from_samples(
                    _fit_result, _last_fit,
                    failure_reason=None if gate_ok else gate_reason)
            para_c0[:, _z] = _fit_result["c0"]
            para_c1[:, _z] = _fit_result["c1"]
            para_dE[:, _z] = _fit_result["dE"]
            chi2[:, _z] = _fit_result["chi2"]
            fit_status_by_z[_z] = fit_status
            fit_reason_by_z[_z] = fit_reason
            effective_rank_by_z[_z] = effective_rank
            sample_rank_by_z[_z] = sample_rank
            report_lines += [f"z = {_z}", "-" * 56,
                             f"condition number = {cond:.3g}",
                             f"fit status = {fit_status}",
                             f"effective covariance rank = {effective_rank}",
                             f"sample covariance rank = {sample_rank}",
                             f"required parameter rank = {required_rank}", ""]

            if fit_status not in ("identifiable", "prior_constrained"):
                report_lines += [f"fit skipped: {fit_reason}", ""]
                continue

            if _last_fit is not None:
                report_lines.append(_last_fit.format(maxline=True))

            report_lines += ["", ""]

        channel_fit_status, channel_fit_reason = aggregate_fit_statuses(
            fit_status_by_z, fit_reason_by_z)
        ch_results[had_name] = {
            'ratio': ratio, 'c0': para_c0, 'c1': para_c1,
            'dE': para_dE, 'chi2': chi2,
            'fit_status': channel_fit_status,
            'fit_status_by_z': fit_status_by_z,
            'fit_reason': channel_fit_reason,
            'fit_reason_by_z': np.asarray(fit_reason_by_z),
            'effective_rank_by_z': effective_rank_by_z,
            'sample_rank_by_z': sample_rank_by_z,
            'required_rank': required_rank,
        }
        channel_reports[had_name] = report_lines

    # 两个 channel 必须在独立产物中保存；aggregate 只在循环结束后生成一次，
    # 从而不会被后续 pion 迭代覆盖 proton 的结果或报告。
    channel_statuses = [result['fit_status'] for result in ch_results.values()]
    channel_reasons = [result['fit_reason'] for result in ch_results.values()]
    aggregate_status, aggregate_reason = aggregate_fit_statuses(
        channel_statuses, channel_reasons)
    channel_names = list(ch_results)
    channel_status_array = np.asarray(channel_statuses)
    channel_reason_array = np.asarray(channel_reasons)
    effective_rank_array = np.asarray(
        [ch_results[name]['effective_rank_by_z'].min()
         for name in channel_names], dtype=np.int64)
    sample_rank_array = np.asarray(
        [ch_results[name]['sample_rank_by_z'].min()
         for name in channel_names], dtype=np.int64)

    aggregate_report_lines = [
        "=" * 70,
        "  Disconnected Aggregate Fit Report",
        "=" * 70,
        f"  aggregate fit status = {aggregate_status}",
        f"  aggregate fit reason = {aggregate_reason}",
        f"  channels = {', '.join(channel_names)}",
        "=" * 70, "",
    ]
    aggregate_payload = {
        "fit_status": np.asarray(aggregate_status),
        "fit_reason": np.asarray(aggregate_reason),
        "fit_status_by_channel": channel_status_array,
        "fit_reason_by_channel": channel_reason_array,
        "effective_rank_by_channel": effective_rank_array,
        "sample_rank_by_channel": sample_rank_array,
        "required_rank": np.asarray(required_rank, dtype=np.int64),
        "channel_names": np.asarray(channel_names, dtype="<U32"),
    }
    for had_name in channel_names:
        result = ch_results[had_name]
        aggregate_report_lines += [
            f"channel = {had_name}", "-" * 56,
            f"fit status = {result['fit_status']}",
            f"fit reason = {result['fit_reason']}", "",
            "effective covariance rank = "
            f"{result['effective_rank_by_z'].min()} (minimum over z)",
            "sample covariance rank = "
            f"{result['sample_rank_by_z'].min()} (minimum over z)",
            f"required parameter rank = {required_rank}", "",
        ]
        for name in ("c0", "c1", "dE", "chi2"):
            aggregate_payload[f"{name}_{had_name}"] = result[name]

        # Keep the historical unqualified keys as an explicitly documented
        # proton view for pipeline/report readers that predate channel files.
        if had_name == "proton":
            for name in ("c0", "c1", "dE", "chi2"):
                aggregate_payload[name] = result[name]
            aggregate_payload["fit_status_by_z"] = result["fit_status_by_z"]
            aggregate_payload["fit_reason_by_z"] = result["fit_reason_by_z"]
            aggregate_payload["effective_rank"] = result[
                "effective_rank_by_z"]
            aggregate_payload["sample_rank"] = result["sample_rank_by_z"]
            aggregate_payload["legacy_channel"] = np.asarray("proton")

        channel_payload = {
            name: result[name] for name in ("c0", "c1", "dE", "chi2")
        }
        channel_payload.update({
            "fit_status": np.asarray(result["fit_status"]),
            "fit_status_by_z": result["fit_status_by_z"],
            "fit_reason": np.asarray(result["fit_reason"]),
            "fit_reason_by_z": result["fit_reason_by_z"],
            "effective_rank": result["effective_rank_by_z"],
            "sample_rank": result["sample_rank_by_z"],
            "required_rank": np.asarray(required_rank, dtype=np.int64),
            "channel": np.asarray(had_name),
        })
        data_path = os.path.join(out_dir, f"0_fit_data_{had_name}.npz")
        report_path = os.path.join(out_dir, f"1_fit_report_{had_name}.txt")
        np.savez(data_path, **channel_payload)
        channel_report = list(channel_reports[had_name])
        channel_report += [
            f"aggregate fit status = {aggregate_status}",
            f"aggregate fit reason = {aggregate_reason}", "",
        ]
        with open(report_path, "w") as f:
            f.write("\n".join(channel_report))
        result["fit_data_path"] = data_path
        result["fit_report_path"] = report_path
        result["aggregate_fit_status"] = aggregate_status
        result["aggregate_fit_reason"] = aggregate_reason

    aggregate_payload["effective_rank"] = np.asarray(
        effective_rank_array.min(), dtype=np.int64)
    aggregate_payload["sample_rank"] = np.asarray(
        sample_rank_array.min(), dtype=np.int64)
    np.savez(os.path.join(out_dir, "0_fit_data.npz"), **aggregate_payload)
    with open(os.path.join(out_dir, "1_fit_report.txt"), "w") as f:
        f.write("\n".join(aggregate_report_lines))
    logger(f"  Saved per-channel ratio + fit and aggregate status to {out_dir}")

    # ── 绘图（code_1.py 风格：ratio/c0/chi2，与 analyze.py 一致）──
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    for had_name, res in ch_results.items():
        _plot_disconnected(had_name, res, out_dir, logger)
    return ch_results


def _plot_disconnected(had_name, res, out_dir, logger=print):
    """code_1.py 风格图：ratio.png（逐 z）、c0.png、chi2.png。"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fit_status = str(res.get("fit_status", "unavailable"))
    if fit_status not in ("identifiable", "prior_constrained"):
        logger(
            f"  {had_name} fit plots skipped: status={fit_status}; "
            f"reason={res.get('fit_reason', 'fit status unavailable')}"
        )
        return

    ratio = res['ratio']              # (Nsample, dt, dtau, z)
    para_c0, para_c1 = res['c0'], res['c1']
    chi2 = res['chi2']
    rm = ratio.mean(0); re_ = sem(ratio, True)

    # c0 vs z
    z_list = list(range(rm.shape[-1]))
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.errorbar(z_list, para_c0.mean(0), yerr=sem(para_c0, True), fmt='x-',
                label='c0(z)')
    ax.axhline(0, color='gray', lw=0.8)
    ax.set_xlabel('z')
    ax.set_ylabel('c0')
    ax.set_title(f'{had_name}: c0 vs z (disconnected ratio fit)')
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, f'c0_{had_name}.png'), dpi=150)
    plt.close(fig)

    # chi2/dof vs z
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(z_list, chi2.mean(0), s=30)
    ax.axhline(1.0, color='orange', ls='--')
    ax.set_xlabel('z'); ax.set_ylabel('chi2/dof'); ax.set_ylim(0, 2)
    ax.set_title(f'{had_name}: chi2/dof vs z')
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, f'chi2_{had_name}.png'), dpi=150)
    plt.close(fig)

    # ratio(dt,dtau,z) 若干 z
    zs = [0, 6, 12, 18]
    zs = [z for z in zs if z < rm.shape[-1]]
    nrow = (len(zs) + 1) // 2
    fig, axes = plt.subplots(nrow, 2, figsize=(12, 4 * nrow), squeeze=False)
    for k, z in enumerate(zs):
        ax = axes[k // 2][k % 2]
        for dt in [8, 10, 12, 14]:
            if dt >= rm.shape[0]:
                continue
            tau = np.arange(dt + 1)
            xv = tau - dt / 2
            yv = rm[dt, :dt + 1, z]
            ye = re_[dt, :dt + 1, z]
            ax.errorbar(xv, yv, yerr=ye, fmt='x', capsize=0, label=f'dt={dt}')
        ax.set_xlabel('tau - t_sep/2'); ax.set_ylabel('R')
        ax.set_title(f'z={z}, c0={para_c0[:, z].mean():.3f}')
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(handles, labels, fontsize=8)
        ax.grid(alpha=0.3)
    fig.suptitle(f'{had_name}: Disconnected ratio R(dt,dtau,z), Pz=2')
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, f'ratio_{had_name}.png'), dpi=150)
    plt.close(fig)
    logger(f"  Plots saved to {out_dir}")
