"""契约测试：MPI 计划、设备绑定、预检与空组态语义。

本模块不依赖 pytest，既可由统一测试入口调用，也可直接执行：

    python -m pyqcd.testing._mpi_planning_contract
"""
from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import pyqcd.parallel._mpi as mpi


def _recommended_plan():
    """Hand-written recommended plan used by serial-fallback tests."""
    return {
        'n_gpu': 2,
        'b_mb': 100.0,
        'gpu_total_mb': 200.0,
        'a_mb': 50.0,
        'm': 3,
        'N': 4,
        'Y': 2,
        'X': 1,
        'per_rank_vram_mb': 50.0,
        'cpu_ok': True,
        'mem_ok': True,
        'notes': 'N*a=n*b formula',
    }


def test_size_one_returns_effective_serial_plan_without_mutating_input():
    """size=1 must report one executed rank and preserve planned_N."""
    original = _recommended_plan()
    messages = []
    observed = []

    def capture_serial(**kwargs):
        observed.append(kwargs)
        return {'run_dir': kwargs['run_dir']}

    with patch.object(mpi, 'get_mpi_context', return_value=(None, 0, 1)), \
            patch('pyqcd.pipeline.run_pipeline', side_effect=capture_serial):
        result, effective = mpi.run_parallel_pipeline(
            steps=(), conf_ids=[101, 102, 103],
            run_dir='/contract/serial-fallback', logger=messages.append,
            backend='numpy', plan=original, resources={'provided': True})

    assert result == {'run_dir': '/contract/serial-fallback'}
    assert observed and observed[0]['conf_ids'] == [101, 102, 103]
    assert effective is not original
    assert original == _recommended_plan()
    assert effective['planned_N'] == 4
    assert effective['N'] == 1
    assert effective['X'] == 3
    assert effective['Y'] == 1
    assert effective['n_gpu'] == 1
    assert 'serial fallback' in mpi.format_plan(effective).lower()
    assert messages.count(
        f"[parallel] plan: {mpi.format_plan(effective)}") == 1


def test_size_one_dry_run_keeps_recommended_plan():
    """dry-run must expose the recommendation rather than serial fallback."""
    recommended = _recommended_plan()
    with patch.object(mpi, 'get_mpi_context', return_value=(None, 0, 1)), \
            patch('pyqcd.pipeline.run_pipeline') as serial_run:
        result, returned = mpi.run_parallel_pipeline(
            steps=(), conf_ids=[101, 102, 103], logger=None,
            backend='numpy', plan=recommended, resources={'provided': True},
            dry_run=True)

    assert result is None
    assert returned['N'] == 4
    assert returned['planned_N'] if 'planned_N' in returned else True
    serial_run.assert_not_called()


def _resources(*, n_gpu, cpu_threads, mem_avail_mb, gpu_usable_mb=4000.0):
    """Small deterministic resource snapshot for planning contracts."""
    return {
        'n_gpu': n_gpu,
        'gpu_vram_mb': gpu_usable_mb / 0.8 if gpu_usable_mb else 0.0,
        'gpu_usable_mb': gpu_usable_mb,
        'cpu_threads': cpu_threads,
        'mem_total_mb': mem_avail_mb,
        'mem_avail_mb': mem_avail_mb,
    }


def test_plan_rejects_nonpositive_task_count():
    """m=0 and m<0 must be rejected before any division or plan output."""
    resources = _resources(n_gpu=0, cpu_threads=8, mem_avail_mb=8192.0)
    for task_count in (0, -1):
        try:
            mpi.plan_parallel(task_count, 100.0, resources=resources)
        except ValueError as exc:
            assert 'm' in str(exc)
        else:
            raise AssertionError(f'm={task_count} was accepted')


def test_plan_recomputes_ram_status_after_caps():
    """The returned mem_ok must describe the final N, not the initial guess."""
    plan = mpi.plan_parallel(
        4, 1000.0,
        resources=_resources(n_gpu=2, cpu_threads=8, mem_avail_mb=1.0),
    )

    assert plan['N'] == 2
    assert plan['X'] == 2
    assert plan['Y'] == 1
    assert plan['mem_ok'] is False


def test_plan_treats_zero_available_ram_as_known_exhaustion():
    """MemAvailable=0 is a measured failure, not an unknown-value fallback."""
    resources = _resources(
        n_gpu=0, cpu_threads=8, mem_avail_mb=0.0)
    resources['mem_total_mb'] = 8192.0

    plan = mpi.plan_parallel(2, 1000.0, resources=resources)

    assert plan['N'] == 1
    assert plan['mem_ok'] is False
    assert plan['mem_needed_mb'] > resources['mem_avail_mb']


