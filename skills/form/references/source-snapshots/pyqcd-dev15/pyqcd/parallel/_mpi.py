"""
MPI Parallel Execution for pyqcd
================================

Task-parallel execution of the pipeline across MPI processes, following
the user's resource formula:

    N * a  = n * b        (N processes x per-task VRAM = total usable VRAM)
    X      = m / N        (number of batches; each batch submits X tasks)
    Y      = N / n        (integer; Y processes per GPU)

where
- ``a`` : VRAM needed by one meta-task (smallest independent unit)
- ``m`` : total number of meta-tasks
- ``b`` : usable VRAM per GPU (default 80% of card capacity)
- ``n`` : number of GPUs

Meta-tasks are the per-configuration compute steps (vertex / 2pt / ope /
3pt / 4pt); each writes its own HDF5 files under ``data/conf<id>/`` so
ranks never share mutable state. Analysis / plotting / report steps stay
serial on rank 0 (light CPU work, as agreed).

Meta-task scheduling: round-robin static partitioning (rank r handles
conf_ids[r::N]). Collective status exchanges are the synchronization points;
there are no unprotected barriers that can strand healthy ranks after a peer
fails.
Memory is released automatically after each meta-task
(``del`` + ``torch.cuda.empty_cache`` + ``gc.collect``).
"""

import gc
import math
import os
import time

from ._resources import detect_resources
from ..pipeline._run_dir import reserve_unique_run_dir

# ═══════════════════════════════════════════════════════════════════
# MPI context
# ═══════════════════════════════════════════════════════════════════

_MPI_LAUNCH_ENV = (
    'OMPI_COMM_WORLD_SIZE', 'PMI_SIZE', 'PMI_RANK', 'PMIX_RANK',
    'MV2_COMM_WORLD_SIZE', 'MV2_COMM_WORLD_RANK',
)

_MPI_PARALLEL_STEPS = frozenset(('vertex', '2pt', 'ope', '3pt', '4pt'))
_MPI_RANK_ZERO_STEPS = frozenset(('env', 'analysis', 'plots', 'report'))
_MPI_SUPPORTED_STEPS = _MPI_PARALLEL_STEPS | _MPI_RANK_ZERO_STEPS


def get_mpi_context():
    """Return (comm, rank, size) if running under MPI, else (None, 0, 1)."""
    try:
        from mpi4py import MPI
        comm = MPI.COMM_WORLD
        return comm, comm.Get_rank(), comm.Get_size()
    except Exception as exc:
        launch_markers = [name for name in _MPI_LAUNCH_ENV
                          if name in os.environ]
        if launch_markers:
            markers = ', '.join(launch_markers)
            raise RuntimeError(
                'MPI launcher detected via '
                f'{markers}, but mpi4py initialization failed') from exc
        return None, 0, 1


def _failure_summary(phase, rank, exc):
    """Build a communicator-safe summary without serializing ``exc``."""
    try:
        message = str(exc)
    except BaseException:
        message = '<exception message unavailable>'
    return {
        'phase': str(phase),
        'rank': int(rank),
        'type': type(exc).__name__,
        'message': message,
    }


def _collective_failure_rendezvous(comm, local_failure):
    """Raise the same aggregate failure after every rank reports status.

    Real MPI communicators provide ``allgather``.  The one-entry fallback
    keeps serial ``DummyComm`` and legacy normal-path fakes usable; those
    communicators cannot model a multi-rank failure rendezvous themselves.
    """
    if hasattr(comm, 'allgather'):
        reported = comm.allgather(local_failure)
    else:
        reported = [local_failure]
    failures = [item for item in reported if item is not None]
    if not failures:
        return
    details = '; '.join(
        f"phase={item['phase']} rank={item['rank']} type={item['type']} "
        f"message={item['message']}"
        for item in failures
    )
    raise RuntimeError(f'MPI collective failure: {details}')


