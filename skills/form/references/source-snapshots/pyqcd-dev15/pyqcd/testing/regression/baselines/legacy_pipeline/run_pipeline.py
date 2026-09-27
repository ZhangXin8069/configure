#!/usr/bin/env python3
"""
docker-v20260805 — Full GPU Distillation Pipeline (Orchestrator)
================================================================

Steps:
  0  Environment / data-path check
  1  Vertex functions        → VdV, VVV
  2  Wick + dynamic contraction → 2pt (pp, pn, pion) at P0 & P2
  3  OPE (gluon operator)    → ops_mu*_nu*_dz*.npz (+ combined)
  4  3pt (PJN)               → proton/pion 3pt at P0 & P2
  5  4pt (PJNNJNp)           → two-hadron-sink 4pt
  6  Statistical analysis     → Jackknife / meff / ratio_3p (code_1.py style)
  7  Plots                   → meff, correlators, ratios
  8  LaTeX report            → physics_report.tex → PDF

Every step saves its intermediate arrays and writes progress to the log file
(mirrored to /root/PyQCD/logs).

Usage:
  python run_pipeline.py                                 # all steps, 10 configs
  python run_pipeline.py --conf-ids 6250 --skip-4pt      # fast smoke test
  python run_pipeline.py --precision complex64           # single precision (default)
  python run_pipeline.py --Nev1 60                       # truncated VVV/contraction
  python run_pipeline.py --steps vertex,2pt,analysis     # selected steps
"""

from __future__ import annotations

import argparse, gc, json, os, sys, time, traceback
from datetime import datetime
from pathlib import Path

import numpy as np

_SCRIPT_DIR = Path(__file__).parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from config import (CONF_IDS, NEV, NEV1, PRECISION, NT, NX, ALttc,
                    AGENT_LOGS_DIR)
from utils import (setup_logging, print_banner, Timer, log_gpu_memory,
                   free_gpu_memory, dump_config_snapshot, HAS_CUPY,
                   save_array, load_array)


# ═══════════════════════════════════════════════════════════════════
# Steps
# ═══════════════════════════════════════════════════════════════════

def step_env(config, logger):
    print_banner("Step 0: Environment Check", logger)
    env = {'ok': True}
    logger.info(f"Python {sys.version.split()[0]}")
    logger.info(f"Configs: {config['conf_ids']} (Nconf={len(config['conf_ids'])})")
    logger.info(f"Precision: {config['precision']}, Nev={NEV}, Nev1={config['Nev1']}")
    if HAS_CUPY:
        import cupy as cp
        dev = cp.cuda.Device(); props = cp.cuda.runtime.getDeviceProperties(dev.id)
        name = props['name'].decode() if isinstance(props['name'], bytes) else props['name']
        free, total = cp.cuda.runtime.memGetInfo()
        env['gpu'] = name
        logger.info(f"GPU: {name} | free={free/2**30:.1f}/{total/2**30:.1f} GB")
        logger.info(f"CuPy {cp.__version__} | CUDA {cp.cuda.runtime.runtimeGetVersion()}")
    else:
        logger.warning("NO GPU — falling back to CPU (slow)")
    for cid in config['conf_ids']:
        from config import get_eigen_path, get_peram_dir, get_gauge_path
        e = os.path.isdir(os.path.dirname(get_eigen_path(cid, 0)))
        p = os.path.isdir(get_peram_dir(cid))
        g = os.path.exists(get_gauge_path(cid))
        logger.info(f"  conf={cid}: eigvec={'✓' if e else '✗'} "
                    f"peram={'✓' if p else '✗'} gauge={'✓' if g else '✗'}")
    log_gpu_memory(logger)
    return env


def step_vertex(config, run_dir, logger):
    print_banner("Step 1: Vertex Functions (VdV, VVV)", logger)
    from compute_vertex import compute_all_vertices
    # Vertices are saved to disk per config; the return value is discarded so
    # the (≈11.5 GB for 10 configs) arrays are not held in host RAM.
    compute_all_vertices(config['conf_ids'], run_dir, logger,
                         config['precision'], recompute=False)
    return None


def step_2pt(config, run_dir, logger):
    print_banner("Step 2: 2pt Correlators (pp, pn, pion)", logger)
    from compute_contraction import compute_2pt_all
    # vertices=None ⇒ each config's VdV/VVV is loaded from disk on demand,
    # keeping peak host memory bounded (≈2 GB instead of ≈23 GB).
    data = compute_2pt_all(config['conf_ids'], run_dir, logger,
                           vertices=None, precision=config['precision'],
                           channels=config.get('channels', ('pp', 'pn', 'pion')))
    return data


