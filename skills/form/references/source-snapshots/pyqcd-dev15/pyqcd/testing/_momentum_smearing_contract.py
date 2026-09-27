"""蒸馏顶点动量相位与本征矢应用的独立契约测试。

本模块由 ``pyqcd.testing`` 的集中调度器注册，也可单独执行：

    python -m pyqcd.testing._momentum_smearing_contract -v

测试侧 loop oracle 固定采用 ``Pos=(z,y,x)`` 与
``exp[-i*2*pi*(pz*z/Lz + py*y/Ly + px*x/Lx)]``，以及手工的颜色
Levi-Civita 收缩，不复用生产实现。后端测试用于捕获生产代码把设备数组
经 ``np.asarray`` 强制落 host、或漏掉活动后端转换的回归。
"""
from __future__ import annotations

from itertools import permutations
import unittest

import numpy as np

from pyqcd.tools import get_backend, set_backend, set_precision
from pyqcd.vertex import (
    Mom_VVV_sink_t,
    Mom_VdV_sink_t,
    momsmear_phase,
    phase_exp_2pt,
    phase_exp_3pt,
)


def _loop_phase_oracle(momentum, lattice_shape, dtype=np.complex128):
    """独立逐点 oracle；平坦顺序固定为 z、y、x。"""
    pz, py, px = (float(value) for value in momentum)
    lz, ly, lx = (int(value) for value in lattice_shape)
    phase = np.empty(lz * ly * lx, dtype=dtype)
    index = 0
    for z in range(lz):
        for y in range(ly):
            for x in range(lx):
                angle = (pz * z / lz + py * y / ly + px * x / lx)
                phase[index] = np.exp(
                    np.asarray(-2j * np.pi * angle, dtype=dtype))
                index += 1
    return phase


def _loop_apply_oracle(eigvecs, momentum, lattice_shape):
    """独立构造 ``eigvecs * phase``，不调用任何 vertex API。"""
    eigvecs = np.asarray(eigvecs)
    phase = _loop_phase_oracle(
        momentum, lattice_shape, dtype=eigvecs.dtype)
    if eigvecs.ndim == 5:
        lz, ly, lx = lattice_shape
        phase = phase.reshape(1, lz, ly, lx, 1)
    else:
        phase = phase.reshape(1, -1, 1)
    return eigvecs * phase


def _loop_vdv_oracle(phase_exp, eigvecs):
    """独立逐点 VdV oracle，显式保留 ``(z,y,x,color)`` 轴。"""
    phase_exp = np.asarray(phase_exp)
    eigvecs = np.asarray(eigvecs)
    if phase_exp.ndim == 4:
        phase_exp = phase_exp[None, ...]
    n_mom = phase_exp.shape[0]
    nev = eigvecs.shape[0]
    result = np.zeros(
        (n_mom, nev, nev), dtype=np.result_type(phase_exp, eigvecs))
    for mom in range(n_mom):
        for left in range(nev):
            for right in range(nev):
                total = 0j
                for z in range(eigvecs.shape[1]):
                    for y in range(eigvecs.shape[2]):
                        for x in range(eigvecs.shape[3]):
                            for color in range(eigvecs.shape[4]):
                                total += (
                                    np.conj(eigvecs[left, z, y, x, color])
                                    * phase_exp[mom, z, y, x, color]
                                    * eigvecs[right, z, y, x, color]
                                )
                result[mom, left, right] = total
    return result


def _permutation_sign(permutation):
    """Return the sign of a three-color permutation."""
    inversions = sum(
        permutation[left] > permutation[right]
        for left in range(3)
        for right in range(left + 1, 3)
    )
    return -1 if inversions % 2 else 1


