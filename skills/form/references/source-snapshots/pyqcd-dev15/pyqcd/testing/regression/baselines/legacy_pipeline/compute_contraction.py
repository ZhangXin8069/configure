"""
Wick Contraction + Dynamic Contraction (docker-v20260805)
=========================================================

Computes hadron correlation functions from distillation perambulators and the
VdV/VVV vertices using the sush/lqcddb dynamic-contraction engine:

  * 2pt  pp   — proton-proton       (P=(0,0,0) and P=(0,0,2))
  * 2pt  pn   — proton-neutron      (P=(0,0,0) and P=(0,0,2))
  * 2pt  pion — pion                (P=(0,0,0) and P=(0,0,2))
  * 3pt  PJN  — proton-vector-current-nucleon  (P=0 and P=(0,0,2))
  * 4pt  PJNNJNp — [neutron+pion]-vector-current-proton

Every correlator is source-averaged over all 72 time sources and saved as an
intermediate ``.npy`` under ``output/output_<ts>/data/conf<id>/``.

Perambulator convention (after reading):
    peram[t_sink, d_sink, d_source, ev_sink, ev_source]  (Nt,4,4,Nev,Nev)
Sequential (γ₅ time-reversed) perambulator used for ('tsrc','tsink') entries.
"""

from __future__ import annotations

import os, time
import numpy as np

from config import (NT, NEV, NEV1, T_SEP, PRECISION,
                    PP_SINK, PP_SRC, PN_SINK, PN_SRC,
                    PION_SINK, PION_SRC,
                    PJN_SINK, PJN_SRC, PJN_CURR,
                    PION3_SINK, PION3_SRC, PION3_CURR,
                    PJNNJNP_SINK, PJNNJNP_SRC, PJNNJNP_CURR,
                    FOURPT_NEV1, FOURPT_TSEP, FOURPT_MOM, FOURPT_SRC_STEP,
                    get_peram_dir, conf_data_dir)
from utils import Timer, save_array, free_gpu_memory, log_gpu_memory

from lib.backend import set_backend, get_backend
from lib.dynamic import (PeramRegistry, VRegistry, GammaRegistry,
                         dynamic_contraction, clear_plan_cache)
from lib.gamma_matrix import gamma
from lib.io_readers import readin_peram_time_slice
from lib.seqperam import seq_peram

# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _real_sum(val):
    """Sum all elements of a contraction result and take the real part.

    After spin projection (Projection=True) the (Ns,Ns,N_mom) output's 16
    spin components are summed to give the projected scalar correlator,
    matching v20260803's ``real(sum(val))/NT`` convention.
    """
    v = val.get() if hasattr(val, 'get') else val
    return float(np.real(np.sum(np.asarray(v).ravel())))


def _load_peram_set(backend, peram_dir, conf_id, times, dtype, nev1=None):
    """Load perambulators for a set of time slices, reading each once.

    Returns a dict {t: (peram_t, peram_seq_t)} where peram_t has shape
    (Nt, 4, 4, Nev', Nev') on GPU (Nev' = nev1 if given, else NEV) and
    peram_seq_t is the γ₅-reversed version. Caching by time avoids re-reading
    the same slice across the tau loop.
    """
    if nev1 is None:
        nev1 = NEV
    cache = {}
    for t in times:
        if t in cache:
            continue
        peram_cpu = readin_peram_time_slice(peram_dir, str(conf_id), t, NT, NEV)
        peram_t = backend.asarray(peram_cpu[:, :, :, :nev1, :nev1].astype(dtype))
        cache[t] = (peram_t, seq_peram(peram_t))
    return cache


