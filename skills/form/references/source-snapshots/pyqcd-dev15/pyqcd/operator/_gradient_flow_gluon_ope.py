"""
参考 schema-v2 梯度流胶子 OPE。

本模块与 ``_gluon_ope.py`` 中的 docker legacy 算符保持隔离。参考生产链
的关键语义是：

* 输入为 thin-link 规范组态，流化使用四维 Wilson flow；
* Clover 场强同时保留 ``legacy_untraced`` 和生产用 ``traceless`` 投影；
* 直线 Wilson 线保存 ``+z``、``-z`` 两个原始方向；
* 输出轴为
  ``(field_projection, channel, z_orientation, component, z, t)``；
* helicity ``pol35`` 的复数相位由 ratio 统计层保留到最后再投影。

这里的 OPE 是有限流时间 bare observable，不包含 Z_R、混合、CS 核、
LaMET/pseudo-PDF matching 或连续极限外推。
"""
from __future__ import annotations

import json
import os
import tempfile

import numpy as np

from ..tools._backend import get_backend
from ._gluon_ope import compute_dual_field_strength, plaquette_clover


OPE_SCHEMA = "gradient_flow_gluon_ope_v2"
OPE_STATUS = "flowed_bare_ope_observable"
FIELD_PROJECTIONS = ("legacy_untraced", "traceless")
CHANNELS = ("unpolarized", "helicity")
ORIENTATIONS = ("plus_z_raw", "minus_z_raw", "even_sum", "odd_difference")
COMPONENTS = ("combined", "Mtiti", "Mijij", "ti", "tj", "ij_single")
OPE_AXES = ("field_projection", "channel", "z_orientation",
            "component", "z", "t")

_PAIRS = tuple(
    (mu, nu) for mu in range(4) for nu in range(mu + 1, 4)
)


def _to_numpy(value):
    """将 NumPy/CuPy/Torch 后端数组显式转回主机 NumPy。"""
    detach = getattr(value, "detach", None)
    if detach is not None:
        return value.detach().cpu().numpy()
    asnumpy = getattr(get_backend(), "asnumpy", None)
    if asnumpy is not None:
        return asnumpy(value)
    getter = getattr(value, "get", None)
    if getter is not None:
        return getter()
    return np.asarray(value)


def _validate_gauge(gauge):
    """检查统一 tzyx gauge 布局，并交给当前后端。"""
    shape = getattr(gauge, "shape", None)
    if shape is None or len(shape) != 7:
        raise ValueError(
            "gauge 必须具有形状 (Nt,Nz,Ny,Nx,4,Nc,Nc)，"
            f"收到 {shape!r}")
    if tuple(shape[4:5]) != (4,) or shape[5] != shape[6]:
        raise ValueError(
            "gauge 必须具有形状 (Nt,Nz,Ny,Nx,4,Nc,Nc)，"
            f"收到 {tuple(shape)!r}")
    if any(int(length) <= 0 for length in shape[:4]):
        raise ValueError("gauge 的四个格点长度必须为正")
    backend = get_backend()
    array = backend.asarray(gauge)
    torch = getattr(backend, "torch", None)
    if torch is not None:
        allowed = (torch.complex64, torch.complex128)
        valid_dtype = array.dtype in allowed
    else:
        valid_dtype = np.dtype(array.dtype) in (
            np.dtype("complex64"), np.dtype("complex128")
        )
    if not valid_dtype:
        raise ValueError("gauge dtype 必须是 complex64 或 complex128")
    return array


def _nonnegative_int(name, value, minimum=0):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, np.integer))):
        raise ValueError(f"{name} 必须是非布尔整数")
    value = int(value)
    if value < minimum:
        raise ValueError(f"{name} 必须 >= {minimum}")
    return value


def _spatial_direction(name, value):
    value = _nonnegative_int(name, value)
    if value > 2:
        raise ValueError(f"{name} 必须是空间方向 0=x, 1=y, 2=z")
    return value


def _finite_real(name, value):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))):
        raise ValueError(f"{name} 必须是有限实标量")
    value = float(value)
    if not np.isfinite(value):
        raise ValueError(f"{name} 必须是有限实标量")
    return value


def _canonical_pair(mu, nu):
    return (mu, nu) if mu < nu else (nu, mu)


def _ordered_field(fields, mu, nu):
    field = fields[_canonical_pair(mu, nu)]
    return field if mu < nu else -field