def test_plan_marks_oversized_gpu_task_unusable():
    """One task larger than per-GPU b must not be advertised as executable."""
    plan = mpi.plan_parallel(
        2, 1000.0,
        resources=_resources(
            n_gpu=1, cpu_threads=8, mem_avail_mb=8192.0,
            gpu_usable_mb=500.0),
    )

    assert plan['N'] == 1
    assert plan['Y'] == 1
    assert plan['gpu_ok'] is False
    assert plan['gpu_needed_mb'] == 1000.0
    assert 'gpu_ok=False' in mpi.format_plan(plan)


def test_unknown_and_zero_gpu_budgets_are_distinct_and_fail_closed():
    """Unknown b must stay unknown; an explicit zero remains numeric zero."""
    common = {
        'n_gpu': 1,
        'gpu_vram_mb': None,
        'cpu_threads': 8,
        'mem_total_mb': 8192.0,
        'mem_avail_mb': 8192.0,
    }
    unknown = mpi.plan_parallel(
        2, None, resources=dict(common, gpu_usable_mb=None))
    zero = mpi.plan_parallel(
        2, 1000.0, resources=dict(common, gpu_usable_mb=0.0))

    assert unknown['b_mb'] is None
    assert unknown['gpu_ok'] is False
    assert 'b=unknown' in mpi.format_plan(unknown)
    assert 'b=0 MB' not in mpi.format_plan(unknown)
    assert zero['b_mb'] == 0.0
    assert zero['gpu_ok'] is False
    assert 'b=0 MB' in mpi.format_plan(zero)


def test_unknown_gpu_count_is_not_reported_as_cpu_only():
    """Losing both GPU probes must remain unknown and fail the GPU gate."""
    resources = {
        'n_gpu': None,
        'gpu_vram_mb': None,
        'gpu_usable_mb': None,
        'cpu_threads': 8,
        'mem_total_mb': 8192.0,
        'mem_avail_mb': 8192.0,
    }

    plan = mpi.plan_parallel(2, 1000.0, resources=resources)
    rendered = mpi.format_plan(plan)

    assert plan['n_gpu'] == 0
    assert plan['n_gpu_available'] is None
    assert plan['b_mb'] is None
    assert plan['gpu_ok'] is False
    assert 'GPU availability unknown' in rendered
    assert 'no GPU detected' not in plan['notes']


def test_unknown_available_ram_is_not_replaced_by_total_ram():
    """MemTotal is capacity, not a substitute for unknown MemAvailable."""
    resources = _resources(
        n_gpu=0, cpu_threads=8, mem_avail_mb=8192.0)
    resources['mem_avail_mb'] = None
    resources['mem_total_mb'] = 8192.0

    plan = mpi.plan_parallel(2, 1000.0, resources=resources)

    assert plan['mem_available_mb'] is None
    assert plan['mem_ok'] is None
    assert 'mem_ok=unknown' in mpi.format_plan(plan)


def test_negative_gpu_override_is_rejected():
    """A negative explicit device count is invalid, not a CPU request."""
    resources = _resources(
        n_gpu=2, cpu_threads=8, mem_avail_mb=8192.0)
    try:
        mpi.plan_parallel(2, None, resources=resources, n_gpu=-1)
    except ValueError as exc:
        assert 'n_gpu' in str(exc)
    else:
        raise AssertionError('negative n_gpu override was accepted')


def test_cpu_plan_reports_unknown_per_task_vram_input():
    """The CPU formatter must not hide that a was never measured/provided."""
    plan = mpi.plan_parallel(
        2, None,
        resources=_resources(
            n_gpu=0, cpu_threads=8, mem_avail_mb=8192.0),
    )

    assert plan['a_mb'] is None
    assert 'a=not provided' in mpi.format_plan(plan)


def test_gpu_info_distinguishes_probe_failure_from_known_zero_devices():
    """Both detector failures are unknown; a successful zero probe is known."""
    from pyqcd.parallel import _resources as resource_module

    cuda_zero = SimpleNamespace(
        is_available=lambda: False,
        device_count=lambda: 0,
    )
    fake_torch = SimpleNamespace(cuda=cuda_zero)
    with patch.dict(sys.modules, {'torch': None}), \
            patch('subprocess.run', side_effect=OSError('probe unavailable')):
        assert resource_module.gpu_info() == (None, None, None)
    with patch.dict(sys.modules, {'torch': fake_torch}), \
            patch('subprocess.run', side_effect=OSError('nvidia-smi absent')):
        assert resource_module.gpu_info() == (0, 0, 0)


