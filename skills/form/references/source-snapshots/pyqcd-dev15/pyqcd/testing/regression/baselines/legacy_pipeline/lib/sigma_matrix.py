"""
Pauli (Sigma) Matrices
======================

Pauli matrices σ₀, σ₁, σ₂, σ₃ in the standard representation.
Provides ``sigma(i)`` and momentum-contracted variants.

Adapted from lqcddb constant/sigma_matrix.py.
"""

import numpy as np
from .backend import get_backend

# ── Pauli matrices in standard representation ──────────────────────

# σ₀ (identity)
_s0 = np.zeros((2, 2), dtype=complex)
_s0[0, 0] = 1.0
_s0[1, 1] = 1.0

# σ₁ (x)
_s1 = np.zeros((2, 2), dtype=complex)
_s1[0, 1] = 1.0
_s1[1, 0] = 1.0

# σ₂ (y)
_s2 = np.zeros((2, 2), dtype=complex)
_s2[0, 1] = -1j
_s2[1, 0] = 1j

# σ₃ (z)
_s3 = np.zeros((2, 2), dtype=complex)
_s3[0, 0] = 1.0
_s3[1, 1] = -1.0


def sigma(i: int):
    """Return the i-th Pauli matrix.

    Parameters
    ----------
    i : int
        0: identity, 1: σₓ, 2: σ_y, 3: σ_z.

    Returns
    -------
    ndarray, shape (2, 2), dtype complex128
        The Pauli matrix as a backend array.
    """
    backend = get_backend()
    matrices = {0: _s0, 1: _s1, 2: _s2, 3: _s3}
    if i not in matrices:
        raise ValueError(f"Invalid sigma index {i}. Must be 0..3.")
    return backend.asarray(matrices[i])


def Mom_times_sigma(Mom: list = None, upto4dim: bool = False):
    """Compute p·σ = p_x σ_x + p_y σ_y + p_z σ_z.

    Parameters
    ----------
    Mom : list of float, shape (..., 3)
        Momentum vector [pz, py, px].
    upto4dim : bool
        If True, embed 2×2 result in a 4×4 block-diagonal matrix.

    Returns
    -------
    ndarray, shape (..., 2, 2) or (..., 4, 4)
        p·σ matrix.
    """
    from .base_functions import cached_contract

    if Mom is None:
        Mom = [0, 0, 0]
    backend = get_backend()
    Mom_array = backend.asarray(Mom)

    # Normalize momentum
    norm = backend.sqrt(backend.sum(Mom_array ** 2, axis=-1, keepdims=True))
    eps = 1e-12
    Mom_normalized = backend.where(
        norm > eps,
        Mom_array / norm,
        backend.zeros_like(Mom_array),
    )

    # σ matrices in order: σ_z, σ_y, σ_x
    sigma_array = backend.asarray([sigma(3), sigma(2), sigma(1)])
    result = cached_contract('...a,abc->...bc', Mom_normalized, sigma_array)

    if upto4dim:
        shape = result.shape[:-2] + (4, 4)
        expanded = backend.zeros(shape, dtype=result.dtype)
        expanded[..., :2, :2] = result
        expanded[..., 2:, 2:] = result
        return expanded

    return result
