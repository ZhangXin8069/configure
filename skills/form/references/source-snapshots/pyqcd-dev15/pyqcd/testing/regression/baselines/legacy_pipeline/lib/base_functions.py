"""
Base Utility Functions
======================

Core utilities used throughout the pipeline:
- ``cached_contract``: LRU-cached einsum with opt_einsum fallback
- ``ArraySlicer``: Multi-dimensional array slicing with assignment
- ``levi_civita_tensor``: Levi-Civita symbol in N dimensions
- ``creat_mom_list``: Generate momentum lists for given Q² shells

Adapted from lqcddb base/base_functions.py.
"""

from .backend import get_backend

import numpy as _np


def np_broadcast_view(shape, dtype):
    """Zero-memory broadcast view with the given shape/dtype.

    Used as a placeholder in ``contract_path`` for path scoring — carries
    shape and dtype metadata only, never copies data.
    """
    return _np.broadcast_to(_np.empty((), dtype=dtype), shape)


# ═══════════════════════════════════════════════════════════════════
# Cached Einsum
# ═══════════════════════════════════════════════════════════════════

# Module-level compiled-expression cache.
# Key = (einsum_str, input_shapes, optimizer_key); value = a compiled
# opt_einsum.contract_expression. The compiled expression is reusable for
# ANY input arrays with those shapes (numpy OR cupy), so the cache works
# with GPU backends even though cupy arrays themselves are unhashable.
_expr_cache: dict = {}

# Candidate optimizers tried on the cold path when optimize=True.
_AUTO_OPTIMIZERS = ('auto', 'greedy', 'optimal', 'dp')


def _validate_einsum_shapes(einsum_str: str, shapes: tuple):
    """Early shape validation for the cold (cache-miss) path.

    Confirms each operand's ndim matches its subscript labels and that
    repeated labels have consistent sizes, producing a readable error
    message instead of a cryptic opt_einsum failure.
    """
    lhs, rhs = einsum_str.split('->')
    operands = lhs.split(',')
    if len(operands) != len(shapes):
        raise ValueError(
            f"cached_contract: {len(operands)} subscripts but "
            f"{len(shapes)} tensors: {einsum_str} {shapes}")
    for sub, shape in zip(operands, shapes):
        if '...' in sub:
            continue   # broadcast ellipsis — skip the strict ndim check
        labels = [c for c in sub if c not in '.-']
        if len(labels) != len(shape):
            raise ValueError(
                f"cached_contract: subscript '{sub}' has {len(labels)} "
                f"indices but tensor has ndim {len(shape)}: {einsum_str} {shapes}")


def cached_contract(einsum_str: str, *tensors, optimize='auto'):
    """Tensor contraction with a compiled-expression LRU cache.

    Reuses an ``opt_einsum.contract_expression`` for repeated
    (subscripts, shapes, optimizer) keys so the contraction path is found
    only once — essential for the many repeated same-shape contractions
    in the Wick engine. Falls back to ``backend.einsum`` if opt_einsum is
    unavailable.

    Parameters
    ----------
    einsum_str : str
        Einstein summation subscript string, e.g. ``'ab,bc->ac'``.
    *tensors : ndarray
        Input arrays (numpy or cupy). Shapes, not values, form the key.
    optimize : str, bool, or list of str
        Path-optimization strategy. ``True`` tries a preset list and keeps
        the cheapest path.

    Returns
    -------
    ndarray
        Contraction result in the active backend.
    """
    from opt_einsum import contract_expression, contract_path

    backend = get_backend()
    shapes = tuple(t.shape for t in tensors)

    # ── Parse optimize → cache key (hot path: only builds the key) ──
    if isinstance(optimize, str):
        opt_key = optimize
    elif optimize is True:
        opt_key = _AUTO_OPTIMIZERS
    elif isinstance(optimize, list):
        opt_key = tuple(optimize)
    else:
        raise TypeError(
            f"optimize must be str, bool, or list, got {type(optimize)}")

    key = (einsum_str, shapes, opt_key)
    expr = _expr_cache.get(key)
    if expr is not None:
        return expr(*tensors)

    # ════════════════════════════════════════════════════════════════
    # Cold path — first call for this (subscripts, shapes) combination
    # ════════════════════════════════════════════════════════════════
    try:
        from opt_einsum import contract as opt_contract
        _HAS_OPT = True
    except ImportError:
        _HAS_OPT = False

    if not _HAS_OPT:
        return backend.einsum(einsum_str, *tensors, optimize=optimize)

    # Resolve candidate optimizers
    if isinstance(optimize, str):
        candidate_opts = [optimize]
    elif optimize is True:
        candidate_opts = list(_AUTO_OPTIMIZERS)
    else:
        candidate_opts = list(optimize)

    _validate_einsum_shapes(einsum_str, shapes)

    # Build zero-memory broadcast placeholders for path scoring.
    # cupy arrays can't be used as placeholders in numpy contract_path,
    # so we always use numpy views (dtype/shape only — no data copied).
    placeholders = tuple(
        np_broadcast_view(t.shape, t.dtype) for t in tensors
    )

    best_expr, best_score = None, None
    tried = set()
    for opt in candidate_opts:
        key_opt = opt if not isinstance(opt, list) else tuple(opt)
        if key_opt in tried:
            continue
        tried.add(key_opt)
        try:
            _, path_info = contract_path(einsum_str, *placeholders,
                                         optimize=opt)
            # Score by (FLOPs, largest intermediate) — cheapest path wins
            score = (path_info.opt_cost, path_info.largest_intermediate)
            if best_score is None or score < best_score:
                best_expr = contract_expression(einsum_str, *shapes,
                                                optimize=path_info.path)
                best_score = score
        except Exception:
            continue

    if best_expr is None:
        # Fallback: let opt_einsum decide
        expr = contract_expression(einsum_str, *shapes)
    else:
        expr = best_expr

    _expr_cache[key] = expr
    return expr(*tensors)


