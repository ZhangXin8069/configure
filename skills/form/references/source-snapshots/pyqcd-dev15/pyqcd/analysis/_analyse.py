"""
Statistical Analysis Module
===========================

Jackknife and Bootstrap resampling, effective mass extraction (log, cosh),
3pt/2pt ratio computation, and GEVP solver.

Adapted from lqcddb analyse/analyse.py.
"""

import numpy as np
from ..tools._backend import get_backend
from ..lattice._constants import fm2GeV
from ..tools._base import ArraySlicer


def _errstate(backend):
    """后端无关的 errstate：numpy 有，cupy 没有（cupy 下直接计算并容忍 NaN）。"""
    ctx = getattr(backend, 'errstate', None)
    if ctx is not None:
        return ctx(divide='ignore', invalid='ignore')
    from contextlib import nullcontext
    return nullcontext()


# ═══════════════════════════════════════════════════════════════════
# Momentum to Energy conversion (GeV)
# ═══════════════════════════════════════════════════════════════════

def Mom2GeV(Nx: int, alttc: float, Mom, M0):
    """Convert lattice momentum to energy in GeV.

    E = sqrt(Q²·p² + M₀²)  where Q = 2π/(Nx·a)

    Parameters
    ----------
    Nx : int
        Spatial lattice size.
    alttc : float
        Lattice spacing in fm.
    Mom : float, list of float, or list of list of float
        Momentum: scalar (p²), [pz,py,px], or [[...],...].
    M0 : float or list of float
        Mass(es) in GeV.

    Returns
    -------
    float or list of float
        Energy in GeV.
    """
    single_Q2 = 2 * np.pi / Nx * (fm2GeV / alttc)

    if isinstance(Mom, (int, float)):
        mom_sq = Mom
    elif isinstance(Mom, list):
        if not Mom:
            mom_sq = 0.0
        elif isinstance(Mom[0], (int, float)):
            mom_sq = sum(x**2 for x in Mom)
        elif isinstance(Mom[0], list):
            mom_sq = [sum(x**2 for x in sub) for sub in Mom]
        else:
            raise TypeError(f"Unsupported Mom type: {type(Mom[0])}")
    else:
        raise TypeError(f"Unsupported Mom type: {type(Mom)}")

    if isinstance(M0, (int, float)):
        if isinstance(mom_sq, list):
            return [(single_Q2**2 * msq + M0**2)**0.5 for msq in mom_sq]
        else:
            return (single_Q2**2 * mom_sq + M0**2)**0.5
    elif isinstance(M0, list):
        if not M0:
            return [0.0] * len(mom_sq) if isinstance(mom_sq, list) else 0.0
        if isinstance(mom_sq, list):
            result = []
            for msq in mom_sq:
                total = sum((single_Q2**2 * msq + m**2)**0.5 for m in M0)
                result.append(total)
            return result
        else:
            return sum((single_Q2**2 * mom_sq + m**2)**0.5 for m in M0)
    else:
        raise TypeError(f"Unsupported M0 type: {type(M0)}")


# ═══════════════════════════════════════════════════════════════════
# Jackknife Resampling
# ═══════════════════════════════════════════════════════════════════

