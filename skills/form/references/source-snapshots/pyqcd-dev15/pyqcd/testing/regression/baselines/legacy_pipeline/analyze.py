"""
Statistical Analysis — Jackknife / meff / ratio_3p (docker-v20260805)
=====================================================================

Implements the statistical analysis requested by the user, with the OUTPUT
FORMAT of ``examples/huangcl/02_ratio/code_1.py``:

  1. Jackknife + effective mass for pion & proton at P=(0,0,0) and P=(0,0,2).
  2. Connected 3pt/2pt ratio R(τ) (from the PJN correlators) via
     ``lib.analyse.ratio_3pt``.
  3. Disconnected gluon-PDF ratio R(dt, dtau, z) (code_1.py algorithm):
        C3(dt,dtau,z) = C2(dt) · OPE(dtau,z)          (disconnected factorisation)
        R(dt,dtau,z)  = <[C3 - C2·⟨OPE⟩] / C2>_ti      (jackknife over configs)
     with per-z correlated fits
        R(dt,dtau) = c0 + c1·e^{-dE·dtau} + c1·e^{-dE·(dt-dtau)}
     exactly as in code_1.py (lsqfit.nonlinear_fit, svdcut, per-sample fits).

Outputs (all saved under the run directory):
    data/analysis/meff_{ch}_mean/err.npy, corr_{ch}_mean/err.npy
    data/analysis/ratio_{had}_{mom}_mean/err.npy        (connected 3pt/2pt)
    analysis/disconnected/ratio_{ch}.npy, 0_fit_data.npz, 1_fit_report.txt,
        plots ratio.png / c0.png / chi2.png
"""

from __future__ import annotations

import os, time
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from config import (NT, NX, ALttc, FM2GEV, T_SEP_3PT, NEV,
                    ANALYSIS_MOMENTA, conf_data_dir)
from utils import save_array, print_banner

from lib.analyse import Jackknife, meff, ratio_3pt

# ═══════════════════════════════════════════════════════════════════
# 1. Jackknife + effective mass (pion & proton at P0 / P2)
# ═══════════════════════════════════════════════════════════════════

# channel key in corr_2pt_all  → (particle, momentum tag)
CHANNELS = [
    ('proton', 'P0', 'corr_pp_P0'),
    ('proton', 'P2', 'corr_pp_P2'),
    ('pion',   'P0', 'corr_pion_P0'),
    ('pion',   'P2', 'corr_pion_P2'),
]


