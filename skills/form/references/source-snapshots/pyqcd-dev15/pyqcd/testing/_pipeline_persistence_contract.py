"""Pipeline filesystem-side-effect and persistence regression contracts.

The focused module remains directly runnable and is also aggregated by the
public ``pyqcd.testing`` regression entrypoint.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import h5py
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_SOURCE = PROJECT_ROOT / "pyqcd" / "pipeline" / "_config.py"
TMD_WORKFLOW_SOURCE = (
    PROJECT_ROOT / "pyqcd" / "testing" / "tmd" / "pdf_workflow.py"
)
EXPECTED_NT = 72
CHANNELS = ("pp", "pn", "pion")
MOMENTA = ("P0", "P2")


def _isolated_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.fspath(root)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _assert_subprocess_ok(completed: subprocess.CompletedProcess[str]) -> None:
    assert completed.returncode == 0, (
        f"subprocess failed with rc={completed.returncode}\n"
        f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )


def test_config_import_does_not_create_output_trees():
    """Importing pipeline configuration must be a read-only operation."""
    with tempfile.TemporaryDirectory() as tmp:
        isolated_root = Path(tmp) / "project"
        target_dir = isolated_root / "pyqcd" / "pipeline"
        target_dir.mkdir(parents=True)
        target = target_dir / "_config.py"
        shutil.copy2(CONFIG_SOURCE, target)

        code = (
            "import importlib.util\n"
            f"spec = importlib.util.spec_from_file_location('isolated_config', {str(target)!r})\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(module)\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=isolated_root,
            env=_isolated_env(isolated_root),
            text=True,
            capture_output=True,
        )
        _assert_subprocess_ok(completed)

        created = [
            name for name in ("data", "plots", "logs", "output")
            if (isolated_root / name).exists()
        ]
        assert created == [], f"config import created directories: {created}"


def test_parallel_cli_dry_run_does_not_create_output_trees():
    """The documented MPI planning dry-run must not persist directories."""
    with tempfile.TemporaryDirectory() as tmp:
        isolated_root = Path(tmp)
        (isolated_root / "pyqcd").symlink_to(
            PROJECT_ROOT / "pyqcd", target_is_directory=True)

        completed = subprocess.run(
            [sys.executable, "-m", "pyqcd.parallel", "--dry-run",
             "--confs", "6250,6450", "--n-gpu", "0"],
            cwd=isolated_root,
            env=_isolated_env(isolated_root),
            text=True,
            capture_output=True,
        )
        _assert_subprocess_ok(completed)

        created = [
            name for name in ("data", "plots", "logs", "output")
            if (isolated_root / name).exists()
        ]
        assert created == [], f"parallel dry-run created directories: {created}"


def test_tmd_workflow_dry_run_does_not_create_output_trees():
    """The TMD dry-run must report its plan without creating output trees."""
    with tempfile.TemporaryDirectory() as tmp:
        isolated_root = Path(tmp)
        output = isolated_root / "not-created"

        completed = subprocess.run(
            [sys.executable, "-m", "pyqcd.testing.tmd.pdf_workflow",
             "--dry-run", "--out", os.fspath(output)],
            cwd=PROJECT_ROOT,
            env=_isolated_env(PROJECT_ROOT),
            text=True,
            capture_output=True,
        )
        _assert_subprocess_ok(completed)

        assert not output.exists(), (
            f"TMD dry-run created output directory: {output}"
        )


def test_tmd_workflow_analysis_forwards_tmd_cache_identity():
    """Analysis must request the exact flow cache produced by computation."""
    spec = importlib.util.spec_from_file_location(
        "pipeline_persistence_tmd", TMD_WORKFLOW_SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    captured = {}
    captured_2pt = {}
    logger = lambda *_args: None
    args = SimpleNamespace(staple_length=9, precision="complex128")

    def capture_loader(run_dir, conf_ids, z_list, b_list, **kwargs):
        captured.update({
            "run_dir": run_dir,
            "conf_ids": conf_ids,
            "z_list": z_list,
            "b_list": b_list,
            "kwargs": kwargs,
        })
        return {}

    def capture_2pt(run_dir, conf_ids, momentum_tags, **kwargs):
        captured_2pt.update({
            "run_dir": run_dir,
            "conf_ids": conf_ids,
            "momentum_tags": momentum_tags,
            "kwargs": kwargs,
        })
        return {}

    with tempfile.TemporaryDirectory() as tmp, \
            patch.object(module, "TAU", 1.75), \
            patch.object(module, "EPS", 0.025), \
            patch.object(module, "load_multi_2pt",
                         side_effect=capture_2pt), \
            patch("pyqcd.pipeline._tmd9.load_tmd_ope_all",
                  side_effect=capture_loader), \
            patch.object(module, "run_tmd_pdf_chain"), \
            patch.object(module, "write_summary"):
        momenta = ((10, -2, 0),)
        module.run_analysis([6250], momenta, tmp, logger, args)

    assert captured_2pt == {
        "run_dir": tmp,
        "conf_ids": [6250],
        "momentum_tags": ["P10_-2_0"],
        "kwargs": {
            "channels": ("pp",),
            "logger": logger,
            "momenta": momenta,
            "precision": "complex128",
        },
    }

    assert captured["run_dir"] == tmp
    assert captured["conf_ids"] == [6250]
    assert captured["z_list"] == module.Z_LIST
    assert captured["b_list"] == module.B_LIST
    assert captured["kwargs"] == {
        "logger": logger,
        "staple_length": 9,
        "tau": 1.75,
        "eps": 0.025,
        "precision": "complex128",
    }


def test_tmd_workflow_smoke_uses_exactly_the_requested_single_momentum():
    """公开 --smoke-mom 不能是无效参数，smoke 必须只选择一个动量。"""
    spec = importlib.util.spec_from_file_location(
        "pipeline_persistence_tmd_scope", TMD_WORKFLOW_SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    args = SimpleNamespace(
        smoke=True, smoke_mom="P10_-2_0", conf_ids=None, momenta="Z")
    conf_ids, momenta = module.select_run_scope(args)
    assert conf_ids == [6250]
    assert momenta == [(10, -2, 0)]


def test_tmd_workflow_pdf_inputs_require_longitudinal_verified_samples():
    """PDF 链不得消费无状态二维均值或带横向动量的伪输入。"""
    spec = importlib.util.spec_from_file_location(
        "pipeline_persistence_tmd_pdf", TMD_WORKFLOW_SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    messages = []
    with tempfile.TemporaryDirectory() as tmpdir:
        analysis_dir = Path(tmpdir) / "analysis"
        analysis_dir.mkdir()
        sample_plateau = np.array([
            [[2.0], [1.0]],
            [[2.2], [1.1]],
            [[1.8], [0.9]],
        ])

        # P200: numeric artifact exists but its status is absent.
        np.save(analysis_dir / "c0_plateau_P200.npy", sample_plateau)
        # P400: the only fully verified longitudinal input.
        np.save(analysis_dir / "c0_plateau_P400.npy", sample_plateau)
        np.savez(
            analysis_dir / "c0_plateau_status_P400.npz",
            plateau_status=np.asarray("identifiable"),
        )
        # P10_-2_0: valid status/data, but py != 0 so not a z-momentum TMD.
        np.save(analysis_dir / "c0_plateau_P10_-2_0.npy", sample_plateau)
        np.savez(
            analysis_dir / "c0_plateau_status_P10_-2_0.npz",
            plateau_status=np.asarray("identifiable"),
        )
        # P600: status exists but a 2-D mean is not a resampled input.
        np.save(analysis_dir / "c0_plateau_P600.npy", sample_plateau.mean(0))
        np.savez(
            analysis_dir / "c0_plateau_status_P600.npz",
            plateau_status=np.asarray("identifiable"),
        )

        actual = module.load_verified_plateau_inputs(
            analysis_dir,
            [(2, 0, 0), (4, 0, 0), (10, -2, 0), (6, 0, 0)],
            logger=messages.append,
        )

    assert set(actual) == {"P400"}
    assert actual["P400"]["pz_lattice"] == 4
    assert actual["P400"]["hR"].shape == (2, 1)
    assert any("status" in message and "unavailable" in message
               for message in messages)
    assert any("longitudinal" in message for message in messages)
    assert any("sample" in message and "shape" in message
               for message in messages)


def _capturing_allocator(calls: list[str], run_dir: Path):
    def reserve(output_root, tag=None):
        calls.append(os.fspath(output_root))
        run_dir.mkdir()
        return os.fspath(run_dir)

    return reserve


def test_runner_default_root_tracks_config_output_dir():
    """Changing the canonical config root must affect the public runner."""
    from pyqcd.pipeline import _config, _runner

    with tempfile.TemporaryDirectory() as tmp:
        canonical = Path(tmp) / "canonical-output"
        run_dir = Path(tmp) / "runner-run"
        calls: list[str] = []
        with patch.object(_config, "OUTPUT_DIR", os.fspath(canonical)), \
                patch.object(
                    _runner, "reserve_unique_run_dir",
                    side_effect=_capturing_allocator(calls, run_dir)):
            actual = _runner.make_run_dir()

        assert actual == os.fspath(run_dir)
        assert calls == [os.fspath(canonical)], calls


def test_direct_serial_default_root_tracks_config_output_dir():
    """The direct serial implementation must consume the canonical root."""
    from pyqcd.pipeline import _config, _steps

    with tempfile.TemporaryDirectory() as tmp:
        canonical = Path(tmp) / "canonical-output"
        run_dir = Path(tmp) / "serial-run"
        calls: list[str] = []
        with patch.object(_config, "OUTPUT_DIR", os.fspath(canonical)), \
                patch.object(
                    _steps, "reserve_unique_run_dir",
                    side_effect=_capturing_allocator(calls, run_dir)):
            result = _steps.run_pipeline(
                steps=(), conf_ids=[6250], logger=None, backend="numpy")

        assert result["run_dir"] == os.fspath(run_dir)
        assert calls == [os.fspath(canonical)], calls


def test_single_rank_parallel_fallback_tracks_config_output_dir():
    """Single-rank MPI fallback must inherit the serial canonical root."""
    from pyqcd.parallel import _mpi
    from pyqcd.pipeline import _config, _steps

    plan = {"n_gpu": 0, "N": 1, "m": 1, "X": 1}
    with tempfile.TemporaryDirectory() as tmp:
        canonical = Path(tmp) / "canonical-output"
        run_dir = Path(tmp) / "single-rank-run"
        calls: list[str] = []
        with patch.object(_config, "OUTPUT_DIR", os.fspath(canonical)), \
                patch.object(_mpi, "get_mpi_context",
                             return_value=(None, 0, 1)), \
                patch.object(
                    _steps, "reserve_unique_run_dir",
                    side_effect=_capturing_allocator(calls, run_dir)):
            result, actual_plan = _mpi.run_parallel_pipeline(
                steps=(), conf_ids=[6250], logger=None, backend="numpy",
                resources={"provided": True}, plan=plan)

        assert result["run_dir"] == os.fspath(run_dir)
        assert actual_plan is plan
        assert calls == [os.fspath(canonical)], calls


def test_save_array_failure_preserves_previous_file_atomically():
    """An interrupted HDF5 write must not expose a partial final file."""
    from pyqcd.pipeline import _steps

    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        destination = directory / "corr_pp_P0_7.h5"
        original = np.arange(8, dtype=np.float64)
        _steps.save_array(destination, original)
        original_bytes = destination.read_bytes()
        writer_paths: list[Path] = []

        def interrupted_writer(_array, file_path):
            writer_path = Path(file_path)
            writer_paths.append(writer_path)
            writer_path.write_bytes(b"partial-hdf5")
            raise RuntimeError("simulated interrupted write")

        with patch.object(_steps, "save_tensor_h5",
                          side_effect=interrupted_writer):
            try:
                _steps.save_array(destination, original + 1)
            except RuntimeError as exc:
                assert str(exc) == "simulated interrupted write"
            else:
                raise AssertionError("interrupted HDF5 write did not propagate")

        assert writer_paths and writer_paths[0] != destination, writer_paths
        assert writer_paths[0].parent == destination.parent
        assert destination.read_bytes() == original_bytes
        with h5py.File(destination, "r") as handle:
            assert np.array_equal(handle["data"][...], original)
        assert list(directory.iterdir()) == [destination]


def test_save_array_success_is_readable_without_temporary_files():
    """A successful atomic save must leave one canonical readable HDF5."""
    from pyqcd.pipeline import _steps

    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        destination = directory / "corr_pp_P0_7.h5"
        expected = np.arange(8, dtype=np.float64)
        _steps.save_array(destination, expected)

        with h5py.File(destination, "r") as handle:
            assert np.array_equal(handle["data"][...], expected)
        assert list(directory.iterdir()) == [destination]


def test_save_array_cleanup_failure_preserves_primary_write_exception():
    """Temporary-file cleanup must never replace the actual write failure."""
    from pyqcd.pipeline import _steps

    primary = RuntimeError("primary HDF5 write failure")
    with tempfile.TemporaryDirectory() as tmp, \
            patch.object(_steps, "save_tensor_h5", side_effect=primary), \
            patch.object(_steps.os, "unlink",
                         side_effect=OSError("temporary cleanup failure")):
        try:
            _steps.save_array(Path(tmp) / "artifact.h5", np.arange(3.0))
        except RuntimeError as exc:
            assert exc is primary
        else:
            raise AssertionError("cleanup failure masked the primary write error")


_OPE_COMPONENTS = ((0, 1), (3, 0), (3, 1))


def _compute_fake_ope(run_dir: Path, gauge_path: Path, *,
                      precision: str = "complex64", z_dir: int = 2,
                      fail_compute: bool = False,
                      read_gauge_side_effect=None,
                      validate_side_effect=None, logger=None):
    """Run the persistence path with tiny deterministic OPE component data."""
    from pyqcd.pipeline import _steps
    from pyqcd.tools import set_backend

    set_backend("numpy")
    gauge = np.zeros((2, 1, 1, 1, 4, 3, 3), dtype=np.complex128)
    calls = []

    def fake_channel(_gauge, spec, delta_z, nt, nx, compute_dtype,
                     **_kwargs):
        dtype_name = np.dtype(compute_dtype).name
        calls.append(((spec.mu, spec.nu), spec.z_dir, dtype_name, nt, nx))
        component_index = _OPE_COMPONENTS.index((spec.mu, spec.nu)) + 1
        precision_offset = 100.0 if dtype_name == "complex128" else 0.0
        value = precision_offset + 10.0 * spec.z_dir + component_index
        return np.full((delta_z, nt), value, dtype=np.dtype(compute_dtype))

    read_side_effect = (AssertionError("strict OPE cache unexpectedly missed")
                        if fail_compute else read_gauge_side_effect)
    channel_side_effect = (AssertionError("strict OPE cache recomputed")
                           if fail_compute else fake_channel)
    with patch.object(_steps, "HAS_CUPY", True), \
            patch.object(_steps, "NT", 2), \
            patch.object(_steps, "NX", 1), \
            patch.object(_steps, "get_gauge_path",
                         return_value=os.fspath(gauge_path)), \
            patch.object(_steps, "read_gauge_lime",
                         side_effect=read_side_effect,
                         return_value=gauge), \
            patch.object(_steps, "_validate_gauge",
                         side_effect=validate_side_effect), \
            patch.object(_steps, "gluon_ope_channel",
                         side_effect=channel_side_effect), \
            patch.object(_steps, "free_gpu_memory"), \
            patch.object(_steps, "log_gpu_memory"):
        result = _steps.compute_ope_for_config(
            7, run_dir, logger=logger, precision=precision,
            delta_z=2, z_dir=z_dir, components=_OPE_COMPONENTS)
    return result, calls


def _ope_artifact_paths(run_dir: Path, conf_id: int = 7,
                        delta_z: int = 2) -> list[Path]:
    cdir = run_dir / "data" / f"conf{conf_id}"
    return [
        cdir / f"ops_mu{mu}_nu{nu}_dz{delta_z}_conf{conf_id}.h5"
        for mu, nu in _OPE_COMPONENTS
    ] + [cdir / f"ope_combined_conf{conf_id}.h5"]


def _stat_fingerprint(path: Path) -> tuple[int, int, int, int, int]:
    stat = path.stat()
    return (stat.st_dev, stat.st_ino, stat.st_size,
            stat.st_mtime_ns, stat.st_ctime_ns)


def _rewrite_in_place(path: Path, payload: bytes) -> None:
    """Change file contents without replacing the directory entry."""
    before = path.stat()
    assert len(payload) == before.st_size
    path.write_bytes(payload)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))
    after = path.stat()
    assert _stat_fingerprint(path) != _stat_fingerprint_from_stat(before)
    assert after.st_size == before.st_size


def _stat_fingerprint_from_stat(stat) -> tuple[int, int, int, int, int]:
    return (stat.st_dev, stat.st_ino, stat.st_size,
            stat.st_mtime_ns, stat.st_ctime_ns)


def _fake_ope_cache_specs(run_dir: Path, gauge_path: Path, result):
    """Rebuild the exact production spec for a previously written fixture."""
    from pyqcd.pipeline import _steps

    cdir = run_dir / "data" / "conf7"
    paths = {
        component: cdir / (
            f"ops_mu{component[0]}_nu{component[1]}_dz2_conf7")
        for component in _OPE_COMPONENTS
    }
    combined_path = cdir / "ope_combined_conf7"
    with patch.object(_steps, "NT", 2), patch.object(_steps, "NX", 1):
        return _steps._ope_cache_specs(
            7, paths, combined_path, "complex64", 2, 2,
            result["channel_specs"], result["combined_spec"], gauge_path)


def _h5_attrs_snapshot(paths: list[Path]):
    snapshot = {}
    for path in paths:
        with h5py.File(path, "r") as handle:
            attrs = {}
            for key, value in handle.attrs.items():
                if isinstance(value, np.ndarray):
                    attrs[key] = value.copy()
                else:
                    attrs[key] = value
            snapshot[path] = attrs
    return snapshot


def _assert_h5_attrs_unchanged(before, paths: list[Path]) -> None:
    after = _h5_attrs_snapshot(paths)
    assert after.keys() == before.keys()
    for path in paths:
        assert after[path].keys() == before[path].keys()
        for key, expected in before[path].items():
            actual = after[path][key]
            if isinstance(expected, np.ndarray):
                np.testing.assert_array_equal(actual, expected)
            else:
                assert actual == expected


def _assert_source_change_was_rejected(error, result, context: str) -> None:
    if error is not None:
        message = str(error).lower()
        assert any(token in message for token in
                   ("gauge", "source", "组态", "规范")), message
        assert any(token in message for token in
                   ("change", "changed", "identity", "stat", "变化", "变更")), \
            message
    else:
        assert result is None, (
            f"gauge source changed during {context}, but computation "
            "returned a result instead of a conservative miss")


def test_ope_cache_resolves_lime_contents_record_for_read_and_identity():
    """A contents directory must read and identify its canonical record."""
    from pyqcd.operator._gluon_ope import _resolve_ildg_binary_record
    from pyqcd.pipeline import _steps

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "run"
        contents = root / "gauge.lime.contents"
        contents.mkdir()
        record = contents / "msg02.rec04.ildg-binary-data"
        record.write_bytes(b"record-v1")
        read_paths = []

        def fake_reader(filepath, *_args):
            resolved = Path(_resolve_ildg_binary_record(filepath))
            read_paths.append(resolved)
            return np.zeros((2, 1, 1, 1, 4, 3, 3), dtype=np.complex128)

        _compute_fake_ope(
            run_dir, contents, read_gauge_side_effect=fake_reader)

        assert read_paths == [record]
        identity = _steps._gauge_source_identity(contents)
        assert identity["path"] == os.path.realpath(record), identity
        assert identity["stat_available"] is True
        assert identity["size"] == record.stat().st_size


def test_ope_cache_misses_when_lime_contents_record_changes_in_place():
    """Changing only the record must invalidate a cached contents directory."""
    from pyqcd.operator._gluon_ope import _resolve_ildg_binary_record

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "run"
        contents = root / "gauge.lime.contents"
        contents.mkdir()
        record = contents / "msg02.rec04.ildg-binary-data"
        record.write_bytes(b"record-v1")
        read_paths = []

        def fake_reader(filepath, *_args):
            read_paths.append(Path(_resolve_ildg_binary_record(filepath)))
            return np.zeros((2, 1, 1, 1, 4, 3, 3), dtype=np.complex128)

        _compute_fake_ope(
            run_dir, contents, read_gauge_side_effect=fake_reader)
        directory_stat = _stat_fingerprint(contents)
        _rewrite_in_place(record, b"record-v2")
        assert _stat_fingerprint(contents) == directory_stat

        _, calls = _compute_fake_ope(
            run_dir, contents, read_gauge_side_effect=fake_reader)

        assert calls == [
            ((0, 1), 2, "complex64", 2, 1),
            ((3, 0), 2, "complex64", 2, 1),
            ((3, 1), 2, "complex64", 2, 1),
        ], calls
        assert read_paths == [record, record]


def test_ope_cache_rechecks_gauge_stat_before_returning_cache_hit():
    """A source mutation during cache reads cannot become a cache hit."""
    from pyqcd.pipeline import _steps

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "run"
        gauge_path = root / "gauge.lime"
        gauge_path.write_bytes(b"source-v1")
        fresh, _ = _compute_fake_ope(run_dir, gauge_path)
        specs = _fake_ope_cache_specs(run_dir, gauge_path, fresh)
        artifacts = _ope_artifact_paths(run_dir)
        artifact_snapshot = {
            path: (path.read_bytes(), _stat_fingerprint(path))
            for path in artifacts
        }

        original_loader = _steps._load_strict_cache_mapping

        def mutate_during_cache_read(
                specs_arg, logger, payload_sha_attr=None):
            _rewrite_in_place(gauge_path, b"source-v2")
            return original_loader(
                specs_arg, logger, payload_sha_attr=payload_sha_attr)

        messages = []
        error = None
        cached = None
        try:
            with patch.object(
                    _steps, "_load_strict_cache_mapping",
                    side_effect=mutate_during_cache_read):
                cached = _steps._load_strict_ope_cache(
                    specs, _OPE_COMPONENTS, fresh["channel_specs"],
                    fresh["combined_spec"], messages.append)
        except Exception as exc:
            error = exc

        _assert_source_change_was_rejected(error, cached, "strict-cache read")
        for path, (payload, stat) in artifact_snapshot.items():
            assert path.read_bytes() == payload
            assert _stat_fingerprint(path) == stat


def test_ope_cache_rechecks_gauge_stat_after_fresh_reader_before_publish():
    """A source mutation after the reader returns must publish no OPE files."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "run"
        gauge_path = root / "gauge.lime"
        gauge_path.write_bytes(b"source-v1")

        def mutate_after_reader(_gauge, _logger):
            _rewrite_in_place(gauge_path, b"source-v2")

        result = None
        error = None
        try:
            result, _calls = _compute_fake_ope(
                run_dir, gauge_path,
                validate_side_effect=mutate_after_reader)
        except Exception as exc:
            error = exc

        _assert_source_change_was_rejected(error, result, "fresh reader path")
        assert not any(path.exists()
                       for path in _ope_artifact_paths(run_dir))