def Jackknife(data, Nconf_axes=0, only_sample: bool = False, cov_axes=None):
    """Jackknife resampling with optional covariance matrix.

    For N configurations, generates N jackknife samples, each being the
    mean of (N-1) configurations with one left out.

    Auto-detects numpy vs cupy input and uses the appropriate backend.

    Parameters
    ----------
    data : ndarray
        Input data. Configuration axis must be present.
    Nconf_axes : int
        Axis index for configurations (default 0).
    only_sample : bool
        If True, return only jackknife samples (skip mean/err/cov).
    cov_axes : int, tuple, or None
        Axes for which to compute covariance matrix. None = skip.

    Returns
    -------
    dict
        Keys: 'data_sample', 'data_mean', 'data_err', 'data_cov' (if cov_axes).
    """
    # Auto-detect backend from input data type
    is_cupy = type(data).__module__.startswith('cupy')
    if is_cupy:
        backend = get_backend()
    else:
        import numpy as _np
        backend = _np

    ndim = data.ndim
    Nconf_axes = Nconf_axes % ndim
    Nconf = data.shape[Nconf_axes]

    # Jackknife samples: mean over all-but-one
    data_sum = backend.sum(data, axis=Nconf_axes, keepdims=True)
    data_sample = -(data - data_sum) / (Nconf - 1)

    if only_sample:
        return {'data_sample': data_sample}

    # Mean and standard error
    data_mean = backend.mean(data, axis=Nconf_axes)
    data_err = np.sqrt(float(Nconf - 1)) * backend.std(data_sample, axis=Nconf_axes)

    result = {'data_sample': data_sample, 'data_mean': data_mean, 'data_err': data_err}

    if cov_axes is not None:
        if isinstance(cov_axes, int):
            cov_axes = (cov_axes % ndim,)
        else:
            cov_axes = tuple(ax % ndim for ax in cov_axes)

        residual = data_sample - data_mean
        all_axes = list(range(ndim))
        other_axes = [ax for ax in all_axes
                      if ax != Nconf_axes and ax not in cov_axes]
        new_order = [Nconf_axes] + other_axes + list(cov_axes)
        r = backend.transpose(residual, new_order)

        shape_other = [residual.shape[ax] for ax in other_axes]
        shape_cov = [residual.shape[ax] for ax in cov_axes]
        N_cov = int(np.prod(shape_cov))
        r_flat = r.reshape([Nconf] + shape_other + [N_cov])

        cov_sum = backend.einsum('n...i,n...j->...ij', r_flat, r_flat, optimize=True)
        cov = cov_sum * (Nconf - 1) / Nconf
        result['data_cov'] = cov.reshape(shape_other + shape_cov + shape_cov)

    return result


# ═══════════════════════════════════════════════════════════════════
# Bootstrap Resampling
# ═══════════════════════════════════════════════════════════════════

def Bootstrap(data, Nconf_axes=0, only_sample=False, cov_axes=None,
              M=0, N=0):
    """Bootstrap resampling with optional covariance.

    Parameters
    ----------
    data : ndarray
        Input data.
    Nconf_axes : int
        Configuration axis.
    only_sample : bool
        Return only samples.
    cov_axes : int, tuple, or None
        Axes for covariance matrix.
    M : int
        Number of configurations per bootstrap sample (default Nconf-5).
    N : int
        Number of bootstrap samples (default Nconf*4).

    Returns
    -------
    dict
        Keys: 'data_sample', 'data_mean', 'data_err', 'data_cov'.
    """
    backend = get_backend()
    ndim = data.ndim
    Nconf_axes = Nconf_axes % ndim
    Nconf = data.shape[Nconf_axes]

    if M == 0:
        M = max(Nconf - 5, 1)
    if N == 0:
        N = Nconf * 4

    sample_shape = tuple(list(data.shape[:Nconf_axes]) + list(data.shape[Nconf_axes+1:]))
    data_sample = backend.zeros((N,) + sample_shape, dtype=complex)

    # Sample 0: all configurations
    indices = backend.arange(Nconf)
    selected = backend.take(data, indices, axis=Nconf_axes)
    data_sample[0] = backend.mean(selected, axis=Nconf_axes)

    for i in range(1, N):
        indices = backend.random.choice(Nconf, size=M, replace=True)
        selected = backend.take(data, indices, axis=Nconf_axes)
        data_sample[i] = backend.mean(selected, axis=Nconf_axes)

    if only_sample:
        return {'data_sample': data_sample}

    data_mean = backend.mean(data_sample, axis=0)
    data_err = backend.std(data_sample, axis=0)

    result = {'data_sample': data_sample, 'data_mean': data_mean, 'data_err': data_err}

    if cov_axes is not None:
        if isinstance(cov_axes, int):
            cov_axes = (cov_axes % ndim,)
        else:
            cov_axes = tuple(ax % ndim for ax in cov_axes)

        cov_axes_r = tuple(ax + 1 if ax < Nconf_axes else ax for ax in cov_axes)
        residual = data_sample - backend.mean(data_sample, axis=0, keepdims=True)
        ndim_sample = residual.ndim
        all_axes = list(range(ndim_sample))
        other_axes = [ax for ax in all_axes if ax != 0 and ax not in cov_axes_r]
        new_order = [0] + other_axes + list(cov_axes_r)
        r = backend.transpose(residual, new_order)

        shape_other = [residual.shape[ax] for ax in other_axes]
        shape_cov = [residual.shape[ax] for ax in cov_axes_r]
        N_cov = int(np.prod(shape_cov))
        r_flat = r.reshape((N,) + tuple(shape_other) + (N_cov,))

        cov = backend.einsum('n...i,n...j->...ij', r_flat, r_flat) / N
        result['data_cov'] = cov.reshape(tuple(shape_other) + tuple(shape_cov) + tuple(shape_cov))

    return result


