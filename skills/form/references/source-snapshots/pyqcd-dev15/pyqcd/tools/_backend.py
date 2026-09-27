"""
GPU/CPU Backend Switching Module
================================

Provides global backend state for array operations. All modules that create
arrays should call ``get_backend()`` to get the current backend module
(numpy, cupy or torch), and use ``set_backend(name)`` to switch.

Supported backends:
- ``'numpy'``: CPU, NumPy ndarray
- ``'cupy'``:  NVIDIA GPU via CuPy (requires cupy)
- ``'torch'``: PyTorch tensors (CPU or CUDA), auto-converts numpy/cupy input

Adapted from lqcddb base/backend.py; torch backend mirrors pyqcu.cann.
"""

import numpy as np

# Global backend state — modified by set_backend()
_CURRENT_BACKEND = np
_BACKEND_NAME = 'numpy'

# Default torch device (None = CPU)
_TORCH_DEVICE = None


def set_backend(name: str, device=None):
    """Switch the global array backend.

    Parameters
    ----------
    name : str
        ``'numpy'`` for CPU, ``'cupy'`` for NVIDIA GPU (CuPy), or
        ``'torch'`` for PyTorch (CPU or CUDA via ``device``).
        ``'gpu'`` / ``'cuda'`` are aliases for ``'torch'`` with CUDA.
    device : str or torch.device, optional
        Target device for the torch backend (e.g. ``'cpu'``, ``'cuda'``,
        ``'cuda:0'``). Ignored for numpy/cupy backends.

    Raises
    ------
    ImportError
        If cupy is not installed when switching to 'cupy'.
    ValueError
        If name is not a supported backend.
    """
    global _CURRENT_BACKEND, _BACKEND_NAME, _TORCH_DEVICE

    name_lower = name.lower()
    if name_lower == 'numpy':
        _CURRENT_BACKEND = np
        _BACKEND_NAME = 'numpy'
        _TORCH_DEVICE = None
    elif name_lower == 'cupy':
        try:
            import cupy as cp
            _CURRENT_BACKEND = cp
            _BACKEND_NAME = 'cupy'
            _TORCH_DEVICE = None
        except ImportError:
            raise ImportError(
                "CuPy is not installed. Install with: pip install cupy")
    elif name_lower in ('torch', 'gpu', 'cuda'):
        from . import _torch_backend as tb
        if name_lower != 'torch' and device is None:
            if not tb.torch.cuda.is_available():
                raise ImportError(
                    "CUDA not available; use set_backend('torch', device='cpu')")
            device = 'cuda'
        if device is None or str(device).startswith('cpu'):
            # CPU 后端自动线程调优：8 线程最优（16 线程过度并行反而慢 ~40%）
            try:
                import os as _os
                tb.torch.set_num_threads(min(_os.cpu_count() or 4, 8))
            except Exception:
                pass
        _CURRENT_BACKEND = tb
        _BACKEND_NAME = 'torch'
        _TORCH_DEVICE = device
        tb.set_device(device)
    else:
        raise ValueError(
            f"Unknown backend '{name}'. Choose 'numpy', 'cupy' or 'torch'.")


def get_backend():
    """Return the current backend module (numpy, cupy or torch adapter).

    Returns
    -------
    module
        The current backend module. All array creation should use
        ``backend.zeros()``, ``backend.asarray()``, etc.
    """
    return _CURRENT_BACKEND


def get_backend_name():
    """Return the current backend name as a string
    ('numpy', 'cupy' or 'torch')."""
    return _BACKEND_NAME


def get_torch_device():
    """Return the device configured for the torch backend (None = CPU)."""
    return _TORCH_DEVICE


def set_precision(complex_dtype):
    """Switch the global complex precision for the torch backend.

    Parameters
    ----------
    complex_dtype : str
        ``'complex64'`` or ``'complex128'``.
    """
    from . import _torch_backend as tb
    tb.set_precision(complex_dtype)


def get_precision():
    """Return the current complex precision ('complex64'/'complex128')."""
    if _BACKEND_NAME != 'torch':
        return 'complex128'  # numpy/cupy native complex128
    from . import _torch_backend as tb
    return tb.get_precision()
