"""Serial and MPI default run-directory contracts without filesystem writes."""

from unittest.mock import patch

import pyqcd.parallel._mpi as mpi
from pyqcd.pipeline import _config as pipeline_config
import pyqcd.pipeline._runner as runner
import pyqcd.pipeline._steps as steps
from pyqcd.pipeline import _run_dir as run_dir_module


_PLAN = {'n_gpu': 0, 'N': 2, 'm': 1, 'X': 1}


class _IndependentComm:
    """Minimal communicator for one isolated MPI job."""

    def __init__(self, rank=0, shared=None):
        self.rank = rank
        self.shared = shared if shared is not None else {'run_dir': None}
        self.sent = []

    def bcast(self, value, root=0):
        assert root == 0
        self.sent.append(value)
        if self.rank == root:
            self.shared['run_dir'] = value
        return self.shared['run_dir']

    def allgather(self, value):
        """Model a successful two-rank failure rendezvous."""
        return [value, None]

    def Barrier(self):
        return None


def _run_rank(comm, rank, run_dir=None):
    """Exercise the real MPI driver while suppressing all filesystem writes."""
    with patch.object(mpi, 'get_mpi_context',
                      return_value=(comm, rank, 2)), \
            patch.object(mpi.os, 'makedirs'), \
            patch('pyqcd.pipeline._steps.dump_config_snapshot'):
        result, _ = mpi.run_parallel_pipeline(
            steps=(), conf_ids=[6250], run_dir=run_dir, logger=None,
            backend='numpy', plan=_PLAN, resources={'provided': True})
    return result['run_dir']


def test_default_run_dirs_are_unique_across_independent_jobs_in_same_second():
    """Independent jobs must not collide when wall time and PID coincide."""
    comms = [_IndependentComm(), _IndependentComm()]
    with patch.object(mpi.time, 'strftime',
                      return_value='20260830_120000'), \
            patch.object(mpi.time, 'time_ns',
                         return_value=1788062400123456789), \
            patch.object(mpi.os, 'getpid', return_value=4242), \
            patch('secrets.token_hex',
                  side_effect=('0123456789abcdef', 'fedcba9876543210')):
        paths = [_run_rank(comm, 0) for comm in comms]

    assert paths[0] != paths[1], \
        f'independent MPI jobs selected the same default run_dir: {paths[0]}'
    assert mpi.os.path.dirname(paths[0]) == mpi.os.path.dirname(paths[1])
    assert mpi.os.path.basename(paths[0]).startswith(
        'output_20260830_120000_123456789_p4242_')
    assert mpi.os.path.basename(paths[1]).endswith('_fedcba9876543210')


def test_rank_zero_default_run_dir_is_broadcast_within_one_job():
    """All ranks in one communicator must receive rank 0's single path."""
    shared = {'run_dir': None}
    root = _IndependentComm(rank=0, shared=shared)
    worker = _IndependentComm(rank=1, shared=shared)
    with patch.object(mpi.time, 'strftime',
                      return_value='20260830_120000'), \
            patch.object(mpi.time, 'time_ns',
                         return_value=1788062400123456789), \
            patch.object(mpi.os, 'getpid', return_value=4242), \
            patch('secrets.token_hex',
                  return_value='0123456789abcdef') as token_hex:
        root_path = _run_rank(root, 0)
        worker_path = _run_rank(worker, 1)

    assert root_path == worker_path
    assert root.sent == [root_path]
    assert worker.sent == [None]
    token_hex.assert_called_once_with(8)


def test_mpi_default_run_dir_uses_dynamic_pipeline_output_root():
    """MPI must share the serial pipeline's runtime ``OUTPUT_DIR`` root."""
    comm = _IndependentComm(rank=0)
    observed_roots = []
    canonical_root = '/analysis/canonical-output'
    expected = f'{canonical_root}/reserved-job'

    def reserve(root):
        observed_roots.append(root)
        return expected

    with patch.object(pipeline_config, 'OUTPUT_DIR', canonical_root), \
            patch.object(mpi, 'reserve_unique_run_dir', side_effect=reserve):
        actual = _run_rank(comm, 0)

    assert observed_roots == [canonical_root]
    assert actual == expected
    assert comm.sent == [expected]


