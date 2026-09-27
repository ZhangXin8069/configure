"""
Binary Data I/O Readers
=======================

Functions for reading lattice QCD binary data files:
- ``readin_eigvecs``: Read Laplacian eigenvectors (binary float64 format)
- ``readin_peram``: Read perambulator (propagator) data (binary float64 format)
- ``safe_save``: Save numpy arrays with fallback paths

Adapted from lqcddb io/write_date.py.

Binary Format Conventions
-------------------------
- All data is stored as float64 (double precision) in big-endian byte order
- Complex numbers are stored as interleaved [real, imag] pairs
- Eigenvector file: (Nev, Nx³, Nc, 2) float64 → (Nev, Nx³, Nc) complex128
- Perambulator file: per time source, 4 Dirac source index files,
  concatenated then reshaped as (4, Nt, Nev, 4, Nev, 2) → (Nt, 4, 4, Nev, Nev)
"""

import numpy as np
import os
from typing import Optional


def readin_eigvecs(file_path: str, Nx: int):
    """Read distillation Laplacian eigenvectors from binary file.

    File format: float64, shape (Nev, Nx³, 3, 2)
    where the last dimension stores [real, imag] pairs.

    Parameters
    ----------
    file_path : str
        Path to the eigenvector binary file, e.g.
        ``/path/to/eigvecs_t000_6250``.
    Nx : int
        Spatial lattice size (assumed isotropic: Nx = Ny = Nz).

    Returns
    -------
    ndarray, shape (Nev, Nx*Nx*Nx, 3), dtype complex128
        Eigenvectors reshaped into (eigenvector_index, spatial_site, color).
        ``Nev`` is auto-detected from the file size.
    """
    with open(file_path, 'rb') as f:
        eigvecs = np.fromfile(f, dtype='f8')

    # Auto-detect Nev from file size
    eigvecs_size = eigvecs.size
    Nev = int(eigvecs_size / (Nx * Nx * Nx * 3 * 2))

    # Reshape: (Nev, Nx³, 3, 2) → complex → (Nev, Nx³, 3)
    eigvecs = eigvecs.reshape(Nev, Nx * Nx * Nx, 3, 2)
    eigvecs = eigvecs[..., 0] + eigvecs[..., 1] * 1j

    return eigvecs


def readin_eigvecs_gpu(file_path: str, Nx: int, Nev_use: int = None):
    """Read eigenvectors directly to GPU memory.

    Same as ``readin_eigvecs`` but returns a cupy array.
    Requires cupy to be installed and the backend to be set to 'cupy'.

    Parameters
    ----------
    file_path : str
        Path to eigenvector binary file.
    Nx : int
        Spatial lattice size.
    Nev_use : int, optional
        Number of eigenvectors to keep (truncate to first ``Nev_use``).
        If None, use all eigenvectors in the file.

    Returns
    -------
    cupy.ndarray, shape (Nev_use, Nx*Nx*Nx, 3), dtype complex128
        Eigenvectors on GPU.
    """
    import cupy as cp

    with open(file_path, 'rb') as f:
        eigvecs = np.fromfile(f, dtype='f8')

    Nev_full = int(eigvecs.size / (Nx * Nx * Nx * 3 * 2))
    eigvecs = eigvecs.reshape(Nev_full, Nx * Nx * Nx, 3, 2)
    eigvecs = eigvecs[..., 0] + eigvecs[..., 1] * 1j

    if Nev_use is not None and Nev_use < Nev_full:
        eigvecs = eigvecs[:Nev_use]

    return cp.asarray(eigvecs)


def readin_peram(peram_dir: str, conf_id: str, Nt: int,
                 Nev1: Optional[int] = None):
    """Read distillation perambulator from binary files.

    Reads all 4 Dirac source index files per time source and assembles
    the full perambulator array.

    File naming convention:
        ``perams.{conf_id}.{d_source}.{t_source}``

    Parameters
    ----------
    peram_dir : str
        Directory containing perambulator binary files.
    conf_id : str
        Configuration ID (e.g., ``'6250'``).
    Nt : int
        Number of time slices.
    Nev1 : int, optional
        Truncate eigenvector indices to first ``Nev1``. If None, use all.

    Returns
    -------
    ndarray, shape (Nt, Nt, 4, 4, Nev1, Nev1), dtype complex128
        Full perambulator array. Axes:
        - axis 0: t_source (source time)
        - axis 1: t_sink (sink time)
        - axis 2: d_sink (Dirac sink index, 0..3)
        - axis 3: d_source (Dirac source index, 0..3)
        - axis 4: ev_sink (eigenvector sink index)
        - axis 5: ev_source (eigenvector source index)
    """
    # First, determine Nev from the first file
    test_file = f"{peram_dir}/perams.{conf_id}.0.0"
    with open(test_file, 'rb') as f:
        test_data = np.fromfile(f, dtype='f8')

    # Single d_source file: Nt * Nev * 4 * Nev * 2 = 8 * Nt * Nev²
    Nev_full = int(np.sqrt(test_data.size / (8 * Nt)))

    if Nev1 is None:
        Nev1 = Nev_full

    # Allocate output array: (t_source, t_sink, d_sink, d_source, ev_sink, ev_source)
    peram_cpu_all = np.zeros((Nt, Nt, 4, 4, Nev1, Nev1), dtype=complex)

    for t_source in range(Nt):
        # Read d_source=0
        with open(f"{peram_dir}/perams.{conf_id}.0.{t_source}", 'rb') as f:
            peram = np.fromfile(f, dtype='f8')

        # Read and append d_source=1,2,3
        for d_source in range(1, 4):
            with open(f"{peram_dir}/perams.{conf_id}.{d_source}.{t_source}", 'rb') as f:
                temp = np.fromfile(f, dtype='f8')
                peram = np.append(peram, temp)

        # Reshape: (d_source=4, t_sink=Nt, ev_source=Nev, d_sink=4, ev_sink=Nev, complex=2)
        peram = peram.reshape(4, Nt, Nev_full, 4, Nev_full, 2)

        # Transpose: (t_sink, d_sink, d_source, ev_sink, ev_source, complex)
        peram = peram.transpose(1, 3, 0, 4, 2, 5)

        # Convert to complex
        peram = peram[..., 0] + peram[..., 1] * 1j

        # Truncate to Nev1 and store
        peram_cpu_all[t_source] = peram[:, :, :, :Nev1, :Nev1]

    return peram_cpu_all