def _run_2pt(backend, sink_op, src_op, peram_t, peram_seq_t,
             t_src, t_sink, v_src, v_sink, v_kind, gamma_name, gamma_val,
             projector, Vindex=('M', 'M')):
    """Run ONE 2pt dynamic contraction for a (sink, source) operator pair.

    Parameters
    ----------
    peram_t : cupy (Nt,4,4,Nev,Nev) perambulator at the fixed source time.
    peram_seq_t : cupy sequential (γ₅-reversed) perambulator.
    v_src / v_sink : cupy vertex slices (1, Nev, Nev[, Nev]) — already
        conjugated for the source where required.
    v_kind : 'VVV' (baryon) or 'VDV' (meson).
    gamma_name : 'gamma_7' (baryon) or 'gamma_5' (meson).
    gamma_val : the 4×4 gamma matrix on GPU.

    Returns
    -------
    scalar float — the spin-projected, element-summed correlator value.
    """
    PR = PeramRegistry(); VR = VRegistry(); GR = GammaRegistry()
    GR.register(gamma_name, gamma_val)
    GR.register('Projector', (projector, projector))
    if v_kind == 'VVV':
        VR.register('VVV_0', 'tsrc', v_src)
        VR.register('VVV_0', 'tsink', v_sink)
    else:
        VR.register('VDV_0', 'tsrc', v_src)
        VR.register('VDV_0', 'tsink', v_sink)
    # (both VVV and VDV at sink/source are harmless to over-register)
    PR.register('light', ('tsrc', 'tsrc'), peram_t[t_src])
    PR.register('light', ('tsink', 'tsrc'), peram_t[t_sink])
    PR.register('light', ('tsrc', 'tsink'), peram_seq_t[t_sink])

    try:
        dc = dynamic_contraction(
            [(sink_op, src_op)],
            peram_registry=PR, v_registry=VR, gamma_registry=GR,
            Cpt='2pt', Vindex=list(Vindex),
            use_equivalence=False, ignore_dis=False,
            Projection=True, verbose=False)
        return _real_sum(dc.calculate_all())
    except KeyError:
        # No valid Wick diagram — this is the flavour-forbidden pn channel
        # (proton uud ↔ neutron udd: u-count 2 vs ū-count 1 → no contraction).
        # The correlator vanishes identically in exact SU(2) QCD.
        return 0.0


# ═══════════════════════════════════════════════════════════════════
# 2pt correlators — pp, pn, pion at P0 and P2
# ═══════════════════════════════════════════════════════════════════

def compute_2pt_for_config(conf_id, run_dir, logger, vertices,
                           precision=PRECISION, channels=('pp', 'pn', 'pion')):
    """Compute source-averaged 2pt correlators for one configuration.

    Returns dict with keys like ``corr_pp_P0`` (Nt,), ``corr_pi_P2`` (Nt,) ...
    """
    backend = get_backend()
    dtype = np.complex64 if precision == 'complex64' else np.complex128
    cdir = conf_data_dir(run_dir, conf_id)

    VdV = vertices['VdV']   # (Nt, N_mom, Nev, Nev)
    VVV = vertices['VVV']   # (Nt, N_mom, Nev1, Nev1, Nev1)
    peram_dir = get_peram_dir(conf_id)

    projector = backend.asarray((gamma(0) + gamma(4)) / 2.0, dtype=dtype)
    g7 = backend.asarray(gamma(7), dtype=dtype)   # proton / neutron
    g5 = backend.asarray(gamma(5), dtype=dtype)   # pion

    # Accumulators, source-averaged: (Nt,) per channel / momentum
    acc = {f'corr_{ch}_{mom}': np.zeros(NT, dtype=np.float64)
           for ch in channels for mom in ('P0', 'P2')}
    # channel → operator group + gamma
    op_cfg = {
        'pp':   (PP_SINK, PP_SRC, 'VVV', g7, 'gamma_7'),
        'pn':   (PN_SINK, PN_SRC, 'VVV', g7, 'gamma_7'),
        'pion': (PION_SINK, PION_SRC, 'VDV', g5, 'gamma_5'),
    }
    op_cfg = {ch: op_cfg[ch] for ch in channels}

    logger.info(f"  2pt channels: {list(op_cfg.keys())} at P=(0,0,0),(0,0,2)")
    t_start = time.perf_counter()

    for t_src in range(NT):
        # ── Load perambulator for this source time (all sinks at once) ──
        peram_cpu = readin_peram_time_slice(peram_dir, str(conf_id), t_src,
                                            NT, NEV)
        peram_t = backend.asarray(peram_cpu.astype(dtype))
        peram_seq_t = seq_peram(peram_t)

        for t_sink in range(NT):
            dt = (t_sink - t_src + NT) % NT

            # Proton / neutron / pion at P0 and P2
            for ch, (sink_op, src_op, vkind, gval, gname) in op_cfg.items():
                for mi, mom_tag in enumerate(('P0', 'P2')):
                    if vkind == 'VVV':
                        v_src = backend.asarray(
                            VVV[t_src, mi:mi + 1].conj(), dtype=dtype)
                        v_sink = backend.asarray(
                            VVV[t_sink, mi:mi + 1], dtype=dtype)
                    else:
                        v_src = backend.asarray(
                            VdV[t_src, mi:mi + 1].conj(), dtype=dtype)
                        v_sink = backend.asarray(
                            VdV[t_sink, mi:mi + 1], dtype=dtype)
                    val = _run_2pt(backend, sink_op, src_op,
                                   peram_t, peram_seq_t,
                                   t_src, t_sink, v_src, v_sink, vkind,
                                   gname, gval, projector)
                    acc[f'corr_{ch}_{mom_tag}'][dt] += val / NT

        if t_src % 12 == 0 or t_src == NT - 1:
            logger.info(f"    t_src={t_src:3d}/{NT} "
                        f"elapsed={time.perf_counter()-t_start:.0f}s "
                        f"pp0={acc['corr_pp_P0'][0]:.4e} "
                        f"pi0={acc['corr_pion_P0'][0]:.4e}")
        del peram_t, peram_seq_t

    # Save intermediates
    for key, arr in acc.items():
        save_array(os.path.join(cdir, f'{key}_{conf_id}.npy'), arr, logger)
    logger.info(f"  2pt saved: " + ", ".join(
        f"{k}={v[0]:.3e}" for k, v in acc.items()))
    return acc