def _validate_mpi_preflight(steps, plan, size):
    """Validate work that every rank must agree can execute safely."""
    def plan_int(name, *, minimum):
        value = plan.get(name)
        if (isinstance(value, bool) or not isinstance(value, int)
                or value < minimum):
            raise ValueError(
                f"MPI plan {name} must be an integer >= {minimum}")
        return value

    planned_size = plan_int('N', minimum=1)
    task_count = plan_int('m', minimum=1)
    batch_count = plan_int('X', minimum=1)
    gpu_count = plan_int('n_gpu', minimum=0)
    expected_batches = math.ceil(task_count / planned_size)
    if batch_count != expected_batches:
        raise ValueError(
            f'MPI plan X={batch_count} must equal ceil(m/N)='
            f'{expected_batches}')
    planned_y = plan.get('Y')
    if gpu_count > 0:
        if (isinstance(planned_y, bool)
                or not isinstance(planned_y, int) or planned_y < 1):
            raise ValueError('MPI GPU plan Y must be a positive integer')
        if planned_size != planned_y * gpu_count:
            raise ValueError(
                f'MPI plan N={planned_size} must equal '
                f'Y*n_gpu={planned_y * gpu_count}')
    elif planned_y is not None and planned_y != 0:
        raise ValueError('MPI CPU plan Y must be 0 when provided')
    available_gpu_count = plan.get('n_gpu_available')
    if (available_gpu_count is not None
            and (isinstance(available_gpu_count, bool)
                 or not isinstance(available_gpu_count, int)
                 or available_gpu_count < gpu_count)):
        raise ValueError(
            'MPI plan n_gpu exceeds its recorded n_gpu_available')

    if 'tmd' in steps and size > 1:
        raise NotImplementedError(
            "MPI step 'tmd' is not supported; its current pipeline "
            'implementation consumes one in-memory gauge field and has no '
            'safe per-rank output contract')
    supported = (_MPI_SUPPORTED_STEPS | {'tmd'}) if size <= 1 \
        else _MPI_SUPPORTED_STEPS
    unknown = sorted(set(steps) - supported)
    if unknown:
        raise ValueError(
            'unknown MPI pipeline step(s): ' + ', '.join(map(str, unknown)))
    if plan.get('mem_ok') is False:
        raise ValueError('MPI plan mem_ok=False; refusing to create run directory')
    if plan.get('gpu_ok') is False:
        raise ValueError('MPI plan gpu_ok=False; refusing to create run directory')
    if plan.get('cpu_ok') is False:
        raise ValueError('MPI plan cpu_ok=False; refusing to create run directory')
    if size > 1 and planned_size != size:
        raise ValueError(
            f'MPI plan process count N={planned_size} does not match '
            f'communicator size={size}')


# ═══════════════════════════════════════════════════════════════════
# Parallel plan (user formula)
# ═══════════════════════════════════════════════════════════════════

