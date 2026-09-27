"""
9 步管线计算编排（pyqcd/pipeline/_steps）
==========================================

照抄冻结蒸馏基线的 compute_vertex/compute_contraction/
compute_ope/analyze/report/run_pipeline 编排逻辑（成功实例基线），
但所有计算调用 pyqcd 子包（lattice/tools/vertex/contraction/operator/
analysis），自包含且不反向依赖测试包。

步骤与逻辑输出沿用基线；张量新产物统一为 `.h5`，读取时兼容旧 `.npy/.npz`：

    data/conf{id}/VdV_mom_{id}.h5, VVV_mom_{id}.h5
    data/conf{id}/corr_{ch}_{P0|P2}_{id}.h5
    data/conf{id}/ops_mu{mu}_nu{nu}_dz{dz}_conf{id}.h5, ope_combined_conf{id}.h5
    data/conf{id}/{proton|pion}_{P0|P2}_3pt_{id}.h5, pjnnjnp_4pt_{id}.h5
    data/analysis/{meff|corr}_{had}_{mom}_{mean|err}.h5
    data/analysis/ratio_{had}_{mom}_{mean|err}.h5
    analysis/disconnected/{ratio,0_fit_data,1_fit_report,c0/chi2/ratio png}
    plots/{meff_all_channels,correlators_all_channels,ratio_3pt_all_channels}.png
    physics_report.tex/pdf（xelatex 两遍）
    analysis_summary.json, run_config.json
"""
from __future__ import annotations

import gc
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from collections import OrderedDict
from datetime import datetime

import h5py
import numpy as np

from ..tools import (
    dump_env, set_backend, get_backend, get_backend_name, set_precision,
)
from ..tools._io import (
    readin_eigvecs_gpu, readin_peram_time_slice,
    save_tensor_h5, load_tensor_h5,
)
from ..lattice import gamma
from ..vertex import phase_exp_2pt, phase_exp_3pt, Mom_VdV_sink_t
from ..contraction import (
    PeramRegistry, VRegistry, GammaRegistry, dynamic_contraction,
    clear_plan_cache, seq_peram,
)
from ..operator import (
    read_gauge_lime, gluon_ope_operator_z0, gluon_ope_channel,
    FieldStrengthCache, OPEChannelSpec, plaquette_clover,
    resolve_ildg_binary_record,
)
from . import _config as _pipeline_config
from ._config import (
    NT, NX, NEV, NEV1, ALttc, CONF_IDS, PRECISION,
    MOM_SINK_VDV, MOM_SINK_VVV, ANALYSIS_MOMENTA,
    PP_SINK, PP_SRC, PN_SINK, PN_SRC, PION_SINK, PION_SRC,
    PJN_SINK, PJN_SRC, PJN_CURR, PION3_SINK, PION3_SRC, PION3_CURR,
    PJNNJNP_SINK, PJNNJNP_SRC, PJNNJNP_CURR,
    FOURPT_NEV1, FOURPT_TSEP, FOURPT_MOM, FOURPT_SRC_STEP,
    T_SEP, T_SEP_3PT, DELTA_Z, Z_DIR, OPE_COMPONENTS,
    get_eigen_path, get_peram_dir, get_gauge_path,
)
from ._run_dir import reserve_unique_run_dir
from ._validate import ProgressLog

try:  # GPU 内存探测（仅 try/except，遵守 pyqcd 反模式约定）
    import cupy as _cp
    HAS_CUPY = True
except ImportError:
    _cp = None
    HAS_CUPY = False


# ═══════════════════════════════════════════════════════════════════
# 通用工具（照抄 docker-v20260805/utils.py 的用时部分）
# ═══════════════════════════════════════════════════════════════════

def _info(logger, msg):
    """兼容 print 与 logging.Logger。"""
    if logger is None:
        return
    if hasattr(logger, 'info'):
        logger.info(msg)
    else:
        logger(msg)


def _momentum_tag(momentum):
    """边界明确的三分量动量标签；保留常用单数字 ``P200``。"""
    try:
        components = tuple(momentum)
    except TypeError as exc:
        raise ValueError("momentum 必须恰含三个整数") from exc
    if (len(components) != 3
            or any(isinstance(value, (bool, np.bool_))
                   or not isinstance(value, (int, np.integer))
                   for value in components)):
        raise ValueError("momentum 必须恰含三个非布尔整数")
    components = tuple(int(value) for value in components)
    if all(0 <= value <= 9 for value in components):
        return "P" + "".join(str(value) for value in components)
    return "P" + "_".join(str(value) for value in components)


def _warn(logger, msg):
    if logger is None:
        return
    if hasattr(logger, 'warning'):
        logger.warning(msg)
    else:
        logger(f"[warn] {msg}")


def _backend_synchronizer():
    """Capture the configured GPU backend's synchronization callback."""
    backend_name = get_backend_name()
    if backend_name == 'cupy':
        return _cp.cuda.Stream.null.synchronize
    if backend_name == 'torch':
        backend = get_backend()
        device = backend.get_device()
        if device is not None and str(device).startswith('cuda'):
            return lambda: backend.torch.cuda.synchronize(device)
    return None


def _timer(name, logger, fn, *args, **kw):
    """带计时地执行 fn(*args, **kw)，返回 (结果, 秒数)。"""
    synchronize = _backend_synchronizer()
    if synchronize is not None:
        synchronize()
    t0 = time.perf_counter()
    try:
        res = fn(*args, **kw)
    except BaseException:
        if synchronize is not None:
            try:
                synchronize()
            except BaseException:
                # 保留计算/用户中断作为主异常；后同步仅属清理路径。
                pass
        raise
    else:
        # 计算成功时，同步失败意味着结果尚未可靠完成，必须上抛。
        if synchronize is not None:
            synchronize()
    el = time.perf_counter() - t0
    _info(logger, f"{name}: {el:.3f} s")
    return res, el


def free_gpu_memory():
    """释放 GPU 内存（cupy 内存池 / torch 缓存，按当前后端）。"""
    if get_backend_name() == 'torch':
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass
    if get_backend_name() == 'cupy' and HAS_CUPY:
        try:
            _cp.get_default_memory_pool().free_all_blocks()
        except Exception:
            pass


def log_gpu_memory(logger, label: str = ''):
    if get_backend_name() == 'torch':
        try:
            import torch
            if torch.cuda.is_available():
                free, total = torch.cuda.mem_get_info()
                _info(logger, f"GPU memory{label}: used={(total - free)/2**20:.0f} MB, "
                              f"free={free/2**20:.0f} MB, total={total/2**20:.0f} MB")
                return
        except Exception:
            pass
    if get_backend_name() == 'cupy' and HAS_CUPY:
        try:
            total, used = _cp.cuda.runtime.memGetInfo()
            _info(logger, f"GPU memory{label}: used={(total - used)/2**20:.0f} MB, "
                          f"free={used/2**20:.0f} MB, total={total/2**20:.0f} MB")
        except Exception:
            pass
    else:
        _info(logger, f"GPU memory{label}: N/A")


_STRICT_CONTRACT_JSON_ATTR = "pyqcd_cache_contract_json"
_STRICT_CONTRACT_SHA_ATTR = "pyqcd_cache_contract_sha256"
_OPE_PAYLOAD_SHA_ATTR = "pyqcd_ope_payload_sha256"

_OPE_METADATA_SCHEMA = "1"
_OPE_METADATA_SCHEMA_ATTR = "pyqcd_ope_metadata_schema"
_OPE_CHANNEL_SPECS_ATTR = "pyqcd_ope_channel_specs_json"
_OPE_COMBINED_SPEC_ATTR = "pyqcd_ope_combined_spec_json"
_OPE_CHANNEL_FIELDS = frozenset((
    "mode", "mu", "nu", "mu2", "nu2", "z_dir", "second_insert",
    "direction", "sum_kind", "normalization", "output_projection",
    "field_projection"))
_OPE_COMBINED_FIELDS = frozenset((
    "mode", "components", "coefficients", "z_dir", "second_insert",
    "direction", "sum_kind", "normalization", "output_projection",
    "field_projection"))
_OPE_SHARED_FIELDS = (
    "mode", "z_dir", "second_insert", "direction", "sum_kind",
    "normalization", "output_projection", "field_projection")


def _strict_contract_payload(contract):
    return json.dumps(
        contract, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False)


def _strict_contract_attrs(contract):
    payload = _strict_contract_payload(contract)
    return {
        _STRICT_CONTRACT_JSON_ATTR: payload,
        _STRICT_CONTRACT_SHA_ATTR: hashlib.sha256(
            payload.encode('utf-8')).hexdigest(),
    }


def _ope_payload_sha256(array):
    """Hash an OPE payload using its canonical C-order byte representation."""
    if hasattr(array, 'detach'):
        array = array.detach().cpu().numpy()
    elif hasattr(array, 'get') and callable(array.get):
        array = array.get()
    array = np.ascontiguousarray(np.asarray(array))
    return hashlib.sha256(array.tobytes(order='C')).hexdigest()


def _ope_payload_attrs(array):
    """Return the OPE-only payload integrity attribute."""
    return {_OPE_PAYLOAD_SHA_ATTR: _ope_payload_sha256(array)}


def _strict_attr_text(value):
    if isinstance(value, (bytes, np.bytes_)):
        return bytes(value).decode('utf-8')
    if isinstance(value, (str, np.str_)):
        return str(value)
    return value if isinstance(value, str) else None


def _ope_metadata_attrs(channel_metadata, combined_spec):
    """Encode OPE channel identity as canonical JSON HDF5 attributes."""
    return {
        _OPE_METADATA_SCHEMA_ATTR: _OPE_METADATA_SCHEMA,
        _OPE_CHANNEL_SPECS_ATTR: _strict_contract_payload(channel_metadata),
        _OPE_COMBINED_SPEC_ATTR: _strict_contract_payload(combined_spec),
    }


def _validate_ope_metadata_payloads(channel_text, combined_text):
    """Validate and decode the complete OPE metadata contract.

    Validation is deliberately independent of filenames, array shapes, and
    the current pipeline defaults.  A valid payload must describe one
    internally consistent insertion family; in particular a combined
    contract cannot mix F and Ftilde channel metadata.
    """
    if not isinstance(channel_text, str) or not isinstance(combined_text, str):
        raise ValueError("OPE metadata JSON attrs 必须是 UTF-8 字符串")
    try:
        channel_payload = json.loads(channel_text)
        combined_payload = json.loads(combined_text)
    except (TypeError, ValueError) as exc:
        raise ValueError("OPE metadata JSON 不可解析") from exc

    if channel_text != _strict_contract_payload(channel_payload):
        raise ValueError("channel_specs JSON 不是 canonical JSON")
    if combined_text != _strict_contract_payload(combined_payload):
        raise ValueError("combined_spec JSON 不是 canonical JSON")
    if (not isinstance(channel_payload, list) or not channel_payload
            or any(not isinstance(item, dict) for item in channel_payload)):
        raise ValueError("channel_specs 必须是非空对象列表")
    if (not isinstance(combined_payload, dict)
            or set(combined_payload) != _OPE_COMBINED_FIELDS):
        raise ValueError("combined_spec 字段集合不完整或含未知字段")

    specs = []
    for item in channel_payload:
        if set(item) != _OPE_CHANNEL_FIELDS:
            raise ValueError("channel spec 字段集合不完整或含未知字段")
        try:
            spec = OPEChannelSpec(**item)
        except (TypeError, ValueError) as exc:
            raise ValueError("channel spec 未通过 OPEChannelSpec 校验") from exc
        if spec.to_dict() != item:
            raise ValueError("channel spec 规范化后与 JSON 不一致")
        specs.append(spec)

    components = combined_payload["components"]
    coefficients = combined_payload["coefficients"]
    if (not isinstance(components, list)
            or len(components) != len(specs)
            or not isinstance(coefficients, list)
            or len(coefficients) != len(specs)):
        raise ValueError("combined_spec components/coefficients 长度不一致")

    component_pairs = []
    for component in components:
        if (not isinstance(component, list) or len(component) != 2
                or any(isinstance(value, (bool, np.bool_))
                       or not isinstance(value, (int, np.integer))
                       for value in component)):
            raise ValueError("combined_spec components 必须是二元整数列表")
        component_pairs.append(tuple(int(value) for value in component))
    spec_pairs = [(spec.mu, spec.nu) for spec in specs]
    if (len(set(component_pairs)) != len(component_pairs)
            or len(set(spec_pairs)) != len(spec_pairs)
            or set(component_pairs) != set(spec_pairs)):
        raise ValueError("combined_spec components 与 channel_specs 不一致")

    for coefficient in coefficients:
        if (isinstance(coefficient, (bool, np.bool_))
                or not isinstance(coefficient, (int, float, np.integer,
                                                np.floating))
                or not np.isfinite(coefficient)):
            raise ValueError("combined_spec coefficients 必须是有限实数")

    first = specs[0]
    try:
        # Reuse the public channel validator for all combined shared fields,
        # including strict bool rejection and mode/insertion consistency.
        OPEChannelSpec(
            mode=combined_payload["mode"], mu=first.mu, nu=first.nu,
            mu2=first.mu2, nu2=first.nu2,
            z_dir=combined_payload["z_dir"],
            second_insert=combined_payload["second_insert"],
            direction=combined_payload["direction"],
            sum_kind=combined_payload["sum_kind"],
            normalization=combined_payload["normalization"],
            output_projection=combined_payload["output_projection"],
            field_projection=combined_payload["field_projection"])
    except (TypeError, ValueError) as exc:
        raise ValueError("combined_spec 共享字段未通过 OPEChannelSpec 校验") \
            from exc
    for spec in specs:
        for field in _OPE_SHARED_FIELDS:
            if getattr(spec, field) != combined_payload[field]:
                raise ValueError(
                    f"combined_spec 与 channel_specs 的 {field} 不一致")

    return [spec.to_dict() for spec in specs], combined_payload


def _strict_array(value, name, spec):
    """验证 strict cache 的完整数组边界，不执行隐式 dtype 转换。"""
    if hasattr(value, 'detach'):
        value = value.detach().cpu().numpy()
    elif hasattr(value, 'get') and callable(value.get):
        value = value.get()
    array = np.asarray(value)
    expected_shape = tuple(spec['shape'])
    expected_dtype = np.dtype(spec['dtype'])
    if array.shape != expected_shape:
        raise ValueError(
            f"{name} shape 契约不匹配: expected {expected_shape}, "
            f"got {array.shape}")
    if array.dtype != expected_dtype:
        raise ValueError(
            f"{name} dtype 契约不匹配: expected {expected_dtype}, "
            f"got {array.dtype}")
    try:
        finite = _array_all_finite(array)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 不能执行有限性检查: {exc}") from exc
    if not finite:
        raise ValueError(f"{name} 必须全部有限，不能含 NaN 或 Inf")
    return array


def _array_all_finite(array):
    """等价于 ``isfinite(...).all()``，但限制大型张量临时布尔内存。"""
    array = np.asarray(array)
    if array.ndim == 0:
        return bool(np.isfinite(array))
    for index in range(array.shape[0]):
        if not np.isfinite(array[index]).all():
            return False
    return True


