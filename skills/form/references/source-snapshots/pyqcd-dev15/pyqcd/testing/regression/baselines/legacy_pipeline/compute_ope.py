"""
OPE — Disconnected Gluon Operator from Gauge Configurations (docker-v20260805)
===============================================================================

Computes the nonlocal gluon operator that enters the disconnected diagram of
the gluon PDF:

    O_{μν}(z) = Σ_{x⊥} Tr[ F_{μν}(x + z) · W†(z→0) · F̃_{μν}(x) · W(0→z) ]

where F̃_{μν} = ½ ε_{μνρσ} F_{ρσ} is the DUAL field strength and W is the
Wilson line along the z-direction (built by rolling the gauge links).

Algorithm: the CORRECTED donghx formulation (docker-v20260802
``compute_ope_gpu.py``):

  1. Read the ILDG .lime gauge config (big-endian float64, tail-offset scan).
  2. Compute the Clover field strength F_{μν} = -i/8 Σ_k (P_k - P_k†) with the
     4-plaquette average.
  3. Compute the dual F̃_{μν} = ½ ε_{μνρσ} F_{ρσ}.
  4. Transport F(z) back along the Wilson line, multiply by F̃(0), transport
     forward, then color-trace + sum over all spatial axes.
  5. Repeat for the (μ,ν) components used by code_1.py:
         O = -O_{30} - O_{31} + 2·O_{01}
     and save one ``ops_mu{mu}_nu{nu}_dz{delta_z}_conf{conf_id}.npz`` per
     component (key ``'ops'``, shape (delta_z, Nt)) — the exact format the
     huangcl ``code_1.py`` analysis consumes.

The OPE is momentum-independent (it is the gluon insertion) — it is combined
with the proton/pion 2pt in the analysis stage to form the disconnected 3pt.
"""

from __future__ import annotations

import os, time
import numpy as np

try:
    import cupy as cp
    HAS_CUPY = True
except ImportError:
    HAS_CUPY = False

from config import (NT, NX, DELTA_Z, Z_DIR, OPE_COMPONENTS,
                    get_gauge_path, conf_data_dir)
from utils import Timer, save_array, free_gpu_memory, log_gpu_memory


# ═══════════════════════════════════════════════════════════════════
# Tensor4 = ½ ε_{μνρσ}  (Levi-Civita, CPU, coefficient lookup)
# ═══════════════════════════════════════════════════════════════════

def build_tensor4() -> np.ndarray:
    """Build Tensor4[μ,ν,ρ,σ] = ½·ε_{μνρσ} matching donghx Operator.py."""
    T = np.zeros((4, 4, 4, 4), dtype=np.float64)
    for i in range(4):
        for j in range(4):
            a = 1.0 if i > j else 0.0
            for k in range(4):
                b = (1.0 if i > k else 0.0) + (1.0 if j > k else 0.0)
                for l in range(4):
                    c = ((1.0 if i > l else 0.0)
                         + (1.0 if j > l else 0.0)
                         + (1.0 if k > l else 0.0))
                    if len({i, j, k, l}) == 4:  # all distinct → permutation
                        T[i, j, k, l] = 1.0 if int(a + b + c) % 2 == 0 else -1.0
    return 0.5 * T


_TENSOR4_NP = build_tensor4()


# ═══════════════════════════════════════════════════════════════════
# Gauge reader (ILDG .lime)
# ═══════════════════════════════════════════════════════════════════

def _first_link_unitarity(raw: np.ndarray, Nc: int = 3) -> float:
    """Deviation |U U† − I| of the first 3×3 link in a raw float64 block."""
    U = raw[:Nc * Nc * 2].reshape(Nc, Nc, 2)
    Uc = U[..., 0] + 1j * U[..., 1]
    return float(np.abs(Uc @ Uc.conj().T - np.eye(Nc)).max())


