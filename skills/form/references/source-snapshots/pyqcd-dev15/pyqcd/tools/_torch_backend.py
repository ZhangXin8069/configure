"""
PyTorch Backend Adapter for pyqcd
=================================

Provides a numpy-like array API backed by PyTorch so that existing pyqcd
modules written against ``get_backend()`` (numpy/cupy) run unchanged on
torch tensors, on CPU or CUDA GPU.

Design (mirrors ``pyqcu.cann``):
- Every array-taking function auto-converts numpy/cupy arrays and Python
  sequences into torch tensors (zero-copy for numpy, via
  ``torch.as_tensor``) — old code passing numpy data keeps working.
- numpy-style signatures are wrapped where torch differs:
  ``roll(x, shifts, axis=)``, ``transpose(x, axes)``, ``take(x, ind, axis=)``,
  ``eye(n, dtype=)``, ``zeros(shape, dtype=)``, ``sum(x, axis=)`` ...
- ``torch.Tensor`` methods ``transpose``/``astype``/``.T``/``get`` are patched
  (idempotently) to numpy semantics.
- Global precision switch: ``set_precision('complex64'|'complex128')``
  controls the default complex dtype for new arrays created with the
  numpy shorthand ``dtype='complex'``.
"""

import functools
import math
import numpy as np
import torch

__all__ = [
    "torch", "np", "set_precision", "get_precision", "complex_dtype",
    "real_dtype", "set_device", "get_device", "asarray", "array",
    "zeros", "ones", "empty", "full",
    "zeros_like", "ones_like", "empty_like", "eye", "arange", "linspace",
    "einsum", "roll", "transpose", "swapaxes", "meshgrid", "stack",
    "concatenate", "take", "broadcast_to", "flip", "expand_dims",
    "squeeze", "reshape", "matmul", "dot", "vdot", "diag", "tril", "trace",
    "abs", "real", "imag", "conj", "exp", "sqrt", "log", "where",
    "isfinite", "allclose", "amax", "amin", "max", "min", "sum", "mean",
    "std", "var", "argmax", "argmin", "asnumpy", "astype", "pi",
    "linalg",
]

# ═══════════════════════════════════════════════════════════════════
# Global precision state
# ═══════════════════════════════════════════════════════════════════

_GLOBAL_COMPLEX_DTYPE = torch.complex128
_GLOBAL_REAL_DTYPE = torch.float64
_GLOBAL_DEVICE = None   # None = CPU


def set_device(device):
    """Set the default device for new tensors (e.g. 'cuda:0')."""
    global _GLOBAL_DEVICE
    _GLOBAL_DEVICE = device


def get_device():
    return _GLOBAL_DEVICE


def _dev(device=None):
    return device if device is not None else _GLOBAL_DEVICE


def set_precision(complex_dtype):
    """Set the global complex precision for new arrays.

    Parameters
    ----------
    complex_dtype : str or torch.dtype
        ``'complex64'`` or ``'complex128'`` (numpy spellings accepted).
    """
    global _GLOBAL_COMPLEX_DTYPE, _GLOBAL_REAL_DTYPE
    if complex_dtype in ('complex64', np.complex64, torch.complex64):
        _GLOBAL_COMPLEX_DTYPE = torch.complex64
        _GLOBAL_REAL_DTYPE = torch.float32
    elif complex_dtype in ('complex128', np.complex128, torch.complex128):
        _GLOBAL_COMPLEX_DTYPE = torch.complex128
        _GLOBAL_REAL_DTYPE = torch.float64
    else:
        raise ValueError(
            f"Unknown precision '{complex_dtype}'. "
            "Choose 'complex64' or 'complex128'.")


def get_precision():
    """Return the current complex precision ('complex64'/'complex128')."""
    return 'complex64' if _GLOBAL_COMPLEX_DTYPE == torch.complex64 \
        else 'complex128'


def complex_dtype():
    return _GLOBAL_COMPLEX_DTYPE


def real_dtype():
    return _GLOBAL_REAL_DTYPE


# ═══════════════════════════════════════════════════════════════════
# dtype mapping (numpy <-> torch)
# ═══════════════════════════════════════════════════════════════════

