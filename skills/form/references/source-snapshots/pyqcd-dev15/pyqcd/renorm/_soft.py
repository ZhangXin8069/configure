"""矩形 Wilson 圈与 SDR 软因子入口。

本模块把文档中记号 ``Z_E(r, b_perp; 1/a)`` 的矩形 Wilson 圈减除因子
显式公开出来，并补齐 SDR 闭环里的 ``Z_O(1/a, mu, Gamma)`` /
``h^{SDR}`` 入口。几何构造完全复用 ``pyqcd.gauge.wilson_rectangle``，
因此同样支持 NumPy / CuPy / torch 后端输入。
"""
from __future__ import annotations

import numpy as np

from ..gauge import wilson_rectangle
from ..tools._backend import get_backend
from ._const import CF, gammaE, pi, alpha_s
from ._ensembles import fm_to_GeV


def _shape_tuple(value):
    shape = getattr(value, "shape", None)
    if shape is None:
        shape = np.shape(value)
    return tuple(int(dim) for dim in shape)


def _ensure_broadcastable(label, *named_values):
    shapes = [_shape_tuple(value) for _name, value in named_values]
    try:
        np.broadcast_shapes(*shapes)
    except ValueError as exc:
        detail = ", ".join(
            f"{name}={shape}" for (name, _value), shape in zip(named_values, shapes))
        raise ValueError(f"{label} 输入形状不兼容，无法广播: {detail}") from exc


def _finite_array(name, value):
    backend = get_backend()
    try:
        array = backend.asarray(value)
    except Exception as exc:
        raise ValueError(f"{name} 必须是数值标量或数组，收到 {value!r}") from exc
    shape = _shape_tuple(array)
    if any(dim == 0 for dim in shape):
        raise ValueError(f"{name} 不能为空，收到形状 {shape}")
    try:
        finite = backend.isfinite(array)
    except Exception as exc:
        raise ValueError(f"{name} 必须是数值标量或数组，收到 {value!r}") from exc
    if not bool(backend.min(finite)):
        raise ValueError(f"{name} 必须全部为有限值，收到 {value!r}")
    return array


def _sqrt_soft_factor(name, value):
    backend = get_backend()
    array = _finite_array(name, value)
    try:
        root = backend.sqrt(array)
    except Exception as exc:
        raise ValueError(f"{name} 的平方根无法计算，收到 {value!r}") from exc
    try:
        finite = backend.isfinite(root)
    except Exception as exc:
        raise ValueError(f"{name} 的平方根必须有限，收到 {value!r}") from exc
    if not bool(backend.min(finite)):
        raise ValueError(f"{name} 的平方根必须有限，收到 {value!r}")
    if not bool(backend.min(backend.abs(root) > 0)):
        raise ValueError(f"{name} 的平方根不能为 0，收到 {value!r}")
    return root


def _nonzero_array(name, value):
    backend = get_backend()
    array = _finite_array(name, value)
    if not bool(backend.min(backend.abs(array) > 0)):
        raise ValueError(f"{name} 不能为 0，收到 {value!r}")
    return array


def Z_E(gauge, r, b_perp, z_dir=2, b_dir=0, *, average=True):
    """矩形 Wilson 圈软因子 ``Z_E(r, b_perp; 1/a)``。"""
    return wilson_rectangle(
        gauge, r, b_perp, z_dir, b_dir, average=average,
    )


def sqrt_Z_E(gauge, r, b_perp, z_dir=2, b_dir=0, *, average=True):
    """返回文档中的 ``sqrt(Z_E)`` 减除因子。"""
    return _sqrt_soft_factor(
        "Z_E", Z_E(
            gauge, r, b_perp, z_dir=z_dir, b_dir=b_dir, average=average))


def rapidity_subtraction(matrix_element, gauge, r, b_perp, z_dir=2, b_dir=0,
                         *, average=True):
    """按文档公式做 rapidity subtraction：``h / sqrt(Z_E)``。"""
    backend = get_backend()
    matrix_element = _finite_array("matrix_element", matrix_element)
    soft = sqrt_Z_E(gauge, r, b_perp, z_dir=z_dir, b_dir=b_dir, average=average)
    _ensure_broadcastable(
        "rapidity_subtraction",
        ("matrix_element", matrix_element),
        ("sqrt_Z_E", soft),
    )
    return backend.asarray(matrix_element) / backend.asarray(soft)


