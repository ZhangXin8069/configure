"""4pt 动态收缩与 MPI 元任务的运行时契约测试。"""
from __future__ import annotations

import builtins
import os
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import h5py
import numpy as np


def test_timer_preserves_primary_failure_when_cupy_post_sync_fails():
    """A cleanup synchronization error must not replace the kernel failure."""
    from pyqcd.pipeline import _steps as steps

    primary = RuntimeError("primary kernel failure")
    synchronizations = []

    class NullStream:
        @staticmethod
        def synchronize():
            synchronizations.append("sync")
            if len(synchronizations) == 2:
                raise RuntimeError("post-sync failure")

    fake_cupy = SimpleNamespace(
        cuda=SimpleNamespace(Stream=SimpleNamespace(null=NullStream())))

    def fail():
        raise primary

    with patch.object(steps, "get_backend_name", return_value="cupy"), \
            patch.object(steps, "_cp", fake_cupy):
        try:
            steps._timer("failing kernel", None, fail)
        except RuntimeError as exc:
            assert exc is primary
        else:
            raise AssertionError("post-sync error masked the primary failure")
    assert synchronizations == ["sync", "sync"]


def test_timer_propagates_post_sync_failure_after_success():
    """Without a primary error, failed GPU completion remains reportable."""
    from pyqcd.pipeline import _steps as steps

    synchronizations = []

    class NullStream:
        @staticmethod
        def synchronize():
            synchronizations.append("sync")
            if len(synchronizations) == 2:
                raise RuntimeError("post-sync failure")

    fake_cupy = SimpleNamespace(
        cuda=SimpleNamespace(Stream=SimpleNamespace(null=NullStream())))
    with patch.object(steps, "get_backend_name", return_value="cupy"), \
            patch.object(steps, "_cp", fake_cupy):
        try:
            steps._timer("successful kernel", None, lambda: 1)
        except RuntimeError as exc:
            assert str(exc) == "post-sync failure"
        else:
            raise AssertionError("failed post-sync was silently ignored")
    assert synchronizations == ["sync", "sync"]


def test_timer_preserves_primary_failure_when_torch_cuda_post_sync_fails():
    """Torch CUDA completion failure must not replace the kernel failure."""
    from pyqcd.pipeline import _steps as steps

    primary = RuntimeError("primary torch kernel failure")
    synchronizations = []

    class FakeCuda:
        @staticmethod
        def synchronize(device=None):
            synchronizations.append(device)
            if len(synchronizations) == 2:
                raise RuntimeError("torch post-sync failure")

    fake_backend = SimpleNamespace(
        get_device=lambda: "cuda:2",
        torch=SimpleNamespace(cuda=FakeCuda()),
    )

    def fail():
        raise primary

    with patch.object(steps, "get_backend_name", return_value="torch"), \
            patch.object(steps, "get_backend", return_value=fake_backend):
        try:
            steps._timer("failing torch kernel", None, fail)
        except RuntimeError as exc:
            assert exc is primary
        else:
            raise AssertionError("Torch post-sync error masked the primary failure")
    assert synchronizations == ["cuda:2", "cuda:2"]


def test_timer_propagates_torch_cuda_post_sync_failure_after_success():
    """A successful Torch CUDA launch still requires completion."""
    from pyqcd.pipeline import _steps as steps

    synchronizations = []

    class FakeCuda:
        @staticmethod
        def synchronize(device=None):
            synchronizations.append(device)
            if len(synchronizations) == 2:
                raise RuntimeError("torch post-sync failure")

    fake_backend = SimpleNamespace(
        get_device=lambda: "cuda:3",
        torch=SimpleNamespace(cuda=FakeCuda()),
    )
    with patch.object(steps, "get_backend_name", return_value="torch"), \
            patch.object(steps, "get_backend", return_value=fake_backend):
        try:
            steps._timer("successful torch kernel", None, lambda: 1)
        except RuntimeError as exc:
            assert str(exc) == "torch post-sync failure"
        else:
            raise AssertionError("failed Torch post-sync was silently ignored")
    assert synchronizations == ["cuda:3", "cuda:3"]


