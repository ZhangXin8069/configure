"""
System Resource Detection
=========================

Detect the resources the user allows pyqcd to use:
- CPU threads (``os.cpu_count`` / affinity)
- RAM (``/proc/meminfo``)
- GPU count & per-GPU VRAM (torch.cuda / nvidia-smi)
- Free disk space (``shutil.disk_usage``)

Used by ``pyqcd.parallel`` to plan the MPI process count following the
user formula: N*a = n*b (N processes x per-task VRAM = total usable VRAM),
batches X = m/N, and Y = N/n processes per GPU.
"""

import os
import shutil


def cpu_threads():
    """Number of usable CPU threads (respecting taskset affinity)."""
    try:
        n = len(os.sched_getaffinity(0))
        if n > 0:
            return n
    except Exception:
        pass
    try:
        return os.cpu_count() or 1
    except Exception:
        return 1


def total_memory_mb():
    """Total physical RAM in MB (None if unknown)."""
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                if line.startswith('MemTotal:'):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return None


def available_memory_mb():
    """Currently available RAM in MB (MemAvailable, None if unknown)."""
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return None


def gpu_info():
    """GPU count and per-GPU total VRAM in MB via torch / nvidia-smi.

    Returns
    -------
    ``(n_gpu, vram_per_gpu_mb, usable_vram_mb)``; known absence is
    ``(0, 0, 0)``, while failure of every detector is ``(None, None, None)``.
    usable_vram = 0.8 * per-GPU VRAM (user convention: b = 80% of card).
    """
    torch_reported_zero = False
    try:
        import torch
        n = int(torch.cuda.device_count())
        if n > 0 and torch.cuda.is_available():
            vram = torch.cuda.get_device_properties(0).total_memory // 2**20
            return n, vram, int(0.8 * vram)
        torch_reported_zero = n == 0
    except Exception:
        pass
    try:  # nvidia-smi fallback
        import subprocess
        completed = subprocess.run(
            ['nvidia-smi', '--query-gpu=memory.total',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=10)
        if completed.returncode != 0:
            raise RuntimeError('nvidia-smi resource probe failed')
        vals = [int(x) for x in completed.stdout.split()]
        if vals:
            n = len(vals)
            vram = vals[0]
            return n, vram, int(0.8 * vram)
        return 0, 0, 0
    except Exception:
        pass
    if torch_reported_zero:
        return 0, 0, 0
    return None, None, None


def free_disk_mb(path='.'):
    """Free disk space in MB at ``path``."""
    try:
        return shutil.disk_usage(path).free // 2**20
    except Exception:
        return None


def detect_resources():
    """Full resource snapshot as a dict.

    Fields: cpu_threads, mem_total_mb, mem_avail_mb, n_gpu,
    gpu_vram_mb, gpu_usable_mb, disk_free_mb.
    """
    n_gpu, vram, usable = gpu_info()
    return {
        'cpu_threads': cpu_threads(),
        'mem_total_mb': total_memory_mb(),
        'mem_avail_mb': available_memory_mb(),
        'n_gpu': n_gpu,
        'gpu_vram_mb': vram,
        'gpu_usable_mb': usable,
        'disk_free_mb': free_disk_mb(),
    }