def read_gauge_lime(filepath: str, Nt: int = NT, Nx: int = NX,
                    Nc: int = 3) -> np.ndarray:
    """Read a .lime gauge config into a complex128 (Nt,Nx,Nx,Nx,4,Nc,Nc) array.

    ILDG .lime files are big-endian float64 with an XML header AND a small
    trailing record, so the gauge data does not necessarily start at
    ``file_size - expected_bytes``. Strategy:

      1. Compute the expected gauge start ``off = file_size - expected_bytes``.
      2. If a valid (unitary) gauge is found there, use it.
      3. Otherwise scan byte offsets within ±16 KB of ``off`` (8-byte steps)
         for the first 3×3 link satisfying unitarity — this recovers the
         exact offset when a trailing record shifts the data start.
    """
    expected_elems = Nt * Nx * Nx * Nx * 4 * Nc * Nc * 2
    expected_bytes = expected_elems * 8
    file_size = os.path.getsize(filepath)
    approx_off = file_size - expected_bytes

    def _read_at(off):
        with open(filepath, 'rb') as f:
            f.seek(off)
            return np.fromfile(f, dtype='>f8', count=expected_elems)

    # ── Fast path: expected tail offset ──
    if 0 <= approx_off < file_size:
        raw = _read_at(approx_off)
        if raw.size == expected_elems and _first_link_unitarity(raw, Nc) < 1e-3:
            return _gauge_from_raw(raw, Nt, Nx, Nc)

    # ── Scan a window around the expected offset ──
    for delta in range(-16384, 16385, 8):
        off = approx_off + delta
        if off < 0 or off + expected_bytes > file_size:
            continue
        raw = _read_at(off)
        if raw.size == expected_elems and _first_link_unitarity(raw, Nc) < 1e-3:
            return _gauge_from_raw(raw, Nt, Nx, Nc)

    raise ValueError(f"No valid gauge data found in {filepath} "
                     f"(size={file_size} bytes)")


def _gauge_from_raw(raw: np.ndarray, Nt: int, Nx: int, Nc: int = 3) -> np.ndarray:
    """Reshape a raw big-endian float64 gauge block to complex (Nt,Nx,Nx,Nx,4,Nc,Nc)."""
    raw = raw.reshape(Nt, Nx, Nx, Nx, 4, Nc, Nc, 2)
    tg = raw[..., 0] + 1j * raw[..., 1]
    return tg.astype(np.complex128, copy=False)


def validate_gauge(gauge: np.ndarray, logger=None) -> dict:
    """Quick validation: unitarity of random links + mean plaquette trace."""
    rng = np.random.default_rng(42)
    Nt, Nz, Ny, Nx, Nd, Nc, _ = gauge.shape
    devs = []
    for _ in range(60):
        t = rng.integers(0, Nt); z = rng.integers(0, Nz)
        y = rng.integers(0, Ny); x = rng.integers(0, Nx)
        U = gauge[t, z, y, x, rng.integers(0, Nd)]
        devs.append(np.abs(U @ U.conj().T - np.eye(Nc)).max())
    plaq = []
    for _ in range(30):
        ti, zi, yi, xi = (rng.integers(0, Nt), rng.integers(0, Nz),
                          rng.integers(0, Ny), rng.integers(0, Nx))
        mu, nu = 1, 2
        U1 = gauge[ti, zi, yi, xi, mu]
        U2 = gauge[ti, zi, (yi + 1) % Ny, xi, nu]
        U3 = gauge[ti, zi, (yi + 1) % Ny, xi, mu].conj().T
        U4 = gauge[ti, zi, yi, xi, nu].conj().T
        plaq.append(np.trace(U1 @ U2 @ U3 @ U4))
    res = {'unitary_dev_max': float(np.max(devs)),
           'plaq_trace_mean_re': float(np.real(np.mean(plaq)))}
    if logger:
        logger.info(f"  Gauge: unitarity_dev={res['unitary_dev_max']:.2e}, "
                    f"plaq_trace_re={res['plaq_trace_mean_re']:.6f}")
    return res


# ═══════════════════════════════════════════════════════════════════
# Clover field strength F_{μν}
# ═══════════════════════════════════════════════════════════════════

