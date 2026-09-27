"""Stout 在 torch CUDA 后端上的设备与数值契约。"""
from __future__ import annotations

import unittest

import numpy as np


def test_stout_torch_cuda_stays_on_device_and_matches_numpy():
    """CUDA 输入不得与 CPU 常量混算，结果须留在 GPU 并匹配 NumPy。"""
    import torch

    if not torch.cuda.is_available():
        raise unittest.SkipTest("torch CUDA is unavailable")

    from pyqcd.smear import stout_smear
    from pyqcd.testing import random_su3_gauge
    from pyqcd.tools import set_backend

    gauge = random_su3_gauge(L=2, seed=421)
    try:
        set_backend("numpy")
        expected = np.asarray(stout_smear(gauge, nstep=1, rho=0.12))

        set_backend("torch", device="cuda:0")
        actual = stout_smear(gauge, nstep=1, rho=0.12)
        assert actual.device.type == "cuda"
        error = float(np.max(np.abs(actual.get() - expected)))
        assert error < 1e-8, \
            f"Stout torch CUDA 与 NumPy 不一致: max|d|={error:.3e}"
    finally:
        set_backend("numpy")


def main():
    test_stout_torch_cuda_stays_on_device_and_matches_numpy()
    print("PASS test_stout_torch_cuda_stays_on_device_and_matches_numpy")


if __name__ == "__main__":
    main()