# ═══════════════════════════════════════════════════════════════════
# Effective Mass
# ═══════════════════════════════════════════════════════════════════

def meff(data_sample, alttc, Nconf_axes: int = 0, Nt_axes: int = 1,
         meff_type: str = 'log'):
    """Compute effective mass from correlation function jackknife samples.

    Parameters
    ----------
    data_sample : ndarray
        Jackknife samples of the correlation function. Must be real.
    alttc : float
        Lattice spacing in fm.
    Nconf_axes : int
        Configuration axis (default 0).
    Nt_axes : int
        Time axis (default 1).
    meff_type : {'log', 'cosh', 'GEVP'}
        Effective mass formula.

    Returns
    -------
    dict
        Keys: 'data_sample', 'data_mean', 'data_err'.
    """
    # Auto-detect backend
    is_cupy = type(data_sample).__module__.startswith('cupy')
    if is_cupy:
        backend = get_backend()
    else:
        import numpy as _np
        backend = _np

    if data_sample.dtype not in (np.float64, np.float32):
        # Convert to real if complex
        data_sample = backend.abs(data_sample)

    Nconf = data_sample.shape[Nconf_axes]
    Nt = data_sample.shape[Nt_axes]

    meff_sample = backend.zeros_like(data_sample)

    with _errstate(backend):
        if meff_type == 'log':
            ArraySlicer(meff_sample).assign(
                dims=[Nt_axes],
                indices=[[x for x in range(Nt - 1)]],
                values=backend.log(
                    ArraySlicer(data_sample).slice(
                        dims=[Nt_axes],
                        indices=[[x for x in range(Nt - 1)]]
                    ) / ArraySlicer(data_sample).slice(
                        dims=[Nt_axes],
                        indices=[[x + 1 for x in range(Nt - 1)]]
                    )
                ) * (fm2GeV / alttc)
            )

        elif meff_type == 'cosh':
            # m_eff(t) = arccosh[(C(t+2) + C(t)) / (2*C(t+1))] / a
            # Handle cases where ratio < 1 (noise-dominated tails):
            # use arccosh(max(ratio, 1.0)) for valid values, NaN → 0
            C_t = ArraySlicer(data_sample).slice(
                dims=[Nt_axes], indices=[[x for x in range(Nt - 2)]])
            C_t1 = ArraySlicer(data_sample).slice(
                dims=[Nt_axes], indices=[[x + 1 for x in range(Nt - 2)]])
            C_t2 = ArraySlicer(data_sample).slice(
                dims=[Nt_axes], indices=[[x + 2 for x in range(Nt - 2)]])

            ratio = (C_t2 + C_t) / (2 * C_t1 + 1e-30)
            # Clamp ratio >= 1 (arccosh undefined for <1)
            ratio_clamped = backend.where(ratio >= 1.0, ratio, 1.0)
            meff_val = backend.arccosh(ratio_clamped) * (fm2GeV / alttc)
            # Set to 0 where ratio was < 1 (invalid signal)
            meff_val = backend.where(ratio >= 1.0, meff_val, 0.0)

            ArraySlicer(meff_sample).assign(
                dims=[Nt_axes],
                indices=[[x for x in range(Nt - 2)]],
                values=meff_val
            )

        elif meff_type == 'GEVP':
            ArraySlicer(meff_sample).assign(
                dims=[Nt_axes],
                indices=[[x for x in range(Nt - 1)]],
                values=backend.log(
                    ArraySlicer(data_sample).slice(
                        dims=[Nt_axes],
                        indices=[[x for x in range(Nt - 1)]]
                    ) / ArraySlicer(data_sample).slice(
                        dims=[Nt_axes],
                        indices=[[x + 1 for x in range(Nt - 1)]]
                    )
                ) * (fm2GeV / alttc)
            )

    meff_mean = backend.mean(meff_sample, axis=Nconf_axes)
    meff_err = backend.std(meff_sample, axis=Nconf_axes) * backend.sqrt(Nconf - 1)

    return {
        'data_sample': meff_sample,
        'data_mean': meff_mean,
        'data_err': meff_err,
    }


