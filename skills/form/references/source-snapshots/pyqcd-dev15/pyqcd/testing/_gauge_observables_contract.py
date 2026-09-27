"""纯数组纯规范观测量的公开 API 契约测试。

该文件故意不修改 ``pyqcd.testing.__init__``；由上层测试控制器按需注册。
测试夹具只使用 NumPy 自己生成确定性的 SU(3) 链接，因此不依赖 refer/、
历史示例树或外部二进制。
"""
from __future__ import annotations

import importlib
import unittest

import numpy as np

from pyqcd.tools import set_backend


LATTICE_SHAPE = (2, 3, 3, 4)  # (Nt, Nz, Ny, Nx)
NC = 3


def _api(test_case):
    """加载公开模块；缺失 API 必须表现为契约失败而非未处理异常。"""
    try:
        return importlib.import_module("pyqcd.gauge")
    except Exception as exc:  # pragma: no cover - RED 阶段的诊断路径
        test_case.fail(f"pyqcd.gauge 公开 API 不可导入: {exc}")


def _random_su3_links(shape=LATTICE_SHAPE, seed=90210):
    """生成逐链接确定性的 SU(3) 基本表示规范场。"""
    rng = np.random.default_rng(seed)
    links = np.empty(shape + (4, NC, NC), dtype=np.complex128)
    for site in np.ndindex(shape):
        for direction in range(4):
            z = rng.normal(size=(NC, NC)) + 1j * rng.normal(size=(NC, NC))
            q, _ = np.linalg.qr(z)
            phase = np.linalg.det(q)
            q[:, -1] *= np.conj(phase / abs(phase))
            links[site + (direction,)] = q
    return links


def _identity_links(shape=LATTICE_SHAPE):
    """恒等规范场。"""
    identity = np.eye(NC, dtype=np.complex128)
    return np.broadcast_to(identity, shape + (4, NC, NC)).copy()


def _require_torch(test_case, *, cuda=False):
    """按需加载 Torch，并在目标设备不可用时清晰跳过。"""
    try:
        import torch
    except ImportError:
        raise unittest.SkipTest("torch is unavailable")
    if cuda and not torch.cuda.is_available():
        raise unittest.SkipTest("CUDA is unavailable")
    return torch


def _require_cuda_torch(test_case):
    """CUDA 回归门必须在当前 CUDA 可用时实测，不能静默跳过。"""
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - 当前验收环境必须安装
        test_case.fail(f"CUDA 回归需要 Torch，但导入失败: {exc}")
    test_case.assertTrue(
        torch.cuda.is_available(),
        "当前 CUDA 应可用；设备继承/CPU-GPU oracle 不得以 skip 掩盖失败",
    )
    return torch


def _torch_identity_links(torch, *, dtype, device):
    """在指定 Torch 设备上生成确定性的恒等规范场。"""
    identity = torch.eye(NC, dtype=dtype, device=device)
    return identity.reshape((1,) * 5 + (NC, NC)).expand(
        LATTICE_SHAPE + (4, NC, NC)).clone()


def _uniform_abelian_two_plane_field(shape=(2, 2, 2, 2)):
    """构造同时带有 (0,1) 与 (2,3) 周期磁通的 Abelian SU(3) 场。"""
    nt, nz, ny, nx = shape
    generator_diag = np.array([0.5, -0.5, 0.0])
    generator = np.diag(generator_diag)
    links = _identity_links(shape)

    phi01 = 4.0 * np.pi / (ny * nx)
    for t in range(nt):
        for z in range(nz):
            for y in range(ny):
                links[t, z, y, :, 0] = np.diag(
                    np.exp(-1j * phi01 * y * generator_diag))
            for x in range(nx):
                links[t, z, ny - 1, x, 1] = np.diag(
                    np.exp(1j * phi01 * ny * x * generator_diag))

    phi23 = 4.0 * np.pi / (nt * nz)
    for y in range(ny):
        for x in range(nx):
            for t in range(nt):
                links[t, :, y, x, 2] = np.diag(
                    np.exp(-1j * phi23 * t * generator_diag))
            for z in range(nz):
                links[nt - 1, z, y, x, 3] = np.diag(
                    np.exp(1j * phi23 * nt * z * generator_diag))

    f01 = 2.0 * np.sin(phi01 / 2.0) * generator
    f23 = 2.0 * np.sin(phi23 / 2.0) * generator
    expected_q = np.trace(f01 @ f23).real / (4.0 * np.pi ** 2)
    return links, f01, f23, expected_q


def _local_su3_transform(shape=LATTICE_SHAPE, seed=90211):
    """确定性的局域对角 SU(3) 规范变换 G(x)。"""
    rng = np.random.default_rng(seed)
    angles = rng.normal(size=shape + (2,))
    transform = np.zeros(shape + (NC, NC), dtype=np.complex128)
    transform[..., 0, 0] = np.exp(1j * angles[..., 0])
    transform[..., 1, 1] = np.exp(1j * angles[..., 1])
    transform[..., 2, 2] = np.exp(-1j * (angles[..., 0] + angles[..., 1]))
    return transform