def test_ope_publish_detects_source_change_after_last_precheck():
    """A source change at the first final replace must not return success."""
    from pyqcd.pipeline import _steps

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "run"
        gauge_path = root / "gauge.lime"
        gauge_path.write_bytes(b"source-v1")
        final_paths = {
            os.fspath(path) for path in _ope_artifact_paths(run_dir)
        }
        original_replace = _steps.os.replace
        changed = False

        def mutate_at_first_final_replace(source, destination):
            nonlocal changed
            if os.fspath(destination) in final_paths and not changed:
                _rewrite_in_place(gauge_path, b"source-v2")
                changed = True
            return original_replace(source, destination)

        result = None
        error = None
        try:
            with patch.object(
                    _steps.os, "replace",
                    side_effect=mutate_at_first_final_replace):
                result, _calls = _compute_fake_ope(run_dir, gauge_path)
        except Exception as exc:
            error = exc

        assert changed, "test did not reach the final OPE publication path"
        _assert_source_change_was_rejected(
            error, result, "post-publication source check")

        # Already-published files carry the old source contract, so a later
        # strict request for the changed source must recompute rather than hit.
        _fresh, calls = _compute_fake_ope(run_dir, gauge_path)
        assert len(calls) == len(_OPE_COMPONENTS)


def test_ope_cache_rejects_coherent_payload_mutation_with_unchanged_attrs():
    """Coherent O01/combined payload edits still fail the payload SHA gate."""
    from pyqcd.pipeline import _steps

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "run"
        gauge_path = root / "gauge.lime"
        gauge_path.write_bytes(b"source-v1")
        fresh, _ = _compute_fake_ope(run_dir, gauge_path)
        specs = _fake_ope_cache_specs(run_dir, gauge_path, fresh)
        artifacts = _ope_artifact_paths(run_dir)
        attrs_before = _h5_attrs_snapshot(artifacts)
        o01_path = artifacts[_OPE_COMPONENTS.index((0, 1))]
        combined_path = artifacts[-1]

        with h5py.File(o01_path, "r+") as o01_handle, \
                h5py.File(combined_path, "r+") as combined_handle:
            delta = np.full_like(o01_handle["data"][...], 3.0)
            o01_handle["data"][...] += delta
            combined_handle["data"][...] += 2.0 * delta

        _assert_h5_attrs_unchanged(attrs_before, artifacts)
        with h5py.File(artifacts[1], "r") as o30_handle, \
                h5py.File(artifacts[2], "r") as o31_handle, \
                h5py.File(o01_path, "r") as o01_handle, \
                h5py.File(combined_path, "r") as combined_handle:
            expected = (-o30_handle["data"][...]
                        - o31_handle["data"][...]
                        + 2.0 * o01_handle["data"][...])
            np.testing.assert_array_equal(expected, combined_handle["data"][...])

        loaded = _steps._load_strict_ope_cache(
            specs, _OPE_COMPONENTS, fresh["channel_specs"],
            fresh["combined_spec"], logger=None)
        assert loaded is None, (
            "strict OPE loader accepted a coherent data-payload mutation "
            "with unchanged attrs")


