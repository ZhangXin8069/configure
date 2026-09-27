"""
Vertex Functions — VdV and VVV (docker-v20260805)
==================================================

Computes the momentum-projected distillation vertices on the GPU:

    VdV_{mn}(P, t) = Σ_x e^{-iP·x} φ†_m(x,t) φ_n(x,t)      (meson vertex)
    VVV_{abc}(P,t) = Σ_x e^{-iP·x} ε_{abc} φ^a_m φ^b_n φ^c_l  (baryon vertex)

Implementation notes
--------------------
* Eigenvectors are read per time slice from the cluster binary files
  (complex128 on disk) and cast to the compute precision (complex64 default).
* Vertices are computed one time slice at a time and streamed to a CPU
  accumulator to bound GPU memory (the VVV full array is (Nt, Nmom, Nev, Nev, Nev)
  ≈ 1.1 GB for Nev=100 at complex64 — held on CPU RAM, one (Nmom,Nev,Nev,Nev)
  slice ≈ 160 MB on GPU).
* Momentum phases follow the [Pz, Py, Px] (z-fastest) convention.

The output arrays match the shapes consumed by the contraction engine:
    VdV : (Nt, N_mom, Nev, Nev)          complex64
    VVV : (Nt, N_mom, Nev, Nev, Nev)     complex64
"""

from __future__ import annotations

import os, time
import numpy as np

from config import (NX, NT, NEV, NEV1, MOM_SINK_VDV, MOM_SINK_VVV,
                    get_eigen_path, conf_data_dir)
from utils import Timer, save_array, free_gpu_memory, log_gpu_memory

from lib.backend import set_backend, get_backend
from lib.vertex import phase_exp_2pt, phase_exp_3pt, Mom_VdV_sink_t


def _compute_vvv_single_t_gpu(ev_t_gpu, ph_gpu, Nx, Nev1):
    """VVV for ONE time slice — memory-efficient x-slicing factorization.

    Adopted from docker-v20260804 (which is ~20× faster than the single
    einsum 'x,abc,mxa,nxb,lxc->mnl' for the same flops). For each x-slice
    of (Nev1, Nx², 3) eigenvectors, contracts the two first color entries
    into an intermediate (a,b,x) then contracts the third color:

        VVV += Σ_{x∈slice} e^{-ipx} ε_{abc} φ^a_m φ^b_n φ^c_l

    All six Levi-Civita permutations are accumulated with their signs.
    """
    backend = get_backend()
    VVV_t = backend.zeros((Nev1, Nev1, Nev1), dtype=ev_t_gpu.dtype)
    L = Nx * Nx                       # sites per x-slice
    for xi in range(Nx):
        s, e = xi * L, (xi + 1) * L
        es = ev_t_gpu[:Nev1, s:e, :]  # (Nev1, Nx², 3)
        ps = ph_gpu[s:e]              # (Nx²,)
        # Even (cyclic) permutations — ε sign +1
        T = backend.einsum('x,ax,bx->abx', ps, es[..., 0], es[..., 1])
        VVV_t += backend.einsum('abx,cx->abc', T, es[..., 2])
        T = backend.einsum('x,ax,bx->abx', ps, es[..., 1], es[..., 2])
        VVV_t += backend.einsum('abx,cx->abc', T, es[..., 0])
        T = backend.einsum('x,ax,bx->abx', ps, es[..., 2], es[..., 0])
        VVV_t += backend.einsum('abx,cx->abc', T, es[..., 1])
        # Odd (anti-cyclic) permutations — ε sign -1
        T = backend.einsum('x,ax,bx->abx', ps, es[..., 0], es[..., 2])
        VVV_t -= backend.einsum('abx,cx->abc', T, es[..., 1])
        T = backend.einsum('x,ax,bx->abx', ps, es[..., 1], es[..., 0])
        VVV_t -= backend.einsum('abx,cx->abc', T, es[..., 2])
        T = backend.einsum('x,ax,bx->abx', ps, es[..., 2], es[..., 1])
        VVV_t -= backend.einsum('abx,cx->abc', T, es[..., 0])
    return VVV_t