def run_meff_jackknife(corr_2pt_all, conf_ids, run_dir, logger):
    """Jackknife effective masses for all channels.

    corr_2pt_all : dict conf_id → {'corr_pp_P0': (Nt,), 'corr_pi_P2': (Nt,), ...}
    """
    print_banner("Analysis 1: Jackknife + Effective Mass", logger)
    an_dir = os.path.join(run_dir, 'data', 'analysis')
    os.makedirs(an_dir, exist_ok=True)

    meff_types = {'proton': 'cosh', 'pion': 'log'}
    results = {}

    for particle, mom, key in CHANNELS:
        ml = f"P{list(ANALYSIS_MOMENTA[particle].values())[0 if mom=='P0' else 1]}"
        # Gather (Nconf, Nt) real correlators
        stack = np.stack([np.real(corr_2pt_all[cid][key]) for cid in conf_ids])
        jk = Jackknife(stack, Nconf_axes=0)
        mf = meff(jk['data_sample'], ALttc, Nconf_axes=0, Nt_axes=1,
                  meff_type=meff_types[particle])

        cmean, cerr = np.real(jk['data_mean']), np.real(jk['data_err'])
        mmean, merr = np.real(mf['data_mean']), np.real(mf['data_err'])

        # ── Plateau selection ──
        # Proton: later window [6,12] to avoid the early-t excited-state
        # contamination (meff falls from ~1.2 at t=4 to ~1.06 at t=6-10).
        # Pion: log meff is clean and flat from t≈7 onward.
        if particle == 'proton':
            ps, pe = 6, min(NT - 2, 12)
        else:
            ps, pe = 5, min(NT - 2, 18)
        mask = np.isfinite(mmean[ps:pe]) & (merr[ps:pe] > 0) & (mmean[ps:pe] > 0.01)
        if np.sum(mask) < 2:   # fallback to a shorter window
            ps, pe = 2, min(8, NT - 1)
            mask = np.isfinite(mmean[ps:pe]) & (merr[ps:pe] > 0)
        t_plt = np.arange(ps, pe)[mask]
        w = 1.0 / (merr[ps:pe][mask] ** 2 + 1e-10)
        E0 = float(np.sum(mmean[ps:pe][mask] * w) / np.sum(w))
        E0_err = float(1.0 / np.sqrt(np.sum(w)))

        # ── Expected energy & dispersion check ──
        if mom == 'P0':
            E_exp = 1.0 if particle == 'proton' else 0.30
        else:
            m0 = results.get(f'{particle}_P0', {}).get('E0', E0)
            p_phys = (2 * np.pi * 2 / NX) * (FM2GEV / ALttc)   # ≈ 0.981 GeV
            E_exp = np.sqrt(m0 ** 2 + p_phys ** 2)
        dev = abs(E0 - E_exp) / (E0_err + 1e-10)
        status = '✓' if dev < 2 else ('⚠' if dev < 4 else '✗')

        logger.info(f"\n{particle} {ml}: E0 = {E0:.4f} ± {E0_err:.4f} GeV  "
                    f"(expected {E_exp:.3f}, {status} dev={dev:.1f}σ, "
                    f"plateau t∈[{ps},{pe}], {np.sum(mask)} pts)")
        logger.info(f"  C(0) = {cmean[0]:.6e} ± {cerr[0]:.6e}")

        results[f'{particle}_{mom}'] = {
            'E0': E0, 'E0_err': E0_err, 'E_exp': E_exp, 'dev': dev,
            'plateau': (ps, pe), 'npts': int(np.sum(mask)),
            'meff_mean': mmean, 'meff_err': merr,
            'corr_mean': cmean, 'corr_err': cerr,
        }
        save_array(os.path.join(an_dir, f'meff_{particle}_{mom}_mean.npy'), mmean, logger)
        save_array(os.path.join(an_dir, f'meff_{particle}_{mom}_err.npy'), merr, logger)
        save_array(os.path.join(an_dir, f'corr_{particle}_{mom}_mean.npy'), cmean, logger)
        save_array(os.path.join(an_dir, f'corr_{particle}_{mom}_err.npy'), cerr, logger)

    return results


# ═══════════════════════════════════════════════════════════════════
# 2. Connected 3pt/2pt ratio R(τ) from the PJN correlators
# ═══════════════════════════════════════════════════════════════════

def run_connected_ratio(corr_2pt_all, corr_3pt_all, conf_ids, run_dir, logger,
                        t_sep=None):
    """3pt/2pt ratio R(τ) for pion & proton at P0 / P2 (v20260803 style).

    Uses the z-component (γ₃) of the vector current. The full ratio formula
    with the sqrt factor is taken from ``lib.analyse.ratio_3pt``.
    """
    print_banner("Analysis 2: Connected 3pt/2pt Ratio R(τ)", logger)
    an_dir = os.path.join(run_dir, 'data', 'analysis')
    os.makedirs(an_dir, exist_ok=True)

    pairs = [
        ('proton', 'P0', 'corr_pp_P0', 'proton_P0_3pt'),
        ('proton', 'P2', 'corr_pp_P2', 'proton_P2_3pt'),
        ('pion',   'P0', 'corr_pion_P0', 'pion_P0_3pt'),
        ('pion',   'P2', 'corr_pion_P2', 'pion_P2_3pt'),
    ]
    results = {}
    for had, mom, k2, k3 in pairs:
        # γ₃ = index 3 of the gamma_mu components
        s3 = np.stack([np.real(corr_3pt_all[cid][k3][:, 3]) for cid in conf_ids])
        s2 = np.stack([np.real(corr_2pt_all[cid][k2]) for cid in conf_ids])
        # Derive t_sep from the 3pt tau dimension (Ntau-1) so the ratio matches
        # the actual source-sink separation used to build the 3pt data.
        ts = s3.shape[1] - 1 if t_sep is None else t_sep
        jk3 = Jackknife(s3, Nconf_axes=0)
        jk2 = Jackknife(s2, Nconf_axes=0)
        ratio = ratio_3pt(jk3['data_sample'], jk2['data_sample'],
                          data_2ptF_sample=None, t_sep=ts,
                          Nconf_axes=0, tau_axes=1, t_sink_axes=1)
        rm, re_ = np.real(ratio['data_mean']), np.real(ratio['data_err'])
        # Report only τ ∈ [0, ts]
        log_lines = [f"  {had} {mom}  R(τ) (t_sep={ts}, γ₃):"]
        for t in range(min(len(rm), ts + 1)):
            log_lines.append(f"    R({t:2d}) = {rm[t]:+.6f} ± {re_[t]:.6f}")
        logger.info('\n'.join(log_lines))
        results[f'{had}_{mom}'] = {'R': rm, 'R_err': re_, 't_sep': ts}
        save_array(os.path.join(an_dir, f'ratio_{had}_{mom}_mean.npy'), rm, logger)
        save_array(os.path.join(an_dir, f'ratio_{had}_{mom}_err.npy'), re_, logger)
    return results