def test_timer_does_not_synchronize_torch_cpu():
    """Torch CPU work must not touch the CUDA runtime."""
    from pyqcd.pipeline import _steps as steps

    class RejectCuda:
        @staticmethod
        def synchronize(device=None):
            raise AssertionError(f"unexpected CUDA synchronize on {device}")

    fake_backend = SimpleNamespace(
        get_device=lambda: "cpu",
        torch=SimpleNamespace(cuda=RejectCuda()),
    )
    with patch.object(steps, "get_backend_name", return_value="torch"), \
            patch.object(steps, "get_backend", return_value=fake_backend):
        result, elapsed = steps._timer("torch cpu", None, lambda: 7)

    assert result == 7
    assert elapsed >= 0.0


def test_4pt_dynamic_failure_is_raised_before_output_is_saved():
    """吞掉动态收缩异常会把未计算项伪装成零并写入产物。"""
    from pyqcd.pipeline import _steps as steps

    class NumpyBackend:
        @staticmethod
        def asarray(array, dtype=None):
            return np.asarray(array, dtype=dtype)

    class FailingContraction:
        def calculate_all(self):
            raise RuntimeError("dynamic contraction failure")

    peram = np.zeros((1, 1, 1, 1, 1), dtype=np.complex128)
    vertices = {
        "VdV": np.zeros((1, 1, 1, 1), dtype=np.complex128),
        "VVV": np.zeros((1, 1, 1, 1, 1), dtype=np.complex128),
    }
    saved = Mock()

    with tempfile.TemporaryDirectory() as run_dir, \
            patch.object(steps, "NT", 1), \
            patch.object(steps, "get_backend", return_value=NumpyBackend()), \
            patch.object(steps, "get_backend_name", return_value="numpy"), \
            patch.object(steps, "get_peram_dir", return_value=run_dir), \
            patch.object(steps, "_load_peram_set",
                         return_value={0: (peram, peram)}), \
            patch.object(steps, "dynamic_contraction",
                         return_value=FailingContraction()), \
            patch.object(steps, "save_array", saved):
        try:
            steps.compute_4pt_for_config(
                7, run_dir, logger=None, vertices=vertices, t_sep=0,
                nev1=1, momenta=(0,), src_step=1)
        except RuntimeError as exc:
            assert str(exc) == "dynamic contraction failure"
        else:
            raise AssertionError("动态收缩异常被吞掉，4pt 继续执行")

    assert saved.call_count == 0, "动态收缩失败后仍写入了部分 4pt 产物"


def test_meta_task_cpu_success_cleans_without_importing_torch():
    """numpy/cupy 元任务不得因清理路径导入 torch。"""
    from pyqcd.parallel import _mpi as mpi
    from pyqcd.pipeline import _steps as steps

    cleaned = []
    real_import = builtins.__import__

    def reject_torch(name, *args, **kwargs):
        if name == "torch":
            raise AssertionError("numpy 元任务不应导入 torch")
        return real_import(name, *args, **kwargs)

    with patch.object(steps, "compute_vertices_for_config",
                      lambda *args: "done"), \
            patch.object(steps, "free_gpu_memory",
                         lambda: cleaned.append("gpu")), \
            patch.object(mpi.gc, "collect",
                         lambda: cleaned.append("gc")), \
            patch("builtins.__import__", reject_torch):
        elapsed = mpi.run_meta_task(
            "vertex", 7, {"backend": "numpy"}, ".", logger=None)

    assert elapsed >= 0.0
    assert cleaned == ["gpu", "gc"]


def test_meta_task_failure_propagates_after_cleanup():
    """计算异常必须原样上抛，同时 finally 仍执行两类清理。"""
    from pyqcd.parallel import _mpi as mpi
    from pyqcd.pipeline import _steps as steps

    failure = RuntimeError("vertex failed")
    cleaned = []

    def fail(*args):
        raise failure

    with patch.object(steps, "compute_vertices_for_config", fail), \
            patch.object(steps, "free_gpu_memory",
                         lambda: cleaned.append("gpu")), \
            patch.object(mpi.gc, "collect",
                         lambda: cleaned.append("gc")):
        try:
            mpi.run_meta_task(
                "vertex", 7, {"backend": "numpy"}, ".", logger=None)
        except RuntimeError as exc:
            assert exc is failure
        else:
            raise AssertionError("元任务异常未传播")

    assert cleaned == ["gpu", "gc"]


