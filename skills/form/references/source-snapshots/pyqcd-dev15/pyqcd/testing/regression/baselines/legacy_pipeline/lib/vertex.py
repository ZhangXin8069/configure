"""
Vertex Functions: VdV and VVV
=============================

Computes vertex tensors V†DV (meson, 2-eigenvector) and VVV (baryon,
3-eigenvector) from distillation eigenvectors with momentum projection
and gauge-link transport.

Core functions:
- ``phase_exp_2pt``: Momentum phase factor e^{-ip·x} for 2pt (shape includes color)
- ``phase_exp_3pt``: Momentum phase factor e^{-ip·x} for 3pt (scalar, no color)
- ``Mom_VdV_sink_t``: Compute V_{mn}(p) = Σ_x e^{-ipx} φ_m†(x) φ_n(x)
- ``Mom_VVV_sink_t``: Compute V_{mnl}(p) = Σ_x e^{-ipx} ε_{abc} φ_m^a(x) φ_n^b(x) φ_l^c(x)

Adapted from lqcddb eigvectors/vertex.py.
"""

import numpy as np
from .backend import get_backend
from .constants import Nc, Nd
from .base_functions import cached_contract


# ═══════════════════════════════════════════════════════════════════
# Momentum Phase Factors
# ═══════════════════════════════════════════════════════════════════

def phase_exp_2pt(Nx: int, Mom: list = None):
    """Compute momentum phase factor e^{-ip·x} for 2pt functions.

    The phase factor is a 4D array with shape (Nx, Nx, Nx, Nc),
    where the color dimension (Nc) simply repeats the spatial phase.

    Parameters
    ----------
    Nx : int
        Spatial lattice size (isotropic: Nx = Ny = Nz).
    Mom : list of int, optional
        Momentum [pz, py, px] in units of 2π/L. Default [0, 0, 0].

    Returns
    -------
    ndarray, shape (Nx, Nx, Nx, Nc), dtype complex128
        e^{-i 2π p·x / Nx} replicated over color index.
    """
    backend = get_backend()
    if Mom is None:
        Mom = [0, 0, 0]

    if all(x == 0 for x in Mom):
        return backend.ones((Nx, Nx, Nx, Nc), dtype=complex)

    mom_array = backend.asarray(Mom, dtype=complex)
    factor = -2j * backend.pi / Nx

    # Create 1D coordinate arrays and broadcast via reshape
    z = backend.arange(Nx, dtype=complex)
    y = backend.arange(Nx, dtype=complex)
    x = backend.arange(Nx, dtype=complex)

    # Phase along each direction, broadcast to 3D
    z_phase = backend.exp(factor * mom_array[0] * z[:, None, None])
    y_phase = backend.exp(factor * mom_array[1] * y[None, :, None])
    x_phase = backend.exp(factor * mom_array[2] * x[None, None, :])

    # Combined 3D phase
    phase_3d = z_phase * y_phase * x_phase

    # Replicate over color dimension
    phase_exp = backend.stack([phase_3d, phase_3d, phase_3d], axis=-1)

    return phase_exp


def phase_exp_3pt(Nx: int, Mom: list = None):
    """Compute momentum phase factor e^{-ip·x} for 3pt/VVV functions.

    Returns a scalar (no color) 3D phase array. Used for VVV where
    the color structure is handled by the Levi-Civita contraction.

    Parameters
    ----------
    Nx : int
        Spatial lattice size.
    Mom : list of int, optional
        Momentum [pz, py, px] in units of 2π/L.

    Returns
    -------
    ndarray, shape (Nx, Nx, Nx), dtype complex128
        e^{-i 2π p·x / Nx}.
    """
    backend = get_backend()
    if Mom is None:
        Mom = [0, 0, 0]

    if all(x == 0 for x in Mom):
        return backend.ones(Nx ** 3, dtype=complex).reshape(Nx, Nx, Nx)

    coords = backend.arange(Nx, dtype=complex)
    zz, yy, xx = backend.meshgrid(coords, coords, coords, indexing='ij')

    dot = Mom[0] * zz + Mom[1] * yy + Mom[2] * xx
    phase_exp = backend.exp(-2j * backend.pi * dot / Nx)

    return phase_exp


