"""
GPU/CPU Backend Switching Module
================================

Provides global backend state for array operations. All modules that create
arrays should call ``get_backend()`` to get the current backend module
(numpy or cupy), and use ``set_backend(name)`` to switch.

Adapted from lqcddb base/backend.py.
"""

import numpy as np

# Global backend state — modified by set_backend()
_CURRENT_BACKEND = np
_BACKEND_NAME = 'numpy'


def set_backend(name: str):
    """Switch the global array backend.

    Parameters
    ----------
    name : str
        ``'numpy'`` for CPU or ``'cupy'`` for NVIDIA GPU.

    Raises
    ------
    ImportError
        If cupy is not installed when switching to GPU.
    ValueError
        If name is not ``'numpy'`` or ``'cupy'``.
    """
    global _CURRENT_BACKEND, _BACKEND_NAME

    name_lower = name.lower()
    if name_lower == 'numpy':
        _CURRENT_BACKEND = np
        _BACKEND_NAME = 'numpy'
    elif name_lower == 'cupy':
        try:
            import cupy as cp
            _CURRENT_BACKEND = cp
            _BACKEND_NAME = 'cupy'
        except ImportError:
            raise ImportError(
                "CuPy is not installed. Install with: pip install cupy")
    else:
        raise ValueError(
            f"Unknown backend '{name}'. Choose 'numpy' or 'cupy'.")


def get_backend():
    """Return the current backend module (numpy or cupy).

    Returns
    -------
    module
        The current backend module. All array creation should use
        ``backend.zeros()``, ``backend.asarray()``, etc.
    """
    return _CURRENT_BACKEND


def get_backend_name():
    """Return the current backend name as a string ('numpy' or 'cupy')."""
    return _BACKEND_NAME