# ═══════════════════════════════════════════════════════════════════
# 3. Disconnected gluon-PDF ratio (code_1.py style) + fits
# ═══════════════════════════════════════════════════════════════════

# ── code_1.py statistical helpers ──────────────────────────────────

def sem(data, jackknife=True):
    """Standard error of the mean over the sample axis (axis 0)."""
    error = data.std(0)
    if jackknife:
        error = error * np.sqrt(data.shape[0] - 1)
    return error


def resample(corr, jackknife=True, Nsample=None, seed=0):
    """Delete-one jackknife (or bootstrap) resampling over the config axis.

    Returns array with sample index along axis 0.
    """
    n_conf = corr.shape[0]
    if jackknife:
        return (n_conf * corr.mean(0) - corr) / (n_conf - 1)
    rng = np.random.default_rng(seed=seed)
    idx = rng.integers(0, n_conf, size=(Nsample, n_conf))
    return corr[idx].mean(1)


def cov_mat(arr, jackknife=True):
    """Jackknife covariance of the mean + eigenvalue condition number."""
    diff = arr - arr.mean(0)
    n = arr.shape[0]
    if jackknife:
        cov = np.matmul(diff.T, diff) / n * (n - 1)
    else:
        cov = np.matmul(diff.T, diff) / n
    eig = np.linalg.eigvalsh(cov)
    cond = eig[-1] / eig[0] if eig[0] > 0 else np.inf
    return cov, cond


def _model(x, p):
    """R(dt,dtau) = c0 + c1 e^{-dE·dtau} + c1 e^{-dE·(dt-dtau)}."""
    dt = np.array([_x[0] for _x in x])
    dtau = np.array([_x[1] for _x in x])
    return (np.ones(len(x)) * p["c0"]
            + p["c1"] * np.exp(-p["dE"] * dtau)
            + p["c1"] * np.exp(-p["dE"] * (dt - dtau)))