def test_serial_fallback_recomputes_derived_resource_fields():
    """The effective N=1 view must not retain N-rank RAM/VRAM estimates."""
    resources = _resources(
        n_gpu=2, cpu_threads=64, mem_avail_mb=65536.0,
        gpu_usable_mb=4000.0)
    recommended = mpi.plan_parallel(16, 1000.0, resources=resources)
    effective = mpi._serial_fallback_plan(recommended)

    assert recommended['N'] == 8
    assert recommended['gpu_needed_mb'] == 4000.0
    assert recommended['mem_needed_mb'] == 24000.0
    assert effective['N'] == 1
    assert effective['Y'] == 1
    assert effective['gpu_needed_mb'] == 1000.0
    assert effective['mem_needed_mb'] == 3000.0
    assert effective['gpu_ok'] is True
    assert effective['mem_ok'] is True


def test_plan_reduces_active_gpus_when_tasks_are_fewer():
    """m<n must reduce active GPUs so N=Y*n_gpu remains integral."""
    plan = mpi.plan_parallel(
        2, None,
        resources=_resources(n_gpu=4, cpu_threads=16, mem_avail_mb=8192.0),
    )

    assert plan['n_gpu_available'] == 4
    assert plan['n_gpu'] == 2
    assert plan['N'] == 2
    assert plan['Y'] == 1
    assert plan['X'] == 1


def test_plan_reduces_active_gpus_when_cpu_cap_is_smaller():
    """A CPU cap below available GPUs must not yield a fractional Y."""
    plan = mpi.plan_parallel(
        8, None,
        resources=_resources(n_gpu=4, cpu_threads=2, mem_avail_mb=8192.0),
    )

    assert plan['n_gpu_available'] == 4
    assert plan['n_gpu'] == 2
    assert plan['N'] == 2
    assert plan['Y'] == 1
    assert plan['cpu_ok'] is True


def test_format_plan_reports_active_and_available_gpu_counts():
    """A reduced plan must disclose both active and discovered GPU counts."""
    plan = mpi.plan_parallel(
        2, None,
        resources=_resources(n_gpu=4, cpu_threads=16, mem_avail_mb=8192.0),
    )
    rendered = mpi.format_plan(plan)

    assert '2 active GPUs' in rendered
    assert '4 available' in rendered


def test_gpu_formula_uses_per_gpu_memory_and_preserves_integral_force_cap():
    """Y=b/a per GPU; N, VRAM text, and force_y stay self-consistent."""
    resources = _resources(
        n_gpu=2, cpu_threads=64, mem_avail_mb=65536.0,
        gpu_usable_mb=4000.0)
    plan = mpi.plan_parallel(16, 1000.0, resources=resources)

    assert plan['n_gpu'] == 2
    assert plan['Y'] == 4
    assert plan['N'] == 8
    assert plan['N'] == plan['Y'] * plan['n_gpu']
    assert plan['per_rank_vram_mb'] == 1000.0
    rendered = mpi.format_plan(plan)
    assert 'Y=4 proc/GPU' in rendered
    assert 'per-rank VRAM 1000 MB' in rendered

    capped = mpi.plan_parallel(
        16, 1000.0, resources=resources, force_y=7)
    assert capped['Y'] == 7
    assert capped['N'] == 14
    assert capped['N'] == capped['Y'] * capped['n_gpu']


class _PlanningComm:
    """Minimal successful allgather for a one-process contract model."""

    @staticmethod
    def allgather(value):
        return [value, None]


def test_preflight_rejects_explicit_memory_failure_before_setup():
    """An explicit failed memory gate must stop before creating run dirs."""
    plan = {
        'n_gpu': 0,
        'N': 2,
        'm': 2,
        'X': 1,
        'mem_ok': False,
    }
    with tempfile.TemporaryDirectory() as tmpdir, \
            patch.object(mpi, 'get_mpi_context',
                         return_value=(_PlanningComm(), 0, 2)), \
            patch.object(mpi.os, 'makedirs') as makedirs:
        try:
            mpi.run_parallel_pipeline(
                steps=(), conf_ids=[101], run_dir=os.path.join(tmpdir, 'run'),
                logger=None, backend='numpy', plan=plan,
                resources={'provided': True})
        except RuntimeError as exc:
            assert 'mem_ok=False' in str(exc)
        else:
            raise AssertionError('explicit mem_ok=False was accepted')

    assert not makedirs.called