_NP_TO_TORCH = {
    np.float32: torch.float32, np.float64: torch.float64,
    np.complex64: torch.complex64, np.complex128: torch.complex128,
    np.int32: torch.int32, np.int64: torch.int64,
    np.bool_: torch.bool,
}

_TORCH_TO_NP = {v: k for k, v in _NP_TO_TORCH.items()}
_TORCH_TO_NP.update({torch.float16: np.float16, torch.int16: np.int16})


def _resolve_dtype(dtype, default=None):
    """Map numpy dtype / str / torch dtype to a torch dtype.

    The numpy shorthand ``'complex'`` (and ``complex``) resolves to the
    global precision. ``None`` falls back to ``default`` (torch.float64).
    """
    if dtype is None:
        return default if default is not None else _GLOBAL_REAL_DTYPE
    if isinstance(dtype, torch.dtype):
        return dtype
    if dtype is complex or dtype == 'complex':
        return _GLOBAL_COMPLEX_DTYPE
    if isinstance(dtype, np.dtype):
        dtype = dtype.type
    if dtype in _NP_TO_TORCH:
        return _NP_TO_TORCH[dtype]
    if isinstance(dtype, str):
        s = dtype.lower().replace('np.', '')
        table = {
            'float64': torch.float64, 'float32': torch.float32,
            'double': torch.float64, 'float': torch.float64,
            'complex128': _GLOBAL_COMPLEX_DTYPE,
            'complex64': torch.complex64,
            'complex': _GLOBAL_COMPLEX_DTYPE,
            'int64': torch.int64, 'int32': torch.int32,
            'long': torch.int64, 'int': torch.int64,
            'bool': torch.bool,
        }
        if s in table:
            return table[s]
    raise TypeError(f"Unsupported dtype: {dtype!r}")


def to_numpy_dtype(dtype):
    """Map a torch dtype back to the closest numpy dtype (for IO)."""
    if isinstance(dtype, torch.dtype):
        return _TORCH_TO_NP.get(dtype, np.complex128)
    return np.dtype(dtype)


# ═══════════════════════════════════════════════════════════════════
# Auto-conversion helper (numpy/cupy input -> torch tensor)
# ═══════════════════════════════════════════════════════════════════

# kwargs that must NOT be tensorized (scalars / config)
_NON_ARRAY_KW = {
    'dtype', 'device', 'keepdims', 'keepdim', 'axis', 'dim', 'dims',
    'axis1', 'axis2', 'indexing', 'rtol', 'atol', 'equal_nan',
    'n', 'm', 'k', 'diagonal', 'num', 'start', 'stop', 'step',
    'full_matrices', 'compute_uv', 'mode', 'ord', 'fill_value', 'shifts',
}


def _tensorize(x):
    """Convert numpy arrays / cupy arrays / sequences to torch tensors.

    Scalars, strings and existing torch tensors pass through unchanged.
    - numpy arrays keep their explicit dtype (e.g. astype('complex64') is
      respected — the global precision only applies to dtype-less input);
    - Python sequences of complex follow the global precision
      (``set_precision``); Python lists of floats follow numpy semantics
      (float64).
    """
    if isinstance(x, torch.Tensor):
        return x
    if x is None or isinstance(x, (str, bool, int, float, complex)):
        return x
    if hasattr(x, 'get') and hasattr(x, 'shape') \
            and not isinstance(x, np.ndarray):     # cupy-style array
        x = x.get()
    if isinstance(x, np.ndarray):
        t = torch.from_numpy(x)
    elif isinstance(x, (list, tuple)):
        if x and all(isinstance(e, (torch.Tensor, np.ndarray)) for e in x):
            # list of tensors/ndarrays（如 [gamma(1), gamma(2), ...]）：
            # 统一转 numpy 堆叠再入 torch（torch.as_tensor 不支持此形态）
            arrs = [e.detach().cpu().numpy()
                    if isinstance(e, torch.Tensor) else e for e in x]
            t = torch.from_numpy(np.asarray(arrs))
        else:
            t = torch.as_tensor(x)
            if torch.is_complex(t):
                t = t.to(_GLOBAL_COMPLEX_DTYPE)
            elif t.dtype == torch.float32:
                t = t.to(torch.float64)
    else:
        return x
    if _GLOBAL_DEVICE is not None:
        t = t.to(_GLOBAL_DEVICE)
    return t