def compute_vertices_for_config(conf_id: int, run_dir: str, logger,
                                precision: str = 'complex64',
                                recompute: bool = False) -> dict:
    """Compute (or load cached) VdV/VVV for one configuration.

    Parameters
    ----------
    conf_id : int
        Configuration ID.
    run_dir : str
        Output run directory (data/conf{id}/ receives the vertices).
    logger : logging.Logger
        Logger for progress output.
    precision : str
        'complex64' (single, default) or 'complex128' (double).
    recompute : bool
        Force recomputation even if cached files exist.

    Returns
    -------
    dict with keys 'VdV' (Nt, N_mom, Nev, Nev) and 'VVV' (Nt, N_mom, Nev, Nev, Nev).
    """
    backend = get_backend()
    dtype = np.complex64 if precision == 'complex64' else np.complex128

    cdir = conf_data_dir(run_dir, conf_id)
    vdv_path = os.path.join(cdir, f'VdV_mom_{conf_id}.npy')
    vvv_path = os.path.join(cdir, f'VVV_mom_{conf_id}.npy')

    # ── Load cache if present and the user does not force recompute ──
    if os.path.exists(vdv_path) and os.path.exists(vvv_path) and not recompute:
        VdV = np.load(vdv_path)
        VVV = np.load(vvv_path)
        logger.info(f"  conf={conf_id}: loaded cached vertices "
                    f"VdV{VdV.shape} VVV{VVV.shape}")
        return {'VdV': VdV, 'VVV': VVV}

    logger.info(f"  conf={conf_id}: computing vertices over {NT} time slices "
                f"(VdV {len(MOM_SINK_VDV)} mom, VVV {len(MOM_SINK_VVV)} mom, "
                f"Nev={NEV}, Nev1={NEV1}, dtype={dtype.__name__})")

    # ── Momentum phase factors (identical for every config/time slice) ──
    # phase_exp_2pt has shape (Nx,Nx,Nx,Nc) → flattened to (V_full,) per momentum.
    # Note: under the cupy backend phase_exp_* return GPU arrays — move to CPU.
    p2f = np.zeros((len(MOM_SINK_VDV), NX * NX * NX * 3), dtype=np.complex128)
    for i, mom in enumerate(MOM_SINK_VDV):
        _ph = phase_exp_2pt(NX, mom)
        _ph_np = _ph.get() if hasattr(_ph, 'get') else np.asarray(_ph)
        p2f[i] = _ph_np.reshape(-1)
    p2f_gpu = backend.asarray(p2f.astype(dtype))
    # VVV phases are color-free (Nx,Nx,Nx).
    p3_list = []
    for mom in MOM_SINK_VVV:
        _ph = phase_exp_3pt(NX, mom)
        p3_list.append(_ph.get() if hasattr(_ph, 'get') else np.asarray(_ph))

    # ── Streaming per time slice ─────────────────────────────────────
    VdV = np.zeros((NT, len(MOM_SINK_VDV), NEV, NEV), dtype=dtype)
    VVV = np.zeros((NT, len(MOM_SINK_VVV), NEV1, NEV1, NEV1), dtype=dtype)

    from lib.io_readers import readin_eigvecs_gpu
    t0 = time.perf_counter()
    for t in range(NT):
        # Eigvecs: (Nev, Nx³, Nc) complex128 on GPU → reshape (Nev,Nx,Nx,Nx,Nc)
        ev = readin_eigvecs_gpu(get_eigen_path(conf_id, t), NX, NEV)
        ev = ev.reshape(NEV, NX, NX, NX, 3).astype(dtype)
        # VdV: single einsum 'nV,MV,mV->Mnm' over all momenta
        vdv_t = Mom_VdV_sink_t(p2f_gpu, ev)
        VdV[t] = vdv_t.get() if hasattr(vdv_t, 'get') else vdv_t
        # VVV: one momentum at a time (x-slicing factorization — fast + memory-lean)
        ev_flat = ev.reshape(NEV, NX * NX * NX, 3)
        for m, ph_np in enumerate(p3_list):
            ph_gpu = backend.asarray(ph_np.reshape(-1).astype(dtype))
            vvv_t = _compute_vvv_single_t_gpu(ev_flat, ph_gpu, NX, NEV1)
            VVV[t, m] = vvv_t.get() if hasattr(vvv_t, 'get') else vvv_t
        if t % 12 == 0 or t == NT - 1:
            logger.info(f"    t={t:3d}/{NT}  elapsed={time.perf_counter()-t0:.0f}s")

    free_gpu_memory()
    log_gpu_memory(logger, " after vertices")

    # Sanity: at P=0 the VdV diagonal should be ≈ 1 (orthonormal eigenvectors).
    diag = np.abs(np.diag(VdV[0, 0])).real
    logger.info(f"    VdV(P=0,t=0) diagonal: [{diag.min():.3f}, {diag.max():.3f}]  "
                f"(≈1 ⇒ orthonormal)")
    logger.info(f"    VVV(P=0,t=0) |v|: [{np.abs(VVV[0,0]).min():.3e}, "
                f"{np.abs(VVV[0,0]).max():.3e}]")

    save_array(vdv_path, VdV, logger)
    save_array(vvv_path, VVV, logger)
    logger.info(f"    Saved VdV{VdV.shape} VVV{VVV.shape} for conf={conf_id}")

    return {'VdV': VdV, 'VVV': VVV}


def compute_all_vertices(conf_ids, run_dir, logger, precision='complex64',
                         recompute=False) -> dict:
    """Compute VdV/VVV for every configuration.

    Each config's vertices are saved to disk; the returned dict is empty so
    that the (≈1.15 GB/config) arrays are NOT retained in host RAM.
    """
    set_backend('cupy')
    for cid in conf_ids:
        with Timer(f"  Vertices conf={cid}", logger):
            compute_vertices_for_config(cid, run_dir, logger, precision, recompute)
        free_gpu_memory()
    logger.info(f"Vertices computed & saved for {len(conf_ids)} configs")
    return {}