def test_parallel_setup_applies_backend_before_vertex_compute():
    """并行驱动必须在元任务前应用请求的后端与设备。"""
    from pyqcd.parallel import _mpi as mpi
    from pyqcd.pipeline import _steps as steps
    from pyqcd.tools import (
        get_backend_name, get_torch_device, set_backend,
    )

    class LocalCollective:
        @staticmethod
        def allgather(value):
            return [value]

        @staticmethod
        def bcast(value, root=0):
            assert root == 0
            return value

        @staticmethod
        def Barrier():
            return None

    observed = []

    def capture_backend(*_args, **_kwargs):
        observed.append((get_backend_name(), str(get_torch_device())))

    plan = {'n_gpu': 0, 'N': 2, 'm': 1, 'X': 1}
    set_backend('numpy')
    try:
        with tempfile.TemporaryDirectory() as run_dir, \
                patch.object(mpi, 'get_mpi_context',
                             return_value=(LocalCollective(), 0, 2)), \
                patch.object(steps, 'dump_config_snapshot'), \
                patch.object(steps, 'compute_vertices_for_config',
                             side_effect=capture_backend), \
                patch.object(steps, 'free_gpu_memory'):
            mpi.run_parallel_pipeline(
                steps=('vertex',), conf_ids=[7], run_dir=run_dir,
                logger=None, backend='torch', device='cpu', plan=plan,
                resources={'provided': True})
    finally:
        set_backend('numpy')

    assert observed == [('torch', 'cpu')], observed


def test_mpi_launcher_does_not_silently_fallback_without_mpi4py():
    """MPI launcher 下 mpi4py 初始化失败必须快速失败而非伪装串行。"""
    from pyqcd.parallel import _mpi as mpi

    real_import = builtins.__import__

    def reject_mpi4py(name, *args, **kwargs):
        if name == 'mpi4py':
            raise ImportError('mpi4py unavailable')
        return real_import(name, *args, **kwargs)

    with patch.dict(os.environ, {'OMPI_COMM_WORLD_SIZE': '2'}, clear=True), \
            patch('builtins.__import__', reject_mpi4py):
        try:
            mpi.get_mpi_context()
        except RuntimeError as exc:
            message = str(exc)
        else:
            raise AssertionError('MPI launcher 下错误退化为独立串行进程')

    assert 'MPI launcher detected' in message
    assert 'OMPI_COMM_WORLD_SIZE' in message


def test_serial_pipeline_base_exception_cleans_and_propagates():
    """串行管线被中断时必须清理资源且保留原始异常对象。"""
    from pyqcd.pipeline import _steps as steps

    failure = KeyboardInterrupt('serial interrupted')
    cleaned = []

    def fail_vertex(*_args, **_kwargs):
        raise failure

    with tempfile.TemporaryDirectory() as run_dir, \
            patch.object(steps, 'step_vertex', side_effect=fail_vertex), \
            patch.object(steps, 'free_gpu_memory',
                         side_effect=lambda: cleaned.append('gpu')), \
            patch('gc.collect', side_effect=lambda: cleaned.append('gc')):
        try:
            steps.run_pipeline(
                steps=('vertex',), conf_ids=[7], run_dir=run_dir,
                logger=None, backend='numpy')
        except KeyboardInterrupt as exc:
            assert exc is failure
        else:
            raise AssertionError('串行中断未原样传播')

    assert cleaned == ['gpu', 'gc'], cleaned