def test_load_ope_reports_stale_canonical_source_without_rejecting_data():
    """Historical OPE data remain loadable, but stale provenance is explicit."""
    from pyqcd.pipeline import _steps

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "run"
        gauge_path = root / "gauge.lime"
        gauge_path.write_bytes(b"source-v1")

        fresh, _calls = _compute_fake_ope(run_dir, gauge_path)
        combined_path = (
            run_dir / "data" / "conf7" / "ope_combined_conf7.h5")
        required_attrs = {
            _steps._STRICT_CONTRACT_JSON_ATTR,
            _steps._STRICT_CONTRACT_SHA_ATTR,
            _steps._OPE_PAYLOAD_SHA_ATTR,
            _steps._OPE_METADATA_SCHEMA_ATTR,
            _steps._OPE_CHANNEL_SPECS_ATTR,
            _steps._OPE_COMBINED_SPEC_ATTR,
        }
        with h5py.File(combined_path, "r") as handle:
            assert required_attrs <= set(handle.attrs)

        _rewrite_in_place(gauge_path, b"source-v2")
        messages = []
        with patch.object(
                _steps, "get_gauge_path",
                return_value=os.fspath(gauge_path)):
            loaded = _steps.load_ope(run_dir, messages.append)

        entry = loaded[7]
        assert entry["metadata_status"] == "stale", entry
        assert entry["source_identity_status"] == "stale", entry
        np.testing.assert_array_equal(entry["combined"], fresh["combined"])
        assert entry["channel_specs"] == fresh["channel_specs"]
        assert entry["combined_spec"] == fresh["combined_spec"]
        assert any(
            "stale" in message.lower()
            and "gauge source identity" in message.lower()
            for message in messages
        ), messages