def test_explicit_run_dir_is_broadcast_unchanged():
    """An explicit run_dir remains byte-for-byte unchanged on every rank."""
    shared = {'run_dir': None}
    root = _IndependentComm(rank=0, shared=shared)
    worker = _IndependentComm(rank=1, shared=shared)
    explicit = '/analysis/user-selected-run'

    with patch('secrets.token_hex') as token_hex:
        root_path = _run_rank(root, 0, run_dir=explicit)
        worker_path = _run_rank(worker, 1, run_dir=explicit)

    assert root_path == explicit
    assert worker_path == explicit
    assert root.sent == [explicit]
    assert worker.sent == [None]
    token_hex.assert_not_called()


def test_default_run_tag_rejects_path_components_before_writing():
    """展示标签只能是 basename，不能把默认目录带出 output_root。"""
    with patch.object(run_dir_module.os, 'makedirs') as makedirs:
        try:
            run_dir_module.reserve_unique_run_dir(
                '/analysis/output', tag='../../../escaped')
        except ValueError as exc:
            assert 'tag' in str(exc)
        else:
            raise AssertionError('路径型 tag 未被拒绝')

    makedirs.assert_not_called()


def test_runner_default_run_dirs_are_unique_within_same_second():
    """The public serial directory factory must not reuse a concurrent path."""
    with patch('time.strftime', return_value='20260830_120000'), \
            patch('time.time_ns', return_value=1788062400123456789), \
            patch('os.getpid', return_value=4242), \
            patch('os.makedirs'), \
            patch('secrets.token_hex',
                  side_effect=('0123456789abcdef', 'fedcba9876543210')):
        paths = [runner.make_run_dir() for _ in range(2)]

    assert paths[0] != paths[1], \
        f'public serial factory reused default run_dir: {paths[0]}'
    assert runner.os.path.basename(paths[0]).startswith(
        'output_20260830_120000_123456789_p4242_')
    assert runner.os.path.basename(paths[1]).endswith('_fedcba9876543210')


def test_steps_default_run_dirs_are_unique_within_same_second():
    """The direct ``_steps.run_pipeline`` entry must share the unique policy."""
    fixed_datetime = type('FixedDateTime', (), {
        'now': classmethod(lambda cls: type('Now', (), {
            'strftime': lambda self, fmt: '20260830_120000',
        })()),
    })
    with patch('time.strftime', return_value='20260830_120000'), \
            patch('time.time_ns', return_value=1788062400123456789), \
            patch('os.getpid', return_value=4242), \
            patch('os.makedirs'), \
            patch('secrets.token_hex',
                  side_effect=('0123456789abcdef', 'fedcba9876543210')), \
            patch.object(steps, 'datetime', fixed_datetime), \
            patch.object(steps, 'dump_config_snapshot'):
        paths = [
            steps.run_pipeline(
                steps=(), conf_ids=[6250], logger=None, backend='numpy',
            )['run_dir']
            for _ in range(2)
        ]

    assert paths[0] != paths[1], \
        f'direct serial pipeline reused default run_dir: {paths[0]}'
    assert steps.os.path.basename(paths[0]).startswith(
        'output_20260830_120000_123456789_p4242_')
    assert steps.os.path.basename(paths[1]).endswith('_fedcba9876543210')


def main():
    tests = (
        test_default_run_dirs_are_unique_across_independent_jobs_in_same_second,
        test_rank_zero_default_run_dir_is_broadcast_within_one_job,
        test_mpi_default_run_dir_uses_dynamic_pipeline_output_root,
        test_explicit_run_dir_is_broadcast_unchanged,
        test_default_run_tag_rejects_path_components_before_writing,
        test_runner_default_run_dirs_are_unique_within_same_second,
        test_steps_default_run_dirs_are_unique_within_same_second,
    )
    for test in tests:
        test()
        print(f'PASS {test.__name__}')
    print(f'{len(tests)} passed, 0 failed')


if __name__ == '__main__':
    main()