def run_disconnected_ratio(corr_2pt_all, ope_all, conf_ids, run_dir, logger,
                           dt_max=20, dt_start=7, dt_end=10, cut=6,
                           p0=None, target_momentum='P2'):
    """code_1.py-style disconnected gluon ratio + per-z correlated fits.

    For each channel (pion / proton) at the target momentum (default P2),
    combine the 2pt with the combined OPE operator:
        C3(dt,dtau,z) = C2(dt) · OPE(dtau,z)
    Jackknife-resample all three stacks, subtract the disconnected vacuum
    piece, form R = <C3_disc / C2>_ti, then fit the code_1.py model per z.

    Outputs (analysis/disconnected/):
        ratio_{ch}.npy, 0_fit_data.npz (c0,c1,dE,chi2), 1_fit_report.txt,
        ratio.png, c0.png, chi2.png
    """
    import lsqfit, gvar as gv

    print_banner("Analysis 3: Disconnected Gluon Ratio (code_1.py style)", logger)
    if p0 is None:
        p0 = {"c0": 0.6, "c1": -2, "dE": 1}

    Nconf = len(conf_ids)
    Nsample = Nconf          # jackknife: Nsample == Nconf
    jack = True
    out_dir = os.path.join(run_dir, 'analysis', 'disconnected')
    os.makedirs(out_dir, exist_ok=True)

    # Channels: use pp (proton) and pion 2pt at the target momentum
    channels = [('proton', 'corr_pp', 'proton'), ('pion', 'corr_pion', 'pion')]
    ch_results = {}

    for ch_key, k2, had_name in channels:
        logger.info(f"\n{'─' * 60}\n  Channel: {had_name} at Pz=2\n{'─' * 60}")

        # ── Build (Nconf, Nt, Nt) translation-invariant 2pt from C(dt) ──
        key2 = f'{k2}_P{target_momentum[-1]}'
        _corr = np.stack([np.real(corr_2pt_all[cid][key2]) for cid in conf_ids])
        # C(t_sink, t_src) = C((t_sink - t_src) % Nt)
        full = np.zeros((Nconf, NT, NT), dtype=np.float64)
        for ti in range(NT):
            full[:, :, ti] = np.roll(_corr, -ti, axis=1)

        # ── OPE combined: (Nconf, Nx, Nt) → transpose (Nconf, tau, z) ──
        _ope = np.stack([ope_all[cid]['combined'] for cid in conf_ids])
        _ope = _ope.transpose(0, 2, 1)   # (Nconf, tau, z)
        logger.info(f"  2pt full: {full.shape}, OPE combined: {_ope.shape}")

        # ── Relative-time construction (code_1.py) ──
        _corr2_rel = np.zeros((Nconf, NT, dt_max), dtype=np.float64)
        _ope_rel = np.zeros((Nconf, NT, dt_max, NX), dtype=np.float64)
        for ti in range(NT):
            corr2_shift = np.roll(full[:, :, ti], -ti, axis=1)
            _corr2_rel[:, ti, :] = corr2_shift[:, :dt_max]
            ope_shift = np.roll(_ope, -ti, axis=1)
            _ope_rel[:, ti, :, :] = ope_shift[:, :dt_max, :]

        # ── Disconnected 3pt = C2 × OPE (factorisation) ──
        _corr3 = np.zeros((Nconf, NT, dt_max, dt_max, NX), dtype=np.float64)
        for _dt in range(dt_max):
            for _dtau in range(_dt + 1):
                _corr3[:, :, _dt, _dtau, :] = (
                    _ope_rel[:, :, _dtau, :] * _corr2_rel[:, :, _dt][:, :, None])

        # ── Jackknife resample ──
        corr2 = resample(_corr2_rel, jack, Nsample)
        ope = resample(_ope_rel, jack, Nsample)
        corr3 = resample(_corr3, jack, Nsample)
        logger.info(f"  Resampled: corr2={corr2.shape}, ope={ope.shape}, "
                    f"corr3={corr3.shape}")

        # ── Disconnected subtraction + ratio ──
        corr3_disc = corr3 - corr2[:, :, :, None, None] * ope[:, :, None, :, :]
        eps = 1e-30
        ratio = np.mean(corr3_disc / (corr2[:, :, :, None, None] + eps), axis=1)
        ratio = ratio.real   # (Nsample, dt_max, dt_max, Nx)
        logger.info(f"  Ratio shape: {ratio.shape}, "
                    f"range=[{ratio.min():.4e}, {ratio.max():.4e}]")
        np.save(os.path.join(out_dir, f'ratio_{had_name}_P{target_momentum[-1]}.npy'),
                ratio)

        # ── Per-z correlated fit (code_1.py model) ──
        front_remove = cut // 2
        back_remove = cut - front_remove
        x_coor = [(dt, dtau)
                  for dt in range(dt_start, dt_end + 1)
                  for dtau in range(front_remove, dt - back_remove + 1)]
        Ndata = len(x_coor)
        logger.info(f"  Fit range: t_sep∈[{dt_start},{dt_end}], cut={cut}, "
                    f"Ndata={Ndata}")

        para_c0 = np.zeros((Nsample, NX))
        para_c1 = np.zeros((Nsample, NX))
        para_dE = np.zeros((Nsample, NX))
        chi2 = np.zeros((Nsample, NX))

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

        t0_fit = time.perf_counter()
        for _z in range(NX):
            sub_sample = np.zeros((Nsample, Ndata))
            for i, (dt, dtau) in enumerate(x_coor):
                sub_sample[:, i] = ratio[:, dt, dtau, _z]
            cov, cond = cov_mat(sub_sample, jack)
            report_lines += [f"z = {_z}", "-" * 56,
                             f"condition number = {cond:.3g}", ""]

            for _id in range(Nsample):
                y_coor = gv.gvar(sub_sample[_id], cov)
                _fit = lsqfit.nonlinear_fit(data=(x_coor, y_coor), p0=p0,
                                            fcn=_model, svdcut=1e-6)
                para_c0[_id, _z] = _fit.pmean["c0"]
                para_c1[_id, _z] = _fit.pmean["c1"]
                para_dE[_id, _z] = _fit.pmean["dE"]
                chi2[_id, _z] = _fit.chi2 / _fit.dof
            if _id == Nsample - 1:
                report_lines.append(_fit.format(maxline=True))
                report_lines.append("")

            logger.info(f"  z={_z}  c0={para_c0[:, _z].mean():.3g} ± "
                        f"{sem(para_c0[:, _z], jack):.3g}  "
                        f"c1={para_c1[:, _z].mean():.3g} ± "
                        f"{sem(para_c1[:, _z], jack):.3g}  "
                        f"dE={para_dE[:, _z].mean():.3g} ± "
                        f"{sem(para_dE[:, _z], jack):.3g}  "
                        f"chi2/dof={chi2[:, _z].mean():.2g}")

        # ── Summary table (code_1.py format) ──
        report_lines += ["=" * 70, "  Summary Table", "=" * 70]
        hdr = f"| {'z':>2} | {'c0':>10} | {'c1':>10} | {'dE':>10} | {'chi2/dof':>8} |"
        sep = f"|{'':->4}|{'':->12}|{'':->12}|{'':->12}|{'':->10}|"
        report_lines += [sep, hdr, sep]
        for _z in range(NX):
            report_lines.append(
                f"| {_z:2d} | {para_c0[:, _z].mean():.3f}"
                f"({sem(para_c0[:, _z], jack) * 1e3:.0f}) | "
                f"{para_c1[:, _z].mean():.3f}({sem(para_c1[:, _z], jack) * 1e3:.0f}) | "
                f"{para_dE[:, _z].mean():.3f}({sem(para_dE[:, _z], jack) * 1e3:.0f}) | "
                f"{chi2[:, _z].mean():.2g} |")
        report_lines += [sep]
        with open(os.path.join(out_dir, '1_fit_report.txt'), 'w') as f:
            f.write('\n'.join(report_lines))
        np.savez(os.path.join(out_dir, '0_fit_data.npz'),
                 c0=para_c0, c1=para_c1, dE=para_dE, chi2=chi2)

        ch_results[had_name] = {
            'ratio': ratio, 'c0': para_c0, 'c1': para_c1, 'dE': para_dE,
            'chi2': chi2, 'x_coor': x_coor,
        }
        logger.info(f"  Fit time: {time.perf_counter()-t0_fit:.1f}s")

    # ── Plots (code_1.py style) ──
    for had_name, res in ch_results.items():
        _plot_disconnected(had_name, res, out_dir, logger)
    return ch_results