# ═══════════════════════════════════════════════════════════════════
# 3pt/2pt Ratio
# ═══════════════════════════════════════════════════════════════════

def ratio_3pt(data_3pt_sample, data_2ptI_sample, data_2ptF_sample=None,
              t_sep=12, Nconf_axes=0,
              tau_axes=-1, t_sink_axes=-1,
              t_src_axes=None,
              link_axes=None, link_fold=False):
    """Compute 3pt/2pt ratio R(τ) = C₃(τ) / C₂(t_sep) × sqrt(…).

    R = C₃ / C₂^F(t_sep) × √[C₂^I(t_sep-τ)·C₂^F(τ)·C₂^F(t_sep)
                              / (C₂^F(t_sep-τ)·C₂^I(τ)·C₂^I(t_sep))]

    Parameters
    ----------
    data_3pt_sample : ndarray
        3pt jackknife samples.
    data_2ptI_sample : ndarray
        Initial-state 2pt jackknife samples.
    data_2ptF_sample : ndarray, optional
        Final-state 2pt samples. If None, use data_2ptI_sample.
    t_sep : int
        Source-sink separation.
    Nconf_axes : int
        Configuration axis.
    tau_axes : int
        Current insertion time τ axis (for 3pt).
    t_sink_axes : int
        Sink time axis (for 2pt).
    t_src_axes : int, optional
        Source time axis (for 2D mode).
    link_axes : int, optional
        Wilson link axis.
    link_fold : bool
        Fold link dimension.

    Returns
    -------
    dict
        Keys: 'data_sample', 'data_mean', 'data_err'.
    """
    # Auto-detect backend from input to avoid cupy/numpy mismatch
    is_cupy = type(data_3pt_sample).__module__.startswith('cupy')
    if is_cupy:
        backend = get_backend()
    else:
        import numpy as _np_backend
        backend = _np_backend

    if data_2ptF_sample is None:
        data_2ptF_sample = data_2ptI_sample

    # Link folding
    if link_fold and link_axes is not None:
        def _fold(d, ax):
            lm = d.shape[ax] // 2
            idx_u = [slice(None)] * d.ndim
            idx_u[ax] = [x for x in range(lm, 2*lm+1)]
            idx_l = [slice(None)] * d.ndim
            idx_l[ax] = [x for x in range(lm+1)][::-1]
            return (d[tuple(idx_u)] + d[tuple(idx_l)]) / 2
        data_3pt_sample = _fold(data_3pt_sample, link_axes)
        data_2ptI_sample = _fold(data_2ptI_sample, link_axes)
        data_2ptF_sample = _fold(data_2ptF_sample, link_axes)

    Nconf = data_3pt_sample.shape[Nconf_axes]

    if t_src_axes is None:
        # 1D mode: single time axis per array
        Ntau = data_3pt_sample.shape[tau_axes]
        idx_tshift = t_sep - backend.arange(Ntau)

        C2F_tsep_minus_tau = ArraySlicer(data_2ptF_sample).slice(
            dims=[t_sink_axes], indices=[list(idx_tshift)])
        C2I_tsep_minus_tau = ArraySlicer(data_2ptI_sample).slice(
            dims=[t_sink_axes], indices=[list(idx_tshift)])

        C2F_tsep = data_2ptF_sample.take(t_sep, axis=t_sink_axes)
        C2F_tsep = backend.expand_dims(C2F_tsep, axis=tau_axes)
        C2I_tsep = data_2ptI_sample.take(t_sep, axis=t_sink_axes)
        C2I_tsep = backend.expand_dims(C2I_tsep, axis=tau_axes)

        # Slice 2pt at t=τ for C₂^F(τ) and C₂^I(τ) in the ratio formula
        C2F_tau_idx = backend.arange(Ntau)
        C2F_at_tau = ArraySlicer(data_2ptF_sample).slice(
            dims=[t_sink_axes], indices=[list(C2F_tau_idx)])
        C2I_at_tau = ArraySlicer(data_2ptI_sample).slice(
            dims=[t_sink_axes], indices=[list(C2F_tau_idx)])

        num = C2I_tsep_minus_tau * C2F_at_tau * C2F_tsep
        den = C2F_tsep_minus_tau * C2I_at_tau * C2I_tsep
        with _errstate(backend):
            sqrt_term = backend.sqrt(backend.maximum(
                backend.nan_to_num(num / den, nan=0.0), 0))
        ratio_sample = data_3pt_sample / C2F_tsep * sqrt_term

    else:
        # 2D mode: source time + tau/sink axes
        Nt_src = data_3pt_sample.shape[t_src_axes]
        Ntau = data_3pt_sample.shape[tau_axes]
        ndim = data_3pt_sample.ndim
        _src_pos = t_src_axes if t_src_axes >= 0 else ndim + t_src_axes
        _sink_pos = t_sink_axes if t_sink_axes >= 0 else ndim + t_sink_axes
        _tau_pos = tau_axes if tau_axes >= 0 else ndim + tau_axes
        _sink = (_sink_pos - 1) if _sink_pos > _src_pos else _sink_pos
        _tau = (_tau_pos - 1) if _tau_pos > _src_pos else _tau_pos

        ratio_sample = backend.zeros_like(data_3pt_sample)

        for t_src in range(Nt_src):
            t_sep_time = (t_src + t_sep) % Nt_src
            t_ops = (t_src + backend.arange(Ntau)) % Nt_src
            t_diffs = (t_src + t_sep - backend.arange(Ntau)) % Nt_src

            C3_slice = data_3pt_sample.take(t_src, axis=t_src_axes)
            C3_by_tau = ArraySlicer(C3_slice).slice(
                dims=[_tau], indices=[list(t_ops)])

            C2F_tsep = data_2ptF_sample.take(t_src, axis=t_src_axes)
            C2F_tsep = C2F_tsep.take(t_sep_time, axis=_sink)
            C2F_tsep = backend.expand_dims(C2F_tsep, axis=_tau)

            C2F_tau_src = data_2ptF_sample.take(t_src, axis=t_src_axes)
            C2F_tau = ArraySlicer(C2F_tau_src).slice(
                dims=[_sink], indices=[list(t_ops)])
            C2F_tshift_src = data_2ptF_sample.take(t_src, axis=t_src_axes)
            C2F_tshift = ArraySlicer(C2F_tshift_src).slice(
                dims=[_sink], indices=[list(t_diffs)])

            C2I_tsep = data_2ptI_sample.take(t_src, axis=t_src_axes)
            C2I_tsep = C2I_tsep.take(t_sep_time, axis=_sink)
            C2I_tsep = backend.expand_dims(C2I_tsep, axis=_tau)
            C2I_tau_src = data_2ptI_sample.take(t_src, axis=t_src_axes)
            C2I_tau = ArraySlicer(C2I_tau_src).slice(
                dims=[_sink], indices=[list(t_ops)])
            C2I_tshift_src = data_2ptI_sample.take(t_src, axis=t_src_axes)
            C2I_tshift = ArraySlicer(C2I_tshift_src).slice(
                dims=[_sink], indices=[list(t_diffs)])

            num = C2I_tshift * C2F_tau * C2F_tsep
            den = C2F_tshift * C2I_tau * C2I_tsep
            with _errstate(backend):
                sqrt_term = backend.sqrt(backend.maximum(
                    backend.nan_to_num(num / den, nan=0.0), 0))

            ratio_slice = C3_by_tau / C2F_tsep * sqrt_term

            t_ops_inv = (backend.arange(Ntau) - t_src) % Nt_src
            ratio_slice_abs = ArraySlicer(ratio_slice).slice(
                dims=[_tau], indices=[list(t_ops_inv)])

            idx_assign = [slice(None)] * ratio_sample.ndim
            idx_assign[t_src_axes] = t_src
            ratio_sample[tuple(idx_assign)] = ratio_slice_abs

    ratio_mean = backend.mean(ratio_sample.real, axis=Nconf_axes)
    ratio_err = backend.std(ratio_sample.real, axis=Nconf_axes) * backend.sqrt(Nconf - 1)

    return {
        'data_sample': ratio_sample,
        'data_mean': ratio_mean,
        'data_err': ratio_err,
    }