def _load_strict_cache_spec(spec, payload_sha_attr=None):
    """只读加载单个 canonical HDF5；可在同一次读取中校验 payload。"""
    path = os.fspath(spec['path'])
    if not os.path.isfile(path):
        return None, 'canonical 文件不存在'
    expected_attrs = _strict_contract_attrs(spec['contract'])
    try:
        with h5py.File(path, 'r') as handle:
            payload = _strict_attr_text(
                handle.attrs.get(_STRICT_CONTRACT_JSON_ATTR))
            digest = _strict_attr_text(
                handle.attrs.get(_STRICT_CONTRACT_SHA_ATTR))
            if payload is None or digest is None:
                return None, '缺少完整物理契约元数据'
            actual_digest = hashlib.sha256(
                payload.encode('utf-8')).hexdigest()
            if digest != actual_digest:
                return None, 'HDF5 契约 SHA-256 与 JSON 不一致'
            if (payload != expected_attrs[_STRICT_CONTRACT_JSON_ATTR]
                    or digest != expected_attrs[_STRICT_CONTRACT_SHA_ATTR]):
                return None, 'HDF5 物理契约与请求不一致'
            if set(handle.keys()) != {'data'}:
                return None, 'HDF5 顶层数据集必须只有 data'
            dataset = handle['data']
            if not isinstance(dataset, h5py.Dataset):
                return None, 'HDF5 data 不是数据集'
            if tuple(dataset.shape) != tuple(spec['shape']):
                return None, 'data 完整 shape 不匹配'
            if dataset.dtype != np.dtype(spec['dtype']):
                return None, 'data dtype 不匹配'
            array = dataset[...]
            try:
                finite = _array_all_finite(array)
            except (TypeError, ValueError) as exc:
                return None, f'data 不能执行有限性检查: {exc}'
            if not finite:
                return None, 'data 含 NaN 或 Inf'
            if payload_sha_attr is not None:
                payload_digest = _strict_attr_text(
                    handle.attrs.get(payload_sha_attr))
                if payload_digest is None:
                    return None, f'缺少 payload SHA-256 属性 {payload_sha_attr}'
                actual_payload_digest = _ope_payload_sha256(array)
                if payload_digest != actual_payload_digest:
                    return None, 'data payload SHA-256 不匹配'
            return array, None
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return None, f'HDF5 不可读: {exc}'


def _load_strict_cache_mapping(specs, logger, payload_sha_attr=None):
    """仅当一组 canonical artifact 全部匹配时返回。"""
    loaded = {}
    for name, spec in specs.items():
        array, reason = _load_strict_cache_spec(
            spec, payload_sha_attr=payload_sha_attr)
        if array is None:
            _info(logger, f"  ignored incompatible strict cache: "
                          f"{spec['path']} ({reason})")
            return None
        loaded[name] = array
    return loaded


def save_array(filepath, arr, logger=None, attrs=None):
    """保存数组（GPU → CPU 转换后 .h5；h5py 为唯一读写工具）。

    兼容旧调用：传入 .npy 路径时自动改存 .h5；旧 .npy 产物的
    读取由 ``_load_any`` 回退支持。
    """
    filepath = os.fspath(filepath)
    if filepath.endswith(('.npy', '.npz')):
        filepath = filepath.rsplit('.', 1)[0] + '.h5'
    elif not filepath.endswith('.h5'):
        filepath += '.h5'
    directory = os.path.dirname(filepath) or '.'
    os.makedirs(directory, exist_ok=True)
    with tempfile.NamedTemporaryFile(
            dir=directory, prefix=f'.{os.path.basename(filepath)}.',
            suffix='.tmp.h5', delete=False) as temporary:
        temporary_path = temporary.name
    try:
        save_tensor_h5(arr, temporary_path)
        if attrs is not None:
            with h5py.File(temporary_path, 'r+') as handle:
                if set(handle.keys()) != {'data'}:
                    raise ValueError(
                        "strict HDF5 顶层数据集必须只有 data")
                if not isinstance(handle['data'], h5py.Dataset):
                    raise ValueError("strict HDF5 data 必须是 Dataset")
                for key, value in dict(attrs).items():
                    handle.attrs[str(key)] = value
                handle.flush()
        os.replace(temporary_path, filepath)
    finally:
        try:
            os.unlink(temporary_path)
        except OSError:
            # 临时文件清理是 best-effort，不能覆盖写入或发布异常。
            pass
    arr_np = arr.get() if hasattr(arr, 'get') else np.asarray(arr)
    _info(logger, f"Saved {os.path.basename(filepath)} "
                  f"shape={np.shape(arr)} dtype={getattr(arr_np, 'dtype', '?')} "
                  f"({os.path.getsize(filepath)/1024:.1f} KB)")


def _array_stem(path):
    """去掉受支持的数组后缀，统一生产者与兼容读取器的路径语义。"""
    path = os.fspath(path)
    for ext in ('.h5', '.npy', '.npz'):
        if path.endswith(ext):
            return path[:-len(ext)]
    return path


def _existing_array_path(path_without_ext):
    """Return the preferred existing array path for a stem, if any."""
    stem = _array_stem(path_without_ext)
    for ext in ('.h5', '.npy', '.npz'):
        path = stem + ext
        if os.path.exists(path):
            return path
    return None


def _array_exists(path):
    """规范 HDF5 或旧 NumPy 产物是否存在。"""
    stem = _array_stem(path)
    return any(os.path.exists(stem + ext) for ext in ('.h5', '.npy', '.npz'))


def _read_ope_metadata(path_without_ext):
    """Read OPE identity only from a complete, validated HDF5 attr set.

    Legacy NumPy/NPZ files and HDF5 files without all three OPE attrs remain
    readable as arrays, but they are never assigned the current default
    channel semantics.
    """
    h5_path = _array_stem(path_without_ext) + '.h5'
    if not os.path.isfile(h5_path):
        return 'missing', None
    try:
        with h5py.File(h5_path, 'r') as handle:
            present = tuple(
                key in handle.attrs for key in (
                    _OPE_METADATA_SCHEMA_ATTR,
                    _OPE_CHANNEL_SPECS_ATTR,
                    _OPE_COMBINED_SPEC_ATTR))
            schema = _strict_attr_text(
                handle.attrs.get(_OPE_METADATA_SCHEMA_ATTR))
            channel_text = _strict_attr_text(
                handle.attrs.get(_OPE_CHANNEL_SPECS_ATTR))
            combined_text = _strict_attr_text(
                handle.attrs.get(_OPE_COMBINED_SPEC_ATTR))
    except (OSError, RuntimeError, TypeError, UnicodeError, ValueError):
        return 'invalid', None

    if not any(present):
        return 'missing', None
    if (not all(present) or schema != _OPE_METADATA_SCHEMA
            or channel_text is None or combined_text is None):
        return 'invalid', None
    try:
        metadata = _validate_ope_metadata_payloads(
            channel_text, combined_text)
    except (TypeError, ValueError, UnicodeError):
        return 'invalid', None
    return 'validated', metadata


def _read_ope_source_identity_status(path_without_ext, conf_id):
    """Classify current-source freshness for a canonical combined OPE.

    This is a provenance snapshot for ``load_ope`` rather than a cache-hit
    decision.  Legacy artifacts have no strict contract and therefore report
    ``missing``; a source recorded without positive stat evidence reports
    ``unverified``.  Callers must not interpret the result as a lock or a
    byte-level immutability guarantee.
    """
    h5_path = _array_stem(path_without_ext) + '.h5'
    if not os.path.isfile(h5_path):
        return 'missing'
    try:
        with h5py.File(h5_path, 'r') as handle:
            present = tuple(
                key in handle.attrs for key in (
                    _STRICT_CONTRACT_JSON_ATTR,
                    _STRICT_CONTRACT_SHA_ATTR))
            payload = _strict_attr_text(
                handle.attrs.get(_STRICT_CONTRACT_JSON_ATTR))
            digest = _strict_attr_text(
                handle.attrs.get(_STRICT_CONTRACT_SHA_ATTR))
    except (OSError, RuntimeError, TypeError, UnicodeError, ValueError):
        return 'invalid'

    if not any(present):
        return 'missing'
    if not all(present) or payload is None or digest is None:
        return 'invalid'
    if hashlib.sha256(payload.encode('utf-8')).hexdigest() != digest:
        return 'invalid'
    try:
        contract = json.loads(payload)
        canonical = _strict_contract_payload(contract)
    except (TypeError, ValueError, UnicodeError):
        return 'invalid'
    if (not isinstance(contract, dict) or payload != canonical
            or contract.get('artifact') != 'ope_combined'
            or contract.get('conf_id') != int(conf_id)):
        return 'invalid'

    source = contract.get('gauge_source')
    if (not isinstance(source, dict)
            or not isinstance(source.get('path'), str)
            or not isinstance(source.get('stat_available'), bool)):
        return 'invalid'
    if not source['stat_available']:
        return 'unverified'
    try:
        current_path = _canonical_gauge_input(get_gauge_path(int(conf_id)))
        current = _gauge_source_identity(current_path)
    except (KeyError, OSError, TypeError, ValueError):
        return 'unavailable'
    if not current.get('stat_available', False):
        return 'unavailable'
    return 'validated' if current == source else 'stale'


def _load_any(path_without_ext, dataset='data'):
    """读取数组：优先 .h5（新格式），回退 .npy/.npz（旧产物兼容）。"""
    path_without_ext = _array_stem(path_without_ext)
    h5p = path_without_ext + '.h5'
    if os.path.exists(h5p):
        return load_tensor_h5(h5p, dataset=dataset)
    for ext, ds in (('.npy', None), ('.npz', 'ops')):
        p = path_without_ext + ext
        if os.path.exists(p):
            if ext == '.npy':
                return np.load(p)
            return np.load(p)[ds]
    raise FileNotFoundError(f"no data file for {path_without_ext}")


def _load_exact_cache_array(path_without_ext, expected_shape,
                            expected_dtype):
    """读取 resume artifact，并严格核验 schema/shape/dtype/finite。"""
    stem = _array_stem(path_without_ext)
    h5_path = stem + '.h5'
    npy_path = stem + '.npy'
    try:
        if os.path.exists(h5_path):
            with h5py.File(h5_path, 'r') as handle:
                if set(handle.keys()) != {'data'}:
                    return None, 'HDF5 顶层数据集必须只有 data'
                dataset = handle['data']
                if not isinstance(dataset, h5py.Dataset):
                    return None, 'HDF5 data 不是 Dataset'
                if tuple(dataset.shape) != tuple(expected_shape):
                    return None, 'data shape 不匹配'
                if dataset.dtype != np.dtype(expected_dtype):
                    return None, 'data dtype 不匹配'
                array = dataset[...]
        elif os.path.exists(npy_path):
            array = np.load(npy_path, allow_pickle=False)
        else:
            return None, 'artifact 不存在'
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return None, f'artifact 不可读: {exc}'

    array = np.asarray(array)
    if array.shape != tuple(expected_shape):
        return None, 'array shape 不匹配'
    if array.dtype != np.dtype(expected_dtype):
        return None, 'array dtype 不匹配'
    try:
        finite = _array_all_finite(array)
    except (TypeError, ValueError) as exc:
        return None, f'array 不能执行有限性检查: {exc}'
    if not finite:
        return None, 'array 含 NaN 或 Inf'
    return array, None


def conf_data_dir(run_dir, conf_id):
    d = os.path.join(run_dir, 'data', f'conf{conf_id}')
    os.makedirs(d, exist_ok=True)
    return d


def dump_config_snapshot(config: dict, filepath: str, logger=None):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(config, f, indent=2, default=str)
    _info(logger, f"Config snapshot -> {filepath}")


# ═══════════════════════════════════════════════════════════════════
# Step 1 — 顶点函数 VdV / VVV（照抄 compute_vertex.py）
# ═══════════════════════════════════════════════════════════════════

def _compute_vvv_single_t_gpu(ev_t_gpu, ph_gpu, Nx, Nev1):
    """单时间片 VVV —— x-slice 分解（比单 einsum 快 ~20×）。"""
    backend = get_backend()
    VVV_t = backend.zeros((Nev1, Nev1, Nev1), dtype=ev_t_gpu.dtype)
    L = Nx * Nx
    for xi in range(Nx):
        s, e = xi * L, (xi + 1) * L
        es = ev_t_gpu[:Nev1, s:e, :]
        ps = ph_gpu[s:e]
        T = backend.einsum('x,ax,bx->abx', ps, es[..., 0], es[..., 1])
        VVV_t += backend.einsum('abx,cx->abc', T, es[..., 2])
        T = backend.einsum('x,ax,bx->abx', ps, es[..., 1], es[..., 2])
        VVV_t += backend.einsum('abx,cx->abc', T, es[..., 0])
        T = backend.einsum('x,ax,bx->abx', ps, es[..., 2], es[..., 0])
        VVV_t += backend.einsum('abx,cx->abc', T, es[..., 1])
        T = backend.einsum('x,ax,bx->abx', ps, es[..., 0], es[..., 2])
        VVV_t -= backend.einsum('abx,cx->abc', T, es[..., 1])
        T = backend.einsum('x,ax,bx->abx', ps, es[..., 1], es[..., 0])
        VVV_t -= backend.einsum('abx,cx->abc', T, es[..., 2])
        T = backend.einsum('x,ax,bx->abx', ps, es[..., 2], es[..., 1])
        VVV_t -= backend.einsum('abx,cx->abc', T, es[..., 0])
    return VVV_t


def _vertex_momentum_fingerprint(mom_vdv, mom_vvv):
    """为两类顶点的完整动量集合生成边界明确、可读的缓存键。"""
    def encode(momenta):
        return '-'.join(
            'p' + '_'.join(str(component) for component in momentum)
            for momentum in momenta
        ) or 'none'

    return f"vdv-{encode(mom_vdv)}__vvv-{encode(mom_vvv)}"


