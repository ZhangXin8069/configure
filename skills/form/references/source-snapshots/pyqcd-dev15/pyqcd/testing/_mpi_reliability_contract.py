"""Focused fake-communicator contracts for MPI driver reliability."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock, patch

import h5py
import numpy as np

import pyqcd.parallel._mpi as mpi


_PLAN = {'n_gpu': 0, 'N': 2, 'm': 1, 'X': 1}


def _write_valid_2pt_h5_cache(run_dir, conf_id=101):
    """Write the minimal canonical cache consumed by the real serial gate."""
    cdir = Path(run_dir) / 'data' / f'conf{conf_id}'
    cdir.mkdir(parents=True)
    for momentum in ('P0', 'P2'):
        path = cdir / f'corr_pp_{momentum}_{conf_id}.h5'
        with h5py.File(path, 'w') as handle:
            handle.create_dataset(
                'data', data=np.zeros(72, dtype=np.float64))


def _run_real_serial_fallback(run_dir, recompute_2pt):
    """Run public MPI size-one fallback through the real serial pipeline."""
    serial_plan = dict(_PLAN, N=1)
    with patch.object(mpi, 'get_mpi_context',
                      return_value=(None, 0, 1)):
        result, returned_plan = mpi.run_parallel_pipeline(
            steps=('2pt',), conf_ids=[101], run_dir=str(run_dir),
            logger=None, backend='numpy', channels=('pp',),
            plan=serial_plan, resources={'provided': True},
            recompute_2pt=recompute_2pt)
    with (Path(run_dir) / 'run_config.json').open(
            encoding='utf-8') as handle:
        config = json.load(handle)
    return result, returned_plan, serial_plan, config


class _TwoRankComm:
    """One-process model of matching status from two MPI ranks."""

    def __init__(self):
        self.gathered = []

    def allgather(self, value):
        self.gathered.append(value)
        return [value, value]

    def bcast(self, value, root=0):
        assert root == 0
        return value

    def Barrier(self):
        return None


def _run_rank_zero(*, steps=(), plan=None, makedirs_spy=None, **kwargs):
    """Run the real MPI driver with all filesystem setup suppressed."""
    comm = _TwoRankComm()
    makedirs = makedirs_spy or Mock(name='makedirs')
    with patch.object(mpi, 'get_mpi_context',
                      return_value=(comm, 0, 2)), \
            patch.object(mpi.os, 'makedirs', makedirs), \
            patch('pyqcd.pipeline._steps.dump_config_snapshot'):
        result = mpi.run_parallel_pipeline(
            steps=steps, conf_ids=[101],
            run_dir='/contract/explicit-run', logger=None,
            backend='numpy', plan=plan or _PLAN,
            resources={'provided': True}, **kwargs)
    return result, comm, makedirs


def _assert_collective_preflight_failure(steps, expected, *, plan=None):
    makedirs = Mock(name='preflight_makedirs')
    try:
        _run_rank_zero(
            steps=steps, plan=plan, makedirs_spy=makedirs)
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError(
            f'MPI preflight accepted invalid request steps={steps!r} '
            f'plan={plan!r}')

    assert 'phase=preflight' in message
    assert expected in message
    assert not makedirs.called, 'preflight failure occurred after setup writes'


def test_collective_preflight_rejects_tmd_and_unknown_steps():
    """MPI must reject unsupported and unknown work instead of empty success."""
    _assert_collective_preflight_failure(
        ('tmd',), "MPI step 'tmd' is not supported")
    _assert_collective_preflight_failure(
        ('mystery',), 'unknown MPI pipeline step(s): mystery')


def test_collective_preflight_rejects_plan_size_mismatch():
    """A plan for three ranks cannot execute on a two-rank communicator."""
    bad_plan = dict(_PLAN, N=3)
    _assert_collective_preflight_failure(
        (), 'plan process count N=3 does not match communicator size=2',
        plan=bad_plan)


def test_env_step_reaches_rank_zero_report_with_serial_fields():
    """MPI ``env`` has rank-zero semantics and supplies report metadata."""
    observed = []

    def capture_report(_config, _run_dir, _logger, _meff, _timing, env):
        observed.append(env)
        return env

    with patch('pyqcd.pipeline._steps.step_report', capture_report):
        (result, _plan), _comm, _makedirs = _run_rank_zero(
            steps=('env', 'report'), precision='complex128')

    assert observed == [{
        'conf_ids': [101],
        'precision': 'complex128',
        'nx': 24,
        'nt': 72,
        'gauge_dir': (
            '/public/group/lqcd/configurations/CLOVER/'
            'beta6.20_mu-0.2770_ms-0.2400_L24x72'
        ),
    }]
    assert result['summary'] == observed[0]


def _assert_primary_survives_cleanup(primary):
    cleanup_events = []

    def fail_compute(*_args, **_kwargs):
        raise primary

    def fail_free():
        cleanup_events.append('free_gpu_memory')
        raise OSError('free cleanup boom')

    def fail_collect():
        cleanup_events.append('gc.collect')
        raise SystemExit('gc cleanup boom')

    with patch('pyqcd.pipeline._steps.compute_vertices_for_config',
               fail_compute), \
            patch('pyqcd.pipeline._steps.free_gpu_memory', fail_free), \
            patch.object(mpi.gc, 'collect', fail_collect):
        try:
            mpi.run_meta_task(
                'vertex', 101, {'precision': 'complex64'},
                '/contract/run', None)
        except BaseException as observed:
            assert observed is primary, \
                f'cleanup replaced {primary!r} with {observed!r}'
        else:
            raise AssertionError(f'primary exception was swallowed: {primary!r}')

    assert cleanup_events == ['free_gpu_memory', 'gc.collect']


def test_run_meta_task_preserves_primary_exception_during_cleanup():
    """Ordinary computation failures survive both failing cleanup actions."""
    _assert_primary_survives_cleanup(LookupError('primary task boom'))


def test_run_meta_task_preserves_primary_baseexception_during_cleanup():
    """KeyboardInterrupt survives both failing cleanup actions unchanged."""
    _assert_primary_survives_cleanup(KeyboardInterrupt('primary interrupt'))


def test_run_meta_task_cleanup_is_best_effort_after_success():
    """Cleanup-only failures do not turn a successful task into failure."""
    cleanup_events = []

    def fail_free():
        cleanup_events.append('free_gpu_memory')
        raise OSError('free cleanup boom')

    def fail_collect():
        cleanup_events.append('gc.collect')
        raise SystemExit('gc cleanup boom')

    with patch('pyqcd.pipeline._steps.compute_vertices_for_config'), \
            patch('pyqcd.pipeline._steps.free_gpu_memory', fail_free), \
            patch.object(mpi.gc, 'collect', fail_collect):
        elapsed = mpi.run_meta_task(
            'vertex', 101, {'precision': 'complex64'},
            '/contract/run', None)

    assert elapsed >= 0.0
    assert cleanup_events == ['free_gpu_memory', 'gc.collect']


def test_mpi_2pt_cache_skips_unless_recompute_is_true():
    """The MPI meta-task uses the same complete-cache gate as ``step_2pt``."""
    computed_modes = []
    mode = {'name': None}

    def fake_compute(*_args, **_kwargs):
        computed_modes.append(mode['name'])

    with tempfile.TemporaryDirectory() as tmpdir:
        cdir = Path(tmpdir) / 'data' / 'conf101'
        cdir.mkdir(parents=True)
        for momentum in ('P0', 'P2'):
            np.save(cdir / f'corr_pp_{momentum}_101.npy',
                    np.zeros(72, dtype=np.float64))

        base_config = {
            'precision': 'complex64',
            'channels': ('pp',),
            'conf_ids': [101],
            'backend': 'numpy',
            'device': None,
        }
        with patch('pyqcd.pipeline._steps._load_vertices_one',
                   return_value={'vertices': 'sentinel'}), \
                patch('pyqcd.pipeline._steps.compute_2pt_for_config',
                      fake_compute), \
                patch('pyqcd.pipeline._steps.free_gpu_memory'):
            mode['name'] = 'cached-default'
            mpi.run_meta_task(
                '2pt', 101, dict(base_config, recompute_2pt=False),
                tmpdir, None)
            mode['name'] = 'forced-recompute'
            mpi.run_meta_task(
                '2pt', 101, dict(base_config, recompute_2pt=True),
                tmpdir, None)

    assert computed_modes == ['forced-recompute']


def test_parallel_driver_propagates_recompute_2pt_to_meta_tasks():
    """The public MPI option reaches each per-configuration 2pt config."""
    observed = []

    def capture_config(step, _cid, config, _run_dir, _logger):
        if step == '2pt':
            observed.append(config.get('recompute_2pt'))
        return 0.0

    with patch.object(mpi, 'run_meta_task', capture_config):
        _run_rank_zero(steps=('2pt',), recompute_2pt=True)

    assert observed == [True]


def test_parallel_driver_does_not_repeat_meta_task_cleanup():
    """A cleanup-only failure outside run_meta_task must not fail the job."""
    cleanup_calls = []

    def fail_redundant_cleanup():
        cleanup_calls.append('free_gpu_memory')
        raise OSError('cleanup-only boom')

    with patch.object(mpi, 'run_meta_task', return_value=0.0), \
            patch('pyqcd.pipeline._steps.free_gpu_memory',
                  side_effect=fail_redundant_cleanup):
        result, _, _ = _run_rank_zero(steps=('vertex',))

    assert result[0]['run_dir'] == '/contract/explicit-run'
    assert cleanup_calls == []


def test_parallel_driver_has_no_unprotected_barrier_collectives():
    """Failure rendezvous already synchronizes ranks; naked barriers may hang."""
    with patch.object(
            _TwoRankComm, 'Barrier',
            side_effect=AssertionError('unprotected Barrier called'),
    ), patch.object(mpi, 'run_meta_task', return_value=0.0):
        _run_rank_zero(steps=('vertex',))
        _run_rank_zero(steps=())


def test_serial_fallback_propagates_recompute_override():
    """The size-one fallback forwards forced recomputation to serial code."""
    serial_plan = dict(_PLAN, N=1)
    observed = []

    def capture_serial(**kwargs):
        observed.append(kwargs.get('recompute_2pt'))
        return {'run_dir': kwargs['run_dir']}

    with patch.object(mpi, 'get_mpi_context',
                      return_value=(None, 0, 1)), \
            patch('pyqcd.pipeline.run_pipeline', capture_serial):
        result, returned_plan = mpi.run_parallel_pipeline(
                steps=('2pt',), conf_ids=[101],
                run_dir='/contract/explicit-run', logger=None,
                backend='numpy', plan=serial_plan,
                resources={'provided': True}, recompute_2pt=True)

    assert observed == [True]
    assert result == {'run_dir': '/contract/explicit-run'}
    assert returned_plan is serial_plan


def test_serial_fallback_real_pipeline_reuses_cache_when_recompute_is_false():
    """Size-one public fallback reuses valid HDF5 and records JSON false."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / 'reuse'
        _write_valid_2pt_h5_cache(run_dir)
        cache_miss = AssertionError(
            'recompute_2pt=False unexpectedly bypassed valid HDF5 cache')
        with patch('pyqcd.pipeline._steps._load_vertices_one',
                   side_effect=cache_miss), \
                patch('pyqcd.pipeline._steps.compute_2pt_for_config',
                      side_effect=cache_miss):
            result, returned_plan, serial_plan, config = \
                _run_real_serial_fallback(run_dir, recompute_2pt=False)

    assert result['run_dir'] == str(run_dir)
    assert returned_plan is serial_plan
    assert config['recompute_2pt'] is False