def test_ope_cache_validates_payload_in_the_same_strict_load():
    """OPE payload hash must cover the exact array returned by one file read."""
    from pyqcd.pipeline import _steps

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "run"
        gauge_path = root / "gauge.lime"
        gauge_path.write_bytes(b"source-v1")
        fresh, _ = _compute_fake_ope(run_dir, gauge_path)
        specs = _fake_ope_cache_specs(run_dir, gauge_path, fresh)

        # A second reopen can hash bytes different from the already-loaded
        # return array and also doubles payload I/O.  The OPE strict mapping
        # must perform contract, payload hash and array loading together.
        with patch.object(
                _steps, "_validate_ope_payload_digests", create=True,
                side_effect=AssertionError(
                    "strict OPE payload was reopened for a second read")):
            loaded = _steps._load_strict_ope_cache(
                specs, _OPE_COMPONENTS, fresh["channel_specs"],
                fresh["combined_spec"], logger=None)

        assert loaded is not None
        np.testing.assert_array_equal(loaded["combined"], fresh["combined"])


def test_ope_cache_reuses_only_complete_strict_artifact_set():
    """All components and combined output need one exact cache contract."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "run"
        gauge_path = root / "gauge.lime"
        gauge_path.write_bytes(b"gauge-source-v1")

        fresh, calls = _compute_fake_ope(run_dir, gauge_path)
        assert len(calls) == len(_OPE_COMPONENTS)
        cached, cached_calls = _compute_fake_ope(
            run_dir, gauge_path, fail_compute=True)

        assert cached_calls == []
        assert cached["metadata_status"] == "validated"
        np.testing.assert_array_equal(cached["combined"], fresh["combined"])
        cdir = run_dir / "data" / "conf7"
        artifact_paths = [
            cdir / f"ops_mu{mu}_nu{nu}_dz2_conf7.h5"
            for mu, nu in _OPE_COMPONENTS
        ] + [cdir / "ope_combined_conf7.h5"]
        for path in artifact_paths:
            with h5py.File(path, "r") as handle:
                assert set(handle.keys()) == {"data"}
                assert "pyqcd_cache_contract_json" in handle.attrs
                assert "pyqcd_cache_contract_sha256" in handle.attrs


def test_ope_cache_misses_when_physics_identity_changes():
    """Precision, Wilson-line axis, and gauge source identity affect values."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "run"
        gauge_path = root / "gauge.lime"
        gauge_path.write_bytes(b"gauge-source-v1")

        _compute_fake_ope(run_dir, gauge_path, precision="complex64", z_dir=2)
        _, precision_calls = _compute_fake_ope(
            run_dir, gauge_path, precision="complex128", z_dir=2)
        _, direction_calls = _compute_fake_ope(
            run_dir, gauge_path, precision="complex128", z_dir=1)
        gauge_path.write_bytes(b"gauge-source-v2-with-different-size")
        _, source_calls = _compute_fake_ope(
            run_dir, gauge_path, precision="complex128", z_dir=1)

        assert len(precision_calls) == len(_OPE_COMPONENTS)
        assert len(direction_calls) == len(_OPE_COMPONENTS)
        assert len(source_calls) == len(_OPE_COMPONENTS)