def compute_vertices_for_config(conf_id, run_dir, logger,
                                precision='complex64', recompute=False,
                                mom_sink_vdv=None, mom_sink_vvv=None,
                                strict_cache=None):
    """一个组态的 VdV/VVV（缓存命中则直接读取）。

    动量列表可自定义（默认用全局 MOM_SINK_VDV/MOM_SINK_VVV），
    供 test9 等多动量物理链复用；缓存路径带动量指纹避免串数据。
    """
    if strict_cache is not None and not recompute:
        cached = _load_strict_cache_mapping(strict_cache, logger)
        if cached is not None:
            _info(logger, f"  conf={conf_id}: loaded strict cached vertices "
                          f"VdV{cached['VdV'].shape} "
                          f"VVV{cached['VVV'].shape}")
            return cached

    backend = get_backend()
    if get_backend_name() == 'torch':
        set_precision(precision)
    dtype = np.complex64 if precision == 'complex64' else np.complex128

    mom_vdv = list(mom_sink_vdv) if mom_sink_vdv is not None else list(MOM_SINK_VDV)
    mom_vvv = list(mom_sink_vvv) if mom_sink_vvv is not None else list(MOM_SINK_VVV)

    cdir = conf_data_dir(run_dir, conf_id)
    mom_fp = _vertex_momentum_fingerprint(mom_vdv, mom_vvv) \
        if mom_sink_vdv is not None or mom_sink_vvv is not None else 'mom'
    vdv_path = os.path.join(cdir, f'VdV_{mom_fp}_{conf_id}')
    vvv_path = os.path.join(cdir, f'VVV_{mom_fp}_{conf_id}')

    if (strict_cache is None and _array_exists(vdv_path)
            and _array_exists(vvv_path) and not recompute):
        VdV, vdv_reason = _load_exact_cache_array(
            vdv_path, (NT, len(mom_vdv), NEV, NEV), dtype)
        VVV, vvv_reason = _load_exact_cache_array(
            vvv_path, (NT, len(mom_vvv), NEV1, NEV1, NEV1), dtype)
        if VdV is not None and VVV is not None:
            _info(logger, f"  conf={conf_id}: loaded cached vertices "
                          f"VdV{VdV.shape} VVV{VVV.shape}")
            return {'VdV': VdV, 'VVV': VVV}
        _info(logger, f"  conf={conf_id}: ignored incompatible vertex cache "
                      f"(VdV: {vdv_reason}; VVV: {vvv_reason})")

    _info(logger, f"  conf={conf_id}: computing vertices over {NT} time slices "
                  f"(VdV {len(mom_vdv)} mom, VVV {len(mom_vvv)} mom, "
                  f"Nev={NEV}, Nev1={NEV1}, dtype={dtype.__name__})")

    p2f = np.zeros((len(mom_vdv), NX * NX * NX * 3), dtype=np.complex128)
    for i, mom in enumerate(mom_vdv):
        _ph = phase_exp_2pt(NX, mom)
        _ph_np = _ph.get() if hasattr(_ph, 'get') else np.asarray(_ph)
        p2f[i] = _ph_np.reshape(-1)
    p2f_gpu = backend.asarray(p2f.astype(dtype))
    p3_list = []
    for mom in mom_vvv:
        _ph = phase_exp_3pt(NX, mom)
        p3_list.append(_ph.get() if hasattr(_ph, 'get') else np.asarray(_ph))

    VdV = np.zeros((NT, len(mom_vdv), NEV, NEV), dtype=dtype)
    VVV = np.zeros((NT, len(mom_vvv), NEV1, NEV1, NEV1), dtype=dtype)

    t0 = time.perf_counter()
    for t in range(NT):
        ev = readin_eigvecs_gpu(get_eigen_path(conf_id, t), NX, NEV)
        ev = ev.reshape(NEV, NX, NX, NX, 3).astype(dtype)
        vdv_t = Mom_VdV_sink_t(p2f_gpu, ev)
        VdV[t] = vdv_t.get() if hasattr(vdv_t, 'get') else vdv_t
        ev_flat = ev.reshape(NEV, NX * NX * NX, 3)
        for m, ph_np in enumerate(p3_list):
            ph_gpu = backend.asarray(ph_np.reshape(-1).astype(dtype))
            vvv_t = _compute_vvv_single_t_gpu(ev_flat, ph_gpu, NX, NEV1)
            VVV[t, m] = vvv_t.get() if hasattr(vvv_t, 'get') else vvv_t
        if t % 12 == 0 or t == NT - 1:
            _info(logger, f"    t={t:3d}/{NT}  elapsed={time.perf_counter()-t0:.0f}s")

    free_gpu_memory()
    log_gpu_memory(logger, " after vertices")

    if strict_cache is not None:
        VdV = _strict_array(VdV, 'VdV', strict_cache['VdV'])
        VVV = _strict_array(VVV, 'VVV', strict_cache['VVV'])

    diag = np.abs(np.diag(VdV[0, 0])).real
    _info(logger, f"    VdV(P=0,t=0) diagonal: [{diag.min():.3f}, {diag.max():.3f}]  "
                  f"(≈1 ⇒ orthonormal)")
    _info(logger, f"    VVV(P=0,t=0) |v|: [{np.abs(VVV[0,0]).min():.3e}, "
                  f"{np.abs(VVV[0,0]).max():.3e}]")

    if strict_cache is None:
        save_array(vdv_path, VdV, logger)
        save_array(vvv_path, VVV, logger)
    else:
        save_array(
            strict_cache['VdV']['path'], VdV, logger,
            attrs=_strict_contract_attrs(strict_cache['VdV']['contract']))
        save_array(
            strict_cache['VVV']['path'], VVV, logger,
            attrs=_strict_contract_attrs(strict_cache['VVV']['contract']))
    _info(logger, f"    Saved VdV{VdV.shape} VVV{VVV.shape} for conf={conf_id}")
    return {'VdV': VdV, 'VVV': VVV}


def step_vertex(config, run_dir, logger, progress=None):
    set_backend(config.get('backend', 'cupy'),
                device=config.get('device'))
    for cid in config['conf_ids']:
        started = time.perf_counter()
        _timer(f"  Vertices conf={cid}", logger,
               compute_vertices_for_config, cid, run_dir, logger,
               config['precision'], False)
        free_gpu_memory()
        _record_stage_completion(progress, 'vertex', cid, started)
    _info(logger, f"Vertices computed & saved for {len(config['conf_ids'])} configs")


# ═══════════════════════════════════════════════════════════════════
# Step 2/4/5 — 2pt / 3pt / 4pt 关联函数（照抄 compute_contraction.py）
# ═══════════════════════════════════════════════════════════════════

def _contraction_array(val, expected_shape, label):
    """将收缩结果转为 NumPy，并严格核验调用方约定的自由指标。"""
    v = val.get() if hasattr(val, 'get') else val
    arr = np.asarray(v)
    if arr.shape != expected_shape:
        raise ValueError(
            f"{label} contraction expected shape {expected_shape}, "
            f"got {arr.shape}")
    return arr


def _load_peram_set(backend, peram_dir, conf_id, times, dtype, nev1=None,
                    cache=None, max_size=None):
    """读取 peram 时间片集合（可选外部 cache 增量复用：滑动窗口只补新 t）。

    cache 为 OrderedDict；超过 ``max_size`` 时淘汰最旧时间片，防止
    全 NT 时间片驻留 GPU 显存（72×2×88MB ≈ 12.7GB 不可接受）。
    """
    from collections import OrderedDict
    if nev1 is None:
        nev1 = NEV
    if cache is None:
        cache = OrderedDict()
    if max_size is None:
        max_size = 2 * (T_SEP + 1) + 1
    for t in times:
        if t in cache:
            cache.move_to_end(t)
            continue
        peram_cpu = readin_peram_time_slice(peram_dir, str(conf_id), t, NT, NEV)
        peram_t = backend.asarray(peram_cpu[:, :, :, :nev1, :nev1].astype(dtype))
        cache[t] = (peram_t, seq_peram(peram_t))
        while len(cache) > max_size:
            cache.popitem(last=False)
    return cache


def _run_2pt(backend, sink_op, src_op, peram_t, peram_seq_t,
             t_src, t_sink, v_src, v_sink, v_kind, gamma_name, gamma_val,
             projector, Vindex=('M', 'M')):
    # p(uud) 与 n(udd) 的两点交叉通道由味守恒严格为零；在构造动态
    # Wick 缩并前显式裁决，避免把注册表或实现中的任意 KeyError 误报为物理零。
    if sink_op == PN_SINK and src_op == PN_SRC:
        return 0.0

    PR = PeramRegistry(); VR = VRegistry(); GR = GammaRegistry()
    GR.register(gamma_name, gamma_val)
    GR.register('Projector', (projector, projector))
    if v_kind == 'VVV':
        VR.register('VVV_0', 'tsrc', v_src)
        VR.register('VVV_0', 'tsink', v_sink)
    else:
        VR.register('VDV_0', 'tsrc', v_src)
        VR.register('VDV_0', 'tsink', v_sink)
    PR.register('light', ('tsrc', 'tsrc'), peram_t[t_src])
    PR.register('light', ('tsink', 'tsrc'), peram_t[t_sink])
    PR.register('light', ('tsrc', 'tsink'), peram_seq_t[t_sink])
    dc = dynamic_contraction(
        [(sink_op, src_op)],
        peram_registry=PR, v_registry=VR, gamma_registry=GR,
        Cpt='2pt', Vindex=list(Vindex),
        use_equivalence=False, ignore_dis=False,
        Projection=True, Oindex='M', verbose=False)
    value = _contraction_array(
        dc.calculate_all(), (1,), "2pt Oindex='M'")
    return float(np.real(value[0]))


def compute_2pt_for_config(conf_id, run_dir, logger, vertices,
                           precision=PRECISION, channels=('pp', 'pn', 'pion')):
    backend = get_backend()
    if get_backend_name() == 'torch':
        set_precision(precision)
    dtype = np.complex64 if precision == 'complex64' else np.complex128
    cdir = conf_data_dir(run_dir, conf_id)

    VdV = vertices['VdV']
    VVV = vertices['VVV']
    peram_dir = get_peram_dir(conf_id)

    projector = backend.asarray((gamma(0) + gamma(4)) / 2.0, dtype=dtype)
    g7 = backend.asarray(gamma(7), dtype=dtype)
    g5 = backend.asarray(gamma(5), dtype=dtype)

    acc = {f'corr_{ch}_{mom}': np.zeros(NT, dtype=np.float64)
           for ch in channels for mom in ('P0', 'P2')}
    op_cfg = {
        'pp':   (PP_SINK, PP_SRC, 'VVV', g7, 'gamma_7'),
        'pn':   (PN_SINK, PN_SRC, 'VVV', g7, 'gamma_7'),
        'pion': (PION_SINK, PION_SRC, 'VDV', g5, 'gamma_5'),
    }
    op_cfg = {ch: op_cfg[ch] for ch in channels}

    _info(logger, f"  2pt channels: {list(op_cfg.keys())} at P=(0,0,0),(0,0,2)")
    t_start = time.perf_counter()

    for t_src in range(NT):
        peram_cpu = readin_peram_time_slice(peram_dir, str(conf_id), t_src,
                                            NT, NEV)
        peram_t = backend.asarray(peram_cpu.astype(dtype))
        peram_seq_t = seq_peram(peram_t)

        for t_sink in range(NT):
            dt = (t_sink - t_src + NT) % NT
            for ch, (sink_op, src_op, vkind, gval, gname) in op_cfg.items():
                for mi, mom_tag in enumerate(('P0', 'P2')):
                    if vkind == 'VVV':
                        v_src = backend.asarray(
                            VVV[t_src, mi:mi + 1].conj(), dtype=dtype)
                        v_sink = backend.asarray(
                            VVV[t_sink, mi:mi + 1], dtype=dtype)
                    else:
                        v_src = backend.asarray(
                            VdV[t_src, mi:mi + 1].conj(), dtype=dtype)
                        v_sink = backend.asarray(
                            VdV[t_sink, mi:mi + 1], dtype=dtype)
                    val = _run_2pt(backend, sink_op, src_op,
                                   peram_t, peram_seq_t,
                                   t_src, t_sink, v_src, v_sink, vkind,
                                   gname, gval, projector)
                    acc[f'corr_{ch}_{mom_tag}'][dt] += val / NT

        if t_src % 12 == 0 or t_src == NT - 1:
            _info(logger, f"    t_src={t_src:3d}/{NT} "
                          f"elapsed={time.perf_counter()-t_start:.0f}s "
                          + " ".join(
                              f"{ch}0={acc[f'corr_{ch}_P0'][0]:.4e}"
                              for ch in channels))
        del peram_t, peram_seq_t

    for key, arr in acc.items():
        save_array(os.path.join(cdir, f'{key}_{conf_id}.npy'), arr, logger)
    _info(logger, f"  2pt saved: " + ", ".join(
        f"{k}={v[0]:.3e}" for k, v in acc.items()))
    return acc


def compute_2pt_for_config_multi(conf_id, run_dir, logger, vertices,
                                 momenta=((0, 0, 0), (0, 0, 2), (0, 0, 4)),
                                 precision=PRECISION,
                                 channels=('pp', 'pn', 'pion'),
                                 v_kind='VVV', strict_cache=None,
                                 recompute=False):
    """多动量 2pt（test9 胶子 TMD 物理链用）：按 (pz,py,px) 列表逐动量计算。

    momenta: 形如 [(pz,py,px), ...] 的动量列表（格点单位 2π/L）。
    输出键：单数字分量保持 corr_pp_P000/P200/P400；多位或负分量
    使用边界明确格式（如 corr_pp_P10_-2_0）。
    顶点由 compute_vertices_for_config 的 mom_sink_vdv/vvv 提供对应索引。
    """
    if strict_cache is not None and not recompute:
        cached = _load_strict_cache_mapping(strict_cache, logger)
        if cached is not None:
            _info(logger, f"  conf={conf_id}: loaded strict cached multi-2pt "
                          f"({len(cached)} artifacts)")
            return cached

    backend = get_backend()
    if get_backend_name() == 'torch':
        set_precision(precision)
    dtype = np.complex64 if precision == 'complex64' else np.complex128
    cdir = conf_data_dir(run_dir, conf_id)

    VdV = vertices['VdV']
    VVV = vertices['VVV']
    peram_dir = get_peram_dir(conf_id)
    n_mom = len(momenta)
    tags = [_momentum_tag(momentum) for momentum in momenta]

    projector = backend.asarray((gamma(0) + gamma(4)) / 2.0, dtype=dtype)
    g7 = backend.asarray(gamma(7), dtype=dtype)
    g5 = backend.asarray(gamma(5), dtype=dtype)

    op_cfg = {
        'pp':   (PP_SINK, PP_SRC, g7, 'gamma_7'),
        'pn':   (PN_SINK, PN_SRC, g7, 'gamma_7'),
        'pion': (PION_SINK, PION_SRC, g5, 'gamma_5'),
    }
    op_cfg = {ch: op_cfg[ch] for ch in channels}

    acc = {f'corr_{ch}_{tag}': np.zeros(NT, dtype=np.float64)
           for ch in channels for tag in tags}
    _info(logger, f"  2pt multi: channels={list(op_cfg.keys())}, "
                  f"momenta={list(momenta)}, v_kind={v_kind}")
    t_start = time.perf_counter()

    for t_src in range(NT):
        peram_cpu = readin_peram_time_slice(peram_dir, str(conf_id), t_src,
                                            NT, NEV)
        peram_t = backend.asarray(peram_cpu.astype(dtype))
        peram_seq_t = seq_peram(peram_t)

        for t_sink in range(NT):
            dt = (t_sink - t_src + NT) % NT
            for ch, (sink_op, src_op, gval, gname) in op_cfg.items():
                for mi in range(n_mom):
                    tag = tags[mi]
                    if v_kind == 'VVV':
                        v_src = backend.asarray(
                            VVV[t_src, mi:mi + 1].conj(), dtype=dtype)
                        v_sink = backend.asarray(
                            VVV[t_sink, mi:mi + 1], dtype=dtype)
                    else:
                        v_src = backend.asarray(
                            VdV[t_src, mi:mi + 1].conj(), dtype=dtype)
                        v_sink = backend.asarray(
                            VdV[t_sink, mi:mi + 1], dtype=dtype)
                    val = _run_2pt(backend, sink_op, src_op,
                                   peram_t, peram_seq_t,
                                   t_src, t_sink, v_src, v_sink, v_kind,
                                   gname, gval, projector)
                    acc[f'corr_{ch}_{tag}'][dt] += val / NT

        if t_src % 12 == 0 or t_src == NT - 1:
            _info(logger, f"    t_src={t_src:3d}/{NT} "
                          f"elapsed={time.perf_counter()-t_start:.0f}s "
                          + " ".join(
                              f"{ch}{tags[0]}={acc[f'corr_{ch}_{tags[0]}'][0]:.4e}"
                              for ch in channels))
        del peram_t, peram_seq_t

    if strict_cache is not None:
        if set(acc) != set(strict_cache):
            raise ValueError(
                "multi-2pt strict cache keys 与计算输出不一致")
        acc = {
            key: _strict_array(array, key, strict_cache[key])
            for key, array in acc.items()
        }

    for key, arr in acc.items():
        if strict_cache is None:
            save_array(
                os.path.join(cdir, f'{key}_{conf_id}.npy'), arr, logger)
        else:
            spec = strict_cache[key]
            save_array(
                spec['path'], arr, logger,
                attrs=_strict_contract_attrs(spec['contract']))
    _info(logger, f"  2pt multi saved: " + ", ".join(
        f"{k}={v[0]:.3e}" for k, v in acc.items()))
    return acc