def _traceless_field(field):
    """逐点去除有限格距 Clover 的单位阵分量。"""
    backend = get_backend()
    nc = int(field.shape[-1])
    trace = backend.einsum("...aa->...", field)
    identity = backend.eye(nc, dtype=field.dtype)
    return field - (trace / float(nc))[..., None, None] * identity


def _field_dictionary(gauge, field_projection):
    if field_projection not in FIELD_PROJECTIONS:
        raise ValueError(
            f"field_projection 必须是 {FIELD_PROJECTIONS!r} 中的字符串")
    fields = {}
    for pair in _PAIRS:
        field = plaquette_clover(gauge, *pair)
        if field_projection == "traceless":
            field = _traceless_field(field)
        fields[pair] = field
    return fields


def _dual(fields, mu, nu):
    dual = compute_dual_field_strength(fields, mu, nu)
    if dual is None:
        raise ValueError(f"无法构造 Ftilde_{mu}{nu}")
    return dual


def _spatial_sum_time(matrix):
    """对 (t,z,y,x,color,color) 的矩阵迹作空间和，返回 (t,)。"""
    backend = get_backend()
    trace = backend.einsum("...aa->...", matrix)
    return _to_numpy(backend.sum(trace, axis=(1, 2, 3)))


def _straight_bilocal(gauge, first, second, z_dir, z_count, direction):
    """计算一对有序场强的直线双局域量，返回 ``(z,t)``。"""
    backend = get_backend()
    axis = 3 - z_dir
    links = gauge[..., z_dir, :, :]
    result = np.empty((z_count, int(gauge.shape[0])), dtype=np.complex128)
    for z in range(z_count):
        if z == 0:
            contracted = backend.matmul(first, second)
        elif direction > 0:
            # F(x+z) U^dagger(x+z,x) F(0) U(x,x+z).
            contracted = backend.roll(first, -z, axis=axis)
            for step in range(z):
                link = backend.roll(
                    links, -(z - 1 - step), axis=axis)
                contracted = backend.matmul(
                    contracted,
                    backend.swapaxes(backend.conj(link), -1, -2))
            contracted = backend.matmul(contracted, second)
            for step in range(z):
                contracted = backend.matmul(
                    contracted, backend.roll(links, -step, axis=axis))
        else:
            # F(x-z) U(x-z,x) F(0) U^dagger(x,x-z).
            contracted = backend.roll(first, z, axis=axis)
            for step in range(z):
                link = backend.roll(links, z - step, axis=axis)
                contracted = backend.matmul(contracted, link)
            contracted = backend.matmul(contracted, second)
            for step in range(z):
                link = backend.roll(links, step + 1, axis=axis)
                contracted = backend.matmul(
                    contracted,
                    backend.swapaxes(backend.conj(link), -1, -2))
        result[z] = _spatial_sum_time(contracted)
    return result


def _component_set(gauge, fields, channel, z_dir, z_count):
    transverse = [direction for direction in range(3) if direction != z_dir]
    i, j = transverse
    use_dual = channel == "helicity"

    def primitive(mu, nu):
        first = _ordered_field(fields, mu, nu)
        second = _dual(fields, mu, nu) if use_dual else first
        plus = _straight_bilocal(gauge, first, second, z_dir, z_count, +1)
        minus = _straight_bilocal(gauge, first, second, z_dir, z_count, -1)
        return np.stack((plus, minus), axis=0)

    ti = primitive(3, i)
    tj = primitive(3, j)
    ij = primitive(i, j)
    mtiti = ti + tj
    mijij = 2.0 * ij
    combined = (
        mtiti - mijij if channel == "unpolarized"
        else mtiti + mijij
    )
    return np.stack(
        (combined, mtiti, mijij, ti, tj, ij), axis=1
    )