def test_ope_cache_never_hits_when_gauge_source_identity_is_unavailable():
    """A path-only unavailable source is insufficient for scientific reuse."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "run"
        unavailable_gauge = root / "missing-gauge.lime"

        _compute_fake_ope(run_dir, unavailable_gauge)
        _, calls = _compute_fake_ope(run_dir, unavailable_gauge)
        assert len(calls) == len(_OPE_COMPONENTS)


def test_ope_cache_rejects_combined_data_inconsistent_with_components():
    """Valid attrs alone cannot bless a combined array with altered values."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "run"
        gauge_path = root / "gauge.lime"
        gauge_path.write_bytes(b"gauge-source-v1")
        _compute_fake_ope(run_dir, gauge_path)

        combined_path = (
            run_dir / "data" / "conf7" / "ope_combined_conf7.h5"
        )
        with h5py.File(combined_path, "r+") as handle:
            handle["data"][...] += 1.0

        repaired, calls = _compute_fake_ope(run_dir, gauge_path)
        assert len(calls) == len(_OPE_COMPONENTS)
        expected = (
            -repaired["components"][(3, 0)]
            - repaired["components"][(3, 1)]
            + 2.0 * repaired["components"][(0, 1)]
        )
        np.testing.assert_array_equal(repaired["combined"], expected)