def test_serial_fallback_real_pipeline_recomputes_when_override_is_true():
    """Size-one public fallback bypasses valid HDF5 and records JSON true."""
    computed = []

    def capture_compute(conf_id, run_dir, _logger, vertices,
                        precision, channels):
        computed.append((conf_id, run_dir, vertices,
                         precision, tuple(channels)))
        return {}

    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / 'force'
        _write_valid_2pt_h5_cache(run_dir)
        vertices = {'vertices': 'sentinel'}
        with patch('pyqcd.pipeline._steps._load_vertices_one',
                   return_value=vertices), \
                patch('pyqcd.pipeline._steps.compute_2pt_for_config',
                      side_effect=capture_compute):
            result, returned_plan, serial_plan, config = \
                _run_real_serial_fallback(run_dir, recompute_2pt=True)

    assert result['run_dir'] == str(run_dir)
    assert returned_plan is serial_plan
    expected_compute = [
        (101, str(run_dir), vertices, 'complex64', ('pp',)),
    ]
    assert computed == expected_compute, (
        'size-one fallback did not force 2pt recomputation; '
        f'observed {computed!r}')
    assert config['recompute_2pt'] is True


def test_cli_recompute_2pt_flag_is_forwarded():
    """The MPI CLI exposes forced 2pt recomputation without hidden defaults."""
    observed = []

    def capture_run(**kwargs):
        observed.append(kwargs.get('recompute_2pt'))
        return None, _PLAN

    with patch.object(sys, 'argv', [
            'pyqcd.parallel', '--steps', '2pt', '--recompute-2pt']), \
            patch.object(mpi, 'detect_resources', return_value={}), \
            patch.object(mpi, 'plan_parallel', return_value=_PLAN), \
            patch.object(mpi, 'run_parallel_pipeline', capture_run):
        mpi.main()

    assert observed == [True]


def main():
    tests = (
        test_collective_preflight_rejects_tmd_and_unknown_steps,
        test_collective_preflight_rejects_plan_size_mismatch,
        test_env_step_reaches_rank_zero_report_with_serial_fields,
        test_run_meta_task_preserves_primary_exception_during_cleanup,
        test_run_meta_task_preserves_primary_baseexception_during_cleanup,
        test_run_meta_task_cleanup_is_best_effort_after_success,
        test_mpi_2pt_cache_skips_unless_recompute_is_true,
        test_parallel_driver_propagates_recompute_2pt_to_meta_tasks,
        test_parallel_driver_does_not_repeat_meta_task_cleanup,
        test_parallel_driver_has_no_unprotected_barrier_collectives,
        test_serial_fallback_propagates_recompute_override,
        test_serial_fallback_real_pipeline_reuses_cache_when_recompute_is_false,
        test_serial_fallback_real_pipeline_recomputes_when_override_is_true,
        test_cli_recompute_2pt_flag_is_forwarded,
    )
    for test in tests:
        test()
        print(f'PASS {test.__name__}')
    print(f'{len(tests)} passed, 0 failed')


if __name__ == '__main__':
    main()