# ═══════════════════════════════════════════════════════════════════
# Source averaging over time translations
# ═══════════════════════════════════════════════════════════════════

def loop_tsrc(data, indx: list = None, Boundary_Conditions: str = 'Periodic',
              Ctype: str = '2pt', t_sep: int = 0):
    """Average correlation function over source time translations.

    Parameters
    ----------
    data : ndarray
        Correlation function with t_src and t_sink axes.
    indx : list of int
        [tsrc_axis, tsink_axis] — the two time axes to loop over.
    Boundary_Conditions : str
        'Periodic' or 'Antiperiodic'.
    Ctype : str
        '2pt' or '3pt'.
    t_sep : int
        Source-sink separation (for 3pt antiperiodic wrapping).

    Returns
    -------
    ndarray
        Source-averaged data. The t_src axis is reduced to size 1.
    """
    if indx is None:
        indx = [-2, -3]

    backend = get_backend()
    type_cupy = type(data).__module__.startswith('cupy')
    data_np = data.get() if type_cupy else np.array(data)

    nd = data_np.ndim
    a0, a1 = indx[0] % nd, indx[1] % nd
    Nt = data_np.shape[a0]
    if data_np.shape[a1] != Nt:
        raise ValueError('data[indx] must have the same size')

    if Ctype == '3pt':
        sign = -1.0 if Boundary_Conditions == 'Antiperiodic' else 1.0
        tail = [slice(None)] * nd
        tail[a0] = slice(Nt - t_sep, Nt)
        data_np[tuple(tail)] *= sign
    elif Boundary_Conditions == 'Antiperiodic':
        for tsrc in range(Nt):
            for tsink in range(Nt):
                if tsink < tsrc:
                    idx = [slice(None)] * nd
                    idx[a0] = tsrc
                    idx[a1] = tsink
                    data_np[tuple(idx)] *= -1.0

    data_looped = np.zeros([(1 if i == a0 else (Nt if i == a1 else d))
                            for i, d in enumerate(data_np.shape)])
    for tsrc in range(Nt):
        for tsink in range(Nt):
            dt = (tsink - tsrc + Nt) % Nt
            sel = [slice(None)] * nd
            sel[a0] = tsrc
            sel[a1] = tsink
            vin = np.expand_dims(data_np[tuple(sel)],
                                 a0 - (a1 < a0))
            tgt = [slice(None)] * nd
            tgt[a1] = dt
            data_looped[tuple(tgt)] += vin

    if type_cupy:
        return backend.asarray(data_looped)
    return data_looped