def test_ope_metadata_present_with_nontext_attrs_is_invalid_not_missing():
    """Present attrs with the wrong HDF5 type are malformed, not legacy."""
    from pyqcd.pipeline import _steps

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ope_combined_conf7.h5"
        with h5py.File(path, "w") as handle:
            handle.create_dataset("data", data=np.zeros((2, 2)))
            handle.attrs["pyqcd_ope_metadata_schema"] = 1
            handle.attrs["pyqcd_ope_channel_specs_json"] = 2
            handle.attrs["pyqcd_ope_combined_spec_json"] = 3

        status, metadata = _steps._read_ope_metadata(path)
        assert status == "invalid"
        assert metadata is None


def _artifact_path(cdir: Path, channel: str, momentum: str,
                   conf_id: int, suffix: str) -> Path:
    return cdir / f"corr_{channel}_{momentum}_{conf_id}{suffix}"


def _write_h5(path: Path, array, dataset: str = "data") -> None:
    with h5py.File(path, "w") as handle:
        handle.create_dataset(dataset, data=array)


def _write_valid_h5_set(cdir: Path, conf_id: int) -> None:
    cdir.mkdir(parents=True, exist_ok=True)
    expected = np.arange(EXPECTED_NT, dtype=np.float64)
    for channel in CHANNELS:
        for momentum in MOMENTA:
            _write_h5(
                _artifact_path(cdir, channel, momentum, conf_id, ".h5"),
                expected,
            )


def _write_valid_npy_set(cdir: Path, conf_id: int) -> None:
    cdir.mkdir(parents=True, exist_ok=True)
    expected = np.arange(EXPECTED_NT, dtype=np.float64)
    for channel in CHANNELS:
        for momentum in MOMENTA:
            np.save(
                _artifact_path(cdir, channel, momentum, conf_id, ".npy"),
                expected,
            )


def test_2pt_resume_accepts_valid_canonical_h5():
    """A complete set of numeric length-Nt HDF5 correlators is reusable."""
    from pyqcd.pipeline import _steps

    with tempfile.TemporaryDirectory() as tmp:
        cdir = Path(tmp) / "conf7"
        _write_valid_h5_set(cdir, 7)
        assert _steps._2pt_all_present(cdir, 7, CHANNELS)


def test_2pt_resume_rejects_invalid_canonical_h5():
    """Broken or noncanonical shape/dtype/schema HDF5 is incomplete."""
    from pyqcd.pipeline import _steps

    def zero_byte(path: Path) -> None:
        path.write_bytes(b"")

    def damaged(path: Path) -> None:
        path.write_bytes(b"not-an-hdf5-file")

    def missing_dataset(path: Path) -> None:
        _write_h5(path, np.arange(EXPECTED_NT), dataset="other")

    def extra_dataset(path: Path) -> None:
        _write_h5(path, np.arange(EXPECTED_NT, dtype=np.float64))
        with h5py.File(path, "r+") as handle:
            handle.create_dataset("unexpected", data=np.zeros(1))

    invalid_cases = (
        ("zero-byte", zero_byte),
        ("damaged", damaged),
        ("missing-data-dataset", missing_dataset),
        ("empty-dataset", lambda path: _write_h5(
            path, np.empty((0,), dtype=np.float64))),
        ("wrong-shape", lambda path: _write_h5(
            path, np.zeros((EXPECTED_NT, 1), dtype=np.float64))),
        ("wrong-numeric-dtype", lambda path: _write_h5(
            path, np.zeros(EXPECTED_NT, dtype=np.float32))),
        ("nonnumeric-dtype", lambda path: _write_h5(
            path, np.full(EXPECTED_NT, b"x", dtype="S1"))),
        ("extra-dataset", extra_dataset),
        ("nan-values", lambda path: _write_h5(
            path, np.full(EXPECTED_NT, np.nan, dtype=np.float64))),
        ("infinite-values", lambda path: _write_h5(
            path, np.full(EXPECTED_NT, np.inf, dtype=np.float64))),
    )

    for label, write_invalid in invalid_cases:
        with tempfile.TemporaryDirectory() as tmp:
            cdir = Path(tmp) / "conf7"
            _write_valid_h5_set(cdir, 7)
            target = _artifact_path(cdir, "pp", "P0", 7, ".h5")
            write_invalid(target)
            assert not _steps._2pt_all_present(cdir, 7, CHANNELS), (
                f"invalid HDF5 was marked complete: {label}"
            )