def test_preflight_rejects_explicit_gpu_failure_before_setup():
    """An impossible per-GPU VRAM plan must fail before directory writes."""
    plan = {
        'n_gpu': 2,
        'N': 2,
        'Y': 1,
        'm': 2,
        'X': 1,
        'mem_ok': True,
        'gpu_ok': False,
    }
    with tempfile.TemporaryDirectory() as tmpdir, \
            patch.object(mpi, 'get_mpi_context',
                         return_value=(_PlanningComm(), 0, 2)), \
            patch.object(mpi.os, 'makedirs') as makedirs:
        try:
            mpi.run_parallel_pipeline(
                steps=(), conf_ids=[101], run_dir=os.path.join(tmpdir, 'run'),
                logger=None, backend='numpy', plan=plan,
                resources={'provided': True})
        except RuntimeError as exc:
            assert 'gpu_ok=False' in str(exc)
        else:
            raise AssertionError('explicit gpu_ok=False was accepted')

    assert not makedirs.called


def test_preflight_rejects_explicit_cpu_failure_before_setup():
    """A custom overcommitted CPU plan must fail before directory writes."""
    plan = {
        'n_gpu': 0,
        'N': 2,
        'Y': 0,
        'm': 2,
        'X': 1,
        'cpu_ok': False,
        'mem_ok': True,
    }
    with tempfile.TemporaryDirectory() as tmpdir, \
            patch.object(mpi, 'get_mpi_context',
                         return_value=(_PlanningComm(), 0, 2)), \
            patch.object(mpi.os, 'makedirs') as makedirs:
        try:
            mpi.run_parallel_pipeline(
                steps=(), conf_ids=[101], run_dir=os.path.join(tmpdir, 'run'),
                logger=None, backend='numpy', plan=plan,
                resources={'provided': True})
        except RuntimeError as exc:
            assert 'cpu_ok=False' in str(exc)
        else:
            raise AssertionError('explicit cpu_ok=False was accepted')

    assert not makedirs.called


def test_preflight_rejects_structurally_inconsistent_custom_plan():
    """N/Y/n_gpu and X/m/N invariants are part of the plan contract."""
    invalid_plans = (
        {'n_gpu': 2, 'N': 2, 'Y': 99, 'm': 2, 'X': 1,
         'mem_ok': True, 'gpu_ok': True},
        {'n_gpu': 0, 'N': 2, 'Y': 0, 'm': 2, 'X': 999,
         'mem_ok': True},
        {'n_gpu': 0, 'N': True, 'Y': 0, 'm': 2, 'X': 1,
         'mem_ok': True},
    )
    for plan in invalid_plans:
        with patch.object(mpi, 'get_mpi_context',
                          return_value=(_PlanningComm(), 0, 2)), \
                patch.object(mpi.os, 'makedirs') as makedirs:
            try:
                mpi.run_parallel_pipeline(
                    steps=(), conf_ids=[101, 102],
                    run_dir='/contract/must-not-exist', logger=None,
                    backend='numpy', plan=plan)
            except RuntimeError as exc:
                assert 'MPI plan' in str(exc)
            else:
                raise AssertionError(f'inconsistent plan was accepted: {plan}')
            assert not makedirs.called


class _SetupComm:
    """One-rank model of a two-rank communicator for setup contracts."""

    def __init__(self, run_dir='/contract/run'):
        self.run_dir = run_dir

    @staticmethod
    def allgather(value):
        return [value, None]

    def bcast(self, value, root=0):
        assert root == 0
        return self.run_dir

    @staticmethod
    def Barrier():
        return None


def _backend_plan():
    return {
        'n_gpu': 2,
        'n_gpu_available': 2,
        'b_mb': 100.0,
        'gpu_total_mb': 200.0,
        'a_mb': 50.0,
        'm': 2,
        'N': 2,
        'Y': 1,
        'X': 1,
        'per_rank_vram_mb': 100.0,
        'cpu_ok': True,
        'mem_ok': True,
    }


def _run_backend_meta_task(backend, device, *, fake_torch=None):
    """Run one rank through real setup and capture its bound config."""
    events = []
    observed = []

    def fake_timer(_name, _logger, fn, *args, **kwargs):
        return fn(*args, **kwargs), 0.0

    def capture_task(_step, _cid, config, _run_dir, _logger):
        observed.append(dict(config))
        return 0.0

    fake_set_backend = lambda name, device=None: events.append(
        ('set_backend', name, device))
    patches = [
        patch.object(mpi, 'get_mpi_context',
                     return_value=(_SetupComm(), 1, 2)),
        patch.object(mpi, 'run_meta_task', side_effect=capture_task),
        patch('pyqcd.pipeline._steps._timer', side_effect=fake_timer),
        patch('pyqcd.pipeline._steps.dump_config_snapshot'),
        patch('pyqcd.pipeline._steps.free_gpu_memory'),
        patch('pyqcd.tools.set_backend', side_effect=fake_set_backend),
    ]
    if fake_torch is not None:
        patches.append(patch.dict(sys.modules, {'torch': fake_torch}))

    with patches[0]:
        with patches[1]:
            with patches[2]:
                with patches[3]:
                    with patches[4]:
                        with patches[5]:
                            if fake_torch is not None:
                                with patches[6]:
                                    mpi.run_parallel_pipeline(
                                        steps=('vertex',), conf_ids=[101, 102],
                                        run_dir='/contract/run', logger=None,
                                        backend=backend, device=device,
                                        plan=_backend_plan(),
                                        resources={'provided': True})
                            else:
                                mpi.run_parallel_pipeline(
                                    steps=('vertex',), conf_ids=[101, 102],
                                    run_dir='/contract/run', logger=None,
                                    backend=backend, device=device,
                                    plan=_backend_plan(),
                                    resources={'provided': True})
    return events, observed