# ═══════════════════════════════════════════════════════════════════
# GEVP Solver
# ═══════════════════════════════════════════════════════════════════

def solve_gevp(C, t0):
    """Solve generalized eigenvalue problem for a correlator matrix.

    C(t) v_n = λ_n(t,t₀) C(t₀) v_n
    λ_n(t,t₀) = exp(-E_n (t - t₀))

    Parameters
    ----------
    C : ndarray, shape (N, N, Nt)
        Correlation function matrix.
    t0 : int
        Reference time slice.

    Returns
    -------
    eigenvalues : ndarray, shape (N, Nt)
        Sorted eigenvalues. t < t₀: ascending; t ≥ t₀: descending.
    eigenvectors : ndarray, shape (N, N, Nt)
        Corresponding eigenvectors.
    """
    backend = get_backend()
    from scipy.linalg import eigh

    if C.ndim != 3:
        raise ValueError(f"C must be 3D, got shape {C.shape}")
    if C.shape[0] != C.shape[1]:
        raise ValueError(f"C first two dims must match, got {C.shape[:2]}")

    N = C.shape[0]
    Nt = C.shape[2]

    if t0 < 0 or t0 >= Nt:
        raise ValueError(f"t0={t0} out of range [0, {Nt-1}]")

    # Hermitianize without discarding valid complex off-diagonal elements.
    C_hermitian = (C.conj().transpose(1, 0, 2) + C) / 2

    # Convert to numpy for scipy
    C_np = (C_hermitian.get() if hasattr(C_hermitian, 'get')
            else C_hermitian)

    C_GEVP = backend.zeros((N, Nt))
    eigvec_dtype = np.complex128 if np.iscomplexobj(C_np) else float
    C_eigvecs = backend.zeros((N, N, Nt), dtype=eigvec_dtype)

    for t in range(Nt):
        eigenvalues, eigenvectors = eigh(C_np[..., t], C_np[..., t0])
        eigenvalues = eigenvalues.real

        if t < t0:
            order = np.argsort(eigenvalues)
        else:
            order = np.argsort(eigenvalues)[::-1]

        eigenvalues = eigenvalues[order]
        eigenvectors = eigenvectors[:, order]

        # Normalize eigenvectors
        coeff = eigenvectors.conj().T @ eigenvectors
        norm = np.sqrt(np.diagonal(coeff).real).reshape(1, -1)
        eigenvectors = eigenvectors / norm

        C_GEVP[:, t] = backend.asarray(eigenvalues)
        C_eigvecs[..., t] = backend.asarray(eigenvectors)

    return C_GEVP, C_eigvecs