def test_2pt_resume_does_not_mask_broken_h5_with_legacy_npy():
    """A broken preferred HDF5 must not be hidden by a legacy sibling."""
    from pyqcd.pipeline import _steps

    with tempfile.TemporaryDirectory() as tmp:
        cdir = Path(tmp) / "conf7"
        _write_valid_h5_set(cdir, 7)
        target_h5 = _artifact_path(cdir, "pp", "P0", 7, ".h5")
        target_npy = _artifact_path(cdir, "pp", "P0", 7, ".npy")
        np.save(target_npy, np.arange(EXPECTED_NT, dtype=np.float64))
        target_h5.write_bytes(b"not-an-hdf5-file")

        assert not _steps._2pt_all_present(cdir, 7, CHANNELS)


def test_2pt_resume_accepts_valid_legacy_npy():
    """Readable numeric length-Nt NumPy correlators remain compatible."""
    from pyqcd.pipeline import _steps

    with tempfile.TemporaryDirectory() as tmp:
        cdir = Path(tmp) / "conf7"
        _write_valid_npy_set(cdir, 7)
        assert _steps._2pt_all_present(cdir, 7, CHANNELS)


def test_2pt_resume_rejects_invalid_legacy_npy():
    """Legacy NumPy 也必须满足精确 float64、shape 与有限性契约。"""
    from pyqcd.pipeline import _steps

    invalid_cases = (
        ("unreadable", lambda path: path.write_bytes(b"not-a-npy-file")),
        ("empty", lambda path: np.save(
            path, np.empty((0,), dtype=np.float64))),
        ("wrong-shape", lambda path: np.save(
            path, np.zeros((EXPECTED_NT, 1), dtype=np.float64))),
        ("wrong-numeric-dtype", lambda path: np.save(
            path, np.zeros(EXPECTED_NT, dtype=np.float32))),
        ("nonnumeric-dtype", lambda path: np.save(
            path, np.full(EXPECTED_NT, "x", dtype="U1"))),
        ("nan-values", lambda path: np.save(
            path, np.full(EXPECTED_NT, np.nan, dtype=np.float64))),
        ("infinite-values", lambda path: np.save(
            path, np.full(EXPECTED_NT, np.inf, dtype=np.float64))),
    )

    for label, write_invalid in invalid_cases:
        with tempfile.TemporaryDirectory() as tmp:
            cdir = Path(tmp) / "conf7"
            _write_valid_npy_set(cdir, 7)
            target = _artifact_path(cdir, "pp", "P0", 7, ".npy")
            write_invalid(target)
            assert not _steps._2pt_all_present(cdir, 7, CHANNELS), (
                f"invalid legacy NumPy was marked complete: {label}"
            )


def test_run_pipeline_default_reuses_2pt_cache_and_records_false():
    """入口默认续跑 2pt 缓存，并在配置快照中明确记录 False。"""
    import json

    from pyqcd.pipeline import _steps

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "run"
        _write_valid_h5_set(run_dir / "data" / "conf7", 7)
        with patch.object(
                _steps, "compute_2pt_for_config",
                side_effect=AssertionError(
                    "默认 recompute_2pt=False 不应重算有效缓存")):
            result = _steps.run_pipeline(
                steps=("2pt",), conf_ids=[7], run_dir=run_dir,
                logger=None, backend="numpy")

        assert Path(result["run_dir"]) == run_dir
        with (run_dir / "run_config.json").open(encoding="utf-8") as handle:
            config = json.load(handle)
        assert config["recompute_2pt"] is False


def test_run_pipeline_recompute_2pt_true_forces_recompute_and_records_true():
    """入口显式 True 必须越过有效 2pt 缓存并记录 True。"""
    import json

    from pyqcd.pipeline import _steps

    calls = []

    def fake_compute(conf_id, *_args):
        calls.append(conf_id)
        return {}

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "run"
        _write_valid_h5_set(run_dir / "data" / "conf7", 7)
        with patch.object(
                _steps, "_load_vertices_one",
                return_value={"VdV": None, "VVV": None}), \
                patch.object(_steps, "compute_2pt_for_config",
                             side_effect=fake_compute):
            result = _steps.run_pipeline(
                steps=("2pt",), conf_ids=[7], run_dir=run_dir,
                logger=None, backend="numpy", recompute_2pt=True)

        assert Path(result["run_dir"]) == run_dir
        assert calls == [7]
        with (run_dir / "run_config.json").open(encoding="utf-8") as handle:
            config = json.load(handle)
        assert config["recompute_2pt"] is True


def test_run_pipeline_preflight_failure_has_no_directory_side_effect():
    """失败的显式 preflight 必须发生在目录预留和任何写入之前。"""
    from pyqcd.pipeline import _steps

    observed = {}

    def guard(config, steps):
        observed["config"] = config
        observed["steps"] = tuple(steps)
        return 0, ["conf7: gauge input missing"]

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "must-not-be-created"
        try:
            _steps.run_pipeline(
                steps=("vertex",), conf_ids=[7], run_dir=run_dir,
                logger=None, backend="numpy", preflight=guard)
        except RuntimeError as exc:
            message = str(exc)
        else:
            raise AssertionError("preflight failure was not raised")

        assert not run_dir.exists(), "preflight 失败后不应创建 run_dir"

    assert observed["steps"] == ("vertex",)
    assert observed["config"]["conf_ids"] == [7]
    assert "gauge input missing" in message
    assert "n_ok=0" in message


