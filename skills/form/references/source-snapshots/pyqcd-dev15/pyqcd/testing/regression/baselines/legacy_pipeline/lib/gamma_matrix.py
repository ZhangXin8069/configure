"""
DeGrand-Rossi Gamma Matrices
=============================

Gamma matrices in the DeGrand-Rossi (DR, chiral-variant) basis.
Provides ``gamma(i)`` for i=0..17, plus utility functions.

The DR basis has the property:
    γ₀ = diag(1, 1, -1, -1)
    γ₅ = γ₁γ₂γ₃γ₄ (in Euclidean metric)

Gamma index reference:
    0:  identity (γ₀/γ₄ in Minkowski → Euclidean)
    1-4: γ₁, γ₂, γ₃, γ₄ (spatial + temporal)
    5:  γ₅ = γ₁γ₂γ₃γ₄
    6:  γ₂γ₃ = -γ₁γ₄γ₅
    7:  γ₃γ₁ = -γ₂γ₄γ₅
    8:  γ₁γ₂ = -γ₃γ₄γ₅
    9-11: γ₁γ₄, γ₂γ₄, γ₃γ₄
    12-15: γ₁γ₅, γ₂γ₅, γ₃γ₅, γ₄γ₅
    16: γ₃γ₁ · (1+γ₄)/2   (positive parity projector)
    17: γ₃γ₁ · (1-γ₄)/2   (negative parity projector)

Adapted from lqcddb constant/gamma_matrix.py.
"""

import numpy as np
from .backend import get_backend

# ── Define gamma matrices in numpy (constant, never changes) ────────

# γ₀ (identity in DR basis: diag(1,1,1,1))
_g0 = np.zeros((4, 4), dtype=complex)
_g0[0, 0] = 1.0
_g0[1, 1] = 1.0
_g0[2, 2] = 1.0
_g0[3, 3] = 1.0

# γ₁ (spatial x)
_g1 = np.zeros((4, 4), dtype=complex)
_g1[0, 3] = 1j
_g1[1, 2] = 1j
_g1[2, 1] = -1j
_g1[3, 0] = -1j

# γ₂ (spatial y)
_g2 = np.zeros((4, 4), dtype=complex)
_g2[0, 3] = -1.0
_g2[1, 2] = 1.0
_g2[2, 1] = 1.0
_g2[3, 0] = -1.0

# γ₃ (spatial z)
_g3 = np.zeros((4, 4), dtype=complex)
_g3[0, 2] = 1j
_g3[1, 3] = -1j
_g3[2, 0] = -1j
_g3[3, 1] = 1j

# γ₄ (temporal)
_g4 = np.zeros((4, 4), dtype=complex)
_g4[0, 2] = 1.0
_g4[1, 3] = 1.0
_g4[2, 0] = 1.0
_g4[3, 1] = 1.0

# γ₅ = γ₁γ₂γ₃γ₄
_g5 = np.zeros((4, 4), dtype=complex)
_g5[0, 0] = 1.0
_g5[1, 1] = 1.0
_g5[2, 2] = -1.0
_g5[3, 3] = -1.0

# Pre-compute all 18 gamma combinations
_GAMMA_CACHE = {}