def _plot_disconnected(had_name, res, out_dir, logger):
    """code_1.py-style plots: ratio.png (per-z), c0.png, chi2.png."""
    ratio = res['ratio']              # (Nsample, dt, dtau, z)
    para_c0, para_c1 = res['c0'], res['c1']
    chi2 = res['chi2']
    rm = ratio.mean(0); re_ = sem(ratio, True)

    # c0 vs z (with c1, dE, chi2 for completeness)
    z_list = list(range(NX))
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

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(z_list, chi2.mean(0), s=30)
    ax.axhline(1.0, color='orange', ls='--')
    ax.set_xlabel('z'); ax.set_ylabel('chi2/dof'); ax.set_ylim(0, 2)
    ax.set_title(f'{had_name}: chi2/dof vs z')
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, f'chi2_{had_name}.png'), dpi=150)
    plt.close(fig)

    # ratio(dt,dtau,z) for a few z
    zs = [0, 6, 12, 18]
    nrow = (len(zs) + 1) // 2
    fig, axes = plt.subplots(nrow, 2, figsize=(12, 4 * nrow), squeeze=False)
    for k, z in enumerate(zs):
        ax = axes[k // 2][k % 2]
        for dt in [8, 10, 12, 14]:
            tau = np.arange(dt + 1)
            xv = tau - dt / 2
            yv = rm[dt, :dt + 1, z] if rm.shape[0] > dt else rm[min(dt, rm.shape[0]-1), :, z]
            ye = re_[dt, :dt + 1, z]
            ax.errorbar(xv, yv, yerr=ye, fmt='x', capsize=0, label=f'dt={dt}')
        ax.set_xlabel('tau - t_sep/2'); ax.set_ylabel('R')
        ax.set_title(f'z={z}, c0={para_c0[:, z].mean():.3f}')
        ax.legend(fontsize=8); ax.grid(alpha=0.3)
    fig.suptitle(f'{had_name}: Disconnected ratio R(dt,dtau,z), Pz=2')
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, f'ratio_{had_name}.png'), dpi=150)
    plt.close(fig)
    logger.info(f"  Plots saved to {out_dir}")


