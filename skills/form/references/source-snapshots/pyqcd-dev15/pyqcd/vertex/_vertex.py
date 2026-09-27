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

import math
import operator
from contextlib import nullcontext

import numpy as np
from ..tools._backend import get_backend, get_backend_name
from ..lattice._constants import Nc, Nd
from ..tools._base import cached_contract


# ═══════════════════════════════════════════════════════════════════
# Momentum Phase Factors
# ═══════════════════════════════════════════════════════════════════

def phase_exp_2pt(Nx=None, Mom: list = None, lattice_shape=None):
    """Compute momentum phase factor e^{-ip·x} for 2pt functions.

    The phase factor is a 4D array with shape (Lz, Ly, Lx, Nc),
    where the color dimension (Nc) simply repeats the spatial phase.

    Parameters
    ----------
    Nx : int or tuple of int, optional
        Legacy isotropic size, or the spatial shape ``(Lz, Ly, Lx)``.
        When omitted, ``lattice_shape`` must be supplied.
    Mom : sequence of real, optional
        Momentum [pz, py, px] in units of 2π/L. Default [0, 0, 0].
    lattice_shape : tuple of int, optional
        Explicit spatial shape ``(Lz, Ly, Lx)``. This is an alternative to
        passing the shape as ``Nx``.

    Returns
    -------
    ndarray, shape (Lz, Ly, Lx, Nc), dtype complex128
        e^{-i 2π (pz*z/Lz + py*y/Ly + px*x/Lx)} replicated over color.
    """
    backend = get_backend()
    shape = _resolve_phase_shape(Nx, lattice_shape)
    momentum = _validate_momentum((0, 0, 0) if Mom is None else Mom)
    lz, ly, lx = shape

    if np.all(momentum == 0.0):
        return backend.ones((lz, ly, lx, Nc), dtype=complex)

    mom_array = backend.asarray(momentum, dtype=complex)

    # Create 1D coordinate arrays and broadcast via reshape
    z = backend.arange(lz, dtype=complex)
    y = backend.arange(ly, dtype=complex)
    x = backend.arange(lx, dtype=complex)

    # Phase along each direction, broadcast to 3D
    z_phase = backend.exp(
        (-2j * backend.pi / lz) * mom_array[0] * z[:, None, None])
    y_phase = backend.exp(
        (-2j * backend.pi / ly) * mom_array[1] * y[None, :, None])
    x_phase = backend.exp(
        (-2j * backend.pi / lx) * mom_array[2] * x[None, None, :])

    # Combined 3D phase
    phase_3d = z_phase * y_phase * x_phase

    # Replicate over color dimension
    phase_exp = backend.stack([phase_3d] * Nc, axis=-1)

    return phase_exp


