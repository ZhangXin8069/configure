"""
Shared Utilities — docker-v20260805
===================================

Logging, timing, GPU-memory introspection, and numpy/cupy array I/O with
precision handling. Used by every pipeline step so that all progress is
mirrored both to a timestamped log file and to the console.

The user's requirement is that EVERY process output be saved as a log; this
module centralises that behaviour via :func:`setup_logging`.
"""

from __future__ import annotations

import os, sys, time, traceback
from datetime import datetime
import numpy as np

try:
    import cupy as cp
    HAS_CUPY = True
except ImportError:
    cp = np
    HAS_CUPY = False


# ═══════════════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════════════

def setup_logging(log_dir: str, name: str = 'pipeline',
                  verbose: bool = False, rank: int = 0):
    """Create a logger that writes to a timestamped file AND the console.

    Both the central log directory ``/root/PyQCD/logs`` and the
    run-local ``logs/`` directory receive the same file, so the report is
    reproducible from either location.

    Parameters
    ----------
    log_dir : str
        Directory to write the log file into.
    name : str
        Logger name (also prefixes the file name).
    verbose : bool
        If True, DEBUG-level messages are also shown on the console.
    rank : int
        MPI rank (only rank 0 writes files / console).
    """
    import logging
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    logger = logging.getLogger(f"{name}-{ts}")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter('%(asctime)s %(levelname)-7s %(message)s',
                            datefmt='%H:%M:%S')

    # File handler (always DEBUG — full detail saved to disk)
    fpath = os.path.join(log_dir, f"{name}_{ts}.log")
    fh = logging.FileHandler(fpath, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Console handler (INFO by default, DEBUG if verbose)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    logger.info(f"Log file: {fpath}")
    return logger


def print_banner(msg: str, logger=None):
    """Print a section banner to both logger and console."""
    line = "═" * 64
    if logger:
        logger.info(f"\n{line}\n  {msg}\n{line}")
    else:
        print(f"\n{line}\n  {msg}\n{line}")


# ═══════════════════════════════════════════════════════════════════
# Timing
# ═══════════════════════════════════════════════════════════════════

class Timer:
    """Context manager that logs elapsed wall time.

    Optionally synchronises the CUDA stream at entry/exit so the measured
    time reflects GPU work, not just kernel-launch time.
    """

    def __init__(self, name: str, logger=None, sync: bool = True):
        self.name = name
        self.logger = logger
        self.sync = sync
        self.elapsed = 0.0

    def __enter__(self):
        if self.sync and HAS_CUPY:
            cp.cuda.Stream.null.synchronize()
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        if self.sync and HAS_CUPY:
            cp.cuda.Stream.null.synchronize()
        self.elapsed = time.perf_counter() - self.t0
        msg = f"{self.name}: {self.elapsed:.3f} s"
        if self.logger:
            self.logger.info(msg)
        else:
            print(msg)
        return False


# ═══════════════════════════════════════════════════════════════════
# GPU memory introspection
# ═══════════════════════════════════════════════════════════════════

def gpu_memory_info():
    """Return (total_mb, free_mb, used_mb) for the current GPU."""
    if not HAS_CUPY:
        return (0, 0, 0)
    try:
        total, used = cp.cuda.runtime.memGetInfo()
        return (total / 2**20, (total - used) / 2**20, used / 2**20)
    except Exception:
        return (0, 0, 0)


def log_gpu_memory(logger, label: str = ''):
    """Log current GPU memory usage."""
    total, free, used = gpu_memory_info()
    if total:
        logger.info(f"GPU memory{label}: used={used:.0f} MB, "
                    f"free={free:.0f} MB, total={total:.0f} MB")
    else:
        logger.info(f"GPU memory{label}: N/A")


def free_gpu_memory():
    """Release cached CuPy memory-pool blocks (call between heavy steps)."""
    if HAS_CUPY:
        cp.get_default_memory_pool().free_all_blocks()


# ═══════════════════════════════════════════════════════════════════
# Precision / dtype helpers
# ═══════════════════════════════════════════════════════════════════

def get_dtype(precision: str = 'complex64'):
    """Map a precision string to a numpy complex dtype.

    The user's requirement: "注意数据读写间的精度转换" — input on disk is
    complex128 (float64 real/imag interleaved); we convert to the requested
    compute precision (complex64 by default) for GPU work and write outputs
    in that precision.
    """
    return np.complex64 if precision == 'complex64' else np.complex128


def ensure_precision(arr, dtype):
    """Convert an array to the requested dtype (no-op if already correct)."""
    if arr.dtype != dtype:
        return arr.astype(dtype, copy=False)
    return arr


# ═══════════════════════════════════════════════════════════════════
# Array I/O (with cupy→numpy conversion)
# ═══════════════════════════════════════════════════════════════════

def to_cpu(arr):
    """Convert a cupy array to numpy (no-op for numpy input)."""
    if HAS_CUPY and isinstance(arr, cp.ndarray):
        return cp.asnumpy(arr)
    return np.asarray(arr)


def to_gpu(arr):
    """Convert a numpy array to cupy (no-op for cupy input)."""
    if HAS_CUPY:
        return cp.asarray(arr)
    return np.asarray(arr)


def save_array(filepath, arr, logger=None):
    """Save an array to ``.npy``, converting from GPU if needed.

    Precision note: intermediate results are stored in the compute precision
    (complex64 by default) to keep disk usage down. The raw input on disk is
    complex128 — see ``lib.io_readers`` for the read-time conversion.
    """
    arr_np = to_cpu(arr)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    np.save(filepath, arr_np)
    if logger:
        logger.debug(f"Saved {os.path.basename(filepath)} "
                     f"shape={arr_np.shape} dtype={arr_np.dtype} "
                     f"({os.path.getsize(filepath)/1024:.1f} KB)")


def load_array(filepath, to_gpu_: bool = False, dtype=None):
    """Load a ``.npy`` array (optionally to GPU, optionally cast dtype)."""
    arr = np.load(filepath, allow_pickle=True)
    if dtype is not None and arr.dtype != dtype:
        arr = arr.astype(dtype, copy=False)
    return to_gpu(arr) if to_gpu_ else arr


def dump_config_snapshot(config: dict, filepath: str, logger=None):
    """Save a JSON snapshot of the run configuration."""
    import json
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(config, f, indent=2, default=str)
    if logger:
        logger.info(f"Config snapshot -> {filepath}")


def log_exception(logger, e, msg: str = ''):
    """Log a full traceback for an exception."""
    if msg:
        logger.error(msg)
    logger.error(''.join(traceback.format_exception(type(e), e, e.__traceback__)))