def _2pt_all_present(cdir, conf_id, channels):
    """仅当每个 2pt 产物满足精确 float64/schema 契约才命中。"""
    for ch in channels:
        for mom in ('P0', 'P2'):
            base = os.path.join(cdir, f'corr_{ch}_{mom}_{conf_id}')
            arr, _reason = _load_exact_cache_array(
                base, (NT,), np.float64)
            if arr is None:
                return False
    return True


def step_2pt(config, run_dir, logger, progress=None):
    set_backend(config.get('backend', 'cupy'),
                device=config.get('device'))
    channels = config.get('channels', ('pp', 'pn', 'pion'))
    recompute = config.get('recompute_2pt', False)
    n_hit = 0
    for cid in config['conf_ids']:
        started = time.perf_counter()
        _info(logger, f"\n─── 2pt: conf {cid} ───")
        # 断点续跑（整合 data/from-logs/logs/test8）：该组态 corr_{ch}_{P0,P2} 全存在则跳过
        # （vertex/OPE 缓存由 pyqcd 内部处理，2pt 级此前缺失——服务器长跑
        #   中断后重跑可跳过已完成组态，节省数小时）
        if not recompute and _2pt_all_present(
                conf_data_dir(run_dir, cid), cid, channels):
            _info(logger, f"  conf={cid}: 2pt 缓存命中，跳过"
                          "（recompute_2pt=True 强制重算）")
            n_hit += 1
            _record_stage_completion(progress, '2pt', cid, started)
            continue
        verts = _load_vertices_one(run_dir, cid)
        _timer(f"  2pt conf={cid}", logger, compute_2pt_for_config,
               cid, run_dir, logger, verts, config['precision'],
               channels)
        del verts
        free_gpu_memory()
        _record_stage_completion(progress, '2pt', cid, started)
    if n_hit == len(config['conf_ids']) and n_hit > 0:
        _info(logger, f"2pt 全部缓存命中（{n_hit}/{n_hit}），无需重算")


def _run_3pt(backend, sink_op, src_op, curr_op, PR, VR, GR, Vindex, Gindex):
    dc = dynamic_contraction(
        [(sink_op, src_op, curr_op)],
        peram_registry=PR, v_registry=VR, gamma_registry=GR,
        Cpt='3pt', Vindex=list(Vindex), Gindex=list(Gindex),
        use_equivalence=False, ignore_dis=False,
        Projection=True, Oindex='GM', verbose=False)
    value = _contraction_array(
        dc.calculate_all(), (4, 1), "3pt Oindex='GM'")
    return value[:, 0]


def compute_3pt_for_config(conf_id, run_dir, logger, vertices,
                           precision=PRECISION, t_sep=T_SEP):
    backend = get_backend()
    if get_backend_name() == 'torch':
        set_precision(precision)
    dtype = np.complex64 if precision == 'complex64' else np.complex128
    cdir = conf_data_dir(run_dir, conf_id)
    Ntau = t_sep + 1

    VdV = vertices['VdV']; VVV = vertices['VVV']
    peram_dir = get_peram_dir(conf_id)

    projector = backend.asarray((gamma(0) + gamma(4)) / 2.0, dtype=dtype)
    gmu = backend.asarray([gamma(1), gamma(2), gamma(3), gamma(4)],
                          dtype=dtype)
    g7 = backend.asarray(gamma(7), dtype=dtype)
    g5 = backend.asarray(gamma(5), dtype=dtype)

    acc = {f'{had}_{mom}': np.zeros((Ntau, 4), dtype=np.float64)
           for had in ('proton', 'pion') for mom in ('P0', 'P2')}

    _info(logger, f"  3pt PJN: t_sep={t_sep}, Ntau={Ntau}, gamma_mu=4 components")
    t_start = time.perf_counter()

    peram_cache = OrderedDict()
    for t_src in range(NT):
        t_sink = (t_src + t_sep) % NT
        need_times = sorted(set([t_src, t_sink] + [(t_src + tau) % NT
                                                   for tau in range(Ntau)]))
        pc = _load_peram_set(backend, peram_dir, str(conf_id), need_times,
                             dtype, cache=peram_cache)
        p_src, p_srcS = pc[t_src]
        p_snk, p_snkS = pc[t_sink]

        for tau in range(Ntau):
            t_cur = (t_src + tau) % NT
            p_cur, p_curS = pc[t_cur]

            PR = PeramRegistry()
            PR.register('light', ('tsink', 'tsrc'), p_src[t_sink])
            PR.register('light', ('tcur0', 'tsrc'), p_src[t_cur])
            PR.register('light', ('tsrc', 'tsrc'),  p_src[t_src])
            PR.register('light', ('tsink', 'tcur0'), p_cur[t_sink])
            PR.register('light', ('tcur0', 'tcur0'), p_cur[t_cur])
            PR.register('light', ('tsrc', 'tcur0'),  p_cur[t_src])
            PR.register('light', ('tcur0', 'tsink'), p_snk[t_cur])
            PR.register('light', ('tsink', 'tsink'), p_snk[t_sink])
            PR.register('light', ('tsrc', 'tsink'),  p_srcS[t_sink])
            PR.register('light', ('tsrc', 'tcur0'),  p_srcS[t_cur])
            PR.register('light', ('tcur0', 'tsink'), p_curS[t_sink])
            PR.register('light', ('tsink', 'tcur0'), p_snkS[t_cur])

            GRp = GammaRegistry()
            GRp.register('gamma_7', g7)
            GRp.register('gamma_mu', gmu)
            GRp.register('Projector', (projector, projector))
            GRpi = GammaRegistry()
            GRpi.register('gamma_5', g5)
            GRpi.register('gamma_mu', gmu)
            GRpi.register('Projector', (projector, projector))

            for mi, mom_tag in enumerate(('P0', 'P2')):
                VR = VRegistry()
                VR.register('VVV_0', 'tsrc',
                            backend.asarray(VVV[t_src, mi:mi + 1].conj(), dtype=dtype))
                VR.register('VDV_0', 'tcur0',
                            backend.asarray(VdV[t_cur, mi:mi + 1], dtype=dtype))
                VR.register('VVV_0', 'tsink',
                            backend.asarray(VVV[t_sink, mi:mi + 1], dtype=dtype))
                vn = _run_3pt(backend, PJN_SINK, PJN_SRC, PJN_CURR,
                              PR, VR, GRp, ['M', 'M', 'M'], ['', 'G', ''])
                acc[f'proton_{mom_tag}'][tau] += np.real(vn) / NT

            for mi, mom_tag in enumerate(('P0', 'P2')):
                VR = VRegistry()
                VR.register('VDV_0', 'tsrc',
                            backend.asarray(VdV[t_src, mi:mi + 1].conj(), dtype=dtype))
                VR.register('VDV_0', 'tcur0',
                            backend.asarray(VdV[t_cur, mi:mi + 1], dtype=dtype))
                VR.register('VDV_0', 'tsink',
                            backend.asarray(VdV[t_sink, mi:mi + 1], dtype=dtype))
                vn = _run_3pt(backend, PION3_SINK, PION3_SRC, PION3_CURR,
                              PR, VR, GRpi, ['M', 'M', 'M'], ['', 'G', ''])
                acc[f'pion_{mom_tag}'][tau] += np.real(vn) / NT

            del p_cur, p_curS

        if t_src % 12 == 0 or t_src == NT - 1:
            _info(logger, f"    t_src={t_src:3d}/{NT} "
                          f"elapsed={time.perf_counter()-t_start:.0f}s "
                          f"protP0[0,3]={acc['proton_P0'][0,3]:.3e} "
                          f"piP0[0,3]={acc['pion_P0'][0,3]:.3e}")
        del p_src, p_snk, p_srcS, p_snkS

    for key, arr in acc.items():
        save_array(os.path.join(cdir, f'{key}_3pt_{conf_id}.npy'), arr, logger)
    _info(logger, f"  3pt saved: " + ", ".join(
        f"{k}={v[0,3]:.3e}" for k, v in acc.items()))
    return acc


def step_3pt(config, run_dir, logger, progress=None):
    set_backend(config.get('backend', 'cupy'),
                device=config.get('device'))
    for cid in config['conf_ids']:
        started = time.perf_counter()
        _info(logger, f"\n─── 3pt PJN: conf {cid} ───")
        verts = _load_vertices_one(run_dir, cid)
        _timer(f"  3pt conf={cid}", logger, compute_3pt_for_config,
               cid, run_dir, logger, verts, config['precision'],
               config.get('t_sep', T_SEP))
        del verts
        free_gpu_memory()
        _record_stage_completion(progress, '3pt', cid, started)


def compute_4pt_for_config(conf_id, run_dir, logger, vertices,
                           precision=PRECISION, t_sep=FOURPT_TSEP,
                           nev1=FOURPT_NEV1, momenta=FOURPT_MOM,
                           src_step=FOURPT_SRC_STEP):
    backend = get_backend()
    if get_backend_name() == 'torch':
        set_precision(precision)
    dtype = np.complex64 if precision == 'complex64' else np.complex128
    cdir = conf_data_dir(run_dir, conf_id)
    Ntau = t_sep + 1
    N_mom = len(momenta)
    sources = list(range(0, NT, src_step))

    VdV = vertices['VdV']; VVV = vertices['VVV']
    peram_dir = get_peram_dir(conf_id)

    projector = backend.asarray((gamma(0) + gamma(4)) / 2.0, dtype=dtype)
    gmu = backend.asarray([gamma(1), gamma(2), gamma(3), gamma(4)], dtype=dtype)
    g7 = backend.asarray(gamma(7), dtype=dtype)
    g5 = backend.asarray(gamma(5), dtype=dtype)

    acc = np.zeros((Ntau, N_mom, 4), dtype=np.float64)
    nsrc = len(sources)

    _info(logger, f"  4pt PJNNJNp: n(sink) — J — [p̄ + π](src), t_sep={t_sep}, "
                  f"Nev1={nev1}, mom={momenta}, src_step={src_step} "
                  f"({nsrc}/{NT} sources)")
    t_start = time.perf_counter()
    peram_cache = OrderedDict()

    for t_src in sources:
        t_sink = (t_src + t_sep) % NT
        need_times = sorted(set([t_src, t_sink] + [(t_src + tau) % NT
                                                   for tau in range(Ntau)]))
        pc = _load_peram_set(backend, peram_dir, str(conf_id), need_times,
                             dtype, nev1=nev1, cache=peram_cache)
        p_src, p_srcS = pc[t_src]
        p_snk, p_snkS = pc[t_sink]

        for tau in range(Ntau):
            t_cur = (t_src + tau) % NT
            p_cur, p_curS = pc[t_cur]

            PR = PeramRegistry()
            PR.register('light', ('tsink', 'tsrc'), p_src[t_sink])
            PR.register('light', ('tcur0', 'tsrc'), p_src[t_cur])
            PR.register('light', ('tsrc', 'tsrc'),  p_src[t_src])
            PR.register('light', ('tsink', 'tcur0'), p_cur[t_sink])
            PR.register('light', ('tcur0', 'tcur0'), p_cur[t_cur])
            PR.register('light', ('tsrc', 'tcur0'),  p_cur[t_src])
            PR.register('light', ('tcur0', 'tsink'), p_snk[t_cur])
            PR.register('light', ('tsink', 'tsink'), p_snk[t_sink])
            PR.register('light', ('tsrc', 'tsink'),  p_srcS[t_sink])
            PR.register('light', ('tsrc', 'tcur0'),  p_srcS[t_cur])
            PR.register('light', ('tcur0', 'tsink'), p_curS[t_sink])
            PR.register('light', ('tsink', 'tcur0'), p_snkS[t_cur])

            GR = GammaRegistry()
            GR.register('gamma_7', g7)
            GR.register('gamma_5', g5)
            GR.register('gamma_mu', gmu)
            GR.register('Projector', (projector, projector))

            for imi, mi in enumerate(momenta):
                VR = VRegistry()
                VR.register('VVV_0', 'tsink',
                            backend.asarray(VVV[t_sink, mi:mi + 1, :nev1, :nev1, :nev1],
                                            dtype=dtype))
                VR.register('VDV_0', 'tcur0',
                            backend.asarray(VdV[t_cur, mi:mi + 1, :nev1, :nev1],
                                            dtype=dtype))
                VR.register('VVV_0', 'tsrc',
                            backend.asarray(VVV[t_src, mi:mi + 1, :nev1, :nev1, :nev1].conj(),
                                            dtype=dtype))
                VR.register('VDV_0', 'tsrc',
                            backend.asarray(VdV[t_src, mi:mi + 1, :nev1, :nev1].conj(),
                                            dtype=dtype))
                dc = dynamic_contraction(
                    [(PJNNJNP_SINK, PJNNJNP_SRC, PJNNJNP_CURR)],
                    peram_registry=PR, v_registry=VR, gamma_registry=GR,
                    Cpt='3pt', Vindex=['M', 'M', 'M', 'M'],
                    Gindex=['', 'G', '', ''],
                    use_equivalence=False, ignore_dis=False,
                    Projection=True, Oindex='GM', verbose=False)
                r = dc.calculate_all()
                value = _contraction_array(
                    r, (4, 1), "4pt Oindex='GM'")
                acc[tau, imi] += np.real(value[:, 0]) / nsrc

            del p_cur, p_curS

        if (t_src - sources[0]) % 12 == 0 or t_src == sources[-1]:
            _info(logger, f"    t_src={t_src:3d} "
                          f"elapsed={time.perf_counter()-t_start:.0f}s "
                          f"acc[0,0,3]={acc[0,0,3]:.3e}")
        del p_src, p_snk, p_srcS, p_snkS

    save_array(os.path.join(cdir, f'pjnnjnp_4pt_{conf_id}.npy'), acc, logger)
    _info(logger, f"  4pt PJNNJNp saved: shape={acc.shape}")
    return acc