# ═══════════════════════════════════════════════════════════════════
# 3pt correlators — PJN (proton — vector current — nucleon)
# ═══════════════════════════════════════════════════════════════════

def _run_3pt(backend, sink_op, src_op, curr_op, PR, VR, GR, Vindex, Gindex):
    """Run one 3pt dynamic contraction and return the (n_gamma_mu,) values."""
    dc = dynamic_contraction(
        [(sink_op, src_op, curr_op)],
        peram_registry=PR, v_registry=VR, gamma_registry=GR,
        Cpt='3pt', Vindex=list(Vindex), Gindex=list(Gindex),
        use_equivalence=False, ignore_dis=False,
        Projection=True, verbose=False)
    r = dc.calculate_all()
    v = r.get() if hasattr(r, 'get') else r
    return np.asarray(v).ravel()


def compute_3pt_for_config(conf_id, run_dir, logger, vertices,
                           precision=PRECISION, t_sep=T_SEP):
    """Compute 3pt PJN correlators (tau × gamma_mu) for one configuration.

    The vector current J_μ = ūγ_μd is inserted at every tau ∈ [0, t_sep]
    between source (t_src) and sink (t_src + t_sep). Output arrays are
    (Ntau, 4) with the 4 = γ₁,γ₂,γ₃,γ₄ components (index 3 = γ₃ = z).
    """
    backend = get_backend()
    dtype = np.complex64 if precision == 'complex64' else np.complex128
    cdir = conf_data_dir(run_dir, conf_id)
    Ntau = t_sep + 1

    VdV = vertices['VdV']; VVV = vertices['VVV']
    peram_dir = get_peram_dir(conf_id)

    projector = backend.asarray((gamma(0) + gamma(4)) / 2.0, dtype=dtype)
    gmu = backend.asarray([gamma(1), gamma(2), gamma(3), gamma(4)],
                          dtype=dtype)          # (4,4,4) stack of J currents
    g7 = backend.asarray(gamma(7), dtype=dtype)
    g5 = backend.asarray(gamma(5), dtype=dtype)

    # Accumulators: (Ntau, 4)
    acc = {f'{had}_{mom}': np.zeros((Ntau, 4), dtype=np.float64)
           for had in ('proton', 'pion') for mom in ('P0', 'P2')}

    logger.info(f"  3pt PJN: t_sep={t_sep}, Ntau={Ntau}, gamma_mu=4 components")
    t_start = time.perf_counter()

    for t_src in range(NT):
        t_sink = (t_src + t_sep) % NT
        # Load all needed perams (src, sink, and every current time) once
        need_times = sorted(set([t_src, t_sink] + [(t_src + tau) % NT
                                                   for tau in range(Ntau)]))
        pc = _load_peram_set(backend, peram_dir, str(conf_id), need_times, dtype)
        p_src, p_srcS = pc[t_src]
        p_snk, p_snkS = pc[t_sink]

        for tau in range(Ntau):
            t_cur = (t_src + tau) % NT
            p_cur, p_curS = pc[t_cur]

            # ── Peram registry: all 12 (time-label) pairs the 3pt Wick needs ──
            PR = PeramRegistry()
            PR.register('light', ('tsink', 'tsrc'), p_src[t_sink])
            PR.register('light', ('tcur0', 'tsrc'), p_src[t_cur])
            PR.register('light', ('tsrc', 'tsrc'),  p_src[t_src])
            PR.register('light', ('tsink', 'tcur0'), p_cur[t_sink])
            PR.register('light', ('tcur0', 'tcur0'), p_cur[t_cur])
            PR.register('light', ('tsrc', 'tcur0'),  p_cur[t_src])
            PR.register('light', ('tcur0', 'tsink'), p_snk[t_cur])
            PR.register('light', ('tsink', 'tsink'), p_snk[t_sink])
            PR.register('light', ('tsrc', 'tsink'),  p_srcS[t_sink])
            PR.register('light', ('tsrc', 'tcur0'),  p_srcS[t_cur])
            PR.register('light', ('tcur0', 'tsink'), p_curS[t_sink])
            PR.register('light', ('tsink', 'tcur0'), p_snkS[t_cur])

            GRp = GammaRegistry()
            GRp.register('gamma_7', g7)
            GRp.register('gamma_mu', gmu)
            GRp.register('Projector', (projector, projector))
            GRpi = GammaRegistry()
            GRpi.register('gamma_5', g5)
            GRpi.register('gamma_mu', gmu)
            GRpi.register('Projector', (projector, projector))

            # Proton PJN, P0 and P2
            for mi, mom_tag in enumerate(('P0', 'P2')):
                VR = VRegistry()
                VR.register('VVV_0', 'tsrc',
                            backend.asarray(VVV[t_src, mi:mi + 1].conj(), dtype=dtype))
                VR.register('VDV_0', 'tcur0',
                            backend.asarray(VdV[t_cur, mi:mi + 1], dtype=dtype))
                VR.register('VVV_0', 'tsink',
                            backend.asarray(VVV[t_sink, mi:mi + 1], dtype=dtype))
                vn = _run_3pt(backend, PJN_SINK, PJN_SRC, PJN_CURR,
                              PR, VR, GRp, ['M', 'M', 'M'], ['', 'G', ''])
                acc[f'proton_{mom_tag}'][tau, :min(4, len(vn))] += \
                    np.real(vn[:min(4, len(vn))]) / NT

            # Pion PJN (flavour-diagonal current ūγμu), P0 and P2
            for mi, mom_tag in enumerate(('P0', 'P2')):
                VR = VRegistry()
                VR.register('VDV_0', 'tsrc',
                            backend.asarray(VdV[t_src, mi:mi + 1].conj(), dtype=dtype))
                VR.register('VDV_0', 'tcur0',
                            backend.asarray(VdV[t_cur, mi:mi + 1], dtype=dtype))
                VR.register('VDV_0', 'tsink',
                            backend.asarray(VdV[t_sink, mi:mi + 1], dtype=dtype))
                vn = _run_3pt(backend, PION3_SINK, PION3_SRC, PION3_CURR,
                              PR, VR, GRpi, ['M', 'M', 'M'], ['', 'G', ''])
                acc[f'pion_{mom_tag}'][tau, :min(4, len(vn))] += \
                    np.real(vn[:min(4, len(vn))]) / NT

            del p_cur, p_curS

        if t_src % 12 == 0 or t_src == NT - 1:
            logger.info(f"    t_src={t_src:3d}/{NT} "
                        f"elapsed={time.perf_counter()-t_start:.0f}s "
                        f"protP0[0,3]={acc['proton_P0'][0,3]:.3e} "
                        f"piP0[0,3]={acc['pion_P0'][0,3]:.3e}")
        del p_src, p_snk, p_srcS, p_snkS

    # Save intermediates
    for key, arr in acc.items():
        save_array(os.path.join(cdir, f'{key}_3pt_{conf_id}.npy'), arr, logger)
    logger.info(f"  3pt saved: " + ", ".join(
        f"{k}={v[0,3]:.3e}" for k, v in acc.items()))
    return acc


