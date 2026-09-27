"""
一圈梯度流 OPE -> MS-bar 准算符转换。

本模块对应 ``refer/donghx/Gradient_Flow_GluonPDF/gluon_flow_to_quasi.py``。
它只做有限流 bare OPE 的端点小流时间转换，不做 LaMET/PDF 匹配、软因子、
快度演化或连续极限外推。

对 Wilson 线方向平行/垂直的端点系数，采用

    c_parallel = 1,
    c_perp = 1 + alpha_s C_A/(4 pi)
              log(2 mu^2 t exp(gamma_E)),
    delta_m = -alpha_s C_A/(4 pi) sqrt(2 pi/t),

并按通道乘上

    Z_U(z) = exp(-delta_m |z|) / c_perp^2,
    Z_H(z) = exp(-delta_m |z|) / (c_parallel c_perp).

输入和输出轴均为
``(field_projection, channel, z_orientation, component, z, t)``。
"""
from __future__ import annotations

import math

import numpy as np


GEV_FM = 5.067730716
CA = 3.0
EULER_GAMMA = 0.5772156649015329
FLOW_TO_QUASI_SCHEMA = "gradient_flow_gluon_flow_to_quasi_v1"


def _finite_real(name, value):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))):
        raise ValueError(f"{name} 必须是有限实数")
    value = float(value)
    if not np.isfinite(value):
        raise ValueError(f"{name} 必须是有限实数")
    return value


def coefficients(tau, a_fm, mu_gev, alpha_s, ca=CA):
    """返回 ``(c_parallel, c_perp, delta_m_GeV, t_GeV_minus2)``。"""
    tau = _finite_real("tau", tau)
    a_fm = _finite_real("a_fm", a_fm)
    mu_gev = _finite_real("mu_gev", mu_gev)
    alpha_s = _finite_real("alpha_s", alpha_s)
    ca = _finite_real("ca", ca)
    if tau <= 0.0 or a_fm <= 0.0 or mu_gev <= 0.0:
        raise ValueError("tau、a_fm、mu_gev 必须为正")
    if alpha_s < 0.0:
        raise ValueError("alpha_s 必须非负")
    t_gev = tau * (a_fm * GEV_FM) ** 2
    c_parallel = 1.0
    c_perp = 1.0 + alpha_s * ca / (4.0 * math.pi) * math.log(
        2.0 * mu_gev ** 2 * t_gev * math.exp(EULER_GAMMA)
    )
    delta_m = -alpha_s * ca / (4.0 * math.pi) * math.sqrt(
        2.0 * math.pi / t_gev
    )
    return c_parallel, c_perp, delta_m, t_gev


def match_one(arr, tau, a_fm, mu_gev, alpha_s, ca=CA):
    """对一个 schema-v2 OPE 数组施加参考一圈转换。

    返回 ``(matched, coefficient_metadata)``。输入的 ``combined`` 会在
    匹配后由独立的 ``Mtiti``/``Mijij`` 重新构造，以避免重复使用未匹配的
    组合分量。
    """
    array = np.asarray(arr, dtype=np.complex128)
    if array.ndim != 6:
        raise ValueError(
            "OPE 必须具有 (projection,channel,orientation,component,z,t) 六轴"
        )
    if array.shape[1] != 2 or array.shape[3] < 3:
        raise ValueError(
            "OPE 必须包含两个 channel 及 combined/Mtiti/Mijij 三个组件"
        )
    if any(int(length) <= 0 for length in array.shape):
        raise ValueError("OPE 各轴长度必须为正")
    if not np.isfinite(array).all():
        raise ValueError("OPE 必须只含有限复数")

    c_parallel, c_perp, delta_m, t_gev = coefficients(
        tau, a_fm, mu_gev, alpha_s, ca
    )
    z_gev = (
        np.arange(array.shape[4], dtype=float) * float(a_fm) * GEV_FM
    )
    line = np.exp(-delta_m * z_gev)[None, None, None, None, :, None]
    factor_unpolarized = 1.0 / (c_perp * c_perp)
    factor_helicity = 1.0 / (c_parallel * c_perp)
    factors = np.asarray(
        [factor_unpolarized, factor_helicity], dtype=np.float64
    )

    out = array.copy()
    out *= factors[None, :, None, None, None, None]
    out *= line
    out[:, 0, :, 0, :, :] = (
        out[:, 0, :, 1, :, :] - out[:, 0, :, 2, :, :]
    )
    out[:, 1, :, 0, :, :] = (
        out[:, 1, :, 1, :, :] + out[:, 1, :, 2, :, :]
    )
    metadata = {
        "schema": FLOW_TO_QUASI_SCHEMA,
        "status": "flow_to_MSbar_quasi_operator_one_loop",
        "c_parallel_perp": float(c_parallel),
        "c_perp_perp": float(c_perp),
        "delta_m_GeV": float(delta_m),
        "t_GeV_minus2": float(t_gev),
        "line_factor": "exp(-delta_m*|z|)",
        "component_factors_unpolarized": float(factor_unpolarized),
        "component_factors_helicity": float(factor_helicity),
        "component_factors_by_channel": factors.tolist(),
        "light_cone_matching": "not_applied",
    }
    return out, metadata


gradient_flow_to_quasi_coefficients = coefficients
match_gradient_flow_ope_to_quasi = match_one


__all__ = [
    "GEV_FM", "CA", "EULER_GAMMA", "FLOW_TO_QUASI_SCHEMA",
    "coefficients", "gradient_flow_to_quasi_coefficients",
    "match_one", "match_gradient_flow_ope_to_quasi",
]