def step_4pt(config, run_dir, logger, progress=None):
    set_backend(config.get('backend', 'cupy'),
                device=config.get('device'))
    for cid in config['conf_ids']:
        started = time.perf_counter()
        _info(logger, f"\n─── 4pt PJNNJNp: conf {cid} ───")
        verts = _load_vertices_one(run_dir, cid)
        _timer(f"  4pt conf={cid}", logger, compute_4pt_for_config,
               cid, run_dir, logger, verts, config['precision'],
               config.get('fourpt_tsep', FOURPT_TSEP),
               config.get('fourpt_nev1', FOURPT_NEV1),
               config.get('fourpt_mom', FOURPT_MOM),
               config.get('fourpt_src_step', FOURPT_SRC_STEP))
        del verts
        free_gpu_memory()
        _record_stage_completion(progress, '4pt', cid, started)


# ═══════════════════════════════════════════════════════════════════
# Step 3 — OPE 胶子算符（照抄 compute_ope.py，调用 pyqcd.operator）
# ═══════════════════════════════════════════════════════════════════

def _validate_gauge(gauge, logger):
    rng = np.random.default_rng(42)
    Nt, Nz, Ny, Nx, Nd, Nc, _ = gauge.shape
    devs = []
    for _ in range(60):
        t = rng.integers(0, Nt); z = rng.integers(0, Nz)
        y = rng.integers(0, Ny); x = rng.integers(0, Nx)
        U = gauge[t, z, y, x, rng.integers(0, Nd)]
        devs.append(np.abs(U @ U.conj().T - np.eye(Nc)).max())
    plaq = []
    for _ in range(30):
        ti, zi, yi, xi = (rng.integers(0, Nt), rng.integers(0, Nz),
                          rng.integers(0, Ny), rng.integers(0, Nx))
        mu, nu = 1, 2
        U1 = gauge[ti, zi, yi, xi, mu]
        U2 = gauge[ti, zi, (yi + 1) % Ny, xi, nu]
        U3 = gauge[ti, zi, (yi + 1) % Ny, xi, mu].conj().T
        U4 = gauge[ti, zi, yi, xi, nu].conj().T
        plaq.append(np.trace(U1 @ U2 @ U3 @ U4))
    _info(logger, f"  Gauge: unitarity_dev={np.max(devs):.2e}, "
                  f"plaq_trace_re={np.real(np.mean(plaq)):.6f}")


_LEGACY_OPE_COMBINATION = (
    ((3, 0), -1.0),
    ((3, 1), -1.0),
    ((0, 1), 2.0),
)
_OPE_CACHE_SCHEMA = "pyqcd-ope-cache-v2"
_OPE_ALGORITHM_VERSION = "docker-v20260805-legacy-dual-v2-payload-sha256"


def _legacy_ope_channel_spec(component, z_dir):
    """Build the exact docker-v20260805 channel contract for one component."""
    try:
        mu, nu = tuple(component)
    except (TypeError, ValueError) as exc:
        raise ValueError("OPE component 必须是二元 Lorentz 对") from exc
    return OPEChannelSpec(
        mode="legacy_dual",
        mu=mu,
        nu=nu,
        mu2=mu,
        nu2=nu,
        z_dir=z_dir,
        second_insert="Ftilde",
        direction=1,
        sum_kind="full",
        normalization="bare_spatial_sum",
        output_projection="real",
        field_projection="legacy_untraced")


def _legacy_ope_metadata(channel_specs, z_dir):
    """Return JSON-safe metadata for component and combined legacy OPE."""
    combined = {
        "mode": "legacy_dual",
        "components": [list(component) for component, _ in
                        _LEGACY_OPE_COMBINATION],
        "coefficients": [coefficient for _, coefficient in
                         _LEGACY_OPE_COMBINATION],
        "z_dir": int(z_dir),
        "second_insert": "Ftilde",
        "direction": 1,
        "sum_kind": "full",
        "normalization": "bare_spatial_sum",
        "output_projection": "real",
        "field_projection": "legacy_untraced",
    }
    return [spec.to_dict() for spec in channel_specs], combined


def _validate_legacy_ope_request(precision, delta_z, components):
    """Canonicalize the docker-compatible OPE request before any cache IO."""
    if precision not in ('complex64', 'complex128'):
        raise ValueError("precision 必须是 'complex64' 或 'complex128'")
    if (isinstance(delta_z, (bool, np.bool_))
            or not isinstance(delta_z, (int, np.integer))
            or int(delta_z) <= 0):
        raise ValueError("delta_z 必须是正的非布尔整数")
    try:
        normalized = tuple(tuple(component) for component in components)
    except (TypeError, ValueError) as exc:
        raise ValueError("components 必须是 Lorentz 对序列") from exc
    expected = tuple(component for component, _ in _LEGACY_OPE_COMBINATION)
    if (len(normalized) != len(expected)
            or any(len(component) != 2 for component in normalized)
            or len(set(normalized)) != len(normalized)
            or set(normalized) != set(expected)):
        raise ValueError(
            "legacy OPE components 必须恰为 (3,0)、(3,1)、(0,1)")
    return str(precision), int(delta_z), normalized


def _gauge_source_identity(path):
    """Return a cheap conservative identity for the immutable gauge input.

    Full-file hashing would add an avoidable multi-GB read to every cache
    probe.  The shared ILDG resolver first maps a ``.lime.contents``
    directory to its real binary record.  Resolved path plus stat identity
    makes replacement or mutation a cache miss; when the source is
    unavailable, it is never eligible for a strict cache hit.
    """
    try:
        resolved = resolve_ildg_binary_record(path)
    except (OSError, TypeError, ValueError):
        try:
            resolved = os.path.realpath(
                os.path.abspath(os.fsdecode(os.fspath(path))))
        except (OSError, TypeError, ValueError):
            resolved = str(path)
        return {'path': resolved, 'stat_available': False}
    identity = {'path': resolved, 'stat_available': False}
    try:
        stat = os.stat(resolved)
    except OSError:
        return identity
    identity.update({
        'stat_available': True,
        'device': int(stat.st_dev),
        'inode': int(stat.st_ino),
        'size': int(stat.st_size),
        'mtime_ns': int(stat.st_mtime_ns),
        'ctime_ns': int(stat.st_ctime_ns),
    })
    return identity


def _canonical_gauge_input(path):
    """Pass the same resolved record to the reader when it is available."""
    try:
        return resolve_ildg_binary_record(path)
    except (OSError, TypeError, ValueError):
        return os.fspath(path)


def _assert_gauge_source_unchanged(expected, path, phase):
    """Raise before publication when the source stat identity changed."""
    current = _gauge_source_identity(path)
    if current != expected:
        raise RuntimeError(
            "OPE gauge source changed during "
            f"{phase} (stat identity mismatch): "
            f"expected={expected!r}, current={current!r}")


def _combine_legacy_ope(ops):
    """Apply the exact docker ``-O30-O31+2O01`` linear combination."""
    expected = {component for component, _ in _LEGACY_OPE_COMBINATION}
    if set(ops) != expected:
        raise ValueError("legacy OPE 分量集合不完整或含未知通道")
    combined = None
    for component, coefficient in _LEGACY_OPE_COMBINATION:
        term = coefficient * ops[component]
        combined = term if combined is None else combined + term
    return combined


def _ope_cache_specs(conf_id, paths, combined_path, precision, delta_z,
                     z_dir, channel_metadata, combined_spec, gauge_file):
    """Build strict component/combined artifact contracts for one request."""
    shape = (int(delta_z), int(NT))
    common = {
        'schema': _OPE_CACHE_SCHEMA,
        'algorithm_version': _OPE_ALGORITHM_VERSION,
        'conf_id': int(conf_id),
        'delta_z': int(delta_z),
        'z_dir': int(z_dir),
        'lattice': {'nt': int(NT), 'nx': int(NX)},
        'precision': precision,
        'compute_dtype': precision,
        'output_dtype': np.dtype(precision).name,
        'shape': list(shape),
        'gauge_source': _gauge_source_identity(gauge_file),
        'channel_specs': channel_metadata,
        'combined_spec': combined_spec,
    }
    specs = {}
    component_contracts = []
    for component, channel_spec in zip(paths, channel_metadata):
        mu, nu = component
        contract = dict(common)
        contract.update({
            'artifact': 'ope_component',
            'component': [int(mu), int(nu)],
            'channel_spec': channel_spec,
        })
        key = f'component_{mu}_{nu}'
        specs[key] = {
            'path': _array_stem(paths[component]) + '.h5',
            'shape': shape,
            'dtype': np.dtype(precision),
            'contract': contract,
        }
        component_contracts.append({
            'component': [int(mu), int(nu)],
            'contract_sha256': hashlib.sha256(
                _strict_contract_payload(contract).encode('utf-8')).hexdigest(),
        })
    combined_contract = dict(common)
    combined_contract.update({
        'artifact': 'ope_combined',
        'component_contracts': component_contracts,
    })
    specs['combined'] = {
        'path': _array_stem(combined_path) + '.h5',
        'shape': shape,
        'dtype': np.dtype(precision),
        'contract': combined_contract,
    }
    return specs


def _load_strict_ope_cache(specs, components, channel_metadata,
                           combined_spec, logger):
    """Load a complete OPE set and verify metadata plus linear consistency."""
    gauge_source = specs['combined']['contract']['gauge_source']
    if (not isinstance(gauge_source, dict)
            or not gauge_source.get('stat_available', False)):
        _info(logger, "  ignored strict OPE cache: gauge source identity "
                      "cannot be stat-validated")
        return None
    cached = _load_strict_cache_mapping(
        specs, logger, payload_sha_attr=_OPE_PAYLOAD_SHA_ATTR)
    if cached is None:
        return None
    if _gauge_source_identity(gauge_source['path']) != gauge_source:
        _info(logger, "  ignored strict OPE cache: gauge source identity "
              "changed while loading cache")
        return None
    metadata_status, cached_metadata = _read_ope_metadata(
        specs['combined']['path'])
    if (metadata_status != 'validated'
            or cached_metadata != (channel_metadata, combined_spec)):
        _info(logger, "  ignored incompatible strict OPE cache: "
                      "combined channel metadata mismatch")
        return None
    ops = {
        component: cached[f'component_{component[0]}_{component[1]}']
        for component in components
    }
    recombined = _combine_legacy_ope(ops)
    if not np.array_equal(recombined, cached['combined']):
        _info(logger, "  ignored incompatible strict OPE cache: "
              "combined data differs from cached components")
        return None
    if _gauge_source_identity(gauge_source['path']) != gauge_source:
        _info(logger, "  ignored strict OPE cache: gauge source identity "
              "changed before cache return")
        return None
    return {
        'components': ops,
        'combined': recombined,
        'metadata_status': 'validated',
        'channel_specs': channel_metadata,
        'combined_spec': combined_spec,
    }


def _publish_ope_artifacts(artifacts, source_identity, gauge_file, logger):
    """Stage a complete OPE set, recheck the source, then publish each file."""
    _assert_gauge_source_unchanged(
        source_identity, gauge_file, "OPE computation before cache publish")
    staged = []
    try:
        for final_path, array, attrs in artifacts:
            final_path = os.fspath(final_path)
            directory = os.path.dirname(final_path) or '.'
            os.makedirs(directory, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                    dir=directory, prefix=f'.{os.path.basename(final_path)}.',
                    suffix='.stage.h5', delete=False) as temporary:
                staged_path = temporary.name
            staged.append((staged_path, final_path))
            save_array(staged_path, array, logger, attrs=attrs)

        _assert_gauge_source_unchanged(
            source_identity, gauge_file, "OPE cache staging before publish")
        for staged_path, final_path in staged:
            os.replace(staged_path, final_path)
        _assert_gauge_source_unchanged(
            source_identity, gauge_file, "OPE cache publication completion")
    finally:
        for staged_path, _final_path in staged:
            try:
                os.unlink(staged_path)
            except BaseException:
                # staging 清理不得覆盖 source-race 或写入主异常。
                pass


def compute_ope_for_config(conf_id, run_dir, logger, precision='complex64',
                           delta_z=DELTA_Z, z_dir=Z_DIR,
                           components=OPE_COMPONENTS, recompute=False):
    precision, delta_z, components = _validate_legacy_ope_request(
        precision, delta_z, components)
    if not HAS_CUPY and get_backend_name() != 'torch':
        raise RuntimeError("OPE requires a GPU backend (torch/cupy)")

    if get_backend_name() == 'torch':
        set_precision(precision)
    dtype = np.dtype(precision).type
    cdir = conf_data_dir(run_dir, conf_id)
    channel_specs = tuple(
        _legacy_ope_channel_spec(component, z_dir)
        for component in components)
    channel_metadata, combined_spec = _legacy_ope_metadata(
        channel_specs, z_dir)
    paths = {c: os.path.join(cdir, f'ops_mu{c[0]}_nu{c[1]}_dz{delta_z}_conf{conf_id}')
             for c in components}
    combined_path = os.path.join(
        cdir, f'ope_combined_conf{conf_id}')
    gauge_file = _canonical_gauge_input(get_gauge_path(conf_id))
    strict_cache = _ope_cache_specs(
        conf_id, paths, combined_path, precision, delta_z, z_dir,
        channel_metadata, combined_spec, gauge_file)
    if not recompute:
        cached = _load_strict_ope_cache(
            strict_cache, components, channel_metadata, combined_spec, logger)
        if cached is not None:
            _info(logger, f"  conf={conf_id}: loaded complete strict OPE cache")
            return cached

    _info(logger, f"  conf={conf_id}: OPE from {gauge_file} "
                  f"(dz={delta_z}, z_dir={z_dir}, {precision})")

    ops = {}
    pending_artifacts = []
    gauge_cpu = None
    gauge_gpu = None
    field_strength_cache = None
    source_identity = _gauge_source_identity(gauge_file)
    try:
        gauge_cpu, _t = _timer(f"  read gauge conf={conf_id}", logger,
                               read_gauge_lime, gauge_file, NT, NX)
        _assert_gauge_source_unchanged(
            source_identity, gauge_file, "fresh gauge reader")
        _validate_gauge(gauge_cpu, logger)
        _assert_gauge_source_unchanged(
            source_identity, gauge_file, "fresh gauge validation")
        backend = get_backend()
        gauge_gpu = backend.asarray(gauge_cpu.astype(dtype))
        gauge_cpu = None
        field_strength_cache = FieldStrengthCache(
            gauge_gpu, gauge_immutable=True, max_entries=2)
        for spec in channel_specs:
            mu, nu = spec.mu, spec.nu
            o, _t2 = _timer(f"  OPE mu={mu},nu={nu} conf={conf_id}", logger,
                            gluon_ope_channel, gauge_gpu, spec,
                            delta_z, NT, NX, dtype,
                            field_strength_cache=field_strength_cache,
                            _operator=gluon_ope_operator_z0)
            cache_spec = strict_cache[f'component_{mu}_{nu}']
            o = _strict_array(o, f'OPE component ({mu},{nu})', cache_spec)
            ops[(mu, nu)] = o
            component_attrs = _strict_contract_attrs(cache_spec['contract'])
            component_attrs.update(_ope_payload_attrs(o))
            pending_artifacts.append(
                (cache_spec['path'], o, component_attrs))
            _info(logger, f"    prepared ops_mu{mu}_nu{nu}: shape={o.shape}, "
                          f"|O|∈[{np.abs(o).min():.2e},{np.abs(o).max():.2e}]")
        combined_cache = strict_cache['combined']
        combined = _strict_array(
            _combine_legacy_ope(ops), 'combined OPE', combined_cache)
        combined_attrs = _strict_contract_attrs(combined_cache['contract'])
        combined_attrs.update(
            _ope_metadata_attrs(channel_metadata, combined_spec))
        combined_attrs.update(_ope_payload_attrs(combined))
        pending_artifacts.append(
            (combined_cache['path'], combined, combined_attrs))
        _publish_ope_artifacts(
            pending_artifacts, source_identity, gauge_file, logger)
        for spec in channel_specs:
            mu, nu = spec.mu, spec.nu
            _info(logger, f"    saved ops_mu{mu}_nu{nu}")
    finally:
        try:
            if field_strength_cache is not None:
                field_strength_cache.clear()
        except BaseException:
            # 清理必须是 best-effort，不能覆盖 OPE/save 的原始异常。
            pass
        field_strength_cache = None
        gauge_gpu = None
        gauge_cpu = None
        try:
            free_gpu_memory()
        except BaseException:
            pass
    log_gpu_memory(logger, " after OPE")
    return {
        'components': ops,
        'combined': combined,
        'metadata_status': 'validated',
        'channel_specs': channel_metadata,
        'combined_spec': combined_spec,
    }