# ═══════════════════════════════════════════════════════════════════
# 分组聚合基元 + disconnected 矩阵元构造（整合 lqcddb analyse.py）
# ═══════════════════════════════════════════════════════════════════

def mean_over_array_of_list(arr, axes, groupings):
    """按指标分组沿指定轴求均值（照抄 lqcddb analyse.mean_over_array_of_list）。

    Args:
        arr: 任意形状输入数组。
        axes: 待聚合轴（0 起）。
        groupings: 每轴一组"组列表"，每组为该轴原指标的列表；
            全部指标须恰好覆盖一次。聚合后该轴长度 = 组数。
    Returns:
        形状为原形状、各聚合轴缩为对应组数的数组。
    """
    backend = get_backend()
    arr = backend.asarray(arr)

    if len(axes) != len(groupings):
        raise ValueError("axes and groupings must have same length")

    for ax, groups in zip(axes, groupings):
        if ax < 0 or ax >= arr.ndim:
            raise ValueError(f"axis {ax} out of range")
        all_idx = set()
        for g in groups:
            for i in g:
                if i < 0 or i >= arr.shape[ax]:
                    raise ValueError(f"index {i} out of range on axis {ax}")
                if i in all_idx:
                    raise ValueError(f"duplicate index {i} on axis {ax}")
                all_idx.add(i)
        if len(all_idx) != arr.shape[ax]:
            missing = set(range(arr.shape[ax])) - all_idx
            raise ValueError(f"axis {ax}: indices {missing} not covered")

    for ax, groups in zip(axes, groupings):
        # 原版为 sort+reduceat 分块归并；pyqcd 后端适配层无 reduceat，
        # 改为逐组 take+归约再 stack——分组次序与结果语义等价。
        red = [backend.mean(backend.take(arr, list(g), axis=ax), axis=ax)
               for g in groups]
        arr = backend.stack(red, axis=ax)
    return arr


def sum_over_array_of_list(arr, axes, groupings):
    """按指标分组沿指定轴求和（照抄 lqcddb analyse.sum_over_array_of_list）。

    与 :func:`mean_over_array_of_list` 同构，仅不做组内除法。
    """
    backend = get_backend()
    arr = backend.asarray(arr)

    if len(axes) != len(groupings):
        raise ValueError("axes and groupings must have same length")
    for ax, groups in zip(axes, groupings):
        if ax < 0 or ax >= arr.ndim:
            raise ValueError(f"axis {ax} out of range")
        all_idx = set()
        for g in groups:
            for i in g:
                if i < 0 or i >= arr.shape[ax]:
                    raise ValueError(f"index {i} out of range on axis {ax}")
                if i in all_idx:
                    raise ValueError(f"duplicate index {i} on axis {ax}")
                all_idx.add(i)
        if len(all_idx) != arr.shape[ax]:
            missing = set(range(arr.shape[ax])) - all_idx
            raise ValueError(f"axis {ax}: indices {missing} not covered")

    for ax, groups in zip(axes, groupings):
        red = [backend.sum(backend.take(arr, list(g), axis=ax), axis=ax)
               for g in groups]
        arr = backend.stack(red, axis=ax)
    return arr


