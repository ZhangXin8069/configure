"""
DeGrand-Rossi Gamma Matrices
=============================

Gamma matrices in the DeGrand-Rossi (DR, chiral-variant) basis.
Provides ``gamma(i)`` for i=0..17, plus utility functions.

In this API ``gamma(0)`` is the identity sentinel, not an additional
Euclidean Dirac matrix.  The temporal matrix is ``gamma(4)`` and
``gamma(5) = gamma(1) gamma(2) gamma(3) gamma(4)``; in this DR basis
``gamma(5) = diag(1, 1, -1, -1)``.

Gamma index reference:
    0:  identity I (used in projectors such as (I+γ₄)/2)
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
from ..tools._backend import get_backend, get_backend_name
from ..tools._torch_backend import complex_dtype

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
    t = backend.asarray(_GAMMA_CACHE[i])
    if get_backend_name() == 'torch' and t.dtype.is_complex \
            and t.dtype != complex_dtype():
        t = t.to(complex_dtype())   # 跟随全局复数精度（与数据数组混合不报 dtype 错）
    return t


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


def gamma_index(g):
    """γ 矩阵稀疏分解 (value,row,col)（照抄 sush gamma_matrix.gamma_index）。

    Args:
        g: (4,4) γ 矩阵。
    Returns:
        value (4,) complex、row (4,) int、col (4,) int——非零元按行主序，
        不足 4 个时尾部补零。
    """
    value = np.zeros((4), dtype=complex)
    row = np.zeros((4), dtype=int)
    col = np.zeros((4), dtype=int)
    count = 0
    for i in range(4):
        for j in range(4):
            if np.abs(g[i, j]) != 0.0:
                value[count] = g[i, j]
                row[count] = i
                col[count] = j
                count += 1
    return value, row, col


def PFF_Mom_to_gamma_new(Mom, allow_t: bool = False):
    """PFF 投影的 γ 指标组合表（照抄 sush gamma_matrix.PFF_Mom_to_gamma_new）。

    Args:
        Mom: 动量列表 [[pz,py,px], ...]。
        allow_t: False 用 3 维 Levi-Civita；True 前置时间分量 1 后用 4 维。
    Returns:
        (gamma_indx_list_matrix, 其 γ 矩阵, gamma_indx_list_all, 其 γ 矩阵)。
    """
    from itertools import combinations

    from . import _cg  # noqa: F401  占位保持模块依赖显式
    from ..tools._base import levi_civita_tensor

    gamma_indx_list_matrix = [[[]]]

    if allow_t is False:
        lc_tensor = levi_civita_tensor(3)
        Mom_list = [x[::-1] for x in Mom]
    else:
        lc_tensor = levi_civita_tensor(4)
        Mom_list = [([1] + x)[::-1] for x in Mom]

    if Mom_list == [[0, 0, 0]]:
        gamma_indx_list_matrix = np.asarray(
            [[[x, y] for x in range(1, 5) for y in range(1, 5)]])
    else:
        for _Mom in Mom_list:
            k = [x_indx for x_indx, x in enumerate(_Mom) if x != 0]

            for l in np.asarray(list(combinations(k, lc_tensor.ndim - 2))):
                gamma_indx_list = [[]]
                if lc_tensor.ndim - 2 == 1:
                    gamma_indx_matrix = lc_tensor[..., l[0]]
                elif lc_tensor.ndim - 2 == 2:
                    gamma_indx_matrix = lc_tensor[..., l[0], l[1]]

                gamma_indx = np.argwhere(gamma_indx_matrix != 0) + 1
                for i in list(gamma_indx):
                    i = [int(x) for x in i]
                    gamma_indx_list += [i]

                gamma_indx_list_matrix += [gamma_indx_list[1:]]

        n_comb = len(list(combinations(k, lc_tensor.ndim - 2)))
        gamma_indx_list_matrix = np.asarray(
            gamma_indx_list_matrix[1:]).reshape(-1, n_comb * 2, 2)

    gamma_indx_list_all = np.asarray(
        [[x for x in [1, 2, 3, 4] if x in gamma_indx_list_matrix[y]]
         for y in range(len(Mom))])

    return (gamma_indx_list_matrix,
            tran_indx_to_gamma(gamma_indx_list_matrix),
            gamma_indx_list_all,
            tran_indx_to_gamma(gamma_indx_list_all))


def proton_interpolator(variant: str = "Cg5"):
    """质子插值算符对 (Γ_src, Γ_sink)（照抄 donghx 2pt_proton_* L105--138）。

    variant ∈ {Cg5, Cg5g3, Cg5g4, offdiag01, offdiag02, offdiag12}；
    γ 编号沿用 DR 组合表（gamma(7)=Cγ5 类比 donghx gamma(7)）。
    """
    g3, g4, g7 = gamma(3), gamma(4), gamma(7)
    table = {
        "Cg5": (g7, g7),
        "Cg5g3": (g7 @ g3, g7 @ g3),
        "Cg5g4": (g7 @ g4, g7 @ g4),
        "offdiag01": (g7 @ g3, g7),
        "offdiag02": (g7 @ g4, g7),
        "offdiag12": (g7 @ g3, g7 @ g4),
    }
    if variant not in table:
        raise ValueError(f"unknown interpolator variant: {variant}")
    return table[variant]