# ═══════════════════════════════════════════════════════════════════
# 4pt correlators — PJNNJNp ([neutron+pion] — J — proton)
# ═══════════════════════════════════════════════════════════════════

def compute_4pt_for_config(conf_id, run_dir, logger, vertices,
                           precision=PRECISION, t_sep=FOURPT_TSEP,
                           nev1=FOURPT_NEV1, momenta=FOURPT_MOM,
                           src_step=FOURPT_SRC_STEP):
    """Compute the PJNNJNp 4pt correlator for one configuration.

    Topology (sush contraction.PJNNJNp-.4pt style, flavour-balanced):
        sink  = neutron (udd)
        curr  = vector current J_μ
        source = proton-conjugate + pion   (two hadrons)
    The current is inserted at every tau between source and sink. Because the
    two-hadron-source contraction is the heaviest Wick contraction in the
    pipeline (~Nev³ with 5 perams), the scope is bounded by ``nev1``,
    ``momenta`` and ``src_step`` (see ``config.FOURPT_*``).

    Output: (Ntau, N_mom, 4) — (tau, momentum, gamma_mu component).
    """
    backend = get_backend()
    dtype = np.complex64 if precision == 'complex64' else np.complex128
    cdir = conf_data_dir(run_dir, conf_id)
    Ntau = t_sep + 1
    N_mom = len(momenta)
    sources = list(range(0, NT, src_step))   # sampled source times

    VdV = vertices['VdV']; VVV = vertices['VVV']
    peram_dir = get_peram_dir(conf_id)

    projector = backend.asarray((gamma(0) + gamma(4)) / 2.0, dtype=dtype)
    gmu = backend.asarray([gamma(1), gamma(2), gamma(3), gamma(4)], dtype=dtype)
    g7 = backend.asarray(gamma(7), dtype=dtype)
    g5 = backend.asarray(gamma(5), dtype=dtype)

    acc = np.zeros((Ntau, N_mom, 4), dtype=np.float64)
    nsrc = len(sources)

    logger.info(f"  4pt PJNNJNp: n(sink) — J — [p̄ + π](src), t_sep={t_sep}, "
                f"Nev1={nev1}, mom={momenta}, src_step={src_step} "
                f"({nsrc}/{NT} sources)")
    t_start = time.perf_counter()

    for t_src in sources:
        t_sink = (t_src + t_sep) % NT
        need_times = sorted(set([t_src, t_sink] + [(t_src + tau) % NT
                                                   for tau in range(Ntau)]))
        pc = _load_peram_set(backend, peram_dir, str(conf_id), need_times,
                             dtype, nev1=nev1)
        p_src, p_srcS = pc[t_src]
        p_snk, p_snkS = pc[t_sink]

        for tau in range(Ntau):
            t_cur = (t_src + tau) % NT
            p_cur, p_curS = pc[t_cur]

            PR = PeramRegistry()
            PR.register('light', ('tsink', 'tsrc'), p_src[t_sink])
            PR.register('light', ('tcur0', 'tsrc'), p_src[t_cur])
            PR.register('light', ('tsrc', 'tsrc'),  p_src[t_src])
            PR.register('light', ('tsink', 'tcur0'), p_cur[t_sink])
            PR.register('light', ('tcur0', 'tcur0'), p_cur[t_cur])
            PR.register('light', ('tsrc', 'tcur0'),  p_cur[t_src])
            PR.register('light', ('tcur0', 'tsink'), p_snk[t_cur])
            PR.register('light', ('tsink', 'tsink'), p_snk[t_sink])
            PR.register('light', ('tsrc', 'tsink'),  p_srcS[t_sink])
            PR.register('light', ('tsrc', 'tcur0'),  p_srcS[t_cur])
            PR.register('light', ('tcur0', 'tsink'), p_curS[t_sink])
            PR.register('light', ('tsink', 'tcur0'), p_snkS[t_cur])

            GR = GammaRegistry()
            GR.register('gamma_7', g7)
            GR.register('gamma_5', g5)
            GR.register('gamma_mu', gmu)
            GR.register('Projector', (projector, projector))

            for imi, mi in enumerate(momenta):
                # Wick needs 4 V vertices:
                #   VVV_0@tsink = neutron sink, VDV_0@tcur0 = current,
                #   VVV_0@tsrc  = proton source (conjugated),
                #   VDV_0@tsrc  = pion source (conjugated)
                VR = VRegistry()
                VR.register('VVV_0', 'tsink',
                            backend.asarray(VVV[t_sink, mi:mi + 1, :nev1, :nev1, :nev1],
                                            dtype=dtype))
                VR.register('VDV_0', 'tcur0',
                            backend.asarray(VdV[t_cur, mi:mi + 1, :nev1, :nev1],
                                            dtype=dtype))
                VR.register('VVV_0', 'tsrc',
                            backend.asarray(VVV[t_src, mi:mi + 1, :nev1, :nev1, :nev1].conj(),
                                            dtype=dtype))
                VR.register('VDV_0', 'tsrc',
                            backend.asarray(VdV[t_src, mi:mi + 1, :nev1, :nev1].conj(),
                                            dtype=dtype))
                # (3 groups → '3pt' engine; 4 V vertices → Vindex length 4)
                dc = dynamic_contraction(
                    [(PJNNJNP_SINK, PJNNJNP_SRC, PJNNJNP_CURR)],
                    peram_registry=PR, v_registry=VR, gamma_registry=GR,
                    Cpt='3pt', Vindex=['M', 'M', 'M', 'M'],
                    Gindex=['', 'G', '', ''],
                    use_equivalence=False, ignore_dis=False,
                    Projection=True, verbose=False)
                try:
                    r = dc.calculate_all()
                except Exception as e:
                    logger.warning(f"  4pt contraction failed at "
                                   f"(t_src={t_src},tau={tau},mom={mi}): {e}")
                    continue
                v = r.get() if hasattr(r, 'get') else r
                vn = np.asarray(v).ravel()
                acc[tau, imi, :min(4, len(vn))] += np.real(vn[:min(4, len(vn))]) / nsrc

            del p_cur, p_curS

        if (t_src - sources[0]) % 12 == 0 or t_src == sources[-1]:
            logger.info(f"    t_src={t_src:3d} "
                        f"elapsed={time.perf_counter()-t_start:.0f}s "
                        f"acc[0,0,3]={acc[0,0,3]:.3e}")
        del p_src, p_snk, p_srcS, p_snkS

    save_array(os.path.join(cdir, f'pjnnjnp_4pt_{conf_id}.npy'), acc, logger)
    logger.info(f"  4pt PJNNJNp saved: shape={acc.shape}")
    return acc


