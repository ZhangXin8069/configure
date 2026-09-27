"""真实双 rank 的 MPI collective failure 契约。

逐场景运行示例::

    timeout 6s mpirun --allow-run-as-root -np 2 \
        python -m pyqcd.testing._mpi_failure_contract run-dir
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from pyqcd.parallel import _mpi as mpi


_PLAN = {'n_gpu': 0, 'N': 2, 'm': 2, 'X': 1}
_EXPECTED = {
    'run-dir': ('phase=run-dir', 'rank=0', 'type=OSError',
                'message=reserve boom'),
    'setup': ('phase=setup', 'rank=1', 'type=OSError',
              'message=setup boom'),
    'meta-task': ('phase=meta-task:vertex', 'rank=1',
                  'type=LookupError', 'message=task boom'),
    'meta-task-base': ('phase=meta-task:vertex', 'rank=1',
                       'type=KeyboardInterrupt',
                       'message=interrupt boom'),
    'step-log': ('phase=step-log:vertex', 'rank=0', 'type=OSError',
                 'message=step logger boom'),
    'completion-log': ('phase=completion-log', 'rank=0', 'type=OSError',
                       'message=completion logger boom'),
    'plan-log': ('phase=preflight', 'rank=1', 'type=OSError',
                 'message=plan logger boom'),
    'postprocess': ('phase=postprocess:analysis', 'rank=0',
                    'type=RuntimeError', 'message=analysis boom'),
    'unsupported-tmd': ('phase=preflight', 'type=NotImplementedError',
                        "MPI step 'tmd' is not supported"),
    'unknown-step': ('phase=preflight', 'type=ValueError',
                     'unknown MPI pipeline step(s): mystery'),
    'plan-size': ('phase=preflight', 'type=ValueError',
                  'plan process count N=3 does not match communicator size=2'),
}
_SUCCESS_SCENARIOS = ('step-barrier', 'final-barrier')


class _BarrierFaultProxy:
    """Inject a one-rank Barrier failure while preserving other collectives."""

    def __init__(self, comm, rank):
        self._comm = comm
        self._rank = rank

    def __getattr__(self, name):
        return getattr(self._comm, name)

    def Barrier(self):
        if self._rank == 0:
            raise OSError('barrier boom')
        return self._comm.Barrier()


def _run_scenario(scenario: str) -> None:
    """触发一个 rank 局部失败，并验证所有 rank 收到同一摘要。"""
    from mpi4py import MPI

    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    if comm.Get_size() != 2:
        raise AssertionError('contract requires exactly 2 MPI ranks')

    steps = ()
    conf_ids = [101, 102]
    run_dir = '/contract/explicit-run'
    logger = None
    plan = _PLAN

    with ExitStack() as stack:
        if scenario in _SUCCESS_SCENARIOS:
            proxy = _BarrierFaultProxy(comm, rank)
            stack.enter_context(patch.object(
                mpi, 'get_mpi_context', return_value=(proxy, rank, 2)))
        if scenario == 'setup':
            def fail_setup_on_rank_one(*_args, **_kwargs):
                if rank == 1:
                    raise OSError('setup boom')

            stack.enter_context(patch.object(
                mpi.os, 'makedirs', side_effect=fail_setup_on_rank_one))
        else:
            stack.enter_context(patch.object(mpi.os, 'makedirs'))
        stack.enter_context(
            patch('pyqcd.pipeline._steps.dump_config_snapshot'))

        if scenario == 'run-dir':
            run_dir = None
            stack.enter_context(patch.object(
                mpi, 'reserve_unique_run_dir',
                side_effect=OSError('reserve boom')))
        elif scenario == 'setup':
            pass
        elif scenario in ('meta-task', 'meta-task-base'):
            steps = ('vertex',)

            def fail_on_rank_one(*_args, **_kwargs):
                if rank == 1:
                    if scenario == 'meta-task-base':
                        raise KeyboardInterrupt('interrupt boom')
                    raise LookupError('task boom')
                return 0.0

            stack.enter_context(
                patch.object(mpi, 'run_meta_task', fail_on_rank_one))
        elif scenario == 'step-log':
            steps = ('vertex',)
            stack.enter_context(
                patch.object(mpi, 'run_meta_task', return_value=0.0))

            def fail_rank_zero_step_log(message):
                if rank == 0 and message.startswith('STEP vertex done'):
                    raise OSError('step logger boom')

            logger = fail_rank_zero_step_log
        elif scenario == 'completion-log':
            def fail_rank_zero_completion_log(message):
                if rank == 0 and message.startswith('[parallel] pipeline done'):
                    raise OSError('completion logger boom')

            logger = fail_rank_zero_completion_log
        elif scenario == 'plan-log':
            def fail_rank_one_plan_log(message):
                if rank == 1 and message.startswith('[parallel] plan'):
                    raise OSError('plan logger boom')

            logger = fail_rank_one_plan_log
        elif scenario == 'postprocess':
            steps = ('analysis',)
            stack.enter_context(patch(
                'pyqcd.pipeline._steps.step_analysis',
                side_effect=RuntimeError('analysis boom')))
        elif scenario == 'unsupported-tmd':
            steps = ('tmd',)
        elif scenario == 'unknown-step':
            steps = ('mystery',)
        elif scenario == 'plan-size':
            plan = dict(_PLAN, N=3)
        elif scenario == 'step-barrier':
            steps = ('vertex',)
            stack.enter_context(
                patch.object(mpi, 'run_meta_task', return_value=0.0))
        elif scenario == 'final-barrier':
            pass
        else:  # argparse choices make this unreachable from the CLI.
            raise AssertionError(f'unknown scenario: {scenario}')

        observed = None
        try:
            mpi.run_parallel_pipeline(
                steps=steps, conf_ids=conf_ids, run_dir=run_dir,
                logger=logger, backend='numpy', plan=plan,
                resources={'provided': True})
        except BaseException as exc:  # contract inspects rank boundary
            observed = f'{type(exc).__name__}: {exc}'

    if scenario == 'setup' and observed == 'OSError: setup boom':
        # Keep the failed rank alive so the pre-fix peer remains visibly
        # blocked in its next production collective until the outer timeout.
        time.sleep(30)

    all_observed = comm.allgather(observed)
    if scenario in _SUCCESS_SCENARIOS:
        assert all(message is None for message in all_observed), \
            f'unprotected barrier escaped production flow: {all_observed}'
        if rank == 0:
            print(f'PASS {scenario}: no naked Barrier call', flush=True)
        return
    assert all(message is not None for message in all_observed), \
        f'not every rank raised: {all_observed}'
    assert len(set(all_observed)) == 1, \
        f'ranks received different failures: {all_observed}'
    for fragment in _EXPECTED[scenario]:
        assert fragment in all_observed[0], \
            f'missing {fragment!r} in {all_observed[0]!r}'

    if rank == 0:
        print(f'PASS {scenario}: {all_observed[0]}', flush=True)


def test_mpi_collective_failure_contracts() -> None:
    """从普通测试进程启动真实双 rank，确保四类异常不会永久阻塞。"""
    missing = []
    if importlib.util.find_spec('mpi4py') is None:
        missing.append('mpi4py')
    if shutil.which('mpirun') is None:
        missing.append('mpirun')
    if shutil.which('timeout') is None:
        missing.append('timeout')
    if missing:
        raise unittest.SkipTest(
            'MPI collective failure contract requires: '
            + ', '.join(missing))

    project_root = Path(__file__).resolve().parents[2]
    scenarios = tuple(_EXPECTED) + _SUCCESS_SCENARIOS
    for scenario in scenarios:
        fragments = _EXPECTED.get(
            scenario, (f'PASS {scenario}: no naked Barrier call',))
        command = ['timeout', '8s', 'mpirun']
        if getattr(os, 'geteuid', lambda: -1)() == 0:
            command.append('--allow-run-as-root')
        command.extend([
            '-np', '2', sys.executable, '-m',
            'pyqcd.testing._mpi_failure_contract', scenario,
        ])
        completed = subprocess.run(
            command, cwd=project_root, capture_output=True, text=True)
        combined = completed.stdout + completed.stderr
        assert completed.returncode == 0, \
            f"MPI {scenario} contract failed rc={completed.returncode}:\n{combined}"
        for fragment in fragments:
            assert fragment in combined, \
                f"MPI {scenario} missing {fragment!r}:\n{combined}"


def test_missing_mpi_prerequisites_raise_skiptest() -> None:
    """Each absent launcher dependency is an explicit skip, never a pass."""
    cases = (
        ('mpi4py', None, {'mpirun': '/usr/bin/mpirun',
                          'timeout': '/usr/bin/timeout'}),
        ('mpirun', object(), {'mpirun': None,
                              'timeout': '/usr/bin/timeout'}),
        ('timeout', object(), {'mpirun': '/usr/bin/mpirun',
                              'timeout': None}),
    )
    for expected, mpi4py_spec, executables in cases:
        with patch.object(importlib.util, 'find_spec',
                          return_value=mpi4py_spec), \
                patch.object(shutil, 'which',
                             side_effect=lambda name: executables[name]):
            try:
                test_mpi_collective_failure_contracts()
            except unittest.SkipTest as exc:
                assert expected in str(exc)
            else:
                raise AssertionError(
                    f'missing {expected} was silently treated as PASS')


def test_standalone_main_reports_skip_without_pass() -> None:
    """Direct no-scenario execution reports SKIP and exits successfully."""
    from contextlib import redirect_stdout
    import io

    output = io.StringIO()
    with patch.object(
            sys.modules[__name__], 'test_mpi_collective_failure_contracts',
            side_effect=unittest.SkipTest('missing MPI runtime')), \
            redirect_stdout(output):
        status = main([])

    rendered = output.getvalue()
    assert status == 0
    assert 'SKIP' in rendered
    assert 'PASS' not in rendered


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='PyQCD MPI collective failure contract')
    parser.add_argument(
        'scenario', nargs='?',
        choices=tuple(_EXPECTED) + _SUCCESS_SCENARIOS)
    args = parser.parse_args(argv)
    if args.scenario is not None:
        _run_scenario(args.scenario)
        return 0

    try:
        test_mpi_collective_failure_contracts()
    except unittest.SkipTest as exc:
        print(f'SKIP test_mpi_collective_failure_contracts: {exc}')
        return 0
    print('PASS test_mpi_collective_failure_contracts')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