def step_ope(config, run_dir, logger, progress=None):
    set_backend(config.get('backend', 'cupy'), device=config.get('device'))
    for cid in config['conf_ids']:
        started = time.perf_counter()
        _info(logger, f"\n─── OPE: conf {cid} ───")
        compute_ope_for_config(cid, run_dir, logger, config['precision'])
        _record_stage_completion(progress, 'ope', cid, started)


# ═══════════════════════════════════════════════════════════════════
# 分析层（照抄 run_pipeline.py step_analysis + analyze.py 保存逻辑）
# ═══════════════════════════════════════════════════════════════════

def _load_vertices_one(run_dir, cid):
    cdir = conf_data_dir(run_dir, cid)
    return {
        'VdV': _load_any(os.path.join(cdir, f'VdV_mom_{cid}')),
        'VVV': _load_any(os.path.join(cdir, f'VVV_mom_{cid}')),
    }


def load_2pt(run_dir, logger=None):
    corr = {}
    data_dir = os.path.join(run_dir, 'data')
    if not os.path.isdir(data_dir):
        return corr
    for name in os.listdir(data_dir):
        if not name.startswith('conf'):
            continue
        cid = name[4:]
        cdir = os.path.join(data_dir, name)
        entry = {}
        for f in os.listdir(cdir):
            if f.startswith('corr_') and (f.endswith('.h5') or f.endswith('.npy')):
                base = f[:-3] if f.endswith('.h5') else f[:-4]
                key = base[5:].replace(f'_{cid}', '')
                entry[f'corr_{key}'] = _load_any(os.path.join(cdir, base))
        if entry:
            corr[int(cid)] = entry
    _info(logger, f"Loaded 2pt correlators for {len(corr)} configs")
    return corr


def load_3pt(run_dir, logger=None):
    corr = {}
    data_dir = os.path.join(run_dir, 'data')
    if not os.path.isdir(data_dir):
        return corr
    for name in os.listdir(data_dir):
        if not name.startswith('conf'):
            continue
        cid = name[4:]
        cdir = os.path.join(data_dir, name)
        entry = {}
        for f in os.listdir(cdir):
            if '_3pt_' in f and (f.endswith('.h5') or f.endswith('.npy')) \
                    and 'pjnnjnp' not in f:
                base = f[:-3] if f.endswith('.h5') else f[:-4]
                key = base.replace(f'_{cid}', '')
                entry[key] = _load_any(os.path.join(cdir, base))
        if entry:
            corr[int(cid)] = entry
    if corr:
        _info(logger, f"Loaded 3pt correlators for {len(corr)} configs")
    return corr


def load_ope(run_dir, logger=None):
    ope = {}
    data_dir = os.path.join(run_dir, 'data')
    if not os.path.isdir(data_dir):
        return ope
    for name in os.listdir(data_dir):
        if not name.startswith('conf'):
            continue
        cid = name[4:]
        cdir = os.path.join(data_dir, name)
        comb = os.path.join(cdir, f'ope_combined_conf{cid}')
        if os.path.exists(comb + '.h5') or os.path.exists(comb + '.npy'):
            entry = {
                'combined': _load_any(comb),
            }
            metadata_status, metadata = _read_ope_metadata(comb)
            metadata_valid = metadata_status == 'validated'
            source_status = _read_ope_source_identity_status(comb, int(cid))
            entry['source_identity_status'] = source_status
            if (metadata_status == 'validated'
                    and source_status in ('stale', 'unavailable')):
                metadata_status = 'stale'
                _warn(
                    logger,
                    f"conf={cid}: canonical OPE gauge source identity is "
                    f"stale ({source_status}); loading the historical "
                    "combined artifact without treating it as a cache hit")
            entry['metadata_status'] = metadata_status
            if metadata_valid:
                entry['channel_specs'] = metadata[0]
                entry['combined_spec'] = metadata[1]
            ope[int(cid)] = entry
    if ope:
        _info(logger, f"Loaded combined OPE for {len(ope)} configs")
    return ope


def step_analysis(config, run_dir, logger):
    an_dir = os.path.join(run_dir, 'data', 'analysis')
    os.makedirs(an_dir, exist_ok=True)

    from ..analysis import (
        run_meff_jackknife as _run_meff_jackknife,
        run_3pt_ratio as _run_3pt_ratio,
        run_disconnected_ratio as _run_disconnected_ratio,
    )

    corr2 = load_2pt(run_dir, logger)
    meff_res = _run_meff_jackknife(corr2, config['conf_ids'], NT=NT,
                                   ALttc=ALttc, logger=logger)
    for particle, mom, key in [
        ('proton', 'P0', 'corr_pp_P0'), ('proton', 'P2', 'corr_pp_P2'),
        ('pion', 'P0', 'corr_pion_P0'), ('pion', 'P2', 'corr_pion_P2'),
    ]:
        res = meff_res[f'{particle}_{mom}']
        for q, base in [('meff_mean', 'meff'), ('meff_err', 'meff'),
                        ('corr_mean', 'corr'), ('corr_err', 'corr')]:
            tag = 'mean' if q.endswith('mean') else 'err'
            save_array(os.path.join(an_dir, f'{base}_{particle}_{mom}_{tag}.npy'),
                       res[q], logger)

    ratio_conn = {}
    corr3 = load_3pt(run_dir, logger)
    if corr3:
        ratio_conn = _run_3pt_ratio(corr2, corr3, config['conf_ids'],
                                    logger=logger)
        for had, mom in [('proton', 'P0'), ('proton', 'P2'),
                         ('pion', 'P0'), ('pion', 'P2')]:
            res = ratio_conn.get(f'{had}_{mom}')
            if res is None:
                continue
            save_array(os.path.join(an_dir, f'ratio_{had}_{mom}_mean.npy'),
                       res['R'], logger)
            save_array(os.path.join(an_dir, f'ratio_{had}_{mom}_err.npy'),
                       res['R_err'], logger)
    else:
        _warn(logger, "No 3pt data — skipping connected ratio")

    ratio_disc = {}
    ope = load_ope(run_dir, logger)
    if ope:
        if len(config['conf_ids']) >= 2:
            ratio_disc = _run_disconnected_ratio(corr2, ope, config['conf_ids'],
                                                  run_dir, logger=logger, NT=NT,
                                                  NX=NX)
        else:
            _warn(logger, "Nconf<2 —— 不相连 ratio 拟合统计上无意义，跳过"
                          "（全量 ≥2 组态时启用，与基线一致）")
    else:
        _warn(logger, "No OPE data — skipping disconnected ratio")

    return {'meff': meff_res, 'connected_ratio': ratio_conn,
            'disconnected_ratio': ratio_disc}


# ═══════════════════════════════════════════════════════════════════
# 绘图（照抄 analyze.py plot_meff_results / plot_correlators /
#       plot_connected_ratio）
# ═══════════════════════════════════════════════════════════════════

def _plot_style_common(fig):
    pass


def plot_meff_results(meff_results, run_dir, logger):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    pdir = os.path.join(run_dir, 'plots')
    os.makedirs(pdir, exist_ok=True)
    channels = [('proton', 'P0'), ('proton', 'P2'),
                ('pion', 'P0'), ('pion', 'P2')]
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    for ax, (particle, mom) in zip(axes.ravel(), channels):
        res = meff_results.get(f'{particle}_{mom}')
        if res is None:
            continue
        m, e = res['meff_mean'], res['meff_err']
        t = np.arange(len(m))
        ps, pe = res['plateau']
        ax.errorbar(t, m, yerr=e, fmt='o', ms=4, capsize=2)
        ax.axvspan(ps, pe - 1, alpha=0.15, color='C1')
        ax.axhline(res['E0'], color='C3', ls='--', lw=1)
        ax.axhline(res.get('E_exp', 0), color='C4', ls=':', lw=1)
        ax.set_title(f'{particle} P={mom}  E0={res["E0"]:.3f}±{res["E0_err"]:.3f} '
                     f'(exp {res.get("E_exp", 0):.2f})')
        ax.set_xlabel('t'); ax.set_ylabel(r'$m_{\rm eff}$ [GeV]')
        ax.grid(alpha=0.3)
    fig.suptitle('Effective masses (Jackknife, 10 configs)')
    fig.tight_layout()
    out = os.path.join(pdir, 'meff_all_channels.png')
    fig.savefig(out, dpi=150)
    plt.close(fig)
    _info(logger, f"  Saved {out}")


def plot_correlators(meff_results, run_dir, logger):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    pdir = os.path.join(run_dir, 'plots')
    os.makedirs(pdir, exist_ok=True)
    channels = [('proton', 'P0'), ('proton', 'P2'),
                ('pion', 'P0'), ('pion', 'P2')]
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    for ax, (particle, mom) in zip(axes.ravel(), channels):
        res = meff_results.get(f'{particle}_{mom}')
        if res is None:
            continue
        c, ce = res['corr_mean'], res['corr_err']
        t = np.arange(len(c))
        ax.errorbar(t, np.abs(c), yerr=ce, fmt='.', ms=4, capsize=0)
        ax.set_yscale('log')
        ax.set_title(f'{particle} P={mom}  C(0)={c[0]:.4e}')
        ax.set_xlabel('t'); ax.set_ylabel('|C(t)|')
        ax.grid(alpha=0.3, which='both')
    fig.suptitle('2pt correlators (Jackknife mean)')
    fig.tight_layout()
    out = os.path.join(pdir, 'correlators_all_channels.png')
    fig.savefig(out, dpi=150)
    plt.close(fig)
    _info(logger, f"  Saved {out}")


def plot_connected_ratio(ratio_results, run_dir, logger):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    pdir = os.path.join(run_dir, 'plots')
    os.makedirs(pdir, exist_ok=True)
    pairs = [('proton', 'P0'), ('proton', 'P2'), ('pion', 'P0'), ('pion', 'P2')]
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    for ax, (had, mom) in zip(axes.ravel(), pairs):
        res = ratio_results.get(f'{had}_{mom}')
        if res is None:
            continue
        r, e = res['R'], res['R_err']
        tau = np.arange(len(r))
        ax.errorbar(tau, r, yerr=e, fmt='o', ms=4, capsize=2)
        ax.axhline(0, color='gray', lw=0.8)
        ax.axhline(1, color='k', ls='--', lw=0.8)
        ax.set_title(f'{had} P={mom}  R(τ)  (t_sep={res["t_sep"]})')
        ax.set_xlabel('τ'); ax.set_ylabel('R(τ)')
        ax.grid(alpha=0.3)
    fig.suptitle('Connected 3pt/2pt ratios (PJN, γ₃)')
    fig.tight_layout()
    out = os.path.join(pdir, 'ratio_3pt_all_channels.png')
    fig.savefig(out, dpi=150)
    plt.close(fig)
    _info(logger, f"  Saved {out}")


def step_plots(config, run_dir, logger, meff_res=None, ratio_conn=None):
    if meff_res is None:
        an_dir = os.path.join(run_dir, 'data', 'analysis')
        meff_res = {}
        for particle, mom in [('proton', 'P0'), ('proton', 'P2'),
                              ('pion', 'P0'), ('pion', 'P2')]:
            fm = os.path.join(an_dir, f'meff_{particle}_{mom}_mean')
            fe = os.path.join(an_dir, f'meff_{particle}_{mom}_err')
            if _array_exists(fm) and _array_exists(fe):
                m = _load_any(fm); e = _load_any(fe)
                ps, pe = (4, min(NT - 2, 14)) if particle == 'proton' \
                    else (5, min(NT - 2, 18))
                mask = np.isfinite(m[ps:pe]) & (e[ps:pe] > 0) & (m[ps:pe] > 0.01)
                w = 1.0 / (e[ps:pe][mask] ** 2 + 1e-10)
                meff_res[f'{particle}_{mom}'] = {
                    'meff_mean': m, 'meff_err': e, 'plateau': (ps, pe),
                    'E0': float(np.sum(m[ps:pe][mask] * w) / np.sum(w)),
                    'E0_err': float(1 / np.sqrt(np.sum(w))),
                    'E_exp': 1.0 if particle == 'proton' else 0.30,
                    'corr_mean': _load_any(os.path.join(
                        an_dir, f'corr_{particle}_{mom}_mean')),
                    'corr_err': _load_any(os.path.join(
                        an_dir, f'corr_{particle}_{mom}_err')),
                }
    plot_meff_results(meff_res, run_dir, logger)
    plot_correlators(meff_res, run_dir, logger)
    if ratio_conn:
        plot_connected_ratio(ratio_conn, run_dir, logger)
    return meff_res


# ═══════════════════════════════════════════════════════════════════
# Step 8 — LaTeX 报告（照抄 report.py build_tex + step_report）
# ═══════════════════════════════════════════════════════════════════

_CHANNELS = [('proton', 'P0'), ('proton', 'P2'), ('pion', 'P0'), ('pion', 'P2')]


def _fmt(v, e):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return '—'
    if e is None or (isinstance(e, float) and np.isnan(e)):
        return f'{v:.3f}'
    return f'{v:.3f} ± {e:.3f}'


_LATEX_DIAGNOSTICS = (
    ('Overfull', re.compile(r'Overfull')),
    ('Float too large', re.compile(r'Float too large')),
    ('Missing character', re.compile(r'Missing character')),
)
_LATEX_OUTPUT_TAIL = 4000


def _latex_text(value):
    """将 subprocess 输出安全转换为可扫描文本。"""
    if value is None:
        return ''
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    return str(value)