def _loop_vvv_oracle(phase_exp, eigvecs):
    """独立逐点 VVV oracle，按手工 Levi-Civita 置换求和。"""
    phase_exp = np.asarray(phase_exp)
    eigvecs = np.asarray(eigvecs)
    if phase_exp.ndim == 3:
        phase_exp = phase_exp[None, ...]
    n_mom = phase_exp.shape[0]
    nev = eigvecs.shape[0]
    result = np.zeros(
        (n_mom, nev, nev, nev), dtype=np.result_type(phase_exp, eigvecs))
    color_permutations = tuple(permutations(range(3)))
    for mom in range(n_mom):
        for first in range(nev):
            for second in range(nev):
                for third in range(nev):
                    total = 0j
                    for z in range(eigvecs.shape[1]):
                        for y in range(eigvecs.shape[2]):
                            for x in range(eigvecs.shape[3]):
                                color_sum = 0j
                                for a, b, c in color_permutations:
                                    color_sum += _permutation_sign((a, b, c)) * (
                                        eigvecs[first, z, y, x, a]
                                        * eigvecs[second, z, y, x, b]
                                        * eigvecs[third, z, y, x, c]
                                    )
                                total += phase_exp[mom, z, y, x] * color_sum
                    result[mom, first, second, third] = total
    return result


def _to_numpy(value):
    """将可选后端结果只用于测试断言，不参与生产计算。"""
    if hasattr(value, "detach"):
        return value.detach().cpu().numpy()
    if hasattr(value, "get") and not isinstance(value, np.ndarray):
        return np.asarray(value.get())
    return np.asarray(value)


def _apply(eigvecs, momentum, **kwargs):
    """把缺失 API 转为明确的契约失败，便于 RED 阶段诊断。"""
    try:
        from pyqcd.vertex import apply_momentum_smearing
    except ImportError as exc:  # pragma: no cover - RED 阶段的诊断分支
        raise AssertionError(
            "生产 API apply_momentum_smearing 尚未导出") from exc
    return apply_momentum_smearing(eigvecs, momentum, **kwargs)