def test_vertex_cache_reads_canonical_h5_without_recompute():
    """save_array 产出的 HDF5 顶点必须命中缓存，不能再次读取本征矢。"""
    from pyqcd.pipeline import _steps as steps
    from pyqcd.tools import set_backend

    set_backend("numpy")
    expected_vdv = np.arange(4, dtype=np.float32).reshape(1, 1, 2, 2) \
        .astype(np.complex64)
    expected_vvv = np.ones((1, 1, 1, 1, 1), dtype=np.complex64) * (1 + 1j)
    with tempfile.TemporaryDirectory() as run_dir:
        cdir = steps.conf_data_dir(run_dir, 7)
        steps.save_array(os.path.join(cdir, "VdV_mom_7.npy"), expected_vdv)
        steps.save_array(os.path.join(cdir, "VVV_mom_7.npy"), expected_vvv)

        with patch.object(steps, "NT", 1), \
                patch.object(steps, "NX", 1), \
                patch.object(steps, "NEV", 2), \
                patch.object(steps, "NEV1", 1), \
                patch.object(steps, "MOM_SINK_VDV", ((0, 0, 0),)), \
                patch.object(steps, "MOM_SINK_VVV", ((0, 0, 0),)), \
                patch.object(
                    steps, "readin_eigvecs_gpu",
                    side_effect=AssertionError(
                        "HDF5 cache miss triggered recompute")):
            actual = steps.compute_vertices_for_config(
                7, run_dir, logger=None, precision="complex64",
                recompute=False)

    assert np.array_equal(actual["VdV"], expected_vdv)
    assert np.array_equal(actual["VVV"], expected_vvv)


def test_vertex_cache_rejects_wrong_shape_dtype_finite_and_schema():
    """通用 vertex resume 只能复用精确 shape/dtype/finite/schema 的 HDF5。"""
    from pyqcd.pipeline import _steps as steps
    from pyqcd.tools import set_backend

    class RecomputeTriggered(RuntimeError):
        pass

    set_backend("numpy")
    good_vdv = np.ones((1, 1, 2, 2), dtype=np.complex128)
    good_vvv = np.ones((1, 1, 1, 1, 1), dtype=np.complex128)
    for mode in ("shape", "dtype", "finite", "dataset"):
        with tempfile.TemporaryDirectory() as run_dir:
            cdir = steps.conf_data_dir(run_dir, 7)
            vdv = good_vdv.copy()
            if mode == "shape":
                vdv = np.ones((1, 1, 2, 3), dtype=np.complex128)
            elif mode == "dtype":
                vdv = vdv.astype(np.complex64)
            elif mode == "finite":
                vdv[0, 0, 0, 0] = np.nan + 0j
            steps.save_array(os.path.join(cdir, "VdV_mom_7.h5"), vdv)
            steps.save_array(os.path.join(cdir, "VVV_mom_7.h5"), good_vvv)
            if mode == "dataset":
                with h5py.File(os.path.join(cdir, "VdV_mom_7.h5"), "r+") as h5:
                    h5.create_dataset("unexpected", data=np.zeros(1))

            with patch.object(steps, "NT", 1), \
                    patch.object(steps, "NX", 1), \
                    patch.object(steps, "NEV", 2), \
                    patch.object(steps, "NEV1", 1), \
                    patch.object(steps, "MOM_SINK_VDV", ((0, 0, 0),)), \
                    patch.object(steps, "MOM_SINK_VVV", ((0, 0, 0),)), \
                    patch.object(
                        steps, "readin_eigvecs_gpu",
                        side_effect=RecomputeTriggered(mode)):
                try:
                    steps.compute_vertices_for_config(
                        7, run_dir, logger=None, precision="complex128",
                        recompute=False)
                except RecomputeTriggered:
                    pass
                else:
                    raise AssertionError(
                        f"invalid vertex cache was reused: {mode}")


