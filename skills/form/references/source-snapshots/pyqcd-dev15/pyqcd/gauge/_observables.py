"""纯数组纯规范观测量。

输入规范场统一采用
``(Nt, Nz, Ny, Nx, 4, Nc, Nc)``，链接方向标签为
``0=x, 1=y, 2=z, 3=t``，坐标轴因此为 ``3-direction``。所有数组运算
通过 ``pyqcd.tools._backend.get_backend`` 获取的后端完成；输入可以是
NumPy、CuPy 或 torch 数组，输出留在当前后端。

本模块只保留逐点矩阵到完成颜色迹为止，不堆叠整条路径：矩形圈逐段滚动
取链接，Clover 场强逐个平面构造。这既保持周期边界，也使回程显式使用
``U^dagger`` 而不是数组反转的近似。
"""
from __future__ import annotations

import numbers

import numpy as np

from ..tools._backend import get_backend


_SUPPORTED_NUMPY_DTYPES = frozenset(
    np.dtype(dtype)
    for dtype in (np.float32, np.float64, np.complex64, np.complex128)
)
_SUPPORTED_DTYPE_TEXT = "float32/float64/complex64/complex128"


def _is_supported_dtype(dtype, backend):
    """只接受规范观测量定义的四个精确浮点/复数 dtype。"""
    torch = getattr(backend, "torch", None)
    if torch is not None:
        torch_dtypes = (
            torch.float32, torch.float64,
            torch.complex64, torch.complex128,
        )
        if any(dtype == candidate for candidate in torch_dtypes):
            return True
    try:
        return np.dtype(dtype) in _SUPPORTED_NUMPY_DTYPES
    except (TypeError, ValueError):
        return False


def _is_current_torch_tensor(value, backend):
    """识别当前 Torch 后端的 Tensor，避免全局 device 覆盖输入设备。"""
    torch = getattr(backend, "torch", None)
    tensor_type = getattr(torch, "Tensor", None)
    return tensor_type is not None and isinstance(value, tensor_type)


def _validate_gauge(gauge):
    """检查并转换规范场到当前数组后端。"""
    backend = get_backend()
    shape = getattr(gauge, "shape", None)
    if shape is None or len(shape) != 7:
        raise ValueError(
            "gauge 必须具有形状 (Nt,Nz,Ny,Nx,4,Nc,Nc)，"
            f"收到 {shape!r}")
    if (tuple(shape[4:5]) != (4,) or shape[5] != shape[6]
            or int(shape[5]) <= 0):
        raise ValueError(
            "gauge 必须具有形状 (Nt,Nz,Ny,Nx,4,Nc,Nc)，"
            f"收到 {tuple(shape)!r}")
    if any(int(length) <= 0 for length in shape[:4]):
        raise ValueError(f"gauge 的四个格点长度必须为正，收到 {tuple(shape[:4])!r}")
    dtype = getattr(gauge, "dtype", None)
    if not _is_supported_dtype(dtype, backend):
        raise ValueError(
            "gauge dtype 必须是支持的浮点或复数类型；"
            f"仅支持 {_SUPPORTED_DTYPE_TEXT}，"
            "不接受 bool/整数/float16/bfloat16/complex32 等其他 dtype；"
            f"收到 {dtype!r}")

    # Torch adapter 的 asarray 会按全局默认 device 调用 ``.to(...)``。
    # 当前后端已经是 Torch 且输入本身是 Tensor 时，输入的 device/dtype
    # 是更具体的契约，必须直接沿用，不能被 set_backend 的默认值覆盖。
    array = gauge if _is_current_torch_tensor(gauge, backend) \
        else backend.asarray(gauge)
    if array.ndim != 7 or array.shape[4] != 4 or array.shape[-2] != array.shape[-1]:
        raise ValueError(
            "gauge 转换后仍必须具有 (Nt,Nz,Ny,Nx,4,Nc,Nc) 布局，"
            f"收到 {tuple(array.shape)!r}")
    return array


def _nonnegative_int(name, value):
    if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, numbers.Integral) or int(value) < 0:
        raise ValueError(f"{name} 必须是非负整数，收到 {value!r}")
    return int(value)


def _direction(name, value):
    if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, numbers.Integral) or not 0 <= int(value) < 4:
        raise ValueError(f"{name} 必须是 0,1,2,3 之一，收到 {value!r}")
    return int(value)