def phase_exp_3pt(Nx=None, Mom: list = None, lattice_shape=None):
    """Compute momentum phase factor e^{-ip·x} for 3pt/VVV functions.

    Returns a scalar (no color) 3D phase array. Used for VVV where
    the color structure is handled by the Levi-Civita contraction.

    Parameters
    ----------
    Nx : int or tuple of int, optional
        Legacy isotropic size, or the spatial shape ``(Lz, Ly, Lx)``.
        When omitted, ``lattice_shape`` must be supplied.
    Mom : sequence of real, optional
        Momentum [pz, py, px] in units of 2π/L.
    lattice_shape : tuple of int, optional
        Explicit spatial shape ``(Lz, Ly, Lx)``. This is an alternative to
        passing the shape as ``Nx``.

    Returns
    -------
    ndarray, shape (Lz, Ly, Lx), dtype complex128
        e^{-i 2π (pz*z/Lz + py*y/Ly + px*x/Lx)}.
    """
    backend = get_backend()
    shape = _resolve_phase_shape(Nx, lattice_shape)
    momentum = _validate_momentum((0, 0, 0) if Mom is None else Mom)
    lz, ly, lx = shape

    if np.all(momentum == 0.0):
        return backend.ones(shape, dtype=complex)

    mom_array = backend.asarray(momentum, dtype=complex)
    z = backend.arange(lz, dtype=complex)
    y = backend.arange(ly, dtype=complex)
    x = backend.arange(lx, dtype=complex)
    z_phase = backend.exp(
        (-2j * backend.pi / lz) * mom_array[0] * z[:, None, None])
    y_phase = backend.exp(
        (-2j * backend.pi / ly) * mom_array[1] * y[None, :, None])
    x_phase = backend.exp(
        (-2j * backend.pi / lx) * mom_array[2] * x[None, None, :])

    return z_phase * y_phase * x_phase


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
    backend_name = get_backend_name()
    eigvecs = _coerce_active_array(eigvecs, backend, backend_name)
    phase_exp = _coerce_active_array(phase_exp, backend, backend_name)
    if phase_exp.dtype != eigvecs.dtype:
        phase_exp = backend.asarray(phase_exp, dtype=eigvecs.dtype)

    Nev = eigvecs.shape[0]
    V_full = math.prod(eigvecs.shape[1:])  # Lz*Ly*Lx*Nc

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
    backend_name = get_backend_name()

    eigvecs = _coerce_active_array(eigvecs, backend, backend_name)
    phase_exp = _coerce_active_array(phase_exp, backend, backend_name)
    if phase_exp.dtype != eigvecs.dtype:
        phase_exp = backend.asarray(phase_exp, dtype=eigvecs.dtype)
    Nev, Nz, Ny, Nx = eigvecs.shape[:4]
    # phase 折叠为 (-1,Nz,Ny,Nx)，保持活动 backend/device。
    phase_exp = phase_exp.reshape(-1, Nz, Ny, Nx)
    num_Mom = phase_exp.shape[0]

    def _contract(ph, e0, e1, e2):
        return cached_contract('Mzyx,azyx,bzyx,czyx->Mabc',
                               ph, e0, e1, e2)

    # 参照按 z 切片循环累加；数学上等价于全格点一次求和（仅浮点求和序差异）
    e = [eigvecs[..., c] for c in range(3)]
    VVV = (_contract(phase_exp, e[0], e[1], e[2])
           + _contract(phase_exp, e[1], e[2], e[0])
           + _contract(phase_exp, e[2], e[0], e[1])
           - _contract(phase_exp, e[0], e[2], e[1])
           - _contract(phase_exp, e[1], e[0], e[2])
           - _contract(phase_exp, e[2], e[1], e[0]))

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


def perm_comb(N, M=1, dtype='perm', renormal=False):
    """排列/组合数（照抄 sush vertex_creator.perm_comb，类方法转函数）。"""
    import numpy as _npx

    if (renormal is False and M >= 0) or (renormal is True and M >= 1):
        if dtype == 'perm':
            return float(_npx.prod([N - x for x in range(len([N] * M))]))
        if dtype == 'comb':
            return float(
                _npx.prod([N - x for x in range(len([N] * M))])
                / _npx.prod([x for x in range(1, M + 1, 1)]))
    if M <= 0 and renormal is True:
        return perm_comb(N=N, M=1, dtype=dtype, renormal=False)
    raise ValueError('mistake')


def _positive_index(value, name):
    """Return a strictly positive integer lattice extent."""
    if isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be a positive integer, not bool")
    try:
        result = operator.index(value)
    except TypeError as exc:
        raise TypeError(f"{name} must be a positive integer") from exc
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return int(result)


def _host_array(value, name):
    """Make a host view for validation without producing computation output."""
    if isinstance(value, np.ndarray):
        return value
    if hasattr(value, "detach") and hasattr(value, "cpu"):
        try:
            return value.detach().cpu().numpy()
        except (AttributeError, TypeError, ValueError) as exc:
            raise TypeError(f"{name} must be an array-like real vector") from exc
    if hasattr(value, "get") and hasattr(value, "shape"):
        try:
            return np.asarray(value.get())
        except (AttributeError, TypeError, ValueError) as exc:
            raise TypeError(f"{name} must be an array-like real vector") from exc
    try:
        return np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} must be an array-like real vector") from exc