def dis_connect(data_2pt_sample, data_bubble_sample, Nconf_axes: int,
                t_src_axes: int, t_sink_axes: int, tsep: int,
                dtype: str = 'PDF'):
    """2pt×bubble 时间滚移构造 disconnected 矩阵元（照抄 lqcddb
    analyse.dis_connect；PFF/PDF 两模式）。

    对每个 t_src：2pt 连通部分沿 sink 轴滚 −t 对齐源点，bubble 沿 src 轴滚
    −t 对齐；取 sink=tsep 处乘积并对 src 求和。PFF 模式另加交换项并装配到
    [0..tsep]∪[tsep..2·tsep] 窗口。

    Args:
        data_2pt_sample: (Nconf, ..., t_src, t_sink, ...) 2pt 样本。
        data_bubble_sample: 同形状 bubble 样本。
        Nconf_axes/t_src_axes/t_sink_axes: 对应轴编号。
        tsep: 源-插算符分离。
        dtype: 'PDF'（单乘积全窗）或 'PFF'（对称双乘积分段窗）。
    """
    backend = get_backend()

    nd = data_2pt_sample.ndim
    a_s = t_src_axes % nd
    a_k = t_sink_axes % nd
    Nt = data_2pt_sample.shape[a_s]

    m2p = np.array(data_2pt_sample)
    m2p = m2p - m2p.mean(axis=Nconf_axes, keepdims=True)
    bubc = np.array(data_bubble_sample)
    bubc = bubc - bubc.mean(axis=Nconf_axes, keepdims=True)

    out2 = np.zeros_like(m2p)
    outb = np.zeros_like(m2p)
    kshift = a_k - (a_k > a_s)
    a_s_bub = t_src_axes % bubc.ndim
    for t in range(Nt):
        sel = [slice(None)] * nd
        sel[a_s] = t
        blk = m2p[tuple(sel)]
        out2[tuple(sel)] = np.roll(blk, -t, axis=kshift)
        slot = outb[tuple(sel)]
        val = np.roll(bubc, -t, axis=a_s_bub)
        if val.shape == slot.shape:
            # 参照语义：等尺寸时平坦重解释（C 序）
            outb[tuple(sel)] = val.reshape(slot.shape)
        else:
            # 等秩输入（bubble 与 2pt 同形）：按意图取对齐后同位切片
            outb[tuple(sel)] = val[tuple(sel)]
    del m2p, bubc

    ksel = [slice(None)] * nd
    ksel[a_k] = [tsep]
    term1 = out2[tuple(ksel)] * outb

    matrix = np.zeros_like(outb)
    if dtype == 'PFF':
        term2 = outb[tuple(ksel)] * out2
        fid = [slice(None)] * nd
        fid[a_k] = list(range(tsep + 1))
        bid = [slice(None)] * nd
        bid[a_k] = list(range(tsep, min(2 * tsep + 1, Nt)))
        matrix[tuple(fid)] = term1[tuple(fid)]
        matrix[tuple(bid)] = term2[tuple(bid)]
    else:
        matrix[:] = term1

    del out2, outb
    return matrix.sum(axis=a_s, keepdims=True)

    return backend.sum(data_2pt_bubble_matrix, axis=t_src_axes, keepdims=True)


plot_analyse_marker = ['s', '*', '+', 'x', 'p', 'h', 'v', 'X', 'D', 'P',
                       'H', 'o']
plot_analyse_color = ['#3498DB', '#ff7f0e', '#2ECC71', '#E74C3C',
                      '#9467bd', '#8c564b', '#CB4335', '#e377c2',
                      '#7f7f7f', '#F1C40F', '#17becf', '#2ca02c']


def twopt_slice_boundary(pp, pm):
    """twopt_slice (Nt,Nt) 边界符号翻转（照抄 donghx 2pt_proton_* 装配段）：
    pp 在 t_sink<t_source 处取负；pm 在 t_sink>t_source 处取负。原地修改。"""
    nt = pp.shape[0]
    for t_source in range(nt):
        for t_sink in range(nt):
            if t_sink < t_source:
                pp[t_sink, t_source] *= -1.0
            if t_sink > t_source:
                pm[t_sink, t_source] *= -1.0
    return pp, pm