def test_cupy_binds_rank_device_before_selecting_backend():
    """CuPy setup must select cuda:rank before set_backend('cupy')."""
    events = []

    class FakeDevice:
        def __init__(self, index):
            events.append(('Device', index))
            self.index = index

        def use(self):
            events.append(('use', self.index))

    fake_cupy = ModuleType('cupy')
    fake_cupy.cuda = SimpleNamespace(Device=FakeDevice)
    try:
        with patch.dict(sys.modules, {'cupy': fake_cupy}):
            backend_events, observed = _run_backend_meta_task(
                'cupy', None)
    finally:
        from pyqcd.tools import set_backend
        set_backend('numpy')

    assert events == [('Device', 1), ('use', 1)]
    assert backend_events == [('set_backend', 'cupy', 'cuda:1')]
    assert observed[0]['backend'] == 'cupy'
    assert observed[0]['device'] == 'cuda:1'


def test_torch_aliases_bind_active_rank_gpu():
    """gpu/cuda aliases must canonicalize to torch and bind cuda:rank."""
    for alias in ('gpu', 'cuda'):
        selected = []
        fake_torch = ModuleType('torch')
        fake_torch.cuda = SimpleNamespace(
            set_device=lambda device: selected.append(device))
        events, observed = _run_backend_meta_task(
            alias, None, fake_torch=fake_torch)
        assert selected == ['cuda:1'], (alias, selected)
        assert events == [('set_backend', 'torch', 'cuda:1')]
        assert observed[0]['backend'] == 'torch'
        assert observed[0]['device'] == 'cuda:1'


def test_torch_alias_explicit_cpu_device_is_not_overridden():
    """An explicit CPU target must bypass rank GPU binding for aliases."""
    selected = []
    fake_torch = ModuleType('torch')
    fake_torch.cuda = SimpleNamespace(
        set_device=lambda device: selected.append(device))
    events, observed = _run_backend_meta_task(
        'cuda', 'cpu', fake_torch=fake_torch)

    assert selected == []
    assert events == [('set_backend', 'torch', 'cpu')]
    assert observed[0]['backend'] == 'torch'
    assert observed[0]['device'] == 'cpu'


def test_numpy_setup_does_not_import_gpu_backends():
    """numpy setup must not import torch or cupy as a side effect."""
    imported = []
    real_import = __import__

    def reject_gpu_import(name, *args, **kwargs):
        if name == 'torch' or name == 'cupy':
            imported.append(name)
            raise AssertionError(f'unexpected {name} import')
        return real_import(name, *args, **kwargs)

    with patch('builtins.__import__', side_effect=reject_gpu_import), \
            patch.object(mpi, 'get_mpi_context',
                         return_value=(_SetupComm(), 1, 2)), \
            patch.object(
                mpi, 'detect_resources',
                side_effect=AssertionError(
                    'an explicit plan must skip resource detection')), \
            patch('pyqcd.pipeline._steps.dump_config_snapshot'), \
            patch('pyqcd.tools.set_backend') as set_backend:
        mpi.run_parallel_pipeline(
            steps=(), conf_ids=[101], run_dir='/contract/run', logger=None,
            backend='numpy', device=None, plan=_backend_plan())

    assert imported == []
    set_backend.assert_called_once_with('numpy', device=None)