def _contains_bool(value):
    """Catch bool elements before NumPy can widen a mixed Python sequence."""
    if isinstance(value, (bool, np.bool_)):
        return True
    if isinstance(value, (list, tuple)):
        return any(_contains_bool(item) for item in value)
    return False


def _validate_momentum(momentum):
    """Validate and return momentum as finite float64 ``(pz, py, px)``."""
    if _contains_bool(momentum):
        raise TypeError("momentum must contain finite real numbers, not bool")
    values = _host_array(momentum, "momentum")
    if values.ndim != 1 or values.shape != (3,):
        raise ValueError("momentum must have exactly three entries (pz, py, px)")
    if values.dtype.kind == "b":
        raise TypeError("momentum must contain finite real numbers, not bool")
    if values.dtype.kind == "c":
        raise TypeError("momentum must contain real, not complex, numbers")
    if values.dtype.kind not in "iu f":
        raise TypeError("momentum must contain finite real numbers")
    try:
        values = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise TypeError("momentum must contain finite real numbers") from exc
    if not np.all(np.isfinite(values)):
        raise ValueError("momentum must contain finite real numbers")
    return values


def _validate_lattice_shape(lattice_shape):
    """Validate an explicit ``(Lz, Ly, Lx)`` shape."""
    if isinstance(lattice_shape, (str, bytes)):
        raise TypeError("lattice_shape must contain exactly three extents")
    try:
        shape = tuple(lattice_shape)
    except TypeError as exc:
        raise TypeError("lattice_shape must contain exactly three extents") from exc
    if len(shape) != 3:
        raise ValueError("lattice_shape must contain exactly three extents")
    return tuple(_positive_index(value, "lattice_shape extent") for value in shape)


def _resolve_phase_shape(Nx=None, lattice_shape=None):
    """Resolve legacy scalar ``Nx`` or explicit spatial shape."""
    if lattice_shape is None:
        if Nx is None:
            raise TypeError("Nx or lattice_shape must be supplied")
        try:
            nx = _positive_index(Nx, "Nx")
        except TypeError:
            return _validate_lattice_shape(Nx)
        return (nx, nx, nx)

    shape = _validate_lattice_shape(lattice_shape)
    if Nx is None:
        return shape
    try:
        nx = _positive_index(Nx, "Nx")
    except TypeError:
        legacy_shape = _validate_lattice_shape(Nx)
        if legacy_shape != shape:
            raise ValueError(
                "Nx and lattice_shape specify different spatial shapes")
    else:
        if shape != (nx, nx, nx):
            raise ValueError(
                "Nx and lattice_shape specify different spatial shapes")
    return shape


def _exact_cubic_extent(volume):
    """Return the integer cube root only when ``volume`` is exactly cubic."""
    if volume <= 0:
        return None
    guess = max(1, int(round(volume ** (1.0 / 3.0))))
    for extent in range(max(1, guess - 2), guess + 3):
        if extent ** 3 == volume:
            return extent
    return None


def _coerce_active_array(value, backend, backend_name):
    """Convert input to the active backend while retaining its native dtype."""
    if backend_name == "torch":
        # A Tensor already has an authoritative device.  Do not silently move
        # it to the globally configured device; NumPy/CuPy inputs still follow
        # the Torch adapter's configured device through ``backend.asarray``.
        try:
            import torch
        except ImportError:  # pragma: no cover - active torch implies import
            torch = None
        if torch is not None and isinstance(value, torch.Tensor):
            return value
        return backend.asarray(value)
    if backend_name == "numpy":
        # NumPy forbids implicit conversion of CuPy arrays and may refuse a
        # Torch tensor requiring grad.  Explicit host conversion is confined
        # to the NumPy-active case, where CPU output is the requested backend.
        if hasattr(value, "detach") and hasattr(value, "cpu"):
            return np.asarray(value.detach().cpu().numpy())
        if hasattr(value, "get") and hasattr(value, "shape"):
            return np.asarray(value.get())
    if backend_name == "cupy":
        try:
            return backend.asarray(value)
        except (TypeError, ValueError):
            if hasattr(value, "detach") and hasattr(value, "cpu"):
                return backend.asarray(value.detach().cpu().numpy())
            raise
    return backend.asarray(value)