def _latex_tail(value):
    text = _latex_text(value)
    return text[-_LATEX_OUTPUT_TAIL:] if text else '<empty>'


def _report_log_contents(path):
    """读取本遍生成的 log；首次编译尚未创建 log 属正常情况。"""
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as log:
            return log.read()
    except FileNotFoundError:
        return ''


def _report_file_signature(path):
    """返回文件身份/时间快照，用于拒绝沿用旧 PDF。"""
    try:
        stat = os.stat(path)
    except FileNotFoundError:
        return None
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


def _report_plateau_cell(meff):
    """返回平台表格单元格及点数，缺平台时不构造数值区间。"""
    plateau = meff.get('plateau')
    try:
        if plateau is None or len(plateau) != 2:
            raise ValueError
        ps, pe = plateau
        if not bool(np.isfinite(ps) and np.isfinite(pe) and pe > ps):
            raise ValueError
    except (TypeError, ValueError):
        return '无平台数据', '—'
    return f'$[{ps},{pe}]$', meff.get('npts', '—')


def build_tex(summary, run_dir, meff_vals, connected_ratio, disconn,
              conf_corrs):
    conf_ids = summary.get('conf_ids', CONF_IDS)
    precision = summary.get('precision', 'complex64')
    nev1 = summary.get('nev1', 100)

    meff_rows = []
    for had, mom in _CHANNELS:
        m = meff_vals.get(f'{had}_{mom}', {})
        e0 = m.get('E0'); e0e = m.get('E0_err'); ee = m.get('E_exp')
        plateau_cell, npts = _report_plateau_cell(m)
        meff_rows.append(
            f"    {had} & $P={{{mom}}}$ & {_fmt(e0, e0e)} & {_fmt(ee, None)}"
            f" & {plateau_cell} & {npts} \\\\")

    ratio_rows = []
    for had, mom in _CHANNELS:
        r = connected_ratio.get(f'{had}_{mom}', {})
        R = r.get('R'); Re = r.get('R_err')
        if R is not None:
            t_mid = min(len(R) - 1, 4)
            ratio_rows.append(
                f"    {had} & $P={{{mom}}}$ & ${R[t_mid]:+.4f} \\pm {Re[t_mid]:.4f}$ \\\\")

    disc_rows = []
    disc = disconn.get('proton') if isinstance(disconn, dict) else None
    if disc:
        c0, c1, dE = disc['c0'], disc['c1'], disc['dE']
        chi2 = disc['chi2']
        for z in [0, 4, 8, 12, 16, 20]:
            if z >= c0.shape[1]:
                continue

            def s(arr):
                return f"{arr[:, z].mean():.3f}"
            disc_rows.append(
                f"    {z} & ${s(c0)}$ & ${s(c1)}$ & ${s(dE)}$ & ${chi2[:, z].mean():.2g}$ \\\\")

    timing = summary.get('timing_s', {})
    timing_rows = "\n".join(
        f"    {step} & {t:.1f} s \\\\" for step, t in sorted(timing.items()))

    cfg_rows = []
    if conf_corrs:
        for had, mom in _CHANNELS:
            vals = []
            for cid in conf_ids:
                c = conf_corrs.get(cid, {}).get(
                    'corr_pp' if had == 'proton' else 'corr_pion')
                if c is not None and mom in c and len(c[mom]):
                    vals.append(c[mom][0])
            if vals:
                mean, std = np.mean(vals), np.std(vals)
                cfg_rows.append(
                    f"    {had} P{mom} & {mean:.4e} & {std/abs(mean)*100:.1f}\\% \\\\")

    tex = r"""% ===========================================================================
%  格点QCD GPU蒸馏计算管线 — 物理分析报告 (test0 / pyqcd)
%  Physical Analysis Report — test0 (pyqcd 调用)
% ===========================================================================
\documentclass[11pt,a4paper]{article}
\usepackage[UTF8]{ctex}
\setCJKmainfont{AR PL SungtiL GB}[BoldFont=AR PL UMing CN]
\setCJKsansfont{AR PL KaitiM GB}[BoldFont=AR PL UMing CN]
\setCJKmonofont{AR PL UMing CN}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{physics}
\usepackage{braket}
\usepackage{bm}
\usepackage[margin=2.5cm]{geometry}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage[colorlinks=true,linkcolor=blue,citecolor=blue,urlcolor=blue]{hyperref}
\usepackage{enumitem}
\usepackage{caption}
\usepackage{subcaption}
\usepackage{multirow}
\usepackage{array}

\newcommand{\gev}{\;\mathrm{GeV}}
\newcommand{\fm}{\;\mathrm{fm}}
\newcommand{\fmto}{\;\mathrm{fm}^{-1}}
\newcommand{\meff}{m_{\mathrm{eff}}}
\newcommand{\Nconf}{N_{\mathrm{conf}}}
\newcommand{\Nev}{N_{\mathrm{ev}}}
\newcommand{\Nt}{N_t}
\newcommand{\Nx}{N_x}
\newcommand{\tsep}{t_{\mathrm{sep}}}
\newcommand{\Ctwo}{C^{(2)}}
\newcommand{\Cthree}{C^{(3)}}
\newcommand{\Em}{E^{(0)}}
\newcommand{\pmom}{p_z}
\newcommand{\apm}{a^{-1}}
\newcommand{\jack}{\mathrm{JK}}
\newcommand{\gmu}{\gamma_\mu}

\title{\textbf{格点QCD GPU蒸馏计算管线物理分析报告}\\[0.3em]
       \large 顶点函数、Wick收缩、动态收缩与关联函数分析 (test0 — pyqcd)}
\author{张鑫\thanks{中国科学院近代物理研究所 (IMP, CAS)}}
\date{""" + datetime.now().strftime('%Y年%m月%d日') + r"""}

\begin{document}
\maketitle

\begin{abstract}
本报告基于格点QCD蒸馏(Distillation)框架，在GPU (CUDA) 上实现了完整的关联函数计算管线：
顶点函数($VdV$/$VVV$)、Wick收缩分析、动态收缩、以及两点($pp$/$pn$)、OPE、三点($PJN$)、
四点($PJNNJNp$)关联函数，并进行Jackknife/有效质量/三点比值($ratio_{3p}$)统计分析。
本运行由 `pyqcd.testing.regression.distillation` 调用 pyqcd 包完成。
计算使用CLQCD合作组的规范组态
($\beta=6.20$, $24^3\times72$, $a\approx0.1053\;\fm$, $\apm\approx1.874\;\gev$)，
共 """ + str(len(conf_ids)) + r""" 个组态（""" + ', '.join(map(str, conf_ids)) + r"""），
计算精度 """ + precision + r"""。
\end{abstract}

\tableofcontents
\newpage

\section{引言}
LaMET (Large Momentum Effective Theory) 计算大动量下的准分布 (quasi-distribution)
关联函数并做微扰匹配，得到光锥 parton 分布函数。胶子 PDF 涉及不相连(disconnected)图，
其中三点函数可分解为质子两点函数与胶子算符 (OPE) 两部分的乘积。本报告由 test0 套件
调用 pyqcd 包实现（逻辑照抄成功实例 docker-v20260805，自包含）。

\section{理论框架}
\subsection{格点系综参数}
\begin{table}[h]
\centering
\caption{格点系综参数 (表~\ref{tab:ensemble})}
\label{tab:ensemble}
\begin{tabular}{ll}
\toprule
参数 & 值 \\
\midrule
$\beta$ & 6.20 (Clover Wilson) \\
格点 & $24^3\times72$ \\
格距 $a$ & 0.1053 fm \\
逆格距 $\apm$ & $\approx 1.874$ GeV \\
本征矢数 $\Nev$ / $N_{\mathrm{ev,1}}$ & 100 / """ + str(nev1) + r""" \\
动量 & $P=(0,0,0)$, $P=(0,0,2)$ \\
组态数 $\Nconf$ & """ + str(len(conf_ids)) + r""" \\
精度 & """ + precision + r""" \\
\bottomrule
\end{tabular}
\end{table}

\subsection{蒸馏方法与顶点函数}
蒸馏 (distillation) 方法把夸克传播子投影到拉普拉斯算符的低模空间：
\[ \tau_{ij}(t_s,t_f) = v^\dagger_i(t_s)\, M^{-1}(t_s,t_f)\, v_j(t_f). \]
两点关联函数所需的顶点函数为
\begin{equation}
V^{VdV}_{mn}(\mathbf{p}) = \sum_{\mathbf{x}} e^{-i\mathbf{p}\cdot\mathbf{x}}\,
    v^\dagger_m(\mathbf{x})\, v_n(\mathbf{x}),
\label{eq:VdV}
\end{equation}
\begin{equation}
V^{VVV}_{m n l}(\mathbf{p}) = \sum_{\mathbf{x}} e^{-i\mathbf{p}\cdot\mathbf{x}}\,
    \varepsilon_{abc}\, v^a_m(\mathbf{x})\, v^b_n(\mathbf{x})\, v^c_l(\mathbf{x}),
\label{eq:VVV}
\end{equation}
其中 $VdV$ 用于介子，$VVV$ 用于重子（质子/中子）。

\subsection{两点关联函数与有效质量}
源平均后的两点函数为
\[ C(t) = \frac{1}{\Nt}\sum_{t_s} C(t_s,\, t_s + t). \]
有效质量的对数形式与双曲余弦形式为
\begin{equation}
\meff(t) = \ln\frac{C(t)}{C(t+1)}\cdot\frac{\hbar c}{a}, \qquad
\meff(t) = \operatorname{arccosh}\frac{C(t+2)+C(t)}{2C(t+1)}\cdot\frac{\hbar c}{a}.
\label{eq:meff}
\end{equation}

\subsection{三点/两点比值}
连通的三点函数 $C^{(3)}(\tau)$（质子-矢量流-核子）与两点函数 $C^{(2)}$ 的比值采用
lqcddb 的 $ratio_{3p}$ 公式，包含 $\sqrt{\cdots}$ 因子。不相连胶子比值则按
huangcl 的 code\_1.py 算法构造：
\begin{equation}
C^{(3)}(t, \tau, z) = C^{(2)}(t)\, O(z,\tau),
\qquad R(t,\tau,z) = \frac{C^{(3)} - C^{(2)}\braket{O}}{C^{(2)}},
\end{equation}
并对每个 $z$ 做关联拟合 $R(t,\tau) = c_0 + c_1 e^{-dE\,\tau} + c_1 e^{-dE\,(t-\tau)}$。

\section{计算方法 (GPU管线)}
管线步骤：
\begin{enumerate}
    \item 顶点函数：$VdV$/$VVV$（GPU，按时间片流式计算）
    \item Wick收缩分析 + 动态收缩（lqcddb 引擎，注册表 + einsum 计划缓存）
    \item 关联函数：2pt ($pp$/$pn$/pion)、OPE (胶子算符)、3pt ($PJN$)、4pt ($PJNNJNp$)
    \item 统计分析：Jackknife、有效质量、$ratio_{3p}$（code\_1.py 形式）
    \item 绘图与 LaTeX 报告
\end{enumerate}
全部中间结果与日志均保存在版本目录中。

\section{结果与分析}
\subsection{两点关联函数与有效质量}
表~\ref{tab:meff} 给出各道的有效质量（Jackknife，加权平台）。
\begin{table}[h]
\centering
\caption{有效质量 (加权平台) (表~\ref{tab:meff})}
\label{tab:meff}
\begin{tabular}{llccccl}
\toprule
粒子 & 动量 & $E_0$ [GeV] & 期望 [GeV] & 平台 & 点数 \\
\midrule
""" + '\n'.join(meff_rows) + r"""
\bottomrule
\end{tabular}
\end{table}

\subsection{三点/两点连通比值}
表~\ref{tab:ratio} 给出 $\gamma_3$（$z$方向）分量的比值 $R(\tau)$。
\begin{table}[h]
\centering
\caption{连通三点/两点比值 (表~\ref{tab:ratio})}
\label{tab:ratio}
\begin{tabular}{llc}
\toprule
粒子 & 动量 & $R(\tau{\approx}4)$ \\
\midrule
""" + '\n'.join(ratio_rows) + r"""
\bottomrule
\end{tabular}
\end{table}

\subsection{不相连胶子比值与拟合}
表~\ref{tab:disc} 给出质子 $P_z=2$ 道不相连比值按 code\_1.py 拟合的参数。
\begin{table}[h]
\centering
\caption{不相连比值拟合参数 $R=c_0+c_1e^{-dE\,\tau}+c_1e^{-dE\,(t-\tau)}$ (表~\ref{tab:disc})}
\label{tab:disc}
\begin{tabular}{lcccc}
\toprule
$z$ & $c_0$ & $c_1$ & $dE$ & $\chi^2/\mathrm{dof}$ \\
\midrule
""" + '\n'.join(disc_rows) + r"""
\bottomrule
\end{tabular}
\end{table}

\subsection{组态一致性}
表~\ref{tab:config} 给出各道 $C(0)$ 的组态间离散程度。
\begin{table}[h]
\centering
\caption{各道 $C(0)$ 组态一致性 (表~\ref{tab:config})}
\label{tab:config}
\begin{tabular}{lcc}
\toprule
道 & $\braket{C(0)}$ & 相对离散度 \\
\midrule
""" + '\n'.join(cfg_rows) + r"""
\bottomrule
\end{tabular}
\end{table}

\subsection{计算耗时}
\begin{table}[h]
\centering
\caption{分步耗时 (表~\ref{tab:timing})}
\label{tab:timing}
\begin{tabular}{lr}
\toprule
步骤 & 耗时 \\
\midrule
""" + timing_rows + r"""
\bottomrule
\end{tabular}
\end{table}

\section{讨论与展望}
当前运行使用单精度 (complex64)、$\Nev=100$、$\Nconf=""" + str(len(conf_ids)) + r"""$。
$pn$（质子-中子）两点函数因味守恒而恒为零（质子 $uud$ 与中子 $udd$ 味结构不同），
这与理论预期一致。动量 $P=(0,0,2)$ 对应物理动量
$p_z = \frac{2\pi\cdot 2}{24\,a}\approx 0.981\;\gev$。后续工作可增加本征矢数目、
组态数目、动量涂抹、多源与 GEVP 以改善激发态污染。

\section{结论}
\begin{enumerate}
    \item 完整实现了从顶点函数到四点关联函数的 GPU 蒸馏管线（pyqcd 调用）。
    \item 两点函数与有效质量分析通过 Jackknife 获得统计误差。
    \item 三点 ($PJN$) 与四点 ($PJNNJNp$) 关联函数及比值分析完成。
    \item OPE 胶子算符按 donghx 算法计算并与两点函数组合成不相连比值。
\end{enumerate}

\begin{thebibliography}{9}
\bibitem{zhang2019} J.-H. Zhang et al., PRL 122, 142001 (2019).
\bibitem{fan2021} Z. Fan et al., PRD 104, 074502 (2021).
\bibitem{ji2013} X. Ji, PRL 110, 262002 (2013).
\bibitem{peardon2009} M. Peardon et al., PRD 80, 054506 (2009).
\end{thebibliography}

\end{document}
"""
    return tex