def flowed_gluon_ope(gauge, z_count=25, z_dir=2,
                     field_projections=FIELD_PROJECTIONS):
    """在给定 gauge 上计算参考 schema-v2 OPE，不执行梯度流。

    Args:
        gauge: ``(Nt,Nz,Ny,Nx,4,Nc,Nc)`` 规范链接。
        z_count: 保存的 ``z/a=0..z_count-1`` 数量。
        z_dir: 直线 Wilson 线方向，0=x、1=y、2=z。
        field_projections: 通常为 ``("legacy_untraced", "traceless")``。

    Returns:
        complex128 数组，轴顺序为
        ``(field_projection, channel, orientation, component, z, t)``。
    """
    gauge = _validate_gauge(gauge)
    z_count = _nonnegative_int("z_count", z_count, minimum=1)
    z_dir = _spatial_direction("z_dir", z_dir)
    projections = tuple(field_projections)
    if not projections:
        raise ValueError("field_projections 不能为空")
    if len(set(projections)) != len(projections):
        raise ValueError("field_projections 不得重复")
    if any(value not in FIELD_PROJECTIONS for value in projections):
        raise ValueError(
            f"field_projections 只能来自 {FIELD_PROJECTIONS!r}")
    if projections != FIELD_PROJECTIONS:
        raise ValueError(
            "参考 schema-v2 必须按 "
            f"{FIELD_PROJECTIONS!r} 同时保存两个 field projection")

    nt = int(gauge.shape[0])
    output = np.empty(
        (len(projections), len(CHANNELS), len(ORIENTATIONS),
         len(COMPONENTS), z_count, nt),
        dtype=np.complex128,
    )
    for ip, projection in enumerate(projections):
        fields = _field_dictionary(gauge, projection)
        for ic, channel in enumerate(CHANNELS):
            raw = _component_set(gauge, fields, channel, z_dir, z_count)
            output[ip, ic, 0] = raw[0]
            output[ip, ic, 1] = raw[1]
            output[ip, ic, 2] = raw[0] + raw[1]
            output[ip, ic, 3] = raw[0] - raw[1]
    return output


def _gauge_stats(gauge):
    """生成与参考 v5 metadata 对齐的有限性/幺正性/plaquette 诊断。"""
    array = _to_numpy(gauge)
    nc = int(array.shape[-1])
    links = array.reshape((-1, nc, nc))
    identity = np.eye(nc, dtype=array.dtype)
    unitary_error = np.linalg.norm(
        links @ np.swapaxes(links.conj(), -1, -2) - identity,
        axis=(-2, -1),
    )
    determinants = np.linalg.det(links)
    from ..renorm._gradient_flow import wilson_action_density

    density = np.asarray(_to_numpy(wilson_action_density(gauge)), dtype=float)
    return {
        "plaquette": float(1.0 - np.mean(density)),
        "max_unitarity_frobenius": float(np.max(unitary_error)),
        "max_abs_det_minus_1": float(np.max(np.abs(determinants - 1.0))),
    }


def gradient_flow_gluon_ope(gauge, tau, epsilon=0.01, z_count=25,
                            z_dir=2, conf_id=None, n_steps=None,
                            field_projections=FIELD_PROJECTIONS):
    """thin-link gauge -> Wilson flow -> schema-v2 OPE。

    ``tau`` 是无量纲 ``t/a^2``；生产参考值使用 ``epsilon=0.01``。
    返回 ``(data, metadata)``，其中 metadata 可直接写入 JSON。
    """
    gauge = _validate_gauge(gauge)
    tau = _finite_real("tau", tau)
    epsilon = _finite_real("epsilon", epsilon)
    if tau < 0.0:
        raise ValueError("tau 必须非负")
    if epsilon <= 0.0:
        raise ValueError("epsilon 必须为正")
    if n_steps is not None:
        n_steps = _nonnegative_int("n_steps", n_steps, minimum=1)

    raw_stats = _gauge_stats(gauge)
    from ..renorm._gradient_flow import wilson_flow

    flowed = wilson_flow(
        gauge, tau=tau, eps=epsilon, n_steps=n_steps
    )
    flowed_stats = _gauge_stats(flowed)
    data = flowed_gluon_ope(
        flowed, z_count=z_count, z_dir=z_dir,
        field_projections=field_projections,
    )
    effective_steps = (
        0 if tau == 0.0
        else (n_steps if n_steps is not None else int(np.ceil(tau / epsilon)))
    )
    metadata = {
        "schema": OPE_SCHEMA,
        "status": OPE_STATUS,
        "conf_id": None if conf_id is None else str(conf_id),
        "input_scheme": "thin_link_no_hyp_no_smear",
        "flow": {
            "tau_t_over_a2": tau,
            "epsilon": epsilon,
            "n_steps": effective_steps,
            "step_size": (
                None if effective_steps == 0
                else float(tau / effective_steps)
            ),
            "smoothing_radius_over_a": float(np.sqrt(8.0 * tau)),
        },
        "operator": {
            "z_dir": int(z_dir),
            "z_values_a": list(range(int(z_count))),
            "field_strength": "-i(Q-Qdagger)/8",
            "dual": "0.5*epsilon_E^{munurhosigma}*F_rhosigma",
            "wilson_line": "straight_periodic_plus_minus_z",
        },
        "axes": list(OPE_AXES),
        "axis_labels": {
            "field_projection": list(field_projections),
            "channel": list(CHANNELS),
            "z_orientation": list(ORIENTATIONS),
            "component": list(COMPONENTS),
        },
        "shape": list(data.shape),
        "dtype": str(data.dtype),
        "raw_gauge_stats": raw_stats,
        "flowed_gauge_stats": flowed_stats,
        "not_applied": [
            "renormalization", "zero_flow_time_extrapolation",
            "gluon_quark_mixing", "LaMET_or_pseudoPDF_matching",
            "continuum_extrapolation",
        ],
    }
    return data, metadata