def _is_supported_complex_dtype(dtype):
    """Accept exactly complex64/complex128, with no implicit promotion."""
    if getattr(dtype, "is_complex", False):
        name = str(dtype)
        return name.endswith("complex64") or name.endswith("complex128")
    try:
        dtype = np.dtype(dtype)
    except TypeError:
        return False
    return dtype in (np.dtype(np.complex64), np.dtype(np.complex128))


def _backend_asarray(backend, value, *, dtype=None, device=None,
                     backend_name=None):
    """Call the common ``asarray`` API without NumPy's device keyword."""
    if backend_name == "torch":
        return backend.asarray(value, dtype=dtype, device=device)
    return backend.asarray(value, dtype=dtype)


def _backend_arange(backend, stop, *, dtype, device=None, backend_name=None):
    """Call the common ``arange`` API without NumPy's device keyword."""
    if backend_name == "torch":
        return backend.arange(stop, dtype=dtype, device=device)
    return backend.arange(stop, dtype=dtype)


def _phase_device_context(eigvecs, backend_name):
    """Select an existing CuPy device for all temporary phase arrays."""
    if backend_name != "cupy":
        return nullcontext()
    try:
        import cupy as cp
        return cp.cuda.Device(eigvecs.device.id)
    except (AttributeError, ImportError):  # pragma: no cover - active CuPy
        return nullcontext()


def _resolve_eigvec_shape(eigvecs, lattice_shape):
    """Validate eigvec rank and resolve its spatial ``(Lz, Ly, Lx)`` shape."""
    if eigvecs.ndim not in (3, 5):
        raise ValueError(
            "eigvecs must have shape (Nev,Nz,Ny,Nx,Nc) or (Nev,V,Nc)")
    if eigvecs.shape[0] <= 0 or eigvecs.shape[-1] <= 0:
        raise ValueError("eigvecs Nev and Nc dimensions must be positive")

    if eigvecs.ndim == 5:
        inferred = tuple(_positive_index(size, "eigvecs spatial extent")
                         for size in eigvecs.shape[1:4])
        if lattice_shape is None:
            return inferred
        explicit = _validate_lattice_shape(lattice_shape)
        if explicit != inferred:
            raise ValueError(
                "lattice_shape does not match eigvecs (Nz, Ny, Nx)")
        return explicit

    volume = _positive_index(eigvecs.shape[1], "eigvecs spatial volume")
    if lattice_shape is None:
        extent = _exact_cubic_extent(volume)
        if extent is None:
            raise ValueError(
                "flattened eigvecs require lattice_shape unless V is an exact cube")
        return (extent, extent, extent)
    explicit = _validate_lattice_shape(lattice_shape)
    if math.prod(explicit) != volume:
        raise ValueError("lattice_shape volume does not match flattened eigvecs")
    return explicit