def step_report(config, run_dir, logger, meff_res, timing, env=None):
    # 汇总 JSON（照抄 run_pipeline.py step_report）
    summary = {
        'version': 'test0',
        'conf_ids': config['conf_ids'],
        'precision': config['precision'],
        'nev': NEV, 'nev1': config.get('Nev1', NEV1),
        'lattice': [NT, NX, NX, NX], 'alttc': ALttc,
        'meff': {k: {kk: (float(vv) if isinstance(vv, (int, float, np.floating))
                          else (list(vv) if isinstance(vv, tuple) else None))
                     for kk, vv in v.items()
                     if kk in ('E0', 'E0_err', 'E_exp', 'dev', 'plateau', 'npts')}
                 for k, v in meff_res.items()},
        'timing_s': timing,
        'run_dir': run_dir,
    }
    if env:
        summary['env'] = env
    with open(os.path.join(run_dir, 'analysis_summary.json'), 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    _info(logger, f"Analysis summary -> {run_dir}/analysis_summary.json")

    an_dir = os.path.join(run_dir, 'data', 'analysis')
    meff_vals = {f'{had}_{mom}': {
        'E0': summary['meff'].get(f'{had}_{mom}', {}).get('E0'),
        'E0_err': summary['meff'].get(f'{had}_{mom}', {}).get('E0_err'),
        'E_exp': summary['meff'].get(f'{had}_{mom}', {}).get('E_exp'),
        'plateau': summary['meff'].get(f'{had}_{mom}', {}).get('plateau'),
        'npts': summary['meff'].get(f'{had}_{mom}', {}).get('npts'),
    } for had, mom in _CHANNELS}

    connected_ratio = {}
    for had, mom in _CHANNELS:
        fm = os.path.join(an_dir, f'ratio_{had}_{mom}_mean')
        fe = os.path.join(an_dir, f'ratio_{had}_{mom}_err')
        if _array_exists(fm) and _array_exists(fe):
            connected_ratio[f'{had}_{mom}'] = {'R': _load_any(fm),
                                               'R_err': _load_any(fe)}

    disconn = {}
    disc_dir = os.path.join(run_dir, 'analysis', 'disconnected')
    fp = os.path.join(disc_dir, '0_fit_data.npz')
    if os.path.exists(fp):
        d = np.load(fp)
        disconn['proton'] = {'c0': d['c0'], 'c1': d['c1'], 'dE': d['dE'],
                             'chi2': d['chi2']}

    conf_corrs = {}
    for cid in summary['conf_ids']:
        cdir = os.path.join(run_dir, 'data', f'conf{cid}')
        entry = {}
        for f in os.listdir(cdir) if os.path.isdir(cdir) else []:
            if f.startswith('corr_') and f.endswith(('.h5', '.npy')):
                base = _array_stem(f)
                key = base[5:]
                entry[key] = _load_any(os.path.join(cdir, base))
        if entry:
            conf_corrs[cid] = entry

    tex = build_tex(summary, run_dir, meff_vals, connected_ratio,
                    disconn, conf_corrs)
    tex_path = os.path.join(run_dir, 'physics_report.tex')
    with open(tex_path, 'w') as f:
        f.write(tex)
    _info(logger, f"Wrote {tex_path}")

    pdf = os.path.join(run_dir, 'physics_report.pdf')
    pdf_before = _report_file_signature(pdf)
    log_path = os.path.join(run_dir, 'physics_report.log')
    latex_outputs = []
    command = ['xelatex', '-interaction=nonstopmode',
               '-halt-on-error', 'physics_report.tex']
    for pass_number in (1, 2):
        try:
            completed = subprocess.run(
                command, cwd=run_dir, capture_output=True)
        except OSError as exc:
            raise RuntimeError(
                f"XeLaTeX pass {pass_number} could not start; "
                f"stdout tail: <empty>; stderr tail: <empty>; "
                f"log tail: {_latex_tail(_report_log_contents(log_path))}") \
                from exc

        stdout = _latex_text(getattr(completed, 'stdout', None))
        stderr = _latex_text(getattr(completed, 'stderr', None))
        log_contents = _report_log_contents(log_path)
        latex_outputs.append({
            'stdout': stdout,
            'stderr': stderr,
            'physics_report.log': log_contents,
        })
        returncode = getattr(completed, 'returncode', None)
        _info(logger, f"XeLaTeX pass {pass_number}: returncode={returncode}")
        if returncode != 0:
            raise RuntimeError(
                f"XeLaTeX pass {pass_number} failed "
                f"(returncode={returncode}); "
                f"stdout tail: {_latex_tail(stdout)}; "
                f"stderr tail: {_latex_tail(stderr)}; "
                f"log tail: {_latex_tail(log_contents)}")

    for pass_number, outputs in enumerate(latex_outputs, 1):
        for source, text in outputs.items():
            for diagnostic, pattern in _LATEX_DIAGNOSTICS:
                if pattern.search(text):
                    raise RuntimeError(
                        f"XeLaTeX pass {pass_number} reported {diagnostic} "
                        f"in {source}; output tail: {_latex_tail(text)}")

    if not os.path.isfile(pdf):
        raise RuntimeError(
            "XeLaTeX completed two passes but physics_report.pdf "
            "was not produced")
    if (pdf_before is not None
            and _report_file_signature(pdf) == pdf_before):
        raise RuntimeError(
            "XeLaTeX completed two passes but physics_report.pdf "
            "was not newly produced")
    _info(logger, f"PDF: {pdf}")
    return summary


# ═══════════════════════════════════════════════════════════════════
# 调度（照抄 run_pipeline.py main 循环）
# ═══════════════════════════════════════════════════════════════════

_PROGRESS_STEPS = frozenset(('vertex', '2pt', 'ope', '3pt', '4pt'))


def _run_preflight_hook(hook, config, steps):
    """运行显式输入守卫，并返回可 JSON 序列化的状态记录。

    ``run_pipeline`` 的默认路径不推断任何外部数据布局；只有调用方传入
    hook 时才执行输入检查。hook 的稳定调用契约是
    ``hook(config, steps) -> (n_ok, bad_list)``。
    """
    if hook is None:
        return {
            'requested': False,
            'status': 'not_requested',
            'n_ok': None,
            'bad_list': [],
        }
    if not callable(hook):
        raise TypeError('preflight/input_guard 必须是可调用对象或 None')

    result = hook(config, steps)
    if not isinstance(result, (tuple, list)) or len(result) != 2:
        raise TypeError(
            'preflight/input_guard 必须返回 (n_ok, bad_list)')
    n_ok, bad = result
    try:
        n_ok = int(n_ok)
    except (TypeError, ValueError) as exc:
        raise TypeError('preflight n_ok 必须是整数') from exc
    if n_ok < 0:
        raise ValueError('preflight n_ok 不能为负数')

    if bad is None:
        bad_list = []
    elif isinstance(bad, (str, bytes)):
        bad_list = [bad.decode('utf-8', errors='replace')
                    if isinstance(bad, bytes) else bad]
    else:
        try:
            bad_list = list(bad)
        except TypeError as exc:
            raise TypeError('preflight bad_list 必须是可迭代对象') from exc
        bad_list = [str(item) for item in bad_list]

    if bad_list:
        preview = '; '.join(bad_list[:8])
        if len(bad_list) > 8:
            preview += f'; ...（另有 {len(bad_list) - 8} 项）'
        raise RuntimeError(
            f'pipeline preflight failed: n_ok={n_ok}; '
            f'bad_list[{len(bad_list)}]={preview}')

    return {
        'requested': True,
        'status': 'passed',
        'n_ok': n_ok,
        'bad_list': [],
    }


def _dump_pipeline_env(config, run_dir, conf_ids):
    """调用公共环境快照器并补充本次运行的非机密身份字段。"""
    path = os.path.join(run_dir, 'env.json')
    info = dump_env(path)
    if info is None:
        info = {}
    if not isinstance(info, dict):
        raise TypeError('dump_env 必须返回 dict 或 None')
    info = dict(info)
    identity = {
        'conf_ids': list(conf_ids),
        'precision': config['precision'],
        'backend': config.get('backend'),
        'device': config.get('device'),
        'NT': int(NT),
        'NX': int(NX),
        # 保留旧快照使用的小写字段，便于旧报告读取。
        'nt': int(NT),
        'nx': int(NX),
        'gauge_dir': os.path.dirname(get_gauge_path(conf_ids[0])),
    }
    info.update(identity)
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(info, handle, indent=2, ensure_ascii=False, default=str)
    return info


def _new_stage_progress(step, config, logger):
    """为一个计算阶段建立 logger 适配后的逐组态 ETA 记录器。"""
    return ProgressLog(
        len(config['conf_ids']), label=f'stage={step}', every=1,
        logger=lambda message: _info(logger, message))


def _record_stage_completion(progress, step, conf_id, started):
    """在组态成功完成后写入阶段、组态、耗时和 ETA。"""
    if progress is None:
        return
    elapsed = time.perf_counter() - started
    progress.step(extra=f'step={step} conf={conf_id} '
                  f'elapsed={elapsed:.3f}s')

def run_pipeline(steps=('env', 'vertex', '2pt', 'ope', '3pt', '4pt',
                        'analysis', 'plots', 'report'),
                 conf_ids=None, run_dir=None, logger=print,
                 precision=PRECISION, nev1=None, channels=('pp', 'pn', 'pion'),
                 fourpt_nev1=None, fourpt_tsep=None, fourpt_mom=None,
                 fourpt_src_step=None, t_sep=None, skip_missing=False,
                 backend='cupy', device=None, recompute_2pt=False,
                 preflight=None, input_guard=None):
    """9 步管线调度（pyqcd 自包含实现，与 docker-v20260805 输出一致）。

    backend: 'cupy'（默认，旧行为）或 'torch'（PyTorch，device='cuda' 走 GPU）。
    preflight/input_guard: 可选输入守卫，调用为
        ``hook(config, steps) -> (n_ok, bad_list)``；未传入时不访问外部数据。
    返回 dict: {'run_dir', 'timing', 'summary', 'meff', 'ratio_conn', 'env'}
    """
    steps = tuple(steps)
    if preflight is not None and input_guard is not None:
        raise ValueError('preflight 与 input_guard 只能指定一个')
    guard = preflight if preflight is not None else input_guard
    if conf_ids is None:
        conf_ids = list(CONF_IDS)
    else:
        conf_ids = list(conf_ids)
        if not conf_ids:
            raise ValueError('conf_ids must not be empty')
    config = {
        'precision': precision,
        'Nev1': min(nev1, NEV) if nev1 else NEV1,
        'channels': tuple(channels),
        'conf_ids': conf_ids,
        'backend': backend,
        'device': device,
        'recompute_2pt': recompute_2pt,
    }
    if fourpt_nev1:
        config['fourpt_nev1'] = fourpt_nev1
    if fourpt_tsep:
        config['fourpt_tsep'] = fourpt_tsep
    if fourpt_mom:
        config['fourpt_mom'] = fourpt_mom
    if fourpt_src_step:
        config['fourpt_src_step'] = fourpt_src_step
    if t_sep:
        config['t_sep'] = t_sep

    # 这是唯一的入口前置检查点：在 reserve_unique_run_dir、mkdir、JSON
    # 快照等任何持久化副作用之前执行。默认 guard=None 不猜测数据布局。
    config['preflight'] = _run_preflight_hook(guard, config, steps)

    if run_dir is None:
        run_dir = reserve_unique_run_dir(_pipeline_config.OUTPUT_DIR)
    for d in ['data', 'analysis', 'plots']:
        os.makedirs(os.path.join(run_dir, d), exist_ok=True)
    _info(logger, f"Run directory: {run_dir}")
    _info(logger, f"Config: {config}")
    dump_config_snapshot(config, os.path.join(run_dir, 'run_config.json'), logger)

    timing = {}
    meff_res, ratio_conn, env = None, None, None
    summary = None
    total_start = time.perf_counter()
    try:
        for step in steps:
            t0 = time.perf_counter()
            if step == 'env':
                env = _dump_pipeline_env(config, run_dir, conf_ids)
                _info(logger, f"env: {env}")
            elif step == 'vertex':
                step_vertex(config, run_dir, logger,
                            progress=_new_stage_progress(step, config, logger))
            elif step == '2pt':
                step_2pt(config, run_dir, logger,
                         progress=_new_stage_progress(step, config, logger))
            elif step == 'ope':
                step_ope(config, run_dir, logger,
                         progress=_new_stage_progress(step, config, logger))
            elif step == '3pt':
                step_3pt(config, run_dir, logger,
                         progress=_new_stage_progress(step, config, logger))
            elif step == '4pt':
                step_4pt(config, run_dir, logger,
                         progress=_new_stage_progress(step, config, logger))
            elif step == 'analysis':
                analysis = step_analysis(config, run_dir, logger)
                meff_res = analysis['meff']
                ratio_conn = analysis['connected_ratio']
            elif step == 'plots':
                meff_res = step_plots(config, run_dir, logger,
                                      meff_res, ratio_conn)
            elif step == 'report':
                summary = step_report(config, run_dir, logger,
                                      meff_res, timing, env)
            elif step == 'tmd':
                from ..renorm._tmd import gradient_flow_renormalized_tmd
                from ..operator import read_gauge_lime as _rgl
                gauge = _rgl(get_gauge_path(conf_ids[0]), NT, NX)
                if gauge is not None:
                    tau = 3.0  # 数值接口使用 t/a^2；方案为物理 tau=3a^2
                    z_values = list(range(DELTA_Z))
                    b_values = list(range(0, 6))
                    staple_length = max(abs(z) for z in z_values)
                    O = gradient_flow_renormalized_tmd(
                        gauge, tau, z_values, b_values,
                        L=staple_length)
                    with open(os.path.join(run_dir, 'tmd_gluon_flow.json'),
                              'w') as f:
                        json.dump({
                            'tau': tau,
                            'tau_units': 'dimensionless',
                            'tau_convention': 't/a^2',
                            'physical_flow_time': 'tau*a^2',
                            'flow_eps': 0.01,
                            'staple_length': staple_length,
                            'O_shape': list(np.shape(O)),
                        }, f)
            elif skip_missing:
                _warn(logger, f"step '{step}' unknown — skipped")
            else:
                raise ValueError(f"unknown step '{step}'")
            timing[step] = round(time.perf_counter() - t0, 1)
            _info(logger, f"STEP {step} done in {timing[step]}s")
        total_t = time.perf_counter() - total_start
        _info(logger, f"Pipeline Complete! Total {total_t:.0f}s "
                      f"({total_t/60:.1f} min)")
    except Exception as e:
        import traceback
        _info(logger, f"PIPELINE FAILED: {e}")
        _info(logger, traceback.format_exc())
        raise
    finally:
        # 资源回收是 best-effort；清理异常不得覆盖原始计算异常或用户中断。
        try:
            free_gpu_memory()
        except BaseException:
            pass
        try:
            gc.collect()
        except BaseException:
            pass
    return {'run_dir': run_dir, 'timing': timing, 'summary': summary,
            'meff': meff_res, 'ratio_conn': ratio_conn, 'env': env}