# ═══════════════════════════════════════════════════════════════════
# VdV: Meson Vertex (2 eigenvectors)
# ═══════════════════════════════════════════════════════════════════

def Mom_VdV_sink_t(phase_exp, eigvecs):
    """Compute momentum-projected V†DV meson vertex.

    V_{mn}(p) = Σ_x e^{-ip·x} φ_m†(x) φ_n(x)

    Performs the contraction over all momenta at once using a single
    einsum call.

    Parameters
    ----------
    phase_exp : ndarray, shape (N_mom, V_full)
        Momentum phase factors for all momenta, flattened over spatial+color.
        ``V_full = Nx * Ny * Nz * Nc``.
    eigvecs : ndarray, shape (Nev, Nz, Ny, Nx, Nc)
        Eigenvectors at a given time slice.

    Returns
    -------
    ndarray, shape (N_mom, Nev, Nev), dtype complex128
        V_{mn}(p) for each momentum.
    """
    backend = get_backend()

    Nev = eigvecs.shape[0]
    V_full = np.prod(eigvecs.shape[1:])  # Nx*Ny*Nz*Nc

    eigvecs_flat = eigvecs.reshape(Nev, V_full)    # (Nev, V)
    eigvecs_conj = eigvecs_flat.conj()              # (Nev, V)
    phase_exp = phase_exp.reshape(-1, V_full)       # (N_mom, V)

    # V_{mn}(p) = Σ_x e^{-ipx} φ_m*(x) φ_n(x)
    VdV = cached_contract(
        'nV,MV,mV->Mnm',
        eigvecs_conj, phase_exp, eigvecs_flat
    )

    return VdV


# ═══════════════════════════════════════════════════════════════════
# VVV: Baryon Vertex (3 eigenvectors with Levi-Civita color contraction)
# ═══════════════════════════════════════════════════════════════════

def Mom_VVV_sink_t(phase_exp, eigvecs):
    """Compute momentum-projected VVV baryon vertex.

    V_{mnl}(p) = Σ_x e^{-ip·x} ε_{abc} φ_m^a(x) φ_n^b(x) φ_l^c(x)

    where ε_{abc} is the fully antisymmetric Levi-Civita tensor in
    color space, encoding the baryon's color-singlet wavefunction.

    The VVV tensor encodes the gauge-invariant combination of three
    quarks at the same spatial point, projected to a definite momentum.

    Note: The original lqcddb VVV function sums over all spatial
    directions with a shift. For simplicity and correctness, we use
    a direct Levi-Civita contraction approach that's been validated.

    Parameters
    ----------
    phase_exp : ndarray, shape (Nx, Nx, Nx)
        Momentum phase factor e^{-ip·x} (scalar, no color index).
    eigvecs : ndarray, shape (Nev, Nz, Ny, Nx, Nc)
        Eigenvectors at a given time slice. Nc=3 is the color index.

    Returns
    -------
    ndarray, shape (Nev, Nev, Nev), dtype complex128
        V_{mnl}(p) — fully antisymmetric in (m,n,l) by construction.
    """
    backend = get_backend()

    Nev = eigvecs.shape[0]
    Nx = eigvecs.shape[1]  # assuming isotropic

    # Ensure all inputs are backend arrays (cupy or numpy)
    eigvecs = backend.asarray(eigvecs)
    phase_exp = backend.asarray(phase_exp)

    # Flatten spatial indices: (Nev, Nx³, Nc)
    eigvecs_flat = eigvecs.reshape(Nev, Nx**3, Nc)

    # Phase factor: (Nx³,) — already backend array
    phase = phase_exp.reshape(-1)  # (Nx³,)

    # Levi-Civita tensor for SU(3) color: ε_{abc}
    # Build from numpy then convert to avoid element-wise assignment issues
    import numpy as np
    lc_np = np.zeros((3, 3, 3), dtype=np.complex128)
    lc_np[0, 1, 2] = 1.0
    lc_np[1, 2, 0] = 1.0
    lc_np[2, 0, 1] = 1.0
    lc_np[0, 2, 1] = -1.0
    lc_np[1, 0, 2] = -1.0
    lc_np[2, 1, 0] = -1.0
    levi_civita = backend.asarray(lc_np)

    # V_{mnl}(p) = Σ_{x,a,b,c} e^{-ipx} ε_{abc} φ_m^a(x) φ_n^b(x) φ_l^c(x)
    VVV = cached_contract(
        'x,abc,mxa,nxb,lxc->mnl',
        phase, levi_civita,
        eigvecs_flat, eigvecs_flat, eigvecs_flat
    )

    return VVV