def _average_flag(value):
    if not isinstance(value, (bool, np.bool_)):
        raise ValueError(f"average 必须是布尔值，收到 {value!r}")
    return bool(value)


def _traceless_flag(value):
    if not isinstance(value, (bool, np.bool_)):
        raise ValueError(f"traceless 必须是布尔值，收到 {value!r}")
    return bool(value)


def _adjoint(matrix):
    backend = get_backend()
    return backend.swapaxes(backend.conj(matrix), -1, -2)


def _shift(field, offsets):
    """取 ``field(x+sum_d offsets[d] e_d)``，方向标签映射到 tzyx 轴。"""
    backend = get_backend()
    shifted = field
    for direction, offset in offsets:
        if offset:
            shifted = backend.roll(shifted, -int(offset), axis=3 - direction)
    return shifted


def _identity_field(gauge):
    backend = get_backend()
    nc = int(gauge.shape[-1])
    identity = _identity_matrix_like(gauge[0, 0, 0, 0, 0, :, :])
    return backend.broadcast_to(identity, tuple(gauge.shape[:4]) + (nc, nc))


def _identity_matrix_like(matrix):
    """生成继承 ``matrix`` backend/device/dtype 的局部单位阵。"""
    backend = get_backend()
    identity = backend.zeros_like(matrix)
    nc = int(matrix.shape[-1])
    for diagonal in range(nc):
        identity[..., diagonal, diagonal] = 1
    return identity


def _normalized_trace(matrix, nc, *, real=True):
    backend = get_backend()
    trace = backend.einsum("...aa->...", matrix)
    if real:
        trace = trace.real
    return trace / float(nc)


def wilson_rectangle(gauge, R, T, mu, nu, *, average=True):
    """计算矩形 Wilson 圈 ``W_{mu,nu}(R,T)``。

    路径严格为

    ``+mu`` 重复 ``R`` 步 → ``+nu`` 重复 ``T`` 步 →
    ``-mu`` 重复 ``R`` 步 → ``-nu`` 重复 ``T`` 步。

    ``average=True``（默认）返回所有起点的体积平均
    ``mean_x Re Tr[U_C(x)]/Nc``；``average=False`` 返回每个起点的逐点
    圈场，形状为 ``(Nt,Nz,Ny,Nx)``。``R=0`` 或 ``T=0`` 是零面积单位圈，
    因而逐点结果严格为 1。长度可以超过对应格点长度，滚动操作自动实现
    周期边界。
    """
    gauge = _validate_gauge(gauge)
    R = _nonnegative_int("R", R)
    T = _nonnegative_int("T", T)
    mu = _direction("mu", mu)
    nu = _direction("nu", nu)
    average = _average_flag(average)
    if mu == nu:
        raise ValueError(f"mu 与 nu 必须不同，收到 mu=nu={mu}")

    backend = get_backend()
    nc = int(gauge.shape[-1])
    if R == 0 or T == 0:
        local = backend.ones_like(gauge[..., 0, 0, 0].real)
        return backend.mean(local) if average else local

    u_mu = gauge[..., mu, :, :]
    u_nu = gauge[..., nu, :, :]
    product = _identity_field(gauge)

    # 四段路径按物理行走顺序左到右相乘；所有偏移都相对于原起点 x。
    for step in range(R):
        product = backend.matmul(product, _shift(u_mu, ((mu, step),)))
    for step in range(T):
        product = backend.matmul(
            product, _shift(u_nu, ((mu, R), (nu, step))))
    for step in range(R):
        link = _shift(u_mu, ((mu, R - 1 - step), (nu, T)))
        product = backend.matmul(product, _adjoint(link))
    for step in range(T):
        link = _shift(u_nu, ((nu, T - 1 - step),))
        product = backend.matmul(product, _adjoint(link))

    local = _normalized_trace(product, nc)
    return backend.mean(local) if average else local


def wilson_loop(gauge, R, T, mu, nu, *, average=True):
    """``wilson_rectangle`` 的语义明确别名。"""
    return wilson_rectangle(gauge, R, T, mu, nu, average=average)