def test_vertex_cache_key_distinguishes_vdv_and_vvv_momenta():
    """VVV 动量改变时不得因 VdV 动量相同而静默复用旧缓存。"""
    from pyqcd.pipeline import _steps as steps
    from pyqcd.tools import set_backend

    class RecomputeTriggered(RuntimeError):
        pass

    set_backend("numpy")
    with tempfile.TemporaryDirectory() as run_dir:
        cdir = steps.conf_data_dir(run_dir, 7)
        steps.save_array(os.path.join(cdir, "VdV_mom000_7.npy"),
                         np.zeros((1, 1)))
        steps.save_array(os.path.join(cdir, "VVV_mom000_7.npy"),
                         np.zeros((1, 1, 1)))

        with patch.object(
                steps, "readin_eigvecs_gpu",
                side_effect=RecomputeTriggered("distinct cache key")):
            try:
                steps.compute_vertices_for_config(
                    7, run_dir, logger=None, recompute=False,
                    mom_sink_vdv=[(0, 0, 0)],
                    mom_sink_vvv=[(2, 0, 0)])
            except RecomputeTriggered:
                pass
            else:
                raise AssertionError(
                    "不同 VVV 动量错误命中了仅由 VdV 动量命名的缓存")


def test_plot_recovery_reads_canonical_h5_analysis():
    """独立 plots 步骤必须从规范 HDF5 分析产物恢复四个通道。"""
    from pyqcd.pipeline import _steps as steps

    with tempfile.TemporaryDirectory() as run_dir:
        analysis_dir = os.path.join(run_dir, "data", "analysis")
        for particle, momentum in (
                ("proton", "P0"), ("proton", "P2"),
                ("pion", "P0"), ("pion", "P2")):
            mean = np.linspace(0.8, 1.2, 20)
            error = np.full(20, 0.05)
            corr = np.exp(-0.2 * np.arange(20))
            corr_error = np.full(20, 0.01)
            for stem, value in (
                    ("meff", mean), ("meff_err", error),
                    ("corr", corr), ("corr_err", corr_error)):
                suffix = "err" if stem.endswith("_err") else "mean"
                base = stem[:-4] if stem.endswith("_err") else stem
                steps.save_array(os.path.join(
                    analysis_dir,
                    f"{base}_{particle}_{momentum}_{suffix}.npy"), value)

        with patch.object(steps, "plot_meff_results"), \
                patch.object(steps, "plot_correlators"):
            recovered = steps.step_plots(
                {}, run_dir, logger=None, meff_res=None, ratio_conn=None)

    assert set(recovered) == {
        "proton_P0", "proton_P2", "pion_P0", "pion_P2",
    }
    for result in recovered.values():
        assert result["meff_mean"].shape == (20,)
        assert result["corr_mean"].shape == (20,)


def test_report_reads_canonical_h5_analysis_and_correlators():
    """报告汇总必须消费 HDF5 ratio 与组态级 correlator。"""
    from pyqcd.pipeline import _steps as steps

    captured = {}

    def capture_build_tex(summary, run_dir, meff_vals, connected_ratio,
                          disconnected, conf_corrs):
        captured["connected_ratio"] = connected_ratio
        captured["conf_corrs"] = conf_corrs
        return "report"

    with tempfile.TemporaryDirectory() as run_dir:
        analysis_dir = os.path.join(run_dir, "data", "analysis")
        conf_dir = os.path.join(run_dir, "data", "conf7")
        steps.save_array(os.path.join(
            analysis_dir, "ratio_proton_P0_mean.npy"), np.arange(4.0))
        steps.save_array(os.path.join(
            analysis_dir, "ratio_proton_P0_err.npy"), np.full(4, 0.1))
        steps.save_array(os.path.join(
            conf_dir, "corr_pp_P0_7.npy"), np.arange(6.0))

        def successful_xelatex(command, cwd, capture_output):
            with open(os.path.join(cwd, "physics_report.pdf"), "wb") as pdf:
                pdf.write(b"fresh pdf")
            return subprocess.CompletedProcess(
                command, 0, stdout=b"", stderr=b"")

        with patch.object(steps, "build_tex", side_effect=capture_build_tex), \
                patch.object(steps.subprocess, "run",
                             side_effect=successful_xelatex) as compile_mock:
            summary = steps.step_report(
                {"conf_ids": [7], "precision": "complex128"},
                run_dir, logger=None, meff_res={}, timing={})
        pdf_exists = os.path.isfile(
            os.path.join(run_dir, "physics_report.pdf"))

    assert summary["version"] == "test0"
    assert compile_mock.call_count == 2
    assert pdf_exists
    ratio = captured["connected_ratio"]["proton_P0"]
    assert np.array_equal(ratio["R"], np.arange(4.0))
    assert np.array_equal(ratio["R_err"], np.full(4, 0.1))
    assert np.array_equal(
        captured["conf_corrs"][7]["pp_P0_7"], np.arange(6.0))


