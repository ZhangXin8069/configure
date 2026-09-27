"""
test9 梯度流重整化核子胶子 TMD-PDF 物理链（pyqcd 核心模块）
========================================================

从真实蒸馏数据（eigvec/peram/gauge）出发计算核子中胶子 TMD-PDF：

    1. 蒸馏 2pt：核子谱线 C2(dt)（多动量 Pz=0,2,4 或全方向）
    2. 梯度流：gauge → wilson_flow(τ=3a²) → flowed gauge V_tau
    3. 胶子 TMD 算符：在 flowed gauge 上逐时间片计算
       O(z,b⊥) = M^{tx;tx}+M^{ty;ty}−2M^{xy;xy}（空间求和）→ (nz,nb,Nt)
    4. 不相连 3pt 因子化：C3(dt,dtau,z,b) = C2(dt)·OPE(dtau,z,b)
    5. 真空扣除 + 比值 R(dt,dtau,z,b) = <[C3−C2⟨OPE⟩]/C2>_ti
    6. 逐 (z,b) 拟合 c0(z,b) → 裸矩阵元 hB(z,b,Pz)
    7. 自重整化（梯度流方案）：hR(z,b,Pz) = hB(z,b,Pz)/hB(0,b,Pz=0)
    8. λ 外推 + 傅里叶 → 准 TMD-PDF
    9. NLO 匹配 → 光锥 TMD-PDF x·g(x,b⊥) + CS 核

本模块只放"物理链计算"函数（数据读取、算符、统计、重整化），
顶层编排（配置/目录/CLI/并行）在
`pyqcd/testing/tmd/pdf_workflow.py`。
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time

import h5py
import numpy as np

from ..tools import get_backend, get_backend_name, set_precision
from ..tools._io import save_tensor_h5
from ..pipeline._config import (
    NT, NX, NEV, NEV1, PRECISION, get_gauge_path,
)
from ..pipeline._steps import (
    compute_vertices_for_config, compute_2pt_for_config_multi,
    _info, _momentum_tag,
)
from ..renorm import wilson_flow, flow_action_density, tmd_matrix_elements_time
from ..operator import read_gauge_lime


_CACHE_SCHEMA = "pyqcd.physical-cache.v1"
_CONTRACT_JSON_ATTR = "pyqcd_cache_contract_json"
_CONTRACT_SHA_ATTR = "pyqcd_cache_contract_sha256"
_VERTEX_ALGORITHM_VERSION = "pyqcd.pipeline.vertex-multi.v1"
_MULTI_2PT_ALGORITHM_VERSION = "pyqcd.pipeline.multi-2pt.v1"
_FLOW_ALGORITHM_VERSION = "pyqcd.renorm.wilson-flow.v1"
_OPE_ALGORITHM_VERSION = "pyqcd.pipeline.tmd-ope-time.v1"


def _cache_float(value, name):
    """把物理浮点参数规范化为有限 Python float。"""
    array = np.asarray(value)
    if array.ndim != 0:
        raise ValueError(f"{name} 必须为有限标量")
    result = float(array)
    if not np.isfinite(result):
        raise ValueError(f"{name} 必须为有限标量")
    return result


def _cache_int(value, name):
    """把格点整数规范化，同时拒绝 bool 与有损浮点转换。"""
    if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (int, np.integer)):
        raise ValueError(f"{name} 必须为非布尔格点整数")
    return int(value)


def _cache_int_list(values, name):
    try:
        values = list(values)
    except TypeError as exc:
        raise ValueError(f"{name} 必须为非空格点整数列表") from exc
    if not values:
        raise ValueError(f"{name} 不能为空")
    return [_cache_int(value, f"{name} 元素") for value in values]


def _validate_flow_controls(tau, eps):
    """验证流控制量，且在任何流场 IO 前拒绝非法请求。"""
    tau = _cache_float(tau, "tau")
    eps = _cache_float(eps, "eps")
    if tau < 0.0:
        raise ValueError("tau 必须为非负有限标量")
    if eps <= 0.0:
        raise ValueError("eps 必须为正有限标量")
    return tau, eps


def _validate_precision(precision):
    """缓存与 gauge API 仅接受两种显式复数精度标签。"""
    if (not isinstance(precision, (str, np.str_))
            or str(precision) not in ("complex64", "complex128")):
        raise ValueError("precision 必须是 'complex64' 或 'complex128'")
    return str(precision)


def _validate_momenta(momenta):
    """保序规范化非空三整数动量列表，拒绝 bool 与歧义结构。"""
    if isinstance(momenta, (str, bytes)):
        raise ValueError("momenta 必须为非空三整数动量列表")
    try:
        requested = list(momenta)
    except TypeError as exc:
        raise ValueError("momenta 必须为非空三整数动量列表") from exc
    if not requested:
        raise ValueError("momenta 不能为空")
    normalized = []
    seen = set()
    for index, momentum in enumerate(requested):
        if isinstance(momentum, (str, bytes)):
            raise ValueError(f"momentum[{index}] 必须恰含三个整数")
        try:
            components = list(momentum)
        except TypeError as exc:
            raise ValueError(
                f"momentum[{index}] 必须恰含三个整数") from exc
        if len(components) != 3:
            raise ValueError(f"momentum[{index}] 必须恰含三个整数")
        normalized_momentum = tuple(
            _cache_int(component, f"momentum[{index}] 分量")
            for component in components)
        if normalized_momentum in seen:
            raise ValueError(
                f"momenta 含重复动量 {normalized_momentum}，会合并输出槽")
        seen.add(normalized_momentum)
        normalized.append(normalized_momentum)
    return normalized


def _validate_channels(channels):
    """保序验证 multi-2pt 通道，并拒绝会覆盖输出键的重复项。"""
    if isinstance(channels, (str, bytes)):
        raise ValueError("channels 必须为非空通道列表")
    try:
        requested = list(channels)
    except TypeError as exc:
        raise ValueError("channels 必须为非空通道列表") from exc
    if not requested:
        raise ValueError("channels 不能为空")
    supported = {"pp", "pn", "pion"}
    for channel in requested:
        if not isinstance(channel, (str, np.str_)) or str(channel) not in supported:
            raise ValueError("channels 仅支持 pp、pn、pion")
    normalized = [str(channel) for channel in requested]
    if len(normalized) != len(set(normalized)):
        raise ValueError("channels 不得包含重复通道")
    return normalized


def _validate_v_kind(v_kind):
    if not isinstance(v_kind, (str, np.str_)) or str(v_kind) not in (
            "VDV", "VVV"):
        raise ValueError("v_kind 必须是 'VDV' 或 'VVV'")
    return str(v_kind)


def _validate_tmd_directions(z_dir, b_dir):
    """验证 TMD 的两个不同、受支持的空间方向。"""
    directions = []
    for name, value in (("z_dir", z_dir), ("b_dir", b_dir)):
        value = _cache_int(value, name)
        if value not in (0, 1, 2):
            raise ValueError(
                f"{name} 必须是受支持的空间方向 0=x, 1=y, 2=z")
        directions.append(value)
    if directions[0] == directions[1]:
        raise ValueError("z_dir 与 b_dir 必须是不同的空间方向")
    return tuple(directions)


def _validate_tmd_request(tau, eps, precision, z_dir, b_dir,
                          z_list, b_list):
    """规范化 OPE 请求，独立于组态目录和缓存存在性。"""
    tau, eps = _validate_flow_controls(tau, eps)
    precision = _validate_precision(precision)
    z_dir, b_dir = _validate_tmd_directions(z_dir, b_dir)
    z_list = _cache_int_list(z_list, "z_list")
    b_list = _cache_int_list(b_list, "b_list")
    return tau, eps, precision, z_dir, b_dir, z_list, b_list


def _canonical_contract_json(contract):
    """稳定、无空白、键排序的 UTF-8 JSON 物理契约。"""
    return json.dumps(
        contract, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False)


def _contract_sha256(contract):
    payload = _canonical_contract_json(contract)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _attr_text(value):
    if isinstance(value, (bytes, np.bytes_)):
        return bytes(value).decode("utf-8")
    if isinstance(value, str):
        return value
    return None


def _save_contract_h5(array, path, contract):
    """把数据和契约写入同一临时 HDF5，再原子发布最终文件。"""
    path = os.fspath(path)
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    payload = _canonical_contract_json(contract)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    with tempfile.NamedTemporaryFile(
            dir=directory, prefix=f".{os.path.basename(path)}.",
            suffix=".tmp.h5", delete=False) as temporary:
        temporary_path = temporary.name
    try:
        save_tensor_h5(array, temporary_path)
        with h5py.File(temporary_path, "r+") as handle:
            if set(handle.keys()) != {"data"}:
                raise ValueError("canonical HDF5 顶层数据集必须只有 data")
            if not isinstance(handle["data"], h5py.Dataset):
                raise ValueError("canonical HDF5 data 必须是 Dataset")
            handle.attrs[_CONTRACT_JSON_ATTR] = payload
            handle.attrs[_CONTRACT_SHA_ATTR] = digest
            handle.flush()
        os.replace(temporary_path, path)
    finally:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass


def _as_numpy_contract_array(value):
    """把后端数组转为 NumPy 视图/副本以执行持久化边界检查。"""
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    elif hasattr(value, "get") and callable(value.get):
        value = value.get()
    return np.asarray(value)


def _validate_contract_array(value, name, expected_shape, expected_dtype):
    """严格验证待返回或写入的数组，不做隐式 cast。"""
    try:
        array = _as_numpy_contract_array(value)
    except (TypeError, ValueError, RuntimeError) as exc:
        raise ValueError(f"{name} 无法转换为可验证数组: {exc}") from exc
    expected_shape = tuple(expected_shape)
    if array.shape != expected_shape:
        raise ValueError(
            f"{name} shape 契约不匹配: expected {expected_shape}, "
            f"got {array.shape}")
    expected_dtype = np.dtype(expected_dtype)
    if array.dtype != expected_dtype:
        raise ValueError(
            f"{name} dtype 契约不匹配: expected {expected_dtype}, "
            f"got {array.dtype}")
    try:
        finite = _array_all_finite(array)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 不能执行有限性检查: {exc}") from exc
    if not finite:
        raise ValueError(f"{name} 必须全部有限")
    return array


def _array_all_finite(array):
    """分首轴执行有限性检查，避免大规范场/顶点的全尺寸布尔副本。"""
    array = np.asarray(array)
    if array.ndim == 0:
        return bool(np.isfinite(array))
    for index in range(array.shape[0]):
        if not np.isfinite(array[index]).all():
            return False
    return True


def _load_contract_h5(path, contract, *, expected_shape,
                      expected_dtype):
    """仅在 JSON、SHA-256 与数组边界都精确一致时读取缓存。"""
    expected_payload = _canonical_contract_json(contract)
    expected_digest = hashlib.sha256(
        expected_payload.encode("utf-8")).hexdigest()
    try:
        with h5py.File(path, "r") as handle:
            payload = _attr_text(handle.attrs.get(_CONTRACT_JSON_ATTR))
            digest = _attr_text(handle.attrs.get(_CONTRACT_SHA_ATTR))
            if payload is None or digest is None:
                return None, "缺少完整物理契约元数据"
            actual_digest = hashlib.sha256(
                payload.encode("utf-8")).hexdigest()
            if digest != actual_digest:
                return None, "HDF5 契约 SHA-256 与 JSON 不一致"
            if payload != expected_payload or digest != expected_digest:
                return None, "HDF5 物理契约与请求不一致"
            if set(handle.keys()) != {"data"}:
                return None, "HDF5 顶层数据集必须只有 data"
            if "data" not in handle:
                return None, "HDF5 缺少 data 数据集"
            dataset = handle["data"]
            if not isinstance(dataset, h5py.Dataset):
                return None, "HDF5 data 不是数据集"
            shape = tuple(dataset.shape)
            if shape != tuple(expected_shape):
                return None, (
                    f"data 完整 shape 不匹配: expected {tuple(expected_shape)}, "
                    f"got {shape}")
            if dataset.dtype != np.dtype(expected_dtype):
                return None, f"data dtype 不匹配: {dataset.dtype}"
            data = dataset[...]
            try:
                finite = _array_all_finite(data)
            except (TypeError, ValueError) as exc:
                return None, f"data 不能执行有限性检查: {exc}"
            if not finite:
                return None, "data 含 NaN 或 Inf"
            return data, None
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return None, f"HDF5 不可读: {exc}"


def _load_first_matching_cache(paths, contract, logger, *, expected_shape,
                               expected_dtype):
    """只读探测新旧路径；没有可证 HDF5 元数据的候选一律跳过。"""
    seen = set()
    for path in paths:
        path = os.fspath(path)
        if path in seen or not os.path.exists(path):
            continue
        seen.add(path)
        if not path.endswith(".h5"):
            _info(logger, f"  ignored cache without provable HDF5 metadata: "
                          f"{path}")
            continue
        array, reason = _load_contract_h5(
            path, contract, expected_shape=expected_shape,
            expected_dtype=expected_dtype)
        if array is not None:
            return array, path
        _info(logger, f"  ignored incompatible cache: {path} ({reason})")
    return None, None


def _float_tag(value):
    """生成简短可读标签；精确身份由完整 SHA-256 保证。"""
    text = repr(float(value))
    if text.endswith(".0"):
        text = text[:-2]
    return (text.replace("-", "m").replace("+", "p")
            .replace(".", "p"))


def _int_tag(value):
    return f"m{abs(value)}" if value < 0 else str(value)


def _sequence_tag(prefix, values):
    if not values:
        return f"{prefix}0_empty"
    return (f"{prefix}{len(values)}_{_int_tag(values[0])}"
            f"to{_int_tag(values[-1])}")


def _safe_tag_text(value):
    return "".join(
        char if char.isalnum() or char == "_" else "-"
        for char in str(value))


def _flow_cache_contract(conf_id, tau, eps, precision):
    tau, eps = _validate_flow_controls(tau, eps)
    precision = _validate_precision(precision)
    return {
        "algorithm_version": _FLOW_ALGORITHM_VERSION,
        "artifact": "flowed_gauge",
        "conf_id": _cache_int(conf_id, "conf_id"),
        "dtype": precision,
        "eps": eps,
        "lattice": {"nt": int(NT), "nx": int(NX)},
        "precision": precision,
        "schema": _CACHE_SCHEMA,
        "shape": [int(NT), int(NX), int(NX), int(NX), 4, 3, 3],
        "tau": tau,
    }


def _flow_cache_tag(contract):
    return (
        f"v1_tau{_float_tag(contract['tau'])}_"
        f"eps{_float_tag(contract['eps'])}_"
        f"p{_safe_tag_text(contract['precision'])}_"
        f"sha256-{_contract_sha256(contract)}")


# ═══════════════════════════════════════════════════════════════════
# 动量集合（[pz, py, px]，格点单位 2π/L）
# ═══════════════════════════════════════════════════════════════════

# 集合 A：z 方向 [0,2,4]，其余为 0
MOMENTA_Z = [(0, 0, 0), (2, 0, 0), (4, 0, 0)]
# 集合 B：所有方向 (x,y,z) ∈ {0,2}³（8 个组合，含全零）
_MOM_DIRS = (0, 2)
MOMENTA_ALL = [(pz, py, px)
               for pz in _MOM_DIRS for py in _MOM_DIRS for px in _MOM_DIRS]


def momentum_tag(mom):
    """动量 → 单射标签；单个非负数字保持 ``P200`` 兼容格式。"""
    momentum = _validate_momenta([mom])[0]
    return _momentum_tag(momentum)


def parse_momentum_tag(tag):
    """解析 ``momentum_tag`` 的 canonical 输出，不接受歧义别名。"""
    if not isinstance(tag, (str, np.str_)):
        raise ValueError("动量标签必须是 canonical 字符串")
    text = str(tag)
    try:
        if len(text) == 4 and text.startswith("P") and text[1:].isdigit():
            momentum = tuple(int(component) for component in text[1:])
        elif text.startswith("P"):
            fields = text[1:].split("_")
            if len(fields) != 3 or any(field == "" for field in fields):
                raise ValueError
            momentum = tuple(int(field) for field in fields)
        else:
            raise ValueError
    except ValueError as exc:
        raise ValueError(
            "动量标签必须是 canonical P200 或 P10_-2_0 形式") from exc
    if momentum_tag(momentum) != text:
        raise ValueError(
            "动量标签不是 canonical 形式；请使用 momentum_tag 生成")
    return momentum


def z_direction_momenta(pz_list=(0, 2, 4)):
    """z 方向动量集合（其余分量为 0）。"""
    return [(pz, 0, 0) for pz in pz_list]


def _lattice_cache_contract():
    return {
        "nev": int(NEV),
        "nev1": int(NEV1),
        "nt": int(NT),
        "nx": int(NX),
    }


def _strict_conf_path(run_dir, conf_id):
    """只构造路径，不创建目录。"""
    return os.path.join(
        os.fspath(run_dir), "data", f"conf{int(conf_id)}")


def _strict_cache_spec(path, contract):
    return {
        "contract": contract,
        "dtype": contract["dtype"],
        "path": os.fspath(path),
        "shape": tuple(contract["shape"]),
    }


def _vertex_cache_specs(conf_id, run_dir, momenta, precision):
    conf_id = _cache_int(conf_id, "conf_id")
    cdir = _strict_conf_path(run_dir, conf_id)
    lattice = _lattice_cache_contract()
    momenta_json = [list(momentum) for momentum in momenta]
    specs = {}
    for kind in ("VdV", "VVV"):
        if kind == "VdV":
            artifact = "tmd9_vertex_vdv"
            shape = [
                lattice["nt"], len(momenta),
                lattice["nev"], lattice["nev"],
            ]
        else:
            artifact = "tmd9_vertex_vvv"
            shape = [
                lattice["nt"], len(momenta), lattice["nev1"],
                lattice["nev1"], lattice["nev1"],
            ]
        contract = {
            "algorithm_version": _VERTEX_ALGORITHM_VERSION,
            "artifact": artifact,
            "conf_id": conf_id,
            "dtype": precision,
            "lattice": dict(lattice),
            "momenta": [list(momentum) for momentum in momenta_json],
            "precision": precision,
            "schema": _CACHE_SCHEMA,
            "shape": shape,
        }
        digest = _contract_sha256(contract)
        filename = (
            f"{kind}_tmd9-strict-v1_nm{len(momenta)}_"
            f"p{precision}_sha256-{digest}_conf{conf_id}.h5")
        specs[kind] = _strict_cache_spec(
            os.path.join(cdir, filename), contract)
    return specs


def _multi_2pt_cache_specs(conf_id, run_dir, momenta, channels,
                            precision, v_kind):
    conf_id = _cache_int(conf_id, "conf_id")
    cdir = _strict_conf_path(run_dir, conf_id)
    lattice = _lattice_cache_contract()
    momenta_json = [list(momentum) for momentum in momenta]
    channels_json = list(channels)
    vertex_kind = "VdV" if v_kind == "VDV" else "VVV"
    vertex_contract = _vertex_cache_specs(
        conf_id, run_dir, momenta, precision)[vertex_kind]["contract"]
    vertex_digest = _contract_sha256(vertex_contract)
    specs = {}
    for channel in channels:
        for momentum in momenta:
            tag = momentum_tag(momentum)
            key = f"corr_{channel}_{tag}"
            contract = {
                "algorithm_version": _MULTI_2PT_ALGORITHM_VERSION,
                "artifact": "tmd9_multi_2pt",
                "channel": channel,
                "channels": list(channels_json),
                "conf_id": conf_id,
                "dtype": "float64",
                "lattice": dict(lattice),
                "momentum": list(momentum),
                "momenta": [
                    list(requested) for requested in momenta_json
                ],
                "precision": precision,
                "schema": _CACHE_SCHEMA,
                "shape": [lattice["nt"]],
                "v_kind": v_kind,
                "vertex_algorithm_version":
                    vertex_contract["algorithm_version"],
                "vertex_artifact": vertex_contract["artifact"],
                "vertex_contract_sha256": vertex_digest,
            }
            digest = _contract_sha256(contract)
            filename = (
                f"{key}_tmd9-strict-v1_nm{len(momenta)}_"
                f"nc{len(channels)}_p{precision}_v{v_kind}_"
                f"sha256-{digest}_conf{conf_id}.h5")
            specs[key] = _strict_cache_spec(
                os.path.join(cdir, filename), contract)
    return specs

# ═══════════════════════════════════════════════════════════════════
# 1. 蒸馏顶点 + 2pt（多动量）
# ═══════════════════════════════════════════════════════════════════

def compute_vertices_multi(conf_id, run_dir, logger, momenta,
                           precision=PRECISION, recompute=False):
    """多动量 VdV/VVV 顶点（test9 strict canonical cache）。"""
    precision = _validate_precision(precision)
    momenta = _validate_momenta(momenta)
    strict_cache = _vertex_cache_specs(
        conf_id, run_dir, momenta, precision)
    return compute_vertices_for_config(
        conf_id, run_dir, logger, precision, recompute,
        mom_sink_vdv=momenta, mom_sink_vvv=momenta,
        strict_cache=strict_cache)


def compute_2pt_multi(conf_id, run_dir, logger, vertices, momenta,
                      precision=PRECISION, channels=('pp',),
                      v_kind='VVV', recompute=False):
    """多动量核子 2pt（test9 strict canonical cache）。"""
    precision = _validate_precision(precision)
    momenta = _validate_momenta(momenta)
    channels = _validate_channels(channels)
    v_kind = _validate_v_kind(v_kind)
    strict_cache = _multi_2pt_cache_specs(
        conf_id, run_dir, momenta, channels, precision, v_kind)
    return compute_2pt_for_config_multi(
        conf_id, run_dir, logger, vertices, momenta,
        precision=precision, channels=channels, v_kind=v_kind,
        strict_cache=strict_cache, recompute=recompute)


# ═══════════════════════════════════════════════════════════════════
# 2. 梯度流 + 胶子 TMD 算符矩阵元
# ═══════════════════════════════════════════════════════════════════

def flow_gauge_for_config(conf_id, tau=3.0, eps=0.05, precision=PRECISION,
                          save_dir=None, logger=print, save_gauge=True):
    """读组态 → Wilson flow → flowed gauge（h5 缓存，可复现）。

    Args:
        conf_id: 组态号
        tau: 流时间（格点单位，τ=3a² → t=3）
        eps: RK3 步长（默认 0.05，Luescher ≤0.05 保证 O(ε³)，60 步）
        precision: complex64/complex128
        save_dir: 非 None 时保存 flowed gauge 到 h5（供并行/复用）
        save_gauge: True 时保存 flowed gauge 到 h5；False 时仅返回
            （避免 GPU→CPU 大拷贝 + swap，用于内存紧张环境）
    Returns:
        flowed gauge V (Nt,Nz,Ny,Nx,4,3,3)，torch 张量（torch 后端时）
    """
    contract = _flow_cache_contract(conf_id, tau, eps, precision)
    backend = get_backend()
    tau = contract["tau"]
    eps = contract["eps"]
    precision = contract["precision"]
    h5p = None
    if save_dir is not None:
        os.makedirs(save_dir, exist_ok=True)
        tag = _flow_cache_tag(contract)
        h5p = os.path.join(
            save_dir, f"flowed_gauge_{tag}_conf{contract['conf_id']}.h5")
        legacy_base = os.path.join(
            save_dir, f"flowed_gauge_{contract['conf_id']}")
        dtype = {
            'complex64': np.complex64,
            'complex128': np.complex128,
        }[precision]
        V, cache_path = _load_first_matching_cache(
            (h5p, h5p[:-3] + '.npy',
             legacy_base + '.h5', legacy_base + '.npy'),
            contract, logger,
            expected_shape=(int(NT), int(NX), int(NX), int(NX), 4, 3, 3),
            expected_dtype=dtype)
        if V is not None:
            _info(logger, f"  conf={conf_id}: loaded flowed gauge "
                          f"{V.shape} {V.dtype} from cache {cache_path}")
            return backend.asarray(V)
    gauge_cpu = read_gauge_lime(get_gauge_path(conf_id), NT, NX)
    dtype = {
        'complex64': np.complex64,
        'complex128': np.complex128,
    }[precision]
    if get_backend_name() == 'torch':
        set_precision(precision)
    G = backend.asarray(gauge_cpu.astype(dtype))
    del gauge_cpu
    E0 = float(flow_action_density(G).mean())
    t0 = time.perf_counter()
    V = wilson_flow(G, tau=tau, eps=eps)
    _validate_contract_array(
        V, "flowed gauge",
        (int(NT), int(NX), int(NX), int(NX), 4, 3, 3), dtype)
    E1 = float(flow_action_density(V).mean())
    dt = time.perf_counter() - t0
    del G
    _info(logger, f"  conf={conf_id}: wilson_flow tau={tau} ({dt:.0f}s), "
                  f"Clover E diagnostic: E(t=0)={E0:.4f}; "
                  f"E(t={tau})={E1:.4f}")
    if h5p is not None and save_gauge:
        _save_contract_h5(V, h5p, contract)
        _info(logger, f"  conf={conf_id}: saved flowed gauge -> {h5p} "
                      f"({os.path.getsize(h5p)/2**20:.0f} MB)")
    return V


def _resolve_staple_length(z_list, staple_length):
    """为一批 z 固定唯一 staple 臂长并校验格点整数语义。"""
    if not z_list:
        raise ValueError('z_list 不能为空')
    if staple_length is None:
        staple_length = max(abs(z) for z in z_list)
    if (isinstance(staple_length, (bool, np.bool_))
            or not isinstance(staple_length, (int, np.integer))
            or staple_length < 0):
        raise ValueError('staple_length 必须是非负非布尔格点整数')
    return int(staple_length)


def _validate_color_normalization(color_normalization):
    if color_normalization not in ('fundamental_trace', 'adjoint'):
        raise ValueError(
            "color_normalization 必须是 'fundamental_trace' 或 'adjoint'")
    return color_normalization


def _tmd_ope_contract(conf_id, tau, eps, precision, z_dir, b_dir,
                      z_list, b_list, staple_length, color_normalization):
    tau, eps, precision, z_dir, b_dir, z_list, b_list = (
        _validate_tmd_request(
            tau, eps, precision, z_dir, b_dir, z_list, b_list))
    return {
        "algorithm_version": _OPE_ALGORITHM_VERSION,
        "artifact": "tmd_ope_time",
        "b_dir": b_dir,
        "b_list": b_list,
        "color_normalization": _validate_color_normalization(
            color_normalization),
        "conf_id": _cache_int(conf_id, "conf_id"),
        "dtype": "float64",
        "eps": eps,
        "lattice": {"nt": int(NT), "nx": int(NX)},
        "precision": precision,
        "schema": _CACHE_SCHEMA,
        "shape": [len(z_list), len(b_list), int(NT)],
        "staple_length": _cache_int(staple_length, "staple_length"),
        "tau": tau,
        "z_dir": z_dir,
        "z_list": z_list,
    }


def _tmd_ope_tag(contract):
    return (
        f"v1_{_sequence_tag('z', contract['z_list'])}_"
        f"{_sequence_tag('b', contract['b_list'])}_"
        f"tau{_float_tag(contract['tau'])}_"
        f"eps{_float_tag(contract['eps'])}_"
        f"p{_safe_tag_text(contract['precision'])}_"
        f"zd{_int_tag(contract['z_dir'])}_"
        f"bd{_int_tag(contract['b_dir'])}_"
        f"L{_int_tag(contract['staple_length'])}_"
        f"C{_safe_tag_text(contract['color_normalization'])}_"
        f"sha256-{_contract_sha256(contract)}")


def _tmd_ope_cache_paths(cdir, contract):
    """返回规范路径及两代旧标签的只读探测候选。"""
    conf_id = contract["conf_id"]
    canonical_base = os.path.join(
        cdir, f"tmd_ope_{_tmd_ope_tag(contract)}_conf{conf_id}")
    z_legacy = ''.join(str(value) for value in contract["z_list"])
    b_legacy = ''.join(str(value) for value in contract["b_list"])
    legacy_tags = (
        f"z{z_legacy}_b{b_legacy}_L{contract['staple_length']}_"
        f"C{contract['color_normalization']}",
        f"z{z_legacy}_b{b_legacy}",
    )
    bases = [canonical_base]
    bases.extend(os.path.join(
        cdir, f"tmd_ope_{tag}_conf{conf_id}") for tag in legacy_tags)
    candidates = []
    for base in bases:
        candidates.extend((base + '.h5', base + '.npy'))
    return canonical_base, candidates


def compute_tmd_ope_time(conf_id, run_dir, logger, z_list, b_list,
                         tau=3.0, eps=0.05, precision=PRECISION,
                         z_dir=2, b_dir=0, recompute=False,
                         gauge_flow_dir=None, staple_length=None,
                         color_normalization='fundamental_trace'):
    """单组态梯度流 TMD 算符逐时间片矩阵元 → (nz, nb, Nt) 实数。

    输出键：'tmd'（(nz, nb, Nt)），保存于 <run_dir>/data/conf<id>/。
    算符 O = M^{tx;tx}+M^{ty;ty}−2M^{xy;xy} 在 flowed gauge 上
    （梯度流重整化：算符自动有限）。
    """
    tau, eps, precision, z_dir, b_dir, z_list, b_list = (
        _validate_tmd_request(
            tau, eps, precision, z_dir, b_dir, z_list, b_list))
    staple_length = _resolve_staple_length(z_list, staple_length)
    color_normalization = _validate_color_normalization(color_normalization)
    contract = _tmd_ope_contract(
        conf_id, tau, eps, precision, z_dir, b_dir,
        z_list, b_list, staple_length, color_normalization)
    conf_id = contract["conf_id"]
    tau = contract["tau"]
    eps = contract["eps"]
    precision = contract["precision"]
    z_dir = contract["z_dir"]
    b_dir = contract["b_dir"]
    z_list = contract["z_list"]
    b_list = contract["b_list"]
    staple_length = contract["staple_length"]
    color_normalization = contract["color_normalization"]
    from ..pipeline._steps import conf_data_dir as _cdir
    cdir = _cdir(run_dir, conf_id)
    path, candidates = _tmd_ope_cache_paths(cdir, contract)
    if not recompute:
        tmd, cache_path = _load_first_matching_cache(
            candidates, contract, logger,
            expected_shape=(len(z_list), len(b_list), int(NT)),
            expected_dtype=np.float64)
        if tmd is not None:
            _info(logger, f"  conf={conf_id}: loaded cached TMD OPE "
                          f"{tmd.shape} from {cache_path}")
            return {'tmd': tmd}

    V = flow_gauge_for_config(conf_id, tau, eps, precision,
                              save_dir=gauge_flow_dir, logger=logger,
                              save_gauge=False)
    backend = get_backend()
    if get_backend_name() == 'torch':
        set_precision(precision)
    Vg = backend.asarray(V)
    del V

    t0 = time.perf_counter()
    tmd = tmd_matrix_elements_time(
        Vg, z_list, b_list, z_dir=z_dir, b_dir=b_dir,
        L=staple_length, color_normalization=color_normalization)
    _validate_contract_array(
        tmd, "TMD OPE", (len(z_list), len(b_list), int(Vg.shape[0])),
        np.float64)
    dt = time.perf_counter() - t0
    _info(logger, f"  conf={conf_id}: TMD OPE z={len(z_list)} b={len(b_list)} "
                  f"({dt:.0f}s) -> {tmd.shape}")
    _save_contract_h5(tmd, path + '.h5', contract)
    del Vg
    return {'tmd': tmd}


# ═══════════════════════════════════════════════════════════════════
# 3. 分析链（比值 → 裸矩阵元 → 重整化 → 匹配 → PDF）
# ═══════════════════════════════════════════════════════════════════

def _momenta_from_tags(momentum_tag_list):
    """解析 compact 或分隔式 canonical 动量标签列表。"""
    if isinstance(momentum_tag_list, (str, bytes)):
        raise ValueError("momentum_tag_list 必须为非空动量标签列表")
    try:
        tags = list(momentum_tag_list)
    except TypeError as exc:
        raise ValueError(
            "momentum_tag_list 必须为非空动量标签列表") from exc
    if not tags:
        raise ValueError("momentum_tag_list 不能为空")
    momenta = [parse_momentum_tag(tag) for tag in tags]
    return [str(tag) for tag in tags], _validate_momenta(momenta)


def load_multi_2pt(run_dir, conf_ids, momentum_tag_list, channels=('pp',),
                   logger=print, *, momenta=None, precision=PRECISION,
                   v_kind='VVV'):
    """严格读取多动量 2pt canonical HDF5。

    既有 ``P000``/``P200``/``P400`` 调用保持可用；多位/负分量使用
    ``P10_-2_0`` canonical 格式，也可通过 ``momenta=`` 显式校验。
    """
    precision = _validate_precision(precision)
    channels = _validate_channels(channels)
    v_kind = _validate_v_kind(v_kind)
    if momenta is None:
        tags, momenta = _momenta_from_tags(momentum_tag_list)
    else:
        momenta = _validate_momenta(momenta)
        if isinstance(momentum_tag_list, (str, bytes)):
            raise ValueError(
                "momentum_tag_list 必须为非空动量标签列表")
        try:
            tags = [str(tag) for tag in momentum_tag_list]
        except TypeError as exc:
            raise ValueError(
                "momentum_tag_list 必须为非空动量标签列表") from exc
        expected_tags = [momentum_tag(momentum) for momentum in momenta]
        if not tags or tags != expected_tags:
            raise ValueError(
                "momentum_tag_list 必须与完整有序 momenta 精确一致")

    corr = {}
    for cid in conf_ids:
        specs = _multi_2pt_cache_specs(
            cid, run_dir, momenta, channels, precision, v_kind)
        entry = {}
        for key, spec in specs.items():
            array, reason = _load_contract_h5(
                spec['path'], spec['contract'],
                expected_shape=spec['shape'],
                expected_dtype=spec['dtype'])
            if array is None:
                _info(logger, f"  ignored incompatible multi-2pt cache: "
                              f"{spec['path']} ({reason})")
                entry = {}
                break
            entry[key] = array
        if len(entry) == len(specs):
            corr[_cache_int(cid, "conf_id")] = entry
    _info(logger, f"  Loaded multi-momentum 2pt for {len(corr)} configs "
                  f"({len(tags)} momenta)")
    return corr


def load_tmd_ope_all(run_dir, conf_ids, z_list, b_list, logger=print,
                     staple_length=None,
                     color_normalization='fundamental_trace',
                     tau=3.0, eps=0.05, precision=PRECISION,
                     z_dir=2, b_dir=0):
    """读取 TMD OPE：{conf_id: {'tmd': (nz, nb, Nt)}}。"""
    tau, eps, precision, z_dir, b_dir, z_list, b_list = (
        _validate_tmd_request(
            tau, eps, precision, z_dir, b_dir, z_list, b_list))
    staple_length = _resolve_staple_length(z_list, staple_length)
    color_normalization = _validate_color_normalization(color_normalization)
    ope = {}
    for cid in conf_ids:
        contract = _tmd_ope_contract(
            cid, tau, eps, precision, z_dir, b_dir,
            z_list, b_list, staple_length, color_normalization)
        cdir = _strict_conf_path(run_dir, contract["conf_id"])
        _base, candidates = _tmd_ope_cache_paths(cdir, contract)
        tmd, _cache_path = _load_first_matching_cache(
            candidates, contract, logger,
            expected_shape=(len(z_list), len(b_list), int(NT)),
            expected_dtype=np.float64)
        if tmd is not None:
            ope[contract["conf_id"]] = {'tmd': tmd}
    _info(logger, f"  Loaded TMD OPE for {len(ope)} configs")
    return ope


def self_renormalize(c0):
    """梯度流自重整化：hR(z,b) = c0(z,b) / c0(z=0,b)。

    c0: (Nsample, nz, nb) 逐样本裸矩阵元。
    Returns: (hR, norm) 逐样本。
    """
    c0 = np.asarray(c0, dtype=float)
    norm = c0[:, 0:1, :]           # z=0 每样本每 b
    return c0 / norm, norm


def tmd_renormalize_hybrid(c0_pz, c0_pz0, zs, z_s=None, *, zr_fit):
    """混合方案拼接（短距比值 + 长距 ``Z_R``），逐 sample、逐 b。

    短距 ``z < z_s`` 使用 ``c0_pz / c0_pz0``；令 ``i_s`` 为首个
    ``zs[i_s] >= z_s`` 的格点，长距使用
    ``(c0_pz / Z_R) * (Z_R[i_s] / c0_pz0[i_s])``，与
    :func:`pyqcd.renorm._hybrid.hR_z_Pz` 的离散拼接定义一致。

    Args:
        c0_pz: ``(Nsample, nz, nb)`` 的非零动量裸矩阵元。
        c0_pz0: 与 ``c0_pz`` 同形的零动量裸矩阵元。
        zs: 严格递增且有限的 ``(nz,)`` z 网格。
        z_s: 拼接坐标；允许闭区间 ``[zs[0], zs[-1]]``，默认取中点
            网格 ``zs[nz // 2]``。
        zr_fit: 强制关键字参数，有限的 ``Z_R(z)``，shape ``(nz,)``；
            在 sample 与 b 轴上共享并显式广播。

    Returns:
        ``(Nsample, nz, nb)`` 的有限重整化矩阵元。
    """
    c0 = np.asarray(c0_pz, dtype=float)
    c00 = np.asarray(c0_pz0, dtype=float)
    z_values = np.asarray(zs, dtype=float)
    zr = np.asarray(zr_fit, dtype=float)

    if c0.ndim != 3 or c00.ndim != 3:
        raise ValueError("c0_pz 与 c0_pz0 必须为 (Nsample, nz, nb) 三维数组")
    if c0.shape != c00.shape:
        raise ValueError("c0_pz 与 c0_pz0 shape 必须完全相同")
    if any(size == 0 for size in c0.shape):
        raise ValueError("c0_pz 与 c0_pz0 的各轴均不得为空")

    nz = c0.shape[1]
    if z_values.ndim != 1 or z_values.shape != (nz,):
        raise ValueError(f"zs 必须为与 z 轴一致的 ({nz},) 数组")
    if zr.ndim != 1 or zr.shape != (nz,):
        raise ValueError(f"zr_fit 必须为与 z 轴一致的 ({nz},) 数组")

    for name, values in (
            ("c0_pz", c0), ("c0_pz0", c00),
            ("zs", z_values), ("zr_fit", zr)):
        if not np.all(np.isfinite(values)):
            raise ValueError(f"{name} 必须全部有限")
    if np.any(np.diff(z_values) <= 0.0):
        raise ValueError("zs 必须严格递增")

    if z_s is None:
        z_switch = float(z_values[nz // 2])
    else:
        z_switch_array = np.asarray(z_s, dtype=float)
        if z_switch_array.ndim != 0:
            raise ValueError("z_s 必须为有限标量")
        z_switch = float(z_switch_array)
    if not np.isfinite(z_switch):
        raise ValueError("z_s 必须为有限标量")
    if z_switch < z_values[0] or z_switch > z_values[-1]:
        raise ValueError("z_s 必须位于 zs 的闭区间内")

    short_mask = z_values < z_switch
    long_mask = ~short_mask
    switch_index = int(np.flatnonzero(long_mask)[0])
    if np.any(c00[:, short_mask, :] == 0.0):
        raise ValueError("短距 c0_pz0 分母不得为零")
    if np.any(c00[:, switch_index, :] == 0.0):
        raise ValueError("拼接点 c0_pz0 分母不得为零")
    if np.any(zr[long_mask] == 0.0):
        raise ValueError("长距 zr_fit 分母不得为零")

    hR = np.empty_like(c0)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        hR[:, short_mask, :] = (
            c0[:, short_mask, :] / c00[:, short_mask, :])
        eta_s = zr[switch_index] / c00[:, switch_index, :]
        hR[:, long_mask, :] = (
            c0[:, long_mask, :] / zr[None, long_mask, None]
            * eta_s[:, None, :])
    if not np.all(np.isfinite(hR)):
        raise ValueError("混合重整化结果必须全部有限")
    return hR