def polyakov_loop(gauge, time_dir=3, *, average=False, direction=None):
    """计算完整周期方向的 Polyakov 圈。

    ``time_dir`` 是链接方向标签，默认 ``3=t``。默认返回固定时间切片
    上的空间逐点值（沿该方向的坐标被移除）；每一点为
    ``Tr[prod_{n=0}^{L_dir-1} U_dir(x+n e_dir)]/Nc``，保留 SU(3) 中心相位。
    ``average=True`` 时才返回这些逐点值的平均，避免把单点、空间平均和
    组态平均混为一谈。``direction`` 仅作为 ``time_dir`` 的清晰兼容关键字。
    """
    gauge = _validate_gauge(gauge)
    if direction is not None:
        time_dir = direction
    time_dir = _direction("time_dir", time_dir)
    average = _average_flag(average)

    backend = get_backend()
    nc = int(gauge.shape[-1])
    length = int(gauge.shape[3 - time_dir])
    links = gauge[..., time_dir, :, :]
    product = _identity_field(gauge)
    for step in range(length):
        product = backend.matmul(
            product, _shift(links, ((time_dir, step),)))

    local_full = _normalized_trace(product, nc, real=False)
    # 迹对起始点沿闭合方向只差循环共轭；固定 index=0 即得到逐空间点场。
    slicer = [slice(None)] * 4
    slicer[3 - time_dir] = 0
    local = local_full[tuple(slicer)]
    return backend.mean(local) if average else local


def polyakov_loop_average(gauge, time_dir=3, *, direction=None):
    """返回 ``polyakov_loop(..., average=True)`` 的空间平均。"""
    return polyakov_loop(gauge, time_dir=time_dir, average=True,
                         direction=direction)


def clover_field_strength(gauge, mu, nu, *, traceless=True):
    """返回四叶 ``su(Nc)`` Clover 场强。

    先按现有 PyQCD 约定构造 ``-i/8 sum(P-P^dagger)``，再去除有限格距下
    残留的单位阵分量 ``Tr(F) I/Nc``。结果形状为
    ``(Nt,Nz,Ny,Nx,Nc,Nc)``，并采用 Hermitian、无迹约定。显式传入
    ``traceless=False`` 可复现历史 ``plaquette_clover`` 的未去迹结果。
    """
    gauge = _validate_gauge(gauge)
    mu = _direction("mu", mu)
    nu = _direction("nu", nu)
    traceless = _traceless_flag(traceless)
    if mu == nu:
        raise ValueError(f"mu 与 nu 必须不同，收到 mu=nu={mu}")

    backend = get_backend()
    axis_mu, axis_nu = 3 - mu, 3 - nu
    shifted_mu = backend.roll(gauge, 1, axis=axis_mu)
    shifted_nu = backend.roll(gauge, 1, axis=axis_nu)
    shifted_both = backend.roll(shifted_mu, 1, axis=axis_nu)

    # 四个以 x 为中心、同一 (mu,nu) 取向的 plaquette。
    p1 = backend.matmul(
        gauge[..., mu, :, :],
        backend.roll(gauge, -1, axis=axis_mu)[..., nu, :, :])
    p1 = backend.matmul(
        p1, _adjoint(backend.roll(gauge, -1, axis=axis_nu)[..., mu, :, :]))
    p1 = backend.matmul(p1, _adjoint(gauge[..., nu, :, :]))

    p2 = backend.matmul(
        backend.roll(shifted_mu, -1, axis=axis_mu)[..., nu, :, :],
        _adjoint(backend.roll(shifted_mu, -1, axis=axis_nu)[..., mu, :, :]))
    p2 = backend.matmul(p2, _adjoint(shifted_mu[..., nu, :, :]))
    p2 = backend.matmul(p2, shifted_mu[..., mu, :, :])

    p3 = backend.matmul(
        _adjoint(backend.roll(shifted_both, -1, axis=axis_nu)[..., mu, :, :]),
        _adjoint(shifted_both[..., nu, :, :]))
    p3 = backend.matmul(p3, shifted_both[..., mu, :, :])
    p3 = backend.matmul(
        p3, backend.roll(shifted_both, -1, axis=axis_mu)[..., nu, :, :])

    p4 = backend.matmul(
        _adjoint(shifted_nu[..., nu, :, :]), shifted_nu[..., mu, :, :])
    p4 = backend.matmul(
        p4, backend.roll(shifted_nu, -1, axis=axis_mu)[..., nu, :, :])
    p4 = backend.matmul(
        p4, _adjoint(backend.roll(shifted_nu, -1, axis=axis_nu)[..., mu, :, :]))

    antihermitian_sum = (
        p1 - _adjoint(p1)
        + p2 - _adjoint(p2)
        + p3 - _adjoint(p3)
        + p4 - _adjoint(p4)
    )
    field = -1j * antihermitian_sum / 8.0
    if not traceless:
        return field
    nc = int(field.shape[-1])
    trace = backend.einsum("...aa->...", field)
    identity = _identity_matrix_like(field[0, 0, 0, 0, :, :])
    return field - (trace / float(nc))[..., None, None] * identity