def test_report_real_xelatex_template_has_no_hard_gate_diagnostics():
    """最小有限输入须经过真实 build_tex 与两遍 XeLaTeX 硬门。"""
    if shutil.which("xelatex") is None:
        raise unittest.SkipTest("xelatex is unavailable")
    probe = subprocess.run(
        ["kpsewhich", "physics.sty"],
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0 or not probe.stdout.strip():
        raise unittest.SkipTest("LaTeX package physics.sty is unavailable")

    from pyqcd.pipeline import _steps as steps

    channels = (
        ("proton", "P0"), ("proton", "P2"),
        ("pion", "P0"), ("pion", "P2"),
    )
    meff_res = {
        f"{had}_{momentum}": {
            "E0": 1.0, "E0_err": 0.01, "E_exp": 1.0,
            "plateau": (4, 8), "npts": 4,
        }
        for had, momentum in channels
    }
    messages = []

    with tempfile.TemporaryDirectory() as run_dir:
        analysis_dir = os.path.join(run_dir, "data", "analysis")
        conf_dir = os.path.join(run_dir, "data", "conf7")
        for had, momentum in channels:
            steps.save_array(
                os.path.join(
                    analysis_dir, f"ratio_{had}_{momentum}_mean.npy"),
                np.linspace(0.1, 0.5, 5))
            steps.save_array(
                os.path.join(
                    analysis_dir, f"ratio_{had}_{momentum}_err.npy"),
                np.full(5, 0.01))
        steps.save_array(
            os.path.join(conf_dir, "corr_pp_P0_7.npy"),
            np.linspace(1.0, 0.5, 6))

        summary = steps.step_report(
            {"conf_ids": [7], "precision": "complex128", "Nev1": 100},
            run_dir, messages.append, meff_res, {"analysis": 0.125})

        assert summary["version"] == "test0"
        assert os.path.isfile(os.path.join(run_dir, "physics_report.pdf"))
        assert sum("XeLaTeX pass 1: returncode=0" in message
                   for message in messages) == 1
        assert sum("XeLaTeX pass 2: returncode=0" in message
                   for message in messages) == 1
        with open(os.path.join(run_dir, "physics_report.log"),
                  encoding="utf-8") as log:
            report_log = log.read()
        assert "Underfull" not in report_log


def test_build_tex_missing_or_empty_plateau_uses_explanatory_placeholder():
    """缺失、空值和 None 平台只显示无平台数据，不伪造区间。"""
    from pyqcd.pipeline import _steps as steps

    for channel_data in ({}, {"plateau": []}, {"plateau": None}):
        with tempfile.TemporaryDirectory() as run_dir:
            tex = steps.build_tex(
                {"conf_ids": [7], "precision": "complex128"},
                run_dir,
                {"proton_P0": channel_data}, {}, {}, {})
        assert tex.count("无平台数据") == 4
        assert "$[0,0]$" not in tex


def test_report_first_xelatex_failure_raises_even_with_stale_pdf():
    """第一遍非零退出必须优先于旧 PDF 存在性。"""
    from pyqcd.pipeline import _steps as steps

    with tempfile.TemporaryDirectory() as run_dir:
        pdf_path = os.path.join(run_dir, "physics_report.pdf")
        with open(pdf_path, "wb") as pdf:
            pdf.write(b"old pdf")

        failed = subprocess.CompletedProcess(
            ["xelatex"], 1,
            stdout=b"first pass stdout tail",
            stderr=b"first pass stderr tail")
        with patch.object(steps, "build_tex", return_value="report"), \
                patch.object(steps.subprocess, "run",
                             return_value=failed) as compile_mock:
            try:
                steps.step_report(
                    {"conf_ids": [7], "precision": "complex128"},
                    run_dir, logger=None, meff_res={}, timing={})
            except RuntimeError as exc:
                message = str(exc)
            else:
                raise AssertionError("第一遍 XeLaTeX 失败未抛出")

        with open(pdf_path, "rb") as pdf:
            assert pdf.read() == b"old pdf"

    assert "pass 1" in message
    assert "first pass stderr tail" in message
    assert compile_mock.call_count == 1


def test_report_second_xelatex_failure_raises_after_first_success():
    """第二遍非零退出必须抛出，即使第一遍已经生成 PDF。"""
    from pyqcd.pipeline import _steps as steps

    with tempfile.TemporaryDirectory() as run_dir:
        calls = []

        def xelatex_with_second_pass_failure(command, cwd, capture_output):
            calls.append(command)
            if len(calls) == 1:
                with open(os.path.join(cwd, "physics_report.pdf"), "wb") as pdf:
                    pdf.write(b"first-pass pdf")
                return subprocess.CompletedProcess(
                    command, 0, stdout=b"", stderr=b"")
            return subprocess.CompletedProcess(
                command, 1, stdout=b"second pass stdout tail",
                stderr=b"second pass stderr tail")

        with patch.object(steps, "build_tex", return_value="report"), \
                patch.object(steps.subprocess, "run",
                             side_effect=xelatex_with_second_pass_failure) \
                as compile_mock:
            try:
                steps.step_report(
                    {"conf_ids": [7], "precision": "complex128"},
                    run_dir, logger=None, meff_res={}, timing={})
            except RuntimeError as exc:
                message = str(exc)
            else:
                raise AssertionError("第二遍 XeLaTeX 失败未抛出")

    assert "pass 2" in message
    assert "second pass stderr tail" in message
    assert compile_mock.call_count == 2


def test_report_successful_passes_require_a_new_pdf():
    """两遍成功但没有新 PDF 时，旧 PDF 或空目录都不能伪装成功。"""
    from pyqcd.pipeline import _steps as steps

    for old_pdf in (None, b"stale pdf"):
        with tempfile.TemporaryDirectory() as run_dir:
            pdf_path = os.path.join(run_dir, "physics_report.pdf")
            if old_pdf is not None:
                with open(pdf_path, "wb") as pdf:
                    pdf.write(old_pdf)

            def successful_xelatex(command, cwd, capture_output):
                return subprocess.CompletedProcess(
                    command, 0, stdout=b"", stderr=b"")

            with patch.object(steps, "build_tex", return_value="report"), \
                    patch.object(steps.subprocess, "run",
                                 side_effect=successful_xelatex) as compile_mock:
                try:
                    steps.step_report(
                        {"conf_ids": [7], "precision": "complex128"},
                        run_dir, logger=None, meff_res={}, timing={})
                except RuntimeError as exc:
                    message = str(exc)
                else:
                    raise AssertionError("无新 PDF 时报告验收未失败")

            assert "physics_report.pdf" in message
            assert compile_mock.call_count == 2


def test_report_rejects_latex_diagnostics_from_each_pass_source():
    """两遍任一输出源出现三类 XeLaTeX 诊断都必须硬失败。"""
    from pyqcd.pipeline import _steps as steps

    diagnostics = ("Overfull \\hbox", "Float too large", "Missing character")
    sources = ("stdout", "stderr", "log")
    cases = tuple((source, diagnostic)
                  for source in sources for diagnostic in diagnostics)
    for index, (source, diagnostic) in enumerate(cases):
        trigger_pass = 1 if index % 2 == 0 else 2
        with tempfile.TemporaryDirectory() as run_dir:
            calls = []

            def xelatex_with_diagnostic(command, cwd, capture_output):
                calls.append(command)
                pass_number = len(calls)
                text = diagnostic if pass_number == trigger_pass else ""
                with open(os.path.join(cwd, "physics_report.log"), "w",
                          encoding="utf-8") as log:
                    log.write(text if source == "log" else "clean")
                if pass_number == 2:
                    with open(os.path.join(cwd, "physics_report.pdf"), "wb") as pdf:
                        pdf.write(b"fresh pdf")
                return subprocess.CompletedProcess(
                    command, 0,
                    stdout=text.encode() if source == "stdout" else b"",
                    stderr=text.encode() if source == "stderr" else b"")

            with patch.object(steps, "build_tex", return_value="report"), \
                    patch.object(steps.subprocess, "run",
                                 side_effect=xelatex_with_diagnostic) \
                    as compile_mock:
                try:
                    steps.step_report(
                        {"conf_ids": [7], "precision": "complex128"},
                        run_dir, logger=None, meff_res={}, timing={})
                except RuntimeError as exc:
                    message = str(exc)
                else:
                    raise AssertionError(
                        f"{source}/{diagnostic} 未触发 LaTeX 诊断硬闸门")

            assert diagnostic in message
            assert f"pass {trigger_pass}" in message
            assert compile_mock.call_count == 2


def test_runner_records_stage_eta_after_each_configuration():
    """五个计算阶段都应在每个组态完成时记录 step/conf/耗时/ETA。"""
    from pyqcd.pipeline import _steps

    messages = []
    with tempfile.TemporaryDirectory() as run_dir, \
            patch.object(_steps, "compute_vertices_for_config",
                         return_value={}), \
            patch.object(_steps, "_load_vertices_one", return_value={}), \
            patch.object(_steps, "compute_2pt_for_config", return_value={}), \
            patch.object(_steps, "compute_ope_for_config", return_value={}), \
            patch.object(_steps, "compute_3pt_for_config", return_value={}), \
            patch.object(_steps, "compute_4pt_for_config", return_value={}), \
            patch.object(_steps, "free_gpu_memory"):
        _steps.run_pipeline(
            steps=("vertex", "2pt", "ope", "3pt", "4pt"),
            conf_ids=[7, 8], run_dir=run_dir, logger=messages.append,
            backend="numpy")

    for stage in ("vertex", "2pt", "ope", "3pt", "4pt"):
        for conf_id in (7, 8):
            assert any(
                f"step={stage} conf={conf_id}" in message
                and "ETA" in message
                for message in messages
            ), (stage, conf_id, messages)


def main():
    tests = (
        test_timer_preserves_primary_failure_when_cupy_post_sync_fails,
        test_timer_propagates_post_sync_failure_after_success,
        test_timer_preserves_primary_failure_when_torch_cuda_post_sync_fails,
        test_timer_propagates_torch_cuda_post_sync_failure_after_success,
        test_timer_does_not_synchronize_torch_cpu,
        test_4pt_dynamic_failure_is_raised_before_output_is_saved,
        test_meta_task_cpu_success_cleans_without_importing_torch,
        test_meta_task_failure_propagates_after_cleanup,
        test_parallel_setup_applies_backend_before_vertex_compute,
        test_mpi_launcher_does_not_silently_fallback_without_mpi4py,
        test_serial_pipeline_base_exception_cleans_and_propagates,
        test_vertex_cache_reads_canonical_h5_without_recompute,
        test_vertex_cache_rejects_wrong_shape_dtype_finite_and_schema,
        test_vertex_cache_key_distinguishes_vdv_and_vvv_momenta,
        test_plot_recovery_reads_canonical_h5_analysis,
        test_report_reads_canonical_h5_analysis_and_correlators,
        test_report_real_xelatex_template_has_no_hard_gate_diagnostics,
        test_build_tex_missing_or_empty_plateau_uses_explanatory_placeholder,
        test_report_first_xelatex_failure_raises_even_with_stale_pdf,
        test_report_second_xelatex_failure_raises_after_first_success,
        test_report_successful_passes_require_a_new_pdf,
        test_report_rejects_latex_diagnostics_from_each_pass_source,
        test_runner_records_stage_eta_after_each_configuration,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"{len(tests)} passed, 0 failed")


if __name__ == "__main__":
    main()