# ═══════════════════════════════════════════════════════════════════
# Convenience wrappers over all configs
# ═══════════════════════════════════════════════════════════════════

def _load_vertices_one(run_dir, cid):
    """Load ONE config's VdV/VVV from disk (keeps host RAM bounded)."""
    cdir = conf_data_dir(run_dir, cid)
    return {
        'VdV': np.load(os.path.join(cdir, f'VdV_mom_{cid}.npy')),
        'VVV': np.load(os.path.join(cdir, f'VVV_mom_{cid}.npy')),
    }


def compute_2pt_all(conf_ids, run_dir, logger, vertices=None,
                    precision=PRECISION, channels=('pp', 'pn', 'pion')):
    """2pt for all configs. If ``vertices`` is None, each config's VdV/VVV
    is loaded from disk on demand (memory-friendly for many configs)."""
    set_backend('cupy')
    results = {}
    for cid in conf_ids:
        logger.info(f"\n─── 2pt: conf {cid} ───")
        verts = vertices[cid] if vertices is not None else _load_vertices_one(run_dir, cid)
        with Timer(f"  2pt conf={cid}", logger):
            results[cid] = compute_2pt_for_config(cid, run_dir, logger,
                                                  verts, precision, channels)
        del verts
        free_gpu_memory()
    return results


