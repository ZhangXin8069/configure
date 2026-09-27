"""test9 混合重整化与物理缓存身份的独立契约。"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import h5py
import numpy as np

from pyqcd.pipeline._tmd9 import tmd_renormalize_hybrid
from pyqcd.renorm._hybrid import hR_z_Pz


ERRORS: dict[str, float] = {}

_CACHE_SCHEMA = "pyqcd.physical-cache.v1"
_CONTRACT_JSON_ATTR = "pyqcd_cache_contract_json"
_CONTRACT_SHA_ATTR = "pyqcd_cache_contract_sha256"
_VERTEX_ALGORITHM_VERSION = "pyqcd.pipeline.vertex-multi.v1"
_MULTI_2PT_ALGORITHM_VERSION = "pyqcd.pipeline.multi-2pt.v1"
_FLOW_ALGORITHM_VERSION = "pyqcd.renorm.wilson-flow.v1"
_OPE_ALGORITHM_VERSION = "pyqcd.pipeline.tmd-ope-time.v1"


def _canonical_json(contract):
    return json.dumps(
        contract, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False)


def _contract_sha256(contract):
    return hashlib.sha256(
        _canonical_json(contract).encode("utf-8")).hexdigest()


def _ope_contract(*, conf_id=7, tau=3.0, eps=0.05,
                  precision="complex128", z_dir=2, b_dir=0,
                  z_list=(1, 23), b_list=(4, 56), staple_length=30,
                  color_normalization="fundamental_trace", nt=1, nx=1):
    return {
        "algorithm_version": _OPE_ALGORITHM_VERSION,
        "artifact": "tmd_ope_time",
        "b_dir": int(b_dir),
        "b_list": [int(value) for value in b_list],
        "color_normalization": str(color_normalization),
        "conf_id": int(conf_id),
        "dtype": "float64",
        "eps": float(eps),
        "lattice": {"nt": int(nt), "nx": int(nx)},
        "precision": str(precision),
        "schema": _CACHE_SCHEMA,
        "shape": [len(z_list), len(b_list), int(nt)],
        "staple_length": int(staple_length),
        "tau": float(tau),
        "z_dir": int(z_dir),
        "z_list": [int(value) for value in z_list],
    }


def _flow_contract(*, conf_id=7, tau=3.0, eps=0.05,
                   precision="complex128", nt=1, nx=1):
    return {
        "algorithm_version": _FLOW_ALGORITHM_VERSION,
        "artifact": "flowed_gauge",
        "conf_id": int(conf_id),
        "dtype": str(precision),
        "eps": float(eps),
        "lattice": {"nt": int(nt), "nx": int(nx)},
        "precision": str(precision),
        "schema": _CACHE_SCHEMA,
        "shape": [int(nt), int(nx), int(nx), int(nx), 4, 3, 3],
        "tau": float(tau),
    }


def _lattice_contract(*, nt=1, nx=1, nev=2, nev1=1):
    return {
        "nev": int(nev),
        "nev1": int(nev1),
        "nt": int(nt),
        "nx": int(nx),
    }


def _vertex_contract(kind, *, conf_id=7, precision="complex64",
                     momenta=((0, 0, 0), (2, 0, 0)),
                     nt=1, nx=1, nev=2, nev1=1):
    momenta = [[int(component) for component in momentum]
               for momentum in momenta]
    if kind == "VdV":
        artifact = "tmd9_vertex_vdv"
        shape = [int(nt), len(momenta), int(nev), int(nev)]
    elif kind == "VVV":
        artifact = "tmd9_vertex_vvv"
        shape = [int(nt), len(momenta), int(nev1), int(nev1), int(nev1)]
    else:
        raise ValueError(kind)
    return {
        "algorithm_version": _VERTEX_ALGORITHM_VERSION,
        "artifact": artifact,
        "conf_id": int(conf_id),
        "dtype": str(precision),
        "lattice": _lattice_contract(
            nt=nt, nx=nx, nev=nev, nev1=nev1),
        "momenta": momenta,
        "precision": str(precision),
        "schema": _CACHE_SCHEMA,
        "shape": shape,
    }


def _multi_2pt_contract(channel, momentum, *, conf_id=7,
                        precision="complex64",
                        momenta=((0, 0, 0), (2, 0, 0)),
                        channels=("pp",), v_kind="VVV",
                        nt=1, nx=1, nev=2, nev1=1):
    vertex_kind = "VdV" if v_kind == "VDV" else "VVV"
    vertex_contract = _vertex_contract(
        vertex_kind, conf_id=conf_id, precision=precision,
        momenta=momenta, nt=nt, nx=nx, nev=nev, nev1=nev1)
    return {
        "algorithm_version": _MULTI_2PT_ALGORITHM_VERSION,
        "artifact": "tmd9_multi_2pt",
        "channel": str(channel),
        "channels": [str(value) for value in channels],
        "conf_id": int(conf_id),
        "dtype": "float64",
        "lattice": _lattice_contract(
            nt=nt, nx=nx, nev=nev, nev1=nev1),
        "momentum": [int(component) for component in momentum],
        "momenta": [
            [int(component) for component in value] for value in momenta
        ],
        "precision": str(precision),
        "schema": _CACHE_SCHEMA,
        "shape": [int(nt)],
        "v_kind": str(v_kind),
        "vertex_algorithm_version": _VERTEX_ALGORITHM_VERSION,
        "vertex_artifact": vertex_contract["artifact"],
        "vertex_contract_sha256": _contract_sha256(vertex_contract),
    }


def _strict_conf_dir(root, conf_id=7):
    return Path(root) / "data" / f"conf{int(conf_id)}"


def _vertex_cache_path(root, kind, contract):
    digest = _contract_sha256(contract)
    name = (
        f"{kind}_tmd9-strict-v1_nm{len(contract['momenta'])}_"
        f"p{contract['precision']}_sha256-{digest}_"
        f"conf{contract['conf_id']}.h5"
    )
    return _strict_conf_dir(root, contract["conf_id"]) / name


def _multi_2pt_cache_path(root, contract):
    digest = _contract_sha256(contract)
    momentum = contract["momentum"]
    if all(0 <= int(component) <= 9 for component in momentum):
        tag = "P" + "".join(str(int(component)) for component in momentum)
    else:
        tag = "P" + "_".join(str(int(component)) for component in momentum)
    name = (
        f"corr_{contract['channel']}_{tag}_tmd9-strict-v1_"
        f"nm{len(contract['momenta'])}_nc{len(contract['channels'])}_"
        f"p{contract['precision']}_v{contract['v_kind']}_"
        f"sha256-{digest}_conf{contract['conf_id']}.h5"
    )
    return _strict_conf_dir(root, contract["conf_id"]) / name


def _unit_gauge(dtype=np.complex128):
    return np.broadcast_to(
        np.eye(3, dtype=dtype),
        (1, 1, 1, 1, 4, 3, 3),
    ).copy()


def _cache_files(root, prefix):
    return sorted(Path(root).rglob(f"{prefix}*.h5"))


def _replace_contract_metadata(path, contract):
    payload = _canonical_json(contract)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    with h5py.File(path, "r+") as handle:
        handle.attrs[_CONTRACT_JSON_ATTR] = payload
        handle.attrs[_CONTRACT_SHA_ATTR] = digest


def _write_contract_h5(path, contract, data, *, digest=None):
    payload = _canonical_json(contract)
    if digest is None:
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    with h5py.File(path, "w") as handle:
        handle.create_dataset("data", data=data)
        handle.attrs[_CONTRACT_JSON_ATTR] = payload
        handle.attrs[_CONTRACT_SHA_ATTR] = digest


def _fixture():
    """返回能区分 Z_R 长距支路与裸比值的手算数据。"""
    z = np.array([0.10, 0.20, 0.30, 0.40])
    zr_fit = np.array([2.0, 4.0, 8.0, 16.0])
    c0_pz0 = np.array([
        [[10.0, 5.0], [20.0, 10.0], [40.0, 20.0], [100.0, 50.0]],
        [[8.0, 4.0], [16.0, 8.0], [32.0, 16.0], [80.0, 40.0]],
    ])
    c0_pz = np.array([
        [[5.0, 10.0], [10.0, 15.0], [12.0, 8.0], [16.0, 12.0]],
        [[4.0, 2.0], [12.0, 6.0], [16.0, 12.0], [20.0, 16.0]],
    ])
    return z, zr_fit, c0_pz, c0_pz0


def _reference_pointwise(c0_pz, c0_pz0, z, zr_fit, z_s):
    """逐 sample、逐 b 调用已验证的一维混合公式。"""
    expected = np.empty_like(c0_pz)
    for sample in range(c0_pz.shape[0]):
        for b_index in range(c0_pz.shape[2]):
            _, expected[sample, :, b_index] = hR_z_Pz(
                z, 4, c0_pz[sample, :, b_index],
                c0_pz0[sample, :, b_index], zs=z_s,
                zr_fit=zr_fit, conf="L24x72")
    return expected


class TmdHybridContract(unittest.TestCase):
    def test_momentum_tags_are_injective_and_duplicate_requests_rejected(self):
        """多位/负分量必须有边界，重复动量不得合并同一输出槽。"""
        from pyqcd.pipeline import _tmd9

        left = (1, 23, 0)
        right = (12, 3, 0)
        self.assertNotEqual(_tmd9.momentum_tag(left),
                            _tmd9.momentum_tag(right))
        self.assertEqual(_tmd9.momentum_tag((2, 0, 0)), "P200")
        with self.assertRaisesRegex(ValueError, r"重复|duplicate"):
            _tmd9._validate_momenta([left, left])

    def test_momentum_tags_round_trip_and_reject_noncanonical_forms(self):
        """公开标签解析必须与单射编码互逆，并拒绝前导零等别名。"""
        from pyqcd.pipeline import _tmd9

        for momentum in ((2, 0, 0), (10, -2, 0), (-1, 23, 4)):
            tag = _tmd9.momentum_tag(momentum)
            self.assertEqual(_tmd9.parse_momentum_tag(tag), momentum)
        for bad in ("P1230", "P02_0_0", "P2_0", "2_0_0", "P2__0"):
            with self.subTest(tag=bad), \
                    self.assertRaisesRegex(ValueError, r"动量标签|canonical"):
                _tmd9.parse_momentum_tag(bad)

    def test_multi_2pt_accumulator_keeps_multidigit_momenta_separate(self):
        """实际累加器不得在 contract 建立前合并不同多位动量。"""
        from pyqcd.pipeline import _steps
        from pyqcd.tools import set_backend

        set_backend("numpy")
        momenta = [(1, 23, 0), (12, 3, 0)]
        vertices = {
            "VdV": np.ones((1, 2, 2, 2), dtype=np.complex64),
            "VVV": np.array([1.0, 2.0], dtype=np.complex64).reshape(
                1, 2, 1, 1, 1),
        }

        def contraction(*args, **_kwargs):
            v_sink = np.asarray(args[8])
            return float(np.real(v_sink.reshape(-1)[0]))

        with tempfile.TemporaryDirectory() as root, \
                patch.object(
                    _steps, "readin_peram_time_slice",
                    return_value=np.ones(
                        (1, 1, 1, 2, 2), dtype=np.complex64)), \
                patch.object(_steps, "seq_peram", side_effect=lambda x: x), \
                patch.object(_steps, "_run_2pt", side_effect=contraction):
            actual = _steps.compute_2pt_for_config_multi(
                7, root, None, vertices, momenta,
                precision="complex64", channels=("pp",), v_kind="VVV")

        self.assertEqual(
            set(actual), {"corr_pp_P1_23_0", "corr_pp_P12_3_0"})
        np.testing.assert_array_equal(
            actual["corr_pp_P1_23_0"], np.array([1.0]))
        np.testing.assert_array_equal(
            actual["corr_pp_P12_3_0"], np.array([2.0]))

    def test_contract_hdf5_publish_is_atomic(self):
        """写入中断不得截断既有 canonical artifact 或遗留临时文件。"""
        from pyqcd.pipeline import _tmd9

        contract = {"artifact": "atomic-probe", "schema": _CACHE_SCHEMA}
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "artifact.h5"
            _tmd9._save_contract_h5(
                np.ones(2, dtype=np.float64), path, contract)
            before = path.read_bytes()
            writer_paths = []

            def interrupted(_array, writer_path):
                writer_path = Path(writer_path)
                writer_paths.append(writer_path)
                writer_path.write_bytes(b"partial-hdf5")
                raise RuntimeError("simulated interrupted contract write")

            with patch.object(_tmd9, "save_tensor_h5",
                              side_effect=interrupted):
                with self.assertRaisesRegex(RuntimeError, "interrupted"):
                    _tmd9._save_contract_h5(
                        np.zeros(2, dtype=np.float64), path, contract)

            self.assertTrue(writer_paths)
            self.assertNotEqual(writer_paths[0], path)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(root).iterdir()), [path])

    def test_multi_2pt_contract_binds_vertex_upstream_identity(self):
        """vertex 算法身份变化必须令所有 multi-2pt canonical 键失效。"""
        from pyqcd.pipeline import _tmd9

        args = (7, "/tmp/pyqcd-contract-probe", [(0, 0, 0)],
                ("pp",), "complex64", "VVV")
        before = _tmd9._multi_2pt_cache_specs(*args)
        with patch.object(_tmd9, "_VERTEX_ALGORITHM_VERSION",
                          "pyqcd.pipeline.vertex-multi.v-next"):
            after = _tmd9._multi_2pt_cache_specs(*args)

        before_spec = next(iter(before.values()))
        after_spec = next(iter(after.values()))
        self.assertIn("vertex_algorithm_version",
                      before_spec["contract"])
        self.assertIn("vertex_contract_sha256", before_spec["contract"])
        self.assertNotEqual(before_spec["path"], after_spec["path"])

    def test_ope_contract_binds_spatial_lattice_identity(self):
        """输出 shape 相同也不能跨空间体积复用 OPE canonical cache。"""
        from pyqcd.pipeline import _tmd9

        args = (7, 3.0, 0.05, "complex128", 2, 0,
                [0, 1], [0], 4, "fundamental_trace")
        before = _tmd9._tmd_ope_contract(*args)
        with patch.object(_tmd9, "NX", int(_tmd9.NX) + 1):
            after = _tmd9._tmd_ope_contract(*args)

        self.assertIn("lattice", before)
        self.assertIn("shape", before)
        self.assertIn("dtype", before)
        self.assertNotEqual(_tmd9._contract_sha256(before),
                            _tmd9._contract_sha256(after))

    def test_load_tmd_ope_miss_has_no_filesystem_side_effect(self):
        """纯读取 miss 只构造路径，不得创建 data/conf 目录。"""
        from pyqcd.pipeline import _tmd9

        with tempfile.TemporaryDirectory() as root:
            run_dir = Path(root) / "missing-run"
            actual = _tmd9.load_tmd_ope_all(
                run_dir, [7], [0, 1], [0], logger=None,
                precision="complex128")
            self.assertEqual(actual, {})
            self.assertFalse(run_dir.exists())

    def setUp(self):
        """让受控 unit gauge 与生产形状契约保持同一套相对边界。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.pipeline import _steps

        self._shape_patches = (
            patch.object(_tmd9, "NT", 1),
            patch.object(_tmd9, "NX", 1),
            patch.object(_tmd9, "NEV", 2, create=True),
            patch.object(_tmd9, "NEV1", 1, create=True),
            patch.object(_steps, "NT", 1),
            patch.object(_steps, "NX", 1),
            patch.object(_steps, "NEV", 2),
            patch.object(_steps, "NEV1", 1),
        )
        for shape_patch in self._shape_patches:
            shape_patch.start()

    def tearDown(self):
        for shape_patch in reversed(self._shape_patches):
            shape_patch.stop()

    def test_ope_cache_key_separates_full_physical_contract(self):
        """每个物理参数及 z/b 元素边界都必须产生独立 OPE 产物。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _unit_gauge()
        calls = []

        def encode_call(_gauge, z_list, b_list, **kwargs):
            calls.append((tuple(z_list), tuple(b_list), dict(kwargs)))
            return np.full(
                (len(z_list), len(b_list), 1), len(calls), dtype=float)

        baseline = {
            "tau": 3.0,
            "eps": 0.05,
            "precision": "complex128",
            "z_dir": 2,
            "b_dir": 0,
            "z_list": [1, 23],
            "b_list": [4, 56],
            "staple_length": 30,
            "color_normalization": "fundamental_trace",
        }
        variants = [
            ("baseline", {}),
            ("tau", {"tau": 4.0}),
            ("eps", {"eps": 0.025}),
            ("precision", {"precision": "complex64"}),
            ("z_dir", {"z_dir": 1}),
            ("b_dir", {"b_dir": 1}),
            # 旧拼接标签中 1|23 == 12|3，4|56 == 45|6。
            ("z_sequence_boundary", {"z_list": [12, 3]}),
            ("b_sequence_boundary", {"b_list": [45, 6]}),
            ("staple_length", {"staple_length": 31}),
            ("color_normalization", {"color_normalization": "adjoint"}),
        ]

        markers = []
        with tempfile.TemporaryDirectory() as run_dir, \
                patch.object(_tmd9, "flow_gauge_for_config",
                             return_value=gauge), \
                patch.object(_tmd9, "tmd_matrix_elements_time",
                             side_effect=encode_call):
            for name, override in variants:
                params = {**baseline, **override}
                result = _tmd9.compute_tmd_ope_time(
                    7, run_dir, None,
                    params.pop("z_list"), params.pop("b_list"), **params)
                markers.append((name, float(result["tmd"][0, 0, 0])))
            files = _cache_files(run_dir, "tmd_ope_")

        expected_markers = [
            (name, float(index))
            for index, (name, _override) in enumerate(variants, start=1)
        ]
        self.assertEqual(markers, expected_markers)
        self.assertEqual(len(calls), len(variants))
        self.assertEqual(len(files), len(variants))
        self.assertEqual(len({path.name for path in files}), len(variants))

    def test_ope_hdf5_records_canonical_contract_and_sha256(self):
        """HDF5 与文件名必须携带同一份完整规范 JSON 和 SHA-256。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        contract = _ope_contract()
        payload = _canonical_json(contract)
        digest = _contract_sha256(contract)
        gauge = _unit_gauge()
        tmd = np.arange(4, dtype=float).reshape(2, 2, 1)

        with tempfile.TemporaryDirectory() as run_dir, \
                patch.object(_tmd9, "flow_gauge_for_config",
                             return_value=gauge), \
                patch.object(_tmd9, "tmd_matrix_elements_time",
                             return_value=tmd):
            _tmd9.compute_tmd_ope_time(
                7, run_dir, None, [1, 23], [4, 56],
                tau=3.0, eps=0.05, precision="complex128",
                z_dir=2, b_dir=0, staple_length=30,
                color_normalization="fundamental_trace")
            files = _cache_files(run_dir, "tmd_ope_")
            self.assertEqual(len(files), 1)
            path = files[0]
            with h5py.File(path, "r") as handle:
                self.assertIn(_CONTRACT_JSON_ATTR, handle.attrs)
                self.assertIn(_CONTRACT_SHA_ATTR, handle.attrs)
                self.assertEqual(handle.attrs[_CONTRACT_JSON_ATTR], payload)
                self.assertEqual(handle.attrs[_CONTRACT_SHA_ATTR], digest)
                np.testing.assert_array_equal(handle["data"][...], tmd)
                self.assertIsInstance(handle["data"], h5py.Dataset)
                self.assertEqual(handle["data"].shape, tmd.shape)
                self.assertEqual(handle["data"].dtype, np.dtype(np.float64))

            name = path.name
            for fragment in (
                    "z2_1to23", "b2_4to56", "tau3", "eps0p05",
                    "pcomplex128", "zd2_bd0", "L30",
                    "Cfundamental_trace"):
                self.assertIn(fragment, name)
            self.assertRegex(name, rf"sha256-{digest}_conf7[.]h5$")

    def test_ope_metadata_mismatch_is_neither_loaded_nor_reused(self):
        """同名 HDF5 若契约不匹配，纯加载须跳过、计算须覆盖重算。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _unit_gauge()
        calls = []

        def encode_call(_gauge, z_list, b_list, **_kwargs):
            calls.append(1)
            return np.full(
                (len(z_list), len(b_list), 1), len(calls), dtype=float)

        with tempfile.TemporaryDirectory() as run_dir, \
                patch.object(_tmd9, "flow_gauge_for_config",
                             return_value=gauge), \
                patch.object(_tmd9, "tmd_matrix_elements_time",
                             side_effect=encode_call):
            first = _tmd9.compute_tmd_ope_time(
                7, run_dir, None, [1, 23], [4, 56],
                staple_length=30)
            path = _cache_files(run_dir, "tmd_ope_")[0]
            _replace_contract_metadata(path, _ope_contract(tau=4.0))

            loaded = _tmd9.load_tmd_ope_all(
                run_dir, [7], [1, 23], [4, 56], logger=None,
                staple_length=30)
            second = _tmd9.compute_tmd_ope_time(
                7, run_dir, None, [1, 23], [4, 56],
                staple_length=30)

        self.assertEqual(loaded, {})
        np.testing.assert_array_equal(
            first["tmd"], np.full((2, 2, 1), 1.0))
        np.testing.assert_array_equal(
            second["tmd"], np.full((2, 2, 1), 2.0))
        self.assertEqual(len(calls), 2)

    def test_ope_cache_rejects_matching_metadata_with_wrong_numeric_shape(self):
        """完整元数据不能掩盖 OPE 时间轴 shape 错误，且 legacy 只读不变。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.pipeline._steps import conf_data_dir
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _unit_gauge()
        contract = _ope_contract()
        calls = []

        with tempfile.TemporaryDirectory() as run_dir:
            legacy = Path(conf_data_dir(run_dir, 7)) / (
                "tmd_ope_z123_b456_L30_Cfundamental_trace_conf7.h5")
            _write_contract_h5(
                legacy, contract,
                np.zeros((2, 2, 2), dtype=np.float64))
            before = legacy.read_bytes()

            def encode_call(_gauge, z_list, b_list, **_kwargs):
                calls.append(1)
                return np.full((len(z_list), len(b_list), 1), 4.0)

            with patch.object(_tmd9, "flow_gauge_for_config",
                              return_value=gauge), \
                    patch.object(_tmd9, "tmd_matrix_elements_time",
                                 side_effect=encode_call):
                actual = _tmd9.compute_tmd_ope_time(
                    7, run_dir, None, [1, 23], [4, 56],
                    staple_length=30, precision="complex128")

            np.testing.assert_array_equal(
                actual["tmd"], np.full((2, 2, 1), 4.0))
            self.assertEqual(calls, [1])
            self.assertEqual(legacy.read_bytes(), before)
            self.assertEqual(len(_cache_files(run_dir, "tmd_ope_")), 2)

    def test_flow_cache_rejects_matching_metadata_with_wrong_numeric_shape(self):
        """完整元数据不能掩盖 flowed gauge lattice shape 错误。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _unit_gauge()
        contract = _flow_contract()
        calls = []

        with tempfile.TemporaryDirectory() as save_dir:
            legacy = Path(save_dir) / "flowed_gauge_7.h5"
            _write_contract_h5(
                legacy, contract,
                np.zeros((1, 1, 1, 2, 4, 3, 3), dtype=np.complex128))
            before = legacy.read_bytes()

            def encode_flow(gauge_in, tau, eps):
                calls.append((float(tau), float(eps)))
                return gauge_in + 2.0

            with patch.object(_tmd9, "read_gauge_lime", return_value=gauge), \
                    patch.object(_tmd9, "wilson_flow",
                                 side_effect=encode_flow), \
                    patch.object(
                        _tmd9, "flow_action_density",
                        return_value=np.ones(gauge.shape[:4])):
                actual = _tmd9.flow_gauge_for_config(
                    7, tau=3.0, eps=0.05, precision="complex128",
                    save_dir=save_dir, logger=None, save_gauge=True)

            self.assertEqual(calls, [(3.0, 0.05)])
            self.assertEqual(actual.shape, gauge.shape)
            self.assertEqual(
                float(np.real(actual[0, 0, 0, 0, 0, 0, 0])), 3.0)
            self.assertEqual(legacy.read_bytes(), before)
            self.assertEqual(len(_cache_files(save_dir, "flowed_gauge_")), 2)

    def test_ope_cache_rejects_wrong_sha_and_preserves_legacy(self):
        """JSON 正确但 SHA 错误的 legacy 缓存不得命中或改写。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.pipeline._steps import conf_data_dir
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _unit_gauge()
        contract = _ope_contract()
        payload = _canonical_json(contract)
        correct_digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        wrong_digest = "0" * len(correct_digest)
        self.assertNotEqual(correct_digest, wrong_digest)

        with tempfile.TemporaryDirectory() as run_dir:
            legacy = Path(conf_data_dir(run_dir, 7)) / (
                "tmd_ope_z123_b456_L30_Cfundamental_trace_conf7.h5")
            _write_contract_h5(
                legacy, contract, np.zeros((2, 2, 1), dtype=np.float64),
                digest=wrong_digest)
            before = legacy.read_bytes()
            with patch.object(_tmd9, "flow_gauge_for_config",
                              return_value=gauge), \
                    patch.object(
                        _tmd9, "tmd_matrix_elements_time",
                        return_value=np.full((2, 2, 1), 5.0)) as matrix:
                actual = _tmd9.compute_tmd_ope_time(
                    7, run_dir, None, [1, 23], [4, 56],
                    staple_length=30, precision="complex128")
                np.testing.assert_array_equal(
                    actual["tmd"], np.full((2, 2, 1), 5.0))
                matrix.assert_called_once()
                self.assertEqual(legacy.read_bytes(), before)

    def test_ope_cache_rejects_nonfinite_legacy_data_and_preserves_bytes(self):
        """匹配 metadata 但含 NaN/Inf 的 OPE legacy 只能拒绝。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.pipeline._steps import conf_data_dir
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _unit_gauge()
        contract = _ope_contract()

        for bad_value in (np.nan, np.inf):
            with self.subTest(value=bad_value), \
                    tempfile.TemporaryDirectory() as run_dir:
                legacy = Path(conf_data_dir(run_dir, 7)) / (
                    "tmd_ope_z123_b456_L30_Cfundamental_trace_conf7.h5")
                _write_contract_h5(
                    legacy, contract,
                    np.full((2, 2, 1), bad_value, dtype=np.float64))
                before = legacy.read_bytes()
                with patch.object(_tmd9, "flow_gauge_for_config",
                                  return_value=gauge), \
                        patch.object(
                            _tmd9, "tmd_matrix_elements_time",
                            return_value=np.full((2, 2, 1), 6.0)) as matrix:
                    actual = _tmd9.compute_tmd_ope_time(
                        7, run_dir, None, [1, 23], [4, 56],
                        staple_length=30, precision="complex128")

                np.testing.assert_array_equal(
                    actual["tmd"], np.full((2, 2, 1), 6.0))
                matrix.assert_called_once()
                self.assertEqual(legacy.read_bytes(), before)

    def test_flow_cache_rejects_nonfinite_legacy_data_and_preserves_bytes(self):
        """匹配 metadata 但含 NaN/Inf 的 flowed gauge 只能拒绝。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _unit_gauge()
        contract = _flow_contract()

        for bad_value in (np.nan + 0j, np.inf + 0j):
            with self.subTest(value=bad_value), \
                    tempfile.TemporaryDirectory() as save_dir:
                legacy = Path(save_dir) / "flowed_gauge_7.h5"
                _write_contract_h5(
                    legacy, contract,
                    np.full(gauge.shape, bad_value, dtype=np.complex128))
                before = legacy.read_bytes()
                with patch.object(_tmd9, "read_gauge_lime",
                                  return_value=gauge), \
                        patch.object(_tmd9, "wilson_flow",
                                     return_value=gauge + 7.0) as flow, \
                        patch.object(
                            _tmd9, "flow_action_density",
                            return_value=np.ones(gauge.shape[:4])):
                    actual = _tmd9.flow_gauge_for_config(
                        7, tau=3.0, eps=0.05, precision="complex128",
                        save_dir=save_dir, logger=None, save_gauge=True)

                self.assertEqual(actual.shape, gauge.shape)
                flow.assert_called_once()
                self.assertEqual(legacy.read_bytes(), before)

    def test_flow_write_contract_rejects_bad_return_before_persisting(self):
        """flow 写入前必须拒绝错误 shape、dtype 与非有限值。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _unit_gauge()
        cases = {
            "shape": np.zeros((1, 1, 1, 2, 4, 3, 3), dtype=np.complex64),
            "dtype": gauge.copy(),
            "finite": gauge.astype(np.complex64),
        }
        cases["dtype"] = cases["dtype"].astype(np.complex128)
        cases["finite"][0, 0, 0, 0, 0, 0, 0] = np.inf + 0j

        for name, flowed in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as root:
                with patch.object(_tmd9, "read_gauge_lime",
                                  return_value=gauge), \
                        patch.object(_tmd9, "wilson_flow",
                                     return_value=flowed), \
                        patch.object(
                            _tmd9, "flow_action_density",
                            return_value=np.ones(gauge.shape[:4])):
                    with self.assertRaisesRegex(ValueError,
                                                r"shape|dtype|有限"):
                        _tmd9.flow_gauge_for_config(
                            7, tau=3.0, eps=0.05, precision="complex64",
                            save_dir=root, logger=None, save_gauge=True)
                self.assertEqual(_cache_files(root, "flowed_gauge_"), [])

    def test_ope_write_contract_rejects_bad_return_before_persisting(self):
        """OPE 写入前必须拒绝错误 shape、float32 与非有限值。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _unit_gauge()
        cases = {
            "shape": np.zeros((2, 2, 2), dtype=np.float64),
            "dtype": np.zeros((2, 2, 1), dtype=np.float32),
            "finite": np.full((2, 2, 1), np.inf, dtype=np.float64),
        }

        for name, tmd in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as root:
                with patch.object(_tmd9, "flow_gauge_for_config",
                                  return_value=gauge), \
                        patch.object(_tmd9, "tmd_matrix_elements_time",
                                     return_value=tmd):
                    with self.assertRaisesRegex(ValueError,
                                                r"shape|dtype|有限"):
                        _tmd9.compute_tmd_ope_time(
                            7, root, None, [1, 23], [4, 56],
                            staple_length=30, precision="complex128")
                self.assertEqual(_cache_files(root, "tmd_ope_"), [])

    def test_flow_complex64_return_and_disk_dtype_are_preserved(self):
        """合法 complex64 flow 结果返回与落盘 dtype 必须一致。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _unit_gauge()
        with tempfile.TemporaryDirectory() as save_dir, \
                patch.object(_tmd9, "read_gauge_lime", return_value=gauge), \
                patch.object(_tmd9, "wilson_flow",
                             side_effect=lambda value, tau, eps: value), \
                patch.object(
                    _tmd9, "flow_action_density",
                    return_value=np.ones(gauge.shape[:4])):
            flowed = _tmd9.flow_gauge_for_config(
                7, tau=3.0, eps=0.05, precision="complex64",
                save_dir=save_dir, logger=None, save_gauge=True)
            path = _cache_files(save_dir, "flowed_gauge_")[0]
            with h5py.File(path, "r") as handle:
                self.assertEqual(flowed.dtype, np.dtype(np.complex64))
                self.assertEqual(handle["data"].dtype,
                                 np.dtype(np.complex64))
                self.assertEqual(handle["data"].shape, gauge.shape)

    def test_corrupt_matching_legacy_ope_cache_is_ignored_and_untouched(self):
        """契约相同但 data 损坏或 dtype 错误的旧缓存不得复用或改写。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.pipeline._steps import conf_data_dir
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _unit_gauge()
        contract = _ope_contract()
        cases = ("group", "string_dtype")

        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as run_dir:
                cdir = Path(conf_data_dir(run_dir, 7))
                legacy = cdir / (
                    "tmd_ope_z123_b456_L30_Cfundamental_trace_conf7.h5")
                payload = _canonical_json(contract)
                digest = _contract_sha256(contract)
                with h5py.File(legacy, "w") as handle:
                    if case == "group":
                        handle.create_group("data")
                    else:
                        handle.create_dataset(
                            "data", data=np.full((2, 2, 1), "bad", dtype="S3"))
                    handle.attrs[_CONTRACT_JSON_ATTR] = payload
                    handle.attrs[_CONTRACT_SHA_ATTR] = digest
                before = legacy.read_bytes()
                calls = []

                def encode_call(_gauge, z_list, b_list, **_kwargs):
                    calls.append(1)
                    return np.full((len(z_list), len(b_list), 1), 3.0)

                with patch.object(_tmd9, "flow_gauge_for_config",
                                  return_value=gauge), \
                        patch.object(_tmd9, "tmd_matrix_elements_time",
                                     side_effect=encode_call):
                    actual = _tmd9.compute_tmd_ope_time(
                        7, run_dir, None, [1, 23], [4, 56],
                        staple_length=30, precision="complex128")

                self.assertEqual(calls, [1])
                np.testing.assert_array_equal(
                    actual["tmd"], np.full((2, 2, 1), 3.0))
                self.assertEqual(legacy.read_bytes(), before)
                self.assertEqual(len(_cache_files(run_dir, "tmd_ope_")), 2)

    def test_unproven_legacy_ope_cache_is_recomputed(self):
        """旧标签 HDF5 没有可证元数据时只能只读探测，不能复用。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.pipeline._steps import conf_data_dir
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _unit_gauge()
        calls = []

        def encode_call(_gauge, z_list, b_list, **_kwargs):
            calls.append(1)
            return np.full((len(z_list), len(b_list), 1), 1.0)

        with tempfile.TemporaryDirectory() as run_dir:
            cdir = Path(conf_data_dir(run_dir, 7))
            legacy = cdir / (
                "tmd_ope_z123_b456_L30_Cfundamental_trace_conf7.h5")
            with h5py.File(legacy, "w") as handle:
                handle.create_dataset("data", data=np.full((2, 2, 1), 99.0))
            before = legacy.read_bytes()

            with patch.object(_tmd9, "flow_gauge_for_config",
                              return_value=gauge), \
                    patch.object(_tmd9, "tmd_matrix_elements_time",
                                 side_effect=encode_call):
                actual = _tmd9.compute_tmd_ope_time(
                    7, run_dir, None, [1, 23], [4, 56],
                    staple_length=30)

            self.assertTrue(legacy.exists())
            self.assertEqual(legacy.read_bytes(), before)
            self.assertEqual(len(_cache_files(run_dir, "tmd_ope_")), 2)

        np.testing.assert_array_equal(
            actual["tmd"], np.full((2, 2, 1), 1.0))
        self.assertEqual(len(calls), 1)

    def test_metadata_proven_legacy_ope_cache_is_reused_read_only(self):
        """旧标签仅在完整元数据一致时复用，且不得迁移或改写旧文件。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.pipeline._steps import conf_data_dir
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _unit_gauge()
        calls = []

        def encode_call(_gauge, z_list, b_list, **_kwargs):
            calls.append(1)
            return np.full((len(z_list), len(b_list), 1), 7.0)

        with tempfile.TemporaryDirectory() as run_dir, \
                patch.object(_tmd9, "flow_gauge_for_config",
                             return_value=gauge), \
                patch.object(_tmd9, "tmd_matrix_elements_time",
                             side_effect=encode_call):
            first = _tmd9.compute_tmd_ope_time(
                7, run_dir, None, [1, 23], [4, 56],
                staple_length=30)
            canonical = _cache_files(run_dir, "tmd_ope_")[0]
            legacy = Path(conf_data_dir(run_dir, 7)) / (
                "tmd_ope_z123_b456_L30_Cfundamental_trace_conf7.h5")
            self.assertNotEqual(canonical, legacy)
            os.replace(canonical, legacy)

            second = _tmd9.compute_tmd_ope_time(
                7, run_dir, None, [1, 23], [4, 56],
                staple_length=30)
            files = _cache_files(run_dir, "tmd_ope_")

        np.testing.assert_array_equal(first["tmd"], second["tmd"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(files, [legacy])

    def test_flow_log_reports_clover_energy_without_monotonicity_claim(self):
        """粗糙场 Clover E 上升时日志只能诊断，不得宣称流演化单调。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _unit_gauge()
        messages = []
        densities = [
            np.full(gauge.shape[:4], 2.0),
            np.full(gauge.shape[:4], 5.0),
        ]

        with patch.object(_tmd9, "read_gauge_lime", return_value=gauge), \
                patch.object(_tmd9, "wilson_flow", return_value=gauge), \
                patch.object(
                    _tmd9, "flow_action_density", side_effect=densities):
            _tmd9.flow_gauge_for_config(
                7, tau=3.0, eps=0.05, precision="complex128",
                logger=messages.append, save_gauge=False)

        flow_messages = [
            message for message in messages if "wilson_flow" in message
        ]
        self.assertEqual(len(flow_messages), 1)
        diagnostic = flow_messages[0]
        self.assertIn("Clover E diagnostic", diagnostic)
        self.assertIn("E(t=0)=2.0000", diagnostic)
        self.assertIn("E(t=3.0)=5.0000", diagnostic)
        for forbidden in ("decrease", "increase", "monotonic", "->"):
            self.assertNotIn(forbidden, diagnostic.lower())

    def test_flow_rejects_unknown_precision_before_cache_or_gauge_io(self):
        """非法 precision 必须在建目录、探缓存或读取 gauge 前失败。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _unit_gauge()
        invalid_precisions = (
            "float32", "complex256", None, np.dtype("complex128"))

        with tempfile.TemporaryDirectory() as root, \
                patch.object(
                    _tmd9, "_load_first_matching_cache",
                    return_value=(None, None)) as cache_probe, \
                patch.object(
                    _tmd9, "read_gauge_lime",
                    return_value=gauge) as gauge_reader, \
                patch.object(
                    _tmd9, "flow_action_density",
                    return_value=np.ones(gauge.shape[:4])) as density, \
                patch.object(
                    _tmd9, "wilson_flow", return_value=gauge) as flow, \
                patch.object(_tmd9, "_save_contract_h5") as cache_save, \
                patch.object(
                    _tmd9.os.path, "getsize", return_value=0) as size_probe:
            errors = []
            save_dirs = []
            for index, precision in enumerate(invalid_precisions):
                save_dir = Path(root) / f"flow-{index}"
                save_dirs.append(save_dir)
                try:
                    _tmd9.flow_gauge_for_config(
                        7, precision=precision, save_dir=save_dir,
                        logger=None, save_gauge=True)
                except ValueError as exc:
                    errors.append(exc)
                else:
                    errors.append(None)

            self.assertTrue(all(isinstance(exc, ValueError) for exc in errors))
            for exc in errors:
                self.assertRegex(str(exc), r"complex64.*complex128")
            self.assertFalse(any(path.exists() for path in save_dirs))
            cache_probe.assert_not_called()
            gauge_reader.assert_not_called()
            density.assert_not_called()
            flow.assert_not_called()
            cache_save.assert_not_called()
            size_probe.assert_not_called()

    def test_ope_cache_apis_reject_unknown_precision_without_side_effects(self):
        """OPE 计算与加载（含空组态集）均须先拒绝非法 precision。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _unit_gauge()

        def capture_value_error(call):
            try:
                call()
            except ValueError as exc:
                return exc
            return None

        with tempfile.TemporaryDirectory() as root, \
                patch.object(
                    _tmd9, "_load_first_matching_cache",
                    return_value=(None, None)) as cache_probe, \
                patch.object(
                    _tmd9, "flow_gauge_for_config",
                    return_value=gauge) as flow, \
                patch.object(
                    _tmd9, "tmd_matrix_elements_time",
                    return_value=np.zeros((2, 1, 1))) as matrix_elements, \
                patch.object(_tmd9, "_save_contract_h5") as cache_save:
            compute_dir = Path(root) / "compute"
            load_dir = Path(root) / "load"
            empty_load_dir = Path(root) / "load-empty"
            errors = {
                "compute": capture_value_error(lambda: (
                    _tmd9.compute_tmd_ope_time(
                        7, compute_dir, None, [0, 1], [0],
                        precision="float32"))),
                "load": capture_value_error(lambda: (
                    _tmd9.load_tmd_ope_all(
                        load_dir, [7], [0, 1], [0], logger=None,
                        precision="float32"))),
                "load_empty": capture_value_error(lambda: (
                    _tmd9.load_tmd_ope_all(
                        empty_load_dir, [], [0, 1], [0], logger=None,
                        precision="float32"))),
            }

            self.assertTrue(all(
                isinstance(exc, ValueError) for exc in errors.values()))
            for exc in errors.values():
                self.assertRegex(str(exc), r"complex64.*complex128")
            self.assertFalse(compute_dir.exists())
            self.assertFalse(load_dir.exists())
            self.assertFalse(empty_load_dir.exists())
            cache_probe.assert_not_called()
            flow.assert_not_called()
            matrix_elements.assert_not_called()
            cache_save.assert_not_called()

    def test_flow_rejects_invalid_controls_before_cache_or_gauge_io(self):
        """tau>=0 且 eps>0 必须早于流场缓存探测和 gauge 读取。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _unit_gauge()
        cases = ((-1.0, 0.05), (3.0, 0.0), (3.0, -0.05))

        with tempfile.TemporaryDirectory() as root, \
                patch.object(
                    _tmd9, "_load_first_matching_cache",
                    return_value=(None, None)) as cache_probe, \
                patch.object(
                    _tmd9, "read_gauge_lime", return_value=gauge) as reader, \
                patch.object(
                    _tmd9, "wilson_flow", return_value=gauge) as flow, \
                patch.object(
                    _tmd9, "flow_action_density",
                    return_value=np.ones(gauge.shape[:4])) as density:
            errors = []
            save_dirs = []
            for index, (tau, eps) in enumerate(cases):
                save_dir = Path(root) / f"flow-controls-{index}"
                save_dirs.append(save_dir)
                try:
                    _tmd9.flow_gauge_for_config(
                        7, tau=tau, eps=eps, precision="complex128",
                        save_dir=save_dir, logger=None, save_gauge=False)
                except ValueError as exc:
                    errors.append(exc)
                else:
                    errors.append(None)

            self.assertTrue(all(isinstance(exc, ValueError) for exc in errors))
            for exc in errors:
                self.assertRegex(str(exc), r"tau|eps|非负|正")
            self.assertFalse(any(path.exists() for path in save_dirs))
            cache_probe.assert_not_called()
            reader.assert_not_called()
            flow.assert_not_called()
            density.assert_not_called()

    def test_ope_request_controls_precede_cache_and_directory_side_effects(self):
        """OPE 控制量、方向和空列表须在 cache probe/cdir 前拒绝。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _unit_gauge()
        baseline = {
            "tau": 3.0,
            "eps": 0.05,
            "precision": "complex128",
            "z_dir": 2,
            "b_dir": 0,
            "z_list": [0, 1],
            "b_list": [0],
            "staple_length": 30,
        }
        cases = (
            ("tau", {"tau": -1.0}),
            ("eps", {"eps": 0.0}),
            ("z_dir", {"z_dir": 3}),
            ("same_direction", {"z_dir": 1, "b_dir": 1}),
            ("empty_z", {"z_list": []}),
            ("empty_b", {"b_list": []}),
        )

        with tempfile.TemporaryDirectory() as root, \
                patch.object(
                    _tmd9, "_load_first_matching_cache",
                    return_value=(None, None)) as cache_probe, \
                patch.object(
                    _tmd9, "flow_gauge_for_config",
                    return_value=gauge) as flow, \
                patch.object(
                    _tmd9, "tmd_matrix_elements_time",
                    return_value=np.zeros((2, 1, 1))) as matrix_elements, \
                patch.object(_tmd9, "_save_contract_h5") as cache_save:
            compute_errors = []
            load_errors = []
            compute_dirs = []
            load_dirs = []
            for name, override in cases:
                compute_params = {**baseline, **override}
                compute_dir = Path(root) / f"compute-{name}"
                compute_dirs.append(compute_dir)
                try:
                    _tmd9.compute_tmd_ope_time(
                        7, compute_dir, None,
                        compute_params.pop("z_list"),
                        compute_params.pop("b_list"),
                        **compute_params)
                except ValueError as exc:
                    compute_errors.append(exc)
                else:
                    compute_errors.append(None)

                load_params = {**baseline, **override}
                load_dir = Path(root) / f"load-{name}"
                load_dirs.append(load_dir)
                try:
                    _tmd9.load_tmd_ope_all(
                        load_dir, [],
                        load_params.pop("z_list"),
                        load_params.pop("b_list"),
                        logger=None, **load_params)
                except ValueError as exc:
                    load_errors.append(exc)
                else:
                    load_errors.append(None)

            for errors in (compute_errors, load_errors):
                self.assertTrue(
                    all(isinstance(exc, ValueError) for exc in errors))
                for exc in errors:
                    self.assertRegex(
                        str(exc), r"tau|eps|方向|空间|z_list|b_list|不能为空")
            self.assertFalse(any(path.exists() for path in compute_dirs))
            self.assertFalse(any(path.exists() for path in load_dirs))
            cache_probe.assert_not_called()
            flow.assert_not_called()
            matrix_elements.assert_not_called()
            cache_save.assert_not_called()

    def test_save_array_writes_attrs_before_atomic_replace_once(self):
        """严格 HDF5 属性须在临时文件中完成，且张量只保存一次。"""
        from pyqcd.pipeline import _steps

        data = np.arange(6, dtype=np.float64).reshape(2, 3)
        contract = _flow_contract()
        payload = _canonical_json(contract)
        digest = _contract_sha256(contract)
        attrs = {
            _CONTRACT_JSON_ATTR: payload,
            _CONTRACT_SHA_ATTR: digest,
        }

        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "nested" / "array.h5"
            real_save = _steps.save_tensor_h5
            real_replace = _steps.os.replace
            replace_observations = []

            def save_once(array, path):
                return real_save(array, path)

            def inspect_then_replace(source, target):
                with h5py.File(source, "r") as handle:
                    replace_observations.append({
                        "keys": set(handle.keys()),
                        "payload": handle.attrs.get(_CONTRACT_JSON_ATTR),
                        "digest": handle.attrs.get(_CONTRACT_SHA_ATTR),
                    })
                return real_replace(source, target)

            with patch.object(
                    _steps, "save_tensor_h5",
                    side_effect=save_once) as tensor_save, \
                    patch.object(
                        _steps.os, "replace",
                        side_effect=inspect_then_replace) as replace:
                save_error = None
                try:
                    _steps.save_array(
                        destination, data, logger=None, attrs=attrs)
                except TypeError as exc:
                    save_error = exc

            self.assertIsNone(save_error)
            self.assertEqual(tensor_save.call_count, 1)
            self.assertEqual(replace.call_count, 1)
            self.assertEqual(replace_observations, [{
                "keys": {"data"},
                "payload": payload,
                "digest": digest,
            }])
            with h5py.File(destination, "r") as handle:
                self.assertEqual(set(handle.keys()), {"data"})
                self.assertEqual(handle.attrs[_CONTRACT_JSON_ATTR], payload)
                self.assertEqual(handle.attrs[_CONTRACT_SHA_ATTR], digest)
                np.testing.assert_array_equal(handle["data"][...], data)

    def test_vertex_and_2pt_request_validation_precedes_all_side_effects(self):
        """momentum/channels/v_kind 必须在目录、缓存与 delegate 前拒绝。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")

        def capture_exception(callable_):
            try:
                callable_()
            except Exception as exc:  # RED 阶段也把缺失关键字 API 变成断言失败
                return exc
            return None

        with tempfile.TemporaryDirectory() as root, \
                patch.object(
                    _tmd9, "compute_vertices_for_config") as vertices, \
                patch.object(
                    _tmd9, "compute_2pt_for_config_multi") as two_pt, \
                patch.object(
                    _tmd9, "_load_first_matching_cache") as cache_probe:
            root_path = Path(root)
            cases = (
                ("vertex_empty_momenta", lambda path: (
                    _tmd9.compute_vertices_multi(
                        7, path, None, [], precision="complex64"))),
                ("vertex_bad_triplet", lambda path: (
                    _tmd9.compute_vertices_multi(
                        7, path, None, [(0, 0)], precision="complex64"))),
                ("vertex_bool_component", lambda path: (
                    _tmd9.compute_vertices_multi(
                        7, path, None, [(0, False, 0)],
                        precision="complex64"))),
                ("two_pt_empty_momenta", lambda path: (
                    _tmd9.compute_2pt_multi(
                        7, path, None, {}, [], precision="complex64"))),
                ("two_pt_empty_channels", lambda path: (
                    _tmd9.compute_2pt_multi(
                        7, path, None, {}, [(0, 0, 0)],
                        precision="complex64", channels=()))),
                ("two_pt_bad_v_kind", lambda path: (
                    _tmd9.compute_2pt_multi(
                        7, path, None, {}, [(0, 0, 0)],
                        precision="complex64", channels=("pp",),
                        v_kind="UNKNOWN"))),
                ("load_empty_momenta", lambda path: (
                    _tmd9.load_multi_2pt(
                        path, [], [], channels=("pp",), logger=None))),
                ("load_bad_channels", lambda path: (
                    _tmd9.load_multi_2pt(
                        path, [], ["P000"], channels=(), logger=None))),
                ("load_bad_v_kind", lambda path: (
                    _tmd9.load_multi_2pt(
                        path, [], ["P000"], channels=("pp",), logger=None,
                        v_kind="UNKNOWN"))),
            )
            errors = []
            paths = []
            for name, call in cases:
                path = root_path / name
                paths.append(path)
                errors.append(capture_exception(lambda p=path, fn=call: fn(p)))

            self.assertTrue(all(isinstance(exc, ValueError) for exc in errors))
            for exc in errors:
                self.assertRegex(
                    str(exc), r"moment|动量|三个|整数|channels|通道|v_kind|不能为空")
            self.assertFalse(any(path.exists() for path in paths))
            vertices.assert_not_called()
            two_pt.assert_not_called()
            cache_probe.assert_not_called()

    def test_strict_specs_separate_order_precision_channels_and_v_kind(self):
        """完整有序请求必须进入 contract、SHA 与 canonical 文件名。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        momenta = [(0, 0, 0), (2, 0, 0)]
        reversed_momenta = list(reversed(momenta))
        vertex_specs = []
        two_pt_specs = []

        def capture_vertex(*_args, **kwargs):
            vertex_specs.append(kwargs.get("strict_cache"))
            return {
                "VdV": np.zeros((1, 2, 2, 2), dtype=np.complex64),
                "VVV": np.zeros((1, 2, 1, 1, 1), dtype=np.complex64),
            }

        def capture_two_pt(*_args, **kwargs):
            two_pt_specs.append(kwargs.get("strict_cache"))
            return {}

        with tempfile.TemporaryDirectory() as root, \
                patch.object(
                    _tmd9, "compute_vertices_for_config",
                    side_effect=capture_vertex), \
                patch.object(
                    _tmd9, "compute_2pt_for_config_multi",
                    side_effect=capture_two_pt):
            _tmd9.compute_vertices_multi(
                7, root, None, momenta, precision="complex64")
            _tmd9.compute_vertices_multi(
                7, root, None, reversed_momenta, precision="complex64")
            _tmd9.compute_vertices_multi(
                7, root, None, momenta, precision="complex128")

            variants = (
                (momenta, "complex64", ("pp",), "VVV"),
                (reversed_momenta, "complex64", ("pp",), "VVV"),
                (momenta, "complex128", ("pp",), "VVV"),
                (momenta, "complex64", ("pp", "pion"), "VVV"),
                (momenta, "complex64", ("pion", "pp"), "VVV"),
                (momenta, "complex64", ("pp",), "VDV"),
            )
            errors = []
            for requested_momenta, precision, channels, v_kind in variants:
                try:
                    _tmd9.compute_2pt_multi(
                        7, root, None, {}, requested_momenta,
                        precision=precision, channels=channels,
                        v_kind=v_kind)
                except Exception as exc:
                    errors.append(exc)

        self.assertEqual(errors, [])
        self.assertEqual(len(vertex_specs), 3)
        self.assertEqual(len(two_pt_specs), 6)
        self.assertTrue(all(isinstance(specs, dict) for specs in vertex_specs))
        self.assertTrue(all(isinstance(specs, dict) for specs in two_pt_specs))

        vertex_paths = []
        for specs in vertex_specs:
            self.assertEqual(set(specs), {"VdV", "VVV"})
            for kind, spec in specs.items():
                contract = spec["contract"]
                self.assertEqual(contract["algorithm_version"],
                                 _VERTEX_ALGORITHM_VERSION)
                self.assertEqual(contract["artifact"],
                                 f"tmd9_vertex_{kind.lower()}")
                self.assertEqual(contract["lattice"], _lattice_contract())
                self.assertEqual(contract["shape"], list(spec["shape"]))
                self.assertEqual(contract["dtype"],
                                 np.dtype(spec["dtype"]).name)
                self.assertIn(_contract_sha256(contract), spec["path"])
                vertex_paths.append(spec["path"])
        self.assertEqual(len(vertex_paths), len(set(vertex_paths)))

        request_fingerprints = []
        all_two_pt_paths = []
        for specs in two_pt_specs:
            self.assertTrue(specs)
            sample = next(iter(specs.values()))["contract"]
            request_fingerprints.append((
                tuple(map(tuple, sample["momenta"])),
                tuple(sample["channels"]),
                sample["precision"], sample["v_kind"],
            ))
            for spec in specs.values():
                contract = spec["contract"]
                self.assertEqual(contract["algorithm_version"],
                                 _MULTI_2PT_ALGORITHM_VERSION)
                self.assertEqual(contract["lattice"], _lattice_contract())
                self.assertEqual(contract["shape"], [1])
                self.assertEqual(contract["dtype"], "float64")
                self.assertIn(_contract_sha256(contract), spec["path"])
                all_two_pt_paths.append(spec["path"])
        self.assertEqual(len(request_fingerprints),
                         len(set(request_fingerprints)))
        self.assertEqual(len(all_two_pt_paths), len(set(all_two_pt_paths)))

    def test_valid_vertex_canonical_cache_skips_eigvec_io(self):
        """两个 vertex artifact 均可证明匹配时必须早于 eigvec IO 返回。"""
        from pyqcd.pipeline import _steps, _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        momenta = [(0, 0, 0), (2, 0, 0)]
        expected = {
            "VdV": (np.arange(8).reshape(1, 2, 2, 2)
                    .astype(np.complex64)),
            "VVV": (np.arange(2).reshape(1, 2, 1, 1, 1)
                    .astype(np.complex64) + np.complex64(1j)),
        }

        with tempfile.TemporaryDirectory() as root:
            cdir = _strict_conf_dir(root)
            cdir.mkdir(parents=True)
            for kind, data in expected.items():
                contract = _vertex_contract(kind, momenta=momenta)
                _write_contract_h5(
                    _vertex_cache_path(root, kind, contract),
                    contract, data)

            with patch.object(
                    _steps, "readin_eigvecs_gpu",
                    side_effect=AssertionError(
                        "valid strict vertex cache performed eigvec IO")):
                actual = _tmd9.compute_vertices_multi(
                    7, root, None, momenta, precision="complex64")

        for kind in ("VdV", "VVV"):
            np.testing.assert_array_equal(actual[kind], expected[kind])
            self.assertEqual(actual[kind].dtype, np.dtype(np.complex64))

    def test_vertex_strict_miss_writes_exact_complex64_contract(self):
        """vertex 首次计算须只写 canonical 文件及请求 complex64 dtype。"""
        from pyqcd.pipeline import _steps, _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        momenta = [(0, 0, 0), (2, 0, 0)]
        eigvec = np.ones((2, 1, 1, 1, 3), dtype=np.complex128)
        vdv_t = np.full((2, 2, 2), 1.0 + 2.0j, dtype=np.complex64)
        vvv_t = np.full((1, 1, 1), 3.0 + 4.0j, dtype=np.complex64)

        with tempfile.TemporaryDirectory() as root, \
                patch.object(
                    _steps, "readin_eigvecs_gpu", return_value=eigvec), \
                patch.object(
                    _steps, "Mom_VdV_sink_t", return_value=vdv_t), \
                patch.object(
                    _steps, "_compute_vvv_single_t_gpu",
                    return_value=vvv_t):
            actual = _tmd9.compute_vertices_multi(
                7, root, None, momenta, precision="complex64")

            for kind in ("VdV", "VVV"):
                contract = _vertex_contract(kind, momenta=momenta)
                path = _vertex_cache_path(root, kind, contract)
                self.assertTrue(path.is_file(), path)
                with h5py.File(path, "r") as handle:
                    self.assertEqual(set(handle.keys()), {"data"})
                    self.assertEqual(
                        handle.attrs[_CONTRACT_JSON_ATTR],
                        _canonical_json(contract))
                    self.assertEqual(
                        handle.attrs[_CONTRACT_SHA_ATTR],
                        _contract_sha256(contract))
                    self.assertEqual(handle["data"].shape,
                                     tuple(contract["shape"]))
                    self.assertEqual(handle["data"].dtype,
                                     np.dtype(np.complex64))
                    self.assertTrue(np.isfinite(handle["data"][...]).all())
                self.assertEqual(actual[kind].dtype, np.dtype(np.complex64))

            legacy = list(_strict_conf_dir(root).glob(
                "VdV_vdv-*__vvv-*_7.h5"))
            legacy += list(_strict_conf_dir(root).glob(
                "VVV_vdv-*__vvv-*_7.h5"))
            self.assertEqual(legacy, [])

    def test_vertex_write_rejects_shape_dtype_and_nonfinite_results(self):
        """strict vertex 后置 shape/dtype/finite 门必须早于任何写入。"""
        from pyqcd.pipeline import _steps, _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        momenta = [(0, 0, 0), (2, 0, 0)]
        eigvec = np.ones((2, 1, 1, 1, 3), dtype=np.complex128)
        real_zeros = _steps.np.zeros

        for artifact in ("VdV", "VVV"):
            for mode in ("shape", "dtype", "finite"):
                with self.subTest(artifact=artifact, mode=mode), \
                        tempfile.TemporaryDirectory() as root:
                    expected_allocation = (
                        (1, 2, 2, 2) if artifact == "VdV"
                        else (1, 2, 1, 1, 1))

                    def controlled_zeros(shape, *args, **kwargs):
                        if tuple(shape) == expected_allocation:
                            if mode == "shape":
                                shape = (2,) + tuple(shape)[1:]
                            elif mode == "dtype":
                                kwargs["dtype"] = np.complex128
                        return real_zeros(shape, *args, **kwargs)

                    vdv_t = np.ones((2, 2, 2), dtype=np.complex64)
                    vvv_t = np.ones((1, 1, 1), dtype=np.complex64)
                    if artifact == "VdV" and mode == "finite":
                        vdv_t[0, 0, 0] = np.nan + 0j
                    if artifact == "VVV" and mode == "finite":
                        vvv_t[0, 0, 0] = np.nan + 0j
                    with patch.object(
                            _steps, "readin_eigvecs_gpu",
                            return_value=eigvec), \
                            patch.object(
                                _steps, "Mom_VdV_sink_t",
                                return_value=vdv_t), \
                            patch.object(
                                _steps, "_compute_vvv_single_t_gpu",
                                return_value=vvv_t), \
                            patch.object(_steps.np, "zeros",
                                         side_effect=controlled_zeros):
                        with self.assertRaisesRegex(
                                ValueError, r"shape|dtype|有限|NaN|Inf"):
                            _tmd9.compute_vertices_multi(
                                7, root, None, momenta,
                                precision="complex64")
                    self.assertEqual(
                        list(_strict_conf_dir(root).glob(
                            "*tmd9-strict-v1*.h5")), [])

    def test_vertex_rejects_corrupt_canonical_and_unproven_legacy_read_only(self):
        """vertex 错 shape/dtype/SHA/finite/metadata/dataset 均不得命中。"""
        from pyqcd.pipeline import _steps, _tmd9
        from pyqcd.tools import set_backend

        class RecomputeTriggered(RuntimeError):
            pass

        set_backend("numpy")
        momenta = [(0, 0, 0), (2, 0, 0)]
        good_vdv = np.ones((1, 2, 2, 2), dtype=np.complex64)
        good_vvv = np.ones((1, 2, 1, 1, 1), dtype=np.complex64)
        fingerprint = (
            "vdv-p0_0_0-p2_0_0__vvv-p0_0_0-p2_0_0")

        for mode in ("shape", "dtype", "nan", "inf", "sha", "json",
                     "metadata", "dataset"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                cdir = _strict_conf_dir(root)
                cdir.mkdir(parents=True)
                vdv_contract = _vertex_contract("VdV", momenta=momenta)
                vvv_contract = _vertex_contract("VVV", momenta=momenta)
                vdv_path = _vertex_cache_path(root, "VdV", vdv_contract)
                vvv_path = _vertex_cache_path(root, "VVV", vvv_contract)

                bad_vdv = good_vdv.copy()
                digest = None
                if mode == "shape":
                    bad_vdv = np.ones((1, 2, 2, 3), dtype=np.complex64)
                elif mode == "dtype":
                    bad_vdv = good_vdv.astype(np.complex128)
                elif mode == "nan":
                    bad_vdv[0, 0, 0, 0] = np.nan + 0j
                elif mode == "inf":
                    bad_vdv[0, 0, 0, 0] = np.inf + 0j
                elif mode == "sha":
                    digest = "0" * 64

                metadata_contract = vdv_contract
                if mode == "json":
                    metadata_contract = {
                        **vdv_contract,
                        "algorithm_version": "wrong.vertex.algorithm.v9",
                    }

                if mode == "metadata":
                    with h5py.File(vdv_path, "w") as handle:
                        handle.create_dataset("data", data=bad_vdv)
                else:
                    _write_contract_h5(
                        vdv_path, metadata_contract, bad_vdv, digest=digest)
                    if mode == "dataset":
                        with h5py.File(vdv_path, "r+") as handle:
                            handle.create_dataset("extra", data=np.zeros(1))
                _write_contract_h5(vvv_path, vvv_contract, good_vvv)

                legacy_vdv = cdir / f"VdV_{fingerprint}_7.h5"
                legacy_vvv = cdir / f"VVV_{fingerprint}_7.h5"
                with h5py.File(legacy_vdv, "w") as handle:
                    handle.create_dataset("data", data=good_vdv * 9)
                with h5py.File(legacy_vvv, "w") as handle:
                    handle.create_dataset("data", data=good_vvv * 9)
                before = {
                    path: path.read_bytes()
                    for path in (vdv_path, vvv_path,
                                 legacy_vdv, legacy_vvv)
                }

                with patch.object(
                        _steps, "readin_eigvecs_gpu",
                        side_effect=RecomputeTriggered("strict cache miss")):
                    with self.assertRaises(RecomputeTriggered):
                        _tmd9.compute_vertices_multi(
                            7, root, None, momenta,
                            precision="complex64")
                for path, original in before.items():
                    self.assertEqual(path.read_bytes(), original)

    def test_valid_multi_2pt_cache_skips_peram_and_strict_loader_wins(self):
        """合法 2pt canonical cache 跳过 peram，loader 不得误取 legacy。"""
        from pyqcd.pipeline import _steps, _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        momenta = [(0, 0, 0), (2, 0, 0)]
        channels = ("pp", "pion")
        expected = {}

        with tempfile.TemporaryDirectory() as root:
            cdir = _strict_conf_dir(root)
            cdir.mkdir(parents=True)
            marker = 1.0
            for channel in channels:
                for momentum in momenta:
                    contract = _multi_2pt_contract(
                        channel, momentum, momenta=momenta,
                        channels=channels)
                    value = np.array([marker], dtype=np.float64)
                    marker += 1.0
                    expected[f"corr_{channel}_P{momentum[0]}{momentum[1]}{momentum[2]}"] = value
                    _write_contract_h5(
                        _multi_2pt_cache_path(root, contract),
                        contract, value)
                    legacy = cdir / (
                        f"corr_{channel}_P{momentum[0]}{momentum[1]}"
                        f"{momentum[2]}_7.h5")
                    with h5py.File(legacy, "w") as handle:
                        handle.create_dataset(
                            "data", data=np.array([99.0], dtype=np.float64))

            with patch.object(
                    _steps, "readin_peram_time_slice",
                    side_effect=AssertionError(
                        "valid strict 2pt cache performed peram IO")):
                actual = _tmd9.compute_2pt_multi(
                    7, root, None, {
                        "VdV": np.ones(
                            (1, 2, 2, 2), dtype=np.complex64),
                        "VVV": np.ones(
                            (1, 2, 1, 1, 1), dtype=np.complex64),
                    }, momenta,
                    precision="complex64", channels=channels)
            loaded = _tmd9.load_multi_2pt(
                root, [7], ["P000", "P200"],
                channels=channels, logger=None)

        self.assertEqual(set(actual), set(expected))
        self.assertEqual(set(loaded), {7})
        for key, value in expected.items():
            np.testing.assert_array_equal(actual[key], value)
            np.testing.assert_array_equal(loaded[7][key], value)
            self.assertEqual(actual[key].dtype, np.dtype(np.float64))

    def test_multi_2pt_miss_writes_float64_contract_and_preserves_legacy(self):
        """2pt strict miss 只写 canonical，并保持同名旧产物字节不变。"""
        from pyqcd.pipeline import _steps, _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        momenta = [(0, 0, 0)]
        channels = ("pp",)
        vertices = {
            "VdV": np.ones((1, 1, 2, 2), dtype=np.complex64),
            "VVV": np.ones((1, 1, 1, 1, 1), dtype=np.complex64),
        }

        with tempfile.TemporaryDirectory() as root:
            cdir = _strict_conf_dir(root)
            cdir.mkdir(parents=True)
            legacy = cdir / "corr_pp_P000_7.h5"
            with h5py.File(legacy, "w") as handle:
                handle.create_dataset(
                    "data", data=np.array([99.0], dtype=np.float64))
            legacy_before = legacy.read_bytes()

            with patch.object(
                    _steps, "readin_peram_time_slice",
                    return_value=np.ones(
                        (1, 1, 1, 2, 2), dtype=np.complex64)), \
                    patch.object(
                        _steps, "seq_peram",
                        side_effect=lambda value: value), \
                    patch.object(_steps, "_run_2pt", return_value=2.5):
                actual = _tmd9.compute_2pt_multi(
                    7, root, None, vertices, momenta,
                    precision="complex64", channels=channels)

            contract = _multi_2pt_contract(
                "pp", momenta[0], momenta=momenta,
                channels=channels)
            canonical = _multi_2pt_cache_path(root, contract)
            self.assertEqual(legacy.read_bytes(), legacy_before)
            self.assertTrue(canonical.is_file(), canonical)
            np.testing.assert_array_equal(
                actual["corr_pp_P000"], np.array([2.5]))
            self.assertEqual(actual["corr_pp_P000"].dtype,
                             np.dtype(np.float64))
            with h5py.File(canonical, "r") as handle:
                self.assertEqual(set(handle.keys()), {"data"})
                self.assertEqual(handle["data"].shape, (1,))
                self.assertEqual(handle["data"].dtype, np.dtype(np.float64))
                self.assertEqual(handle.attrs[_CONTRACT_JSON_ATTR],
                                 _canonical_json(contract))
                self.assertEqual(handle.attrs[_CONTRACT_SHA_ATTR],
                                 _contract_sha256(contract))

    def test_multi_2pt_write_rejects_shape_dtype_and_nonfinite_results(self):
        """2pt 后置 shape/dtype/finite 门失败时不得产生 canonical 文件。"""
        from pyqcd.pipeline import _steps, _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        momenta = [(0, 0, 0)]
        vertices = {
            "VdV": np.ones((1, 1, 2, 2), dtype=np.complex64),
            "VVV": np.ones((1, 1, 1, 1, 1), dtype=np.complex64),
        }
        real_zeros = _steps.np.zeros

        for mode in ("shape", "dtype", "finite"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                def controlled_zeros(shape, *args, **kwargs):
                    if (tuple(np.atleast_1d(shape)) == (1,)
                            and kwargs.get("dtype") == np.float64):
                        if mode == "shape":
                            shape = 2
                        elif mode == "dtype":
                            kwargs["dtype"] = np.float32
                    return real_zeros(shape, *args, **kwargs)

                value = np.inf if mode == "finite" else 1.0
                with patch.object(
                        _steps, "readin_peram_time_slice",
                        return_value=np.ones(
                            (1, 1, 1, 2, 2), dtype=np.complex64)), \
                        patch.object(
                            _steps, "seq_peram",
                            side_effect=lambda array: array), \
                        patch.object(_steps, "_run_2pt",
                                     return_value=value), \
                        patch.object(_steps.np, "zeros",
                                     side_effect=controlled_zeros):
                    with self.assertRaisesRegex(
                            ValueError, r"shape|dtype|有限|NaN|Inf"):
                        _tmd9.compute_2pt_multi(
                            7, root, None, vertices, momenta,
                            precision="complex64", channels=("pp",))
                self.assertEqual(
                    list(_strict_conf_dir(root).glob(
                        "*tmd9-strict-v1*.h5")), [])

    def test_load_multi_2pt_rejects_all_corrupt_canonical_and_legacy(self):
        """2pt loader 对 shape/dtype/SHA/NaN/Inf/metadata/dataset 全部只读拒绝。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        momentum = (0, 0, 0)
        contract = _multi_2pt_contract(
            "pp", momentum, momenta=(momentum,), channels=("pp",))

        for mode in ("shape", "dtype", "nan", "inf", "sha", "json",
                     "metadata", "dataset"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                cdir = _strict_conf_dir(root)
                cdir.mkdir(parents=True)
                canonical = _multi_2pt_cache_path(root, contract)
                bad = np.array([1.0], dtype=np.float64)
                digest = None
                if mode == "shape":
                    bad = np.array([1.0, 2.0], dtype=np.float64)
                elif mode == "dtype":
                    bad = bad.astype(np.float32)
                elif mode == "nan":
                    bad[0] = np.nan
                elif mode == "inf":
                    bad[0] = np.inf
                elif mode == "sha":
                    digest = "0" * 64

                metadata_contract = contract
                if mode == "json":
                    metadata_contract = {
                        **contract,
                        "algorithm_version": "wrong.multi-2pt.algorithm.v9",
                    }

                if mode == "metadata":
                    with h5py.File(canonical, "w") as handle:
                        handle.create_dataset("data", data=bad)
                else:
                    _write_contract_h5(
                        canonical, metadata_contract, bad, digest=digest)
                    if mode == "dataset":
                        with h5py.File(canonical, "r+") as handle:
                            handle.create_dataset("extra", data=np.zeros(1))

                legacy = cdir / "corr_pp_P000_7.h5"
                with h5py.File(legacy, "w") as handle:
                    handle.create_dataset(
                        "data", data=np.array([99.0], dtype=np.float64))
                before = {
                    canonical: canonical.read_bytes(),
                    legacy: legacy.read_bytes(),
                }

                actual = _tmd9.load_multi_2pt(
                    root, [7], ["P000"], channels=("pp",), logger=None)
                self.assertEqual(actual, {})
                for path, original in before.items():
                    self.assertEqual(path.read_bytes(), original)

    def test_vertex_and_2pt_wrappers_reject_unknown_precision_before_delegate(self):
        """test9 的顶点/2pt 入口也必须在下游和目录 IO 前拒绝非法精度。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        with tempfile.TemporaryDirectory() as root, \
                patch.object(_tmd9, "compute_vertices_for_config") as vertices, \
                patch.object(_tmd9, "compute_2pt_for_config_multi") as two_pt:
            with self.assertRaisesRegex(ValueError, r"complex64.*complex128"):
                _tmd9.compute_vertices_multi(
                    7, Path(root) / "vertices", None, [], precision="float32")
            with self.assertRaisesRegex(ValueError, r"complex64.*complex128"):
                _tmd9.compute_2pt_multi(
                    7, Path(root) / "two_pt", None, {}, [], precision="float32")

            self.assertFalse((Path(root) / "vertices").exists())
            self.assertFalse((Path(root) / "two_pt").exists())
            vertices.assert_not_called()
            two_pt.assert_not_called()

    def test_flowed_gauge_cache_key_and_metadata_cover_flow_contract(self):
        """流场键及 HDF5 契约必须区分 tau、eps、precision。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _unit_gauge()
        calls = []

        def encode_flow(gauge_in, tau, eps):
            calls.append((float(tau), float(eps), str(gauge_in.dtype)))
            return gauge_in + len(calls)

        variants = [
            {"tau": 3.0, "eps": 0.05, "precision": "complex128"},
            {"tau": 4.0, "eps": 0.05, "precision": "complex128"},
            {"tau": 3.0, "eps": 0.025, "precision": "complex128"},
            {"tau": 3.0, "eps": 0.05, "precision": "complex64"},
        ]

        with tempfile.TemporaryDirectory() as save_dir, \
                patch.object(_tmd9, "read_gauge_lime", return_value=gauge), \
                patch.object(_tmd9, "wilson_flow", side_effect=encode_flow), \
                patch.object(
                    _tmd9, "flow_action_density",
                    return_value=np.ones(gauge.shape[:4])):
            markers = []
            for params in variants:
                flowed = _tmd9.flow_gauge_for_config(
                    7, save_dir=save_dir, logger=None, save_gauge=True,
                    **params)
                markers.append(float(np.real(flowed[0, 0, 0, 0, 0, 0, 0])))
            files = _cache_files(save_dir, "flowed_gauge_")
            actual_payloads = set()
            for path in files:
                with h5py.File(path, "r") as handle:
                    self.assertIn(_CONTRACT_JSON_ATTR, handle.attrs)
                    self.assertIn(_CONTRACT_SHA_ATTR, handle.attrs)
                    payload = handle.attrs[_CONTRACT_JSON_ATTR]
                    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
                    self.assertEqual(handle.attrs[_CONTRACT_SHA_ATTR], digest)
                    self.assertIn(digest, path.name)
                    actual_payloads.add(payload)

        expected_payloads = {
            _canonical_json(_flow_contract(**params)) for params in variants
        }
        self.assertEqual(markers, [2.0, 3.0, 4.0, 5.0])
        self.assertEqual(len(calls), len(variants))
        self.assertEqual(len(files), len(variants))
        self.assertEqual(actual_payloads, expected_payloads)

    def test_unproven_legacy_flowed_gauge_is_recomputed(self):
        """旧流场无完整元数据时不得跨 tau/eps/precision 复用。"""
        from pyqcd.pipeline import _tmd9
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _unit_gauge()
        calls = []

        def encode_flow(gauge_in, tau, eps):
            calls.append((tau, eps))
            return gauge_in + 1.0

        with tempfile.TemporaryDirectory() as save_dir:
            legacy = Path(save_dir) / "flowed_gauge_7.h5"
            with h5py.File(legacy, "w") as handle:
                handle.create_dataset("data", data=np.full_like(gauge, 99.0))
            before = legacy.read_bytes()

            with patch.object(_tmd9, "read_gauge_lime", return_value=gauge), \
                    patch.object(_tmd9, "wilson_flow",
                                 side_effect=encode_flow), \
                    patch.object(
                        _tmd9, "flow_action_density",
                        return_value=np.ones(gauge.shape[:4])):
                actual = _tmd9.flow_gauge_for_config(
                    7, tau=3.0, eps=0.05, precision="complex128",
                    save_dir=save_dir, logger=None, save_gauge=True)
                self.assertEqual(legacy.read_bytes(), before)
                files = _cache_files(save_dir, "flowed_gauge_")

        self.assertEqual(len(calls), 1)
        self.assertEqual(
            float(np.real(actual[0, 0, 0, 0, 0, 0, 0])), 2.0)
        self.assertEqual(len(files), 2)

    def test_nonflat_zr_controls_long_distance_instead_of_bare_ratio(self):
        """非平坦 Z_R 必须改变锚点之后的长距点，且广播到 sample、b。"""
        z, zr_fit, c0_pz, c0_pz0 = _fixture()
        actual = tmd_renormalize_hybrid(
            c0_pz, c0_pz0, z, z_s=0.25, zr_fit=zr_fit)
        expected = np.array([
            [[0.5, 2.0], [0.5, 1.5], [0.3, 0.4], [0.2, 0.3]],
            [[0.5, 0.5], [0.75, 0.75], [0.5, 0.75], [0.3125, 0.5]],
        ])
        bare_ratio = c0_pz / c0_pz0

        formula_error = float(np.max(np.abs(actual - expected)))
        bare_separation = float(np.max(
            np.abs(actual[:, 2:, :] - bare_ratio[:, 2:, :])))
        ERRORS["literal_formula"] = formula_error
        ERRORS["bare_ratio_separation"] = bare_separation
        self.assertEqual(actual.shape, c0_pz.shape)
        self.assertLess(formula_error, 1e-15)
        self.assertGreater(bare_separation, 0.09)

    def test_matches_verified_hybrid_formula_pointwise(self):
        """三维管线布局须逐 sample、逐 b 等于 renorm._hybrid.hR_z_Pz。"""
        z, zr_fit, c0_pz, c0_pz0 = _fixture()
        actual = tmd_renormalize_hybrid(
            c0_pz, c0_pz0, z, z_s=0.25, zr_fit=zr_fit)
        expected = _reference_pointwise(
            c0_pz, c0_pz0, z, zr_fit, z_s=0.25)

        error = float(np.max(np.abs(actual - expected)))
        ERRORS["reference_pointwise"] = error
        self.assertLess(error, 1e-15)

    def test_switch_accepts_both_grid_boundaries(self):
        """z_s 可取网格两端；锚点固定为首个 z_i >= z_s。"""
        z, zr_fit, c0_pz, c0_pz0 = _fixture()
        for label, z_s in (("lower", z[0]), ("upper", z[-1])):
            with self.subTest(boundary=label):
                actual = tmd_renormalize_hybrid(
                    c0_pz, c0_pz0, z, z_s=z_s, zr_fit=zr_fit)
                expected = _reference_pointwise(
                    c0_pz, c0_pz0, z, zr_fit, z_s=z_s)
                error = float(np.max(np.abs(actual - expected)))
                ERRORS[f"boundary_{label}"] = error
                self.assertLess(error, 1e-15)

    def test_rejects_invalid_shapes_nonfinite_values_and_switches(self):
        """三维布局、一维 Z_R、有限输入和有效 z_s 区间均为硬边界。"""
        z, zr_fit, c0_pz, c0_pz0 = _fixture()

        c0_nan = c0_pz.copy()
        c0_nan[0, 0, 0] = np.nan
        c00_inf = c0_pz0.copy()
        c00_inf[0, 0, 0] = np.inf
        z_nan = z.copy()
        z_nan[1] = np.nan
        zr_nan = zr_fit.copy()
        zr_nan[2] = np.nan
        c00_short_zero = c0_pz0.copy()
        c00_short_zero[0, 0, 0] = 0.0
        c00_switch_zero = c0_pz0.copy()
        c00_switch_zero[0, 2, 0] = 0.0
        zr_long_zero = zr_fit.copy()
        zr_long_zero[3] = 0.0

        cases = {
            "c0_not_3d": (c0_pz[0], c0_pz0[0], z, zr_fit, 0.25),
            "c0_shape_mismatch": (c0_pz, c0_pz0[:, :-1], z, zr_fit, 0.25),
            "empty_sample_axis": (c0_pz[:0], c0_pz0[:0], z, zr_fit, 0.25),
            "z_wrong_length": (c0_pz, c0_pz0, z[:-1], zr_fit, 0.25),
            "z_not_1d": (c0_pz, c0_pz0, z[:, None], zr_fit, 0.25),
            "z_not_strictly_increasing": (
                c0_pz, c0_pz0, z[[0, 2, 1, 3]], zr_fit, 0.25),
            "zr_wrong_shape": (c0_pz, c0_pz0, z, zr_fit[:, None], 0.25),
            "c0_nonfinite": (c0_nan, c0_pz0, z, zr_fit, 0.25),
            "c00_nonfinite": (c0_pz, c00_inf, z, zr_fit, 0.25),
            "z_nonfinite": (c0_pz, c0_pz0, z_nan, zr_fit, 0.25),
            "zr_nonfinite": (c0_pz, c0_pz0, z, zr_nan, 0.25),
            "zs_nonfinite": (c0_pz, c0_pz0, z, zr_fit, np.nan),
            "zs_below_grid": (c0_pz, c0_pz0, z, zr_fit, 0.09),
            "zs_above_grid": (c0_pz, c0_pz0, z, zr_fit, 0.41),
            "short_denominator_zero": (
                c0_pz, c00_short_zero, z, zr_fit, 0.25),
            "switch_denominator_zero": (
                c0_pz, c00_switch_zero, z, zr_fit, 0.25),
            "long_zr_zero": (c0_pz, c0_pz0, z, zr_long_zero, 0.25),
        }
        for name, (c0, c00, z_values, zr, z_s) in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    tmd_renormalize_hybrid(
                        c0, c00, z_values, z_s=z_s, zr_fit=zr)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        TmdHybridContract)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print("numeric errors:")
    for name, value in sorted(ERRORS.items()):
        print(f"  {name}: {value:.3e}")
    raise SystemExit(0 if result.wasSuccessful() else 1)