def plan_parallel(m, a_mem_mb, resources=None, n_gpu=None, force_y=None,
                  verbose=True):
    """Plan the MPI process count from the user formula N*a = n*b.

    Parameters
    ----------
    m : int
        Number of meta-tasks (e.g. len(conf_ids) x compute steps).
    a_mem_mb : float
        VRAM needed by one meta-task (MB). If None/0, defaults to one
        process per GPU (Y=1).
    resources : dict, optional
        Output of ``detect_resources()``. Auto-detected if None.
    n_gpu : int, optional
        Override GPU count.
    force_y : int, optional
        Force Y (processes per GPU); N = Y*n (still capped by cpu/mem).

    Returns
    -------
    dict with keys: n_gpu, b_mb, gpu_total_mb, a_mb, m, N, Y, X,
    per_rank_vram_mb, cpu_ok, mem_ok, gpu_ok, notes.
    """
    if m <= 0:
        raise ValueError('m must be positive')
    res = resources if resources is not None else detect_resources()
    if a_mem_mb is None:
        a = None
    else:
        a = float(a_mem_mb)
        if not math.isfinite(a):
            raise ValueError('a_mem_mb must be finite when provided')
        if a == 0.0:
            a = None
    if a is not None and a < 0.0:
        raise ValueError('a_mem_mb must be non-negative')

    cpu_limit = max(1, int(res.get('cpu_threads') or 1))

    def gpu_count(value, name):
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValueError(f'{name} must be a non-negative integer')
        try:
            converted = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f'{name} must be a non-negative integer') from exc
        if converted < 0 or converted != value:
            raise ValueError(f'{name} must be a non-negative integer')
        return converted

    available_n = gpu_count(res.get('n_gpu'), 'resources n_gpu')
    requested_n = (available_n if n_gpu is None
                   else gpu_count(n_gpu, 'n_gpu'))
    gpu_count_unknown = available_n is None and requested_n is None
    if requested_n is None:
        n = 0
    elif available_n is None:
        n = requested_n
    else:
        n = min(requested_n, available_n)
    b_value = res.get('gpu_usable_mb')
    b = float(b_value) if b_value is not None else None
    if b is not None and (not math.isfinite(b) or b < 0.0):
        raise ValueError('gpu_usable_mb must be non-negative when known')
    mem = res.get('mem_avail_mb')
    if mem is not None:
        mem = float(mem)
        if not math.isfinite(mem) or mem < 0.0:
            raise ValueError('mem_avail_mb must be non-negative when known')
    mem_per_process = 3.0 * max(1.0, a) if a is not None else 2048.0

    if n < 1:
        # No GPU: retain the historical CPU rule (one process per two
        # threads), then apply task and RAM caps before reporting status.
        N = max(1, min(cpu_limit // 2 or 1, m))
        if mem is not None:
            N = min(N, max(1, int(float(mem) // mem_per_process)))
        N = max(1, min(N, m))
        mem_needed = N * mem_per_process
        return {
            'n_gpu': 0, 'n_gpu_available': available_n,
            'b_mb': None if gpu_count_unknown else 0.0,
            'gpu_total_mb': None if gpu_count_unknown else 0.0,
            'a_mb': a, 'm': m, 'N': N, 'Y': 0,
            'X': math.ceil(m / N), 'per_rank_vram_mb': 0.0,
            'cpu_ok': N <= cpu_limit,
            'mem_ok': None if mem is None else mem_needed <= mem,
            'gpu_ok': False if gpu_count_unknown else None,
            'mem_needed_mb': mem_needed,
            'gpu_needed_mb': 0.0,
            'mem_available_mb': mem,
            'notes': (
                'GPU availability unknown; provisional CPU plan'
                if gpu_count_unknown else
                'no GPU detected; CPU-only plan'
            ),
        }

    # Pick only as many cards as can receive at least one task/process.  A
    # forced Y is included in this cap so N=Y*n remains integral throughout.
    forced_y = None if force_y is None else int(force_y)
    if forced_y is not None and forced_y < 1:
        raise ValueError('force_y must be positive')
    initial_y = forced_y or 1
    active_n = min(n, m // initial_y or 1, cpu_limit // initial_y or 1)
    active_n = max(1, active_n)

    gpu_total = active_n * b if b is not None else None
    if forced_y is None:
        Y = max(1, int(b // a)) if a and b is not None else 1
    else:
        Y = forced_y
    requested_y = Y

    # Apply task, CPU, and RAM caps as integer Y caps.  If one process still
    # cannot fit in RAM, retain that honest minimum and report mem_ok=False.
    Y = min(Y, max(1, m // active_n), max(1, cpu_limit // active_n))
    if mem is not None:
        Y = min(Y, max(1, int(float(mem) //
                                (mem_per_process * active_n))))
    Y = max(1, Y)
    N = active_n * Y
    mem_needed = N * mem_per_process
    gpu_needed = Y * a if a is not None else None
    if b is None or b <= 0.0:
        gpu_ok = False
    elif a is not None:
        gpu_ok = gpu_needed <= b
    else:
        gpu_ok = None
    if forced_y is not None:
        notes = f'forced Y={forced_y}'
    elif a is not None:
        notes = 'Y=floor(b/a) per GPU'
    else:
        notes = 'default Y=1 per GPU'
    if Y != requested_y:
        notes += f'; Y capped from {requested_y} to {Y}'
    if active_n != n:
        notes += f'; active GPUs reduced from {n} to {active_n}'

    return {
        'n_gpu': active_n, 'n_gpu_available': available_n,
        'b_mb': b, 'gpu_total_mb': gpu_total,
        'a_mb': a, 'm': m, 'N': N, 'Y': Y,
        'X': math.ceil(m / N),
        'per_rank_vram_mb': gpu_total / N if gpu_total is not None else None,
        'cpu_ok': N <= cpu_limit,
        'mem_ok': None if mem is None else mem_needed <= mem,
        'gpu_ok': gpu_ok,
        'mem_needed_mb': mem_needed,
        'gpu_needed_mb': gpu_needed,
        'mem_available_mb': mem,
        'notes': notes,
    }


def format_plan(plan):
    """Human-readable plan summary (used in reports / logs)."""
    status = ''
    if plan.get('mem_ok') is False:
        status += '; mem_ok=False'
    elif 'mem_ok' in plan and plan.get('mem_ok') is None:
        status += '; mem_ok=unknown'
    if plan.get('gpu_ok') is False:
        status += '; gpu_ok=False'
    elif plan.get('n_gpu', 0) and plan.get('gpu_ok') is None:
        status += '; gpu_ok=unknown'
    if plan.get('cpu_ok') is False:
        status += '; cpu_ok=False'
    if plan.get('a_mb') is not None:
        task_memory = f"a={plan['a_mb']:.0f} MB/task"
    else:
        task_memory = "a=not provided (default Y=1/GPU)"
    if plan.get('serial_fallback'):
        planned = plan.get('planned_N', plan['N'])
        return (f"serial fallback: executing N={plan['N']} process, "
                f"planned N={planned}; m={plan['m']} tasks, "
                f"X={plan['X']} batches{status}")
    if plan['n_gpu'] == 0:
        label = (
            'GPU availability unknown; provisional CPU plan'
            if plan.get('n_gpu_available') is None else
            'no-GPU plan'
        )
        return (f"{label}: N={plan['N']} processes (CPU), "
                f"{task_memory}, m={plan['m']}, X={plan['X']} "
                f"batches{status}")
    available = plan.get('n_gpu_available', plan['n_gpu'])
    gpu_count = (f"{plan['n_gpu']} active GPUs ({available} available)"
                 if available != plan['n_gpu'] else
                 f"{plan['n_gpu']} GPUs")
    if plan.get('b_mb') is None:
        memory_text = 'b=unknown, total=unknown'
        per_rank_text = 'unknown'
    else:
        memory_text = (
            f"b={plan['b_mb']:.0f} MB each "
            f"(80% of {plan['gpu_total_mb']/plan['n_gpu']/0.8:.0f} MB), "
            f"total={plan['gpu_total_mb']:.0f} MB"
        )
        per_rank_text = f"{plan['per_rank_vram_mb']:.0f} MB"
    return (f"GPU plan: {gpu_count}, {memory_text}; "
            f"{task_memory}, m={plan['m']} tasks → "
            f"mpirun -np {plan['N']} (Y={plan['Y']} proc/GPU), "
            f"X={plan['X']} batches; per-rank VRAM "
            f"{per_rank_text}{status}")


def _serial_fallback_plan(plan):
    """Return a one-process view of a recommended plan without mutating it."""
    if plan.get('N') == 1:
        return plan

    effective = dict(plan)
    effective['planned_N'] = plan.get('planned_N', plan.get('N'))
    effective['serial_fallback'] = True
    effective['N'] = 1
    effective['X'] = math.ceil(plan['m'] / effective['N'])
    a = float(plan.get('a_mb') or 0.0)
    mem_per_process = 3.0 * max(1.0, a) if a else 2048.0
    effective['mem_needed_mb'] = mem_per_process
    if 'mem_available_mb' in plan:
        mem_available = plan.get('mem_available_mb')
        effective['mem_ok'] = (
            mem_available is None or mem_per_process <= mem_available)
    if plan.get('n_gpu', 0):
        effective['n_gpu_available'] = plan.get(
            'n_gpu_available', plan['n_gpu'])
        effective['n_gpu'] = 1
        effective['gpu_total_mb'] = plan.get('b_mb')
        effective['Y'] = 1
        effective['per_rank_vram_mb'] = effective['gpu_total_mb']
        effective['gpu_needed_mb'] = a if a else 0.0
        b = effective['gpu_total_mb']
        if b is None or b <= 0.0:
            effective['gpu_ok'] = False
        elif a:
            effective['gpu_ok'] = a <= b
        else:
            effective['gpu_ok'] = None
    else:
        effective['Y'] = 0
        effective['per_rank_vram_mb'] = 0.0
        effective['gpu_total_mb'] = 0.0
        effective['gpu_needed_mb'] = 0.0
        effective['gpu_ok'] = None
    effective['cpu_ok'] = True
    return effective


def _configure_rank_backend(backend, device, rank, active_n_gpu,
                            set_backend):
    """Canonicalize and bind the backend used by one MPI rank."""
    name = backend.lower()
    if name in ('gpu', 'cuda'):
        name = 'torch'

    explicit_cpu = device is not None and str(device).lower().startswith('cpu')
    if active_n_gpu >= 1 and name in ('torch', 'cupy') and not explicit_cpu:
        index = rank % active_n_gpu
        device = f'cuda:{index}'
        if name == 'torch':
            import torch
            torch.cuda.set_device(device)
        else:
            import cupy as cp
            cp.cuda.Device(index).use()

    set_backend(name, device=device)
    return name, device


# ═══════════════════════════════════════════════════════════════════
# Meta-task execution
# ═══════════════════════════════════════════════════════════════════

def run_meta_task(step, conf_id, config, run_dir, logger):
    """Run one meta-task (step, conf) and release memory afterwards."""
    from ..pipeline._steps import (
        compute_vertices_for_config, step_2pt,
        compute_3pt_for_config, compute_4pt_for_config,
        compute_ope_for_config, _load_vertices_one,
        free_gpu_memory, _timer,
    )
    t0 = __import__('time').perf_counter()
    try:
        if step == 'vertex':
            compute_vertices_for_config(conf_id, run_dir, logger,
                                        config.get('precision', 'complex64'))
        elif step == '2pt':
            per_conf_config = dict(config)
            per_conf_config['conf_ids'] = [conf_id]
            step_2pt(per_conf_config, run_dir, logger)
        elif step == '3pt':
            verts = _load_vertices_one(run_dir, conf_id)
            compute_3pt_for_config(conf_id, run_dir, logger, verts,
                                   config.get('precision', 'complex64'),
                                   config.get('t_sep', 12))
            del verts
        elif step == '4pt':
            verts = _load_vertices_one(run_dir, conf_id)
            compute_4pt_for_config(conf_id, run_dir, logger, verts,
                                   config.get('precision', 'complex64'))
            del verts
        elif step == 'ope':
            # 注意：必须显式设置 GPU 后端（step_ope 内部会做，但并行元任务直接调用
            # compute_ope_for_config，需在此补齐 set_backend，否则退回 numpy/CPU 后端，
            # OPE 将极其缓慢且不利用 GPU）。
            from ..tools import set_backend
            set_backend(config.get('backend', 'cupy'),
                        device=config.get('device'))
            compute_ope_for_config(conf_id, run_dir, logger,
                                   config.get('precision', 'complex64'))
        else:
            raise ValueError(f"no meta-task handler for step '{step}'")
    finally:
        try:
            free_gpu_memory()
        except BaseException:
            pass
        try:
            gc.collect()
        except BaseException:
            pass
    return time.perf_counter() - t0


# ═══════════════════════════════════════════════════════════════════
# Parallel pipeline driver
# ═══════════════════════════════════════════════════════════════════

def run_parallel_pipeline(steps=('env', 'vertex', '2pt', 'ope', '3pt', '4pt',
                                 'analysis', 'plots', 'report'),
                          conf_ids=None, run_dir=None, logger=print,
                          precision='complex64', backend='torch',
                          device=None, a_mem_mb=None, resources=None,
                          plan=None, channels=('pp', 'pn', 'pion'),
                          n_gpu=None, force_y=None, dry_run=False,
                          recompute_2pt=False):
    """Run the pipeline with MPI task parallelism.

    Serial behaviour (no mpirun / MPI size 1) is fully supported:
    falls back to the standard ``run_pipeline``.

    Parallel behaviour (mpirun -np N):
    - compute steps (vertex/2pt/ope/3pt/4pt) are split across ranks
      round-robin per configuration;
    - analysis / plots / report run once on rank 0 after collective status
      exchange confirms all parallel phases completed;
    - the plan (N, Y, X) follows the user formula N*a = n*b.

    Returns (result_dict, plan_dict). ``dry_run=True`` only prints the
    plan (no computation).
    """
    comm, rank, size = get_mpi_context()
    preflight_failure = None
    try:
        from ..pipeline import run_pipeline as _serial_run

        steps = tuple(steps)
        if conf_ids is None:
            conf_ids = [6250]
        else:
            conf_ids = list(conf_ids)
            if not conf_ids:
                raise ValueError('conf_ids must not be empty')
        if plan is None:
            res = resources if resources is not None else detect_resources()
            plan = plan_parallel(len(conf_ids), a_mem_mb, resources=res,
                                 n_gpu=n_gpu, force_y=force_y, verbose=True)
        _validate_mpi_preflight(steps, plan, size)
        if size <= 1 and not dry_run:
            plan = _serial_fallback_plan(plan)
        if logger is not None and (
                size <= 1 or rank == 0 or
                (not dry_run and logger is not print)):
            logger(f"[parallel] plan: {format_plan(plan)}")
    except BaseException as exc:
        if size <= 1:
            raise
        preflight_failure = _failure_summary('preflight', rank, exc)
    if size > 1:
        _collective_failure_rendezvous(comm, preflight_failure)

    if dry_run:
        return None, plan
    if size <= 1:
        return _serial_run(steps=steps, conf_ids=conf_ids, run_dir=run_dir,
                           logger=logger, precision=precision,
                           channels=channels, backend=backend,
                           device=device,
                           recompute_2pt=recompute_2pt), plan

    # ── MPI parallel execution ─────────────────────────────────────
    run_dir_failure = None
    try:
        if rank == 0 and run_dir is None:
            from ..pipeline._config import OUTPUT_DIR
            run_dir = reserve_unique_run_dir(OUTPUT_DIR)
    except BaseException as exc:
        run_dir_failure = _failure_summary('run-dir', rank, exc)
    _collective_failure_rendezvous(comm, run_dir_failure)
    run_dir = comm.bcast(run_dir if rank == 0 else None, root=0)

    setup_failure = None
    try:
        from ..pipeline._steps import (
            run_pipeline as _run, dump_config_snapshot,
            _info, _timer,
        )
        from ..pipeline._config import PRECISION
        from ..tools import set_backend

        backend, device = _configure_rank_backend(
            backend, device, rank, plan.get('n_gpu', 0), set_backend)
        if logger is not None:
            logger(f"[rank {rank}] backend={backend} device={device}")

        config = {
            'precision': precision, 'channels': tuple(channels),
            'conf_ids': conf_ids, 'backend': backend, 'device': device,
            'recompute_2pt': bool(recompute_2pt),
        }
        os.makedirs(os.path.join(run_dir, 'data'), exist_ok=True)
        os.makedirs(os.path.join(run_dir, 'analysis'), exist_ok=True)
        os.makedirs(os.path.join(run_dir, 'plots'), exist_ok=True)
        if rank == 0:
            dump_config_snapshot(
                config, os.path.join(run_dir, 'run_config.json'), logger)
    except BaseException as exc:
        setup_failure = _failure_summary('setup', rank, exc)
    _collective_failure_rendezvous(comm, setup_failure)

    timing = {}
    for step in steps:
        if step not in _MPI_PARALLEL_STEPS:
            continue
        t0 = time.perf_counter()
        task_failure = None
        try:
            # round-robin: rank r handles confs[r::size]
            my_confs = conf_ids[rank::size]
            if logger is not None:
                logger(f"[rank {rank}] {step}: {len(my_confs)} confs "
                       f"→ {my_confs}")
            for cid in my_confs:
                _timer(f"[rank {rank}] {step} conf={cid}", logger,
                       run_meta_task, step, cid, config, run_dir, logger)
        except BaseException as exc:
            task_failure = _failure_summary(
                f'meta-task:{step}', rank, exc)
        _collective_failure_rendezvous(comm, task_failure)
        timing[f'{step}'] = round(__import__('time').perf_counter() - t0, 1)
        step_log_failure = None
        try:
            if rank == 0 and logger is not None:
                logger(f"STEP {step} done (parallel) in {timing[step]}s")
        except BaseException as exc:
            step_log_failure = _failure_summary(
                f'step-log:{step}', rank, exc)
        _collective_failure_rendezvous(comm, step_log_failure)

    # analysis / plots / report: rank 0 only (light CPU work)
    meff_res, ratio_conn, summary, env = None, None, None, None
    postprocess_failure = None
    if rank == 0:
        postprocess_phase = 'postprocess:setup'
        try:
            from ..pipeline._steps import (
                step_analysis, step_plots, step_report, run_pipeline as _rp,
            )
            for step in steps:
                postprocess_phase = f'postprocess:{step}'
                if step == 'env':
                    from ..pipeline._config import NX, NT, get_gauge_path
                    env = {
                        'conf_ids': conf_ids,
                        'precision': config['precision'],
                        'nx': NX,
                        'nt': NT,
                        'gauge_dir': os.path.dirname(
                            get_gauge_path(conf_ids[0])),
                    }
                    if logger is not None:
                        logger(f"env: {env}")
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
        except BaseException as exc:
            postprocess_failure = _failure_summary(
                postprocess_phase, rank, exc)
    _collective_failure_rendezvous(comm, postprocess_failure)
    completion_log_failure = None
    try:
        if rank == 0 and logger is not None:
            logger(f"[parallel] pipeline done: {plan['N']} ranks, "
                   f"{len(conf_ids)} configs, {format_plan(plan)}")
    except BaseException as exc:
        completion_log_failure = _failure_summary(
            'completion-log', rank, exc)
    _collective_failure_rendezvous(comm, completion_log_failure)
    return {'run_dir': run_dir, 'timing': timing, 'summary': summary,
            'meff': meff_res, 'ratio_conn': ratio_conn}, plan


def main():
    """CLI entry: python -m pyqcd.parallel [--dry-run] [--confs a,b] ..."""
    import argparse

    def nonnegative_int(text):
        try:
            value = int(text)
        except (TypeError, ValueError) as exc:
            raise argparse.ArgumentTypeError(
                'must be a non-negative integer') from exc
        if value < 0:
            raise argparse.ArgumentTypeError(
                'must be a non-negative integer')
        return value

    ap = argparse.ArgumentParser(description='pyqcd MPI parallel pipeline')
    ap.add_argument('--steps', nargs='+',
                    default=['env', 'vertex', '2pt', 'ope', '3pt', '4pt',
                             'analysis', 'plots', 'report'])
    ap.add_argument('--confs', type=str, default=None,
                    help='comma-separated conf ids (default 6250)')
    ap.add_argument('--run-dir', default=None)
    ap.add_argument('--backend', default='torch', choices=['torch', 'cupy',
                                                           'numpy'])
    ap.add_argument('--device', default=None)
    ap.add_argument('--n-gpu', type=nonnegative_int, default=None,
                   help='强制使用的 GPU 数量（默认按 detect_resources 自动探测）；'
                        '例如 2 表示用 2 卡并行，逐 rank 绑定 cuda:{rank%%n}')
    ap.add_argument('--a-mem-mb', type=float, default=None,
                   help='VRAM per meta-task in MB (plan formula)')
    ap.add_argument('--precision', default='complex64',
                    choices=['complex64', 'complex128'])
    ap.add_argument('--recompute-2pt', action='store_true',
                    help='force MPI 2pt recomputation even when cache is complete')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    confs = [int(x) for x in args.confs.split(',')] if args.confs else [6250]
    res = detect_resources()
    plan = plan_parallel(len(confs), args.a_mem_mb, resources=res,
                         n_gpu=args.n_gpu)
    run_parallel_pipeline(
        steps=tuple(args.steps), conf_ids=confs, run_dir=args.run_dir,
        precision=args.precision, backend=args.backend,
        device=args.device, a_mem_mb=args.a_mem_mb, plan=plan,
        n_gpu=args.n_gpu, recompute_2pt=args.recompute_2pt,
        dry_run=args.dry_run)


if __name__ == '__main__':
    main()