def plaquette_clover_gpu(g: cp.ndarray, mu: int, nu: int) -> cp.ndarray:
    """F_{μν} = -i/8 Σ_k (P_k - P_k†) with the 4 clover leaves (donghx).

    Args:
        g : gauge on GPU, shape (Nt,Nz,Ny,Nx,4,3,3).
        mu, nu : Lorentz indices (0=t, 1=z, 2=y, 3=x), mu != nu.
    Returns:
        F_{μν} (Nt,Nz,Ny,Nx,3,3) on GPU.
    """
    e = cp.einsum
    a_mu = 3 - mu   # spatial axis of μ in (t,z,y,x)
    a_nu = 3 - nu

    g_lu = cp.roll(g, 1, axis=a_mu)
    g_rd = cp.roll(g, 1, axis=a_nu)
    g_ld = cp.roll(g_lu, 1, axis=a_nu)

    # P1 = P_{μν}
    p1 = e("tzyxab,tzyxbc->tzyxac", g[..., mu, :, :],
           cp.roll(g, -1, axis=a_mu)[..., nu, :, :])
    p1 = e("tzyxab,tzyxcb->tzyxac", p1,
           cp.roll(g, -1, axis=a_nu)[..., mu, :, :].conj())
    p1 = e("tzyxab,tzyxcb->tzyxac", p1, g[..., nu, :, :].conj())

    # P2 = P_{ν,-μ}
    p2 = e("tzyxab,tzyxcb->tzyxac",
           cp.roll(g_lu, -1, axis=a_mu)[..., nu, :, :],
           cp.roll(g_lu, -1, axis=a_nu)[..., mu, :, :].conj())
    p2 = e("tzyxab,tzyxcb->tzyxac", p2, g_lu[..., nu, :, :].conj())
    p2 = e("tzyxab,tzyxbc->tzyxac", p2, g_lu[..., mu, :, :])

    # P3 = P_{-μ,-ν}
    p3 = e("tzyxba,tzyxcb->tzyxac",
           cp.roll(g_ld, -1, axis=a_nu)[..., mu, :, :].conj(),
           g_ld[..., nu, :, :].conj())
    p3 = e("tzyxab,tzyxbc->tzyxac", p3, g_ld[..., mu, :, :])
    p3 = e("tzyxab,tzyxbc->tzyxac", p3,
           cp.roll(g_ld, -1, axis=a_mu)[..., nu, :, :])

    # P4 = P_{-ν,μ}
    p4 = e("tzyxba,tzyxbc->tzyxac", g_rd[..., nu, :, :].conj(),
           g_rd[..., mu, :, :])
    p4 = e("tzyxab,tzyxbc->tzyxac", p4,
           cp.roll(g_rd, -1, axis=a_mu)[..., nu, :, :])
    p4 = e("tzyxab,tzyxcb->tzyxac", p4,
           cp.roll(g_rd, -1, axis=a_nu)[..., mu, :, :].conj())

    tr = (0, 1, 2, 3, 5, 4)  # conjugate = Hermitian adjoint in color
    ans = (p1 - p1.conj().transpose(*tr)
           + p2 - p2.conj().transpose(*tr)
           + p3 - p3.conj().transpose(*tr)
           + p4 - p4.conj().transpose(*tr))
    return cp.array(-1j, dtype=ans.dtype) * ans / cp.array(8.0, dtype=ans.real.dtype)


def compute_dual_field_strength(F_dict: dict, mu: int, nu: int) -> cp.ndarray:
    """F̃_{μν} = ½ Σ_{ρσ} ε_{μνρσ} F_{ρσ} on GPU."""
    result = None
    for rho in range(4):
        for sigma in range(4):
            coeff = _TENSOR4_NP[mu, nu, rho, sigma]
            if abs(coeff) < 1e-10 or rho == sigma:
                continue
            F_rs = F_dict.get((rho, sigma))
            if F_rs is None:
                continue
            term = cp.array(coeff, dtype=F_rs.dtype) * F_rs
            result = term if result is None else result + term
    return result


# ═══════════════════════════════════════════════════════════════════
# OPE operator (donghx roll-based Wilson line)
# ═══════════════════════════════════════════════════════════════════

def compute_ope_donghx_gpu(gauge_gpu, mu, nu, z_dir, delta_z, Nt, Nx, logger,
                           compute_dtype=None):
    """Compute O_{μν}(z) for z = 0..delta_z-1, all time slices.

    Returns (delta_z, Nt) complex array on CPU.
    """
    if compute_dtype is None:
        compute_dtype = gauge_gpu.dtype
    if mu == nu:
        return np.zeros((delta_z, Nt), dtype=compute_dtype)

    z_axis = 3 - z_dir   # spatial axis of the Wilson-line direction

    # ── Determine which F components are needed for F̃ ──
    need_pairs = {(mu, nu)}
    for rho in range(4):
        for sigma in range(4):
            if abs(_TENSOR4_NP[mu, nu, rho, sigma]) > 1e-10 and rho != sigma:
                need_pairs.add((rho, sigma))

    F_dict = {pair: plaquette_clover_gpu(gauge_gpu, pair[0], pair[1])
              for pair in need_pairs}
    F = F_dict[(mu, nu)]
    F_tilde = compute_dual_field_strength(F_dict, mu, nu)
    del F_dict

    # Gauge link along the Wilson-line direction (z_dir): (Nt,Nz,Ny,Nx,3,3)
    U_z = gauge_gpu[..., z_dir, :, :]

    spatial_axes = (1, 2, 3)
    ope = np.zeros((delta_z, Nt), dtype=np.float64)  # real accumulator

    for zi in range(delta_z):
        if zi == 0:
            # O(0) = Σ_x Tr[ F(x) · F̃(x) ]
            ope_t = cp.einsum("tzyxab,tzyxba->tzyx", F, F_tilde)
            ope[0] = cp.asnumpy(cp.sum(ope_t, axis=spatial_axes)).real
            continue

        # F(z): roll F forward by zi along the Wilson-line axis
        ope_t = cp.roll(F, -zi, axis=z_axis)

        # Backward transport: · U†(z-1) · ... · U†(0)
        for step in range(zi):
            U_conj = cp.roll(U_z, -(zi - 1 - step), axis=z_axis).conj()
            ope_t = cp.einsum("...ab,...cb->...ac", ope_t, U_conj)

        # Multiply by F̃ at the origin
        ope_t = cp.einsum("...ab,...bc->...ac", ope_t, F_tilde)

        # Forward transport: · U(0) · ... · U(z-1)
        for step in range(zi):
            U_fwd = cp.roll(U_z, -step, axis=z_axis)
            ope_t = cp.einsum("...ab,...bc->...ac", ope_t, U_fwd)

        # Color trace + spatial sum
        trace = cp.einsum("...aa->...", ope_t)
        ope[zi] = cp.asnumpy(cp.sum(trace, axis=spatial_axes)).real

    return ope.astype(compute_dtype)