def clear_cache():
    """Clear the compiled-expression cache (e.g. after a plan change)."""
    _expr_cache.clear()


# ═══════════════════════════════════════════════════════════════════
# ArraySlicer — Multi-dimensional slicing with assignment
# ═══════════════════════════════════════════════════════════════════

class ArraySlicer:
    """Multi-dimensional array slicing utility with assignment support.

    Provides ``slice()`` for reading and ``assign()`` for writing to
    specific dimensions by index lists. Works with both numpy and cupy arrays.

    Parameters
    ----------
    arr : ndarray
        The array to slice/assign on. Not copied — operations modify
        the original array in-place on assign.

    Examples
    --------
    >>> a = backend.zeros((3, 4, 5))
    >>> sl = ArraySlicer(a)
    >>> sl.assign(dims=[0], indices=[[0, 2]], values=backend.ones((2, 4, 5)))
    >>> sl.slice(dims=[0], indices=[[0, 2]])  # read back
    """

    def __init__(self, arr):
        self.arr = arr

    def slice(self, dims, indices):
        """Read a sub-array by slicing specified dimensions at given indices.

        Parameters
        ----------
        dims : list of int
            Dimensions to slice along (0-indexed).
        indices : list of list of int
            For each dim in ``dims``, a list of indices to select.
            Must have same length as ``dims``.

        Returns
        -------
        ndarray
            The sliced sub-array. Shape: original shape with sliced
            dimensions replaced by the number of selected indices.
        """
        backend = get_backend()
        idx = [slice(None)] * self.arr.ndim
        for d, ind in zip(dims, indices):
            idx[d] = ind
        # Use take for each sliced dimension to handle both numpy and cupy
        result = self.arr
        for d, ind in zip(dims, indices):
            result = backend.take(result, ind, axis=d)
        return result

    def assign(self, dims, indices, values):
        """Assign values to a sub-array at specified dimension indices.

        Parameters
        ----------
        dims : list of int
            Dimensions to assign along.
        indices : list of list of int
            For each dim, a list of indices to write to.
        values : ndarray
            Values to assign. Shape must match the sliced region.

        Returns
        -------
        ndarray
            The modified array (same object, modified in-place).
        """
        idx = [slice(None)] * self.arr.ndim
        for d, ind in zip(dims, indices):
            idx[d] = ind
        self.arr[tuple(idx)] = values
        return self.arr


# ═══════════════════════════════════════════════════════════════════
# Levi-Civita Tensor
# ═══════════════════════════════════════════════════════════════════

def levi_civita_tensor(ndim: int = 3):
    """Generate the fully antisymmetric Levi-Civita symbol.

    Parameters
    ----------
    ndim : int
        Number of dimensions. Default 3 (for SU(3) color).

    Returns
    -------
    ndarray
        Levi-Civita tensor of shape ``(ndim,) * ndim``, dtype int.
        Values are +1 for even permutations, -1 for odd, 0 otherwise.
    """
    import numpy as np

    arr = np.zeros(tuple([ndim] * ndim), dtype=int)
    from itertools import permutations
    for perm in permutations(range(ndim)):
        # Count inversions to determine sign
        inv = 0
        for i in range(ndim):
            for j in range(i + 1, ndim):
                if perm[i] > perm[j]:
                    inv += 1
        arr[perm] = 1 if inv % 2 == 0 else -1
    return get_backend().asarray(arr.astype(float))


# ═══════════════════════════════════════════════════════════════════
# Momentum List Generation
# ═══════════════════════════════════════════════════════════════════

def creat_mom_list(Mom: list = None, fix_Q2: bool = False):
    """Generate momentum triples [pz, py, px] for a given Q² shell.

    Generates all permutations with sign flips of the base momentum,
    removing duplicates.

    Parameters
    ----------
    Mom : list of int, optional
        Base momentum [pz, py, px]. Default [0, 0, 0].
    fix_Q2 : bool
        If True, only include momenta with the same Q² (sum of squares).
        Default False (include all sign-flipped permutations).

    Returns
    -------
    list of list of int
        All unique momentum triples satisfying the constraints.

    Examples
    --------
    >>> creat_mom_list([0, 0, 1])
    [[0, 0, 1], [0, -1, 0], [1, 0, 0], ...]
    """
    import numpy as np

    if Mom is None:
        Mom = [0, 0, 0]

    if all(m == 0 for m in Mom):
        return [[0, 0, 0]]

    Q2 = sum(m**2 for m in Mom)

    # Generate all sign-flipped permutations
    mom_list = []
    from itertools import permutations, product

    # All permutations of the absolute values
    abs_vals = [abs(m) for m in Mom]
    for perm in set(permutations(abs_vals)):
        # All sign combinations for non-zero components
        signs = []
        for val in perm:
            if val == 0:
                signs.append([0])
            else:
                signs.append([-val, val])
        for sign_combo in product(*signs):
            mom_triple = list(sign_combo)
            if mom_triple not in mom_list:
                if not fix_Q2 or sum(m**2 for m in mom_triple) == Q2:
                    mom_list.append(mom_triple)

    # Sort: by Q², then by pz, py, px
    mom_list.sort(key=lambda x: (sum(i**2 for i in x), x[0], x[1], x[2]))
    return mom_list