def _field_product_trace(left, right):
    backend = get_backend()
    return backend.einsum("...ab,...ba->...", left, right)


def clover_topological_charge_density(gauge, *, traceless=True):
    r"""返回逐格点 bare Clover 拓扑荷密度 ``q(x)``。

    使用 Euclidean 约定

    ``q(x) = 1/(32 pi^2) eps_{mu nu rho sigma}
    Tr[F_mu_nu(x) F_rho_sigma(x)]``，其中
    ``F_mu_nu = [-i/8 sum_four_plaquettes(P-P^dagger)]_traceless``。由于
    ``F`` 的反对称性，代码以等价的三项式实现：

    ``q = [Tr(F01 F23) - Tr(F02 F13) + Tr(F03 F12)]/(4 pi^2)``.

    返回形状 ``(Nt,Nz,Ny,Nx)``；这是逐点值，不是体积平均。这里的 q 已
    吸收格点单位 ``a^4`` 的无量纲离散约定，未乘物理 ``a^{-4}``，也不做
    流化、整数量子化或 ensemble 平均。默认 ``traceless=True`` 使用标准
    ``su(Nc)`` 场强；``False`` 仅用于复现历史未去迹 bare Clover 离散值。
    """
    gauge = _validate_gauge(gauge)
    traceless = _traceless_flag(traceless)

    f01 = clover_field_strength(gauge, 0, 1, traceless=traceless)
    f23 = clover_field_strength(gauge, 2, 3, traceless=traceless)
    density = _field_product_trace(f01, f23)
    del f01, f23

    f02 = clover_field_strength(gauge, 0, 2, traceless=traceless)
    f13 = clover_field_strength(gauge, 1, 3, traceless=traceless)
    density = density - _field_product_trace(f02, f13)
    del f02, f13

    f03 = clover_field_strength(gauge, 0, 3, traceless=traceless)
    f12 = clover_field_strength(gauge, 1, 2, traceless=traceless)
    density = density + _field_product_trace(f03, f12)

    backend = get_backend()
    return density.real / (4.0 * backend.pi ** 2)


def clover_topological_charge(gauge, *, traceless=True):
    """返回总 bare Clover 拓扑荷 ``Q=sum_x q(x)``，不是体积平均。"""
    backend = get_backend()
    return backend.sum(clover_topological_charge_density(
        gauge, traceless=traceless))


def clover_topological_charge_density_average(gauge, *, traceless=True):
    """返回逐点 Clover 密度的体积平均 ``<q>_V=mean_x q(x)``。"""
    backend = get_backend()
    return backend.mean(clover_topological_charge_density(
        gauge, traceless=traceless))


def clover_topological_charge_average(gauge, *, traceless=True):
    """``clover_topological_charge_density_average`` 的明确兼容别名。"""
    return clover_topological_charge_density_average(
        gauge, traceless=traceless)


# 常见短名保留清晰的一一语义：density 是逐点，charge 是总和。
topological_charge_density = clover_topological_charge_density
topological_charge = clover_topological_charge
total_topological_charge = clover_topological_charge
topological_charge_density_average = clover_topological_charge_density_average


__all__ = [
    "wilson_rectangle", "wilson_loop",
    "polyakov_loop", "polyakov_loop_average",
    "clover_field_strength",
    "clover_topological_charge_density", "clover_topological_charge",
    "clover_topological_charge_density_average",
    "clover_topological_charge_average",
    "topological_charge_density", "topological_charge",
    "total_topological_charge", "topological_charge_density_average",
]