class MomentumSmearingContract(unittest.TestCase):
    """动量涂抹的物理、布局和后端所有权契约。"""

    @classmethod
    def setUpClass(cls):
        set_backend("numpy")

    @classmethod
    def tearDownClass(cls):
        set_backend("numpy")

    def test_legacy_phase_matches_independent_loop_and_is_contiguous(self):
        """旧入口必须保持 z-y-x 平坦顺序及负指数符号。"""
        momentum = (-1.25, 0.5, 2.0)
        expected = _loop_phase_oracle(momentum, (4, 4, 4))
        actual = momsmear_phase(4, momentum)

        self.assertEqual(actual.shape, (64,))
        self.assertEqual(actual.dtype, np.dtype(np.complex128))
        self.assertTrue(actual.flags.c_contiguous)
        np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-14)

    def test_apply_full_rectangular_layout_matches_loop_oracle(self):
        """五维本征矢在矩形 Lz/Ly/Lx 上逐点应用同一相位。"""
        shape = (2, 2, 3, 4, 3)
        rng = np.random.default_rng(230831)
        eigvecs = (
            rng.normal(size=shape) + 1j * rng.normal(size=shape)
        ).astype(np.complex64)
        momentum = (-0.75, 1.5, 2.25)

        actual = _apply(eigvecs, momentum)
        expected = _loop_apply_oracle(eigvecs, momentum, shape[1:4])

        self.assertEqual(actual.shape, eigvecs.shape)
        self.assertEqual(actual.dtype, eigvecs.dtype)
        np.testing.assert_allclose(actual, expected, rtol=2e-6, atol=2e-6)

    def test_flattened_layout_requires_shape_or_strict_cubic_inference(self):
        """平坦 V 必须显式给矩形体积，只有完全立方时才可省略。"""
        rng = np.random.default_rng(230832)
        cubic = (
            rng.normal(size=(2, 27, 3))
            + 1j * rng.normal(size=(2, 27, 3))
        ).astype(np.complex128)
        rectangular = (
            rng.normal(size=(2, 24, 3))
            + 1j * rng.normal(size=(2, 24, 3))
        ).astype(np.complex128)
        momentum = (1.0, -2.0, 0.5)

        inferred = _apply(cubic, momentum)
        expected_cubic = _loop_apply_oracle(cubic, momentum, (3, 3, 3))
        np.testing.assert_allclose(inferred, expected_cubic,
                                   rtol=1e-12, atol=1e-12)

        explicit = _apply(
            rectangular, momentum, lattice_shape=(2, 3, 4))
        expected_rectangular = _loop_apply_oracle(
            rectangular, momentum, (2, 3, 4))
        np.testing.assert_allclose(explicit, expected_rectangular,
                                   rtol=1e-12, atol=1e-12)

        with self.assertRaises((TypeError, ValueError)):
            _apply(rectangular, momentum)

    def test_zero_momentum_is_identity_and_signed_momentum_is_reversible(self):
        """零动量恒等；先 p 后 -p 必须恢复原本征矢。"""
        rng = np.random.default_rng(230833)
        eigvecs = (
            rng.normal(size=(3, 2, 3, 4, 2))
            + 1j * rng.normal(size=(3, 2, 3, 4, 2))
        ).astype(np.complex64)
        momentum = (-1.25, 0.75, 2.5)

        identity = _apply(eigvecs, (0, 0, 0))
        self.assertEqual(identity.dtype, eigvecs.dtype)
        np.testing.assert_array_equal(_to_numpy(identity), eigvecs)

        recovered = _apply(_apply(eigvecs, momentum), -np.asarray(momentum))
        np.testing.assert_allclose(
            _to_numpy(recovered), eigvecs, rtol=3e-6, atol=3e-6)

    def test_spatial_gram_matrix_and_norm_are_invariant(self):
        """单位模逐点相位不得改变本征矢范数或空间 Gram 矩阵。"""
        rng = np.random.default_rng(230834)
        eigvecs = (
            rng.normal(size=(4, 2, 3, 4, 3))
            + 1j * rng.normal(size=(4, 2, 3, 4, 3))
        ).astype(np.complex128)
        smeared = _to_numpy(_apply(eigvecs, (1.25, -0.5, 2.0)))
        before = eigvecs.reshape(4, -1)
        after = smeared.reshape(4, -1)

        gram_before = before @ before.conj().T
        gram_after = after @ after.conj().T
        np.testing.assert_allclose(gram_after, gram_before,
                                   rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(
            np.sum(np.abs(after) ** 2, axis=1),
            np.sum(np.abs(before) ** 2, axis=1),
            rtol=1e-12, atol=1e-12,
        )

    def test_rejects_invalid_momentum_and_eigenvector_contracts(self):
        """错误长度、bool、复数、非有限值和非复本征矢必须显式拒绝。"""
        eigvecs = np.ones((1, 2, 2, 3, 2), dtype=np.complex128)
        invalid_momenta = (
            (0, 0),
            (0, 0, 0, 0),
            ((0, 0, 0),),
            (True, 0, 0),
            (0j, 0, 0),
            (0, np.nan, 0),
            (0, np.inf, 0),
            ("0", 0, 0),
        )
        for momentum in invalid_momenta:
            with self.subTest(momentum=momentum):
                with self.assertRaises((TypeError, ValueError)):
                    _apply(eigvecs, momentum)

        for invalid in (
            np.ones(eigvecs.shape, dtype=np.float32),
            np.ones(eigvecs.shape, dtype=np.bool_),
            np.ones((1, 2, 6), dtype=np.complex128),
            np.ones((1, 2, 2, 3), dtype=np.complex128),
        ):
            with self.subTest(dtype=invalid.dtype, shape=invalid.shape):
                with self.assertRaises((TypeError, ValueError)):
                    _apply(invalid, (0, 0, 0))

        with self.assertRaises((TypeError, ValueError)):
            _apply(eigvecs, (0, 0, 0), lattice_shape=(2, 2, 2))
        with self.assertRaises((TypeError, ValueError)):
            _apply(eigvecs.reshape(1, 12, 2), (0, 0, 0),
                   lattice_shape=(2, 2, 2))
        with self.assertRaises((TypeError, ValueError)):
            _apply(np.ones((1, 12, 2), dtype=np.complex128), (0, 0, 0))

    def test_preserves_numpy_complex_precision(self):
        """NumPy complex64/128 不得被相位常量提升。"""
        for dtype, atol in ((np.complex64, 2e-6), (np.complex128, 1e-13)):
            with self.subTest(dtype=dtype):
                eigvecs = np.ones((1, 2, 2, 2, 3), dtype=dtype)
                actual = _apply(eigvecs, (0.25, -1.5, 0.75))
                self.assertIsInstance(actual, np.ndarray)
                self.assertEqual(actual.dtype, dtype)
                self.assertFalse(np.iscomplexobj(actual) is False)
                expected = _loop_apply_oracle(
                    eigvecs, (0.25, -1.5, 0.75), (2, 2, 2))
                np.testing.assert_allclose(actual, expected,
                                           rtol=0.0, atol=atol)

    def test_torch_cpu_preserves_dtype_device_and_backend(self):
        """Torch CPU 输入输出必须保持 Tensor、CPU 和复数精度。"""
        try:
            import torch
        except ImportError as exc:
            raise unittest.SkipTest("torch 未安装") from exc

        rng = np.random.default_rng(230835)
        source = (
            rng.normal(size=(1, 2, 2, 3, 2))
            + 1j * rng.normal(size=(1, 2, 2, 3, 2))
        )
        try:
            set_backend("torch", device="cpu")
            for dtype, atol in ((torch.complex64, 3e-6),
                                (torch.complex128, 1e-12)):
                with self.subTest(dtype=dtype):
                    eigvecs = torch.from_numpy(
                        source.astype(np.complex64 if dtype == torch.complex64
                                      else np.complex128))
                    actual = _apply(eigvecs, (1.0, -0.5, 2.25))
                    self.assertIsInstance(actual, torch.Tensor)
                    self.assertEqual(actual.device.type, "cpu")
                    self.assertEqual(actual.dtype, dtype)
                    expected = _loop_apply_oracle(
                        _to_numpy(eigvecs), (1.0, -0.5, 2.25), (2, 2, 3))
                    np.testing.assert_allclose(
                        _to_numpy(actual), expected, rtol=0.0, atol=atol)
        finally:
            set_backend("numpy")

    def test_cupy_preserves_device_and_dtype_when_available(self):
        """可用 CuPy 时结果必须留在同一 GPU 且保持 complex dtype。"""
        try:
            import cupy as cp
            if cp.cuda.runtime.getDeviceCount() < 1:
                raise unittest.SkipTest("无可用 CUDA device")
        except ImportError as exc:
            raise unittest.SkipTest("cupy 未安装") from exc
        except cp.cuda.runtime.CUDARuntimeError as exc:
            raise unittest.SkipTest(f"CUDA 不可用: {exc}") from exc

        source = np.ones((1, 2, 2, 2, 3), dtype=np.complex64)
        try:
            set_backend("cupy")
            eigvecs = cp.asarray(source)
            actual = _apply(eigvecs, (-1.0, 0.5, 1.25))
            self.assertIsInstance(actual, cp.ndarray)
            self.assertEqual(actual.dtype, cp.dtype(np.complex64))
            np.testing.assert_allclose(
                _to_numpy(actual),
                _loop_apply_oracle(source, (-1.0, 0.5, 1.25), (2, 2, 2)),
                rtol=0.0, atol=2e-6,
            )
        finally:
            set_backend("numpy")

    def test_rectangular_phase_helpers_keep_legacy_cubic_call(self):
        """相位 helper 必须支持 ``(Lz,Ly,Lx)``，且不破坏旧 ``Nx`` 调用。"""
        lattice_shape = (2, 3, 4)
        momentum = (1.25, -0.5, 2.0)
        expected = _loop_phase_oracle(momentum, lattice_shape)
        set_backend("numpy")

        try:
            try:
                phase_2pt = phase_exp_2pt(lattice_shape, momentum)
                phase_3pt = phase_exp_3pt(
                    lattice_shape=lattice_shape, Mom=momentum)
                phase_2pt_kw = phase_exp_2pt(
                    lattice_shape=lattice_shape, Mom=momentum)
            except Exception as exc:
                self.fail(
                    "矩形相位 helper 不应把 lattice_shape 当 Nx 标量: "
                    f"{type(exc).__name__}: {exc}")

            np.testing.assert_allclose(
                phase_2pt,
                np.repeat(expected.reshape(lattice_shape + (1,)), 3, axis=-1),
                rtol=0.0, atol=1e-13)
            np.testing.assert_allclose(
                phase_3pt, expected.reshape(lattice_shape),
                rtol=0.0, atol=1e-13)
            np.testing.assert_array_equal(phase_2pt, phase_2pt_kw)

            cubic_shape = (3, 3, 3)
            cubic_momentum = (-1.0, 0.5, 2.0)
            cubic_expected = _loop_phase_oracle(
                cubic_momentum, cubic_shape)
            legacy_2pt = phase_exp_2pt(3, cubic_momentum)
            legacy_3pt = phase_exp_3pt(3, cubic_momentum)
            np.testing.assert_allclose(
                legacy_2pt,
                np.repeat(
                    cubic_expected.reshape(cubic_shape + (1,)),
                    3, axis=-1),
                rtol=0.0, atol=1e-13)
            np.testing.assert_allclose(
                legacy_3pt, cubic_expected.reshape(cubic_shape),
                rtol=0.0, atol=1e-13)
        finally:
            set_backend("numpy")

    def _assert_backend_value(self, value, backend_name, device,
                              np_dtype, label):
        """断言实际结果的 backend、device 与 dtype 所有权。"""
        if backend_name == "numpy":
            self.assertIsInstance(value, np.ndarray, label)
            self.assertEqual(value.dtype, np.dtype(np_dtype), label)
            return
        if backend_name == "torch":
            import torch
            self.assertIsInstance(value, torch.Tensor, label)
            self.assertEqual(value.device, torch.device(device), label)
            self.assertEqual(value.dtype, np_dtype, label)
            return
        import cupy as cp
        self.assertIsInstance(value, cp.ndarray, label)
        self.assertEqual(value.device.id, cp.cuda.Device().id, label)
        self.assertEqual(value.dtype, cp.dtype(np_dtype), label)

    def _run_rectangular_vertex_contract(self, backend_name, device=None):
        """在指定 backend 上运行独立 VdV/VVV 矩形格点契约。"""
        lattice_shape = (2, 3, 4)
        momentum = (1.25, -0.5, 2.0)
        basis_momentum = (-0.75, 1.5, 0.5)
        nev = 2
        rng = np.random.default_rng(230836)
        source = (
            rng.normal(size=(nev,) + lattice_shape + (3,))
            + 1j * rng.normal(size=(nev,) + lattice_shape + (3,))
        )

        if backend_name == "torch":
            import torch
            dtype_cases = (
                (np.complex64, torch.complex64, "complex64", 6e-5),
                (np.complex128, torch.complex128, "complex128", 2e-12),
            )
        elif backend_name == "cupy":
            import cupy as cp
            dtype_cases = (
                (np.complex64, cp.complex64, None, 6e-5),
                (np.complex128, cp.complex128, None, 2e-12),
            )
        else:
            dtype_cases = (
                (np.complex64, np.complex64, None, 6e-5),
                (np.complex128, np.complex128, None, 2e-12),
            )

        try:
            set_backend(backend_name, device=device) \
                if device is not None else set_backend(backend_name)
            backend = get_backend()
            for np_dtype, backend_dtype, precision, tolerance in dtype_cases:
                with self.subTest(backend=backend_name, dtype=np_dtype):
                    if precision is not None:
                        set_precision(precision)
                    eig_host = source.astype(np_dtype)
                    basis_host = _loop_phase_oracle(
                        basis_momentum, lattice_shape, dtype=np_dtype
                    ).reshape(lattice_shape)
                    eig_phase_host = (
                        eig_host * basis_host[None, ..., None])

                    try:
                        phase_2pt = phase_exp_2pt(lattice_shape, momentum)
                        phase_3pt = phase_exp_3pt(lattice_shape, momentum)
                    except Exception as exc:
                        self.fail(
                            "矩形 phase_exp 在活动 backend 上失败: "
                            f"{type(exc).__name__}: {exc}")

                    phase_2pt_np = _to_numpy(phase_2pt)
                    phase_3pt_np = _to_numpy(phase_3pt)
                    expected_phase = _loop_phase_oracle(
                        momentum, lattice_shape)
                    phase_tolerance = (
                        6e-5 if phase_3pt_np.dtype == np.complex64
                        else 2e-12)
                    self._assert_backend_value(
                        phase_2pt, backend_name, device,
                        backend_dtype if backend_name == "torch"
                        else phase_2pt_np.dtype,
                        "phase_exp_2pt backend/device")
                    self._assert_backend_value(
                        phase_3pt, backend_name, device,
                        backend_dtype if backend_name == "torch"
                        else phase_3pt_np.dtype,
                        "phase_exp_3pt backend/device")
                    np.testing.assert_allclose(
                        phase_2pt_np,
                        np.repeat(
                            expected_phase.reshape(lattice_shape + (1,)),
                            3, axis=-1),
                        rtol=0.0, atol=phase_tolerance)
                    np.testing.assert_allclose(
                        phase_3pt_np, expected_phase.reshape(lattice_shape),
                        rtol=0.0, atol=phase_tolerance)

                    phase_2pt_host = phase_2pt_np.astype(
                        np_dtype, copy=False)
                    phase_3pt_host = phase_3pt_np.astype(
                        np_dtype, copy=False)
                    expected_vdv = _loop_vdv_oracle(
                        phase_2pt_host, eig_host)
                    expected_vdv_phase = _loop_vdv_oracle(
                        phase_2pt_host, eig_phase_host)
                    expected_vvv = _loop_vvv_oracle(
                        phase_3pt_host, eig_host)
                    expected_vvv_phase = _loop_vvv_oracle(
                        phase_3pt_host, eig_phase_host)
                    expected_vvv_three = _loop_vvv_oracle(
                        phase_3pt_host * basis_host ** 3, eig_host)

                    # These are independent physical/layout assertions: the
                    # VdV basis phase cancels as phase* phase.conj(), while
                    # VVV receives one phase from each of three eigenvectors.
                    np.testing.assert_allclose(
                        expected_vdv_phase, expected_vdv,
                        rtol=0.0, atol=tolerance)
                    np.testing.assert_allclose(
                        expected_vvv_phase, expected_vvv_three,
                        rtol=0.0, atol=tolerance)

                    eig_backend = backend.asarray(
                        eig_host, dtype=backend_dtype)
                    phase_2pt_backend = backend.asarray(
                        phase_2pt_host, dtype=backend_dtype)
                    phase_3pt_backend = backend.asarray(
                        phase_3pt_host, dtype=backend_dtype)
                    basis_backend = backend.asarray(
                        basis_host, dtype=backend_dtype)
                    eig_phase_backend = (
                        eig_backend * basis_backend[None, ..., None])

                    try:
                        vdv = Mom_VdV_sink_t(
                            phase_2pt_backend, eig_backend)
                        vdv_phase = Mom_VdV_sink_t(
                            phase_2pt_backend, eig_phase_backend)
                        vvv = Mom_VVV_sink_t(
                            phase_3pt_backend, eig_backend)
                        vvv_phase = Mom_VVV_sink_t(
                            phase_3pt_backend, eig_phase_backend)
                        # Host arrays are also a supported numpy-like input;
                        # active backend ownership must still be preserved.
                        vdv_host = Mom_VdV_sink_t(
                            phase_2pt_host, eig_host)
                        vvv_host = Mom_VVV_sink_t(
                            phase_3pt_host, eig_host)
                    except Exception as exc:
                        self.fail(
                            f"{backend_name} vertex contraction failed: "
                            f"{type(exc).__name__}: {exc}")

                    for label, value in (
                        ("VdV", vdv),
                        ("VdV basis phase", vdv_phase),
                        ("VVV", vvv),
                        ("VVV basis phase", vvv_phase),
                        ("VdV host input", vdv_host),
                        ("VVV host input", vvv_host),
                    ):
                        self._assert_backend_value(
                            value, backend_name, device, backend_dtype, label)

                    np.testing.assert_allclose(
                        _to_numpy(vdv), expected_vdv,
                        rtol=0.0, atol=tolerance)
                    np.testing.assert_allclose(
                        _to_numpy(vdv_phase), expected_vdv_phase,
                        rtol=0.0, atol=tolerance)
                    np.testing.assert_allclose(
                        _to_numpy(vvv), expected_vvv,
                        rtol=0.0, atol=tolerance)
                    np.testing.assert_allclose(
                        _to_numpy(vvv_phase), expected_vvv_phase,
                        rtol=0.0, atol=tolerance)
                    np.testing.assert_allclose(
                        _to_numpy(vdv_host), expected_vdv,
                        rtol=0.0, atol=tolerance)
                    np.testing.assert_allclose(
                        _to_numpy(vvv_host), expected_vvv,
                        rtol=0.0, atol=tolerance)
        finally:
            set_backend("numpy")

    def test_numpy_rectangular_vertices_match_oracle(self):
        """NumPy VdV/VVV 矩形格点收缩匹配独立 oracle。"""
        self._run_rectangular_vertex_contract("numpy")

    def test_torch_cpu_rectangular_vertices_keep_backend(self):
        """Torch CPU 必须保留 Tensor、CPU device 与复数 dtype。"""
        try:
            import torch  # noqa: F401
        except ImportError as exc:
            raise unittest.SkipTest("torch 未安装") from exc
        self._run_rectangular_vertex_contract("torch", device="cpu")

    def test_torch_cuda_rectangular_vertices_keep_backend(self):
        """可用 CUDA 时 Torch 顶点不得隐式回落到 host。"""
        try:
            import torch
            if not torch.cuda.is_available():
                raise unittest.SkipTest("CUDA 不可用")
        except ImportError as exc:
            raise unittest.SkipTest("torch 未安装") from exc
        self._run_rectangular_vertex_contract("torch", device="cuda:0")

    def test_cupy_rectangular_vertices_keep_backend(self):
        """可用 CuPy/CUDA 时顶点结果必须留在同一 GPU。"""
        try:
            import cupy as cp
            if cp.cuda.runtime.getDeviceCount() < 1:
                raise unittest.SkipTest("无可用 CUDA device")
        except ImportError as exc:
            raise unittest.SkipTest("cupy 未安装") from exc
        except cp.cuda.runtime.CUDARuntimeError as exc:
            raise unittest.SkipTest(f"CUDA 不可用: {exc}") from exc
        self._run_rectangular_vertex_contract("cupy")


if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False)
    raise SystemExit(0 if result.result.wasSuccessful() else 1)