def readin_peram_time_slice(peram_dir: str, conf_id: str, t_source: int,
                             Nt: int, Nev1: Optional[int] = None):
    """Read perambulator for a single time source slice.

    More memory-efficient than ``readin_peram`` when only one time source
    is needed at a time (avoids allocating the full Nt×Nt array).

    Parameters
    ----------
    peram_dir : str
        Directory containing perambulator files.
    conf_id : str
        Configuration ID.
    t_source : int
        Source time slice to read.
    Nt : int
        Total number of time slices (used to auto-detect Nev).
    Nev1 : int, optional
        Truncate to this many eigenvectors.

    Returns
    -------
    ndarray, shape (Nt, 4, 4, Nev1, Nev1), dtype complex128
        Perambulator for the given time source.
        Axes: (t_sink, d_sink, d_source, ev_sink, ev_source).
    """
    # Auto-detect Nev
    test_file = f"{peram_dir}/perams.{conf_id}.0.{t_source}"
    with open(test_file, 'rb') as f:
        test_data = np.fromfile(f, dtype='f8')
    Nev_full = int(np.sqrt(test_data.size / (8 * Nt)))

    if Nev1 is None:
        Nev1 = Nev_full

    # Read all 4 d_source files
    with open(test_file, 'rb') as f:
        peram = np.fromfile(f, dtype='f8')
    for d_source in range(1, 4):
        with open(f"{peram_dir}/perams.{conf_id}.{d_source}.{t_source}", 'rb') as f:
            temp = np.fromfile(f, dtype='f8')
            peram = np.append(peram, temp)

    # Reshape and transpose
    peram = peram.reshape(4, Nt, Nev_full, 4, Nev_full, 2)
    peram = peram.transpose(1, 3, 0, 4, 2, 5)  # (t_sink, d_sink, d_source, ev_sink, ev_source, complex)
    peram = peram[..., 0] + peram[..., 1] * 1j

    return peram[:, :, :, :Nev1, :Nev1]


def safe_save(file: str, arr, allow_pickle: bool = True,
              fix_imports: bool = True, fallback_dirs: list = None):
    """Save array as .npy file with automatic fallback on failure.

    Tries the primary path first; on OSError falls back to
    ``fallback_dirs`` (if provided), then to a timestamped subdirectory
    of the current working directory.

    Handles cupy arrays by calling ``.get()`` before saving.

    Parameters
    ----------
    file : str
        Target file path. ``.npy`` extension is auto-appended if missing.
    arr : ndarray
        Array to save (numpy or cupy).
    allow_pickle : bool
        Passed to ``numpy.save``.
    fix_imports : bool
        Passed to ``numpy.save``.
    fallback_dirs : list of str, optional
        Additional directories to try before auto-fallback.

    Returns
    -------
    str
        The actual path where the file was saved.

    Raises
    ------
    OSError
        If all save locations fail.
    """
    file = str(file)
    if not file.endswith('.npy'):
        file = file + '.npy'

    basename = os.path.basename(file)

    def _try_save(dir_path):
        candidate = os.path.join(dir_path, basename)
        try:
            os.makedirs(dir_path, exist_ok=True)
            _arr = arr
            if hasattr(_arr, 'get') and callable(_arr.get):
                _arr = _arr.get()
            np.save(candidate, _arr, allow_pickle=allow_pickle,
                    fix_imports=fix_imports)
            return candidate
        except OSError as e:
            print(f"safe_save: failed to save to '{candidate}': {e}")
            return None

    # 1. Try primary path
    primary_dir = os.path.dirname(file) or '.'
    result = _try_save(primary_dir)
    if result is not None:
        return result

    # 2. Try user-provided fallback dirs
    if fallback_dirs:
        for d in fallback_dirs:
            result = _try_save(d)
            if result is not None:
                print(f"safe_save: saved to fallback path '{result}'")
                return result

    # 3. Auto-fallback to cwd
    import time
    auto_dir = os.path.join(
        os.getcwd(), 'data',
        time.strftime('fallback_%Y%m%d_%H%M%S'))
    result = _try_save(auto_dir)
    if result is not None:
        print(f"safe_save: saved to auto fallback path '{result}'")
        return result

    raise OSError(f"safe_save: all save locations exhausted for '{basename}'")


def check_dir_path(save_path: str):
    """Create directory if it doesn't exist.

    Parameters
    ----------
    save_path : str
        Directory path to ensure exists.
    """
    import pathlib
    path = pathlib.Path(save_path)
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        print(f'mkdir_save_path: {save_path}')