def msbar_tmd_reference_matrix_element(z, b_perp, mu=2.0, *,
                                       Lambda_QCD=0.23, nf=3.0,
                                       length_unit="fm"):
    """短距离 SDR 参考矩阵元的 1 圈 MSbar 公式。

    文档 Eq. ``MS_matrix``:

    ``h_MS = 1 + alpha_s C_F/(2 pi) * [1/2
             + 3/2 log(mu^2 (b^2+z^2) exp(gammaE)/4)
             - 2 z/b atan(z/b)]``。

    ``z`` 与 ``b_perp`` 默认用 fm 传入，内部换算到 GeV^-1；也可传
    ``length_unit='gev^-1'`` 使用已换算长度。该短距离 TMD 公式要求
    ``b_perp > 0``。
    """
    backend = get_backend()
    mu = float(mu)
    Lambda_QCD = float(Lambda_QCD)
    nf = float(nf)
    if not (np.isfinite(mu) and mu > 0.0):
        raise ValueError("mu 必须是有限正数")
    if not (np.isfinite(Lambda_QCD) and Lambda_QCD > 0.0):
        raise ValueError("Lambda_QCD 必须是有限正数")
    if not np.isfinite(nf):
        raise ValueError("nf 必须是有限数")

    unit = str(length_unit).lower().replace(" ", "")
    if unit in ("fm", "fermi"):
        length_scale = 1.0 / fm_to_GeV
    elif unit in ("gev^-1", "gev-1", "gevinv", "gev_inv"):
        length_scale = 1.0
    else:
        raise ValueError("length_unit 必须是 'fm' 或 'gev^-1'")

    _ensure_broadcastable(
        "msbar_tmd_reference_matrix_element",
        ("z", z),
        ("b_perp", b_perp),
    )
    z_arr = _finite_array("z", z) * length_scale
    b_arr = _finite_array("b_perp", b_perp) * length_scale
    if not bool(backend.min(b_arr > 0)):
        raise ValueError("b_perp 必须全部为正数")

    atan = getattr(backend, "arctan", None)
    if atan is None:
        atan = getattr(backend, "atan", None)
    if atan is None and hasattr(backend, "torch"):
        atan = backend.torch.atan
    if atan is None:
        raise RuntimeError("当前后端缺少 arctan/atan")

    radius2 = b_arr * b_arr + z_arr * z_arr
    log_arg = backend.asarray(mu * mu * np.exp(gammaE) / 4.0) * radius2
    if not bool(backend.min(log_arg > 0)):
        raise ValueError("MSbar 对数参数必须全部为正")
    bracket = (
        0.5
        + 1.5 * backend.log(log_arg)
        - 2.0 * (z_arr / b_arr) * atan(z_arr / b_arr)
    )
    prefactor = alpha_s(mu, Lambda_QCD, nf) * CF / (2.0 * pi)
    return 1.0 + prefactor * bracket


def short_distance_renormalization_factor(reference_matrix_element,
                                          reference_soft_factor,
                                          msbar_reference):
    """文档 Eq. ``SDR_factor`` 的显式入口。

    直接返回

    ``Z_O(1/a, mu, Gamma) = h_ref / (sqrt(Z_E_ref) * h_MSbar_ref)``

    其中 ``reference_matrix_element`` 对应参考点矩阵元，
    ``reference_soft_factor`` 对应参考点 ``Z_E``，``msbar_reference``
    对应 ``\\tilde h^{MSbar}(z_0, b_{\\perp,0}, \\mu)``。
    """
    backend = get_backend()
    _ensure_broadcastable(
        "short_distance_renormalization_factor",
        ("reference_matrix_element", reference_matrix_element),
        ("reference_soft_factor", reference_soft_factor),
        ("msbar_reference", msbar_reference),
    )
    reference_matrix_element = _finite_array(
        "reference_matrix_element", reference_matrix_element)
    reference_soft_root = _sqrt_soft_factor(
        "reference_soft_factor", reference_soft_factor)
    msbar_reference = _nonzero_array("msbar_reference", msbar_reference)
    return backend.asarray(reference_matrix_element) / backend.asarray(
        reference_soft_root) / backend.asarray(msbar_reference)


def sdr_renormalized_tmd(target_matrix_element, reference_matrix_element,
                         target_soft_factor, reference_soft_factor,
                         msbar_reference):
    """文档 Eq. ``full_renorm_chain`` 的显式入口。

    直接实现

    ``h^{SDR} = (h_target / sqrt(Z_E_target)) /``
    ``          (h_ref / sqrt(Z_E_ref)) / h_MSbar_ref``

    其中 ``target_soft_factor`` 与 ``reference_soft_factor`` 都应传入原始
    ``Z_E``，函数内部会自动取平方根。
    """
    backend = get_backend()
    _ensure_broadcastable(
        "sdr_renormalized_tmd",
        ("target_matrix_element", target_matrix_element),
        ("reference_matrix_element", reference_matrix_element),
        ("target_soft_factor", target_soft_factor),
        ("reference_soft_factor", reference_soft_factor),
        ("msbar_reference", msbar_reference),
    )
    target_matrix_element = _finite_array("target_matrix_element",
                                          target_matrix_element)
    reference_matrix_element = _finite_array("reference_matrix_element",
                                             reference_matrix_element)
    target_soft_root = _sqrt_soft_factor("target_soft_factor",
                                         target_soft_factor)
    reference_soft_root = _sqrt_soft_factor("reference_soft_factor",
                                            reference_soft_factor)
    msbar_reference = _nonzero_array("msbar_reference", msbar_reference)

    target_subtracted = backend.asarray(target_matrix_element) / backend.asarray(
        target_soft_root)
    reference_subtracted = backend.asarray(reference_matrix_element) / \
        backend.asarray(reference_soft_root)
    reference_factor = reference_subtracted / backend.asarray(msbar_reference)
    if not bool(backend.min(backend.abs(reference_factor) > 0)):
        raise ValueError(
            "reference_matrix_element / sqrt(reference_soft_factor) / "
            "msbar_reference 不能为 0")
    return target_subtracted / reference_factor


soft_factor_rectangle = Z_E
soft_subtraction_factor = sqrt_Z_E
soft_subtraction = rapidity_subtraction


__all__ = [
    "Z_E",
    "sqrt_Z_E",
    "rapidity_subtraction",
    "msbar_tmd_reference_matrix_element",
    "short_distance_renormalization_factor",
    "sdr_renormalized_tmd",
    "soft_factor_rectangle",
    "soft_subtraction_factor",
    "soft_subtraction",
]