def _gauge_transform(links, transform):
    """U'_mu(x)=G(x) U_mu(x) G(x+mu)^dagger。"""
    transformed = np.empty_like(links)
    for direction in range(4):
        axis = 3 - direction
        next_transform = np.roll(transform, -1, axis=axis)
        transformed[..., direction, :, :] = (
            transform
            @ links[..., direction, :, :]
            @ next_transform.conj().swapaxes(-1, -2)
        )
    return transformed


def _shift(field, offsets):
    """按方向标签把场从起点 x 取到 x+sum(offsets)*hat(direction)。"""
    shifted = field
    for direction, offset in offsets:
        if offset:
            shifted = np.roll(shifted, -offset, axis=3 - direction)
    return shifted


def _adjoint(matrix):
    return matrix.conj().swapaxes(-1, -2)


def _manual_wilson_field(links, R, T, mu, nu):
    """独立的四段路径 oracle，逐步使用回程链接的真正逆。"""
    out = np.empty(links.shape[:4], dtype=np.float64)
    identity = np.eye(links.shape[-1], dtype=links.dtype)
    for base in np.ndindex(*links.shape[:4]):
        position = list(base)
        product = identity.copy()

        def take_link(direction, sign):
            axis = 3 - direction
            if sign > 0:
                link = links[tuple(position) + (direction,)]
                position[axis] = (position[axis] + 1) % links.shape[axis]
            else:
                position[axis] = (position[axis] - 1) % links.shape[axis]
                link = _adjoint(links[tuple(position) + (direction,)])
            return link

        for _ in range(R):
            product = product @ take_link(mu, +1)
        for _ in range(T):
            product = product @ take_link(nu, +1)
        for _ in range(R):
            product = product @ take_link(mu, -1)
        for _ in range(T):
            product = product @ take_link(nu, -1)
        out[base] = np.trace(product).real / links.shape[-1]
    return out


def _current_plaquette_field(links, mu, nu):
    """当前 ``wilson_action_density`` 使用的正向 1x1 plaquette。"""
    axis_mu, axis_nu = 3 - mu, 3 - nu
    u_mu = links[..., mu, :, :]
    u_nu = links[..., nu, :, :]
    plaquette = (
        u_mu
        @ np.roll(u_nu, -1, axis=axis_mu)
        @ _adjoint(np.roll(u_mu, -1, axis=axis_nu))
        @ _adjoint(u_nu)
    )
    return np.trace(plaquette, axis1=-2, axis2=-1).real / links.shape[-1]


def _legacy_clover_fields(links):
    """用既有 ``plaquette_clover`` 构造未去迹的六个独立平面。"""
    from pyqcd.operator import plaquette_clover

    return {
        (mu, nu): np.asarray(plaquette_clover(links, mu, nu))
        for mu in range(4) for nu in range(mu + 1, 4)
    }


def _project_traceless(field):
    """独立执行颜色空间 ``su(Nc)`` 投影。"""
    nc = field.shape[-1]
    trace = np.trace(field, axis1=-2, axis2=-1)
    return field - (trace / nc)[..., None, None] * np.eye(
        nc, dtype=field.dtype)


def _topological_density_from_fields(fields):
    """按 epsilon 展开的三项式从六个场强计算逐点 q。"""
    def trace(left, right):
        return np.einsum("...ab,...ba->...", left, right)

    density = (
        trace(fields[(0, 1)], fields[(2, 3)])
        - trace(fields[(0, 2)], fields[(1, 3)])
        + trace(fields[(0, 3)], fields[(1, 2)])
    )
    return density.real / (4.0 * np.pi ** 2)


def _to_numpy(value):
    if hasattr(value, "detach"):
        return value.detach().cpu().numpy()
    if hasattr(value, "get"):
        return value.get()
    return np.asarray(value)


class GaugeObservablesContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        set_backend("numpy")

    def tearDown(self):
        set_backend("numpy")

    def test_public_api_is_available(self):
        """纯规范包必须导出四类观测量及其平均/总量入口。"""
        api = _api(self)
        for name in (
            "wilson_rectangle",
            "wilson_loop",
            "polyakov_loop",
            "polyakov_loop_average",
            "clover_topological_charge_density",
            "clover_topological_charge",
            "clover_topological_charge_density_average",
        ):
            self.assertTrue(callable(getattr(api, name, None)), name)

    def test_zero_color_dimension_is_rejected(self):
        """不存在颜色分量的数组不是有效规范场，必须在退化圈前拒绝。"""
        api = _api(self)
        links = np.empty(LATTICE_SHAPE + (4, 0, 0), dtype=np.complex128)
        with self.assertRaises(ValueError):
            api.wilson_rectangle(links, 0, 0, 0, 1)

    def test_non_numeric_gauge_dtype_is_rejected(self):
        """对象 dtype 不能伪装成规范场并绕过零面积分支校验。"""
        api = _api(self)
        links = np.empty(LATTICE_SHAPE + (4, NC, NC), dtype=object)
        with self.assertRaises(ValueError):
            api.wilson_rectangle(links, 0, 0, 0, 1)

    def test_numpy_bool_and_integer_gauge_dtypes_are_rejected(self):
        """NumPy 物理规范场只接受浮点或复数 dtype。"""
        api = _api(self)
        for dtype in (np.bool_, np.int32, np.uint32, np.int64):
            links = np.zeros(LATTICE_SHAPE + (4, NC, NC), dtype=dtype)
            with self.assertRaisesRegex(ValueError, "浮点或复数"):
                api.wilson_rectangle(links, 0, 0, 0, 1)

    def test_torch_cpu_bool_and_integer_gauge_dtypes_are_rejected(self):
        """Torch CPU 物理规范场只接受浮点或复数 dtype。"""
        torch = _require_torch(self)
        api = _api(self)
        set_backend("torch", device="cpu")
        for dtype in (torch.bool, torch.int32, torch.int64):
            links = torch.zeros(LATTICE_SHAPE + (4, NC, NC), dtype=dtype)
            with self.assertRaisesRegex(ValueError, "浮点或复数"):
                api.wilson_rectangle(links, 0, 0, 0, 1)

    def test_numpy_unsupported_precision_dtypes_are_rejected_early(self):
        """NumPy 半精度/扩展精度不能进入 Clover 后才由底层崩溃。"""
        api = _api(self)
        for dtype in (np.float16, np.longdouble, np.clongdouble):
            links = np.zeros(
                (1, 1, 1, 1, 4, NC, NC), dtype=dtype)
            with self.assertRaisesRegex(
                    ValueError, r"仅支持.*float32.*complex128"):
                api.clover_field_strength(links, 0, 1)

    def test_torch_unsupported_precision_dtypes_are_rejected_early(self):
        """Torch float16/bfloat16/complex32 必须在公开入口明确拒绝。"""
        torch = _require_torch(self)
        api = _api(self)
        set_backend("torch", device="cpu")
        dtypes = [torch.float16, torch.bfloat16]
        if hasattr(torch, "complex32"):
            dtypes.append(torch.complex32)
        for dtype in dtypes:
            if dtype == getattr(torch, "complex32", None):
                # 直接 zeros(complex32) 会触发 Torch 的实验性 dtype warning；
                # view_as_complex 是等价且无 warning 的可构造路径。
                links = torch.view_as_complex(torch.zeros(
                    (1, 1, 1, 1, 4, NC, NC, 2), dtype=torch.float16))
            else:
                links = torch.zeros(
                    (1, 1, 1, 1, 4, NC, NC), dtype=dtype)
            try:
                api.clover_field_strength(links, 0, 1)
            except ValueError as exc:
                self.assertRegex(str(exc), r"仅支持.*float32.*complex128")
            except Exception as exc:
                self.fail(
                    f"dtype={dtype} 应早期抛 ValueError，实际为 "
                    f"{type(exc).__name__}: {exc}")
            else:
                self.fail(f"dtype={dtype} 必须被公开 Clover 入口拒绝")

    def test_cupy_unsupported_precision_dtypes_are_rejected_early(self):
        """CuPy 与 NumPy 使用同一组精确支持的 32/64 位 dtype。"""
        try:
            import cupy
        except ImportError:
            raise unittest.SkipTest("cupy is unavailable")

        api = _api(self)
        set_backend("cupy")
        dtypes = [cupy.float16]
        for name in ("longdouble", "clongdouble"):
            dtype = getattr(cupy, name, None)
            if dtype is not None:
                dtypes.append(dtype)
        for dtype in dtypes:
            links = cupy.zeros((1, 1, 1, 1, 4, NC, NC), dtype=dtype)
            with self.assertRaisesRegex(
                    ValueError, r"仅支持.*float32.*complex128"):
                api.clover_field_strength(links, 0, 1)

    def test_supported_float_and_complex_dtypes_keep_reasonable_outputs(self):
        """浮点/复数 gauge 保持对应实部、复数观测量精度。"""
        api = _api(self)
        cases = (
            (np.float32, np.float32, np.complex64),
            (np.float64, np.float64, np.complex128),
            (np.complex64, np.float32, np.complex64),
            (np.complex128, np.float64, np.complex128),
        )
        for dtype, real_dtype, complex_dtype in cases:
            polyakov_dtype = (
                complex_dtype
                if np.issubdtype(dtype, np.complexfloating)
                else real_dtype)
            links = np.broadcast_to(
                np.eye(NC, dtype=dtype),
                (1, 1, 1, 1, 4, NC, NC)).copy()
            set_backend("numpy")
            numpy_zero = api.wilson_rectangle(
                links, 0, 0, 0, 1, average=False)
            numpy_polyakov = api.polyakov_loop(links)
            numpy_field = api.clover_field_strength(links, 0, 1)
            numpy_density = api.clover_topological_charge_density(links)
            self.assertEqual(numpy_zero.dtype, np.dtype(real_dtype))
            self.assertEqual(numpy_polyakov.dtype, np.dtype(polyakov_dtype))
            self.assertEqual(numpy_field.dtype, np.dtype(complex_dtype))
            self.assertEqual(numpy_density.dtype, np.dtype(real_dtype))

            torch = _require_torch(self)
            set_backend("torch", device="cpu")
            torch_zero = api.wilson_rectangle(
                links, 0, 0, 0, 1, average=False)
            torch_polyakov = api.polyakov_loop(links)
            torch_field = api.clover_field_strength(links, 0, 1)
            torch_density = api.clover_topological_charge_density(links)
            expected_real = getattr(torch, str(np.dtype(real_dtype)))
            expected_complex = getattr(torch, str(np.dtype(complex_dtype)))
            expected_polyakov = getattr(torch, str(np.dtype(polyakov_dtype)))
            self.assertEqual(torch_zero.dtype, expected_real)
            self.assertEqual(torch_polyakov.dtype, expected_polyakov)
            self.assertEqual(torch_field.dtype, expected_complex)
            self.assertEqual(torch_density.dtype, expected_real)

    def test_torch_cuda_zero_area_wilson_stays_on_input_device(self):
        """CUDA 零面积 Wilson 圈不能因 ones 默认值回落到 CPU。"""
        torch = _require_torch(self, cuda=True)
        api = _api(self)
        links = _torch_identity_links(
            torch, dtype=torch.complex128, device=torch.device("cuda"))
        set_backend("torch")

        try:
            local = api.wilson_rectangle(
                links, 0, 0, 0, 1, average=False)
        except Exception as exc:
            self.fail(f"零面积 Wilson 在 {links.device} 上异常: {exc}")
        self.assertEqual(local.device, links.device)
        self.assertEqual(local.dtype, torch.float64)
        np.testing.assert_allclose(_to_numpy(local), 1.0,
                                   rtol=0.0, atol=0.0)

    def test_torch_cuda_nonzero_wilson_stays_on_input_device(self):
        """CUDA 非零面积 Wilson 圈的矩阵乘积不能混入 CPU identity。"""
        torch = _require_torch(self, cuda=True)
        api = _api(self)
        links = _torch_identity_links(
            torch, dtype=torch.complex128, device=torch.device("cuda"))
        set_backend("torch")

        try:
            local = api.wilson_rectangle(
                links, 1, 1, 0, 1, average=False)
        except Exception as exc:
            self.fail(f"非零 Wilson 在 {links.device} 上异常: {exc}")
        self.assertEqual(local.device, links.device)
        self.assertEqual(local.dtype, torch.float64)
        np.testing.assert_allclose(_to_numpy(local), 1.0,
                                   rtol=0.0, atol=0.0)

    def test_torch_cuda_polyakov_stays_on_input_device_and_keeps_phase(self):
        """CUDA Polyakov 圈保持设备所有权和 SU(3) 中心复相位。"""
        torch = _require_torch(self, cuda=True)
        api = _api(self)
        links = _torch_identity_links(
            torch, dtype=torch.complex128, device=torch.device("cuda"))
        center = np.exp(2j * np.pi / 3.0)
        links[0, ..., 3, :, :] = center * torch.eye(
            NC, dtype=links.dtype, device=links.device)
        set_backend("torch")

        try:
            local = api.polyakov_loop(links)
        except Exception as exc:
            self.fail(f"Polyakov 圈在 {links.device} 上异常: {exc}")
        self.assertEqual(local.device, links.device)
        self.assertEqual(local.dtype, torch.complex128)
        np.testing.assert_allclose(_to_numpy(local), center,
                                   rtol=0.0, atol=2e-15)

    def test_torch_cuda_clover_field_strength_stays_on_input_device(self):
        """CUDA Clover 场强的去迹 identity 必须与输入同设备同 dtype。"""
        torch = _require_torch(self, cuda=True)
        api = _api(self)
        links = _torch_identity_links(
            torch, dtype=torch.complex128, device=torch.device("cuda"))
        set_backend("torch")

        try:
            field = api.clover_field_strength(links, 0, 1)
        except Exception as exc:
            self.fail(f"Clover 场强在 {links.device} 上异常: {exc}")
        self.assertEqual(field.device, links.device)
        self.assertEqual(field.dtype, torch.complex128)
        np.testing.assert_allclose(_to_numpy(field), 0.0,
                                   rtol=0.0, atol=0.0)

    def test_torch_cuda_topological_charge_stays_on_input_device(self):
        """CUDA 拓扑密度与总荷都必须在输入设备上归约。"""
        torch = _require_torch(self, cuda=True)
        api = _api(self)
        links = _torch_identity_links(
            torch, dtype=torch.complex128, device=torch.device("cuda"))
        set_backend("torch")

        try:
            density = api.clover_topological_charge_density(links)
            charge = api.clover_topological_charge(links)
        except Exception as exc:
            self.fail(f"拓扑荷在 {links.device} 上异常: {exc}")
        self.assertEqual(density.device, links.device)
        self.assertEqual(density.dtype, torch.float64)
        self.assertEqual(charge.device, links.device)
        self.assertEqual(charge.dtype, torch.float64)
        np.testing.assert_allclose(_to_numpy(density), 0.0,
                                   rtol=0.0, atol=0.0)
        np.testing.assert_allclose(_to_numpy(charge), 0.0,
                                   rtol=0.0, atol=0.0)

    def test_torch_cuda_input_device_wins_over_mismatched_global_device(self):
        """全局 CPU 与 CUDA 输入冲突时，所有公开观测量都继承输入设备。"""
        torch = _require_cuda_torch(self)
        api = _api(self)
        links_np = _random_su3_links(shape=(2, 2, 2, 2), seed=90223)

        set_backend("torch", device="cpu")
        cpu_links = torch.as_tensor(
            links_np, dtype=torch.complex64, device="cpu")
        cpu_outputs = {
            "wilson_rectangle": api.wilson_rectangle(
                cpu_links, 2, 3, 0, 3, average=False),
            "wilson_loop": api.wilson_loop(
                cpu_links, 2, 3, 0, 3, average=False),
            "polyakov_loop": api.polyakov_loop(cpu_links),
            "polyakov_loop_average": api.polyakov_loop_average(cpu_links),
            "clover_field_strength": api.clover_field_strength(
                cpu_links, 0, 1),
            "topological_density": api.clover_topological_charge_density(
                cpu_links),
            "topological_charge": api.clover_topological_charge(cpu_links),
            "topological_density_average": (
                api.clover_topological_charge_density_average(cpu_links)),
        }

        cuda_links = torch.as_tensor(
            links_np, dtype=torch.complex64, device=torch.device("cuda"))
        cuda_outputs = {
            "wilson_rectangle": api.wilson_rectangle(
                cuda_links, 2, 3, 0, 3, average=False),
            "wilson_loop": api.wilson_loop(
                cuda_links, 2, 3, 0, 3, average=False),
            "polyakov_loop": api.polyakov_loop(cuda_links),
            "polyakov_loop_average": api.polyakov_loop_average(cuda_links),
            "clover_field_strength": api.clover_field_strength(
                cuda_links, 0, 1),
            "topological_density": api.clover_topological_charge_density(
                cuda_links),
            "topological_charge": api.clover_topological_charge(cuda_links),
            "topological_density_average": (
                api.clover_topological_charge_density_average(cuda_links)),
        }
        expected_dtypes = {
            "wilson_rectangle": torch.float32,
            "wilson_loop": torch.float32,
            "polyakov_loop": torch.complex64,
            "polyakov_loop_average": torch.complex64,
            "clover_field_strength": torch.complex64,
            "topological_density": torch.float32,
            "topological_charge": torch.float32,
            "topological_density_average": torch.float32,
        }

        for name, got in cuda_outputs.items():
            self.assertEqual(got.device, cuda_links.device, name)
            self.assertEqual(got.dtype, expected_dtypes[name], name)
            np.testing.assert_allclose(
                _to_numpy(got), _to_numpy(cpu_outputs[name]),
                rtol=3e-5, atol=3e-6, err_msg=name)

    def test_torch_cuda_nontrivial_observables_match_independent_oracles(self):
        """非平凡 CUDA 场同时通过手写 Wilson 与解析 Clover/拓扑 oracle。"""
        torch = _require_cuda_torch(self)
        api = _api(self)
        random_links = _random_su3_links(
            shape=(2, 2, 2, 2), seed=90224)
        expected_wilson = _manual_wilson_field(
            random_links, 2, 3, 0, 3)

        # 故意保持全局默认设备为 CPU，检查输入 CUDA 设备不会被覆盖。
        set_backend("torch", device="cpu")
        random_cuda = torch.as_tensor(
            random_links, dtype=torch.complex64, device="cuda")
        actual_wilson = api.wilson_rectangle(
            random_cuda, 2, 3, 0, 3, average=False)
        self.assertEqual(actual_wilson.device, random_cuda.device)
        np.testing.assert_allclose(
            _to_numpy(actual_wilson), expected_wilson,
            rtol=3e-5, atol=3e-6)

        abelian_links, expected_f01, expected_f23, expected_q = (
            _uniform_abelian_two_plane_field())
        abelian_cuda = torch.as_tensor(
            abelian_links, dtype=torch.complex64, device="cuda")
        actual_f01 = api.clover_field_strength(
            abelian_cuda, 0, 1)
        actual_f23 = api.clover_field_strength(
            abelian_cuda, 2, 3)
        actual_density = api.clover_topological_charge_density(
            abelian_cuda)
        self.assertEqual(actual_f01.device, abelian_cuda.device)
        self.assertEqual(actual_f23.device, abelian_cuda.device)
        self.assertEqual(actual_density.device, abelian_cuda.device)
        np.testing.assert_allclose(
            _to_numpy(actual_f01),
            np.broadcast_to(expected_f01, abelian_links.shape[:4] + (NC, NC)),
            rtol=3e-5, atol=3e-6)
        np.testing.assert_allclose(
            _to_numpy(actual_f23),
            np.broadcast_to(expected_f23, abelian_links.shape[:4] + (NC, NC)),
            rtol=3e-5, atol=3e-6)
        np.testing.assert_allclose(
            _to_numpy(actual_density), expected_q,
            rtol=3e-5, atol=3e-6)

    def test_clover_topological_density_matches_two_plane_analytic_field(self):
        """双平面 Abelian oracle 锁定 Clover 归一化、epsilon 正号和系数。"""
        api = _api(self)
        links, expected_f01, expected_f23, expected_q = (
            _uniform_abelian_two_plane_field())
        expected_f01 = np.broadcast_to(
            expected_f01, links.shape[:4] + expected_f01.shape)
        expected_f23 = np.broadcast_to(
            expected_f23, links.shape[:4] + expected_f23.shape)

        f01 = _to_numpy(api.clover_field_strength(links, 0, 1))
        f23 = _to_numpy(api.clover_field_strength(links, 2, 3))
        np.testing.assert_allclose(
            f01, expected_f01, rtol=2e-13, atol=2e-13)
        np.testing.assert_allclose(
            f23, expected_f23, rtol=2e-13, atol=2e-13)
        np.testing.assert_allclose(
            f01, _adjoint(f01), rtol=2e-13, atol=2e-13)
        np.testing.assert_allclose(
            _to_numpy(api.clover_field_strength(links, 1, 0)), -f01,
            rtol=2e-13, atol=2e-13)

        density = _to_numpy(api.clover_topological_charge_density(links))
        np.testing.assert_allclose(
            density, expected_q, rtol=2e-13, atol=2e-13)
        np.testing.assert_allclose(
            _to_numpy(api.clover_topological_charge(links)),
            expected_q * density.size, rtol=2e-13, atol=2e-13)

    def test_clover_field_strength_is_traceless_by_default(self):
        """public 场强默认必须落在 su(3)，删除去迹投影时本测试失败。"""
        api = _api(self)
        links = _random_su3_links(shape=(2, 2, 2, 2), seed=90218)

        for mu, nu in ((0, 1), (0, 3), (1, 2), (2, 3)):
            field = _to_numpy(api.clover_field_strength(links, mu, nu))
            trace = np.trace(field, axis1=-2, axis2=-1)
            np.testing.assert_allclose(trace, 0.0, rtol=0.0, atol=3e-13)

    def test_topological_density_uses_traceless_clover_by_default(self):
        """默认 q 必须匹配 legacy Clover 经独立 su(3) 投影后的 oracle。"""
        api = _api(self)
        links = _random_su3_links(shape=(2, 2, 2, 2), seed=90219)
        projected = {
            pair: _project_traceless(field)
            for pair, field in _legacy_clover_fields(links).items()
        }
        expected = _topological_density_from_fields(projected)
        actual = _to_numpy(api.clover_topological_charge_density(links))

        np.testing.assert_allclose(actual, expected, rtol=2e-13,
                                   atol=2e-13)

    def test_clover_untraced_option_matches_legacy_plaquette_clover(self):
        """兼容开关必须复现既有未去迹 Clover；删除该分支时本测试失败。"""
        api = _api(self)
        links = _random_su3_links(shape=(2, 2, 2, 2), seed=90220)
        legacy = _legacy_clover_fields(links)
        self.assertGreater(max(
            np.max(np.abs(np.trace(field, axis1=-2, axis2=-1)))
            for field in legacy.values()), 1e-2)

        for pair, expected in legacy.items():
            try:
                actual = _to_numpy(api.clover_field_strength(
                    links, *pair, traceless=False))
            except TypeError as exc:
                self.fail(f"clover_field_strength 缺少 traceless 开关: {exc}")
            np.testing.assert_allclose(actual, expected, rtol=2e-13,
                                       atol=2e-13)

    def test_topological_untraced_option_matches_legacy_oracle(self):
        """显式未去迹 q 必须保留历史离散值，而不能仍走默认 su(3) 投影。"""
        api = _api(self)
        links = _random_su3_links(shape=(2, 2, 2, 2), seed=90221)
        legacy = _legacy_clover_fields(links)
        expected = _topological_density_from_fields(legacy)
        projected = _topological_density_from_fields({
            pair: _project_traceless(field)
            for pair, field in legacy.items()
        })
        self.assertGreater(np.max(np.abs(expected - projected)), 1e-5)

        try:
            actual = _to_numpy(api.clover_topological_charge_density(
                links, traceless=False))
        except TypeError as exc:
            self.fail(f"拓扑密度缺少 traceless 开关: {exc}")
        np.testing.assert_allclose(actual, expected, rtol=2e-13,
                                   atol=2e-13)

    def test_topological_reductions_forward_traceless_option(self):
        """总荷与体积平均必须归约所请求的未去迹密度。"""
        api = _api(self)
        links = _random_su3_links(shape=(2, 2, 2, 2), seed=90222)
        try:
            density = _to_numpy(api.clover_topological_charge_density(
                links, traceless=False))
            total = _to_numpy(api.clover_topological_charge(
                links, traceless=False))
            average = _to_numpy(
                api.clover_topological_charge_density_average(
                    links, traceless=False))
            average_alias = _to_numpy(api.clover_topological_charge_average(
                links, traceless=False))
        except TypeError as exc:
            self.fail(f"拓扑归约入口未透传 traceless 开关: {exc}")

        np.testing.assert_allclose(total, density.sum(), rtol=2e-13,
                                   atol=2e-13)
        np.testing.assert_allclose(average, density.mean(), rtol=2e-13,
                                   atol=2e-13)
        np.testing.assert_allclose(average_alias, density.mean(),
                                   rtol=2e-13, atol=2e-13)

    def test_traceless_flag_rejects_non_boolean_values(self):
        """整数真值不能静默改变 public Clover 的物理约定。"""
        api = _api(self)
        links = _identity_links(shape=(1, 1, 1, 1))
        try:
            api.clover_field_strength(links, 0, 1, traceless=1)
        except ValueError:
            pass
        except TypeError as exc:
            self.fail(f"clover_field_strength 缺少 traceless 开关: {exc}")
        else:
            self.fail("traceless=1 必须抛出 ValueError")

    def test_real_identity_links_are_supported_by_clover(self):
        """实 dtype 的恒等链接也应能进入 Clover 零场极限。"""
        api = _api(self)
        links = np.broadcast_to(
            np.eye(NC), LATTICE_SHAPE + (4, NC, NC)).copy()

        field = _to_numpy(api.clover_field_strength(links, 0, 1))
        density = _to_numpy(api.clover_topological_charge_density(links))
        np.testing.assert_allclose(field, 0.0, rtol=0.0, atol=0.0)
        np.testing.assert_allclose(density, 0.0, rtol=0.0, atol=0.0)

    def test_identity_field_has_unit_loops_and_zero_clover_charge(self):
        """恒等场满足 W=P=1，且逐点 q、总 Q、体积平均都为零。"""
        api = _api(self)
        links = _identity_links()

        for R, T in ((0, 0), (0, 2), (3, 0), (2, 3)):
            local = _to_numpy(api.wilson_rectangle(
                links, R, T, 0, 3, average=False))
            self.assertEqual(local.shape, links.shape[:4])
            np.testing.assert_allclose(local, 1.0, rtol=0.0, atol=0.0)
            self.assertAlmostEqual(
                float(_to_numpy(api.wilson_rectangle(links, R, T, 0, 3))),
                1.0, places=14)

        polyakov = _to_numpy(api.polyakov_loop(links))
        self.assertEqual(polyakov.shape, links.shape[1:4])
        np.testing.assert_allclose(polyakov, 1.0, rtol=0.0, atol=0.0)
        np.testing.assert_allclose(
            _to_numpy(api.polyakov_loop_average(links)), 1.0 + 0.0j,
            rtol=0.0, atol=0.0)

        density = _to_numpy(api.clover_topological_charge_density(links))
        self.assertEqual(density.shape, links.shape[:4])
        np.testing.assert_allclose(density, 0.0, rtol=0.0, atol=0.0)
        self.assertAlmostEqual(
            float(_to_numpy(api.clover_topological_charge(links))), 0.0,
            places=14)
        self.assertAlmostEqual(
            float(_to_numpy(api.clover_topological_charge_density_average(
                links))), 0.0, places=14)

    def test_one_by_one_wilson_rectangle_matches_current_plaquette(self):
        """1x1 圈必须逐起点复现当前 Wilson plaquette 定义。"""
        api = _api(self)
        links = _random_su3_links()
        for mu, nu in ((0, 1), (0, 3), (2, 3)):
            expected = _current_plaquette_field(links, mu, nu)
            actual = _to_numpy(api.wilson_rectangle(
                links, 1, 1, mu, nu, average=False))
            np.testing.assert_allclose(actual, expected, rtol=2e-13,
                                       atol=2e-13)
            np.testing.assert_allclose(
                _to_numpy(api.wilson_rectangle(links, 1, 1, mu, nu)),
                expected.mean(), rtol=2e-13, atol=2e-13)

    def test_rectangle_uses_periodic_geometry_and_true_inverse_links(self):
        """跨边界矩形必须遵循四段有序路径及真实逆链接。"""
        api = _api(self)
        links = _random_su3_links(shape=(2, 2, 3, 3), seed=90212)
        R, T, mu, nu = 4, 3, 0, 3
        expected = _manual_wilson_field(links, R, T, mu, nu)
        actual = _to_numpy(api.wilson_rectangle(
            links, R, T, mu, nu, average=False))
        np.testing.assert_allclose(actual, expected, rtol=2e-12, atol=2e-12)

        reversed_orientation = _to_numpy(api.wilson_rectangle(
            links, T, R, nu, mu, average=False))
        np.testing.assert_allclose(
            reversed_orientation, actual, rtol=2e-12, atol=2e-12)

    def test_polyakov_loop_is_time_ordered_and_spatially_pointwise(self):
        """Polyakov 圈返回空间逐点场，并匹配完整时间方向有序乘积。"""
        api = _api(self)
        links = _random_su3_links(seed=90213)
        expected = np.empty(links.shape[1:4], dtype=np.complex128)
        for base in np.ndindex(*links.shape[1:4]):
            product = np.eye(NC, dtype=links.dtype)
            t = 0
            for _ in range(links.shape[0]):
                product = product @ links[(t,) + base + (3,)]
                t = (t + 1) % links.shape[0]
            expected[base] = np.trace(product) / NC

        actual = _to_numpy(api.polyakov_loop(links, time_dir=3))
        np.testing.assert_allclose(actual, expected, rtol=2e-13, atol=2e-13)
        np.testing.assert_allclose(
            _to_numpy(api.polyakov_loop_average(links)), expected.mean(),
            rtol=2e-13, atol=2e-13)

    def test_polyakov_loop_preserves_complex_center_phase(self):
        """Polyakov 圈必须保留 SU(3) 中心变换产生的复相位。"""
        api = _api(self)
        links = _identity_links()
        center = np.exp(2j * np.pi / 3.0)
        links[0, ..., 3, :, :] = center * np.eye(NC, dtype=links.dtype)

        expected = np.full(links.shape[1:4], center, dtype=np.complex128)
        actual = _to_numpy(api.polyakov_loop(links))
        np.testing.assert_allclose(actual, expected, rtol=0.0, atol=2e-15)
        np.testing.assert_allclose(
            _to_numpy(api.polyakov_loop_average(links)), center,
            rtol=0.0, atol=2e-15)

    def test_local_su3_gauge_transform_leaves_all_observables_invariant(self):
        """确定性局域 SU(3) 变换下闭合圈、Polyakov 圈和 q 都不变。"""
        api = _api(self)
        links = _random_su3_links(seed=90214)
        transformed = _gauge_transform(links, _local_su3_transform())

        wilson = _to_numpy(api.wilson_rectangle(
            links, 2, 3, 1, 3, average=False))
        transformed_wilson = _to_numpy(api.wilson_rectangle(
            transformed, 2, 3, 1, 3, average=False))
        np.testing.assert_allclose(transformed_wilson, wilson,
                                   rtol=2e-12, atol=2e-12)

        polyakov = _to_numpy(api.polyakov_loop(links))
        transformed_polyakov = _to_numpy(api.polyakov_loop(transformed))
        np.testing.assert_allclose(transformed_polyakov, polyakov,
                                   rtol=2e-12, atol=2e-12)

        density = _to_numpy(api.clover_topological_charge_density(links))
        transformed_density = _to_numpy(
            api.clover_topological_charge_density(transformed))
        np.testing.assert_allclose(transformed_density, density,
                                   rtol=2e-11, atol=2e-11)
        np.testing.assert_allclose(
            _to_numpy(api.clover_topological_charge(transformed)),
            density.sum(), rtol=2e-11, atol=2e-11)

    def test_topological_density_total_and_volume_average_are_distinct(self):
        """q(x)、Q=sum_x q(x)、以及 <q>_V=Q/V 必须有清晰不同入口。"""
        api = _api(self)
        links = _random_su3_links(seed=90215)
        density = _to_numpy(api.clover_topological_charge_density(links))
        total = _to_numpy(api.clover_topological_charge(links))
        average = _to_numpy(
            api.clover_topological_charge_density_average(links))
        np.testing.assert_allclose(total, density.sum(), rtol=2e-13,
                                   atol=2e-13)
        np.testing.assert_allclose(average, density.mean(), rtol=2e-13,
                                   atol=2e-13)
        np.testing.assert_allclose(average, total / density.size,
                                   rtol=2e-13, atol=2e-13)

    def test_torch_cpu_matches_numpy_when_available(self):
        """当前环境有 torch 时，CPU 后端的最小结果必须与 NumPy 一致。"""
        try:
            import torch  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("torch is unavailable")

        api = _api(self)
        links = _random_su3_links(shape=(2, 2, 2, 2), seed=90216)
        set_backend("numpy")
        expected = (
            _to_numpy(api.wilson_rectangle(links, 2, 3, 0, 3,
                                            average=False)),
            _to_numpy(api.polyakov_loop(links)),
            _to_numpy(api.clover_topological_charge_density(links)),
        )
        set_backend("torch", device="cpu")
        actual = (
            _to_numpy(api.wilson_rectangle(links, 2, 3, 0, 3,
                                            average=False)),
            _to_numpy(api.polyakov_loop(links)),
            _to_numpy(api.clover_topological_charge_density(links)),
        )
        for got, want in zip(actual, expected):
            np.testing.assert_allclose(got, want, rtol=2e-11, atol=2e-11)

    def test_cupy_matches_numpy_when_available(self):
        """当前环境有 CuPy 时，最小结果必须与 NumPy 一致。"""
        try:
            import cupy  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("cupy is unavailable")

        api = _api(self)
        links = _random_su3_links(shape=(1, 2, 2, 2), seed=90217)
        set_backend("numpy")
        expected = _to_numpy(api.wilson_rectangle(
            links, 2, 2, 0, 3, average=False))
        set_backend("cupy")
        actual = _to_numpy(api.wilson_rectangle(
            links, 2, 2, 0, 3, average=False))
        np.testing.assert_allclose(actual, expected, rtol=2e-11, atol=2e-11)


def run_gauge_observables_contract(verbosity=2):
    """供外层控制器调用的独立契约入口。"""
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        GaugeObservablesContract)
    return unittest.TextTestRunner(verbosity=verbosity).run(suite)


if __name__ == "__main__":
    result = run_gauge_observables_contract()
    raise SystemExit(0 if result.wasSuccessful() else 1)
