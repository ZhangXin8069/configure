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

from ._backend import get_backend

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

    torch tensors (torch backend) bypass opt_einsum and use
    ``torch.einsum`` directly (torch's own path optimizer applies).

    Parameters
    ----------
    einsum_str : str
        Einstein summation subscript string, e.g. ``'ab,bc->ac'``.
    *tensors : ndarray
        Input arrays (numpy, cupy or torch). Shapes, not values, form the key.
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

    # ── torch path: torch.einsum handles path optimization itself ──
    if any(type(t).__module__.startswith('torch') for t in tensors):
        return backend.einsum(einsum_str, *tensors)

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

def get_cache_keys():
    """返回 cached_contract 当前缓存键列表（对照 sush base_functions 补齐）。"""
    return list(_expr_cache.keys())



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
        # 与输入数组类型一致（numpy 数组用 numpy.take，cupy 数组用 cupy.take），
        # 避免全局 backend 与输入类型不一致导致 cupy/numpy 数组混杂。
        if not type(self.arr).__module__.startswith('cupy'):
            backend = _np
        idx = [slice(None)] * self.arr.ndim
        for d, ind in zip(dims, indices):
            idx[d] = ind
        # Use take for each sliced dimension to handle both numpy and cupy
        result = self.arr
        for d, ind in zip(dims, indices):
            result = backend.take(result, ind, axis=d)
        return result

    def assign(self, dims, indices, values, keep_dims=None):
        """Assign values to a sub-array at specified dimension indices.

        Parameters
        ----------
        dims : list of int
            Dimensions to assign along.
        indices : list of list of int
            For each dim, a list of indices to write to.
        values : ndarray
            Values to assign. Shape must match the sliced region.
        keep_dims : list of int, optional
            照抄参考语义：给出时按目标形状将 values 中未列入 keep_dims
            （含负号约定）的维度压缩为 1 后广播写入。

        Returns
        -------
        ndarray
            The modified array (same object, modified in-place).
        """
        idx = [slice(None)] * self.arr.ndim
        for d, ind in zip(dims, indices):
            idx[d] = ind
        if keep_dims:
            tgt = self.arr[tuple(idx)]
            newshape = [x if (x_indx in keep_dims
                             or x_indx - self.arr.ndim in keep_dims)
                        else 1
                        for x_indx, x in enumerate(tgt.shape)]
            self.arr[tuple(idx)] = _np.asarray(values).reshape(newshape)
        else:
            self.arr[tuple(idx)] = values
        return self.arr

    def get_slices(self, dims, indices):
        """照抄参考：构建 np.ix_ 索引网格（支持负维号与 int/list/slice）。"""
        arr_shape = self.arr.shape
        if len(dims) != len(indices):
            raise ValueError('Dimension and index lists must have the same '
                             'length')
        slices = [list(range(x)) for x in arr_shape]
        for dim, idx in zip(dims, indices):
            dim = dim % self.arr.ndim
            if isinstance(idx, (list, _np.ndarray)):
                slices[dim] = idx
            elif isinstance(idx, int):
                slices[dim] = [idx]
            elif idx == slice(None):
                pass
            elif isinstance(idx, range):
                slices[dim] = list(idx)
            elif isinstance(idx, slice):
                start = idx.start if idx.start is not None else 0
                stop = idx.stop if idx.stop is not None else arr_shape[dim]
                step = idx.step if idx.step is not None else 1
                slices[dim] = list(range(start, stop, step))
            else:
                raise ValueError(f'Unsupported index type: {type(idx)}')
        return _np.ix_(*slices)

    def get_slice_shape(self, dims, indices):
        """目标切片形状（经 np.ix_ 语义）。"""
        slices = self.get_slices(dims, indices)
        dummy = _np.zeros(self.arr.shape)
        return dummy[slices].shape

    def get_info(self):
        """数组基本信息。"""
        return {'shape': self.arr.shape, 'ndim': self.arr.ndim,
                'dtype': self.arr.dtype}


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

def creat_mom_list(Mom=None, fix_Q2: bool = False,
                   only_g0: bool = False):
    """Generate momentum triples [pz, py, px]（对照 sush base_functions 忠实移植）.

    对每个输入动量：在 [min, max] 立方内枚举全部格点，再做非零分量符号
    全展开；fix_Q2=True 时仅保留 sum(x²)==Q² 的壳层；only_g0=True 时仅保留
    全非负分量子集。支持平铺 [pz,py,px]、嵌套 [[..],..] 与 ndarray 输入。

    Returns
    -------
    list of list of int
        sorted 后的全部动量三元组。
    """
    import itertools

    if Mom is None:
        Mom = [0, 0, 0]

    def _add_negative_signs(lst):
        nonzero_indices = [i for i, val in enumerate(lst) if val != 0]
        result = []
        for signs in itertools.product([1, -1],
                                       repeat=len(nonzero_indices)):
            new_list = lst.copy()
            for idx, sign in zip(nonzero_indices, signs):
                new_list[idx] = lst[idx] * sign
            result.append(new_list)
        return result

    if 'array' in str(type(Mom)):
        Mom = Mom.tolist()

    if type(Mom[0]) == list:
        _num = len(Mom)
    else:
        _num = 1
        Mom = [Mom]

    Mom_list_all = []

    for k in range(_num):
        _Mom = Mom[k]

        min_Mom = min(_Mom)
        max_Mom = max(_Mom)

        len_Mom = max_Mom - min_Mom + 1

        Q2 = sum(x ** 2 for x in _Mom)

        for j in range(len_Mom ** 3):
            Mom_list = [(j // (len_Mom ** 2)) % len_Mom + min_Mom,
                        (j // (len_Mom ** 1)) % len_Mom + min_Mom,
                        (j // (len_Mom ** 0)) % len_Mom + min_Mom]
            Mom_list = _add_negative_signs(Mom_list)

            if fix_Q2:
                Mom_list_all += [m for m in Mom_list
                                 if Q2 == sum(x ** 2 for x in m)]
            else:
                Mom_list_all += Mom_list

    if only_g0:
        return sorted([x for x in Mom_list_all if all(y >= 0 for y in x)])

    return sorted(Mom_list_all)