def validate_gradient_flow_gluon_ope(data, metadata, *, conf_id=None,
                                     tau=None, epsilon=None):
    """严格验证 schema-v2 数据和线性/局域恒等式。"""
    array = np.asarray(data)
    checks = {
        "schema": metadata.get("schema") == OPE_SCHEMA,
        "status": metadata.get("status") == OPE_STATUS,
        "dtype": array.dtype == np.dtype("complex128"),
        "axes": metadata.get("axes") == list(OPE_AXES),
        "field_projection_labels": metadata.get("axis_labels", {}).get(
            "field_projection") == list(FIELD_PROJECTIONS),
        "channel_labels": metadata.get("axis_labels", {}).get("channel")
        == list(CHANNELS),
        "orientation_labels": metadata.get("axis_labels", {}).get(
            "z_orientation") == list(ORIENTATIONS),
        "component_labels": metadata.get("axis_labels", {}).get("component")
        == list(COMPONENTS),
        "shape_metadata": tuple(metadata.get("shape", ())) == array.shape,
        "shape_rank": array.ndim == 6 and array.shape[1:4] == (2, 4, 6),
        "finite": bool(np.isfinite(array).all()),
        "raw_group": float(metadata.get("raw_gauge_stats", {}).get(
            "max_unitarity_frobenius", np.inf)) < 5e-5
        and float(metadata.get("raw_gauge_stats", {}).get(
            "max_abs_det_minus_1", np.inf)) < 5e-5,
        "flowed_group": float(metadata.get("flowed_gauge_stats", {}).get(
            "max_unitarity_frobenius", np.inf)) < 5e-4
        and float(metadata.get("flowed_gauge_stats", {}).get(
            "max_abs_det_minus_1", np.inf)) < 5e-4,
        "plaquette_finite": bool(np.isfinite(
            float(metadata.get("raw_gauge_stats", {}).get(
                "plaquette", np.nan))
        ) and np.isfinite(
            float(metadata.get("flowed_gauge_stats", {}).get(
                "plaquette", np.nan))
        )),
        "wilson_flow_direction": float(metadata.get(
            "flowed_gauge_stats", {}).get("plaquette", -np.inf)) + 1e-7
        >= float(metadata.get("raw_gauge_stats", {}).get(
            "plaquette", np.inf)),
        "z0_direction_limit": bool(np.allclose(
            array[:, :, 0, :, 0], array[:, :, 1, :, 0],
            rtol=5e-12, atol=1e-10)),
        "even_definition": bool(np.allclose(
            array[:, :, 2], array[:, :, 0] + array[:, :, 1],
            rtol=5e-12, atol=1e-10)),
        "odd_definition": bool(np.allclose(
            array[:, :, 3], array[:, :, 0] - array[:, :, 1],
            rtol=5e-12, atol=1e-10)),
        "odd_z0_zero": bool(np.allclose(
            array[:, :, 3, :, 0], 0.0, rtol=5e-12, atol=1e-10)),
        "mtiti_definition": bool(np.allclose(
            array[:, :, :, 1], array[:, :, :, 3] + array[:, :, :, 4],
            rtol=5e-12, atol=1e-10)),
        "mijij_definition": bool(np.allclose(
            array[:, :, :, 2], 2.0 * array[:, :, :, 5],
            rtol=5e-12, atol=1e-10)),
        "unpolarized_combined": bool(np.allclose(
            array[:, 0, :, 0], array[:, 0, :, 1] - array[:, 0, :, 2],
            rtol=5e-12, atol=1e-10)),
        "helicity_combined": bool(np.allclose(
            array[:, 1, :, 0], array[:, 1, :, 1] + array[:, 1, :, 2],
            rtol=5e-12, atol=1e-10)),
    }
    if conf_id is not None:
        checks["conf_id"] = str(metadata.get("conf_id")) == str(conf_id)
    if tau is not None:
        checks["tau"] = abs(
            float(metadata.get("flow", {}).get("tau_t_over_a2", np.nan))
            - float(tau)
        ) < 1e-12
    if epsilon is not None:
        checks["epsilon"] = abs(
            float(metadata.get("flow", {}).get("epsilon", np.nan))
            - float(epsilon)
        ) < 1e-12
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError("schema-v2 OPE validation failed: " + ", ".join(failed))
    return checks