def _init_gamma_cache():
    """Pre-compute all gamma matrix combinations."""
    _GAMMA_CACHE[0] = _g0.copy()                             # identity
    _GAMMA_CACHE[1] = _g1.copy()                             # γ₁
    _GAMMA_CACHE[2] = _g2.copy()                             # γ₂
    _GAMMA_CACHE[3] = _g3.copy()                             # γ₃
    _GAMMA_CACHE[4] = _g4.copy()                             # γ₄
    _GAMMA_CACHE[5] = _g5.copy()                             # γ₅
    _GAMMA_CACHE[6] = _g2 @ _g3                              # γ₂γ₃ (=-γ₁γ₄γ₅)
    _GAMMA_CACHE[7] = _g3 @ _g1                              # γ₃γ₁ (=-γ₂γ₄γ₅)
    _GAMMA_CACHE[8] = _g1 @ _g2                              # γ₁γ₂ (=-γ₃γ₄γ₅)
    _GAMMA_CACHE[9] = _g1 @ _g4                              # γ₁γ₄
    _GAMMA_CACHE[10] = _g2 @ _g4                             # γ₂γ₄
    _GAMMA_CACHE[11] = _g3 @ _g4                             # γ₃γ₄
    _GAMMA_CACHE[12] = _g1 @ _g5                             # γ₁γ₅
    _GAMMA_CACHE[13] = _g2 @ _g5                             # γ₂γ₅
    _GAMMA_CACHE[14] = _g3 @ _g5                             # γ₃γ₅
    _GAMMA_CACHE[15] = _g4 @ _g5                             # γ₄γ₅
    # 16: γ₃γ₁ · (1+γ₄)/2  (positive parity projector)
    _GAMMA_CACHE[16] = (_g3 @ _g1) @ (0.5 * (_g0 + _g4))
    # 17: γ₃γ₁ · (1-γ₄)/2  (negative parity projector)
    _GAMMA_CACHE[17] = (_g3 @ _g1) @ (0.5 * (_g0 - _g4))

_init_gamma_cache()


def gamma(i: int):
    """Return the i-th gamma matrix in DeGrand-Rossi basis.

    Parameters
    ----------
    i : int
        Gamma matrix index (0..17). See module docstring for reference.

    Returns
    -------
    ndarray, shape (4, 4), dtype complex128
        The gamma matrix, as a backend array (cupy or numpy depending on
        the current global backend setting).

    Raises
    ------
    SystemExit
        If i is not in the valid range 0..17.
    """
    backend = get_backend()
    if i not in _GAMMA_CACHE:
        raise ValueError(f"Invalid gamma index {i}. Must be 0..17.")
    return backend.asarray(_GAMMA_CACHE[i])


# ── Gamma properties: transpose sign for each gamma ─────────────────
# T_sign: +1 if Γ^T = +Γ, -1 if Γ^T = -Γ
# Used by wick contraction and equivalent diagram identification.
GAMMA_PROPERTIES = {
    'gamma_1':  {'T': (+1,)},
    'gamma_2':  {'T': (+1,)},
    'gamma_3':  {'T': (+1,)},
    'gamma_4':  {'T': (+1,)},
    'gamma_5':  {'T': (+1,)},
    'gamma_6':  {'T': (-1,)},   # γ₂γ₃ is antisymmetric
    'gamma_7':  {'T': (-1,)},   # γ₃γ₁ is antisymmetric
    'gamma_8':  {'T': (-1,)},   # γ₁γ₂ is antisymmetric
    'gamma_9':  {'T': (-1,)},   # γ₁γ₄ is antisymmetric
    'gamma_10': {'T': (-1,)},   # γ₂γ₄ is antisymmetric
    'gamma_11': {'T': (-1,)},   # γ₃γ₄ is antisymmetric
    'gamma_12': {'T': (+1,)},   # γ₁γ₅ = γ₅γ₁
    'gamma_13': {'T': (+1,)},   # γ₂γ₅
    'gamma_14': {'T': (+1,)},   # γ₃γ₅
    'gamma_15': {'T': (+1,)},   # γ₄γ₅
    'gamma_16': {'T': (+1,)},   # parity projector
    'gamma_17': {'T': (+1,)},   # parity projector
}


# ═══════════════════════════════════════════════════════════════════
# Utility: Map index list to gamma array stack
# ═══════════════════════════════════════════════════════════════════

def tran_indx_to_gamma(indx):
    """Convert gamma index(es) to gamma matrix array(s).

    Parameters
    ----------
    indx : int, list of int, or ndarray
        Gamma index or indices.

    Returns
    -------
    ndarray
        If ``indx`` is scalar: shape (4, 4).
        If ``indx`` is array-like: shape ``(*indx.shape, 4, 4)``.
    """
    import numpy as _np

    if isinstance(indx, list):
        indx = _np.asarray(indx)

    if isinstance(indx, (int, _np.integer)):
        return gamma(int(indx))

    indx_shape = list(indx.shape)
    indx_flat = indx.reshape(-1)
    _gamma_stack = _np.asarray([gamma(int(x)) for x in indx_flat])
    return _gamma_stack.reshape(indx_shape + [4, 4])