# ═══════════════════════════════════════════════════════════════════
# Gauge link VdV (Wilson line transport)
# ═══════════════════════════════════════════════════════════════════

def VdV_sink_t_link(eigvecs, phase_exp, link_dir='0', link_max=0,
                     gauge_link=None, eigvecs_max=None, conserved=False,
                     Nx=None):
    """Compute V†DV with gauge link transport along spatial directions.

    For link_max > 0, builds gauge transport paths along the specified
    direction and computes V_{mn}(p, Δx) = Σ_x e^{-ipx} φ_m†(x) U(x→x+Δx) φ_n(x+Δx).

    Parameters
    ----------
    eigvecs : ndarray, shape (Nev, Nx, Nx, Nx, Nc)
        Eigenvectors at sink time slice.
    phase_exp : ndarray, shape (N_mom, V_full)
        Momentum phase factors.
    link_dir : str
        '0' (no link), 'X', 'Y', 'Z', 'all', or 'T' (temporal/conserved).
    link_max : int
        Maximum link displacement (positive and negative).
    gauge_link : ndarray or None
        Gauge field, shape (Nd, Nx, Nx, Nx, Nc, Nc) or None/False for no link.
    eigvecs_max : ndarray or None
        Second set of eigenvectors (for temporal/conserved current).
    conserved : bool
        Whether this is a conserved current calculation.
    Nx : int, optional
        Spatial lattice size. Auto-detected from eigvecs if None.

    Returns
    -------
    ndarray
        VDV array. Shape depends on mode:
        - No link: (N_mom, 1, Nev, Nev)
        - Conserved/temporal: (2, Nev, Nev)
        - Spatial link: (N_mom, 2*link_max+1, Nev, Nev)
    """
    backend = get_backend()

    if Nx is None:
        Nx = eigvecs.shape[1]

    eigvecs = backend.asarray(eigvecs)
    Nev = eigvecs.shape[0]
    V_full = Nx * Nx * Nx * Nc

    if phase_exp is None:
        phase_exp = backend.ones((Nx, Nx, Nx, Nc), dtype=complex)
    phase_exp = backend.asarray(phase_exp)

    eigvecs_flat = eigvecs.reshape(Nev, V_full)
    eigvecs_conj_T = eigvecs_flat.conj().T
    phase_exp = phase_exp.reshape(-1, V_full)
    N_mom = phase_exp.shape[0]

    # ── Case 1: No gauge link ──
    if gauge_link is None or isinstance(gauge_link, bool) or link_dir == '0':
        VDV = backend.zeros((N_mom, 1, Nev, Nev), dtype=complex)
        VDV[:, 0, :, :] = cached_contract(
            'VN,mV,nV->mNn',
            eigvecs_conj_T, phase_exp, eigvecs_flat
        )
        return VDV

    # ── Read gauge link ──
    gauge_link_t = backend.asarray(gauge_link.copy())
    gauge_link_t = gauge_link_t.reshape(Nd, Nx, Nx, Nx, Nc, Nc)

    # Map direction to axis
    dir_map = {'T': 0, 'Z': 1, 'Y': 2, 'X': 3, 'all': 4}
    if link_dir not in dir_map:
        raise ValueError(f"Invalid link_dir: {link_dir}")
    axis_dir = dir_map[link_dir]

    # ── Case 2: Conserved current / temporal ──
    if conserved or link_dir == 'T':
        eigvecs_max = backend.asarray(eigvecs_max)
        _gauge_link = gauge_link_t[3]  # temporal link at Nd-index 3
        glink = _gauge_link.reshape(Nx**3, Nc, Nc)
        ev_max = eigvecs_max.reshape(Nev, Nx**3, Nc)
        ev = eigvecs.reshape(Nev, Nx**3, Nc)

        VDV = backend.zeros((2, Nev, Nev), dtype=complex)
        VDV[0] = cached_contract('nvc,vcb,Nvb->nN', ev.conj(), glink, ev_max)
        VDV[1] = cached_contract('nvc,vbc,Nvb->nN', ev_max.conj(), glink.conj(), ev)
        return VDV

    # ── Case 3: Spatial directions ──
    if axis_dir == 4:  # 'all': sum over X, Y, Z
        A = 3.0
        gauge_indices = [0, 1, 2]
        roll_axes = [1, 2, 3]
    else:
        A = 1.0
        B = 3 - axis_dir  # X(3)→gauge[0], Y(2)→gauge[1], Z(1)→gauge[2]
        gauge_indices = [B]
        roll_axes = [axis_dir]

    VDV = backend.zeros((N_mom, 2 * link_max + 1, Nev, Nev), dtype=complex)
    eye3 = backend.eye(Nc, dtype=complex)

    for g_idx, roll_ax in zip(gauge_indices, roll_axes):
        _gauge_link = gauge_link_t[g_idx]

        for link_indx in range(-link_max, link_max + 1):
            eig_rolled = backend.roll(eigvecs, -link_indx, axis=roll_ax)

            if link_indx == 0:
                link_rolled = eig_rolled.reshape(Nev, Nx**3, Nc)
            else:
                gauge_path = backend.tile(eye3, (Nx**3, 1, 1))

                if link_indx < 0:
                    steps = abs(link_indx)
                    for step in range(steps):
                        shift = steps - step
                        U_shifted = backend.roll(
                            _gauge_link, shift, axis=(roll_ax - 1)
                        ).reshape(Nx**3, Nc, Nc)
                        gauge_path = gauge_path @ U_shifted
                    gauge_path = gauge_path.transpose(0, 2, 1).conj()
                else:
                    for step in range(link_indx):
                        U_shifted = backend.roll(
                            _gauge_link, -step, axis=(roll_ax - 1)
                        ).reshape(Nx**3, Nc, Nc)
                        gauge_path = gauge_path @ U_shifted

                link_rolled = cached_contract(
                    'vcb,Nvb->Nvc', gauge_path,
                    eig_rolled.reshape(Nev, Nx**3, Nc))

            link_flat = link_rolled.reshape(Nev, V_full)
            contrib = cached_contract(
                'VN,mV,nV->mNn', eigvecs_conj_T, phase_exp, link_flat)
            VDV[:, link_indx + link_max, :, :] += contrib

    return VDV / A


# ═══════════════════════════════════════════════════════════════════
# Sink-to-source conversion (Hermitian conjugation)
# ═══════════════════════════════════════════════════════════════════

def sink2src(sink, dtype='VdV'):
    """Convert sink vertex to source vertex via Hermitian conjugation.

    For VdV: source_{mn} = (sink_{nm})* = swapaxes(conj(sink), -1, -2)
    For VVV: source_{mnl} = (sink_{mnl})* = conj(sink)

    Parameters
    ----------
    sink : ndarray
        Sink-side vertex tensor.
    dtype : str
        'VdV' or 'VVV'.

    Returns
    -------
    ndarray
        Source-side vertex tensor.
    """
    backend = get_backend()
    if dtype == 'VdV':
        return backend.swapaxes(backend.asarray(sink).conj(), axis1=-1, axis2=-2)
    elif dtype == 'VVV':
        return backend.asarray(sink).conj()
    else:
        raise ValueError(f"Unknown dtype: {dtype}")