def _autoconv(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        args = tuple(_tensorize(a) for a in args)
        nk = {}
        for k, v in kwargs.items():
            nk[k] = v if k in _NON_ARRAY_KW else _tensorize(v)
        return fn(*args, **nk)
    return wrapper


# ═══════════════════════════════════════════════════════════════════
# torch.Tensor numpy-compat patches (idempotent)
# ═══════════════════════════════════════════════════════════════════

def _patch_tensor():
    if getattr(torch.Tensor, '_pyqcd_patched', False):
        return

    def transpose(self, *axes):
        """numpy-style transpose: ``x.transpose()`` / ``x.transpose(axes)`` /
        ``x.transpose(a, b, ...)`` — arbitrary axis permutation."""
        if len(axes) == 0:
            return torch.permute(self, list(range(self.ndim))[::-1])
        if len(axes) == 1 and isinstance(axes[0], (tuple, list)):
            axes = tuple(axes[0])
        if len(axes) == 2:
            return torch.transpose(self, axes[0], axes[1])
        return torch.permute(self, tuple(axes))

    def astype(self, dtype):
        """numpy-style dtype cast (accepts np dtype / str / torch dtype)."""
        return self.to(_resolve_dtype(dtype))

    def get(self):
        """cupy-compat: return the tensor as a numpy array on CPU."""
        return self.detach().cpu().numpy()

    def repeat(self, repeats, axis=None):
        """numpy-style repeat with axis support (element-wise interleave);
        without ``axis`` falls back to torch block repeat semantics."""
        if axis is not None:
            return torch.repeat_interleave(self, repeats, dim=axis)
        if isinstance(repeats, (tuple, list)):
            return torch.repeat(self, *repeats)
        return torch.repeat(self, repeats)

    torch.Tensor.transpose = transpose
    torch.Tensor.astype = astype
    torch.Tensor.get = get
    torch.Tensor.repeat = repeat
    torch.Tensor.T = property(lambda self: torch.permute(
        self, list(range(self.ndim))[::-1]))

    # Binary ops: numpy operands mixed into torch expressions must be
    # converted through _tensorize (global complex precision), otherwise
    # torch promotes them to complex128 and silently breaks precision
    # switching.
    def _binop(fn):
        def wrapper(self, other):
            if not isinstance(other, torch.Tensor):
                other = _tensorize(other)
            return fn(self, other)
        return wrapper

    for _name in ('__add__', '__radd__', '__sub__', '__rsub__', '__mul__',
                  '__rmul__', '__truediv__', '__rtruediv__', '__matmul__',
                  '__rmatmul__', '__pow__', '__rpow__'):
        try:
            setattr(torch.Tensor, _name,
                    _binop(getattr(torch.Tensor, _name)))
        except AttributeError:
            pass

    torch.Tensor._pyqcd_patched = True


_patch_tensor()

# ═══════════════════════════════════════════════════════════════════
# Array creation / conversion
# ═══════════════════════════════════════════════════════════════════


def asarray(arr, dtype=None, device=None):
    """Convert to torch tensor. numpy/cupy arrays are auto-converted
    (zero-copy for numpy); Python sequences via ``torch.as_tensor``.
    Complex input without explicit ``dtype`` follows the global precision."""
    if isinstance(arr, torch.Tensor):
        t = arr
    elif isinstance(arr, (np.ndarray, list, tuple)) or \
            (hasattr(arr, 'shape') and hasattr(arr, 'get')):
        t = _tensorize(arr)
    else:                                   # python scalar (e.g. 1j, 8.0)
        t = torch.as_tensor(arr)
        if isinstance(arr, complex) or torch.is_complex(t):
            t = t.to(_GLOBAL_COMPLEX_DTYPE)
    if dtype is not None:
        t = t.to(_resolve_dtype(dtype))
    t = t.to(_dev(device))
    return t


def array(arr, dtype=None, device=None):
    """Alias of ``asarray`` (numpy-compat)."""
    return asarray(arr, dtype=dtype, device=device)


def zeros(shape, dtype=None, device=None):
    return torch.zeros(shape, dtype=_resolve_dtype(dtype), device=_dev(device))


def ones(shape, dtype=None, device=None):
    return torch.ones(shape, dtype=_resolve_dtype(dtype), device=_dev(device))


def empty(shape, dtype=None, device=None):
    return torch.empty(shape, dtype=_resolve_dtype(dtype), device=_dev(device))


def full(shape, fill_value, dtype=None, device=None):
    return torch.full(shape, fill_value, dtype=_resolve_dtype(dtype),
                      device=_dev(device))


@_autoconv
def zeros_like(x, dtype=None, device=None):
    if dtype is None:
        return torch.zeros_like(x)
    return torch.zeros_like(x, dtype=_resolve_dtype(dtype))


@_autoconv
def ones_like(x, dtype=None, device=None):
    if dtype is None:
        return torch.ones_like(x)
    return torch.ones_like(x, dtype=_resolve_dtype(dtype))


@_autoconv
def empty_like(x, dtype=None, device=None):
    if dtype is None:
        return torch.empty_like(x)
    return torch.empty_like(x, dtype=_resolve_dtype(dtype))


def eye(n, m=None, dtype=None, device=None):
    if m is None:
        return torch.eye(n, dtype=_resolve_dtype(dtype), device=_dev(device))
    return torch.eye(n, m, dtype=_resolve_dtype(dtype), device=_dev(device))


def arange(start, stop=None, step=1, dtype=None, device=None):
    if stop is None:
        stop, start = start, 0
    dt = _resolve_dtype(dtype)
    if dt.is_complex:
        # torch 不支持复数 arange：实数构造后转复数（numpy 语义）
        return torch.arange(start, stop, step, dtype=dt.to_real(),
                            device=_dev(device)).to(dt)
    return torch.arange(start, stop, step, dtype=dt,
                        device=_dev(device))


def linspace(start, stop, num=50, dtype=None, device=None):
    dt = _resolve_dtype(dtype)
    if dt.is_complex:
        return torch.linspace(start, stop, num, dtype=dt.to_real(),
                              device=_dev(device)).to(dt)
    return torch.linspace(start, stop, num, dtype=dt,
                          device=_dev(device))


# ═══════════════════════════════════════════════════════════════════
# Tensor ops (numpy signatures)
# ═══════════════════════════════════════════════════════════════════

@_autoconv
def einsum(equation, *operands):
    return torch.einsum(equation, *operands)


@_autoconv
def roll(x, shifts, axis=None):
    dims = None if axis is None else axis
    return torch.roll(x, shifts, dims=dims)


@_autoconv
def transpose(x, axes=None):
    if axes is None:
        axes = list(range(x.ndim))[::-1]
    if not isinstance(axes, (tuple, list)):
        axes = (axes,)
    if len(axes) == 2:
        return torch.transpose(x, axes[0], axes[1])
    return torch.permute(x, tuple(axes))


@_autoconv
def swapaxes(x, axis1, axis2):
    return torch.swapaxes(x, axis1, axis2)


def meshgrid(*arrays, indexing='xy'):
    arrays = tuple(_tensorize(a) for a in arrays)
    return torch.meshgrid(*arrays, indexing=indexing)


def stack(arrays, axis=0):
    arrays = tuple(_tensorize(a) for a in arrays)
    return torch.stack(arrays, dim=axis)


def concatenate(arrays, axis=0):
    arrays = tuple(_tensorize(a) for a in arrays)
    return torch.cat(arrays, dim=axis)


@_autoconv
def take(x, indices, axis=None):
    """numpy-style take with axis support (negative indices handled)."""
    if axis is None:
        return torch.take(x, torch.as_tensor(indices, dtype=torch.long))
    ind = torch.as_tensor(indices, dtype=torch.long)
    if ind.numel() == 0:
        return torch.index_select(x, axis, ind)
    neg = ind < 0
    if bool(neg.any()):
        size = x.shape[axis]
        ind = torch.where(neg, ind + size, ind)
    return torch.index_select(x, axis, ind)


def broadcast_to(x, shape):
    # ``shape`` 是元数据而非数组；通用自动转换会把位置参数 tuple
    # 变成 Tensor，torch.broadcast_to 因而拒绝。这里只转换数据参数。
    return torch.broadcast_to(_tensorize(x), tuple(int(n) for n in shape))


@_autoconv
def flip(x, axis=None):
    return torch.flip(x, dims=axis)


@_autoconv
def expand_dims(x, axis):
    return torch.unsqueeze(x, axis)


@_autoconv
def squeeze(x, axis=None):
    if axis is None:
        return torch.squeeze(x)
    return torch.squeeze(x, dim=axis)


@_autoconv
def reshape(x, shape):
    return torch.reshape(x, shape)


@_autoconv
def matmul(x, y):
    return torch.matmul(x, y)


@_autoconv
def dot(x, y):
    if x.ndim == 1 and y.ndim == 1:
        return torch.dot(x, y)
    return torch.matmul(x, y)


@_autoconv
def vdot(x, y):
    return torch.vdot(x.flatten(), y.flatten())


@_autoconv
def diag(x, k=0):
    return torch.diag(x, diagonal=k)


@_autoconv
def tril(x, k=0, diagonal=None):
    """Return the lower triangle without changing dtype or device.

    ``k`` follows NumPy's name and ``diagonal`` is accepted as the matching
    PyTorch spelling.
    """
    if diagonal is not None:
        k = diagonal
    return torch.tril(x, diagonal=k)


@_autoconv
def trace(x):
    if x.ndim == 2:
        return torch.trace(x)
    return torch.einsum('...ii->...', x)


@_autoconv
def abs(x):
    return torch.abs(x)


@_autoconv
def real(x):
    return torch.real(x)


@_autoconv
def imag(x):
    return torch.imag(x)


@_autoconv
def conj(x):
    return torch.conj(x)


@_autoconv
def exp(x):
    return torch.exp(x)


@_autoconv
def sqrt(x):
    return torch.sqrt(x)


@_autoconv
def log(x):
    return torch.log(x)


@_autoconv
def where(cond, x, y):
    return torch.where(cond, x, y)


@_autoconv
def isfinite(x):
    return torch.isfinite(x)


@_autoconv
def allclose(x, y, rtol=1e-05, atol=1e-08, equal_nan=False):
    return torch.allclose(x, y, rtol=rtol, atol=atol, equal_nan=equal_nan)


def _reduce(torch_fn, x, axis=None, keepdims=False, dim=None):
    if axis is None and dim is None:
        return torch_fn(x)
    dims = axis if axis is not None else dim
    return torch_fn(x, dim=dims, keepdim=keepdims)


@_autoconv
def sum(x, axis=None, dtype=None, keepdims=False, dim=None):
    r = _reduce(torch.sum, x, axis, keepdims, dim)
    if dtype is not None:
        r = r.to(_resolve_dtype(dtype))
    return r


@_autoconv
def mean(x, axis=None, dtype=None, keepdims=False, dim=None):
    r = _reduce(torch.mean, x, axis, keepdims, dim)
    if dtype is not None:
        r = r.to(_resolve_dtype(dtype))
    return r


@_autoconv
def std(x, axis=None, dtype=None, keepdims=False, dim=None):
    r = _reduce(torch.std, x, axis, keepdims, dim)
    if dtype is not None:
        r = r.to(_resolve_dtype(dtype))
    return r


@_autoconv
def var(x, axis=None, dtype=None, keepdims=False, dim=None):
    r = _reduce(torch.var, x, axis, keepdims, dim)
    if dtype is not None:
        r = r.to(_resolve_dtype(dtype))
    return r


@_autoconv
def max(x, axis=None, keepdims=False):
    if axis is None:
        return torch.max(x)
    if isinstance(axis, (tuple, list)):
        return torch.amax(x, dim=axis, keepdim=keepdims)
    return torch.max(x, dim=axis, keepdim=keepdims).values


@_autoconv
def min(x, axis=None, keepdims=False):
    if axis is None:
        return torch.min(x)
    if isinstance(axis, (tuple, list)):
        return torch.amin(x, dim=axis, keepdim=keepdims)
    return torch.min(x, dim=axis, keepdim=keepdims).values


@_autoconv
def amax(x, axis=None, keepdims=False):
    if axis is None:
        return torch.amax(x)
    return torch.amax(x, dim=axis, keepdim=keepdims)


@_autoconv
def amin(x, axis=None, keepdims=False):
    if axis is None:
        return torch.amin(x)
    return torch.amin(x, dim=axis, keepdim=keepdims)


@_autoconv
def argmax(x, axis=None):
    if axis is None:
        return torch.argmax(x)
    return torch.argmax(x, dim=axis)


@_autoconv
def argmin(x, axis=None):
    if axis is None:
        return torch.argmin(x)
    return torch.argmin(x, dim=axis)


@_autoconv
def cos(x):
    return torch.cos(x)


@_autoconv
def sin(x):
    return torch.sin(x)


@_autoconv
def arccos(x):
    return torch.acos(x)


@_autoconv
def isnan(x):
    return torch.isnan(x)


@_autoconv
def clip(x, a_min=None, a_max=None):
    return torch.clamp(x, min=a_min, max=a_max)


@_autoconv
def maximum(x, y):
    """逐元素最大值（numpy 语义：y 可为标量）。"""
    if not isinstance(y, torch.Tensor):
        y = torch.as_tensor(y, dtype=x.dtype if x.is_floating_point()
                            or x.is_complex() else None, device=x.device)
    return torch.maximum(x, y)


@_autoconv
def argwhere(x):
    return torch.argwhere(x)


@_autoconv
def identity(n, dtype=None):
    return torch.eye(int(n), dtype=_resolve_dtype(dtype))


@_autoconv
def append(arr, values, axis=None):
    if axis is None:
        return torch.cat((arr.reshape(-1), values.reshape(-1)), dim=0)
    return torch.cat((arr, values), dim=axis)


def random_random(size=None):
    """[0,1) 均匀随机（numpy.random.random 语义），遵循全局精度/device。"""
    shape = size if isinstance(size, (tuple, list)) else \
        (size,) if size is not None else ()
    r = torch.rand(shape, device=get_device(), dtype=torch.float64)
    return r.to(_resolve_dtype('complex128')).real


class _Random:
    """numpy.random.random 兼容入口（仅 random；可复现性由调用方管理）。"""
    random = staticmethod(random_random)


random = _Random()


def asnumpy(x):
    """Convert torch tensor (any device) to numpy array (CPU)."""
    if isinstance(x, torch.Tensor):
        return x.detach().cpu().numpy()
    if hasattr(x, 'get') and hasattr(x, 'shape'):
        return x.get()
    return np.asarray(x)


@_autoconv
def astype(x, dtype):
    return x.to(_resolve_dtype(dtype))


pi = math.pi


# ═══════════════════════════════════════════════════════════════════
# linalg namespace (numpy-compatible subset)
# ═══════════════════════════════════════════════════════════════════

class _Linalg:
    @_autoconv
    def det(self, x):
        return torch.linalg.det(x)

    @_autoconv
    def inv(self, x):
        return torch.linalg.inv(x)

    @_autoconv
    def svd(self, x, full_matrices=True, compute_uv=True):
        if not compute_uv:
            return torch.linalg.svdvals(x)
        return torch.linalg.svd(x, full_matrices=full_matrices)

    @_autoconv
    def qr(self, x, mode='reduced'):
        return torch.linalg.qr(x, mode=mode)

    @_autoconv
    def norm(self, x, ord=None, axis=None, keepdims=False):
        dim = None if axis is None else axis
        return torch.linalg.norm(x, ord=ord, dim=dim, keepdim=keepdims)

    @_autoconv
    def eigvalsh(self, x):
        return torch.linalg.eigvalsh(x)

    @_autoconv
    def eigh(self, x):
        return torch.linalg.eigh(x)


linalg = _Linalg()