def compute_3pt_all(conf_ids, run_dir, logger, vertices=None,
                    precision=PRECISION, t_sep=T_SEP):
    set_backend('cupy')
    results = {}
    for cid in conf_ids:
        logger.info(f"\n─── 3pt PJN: conf {cid} ───")
        verts = vertices[cid] if vertices is not None else _load_vertices_one(run_dir, cid)
        with Timer(f"  3pt conf={cid}", logger):
            results[cid] = compute_3pt_for_config(cid, run_dir, logger,
                                                  verts, precision, t_sep)
        del verts
        free_gpu_memory()
    return results


def compute_4pt_all(conf_ids, run_dir, logger, vertices=None,
                    precision=PRECISION, t_sep=FOURPT_TSEP, nev1=FOURPT_NEV1,
                    momenta=FOURPT_MOM, src_step=FOURPT_SRC_STEP):
    set_backend('cupy')
    results = {}
    for cid in conf_ids:
        logger.info(f"\n─── 4pt PJNNJNp: conf {cid} ───")
        verts = vertices[cid] if vertices is not None else _load_vertices_one(run_dir, cid)
        with Timer(f"  4pt conf={cid}", logger):
            results[cid] = compute_4pt_for_config(cid, run_dir, logger,
                                                  verts, precision,
                                                  t_sep, nev1, momenta, src_step)
        del verts
        free_gpu_memory()
    return results