def step_ope(config, run_dir, logger):
    print_banner("Step 3: OPE (gluon operator)", logger)
    from compute_ope import compute_ope_all
    data = compute_ope_all(config['conf_ids'], run_dir, logger,
                           config['precision'])
    return data


def step_3pt(config, run_dir, logger):
    print_banner("Step 4: 3pt Correlators (PJN)", logger)
    from compute_contraction import compute_3pt_all
    data = compute_3pt_all(config['conf_ids'], run_dir, logger,
                           vertices=None, precision=config['precision'])
    return data


def step_4pt(config, run_dir, logger):
    print_banner("Step 5: 4pt Correlators (PJNNJNp)", logger)
    from compute_contraction import compute_4pt_all
    from config import FOURPT_TSEP, FOURPT_NEV1, FOURPT_MOM, FOURPT_SRC_STEP
    data = compute_4pt_all(
        config['conf_ids'], run_dir, logger,
        vertices=None, precision=config['precision'],
        t_sep=config.get('fourpt_tsep', FOURPT_TSEP),
        nev1=config.get('fourpt_nev1', FOURPT_NEV1),
        momenta=config.get('fourpt_mom', FOURPT_MOM),
        src_step=config.get('fourpt_src_step', FOURPT_SRC_STEP))
    return data


def step_analysis(config, run_dir, logger):
    print_banner("Step 6: Statistical Analysis (Jackknife/meff/ratio_3p)", logger)
    from analyze import (run_meff_jackknife, run_connected_ratio,
                         run_disconnected_ratio)
    corr2 = load_2pt(run_dir, logger)
    meff_res = run_meff_jackknife(corr2, config['conf_ids'], run_dir, logger)

    # Connected 3pt/2pt ratio (requires 3pt data)
    corr3 = load_3pt(run_dir, logger)
    if corr3:
        ratio_conn = run_connected_ratio(corr2, corr3, config['conf_ids'],
                                         run_dir, logger)
    else:
        ratio_conn = {}
        logger.warning("No 3pt data — skipping connected ratio")

    # Disconnected gluon ratio (code_1.py style, requires OPE)
    ope = load_ope(run_dir, logger)
    if ope:
        ratio_disc = run_disconnected_ratio(corr2, ope, config['conf_ids'],
                                            run_dir, logger)
    else:
        ratio_disc = {}
        logger.warning("No OPE data — skipping disconnected ratio")

    return {'meff': meff_res, 'connected_ratio': ratio_conn,
            'disconnected_ratio': ratio_disc}


def step_plots(config, run_dir, logger, meff_res=None, ratio_conn=None):
    print_banner("Step 7: Plots", logger)
    from analyze import plot_meff_results, plot_correlators, plot_connected_ratio
    if meff_res is None:
        # Rebuild from saved arrays
        an_dir = os.path.join(run_dir, 'data', 'analysis')
        from analyze import CHANNELS
        meff_res = {}
        for particle, mom, key in CHANNELS:
            fm = os.path.join(an_dir, f'meff_{particle}_{mom}_mean.npy')
            fe = os.path.join(an_dir, f'meff_{particle}_{mom}_err.npy')
            if os.path.exists(fm):
                m = np.load(fm); e = np.load(fe)
                ps, pe = (4, min(NT - 2, 14)) if particle == 'proton' else (5, min(NT - 2, 18))
                mask = np.isfinite(m[ps:pe]) & (e[ps:pe] > 0) & (m[ps:pe] > 0.01)
                w = 1.0 / (e[ps:pe][mask] ** 2 + 1e-10)
                meff_res[f'{particle}_{mom}'] = {
                    'meff_mean': m, 'meff_err': e, 'plateau': (ps, pe),
                    'E0': float(np.sum(m[ps:pe][mask] * w) / np.sum(w)),
                    'E0_err': float(1 / np.sqrt(np.sum(w))),
                    'E_exp': 1.0 if particle == 'proton' else 0.30,
                    'corr_mean': np.load(os.path.join(an_dir, f'corr_{particle}_{mom}_mean.npy')),
                    'corr_err': np.load(os.path.join(an_dir, f'corr_{particle}_{mom}_err.npy')),
                }
    plot_meff_results(meff_res, run_dir, logger)
    plot_correlators(meff_res, run_dir, logger)
    if ratio_conn:
        plot_connected_ratio(ratio_conn, run_dir, logger)
    return meff_res