# ═══════════════════════════════════════════════════════════════════
# Master plotting (meff + correlators)
# ═══════════════════════════════════════════════════════════════════

def plot_meff_results(meff_results, run_dir, logger):
    """2×2 effective-mass panels for the four channels."""
    pdir = os.path.join(run_dir, 'plots')
    os.makedirs(pdir, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    for ax, (particle, mom, key) in zip(axes.ravel(), CHANNELS):
        res = meff_results.get(f'{particle}_{mom}')
        if res is None:
            continue
        m, e = res['meff_mean'], res['meff_err']
        t = np.arange(len(m))
        ps, pe = res['plateau']
        ax.errorbar(t, m, yerr=e, fmt='o', ms=4, capsize=2)
        ax.axvspan(ps, pe - 1, alpha=0.15, color='C1')
        ax.axhline(res['E0'], color='C3', ls='--', lw=1)
        ax.axhline(res['E_exp'], color='C4', ls=':', lw=1)
        ax.set_title(f'{particle} P={mom}  E0={res["E0"]:.3f}±{res["E0_err"]:.3f} '
                     f'(exp {res["E_exp"]:.2f})')
        ax.set_xlabel('t'); ax.set_ylabel(r'$m_{\rm eff}$ [GeV]')
        ax.grid(alpha=0.3)
    fig.suptitle('Effective masses (Jackknife, 10 configs)')
    fig.tight_layout()
    out = os.path.join(pdir, 'meff_all_channels.png')
    fig.savefig(out, dpi=150)
    plt.close(fig)
    logger.info(f"  Saved {out}")


def plot_correlators(meff_results, run_dir, logger):
    """2×2 semi-log correlator panels for the four channels."""
    pdir = os.path.join(run_dir, 'plots')
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    for ax, (particle, mom, key) in zip(axes.ravel(), CHANNELS):
        res = meff_results.get(f'{particle}_{mom}')
        if res is None:
            continue
        c, ce = res['corr_mean'], res['corr_err']
        t = np.arange(len(c))
        ax.errorbar(t, np.abs(c), yerr=ce, fmt='.', ms=4, capsize=0)
        ax.set_yscale('log')
        ax.set_title(f'{particle} P={mom}  C(0)={c[0]:.4e}')
        ax.set_xlabel('t'); ax.set_ylabel('|C(t)|')
        ax.grid(alpha=0.3, which='both')
    fig.suptitle('2pt correlators (Jackknife mean)')
    fig.tight_layout()
    out = os.path.join(pdir, 'correlators_all_channels.png')
    fig.savefig(out, dpi=150)
    plt.close(fig)
    logger.info(f"  Saved {out}")


def plot_connected_ratio(ratio_results, run_dir, logger):
    """2×2 connected 3pt/2pt ratio panels."""
    pdir = os.path.join(run_dir, 'plots')
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    pairs = [('proton', 'P0'), ('proton', 'P2'), ('pion', 'P0'), ('pion', 'P2')]
    for ax, (had, mom) in zip(axes.ravel(), pairs):
        res = ratio_results.get(f'{had}_{mom}')
        if res is None:
            continue
        r, e = res['R'], res['R_err']
        tau = np.arange(len(r))
        ax.errorbar(tau, r, yerr=e, fmt='o', ms=4, capsize=2)
        ax.axhline(0, color='gray', lw=0.8)
        ax.axhline(1, color='k', ls='--', lw=0.8)
        ax.set_title(f'{had} P={mom}  R(τ)  (t_sep={res["t_sep"]})')
        ax.set_xlabel('τ'); ax.set_ylabel('R(τ)')
        ax.grid(alpha=0.3)
    fig.suptitle('Connected 3pt/2pt ratios (PJN, γ₃)')
    fig.tight_layout()
    out = os.path.join(pdir, 'ratio_3pt_all_channels.png')
    fig.savefig(out, dpi=150)
    plt.close(fig)
    logger.info(f"  Saved {out}")