def test_cli_always_delegates_dry_run_to_driver_once():
    """CLI dry-run must call the driver, which owns output and preflight."""
    observed = []
    output = io.StringIO()

    def capture_driver(**kwargs):
        observed.append(kwargs)
        print('DRIVER PLAN')
        return None, _recommended_plan()

    with patch.object(sys, 'argv', [
            'pyqcd.parallel', '--dry-run', '--steps', 'env',
            '--confs', '101,102', '--n-gpu', '2']), \
            patch.object(mpi, 'detect_resources', return_value={}), \
            patch.object(mpi, 'plan_parallel',
                         return_value=_recommended_plan()), \
            patch.object(mpi, 'run_parallel_pipeline',
                         side_effect=capture_driver), \
            patch('sys.stdout', output):
        mpi.main()

    assert len(observed) == 1
    assert observed[0]['dry_run'] is True
    assert observed[0]['steps'] == ('env',)
    assert output.getvalue() == 'DRIVER PLAN\n'


def test_cli_dry_run_propagates_driver_preflight_failure():
    """An unsupported dry-run step must not be hidden by CLI short-circuit."""
    def reject_driver(**_kwargs):
        raise RuntimeError('driver preflight failure')

    with patch.object(sys, 'argv', [
            'pyqcd.parallel', '--dry-run', '--steps', 'tmd',
            '--confs', '101,102', '--n-gpu', '0']), \
            patch.object(mpi, 'detect_resources', return_value={}), \
            patch.object(mpi, 'plan_parallel',
                         return_value={'n_gpu': 0, 'N': 2, 'm': 2, 'X': 1}), \
            patch.object(mpi, 'run_parallel_pipeline',
                         side_effect=reject_driver):
        try:
            mpi.main()
        except RuntimeError as exc:
            assert str(exc) == 'driver preflight failure'
        else:
            raise AssertionError('CLI swallowed driver preflight failure')


def test_cli_negative_gpu_is_a_usage_error_without_traceback():
    """非法用户参数应由 argparse 以 rc=2 拒绝，而非抛 Python traceback。"""
    stderr = io.StringIO()
    with patch.object(sys, 'argv', [
            'pyqcd.parallel', '--dry-run', '--confs', '101',
            '--n-gpu', '-1']), \
            patch.object(
                mpi, 'detect_resources',
                return_value=_resources(
                    n_gpu=1, cpu_threads=4, mem_avail_mb=8192.0)) as detect, \
            patch('sys.stderr', stderr):
        try:
            mpi.main()
        except SystemExit as exc:
            assert exc.code == 2, exc.code
        else:
            raise AssertionError('negative --n-gpu did not exit with usage error')

    message = stderr.getvalue()
    assert '--n-gpu' in message
    assert 'non-negative' in message
    assert 'Traceback' not in message
    detect.assert_not_called()


def test_dry_run_plan_is_logged_only_by_rank_zero():
    """MPI dry-run must not duplicate the plan line from worker ranks."""
    plan = dict(_backend_plan(), m=2)
    rank_messages = []
    for rank in (0, 1):
        with patch.object(mpi, 'get_mpi_context',
                         return_value=(_PlanningComm(), rank, 2)):
            mpi.run_parallel_pipeline(
                steps=(), conf_ids=[101, 102], logger=rank_messages.append,
                backend='numpy', plan=plan, resources={'provided': True},
                dry_run=True)
        if rank == 0:
            assert rank_messages == [f'[parallel] plan: {mpi.format_plan(plan)}']
        else:
            assert rank_messages == []
        rank_messages.clear()


def test_non_dry_custom_plan_logger_failure_still_rendezvous():
    """Non-dry custom logger failures remain collectively observable."""
    def fail_plan_logger(message):
        if message.startswith('[parallel] plan'):
            raise OSError('plan logger boom')

    with patch.object(mpi, 'get_mpi_context',
                     return_value=(_SetupComm(), 1, 2)), \
            patch.object(mpi.os, 'makedirs'), \
            patch('pyqcd.pipeline._steps.dump_config_snapshot'):
        try:
            mpi.run_parallel_pipeline(
                steps=(), conf_ids=[101, 102],
                run_dir='/contract/run', logger=fail_plan_logger,
                backend='numpy', plan=_backend_plan(),
                resources={'provided': True})
        except RuntimeError as exc:
            assert 'plan logger boom' in str(exc)
        else:
            raise AssertionError('non-dry custom logger failure was hidden')