def test_run_pipeline_successful_preflight_is_recorded_before_steps():
    """成功 guard 的上下文和状态必须进入 run_config 快照。"""
    import json

    from pyqcd.pipeline import _steps

    observed = {}

    def guard(config, steps):
        observed["run_exists"] = os.path.exists(observed["run_dir"])
        observed["steps"] = tuple(steps)
        return len(config["conf_ids"]), []

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "run"
        observed["run_dir"] = run_dir
        result = _steps.run_pipeline(
            steps=(), conf_ids=[7, 8], run_dir=run_dir,
            logger=None, backend="numpy", preflight=guard)

        with (run_dir / "run_config.json").open(encoding="utf-8") as handle:
            config = json.load(handle)

    assert result["run_dir"] == run_dir
    assert observed["run_exists"] is False
    assert observed["steps"] == ()
    assert config["preflight"] == {
        "requested": True,
        "status": "passed",
        "n_ok": 2,
        "bad_list": [],
    }


def test_run_pipeline_env_step_persists_augmented_snapshot_and_result():
    """env 步骤必须落盘 dump_env 结果及非机密运行身份。"""
    import json

    from pyqcd.pipeline import _steps

    base_env = {"git_head": "test-head", "hostname": "test-host"}
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "run"
        with patch.object(
                _steps, "dump_env", return_value=base_env, create=True) as dump:
            result = _steps.run_pipeline(
                steps=("env",), conf_ids=[7], run_dir=run_dir,
                logger=None, backend="numpy", device="cpu",
                precision="complex128")

        dump.assert_called_once_with(os.path.join(os.fspath(run_dir), "env.json"))
        with (run_dir / "env.json").open(encoding="utf-8") as handle:
            env = json.load(handle)

    assert result["env"] == env
    assert env["git_head"] == "test-head"
    assert env["conf_ids"] == [7]
    assert env["precision"] == "complex128"
    assert env["backend"] == "numpy"
    assert env["device"] == "cpu"
    assert env["NT"] == _steps.NT
    assert env["NX"] == _steps.NX
    assert env["gauge_dir"] == os.path.dirname(_steps.get_gauge_path(7))


def test_run_pipeline_without_env_step_does_not_fake_snapshot():
    """省略 env 步骤时既不调用 dump_env，也不返回伪造快照。"""
    from pyqcd.pipeline import _steps

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "run"
        with patch.object(
                _steps, "dump_env", side_effect=AssertionError(
                    "省略 env 时不得调用 dump_env"), create=True):
            result = _steps.run_pipeline(
                steps=(), conf_ids=[7], run_dir=run_dir,
                logger=None, backend="numpy")

        assert not (run_dir / "env.json").exists()

    assert result["env"] is None


TESTS = (
    test_config_import_does_not_create_output_trees,
    test_parallel_cli_dry_run_does_not_create_output_trees,
    test_tmd_workflow_dry_run_does_not_create_output_trees,
    test_tmd_workflow_analysis_forwards_tmd_cache_identity,
    test_tmd_workflow_smoke_uses_exactly_the_requested_single_momentum,
    test_tmd_workflow_pdf_inputs_require_longitudinal_verified_samples,
    test_runner_default_root_tracks_config_output_dir,
    test_direct_serial_default_root_tracks_config_output_dir,
    test_single_rank_parallel_fallback_tracks_config_output_dir,
    test_save_array_failure_preserves_previous_file_atomically,
    test_save_array_success_is_readable_without_temporary_files,
    test_save_array_cleanup_failure_preserves_primary_write_exception,
    test_ope_cache_resolves_lime_contents_record_for_read_and_identity,
    test_ope_cache_misses_when_lime_contents_record_changes_in_place,
    test_ope_cache_rechecks_gauge_stat_before_returning_cache_hit,
    test_ope_cache_rechecks_gauge_stat_after_fresh_reader_before_publish,
    test_ope_publish_detects_source_change_after_last_precheck,
    test_ope_cache_rejects_coherent_payload_mutation_with_unchanged_attrs,
    test_load_ope_reports_stale_canonical_source_without_rejecting_data,
    test_ope_cache_validates_payload_in_the_same_strict_load,
    test_ope_cache_reuses_only_complete_strict_artifact_set,
    test_ope_cache_misses_when_physics_identity_changes,
    test_ope_cache_never_hits_when_gauge_source_identity_is_unavailable,
    test_ope_cache_rejects_combined_data_inconsistent_with_components,
    test_ope_metadata_present_with_nontext_attrs_is_invalid_not_missing,
    test_2pt_resume_accepts_valid_canonical_h5,
    test_2pt_resume_rejects_invalid_canonical_h5,
    test_2pt_resume_does_not_mask_broken_h5_with_legacy_npy,
    test_2pt_resume_accepts_valid_legacy_npy,
    test_2pt_resume_rejects_invalid_legacy_npy,
    test_run_pipeline_default_reuses_2pt_cache_and_records_false,
    test_run_pipeline_recompute_2pt_true_forces_recompute_and_records_true,
    test_run_pipeline_preflight_failure_has_no_directory_side_effect,
    test_run_pipeline_successful_preflight_is_recorded_before_steps,
    test_run_pipeline_env_step_persists_augmented_snapshot_and_result,
    test_run_pipeline_without_env_step_does_not_fake_snapshot,
)


def main() -> None:
    failures = []
    for test in TESTS:
        try:
            test()
        except Exception as exc:
            failures.append((test.__name__, exc))
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")

    if failures:
        names = ", ".join(name for name, _ in failures)
        raise AssertionError(f"{len(failures)} persistence contracts failed: {names}")
    print(f"{len(TESTS)} passed, 0 failed")


if __name__ == "__main__":
    main()