def select_gradient_flow_gluon_component(data, field_projection="traceless",
                                         channel="unpolarized",
                                         orientation="even_sum",
                                         component="combined"):
    """从 schema-v2 数组中选择物理通道或诊断组件。

    helicity 的参考生产数组将 ``combined`` 保存为 ``Mtiti+Mijij``；
    理论目标 ``(Mtiti-Mijij)_odd`` 通过显式 selector 选择，避免把诊断
    加号误当成物理定义。
    """
    array = np.asarray(data)
    if array.ndim != 6 or array.shape[1:4] != (2, 4, 6):
        raise ValueError("data 不是 schema-v2 的六轴数组")
    try:
        ip = FIELD_PROJECTIONS.index(field_projection)
        ic = CHANNELS.index(channel)
        io = ORIENTATIONS.index(orientation)
    except ValueError as exc:
        raise ValueError("未知 field_projection/channel/orientation") from exc
    if component == "helicity_physical_T_minus_S":
        if channel != "helicity":
            raise ValueError("helicity_physical_T_minus_S 只适用于 helicity")
        return array[ip, ic, io, 1] - array[ip, ic, io, 2]
    if component == "helicity_diagnostic_T_plus_S":
        if channel != "helicity":
            raise ValueError("helicity_diagnostic_T_plus_S 只适用于 helicity")
        return array[ip, ic, io, 1] + array[ip, ic, io, 2]
    try:
        ik = COMPONENTS.index(component)
    except ValueError as exc:
        raise ValueError(f"未知 component: {component}") from exc
    return array[ip, ic, io, ik]


def save_gradient_flow_gluon_ope(base, data, metadata):
    """原子保存 ``base.npy`` 与配对 ``base.json``。"""
    base = os.fspath(base)
    validate_gradient_flow_gluon_ope(data, metadata)
    directory = os.path.dirname(base) or "."
    os.makedirs(directory, exist_ok=True)
    npy = base + ".npy"
    jsn = base + ".json"
    with tempfile.NamedTemporaryFile(
            dir=directory, prefix=".ope.", suffix=".npy", delete=False) as tmp:
        tmp_npy = tmp.name
    with tempfile.NamedTemporaryFile(
            dir=directory, prefix=".ope.", suffix=".json", mode="w",
            encoding="utf-8", delete=False) as tmp:
        tmp_json = tmp.name
    try:
        np.save(tmp_npy, np.asarray(data, dtype=np.complex128), allow_pickle=False)
        with open(tmp_json, "w", encoding="utf-8") as stream:
            json.dump(metadata, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(tmp_npy, npy)
        os.replace(tmp_json, jsn)
    finally:
        for path in (tmp_npy, tmp_json):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
    return npy, jsn


def load_gradient_flow_gluon_ope(base, *, validate=True):
    """读取 schema-v2 的成对 NPY/JSON artifact。"""
    base = os.fspath(base)
    npy = base + ".npy"
    jsn = base + ".json"
    if not os.path.isfile(npy) or not os.path.isfile(jsn):
        raise FileNotFoundError(f"缺少配对 OPE artifact: {base}")
    data = np.load(npy, allow_pickle=False)
    with open(jsn, encoding="utf-8") as stream:
        metadata = json.load(stream)
    if validate:
        validate_gradient_flow_gluon_ope(data, metadata)
    return data, metadata


__all__ = [
    "OPE_SCHEMA", "OPE_STATUS", "FIELD_PROJECTIONS", "CHANNELS",
    "ORIENTATIONS", "COMPONENTS", "OPE_AXES",
    "flowed_gluon_ope", "gradient_flow_gluon_ope",
    "validate_gradient_flow_gluon_ope",
    "select_gradient_flow_gluon_component",
    "save_gradient_flow_gluon_ope", "load_gradient_flow_gluon_ope",
]