def test_legal_dry_run_does_not_create_run_directory():
    """A valid serial dry-run remains side-effect free."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / 'not-created'
        with patch.object(mpi, 'get_mpi_context', return_value=(None, 0, 1)):
            result, plan = mpi.run_parallel_pipeline(
                steps=(), conf_ids=[101], run_dir=str(run_dir), logger=None,
                backend='numpy', plan={
                    'n_gpu': 0, 'N': 1, 'm': 1, 'X': 1, 'Y': 0,
                    'mem_ok': True,
                }, resources={'provided': True}, dry_run=True)

    assert result is None
    assert plan['N'] == 1
    assert not run_dir.exists()


def test_real_mpi_tmd_dry_run_fails_without_writing_directory():
    """The documented two-rank unsupported-tmd dry-run must exit nonzero."""
    missing = []
    if importlib.util.find_spec('mpi4py') is None:
        missing.append('mpi4py')
    if shutil.which('mpirun') is None:
        missing.append('mpirun')
    if shutil.which('timeout') is None:
        missing.append('timeout')
    if missing:
        raise unittest.SkipTest(
            'real MPI CLI contract requires: ' + ', '.join(missing))

    project_root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / 'must-not-exist'
        command = ['timeout', '8s', 'mpirun']
        if getattr(os, 'geteuid', lambda: -1)() == 0:
            command.append('--allow-run-as-root')
        command.extend([
            '-np', '2', sys.executable, '-m', 'pyqcd.parallel',
            '--dry-run', '--steps', 'tmd', '--confs', '101,102',
            '--n-gpu', '0', '--run-dir', str(run_dir),
        ])
        env = os.environ.copy()
        env['PYTHONPATH'] = os.pathsep.join(
            [str(project_root), env.get('PYTHONPATH', '')])
        completed = subprocess.run(
            command, cwd=project_root, env=env,
            capture_output=True, text=True)

    assert completed.returncode != 0, (
        'two-rank tmd dry-run unexpectedly succeeded:\n'
        + completed.stdout + completed.stderr)
    assert not run_dir.exists()


def test_mpi_empty_conf_ids_is_rejected_before_serial_call():
    """MPI entry must not silently replace [] with the default conf."""
    with tempfile.TemporaryDirectory() as tmpdir, \
            patch.object(mpi, 'get_mpi_context', return_value=(None, 0, 1)), \
            patch('pyqcd.pipeline.run_pipeline') as serial_run:
        run_dir = Path(tmpdir) / 'must-not-exist'
        try:
            mpi.run_parallel_pipeline(
                steps=(), conf_ids=[], run_dir=str(run_dir), logger=None,
                backend='numpy', plan={
                    'n_gpu': 0, 'N': 1, 'm': 1, 'X': 1, 'Y': 0,
                    'mem_ok': True,
                }, resources={'provided': True})
        except ValueError as exc:
            assert 'conf_ids' in str(exc)
        else:
            raise AssertionError('MPI conf_ids=[] was replaced by a default')

    serial_run.assert_not_called()
    assert not run_dir.exists()


def test_steps_empty_conf_ids_is_rejected_before_directory_creation():
    """Direct serial entry must reject [] before run/config output writes."""
    from pyqcd.pipeline import _steps

    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / 'must-not-exist'
        try:
            _steps.run_pipeline(
                steps=(), conf_ids=[], run_dir=str(run_dir), logger=None,
                backend='numpy')
        except ValueError as exc:
            assert 'conf_ids' in str(exc)
        else:
            raise AssertionError('steps.run_pipeline accepted conf_ids=[]')

    assert not run_dir.exists()


def test_none_conf_ids_keeps_serial_default():
    """None retains the established default configuration list."""
    from pyqcd.pipeline import _config, _steps

    observed = []
    with tempfile.TemporaryDirectory() as tmpdir, \
            patch.object(_steps, 'dump_config_snapshot',
                         side_effect=lambda config, *_args: observed.append(
                             dict(config))):
        _steps.run_pipeline(
            steps=(), conf_ids=None, run_dir=os.path.join(tmpdir, 'run'),
            logger=None, backend='numpy')

    assert observed and observed[0]['conf_ids'] == list(_config.CONF_IDS)


def test_serial_only_tmd_remains_allowed_by_mpi_entry():
    """size=1 may delegate tmd to the serial pipeline."""
    observed = []

    def capture_serial(**kwargs):
        observed.append(kwargs)
        return {'run_dir': kwargs['run_dir']}

    with patch.object(mpi, 'get_mpi_context', return_value=(None, 0, 1)), \
            patch('pyqcd.pipeline.run_pipeline', side_effect=capture_serial):
        result, plan = mpi.run_parallel_pipeline(
            steps=('tmd',), conf_ids=[101],
            run_dir='/contract/serial-tmd', logger=None, backend='numpy',
            plan={
                'n_gpu': 0, 'N': 1, 'm': 1, 'X': 1, 'Y': 0,
                'mem_ok': True,
            }, resources={'provided': True})

    assert result == {'run_dir': '/contract/serial-tmd'}
    assert observed and observed[0]['steps'] == ('tmd',)
    assert plan['N'] == 1


def test_unknown_serial_step_is_rejected_before_serial_call():
    """Unknown work must fail preflight before the serial directory path."""
    with tempfile.TemporaryDirectory() as tmpdir, \
            patch.object(mpi, 'get_mpi_context', return_value=(None, 0, 1)), \
            patch('pyqcd.pipeline.run_pipeline') as serial_run:
        run_dir = Path(tmpdir) / 'must-not-exist'
        try:
            mpi.run_parallel_pipeline(
                steps=('mystery',), conf_ids=[101],
                run_dir=str(run_dir), logger=None, backend='numpy',
                plan={
                    'n_gpu': 0, 'N': 1, 'm': 1, 'X': 1, 'Y': 0,
                    'mem_ok': True,
                }, resources={'provided': True})
        except ValueError as exc:
            assert 'mystery' in str(exc)
        else:
            raise AssertionError('unknown serial step was accepted')

    serial_run.assert_not_called()
    assert not run_dir.exists()


def test_serial_preflight_rejects_explicit_memory_failure_before_call():
    """The explicit RAM gate also applies to size-one non-dry execution."""
    with tempfile.TemporaryDirectory() as tmpdir, \
            patch.object(mpi, 'get_mpi_context', return_value=(None, 0, 1)), \
            patch('pyqcd.pipeline.run_pipeline') as serial_run:
        run_dir = Path(tmpdir) / 'must-not-exist'
        try:
            mpi.run_parallel_pipeline(
                steps=(), conf_ids=[101], run_dir=str(run_dir), logger=None,
                backend='numpy', plan={
                    'n_gpu': 0, 'N': 1, 'm': 1, 'X': 1, 'Y': 0,
                    'mem_ok': False,
                }, resources={'provided': True})
        except ValueError as exc:
            assert 'mem_ok=False' in str(exc)
        else:
            raise AssertionError('serial preflight accepted mem_ok=False')

    serial_run.assert_not_called()
    assert not run_dir.exists()


_TESTS = (
    test_size_one_returns_effective_serial_plan_without_mutating_input,
    test_size_one_dry_run_keeps_recommended_plan,
    test_plan_rejects_nonpositive_task_count,
    test_plan_recomputes_ram_status_after_caps,
    test_plan_treats_zero_available_ram_as_known_exhaustion,
    test_plan_marks_oversized_gpu_task_unusable,
    test_unknown_and_zero_gpu_budgets_are_distinct_and_fail_closed,
    test_unknown_gpu_count_is_not_reported_as_cpu_only,
    test_unknown_available_ram_is_not_replaced_by_total_ram,
    test_negative_gpu_override_is_rejected,
    test_cpu_plan_reports_unknown_per_task_vram_input,
    test_gpu_info_distinguishes_probe_failure_from_known_zero_devices,
    test_serial_fallback_recomputes_derived_resource_fields,
    test_plan_reduces_active_gpus_when_tasks_are_fewer,
    test_plan_reduces_active_gpus_when_cpu_cap_is_smaller,
    test_format_plan_reports_active_and_available_gpu_counts,
    test_gpu_formula_uses_per_gpu_memory_and_preserves_integral_force_cap,
    test_preflight_rejects_explicit_memory_failure_before_setup,
    test_preflight_rejects_explicit_gpu_failure_before_setup,
    test_preflight_rejects_explicit_cpu_failure_before_setup,
    test_preflight_rejects_structurally_inconsistent_custom_plan,
    test_cupy_binds_rank_device_before_selecting_backend,
    test_torch_aliases_bind_active_rank_gpu,
    test_torch_alias_explicit_cpu_device_is_not_overridden,
    test_numpy_setup_does_not_import_gpu_backends,
    test_cli_always_delegates_dry_run_to_driver_once,
    test_cli_dry_run_propagates_driver_preflight_failure,
    test_cli_negative_gpu_is_a_usage_error_without_traceback,
    test_dry_run_plan_is_logged_only_by_rank_zero,
    test_non_dry_custom_plan_logger_failure_still_rendezvous,
    test_legal_dry_run_does_not_create_run_directory,
    test_real_mpi_tmd_dry_run_fails_without_writing_directory,
    test_mpi_empty_conf_ids_is_rejected_before_serial_call,
    test_steps_empty_conf_ids_is_rejected_before_directory_creation,
    test_none_conf_ids_keeps_serial_default,
    test_serial_only_tmd_remains_allowed_by_mpi_entry,
    test_unknown_serial_step_is_rejected_before_serial_call,
    test_serial_preflight_rejects_explicit_memory_failure_before_call,
)
TESTS = _TESTS


def main():
    passed = 0
    for test in _TESTS:
        test()
        print(f'PASS {test.__name__}')
        passed += 1
    print(f'{passed} passed, 0 failed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