def step_report(config, run_dir, logger, env, meff_res, timing):
    print_banner("Step 8: LaTeX Report", logger)
    # Dump analysis summary JSON for the report generator
    summary = {
        'version': 'docker-v20260805',
        'conf_ids': config['conf_ids'],
        'precision': config['precision'],
        'nev': NEV, 'nev1': config['Nev1'],
        'lattice': [NT, NX, NX, NX], 'alttc': ALttc,
        'meff': {k: {kk: float(vv) if isinstance(vv, (int, float, np.floating))
                     else (list(vv) if isinstance(vv, tuple) else None)
                     for kk, vv in v.items() if kk in ('E0', 'E0_err', 'E_exp', 'dev', 'plateau', 'npts')}
                 for k, v in meff_res.items()},
        'timing_s': timing,
        'run_dir': run_dir,
    }
    with open(os.path.join(run_dir, 'analysis_summary.json'), 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    logger.info(f"Analysis summary -> {run_dir}/analysis_summary.json")
    return summary


# ═══════════════════════════════════════════════════════════════════
# Loaders (for resuming from saved intermediates)
# ═══════════════════════════════════════════════════════════════════

def load_vertices(run_dir, logger):
    from config import conf_data_dir
    verts = {}
    for cid in os.listdir(os.path.join(run_dir, 'data')):
        if not cid.startswith('conf'):
            continue
        cid = cid[4:]
        cdir = os.path.join(run_dir, 'data', f'conf{cid}')
        vd = os.path.join(cdir, f'VdV_mom_{cid}.npy')
        vv = os.path.join(cdir, f'VVV_mom_{cid}.npy')
        if os.path.exists(vd) and os.path.exists(vv):
            verts[int(cid)] = {'VdV': np.load(vd), 'VVV': np.load(vv)}
    return verts


def load_2pt(run_dir, logger):
    """Load 2pt correlators. File names are ``corr_<ch>_<conf>.npy``; the
    per-config suffix is stripped so keys match the analysis channels
    ('corr_pp_P0', 'corr_pi_P2', ...)."""
    corr = {}
    for cid in os.listdir(os.path.join(run_dir, 'data')):
        if not cid.startswith('conf'):
            continue
        cid = cid[4:]
        cdir = os.path.join(run_dir, 'data', f'conf{cid}')
        entry = {}
        for f in os.listdir(cdir):
            if f.startswith('corr_') and f.endswith('.npy'):
                key = f[5:].replace(f'_{cid}.npy', '')   # 'pp_P0', 'pi_P2', ...
                entry[f'corr_{key}'] = np.load(os.path.join(cdir, f))
        if entry:
            corr[int(cid)] = entry
    logger.info(f"Loaded 2pt correlators for {len(corr)} configs")
    return corr


def load_3pt(run_dir, logger):
    """Load 3pt correlators. File names are ``<ch>_3pt_<conf>.npy`` → key
    '<ch>_3pt' (e.g. 'proton_P0_3pt')."""
    corr = {}
    for cid in os.listdir(os.path.join(run_dir, 'data')):
        if not cid.startswith('conf'):
            continue
        cid = cid[4:]
        cdir = os.path.join(run_dir, 'data', f'conf{cid}')
        entry = {}
        for f in os.listdir(cdir):
            if '_3pt_' in f and f.endswith('.npy') and 'pjnnjnp' not in f:
                key = f[:-4].replace(f'_{cid}', '')
                entry[key] = np.load(os.path.join(cdir, f))
        if entry:
            corr[int(cid)] = entry
    if corr:
        logger.info(f"Loaded 3pt correlators for {len(corr)} configs")
    return corr


def load_ope(run_dir, logger):
    from config import conf_data_dir
    ope = {}
    for cid in os.listdir(os.path.join(run_dir, 'data')):
        if not cid.startswith('conf'):
            continue
        cid = cid[4:]
        cdir = os.path.join(run_dir, 'data', f'conf{cid}')
        comb = os.path.join(cdir, f'ope_combined_conf{cid}.npy')
        if os.path.exists(comb):
            ope[int(cid)] = {'combined': np.load(comb)}
    if ope:
        logger.info(f"Loaded combined OPE for {len(ope)} configs")
    return ope


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(description='docker-v20260805 GPU pipeline')
    p.add_argument('--conf-id', type=int, default=None)
    p.add_argument('--conf-ids', type=str, default=None,
                   help='comma-separated config IDs')
    p.add_argument('--precision', choices=['complex64', 'complex128'],
                   default=PRECISION)
    p.add_argument('--Nev1', type=int, default=NEV1,
                   help='truncated Nev for VVV / baryon contractions')
    p.add_argument('--steps', type=str, default='all',
                   help='comma list: env,vertex,2pt,ope,3pt,4pt,analysis,plots,report')
    p.add_argument('--skip-2pt', action='store_true')
    p.add_argument('--skip-ope', action='store_true')
    p.add_argument('--skip-3pt', action='store_true')
    p.add_argument('--skip-4pt', action='store_true')
    p.add_argument('--skip-analysis', action='store_true')
    p.add_argument('--skip-plots', action='store_true')
    p.add_argument('--skip-report', action='store_true')
    p.add_argument('--channels', type=str, default='pp,pn,pion',
                   help='2pt channels: comma list of pp,pn,pion')
    p.add_argument('--fourpt-nev1', type=int, default=None,
                   help='eigenvector truncation for the 4pt (default 60)')
    p.add_argument('--fourpt-tsep', type=int, default=None,
                   help='source-sink separation for the 4pt (default 6)')
    p.add_argument('--run-dir', type=str, default=None,
                   help='resume into an existing output run directory')
    p.add_argument('--verbose', '-v', action='store_true')
    return p.parse_args()


def main():
    args = parse_args()
    config = {
        'precision': args.precision,
        'Nev1': min(args.Nev1, NEV),
        'channels': tuple(args.channels.split(',')),
        'verbose': args.verbose,
    }
    config['conf_ids'] = [args.conf_id] if args.conf_id else CONF_IDS
    if args.conf_ids:
        config['conf_ids'] = [int(x) for x in args.conf_ids.split(',')]
    config['Nev1'] = min(config['Nev1'], NEV)
    if args.fourpt_nev1:
        config['fourpt_nev1'] = args.fourpt_nev1
    if args.fourpt_tsep:
        config['fourpt_tsep'] = args.fourpt_tsep

    # ── Output run directory (timestamped, or resumed) ──
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    if args.run_dir:
        run_dir = os.path.join(_SCRIPT_DIR, args.run_dir)
        ts = os.path.basename(args.run_dir).replace('output_', '')  # resume label
    else:
        run_dir = os.path.join(_SCRIPT_DIR, 'output', f'output_{ts}')
    for d in ['data', 'analysis', 'plots']:
        os.makedirs(os.path.join(run_dir, d), exist_ok=True)

    # ── Logging: run-local + central agent/logs ──
    log_dir = AGENT_LOGS_DIR
    logger = setup_logging(log_dir, name=f'docker-v20260805-{ts}',
                           verbose=config['verbose'])
    logger.info(f"Run directory: {run_dir}")
    logger.info(f"Config: {config}")
    dump_config_snapshot(config, os.path.join(run_dir, 'run_config.json'), logger)

    steps = ['env', 'vertex', '2pt', 'ope', '3pt', '4pt',
             'analysis', 'plots', 'report']
    if args.steps != 'all':
        steps = [s.strip() for s in args.steps.split(',')]
    if args.skip_2pt: steps = [s for s in steps if s != '2pt']
    if args.skip_ope: steps = [s for s in steps if s != 'ope']
    if args.skip_3pt: steps = [s for s in steps if s != '3pt']
    if args.skip_4pt: steps = [s for s in steps if s != '4pt']
    if args.skip_analysis: steps = [s for s in steps if s != 'analysis']
    if args.skip_plots: steps = [s for s in steps if s != 'plots']
    if args.skip_report: steps = [s for s in steps if s != 'report']

    timing = {}
    meff_res, ratio_conn, env = None, None, None
    total_start = time.perf_counter()
    try:
        for step in steps:
            tmr = Timer(f"STEP {step}", logger)
            tmr.__enter__()
            try:
                if step == 'env':
                    env = step_env(config, logger)
                elif step == 'vertex':
                    verts = step_vertex(config, run_dir, logger)
                elif step == '2pt':
                    step_2pt(config, run_dir, logger)
                elif step == 'ope':
                    step_ope(config, run_dir, logger)
                elif step == '3pt':
                    step_3pt(config, run_dir, logger)
                elif step == '4pt':
                    step_4pt(config, run_dir, logger)
                elif step == 'analysis':
                    analysis = step_analysis(config, run_dir, logger)
                    meff_res = analysis['meff']
                    ratio_conn = analysis['connected_ratio']
                elif step == 'plots':
                    meff_res = step_plots(config, run_dir, logger, meff_res, ratio_conn)
                elif step == 'report':
                    summary = step_report(config, run_dir, logger, env, meff_res, timing)
            finally:
                tmr.__exit__(None, None, None)
            timing[step] = round(tmr.elapsed, 1)

        total_t = time.perf_counter() - total_start
        print_banner(f"Pipeline Complete! Total {total_t:.0f}s "
                     f"({total_t/60:.1f} min)", logger)
        logger.info(f"Run directory: {run_dir}")
        logger.info(f"Central log: {AGENT_LOGS_DIR}")
        return 0
    except Exception as e:
        logger.error(f"PIPELINE FAILED: {e}")
        logger.error(traceback.format_exc())
        return 1


if __name__ == '__main__':
    sys.exit(main())