# ═══════════════════════════════════════════════════════════════════
# Per-config driver
# ═══════════════════════════════════════════════════════════════════

def compute_ope_for_config(conf_id, run_dir, logger, precision='complex64',
                           delta_z=DELTA_Z, z_dir=Z_DIR,
                           components=OPE_COMPONENTS, recompute=False):
    """Compute the three OPE components for one configuration.

    Saves ``ops_mu{mu}_nu{nu}_dz{delta_z}_conf{conf_id}.npz`` (key 'ops',
    shape (delta_z, Nt)) and returns the combined operator
    O = -O_30 - O_31 + 2·O_01 as (delta_z, Nt).
    """
    if not HAS_CUPY:
        raise RuntimeError("OPE requires a CUDA GPU (cupy)")

    dtype = np.complex64 if precision == 'complex64' else np.complex128
    cdir = conf_data_dir(run_dir, conf_id)
    paths = {c: os.path.join(cdir, f'ops_mu{c[0]}_nu{c[1]}_dz{delta_z}_conf{conf_id}.npz')
             for c in components}

    if all(os.path.exists(p) for p in paths.values()) and not recompute:
        logger.info(f"  conf={conf_id}: loading cached OPE components")
        ops = {c: np.load(paths[c])['ops'] for c in components}
        combined = -ops[(3, 0)] - ops[(3, 1)] + 2.0 * ops[(0, 1)]
        return {'components': ops, 'combined': combined}

    gauge_file = get_gauge_path(conf_id)
    logger.info(f"  conf={conf_id}: OPE from {gauge_file} "
                f"(dz={delta_z}, z_dir={z_dir}, {precision})")

    with Timer(f"  read gauge conf={conf_id}", logger):
        gauge_cpu = read_gauge_lime(gauge_file, NT, NX)
    val = validate_gauge(gauge_cpu, logger)
    gauge_gpu = cp.asarray(gauge_cpu.astype(dtype))
    del gauge_cpu

    ops = {}
    for mu, nu in components:
        with Timer(f"  OPE mu={mu},nu={nu} conf={conf_id}", logger):
            o = compute_ope_donghx_gpu(gauge_gpu, mu, nu, z_dir, delta_z,
                                       NT, NX, logger, dtype)
        ops[(mu, nu)] = o
        np.savez(paths[(mu, nu)], ops=o, mu=np.array(mu), nu=np.array(nu),
                 delta_z=np.array(delta_z), conf_id=np.array(conf_id),
                 shape=np.array(o.shape))
        logger.info(f"    saved ops_mu{mu}_nu{nu}: shape={o.shape}, "
                    f"|O|∈[{np.abs(o).min():.2e},{np.abs(o).max():.2e}]")

    combined = -ops[(3, 0)] - ops[(3, 1)] + 2.0 * ops[(0, 1)]
    save_array(os.path.join(cdir, f'ope_combined_conf{conf_id}.npy'),
               combined, logger)

    free_gpu_memory()
    log_gpu_memory(logger, " after OPE")
    return {'components': ops, 'combined': combined, 'validation': val}


def compute_ope_all(conf_ids, run_dir, logger, precision='complex64',
                    delta_z=DELTA_Z, z_dir=Z_DIR, components=OPE_COMPONENTS,
                    recompute=False) -> dict:
    """Compute OPE for every configuration."""
    results = {}
    for cid in conf_ids:
        logger.info(f"\n─── OPE: conf {cid} ───")
        results[cid] = compute_ope_for_config(cid, run_dir, logger, precision,
                                              delta_z, z_dir, components,
                                              recompute)
    return results