def apply_momentum_smearing(eigvecs, momentum, lattice_shape=None):
    """Apply a spatial momentum-smearing phase to distillation eigenvectors.

    The phase is

    ``exp[-i 2*pi*(pz*z/Lz + py*y/Ly + px*x/Lx)]``

    with coordinates ordered as ``(z, y, x)`` and momentum ordered as
    ``(pz, py, px)``.  This is an eigenvector-local phase multiplication; it
    is distinct from a sink momentum projection or a VdV/VVV contraction.

    Parameters
    ----------
    eigvecs : backend array, complex64 or complex128
        Either ``(Nev, Nz, Ny, Nx, Nc)`` or flattened ``(Nev, V, Nc)``.
    momentum : array-like, shape (3,)
        Signed finite Fourier mode numbers ``(pz, py, px)``.  The physical
        lattice momentum is ``a*p_i = 2*pi*momentum_i/L_i``.
    lattice_shape : tuple of int, optional
        ``(Lz, Ly, Lx)`` for flattened input.  A five-dimensional input must
        agree with its spatial axes.  It may be omitted only for exact cubic
        flattened volumes.

    Returns
    -------
    backend array
        Same shape, complex dtype, backend and (where applicable) device as
        the active computation/input backend.

    Raises
    ------
    TypeError, ValueError
        For bool/complex/non-finite momentum, malformed shapes, non-complex
        eigenvectors, unsupported complex precision, or shape mismatches.
    """
    backend = get_backend()
    backend_name = get_backend_name()
    eigvecs = _coerce_active_array(eigvecs, backend, backend_name)
    if not _is_supported_complex_dtype(getattr(eigvecs, "dtype", None)):
        raise TypeError("eigvecs dtype must be complex64 or complex128")
    momentum = _validate_momentum(momentum)
    shape = _resolve_eigvec_shape(eigvecs, lattice_shape)

    # Keep a directly supplied Torch tensor's device.  NumPy/CuPy inputs are
    # already placed by the active backend adapter.
    device = getattr(eigvecs, "device", None) if backend_name == "torch" else None
    if np.all(momentum == 0.0):
        return eigvecs

    complex_dtype = eigvecs.dtype
    real_dtype = np.float32 if str(complex_dtype).endswith("64") else np.float64
    momentum_backend = _backend_asarray(
        backend, momentum.astype(real_dtype, copy=False), dtype=real_dtype,
        device=device, backend_name=backend_name)

    lz, ly, lx = shape
    with _phase_device_context(eigvecs, backend_name):
        z = _backend_arange(backend, lz, dtype=real_dtype, device=device,
                            backend_name=backend_name)
        y = _backend_arange(backend, ly, dtype=real_dtype, device=device,
                            backend_name=backend_name)
        x = _backend_arange(backend, lx, dtype=real_dtype, device=device,
                            backend_name=backend_name)
        angle = (
            momentum_backend[0] * z[:, None, None] / lz
            + momentum_backend[1] * y[None, :, None] / ly
            + momentum_backend[2] * x[None, None, :] / lx
        )
        phase_argument = _backend_asarray(
            backend, angle, dtype=complex_dtype, device=device,
            backend_name=backend_name)
        # Do not pass a Python complex scalar through the Torch adapter:
        # ``torch.as_tensor(complex_scalar)`` starts at complex64 and a later
        # cast to complex128 cannot recover the lost digits of pi.
        coefficient_host_dtype = (
            np.complex64 if str(complex_dtype).endswith("64")
            else np.complex128)
        coefficient = _backend_asarray(
            backend,
            np.asarray([-2j * np.pi], dtype=coefficient_host_dtype),
            dtype=complex_dtype, device=device, backend_name=backend_name)[0]
        phase = backend.exp(phase_argument * coefficient)
        phase = _backend_asarray(
            backend, phase, dtype=complex_dtype, device=device,
            backend_name=backend_name)

    if eigvecs.ndim == 5:
        phase = phase.reshape((1, lz, ly, lx, 1))
    else:
        phase = phase.reshape((1, lz * ly * lx, 1))
    return eigvecs * phase


def momsmear_phase(Nx: int, Mom):
    """Return the legacy NumPy phase ``e^{-i2π Mom·Pos/Nx}``.

    ``Pos=(z,y,x)`` and the returned contiguous vector uses
    ``z*Nx**2 + y*Nx + x``.  This compatibility helper intentionally always
    returns a NumPy complex128 array; use :func:`apply_momentum_smearing` for
    active-backend eigenvector multiplication and rectangular lattices.
    """
    nx = _positive_index(Nx, "Nx")
    momentum = _validate_momentum(Mom)
    z, y, x = np.indices((nx, nx, nx), dtype=np.float64)
    pos_dot = (z * momentum[0] + y * momentum[1] + x * momentum[2]) / nx
    flat = np.exp(np.asarray(-2j * np.pi * pos_dot, dtype=np.complex128))
    return np.ascontiguousarray(flat.reshape(-1), dtype=np.complex128)
