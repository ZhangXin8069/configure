#!/usr/bin/env python3
"""
test0 —— pyqcd 全量蒸馏管线一致性测试套件
============================================

调用 `pyqcd` 包复现冻结的蒸馏成功实例
（output/output_20260802_120104）的全量结果：中间数据 + 图表 + LaTeX 报告
完整保存，逐项数值一致。

本文件只有测试/编排代码：计算全部委托 pyqcd（pyqcd.pipeline.run_pipeline
及各子包），不包含任何核心计算逻辑。

子命令（test12 风格）：
    env      环境与数据路径自检
    run      完整 9 步管线 → 版本目录（v<YYYYMMDDHHMM>/ 或 --outdir）
    verify   一致性验证（vs docker-v20260805/output/output_20260802_120104）
    check    断言门（verify 全 PASS → exit 0；否则 exit 1）
    plots    仅重新绘图（从已有 run_dir 的 data/analysis 重建）
    report   仅生成 LaTeX 报告（xelatex 两遍）
    collect  汇总版本目录产物清单

公共参数：--outdir 优先于 $TEST0_OUTDIR，再默认
`pyqcd/testing/regression/distillation/artifacts/run_<ts>/`。

运行：
    python -m pyqcd.testing.regression.distillation.main env
    python -m pyqcd.testing.regression.distillation.main run --conf-ids 6250
    python -m pyqcd.testing.regression.distillation.main run
    python -m pyqcd.testing.regression.distillation.main verify --run-dir <run>
    python -m pyqcd.testing.regression.distillation.main check --run-dir <run>
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime

import numpy as np

ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..'))

# 一致性验证的参考基线（成功实例输出，只读磁盘数据比对，不 import 代码）
BASELINE_DIR = os.path.join(
    ROOT, 'pyqcd', 'testing', 'regression', 'baselines',
    'legacy_pipeline', 'output', 'output_20260802_120104')
DEFAULT_CONF_IDS = [6250, 6450, 6650, 6850, 7050,
                    7250, 7450, 7650, 7850, 8050]

WORKDIR = os.path.dirname(os.path.abspath(__file__))

# ── 一致性容差（complex64 中间数据 / float64 分析结果）──
TOL_MIDDLE = 1e-6      # 中间数据相对差（norm 归一）
TOL_ANALYSIS = 1e-8    # 分析数组 / 拟合参数相对差
TOL_SUMMARY = 1e-8     # analysis_summary.json 标量相对差


def dump_env(path):
    """环境快照（test12 env.json 约定）。"""
    git_branch = git_head = 'n/a'
    try:
        git_branch = subprocess.run(
            ['git', '-C', ROOT, 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True, text=True).stdout.strip()
        git_head = subprocess.run(
            ['git', '-C', ROOT, 'log', '-1', '--oneline'],
            capture_output=True, text=True).stdout.strip()
    except Exception:
        pass
    import importlib
    def _ver(m):
        try:
            return importlib.import_module(m).__version__
        except Exception:
            return None
    info = {
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'hostname': platform.node(),
        'python': platform.python_version(),
        'numpy': _ver('numpy'), 'scipy': _ver('scipy'),
        'matplotlib': _ver('matplotlib'), 'cupy': _ver('cupy'),
        'lsqfit': _ver('lsqfit'), 'gvar': _ver('gvar'),
        'xelatex': shutil.which('xelatex'),
        'git_branch': git_branch, 'git_head': git_head,
        'cmdline': ' '.join(sys.argv),
    }
    try:
        out = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total',
                              '--format=csv,noheader'], capture_output=True,
                             text=True)
        info['gpu'] = out.stdout.strip() if out.returncode == 0 else 'n/a'
    except Exception:
        info['gpu'] = 'n/a'
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(info, f, indent=2)
    return info


def resolve_outdir(args):
    """--outdir > $TEST0_OUTDIR > <workdir>/artifacts/run_<ts>/."""
    outdir = args.outdir or os.environ.get('TEST0_OUTDIR')
    if outdir:
        outdir = os.path.abspath(outdir)
    else:
        vdir = os.path.join(
            WORKDIR, 'artifacts',
            'run_' + datetime.now().strftime('%Y%m%d%H%M'))
        if os.path.exists(vdir):
            vdir = f"{vdir}-{datetime.now().strftime('%S')}"
        outdir = vdir
    os.makedirs(outdir, exist_ok=True)
    return outdir


# ═══════════════════════════════════════════════════════════════════
# env —— 环境与数据路径自检
# ═══════════════════════════════════════════════════════════════════

def cmd_env(args):
    print("=== test0 env check ===")
    checks = []
    for name, mod in [('numpy', 'numpy'), ('scipy', 'scipy'),
                      ('matplotlib', 'matplotlib'), ('cupy', 'cupy'),
                      ('lsqfit', 'lsqfit'), ('gvar', 'gvar')]:
        try:
            m = __import__(mod)
            checks.append((name, 'OK', getattr(m, '__version__', '?')))
        except ImportError:
            checks.append((name, 'MISSING', ''))
    xe = shutil.which('xelatex')
    checks.append(('xelatex', 'OK' if xe else 'MISSING', xe or ''))
    for name, st, ver in checks:
        print(f"  [{'✓' if st == 'OK' else '✗'}] {name:12s} {ver}")

    from pyqcd.pipeline._config import (
        EIGEN_DIR, PERAM_DIR, GAUGE_DIR, get_gauge_path)
    import os as _os
    for label, d in [('eigen', EIGEN_DIR), ('peram', PERAM_DIR),
                     ('gauge', GAUGE_DIR)]:
        ok = _os.path.isdir(d)
        print(f"  [{'✓' if ok else '✗'}] {label:12s} {d}")
    first = os.path.isdir(os.path.join(EIGEN_DIR, str(DEFAULT_CONF_IDS[0])))
    print(f"  [{'✓' if first else '✗'}] eigen/6250 存在")
    g = _os.path.exists(get_gauge_path(6250))
    print(f"  [{'✓' if g else '✗'}] gauge/6250 .lime 存在")
    base_ok = os.path.isdir(BASELINE_DIR)
    print(f"  [{'✓' if base_ok else '✗'}] 基线输出目录存在: {BASELINE_DIR}")
    all_ok = all(st == 'OK' for _, st, _ in checks) and base_ok
    print(f"env check: {'PASS' if all_ok else 'FAIL'}")
    sys.exit(0 if all_ok else 1)


# ═══════════════════════════════════════════════════════════════════
# run —— 完整 9 步管线（调用 pyqcd.pipeline.run_pipeline）
# ═══════════════════════════════════════════════════════════════════

def cmd_run(args):
    conf_ids = [int(x) for x in args.conf_ids.split(',')] \
        if args.conf_ids else DEFAULT_CONF_IDS
    if args.steps == 'all':
        steps = ['env', 'vertex', '2pt', 'ope', '3pt', '4pt',
                 'analysis', 'plots', 'report']
        if args.skip_3pt:
            steps = [s for s in steps if s != '3pt']
        if args.skip_4pt:
            steps = [s for s in steps if s != '4pt']
    else:
        steps = [s.strip() for s in args.steps.split(',')]

    run_dir = resolve_outdir(args)
    print(f"版本目录: {run_dir}")
    dump_env(os.path.join(run_dir, 'env.json'))

    from pyqcd.pipeline import run_pipeline
    res = run_pipeline(
        steps=steps, conf_ids=conf_ids, run_dir=run_dir, logger=print,
        precision=args.precision, nev1=args.nev1,
        channels=tuple(args.channels.split(',')),
        fourpt_nev1=args.fourpt_nev1, fourpt_tsep=args.fourpt_tsep)
    print(f"\nrun complete → {res['run_dir']}")
    print(f"timing: {json.dumps(res['timing'], indent=2)}")


# ═══════════════════════════════════════════════════════════════════
# verify —— 一致性验证（vs 基线 output_20260802_120104）
# ═══════════════════════════════════════════════════════════════════

def _rel_maxdiff(a, b):
    """逐元素相对差的最大值（分母为 |b| 的 norm，避免除零）。

    NaN 处理：要求两边 NaN 位置完全相同；只对非 NaN 位置计算相对差
    （meff 在噪声尾区含 NaN 属物理预期，基线同样位置亦有 NaN）。
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.shape != b.shape:
        return float('inf')
    mask = np.isnan(a) | np.isnan(b)
    if mask.any():
        if not np.array_equal(np.isnan(a), np.isnan(b)):
            return float('inf')
        a = a[~mask]
        b = b[~mask]
        if a.size == 0:
            return 0.0
    denom = np.linalg.norm(b)
    if denom == 0:
        return float(np.linalg.norm(a))
    return float(np.linalg.norm(a - b) / denom)


def _cmp_one(name, a, b, tol, results):
    d = _rel_maxdiff(a, b)
    ok = d < tol
    results.append({'item': name, 'rel_diff': d, 'tol': tol, 'pass': ok,
                    'shape_a': list(np.shape(a)), 'shape_b': list(np.shape(b))})
    return ok


def verify_run(run_dir, conf_ids, out, verbose=True):
    """逐项比对 run_dir 与基线（磁盘数据，不 import examples）。"""
    results = []
    missing = []

    def load(base, rel):
        p = os.path.join(base, rel)
        return p if os.path.exists(p) else None

    # ── A. data/conf{id}/ 中间数据 ──
    conf_files = ['VdV_mom_{c}.npy', 'VVV_mom_{c}.npy',
                  'corr_pp_P0_{c}.npy', 'corr_pp_P2_{c}.npy',
                  'corr_pn_P0_{c}.npy', 'corr_pn_P2_{c}.npy',
                  'corr_pion_P0_{c}.npy', 'corr_pion_P2_{c}.npy',
                  'ope_combined_conf{c}.npy',
                  'proton_P0_3pt_{c}.npy', 'proton_P2_3pt_{c}.npy',
                  'pion_P0_3pt_{c}.npy', 'pion_P2_3pt_{c}.npy',
                  'pjnnjnp_4pt_{c}.npy']
    ops_files = ['ops_mu0_nu1_dz24_conf{c}.npz', 'ops_mu3_nu0_dz24_conf{c}.npz',
                 'ops_mu3_nu1_dz24_conf{c}.npz']
    for c in conf_ids:
        for pat in conf_files:
            fname = pat.format(c=c)
            fa = os.path.join(run_dir, 'data', f'conf{c}', fname)
            fb = os.path.join(BASELINE_DIR, 'data', f'conf{c}', fname)
            if not (os.path.exists(fa) and os.path.exists(fb)):
                if not os.path.exists(fb):
                    continue          # 基线本身没有该文件（如冒烟组态）→ 跳过
                missing.append(f'conf{c}/{fname}')
                continue
            _cmp_one(f'conf{c}/{fname}', np.load(fa), np.load(fb),
                     TOL_MIDDLE, results)
        for pat in ops_files:
            fname = pat.format(c=c)
            fa = os.path.join(run_dir, 'data', f'conf{c}', fname)
            fb = os.path.join(BASELINE_DIR, 'data', f'conf{c}', fname)
            if not (os.path.exists(fa) and os.path.exists(fb)):
                if not os.path.exists(fb):
                    continue
                missing.append(f'conf{c}/{fname}')
                continue
            _cmp_one(f'conf{c}/{fname}', np.load(fa)['ops'], np.load(fb)['ops'],
                     TOL_MIDDLE, results)

    # ── B. data/analysis/ 分析数组 ──
    # 统计量（jackknife 均值/误差）依赖组态数：与基线 10 组态不等时，
    # 只做存在性检查（warn），统计量严格比对仅在全量时启用。
    baseline_nconf = len(json.load(open(os.path.join(
        BASELINE_DIR, 'run_config.json')))['conf_ids']) \
        if os.path.exists(os.path.join(BASELINE_DIR, 'run_config.json')) else 10
    stat_full = (len(conf_ids) == baseline_nconf)
    if not stat_full:
        print(f"  [warn] conf 数 {len(conf_ids)} ≠ 基线 {baseline_nconf}："
              f"B/D 统计量仅存在性检查（全量 10 组态时严格比对）")
    an_files = []
    for had, mom in [('proton', 'P0'), ('proton', 'P2'),
                     ('pion', 'P0'), ('pion', 'P2')]:
        for base in ('meff', 'corr', 'ratio'):
            for tag in ('mean', 'err'):
                an_files.append(f'{base}_{had}_{mom}_{tag}.npy')
    for fname in an_files:
        fa = os.path.join(run_dir, 'data', 'analysis', fname)
        fb = os.path.join(BASELINE_DIR, 'data', 'analysis', fname)
        if not (os.path.exists(fa) and os.path.exists(fb)):
            if not os.path.exists(fb):
                continue
            missing.append(f'data/analysis/{fname}')
            continue
        if stat_full:
            _cmp_one(f'data/analysis/{fname}', np.load(fa), np.load(fb),
                     TOL_ANALYSIS, results)
        else:
            results.append({'item': f'data/analysis/{fname}',
                            'rel_diff': None, 'tol': None, 'pass': True,
                            'note': '存在性（Nconf≠基线）'})

    # ── C. analysis/disconnected/ ──
    # 注：Nconf<2 时 disconnected 拟合统计上无意义（pyqcd 自动跳过），
    #     缺失文件记 warn 不算失败；≥2 组态时必须完整。
    smoke = len(conf_ids) < 2
    disc_files = ['ratio_proton_P2.npy', 'ratio_pion_P2.npy',
                  '0_fit_data.npz']
    for fname in disc_files:
        fa = os.path.join(run_dir, 'analysis', 'disconnected', fname)
        fb = os.path.join(BASELINE_DIR, 'analysis', 'disconnected', fname)
        if not (os.path.exists(fa) and os.path.exists(fb)):
            if not os.path.exists(fb):
                continue
            if smoke:
                print(f"  [warn] 冒烟模式跳过 disconnected 比对（Nconf<2）: {fname}")
                continue
            missing.append(f'analysis/disconnected/{fname}')
            continue
        if smoke:
            results.append({'item': f'analysis/disconnected/{fname}',
                            'rel_diff': None, 'tol': None, 'pass': True,
                            'note': '存在性（Nconf<2）'})
            continue
        if fname.endswith('.npz'):
            da = np.load(fa); db = np.load(fb)
            for k in da.files:
                _cmp_one(f'analysis/disconnected/{fname}[{k}]',
                         da[k], db[k], TOL_ANALYSIS, results)
        else:
            _cmp_one(f'analysis/disconnected/{fname}',
                     np.load(fa), np.load(fb), TOL_ANALYSIS, results)

    # ── D. analysis_summary.json 标量 ──
    sa = os.path.join(run_dir, 'analysis_summary.json')
    sb = os.path.join(BASELINE_DIR, 'analysis_summary.json')
    if os.path.exists(sa) and os.path.exists(sb):
        ja = json.load(open(sa)); jb = json.load(open(sb))
        for had, mom in [('proton', 'P0'), ('proton', 'P2'),
                         ('pion', 'P0'), ('pion', 'P2')]:
            for k in ('E0', 'E0_err', 'E_exp', 'dev', 'npts'):
                va = ja.get('meff', {}).get(f'{had}_{mom}', {}).get(k)
                vb = jb.get('meff', {}).get(f'{had}_{mom}', {}).get(k)
                if va is None or vb is None:
                    continue
                if not stat_full:
                    results.append({'item': f'summary meff.{had}_{mom}.{k}',
                                    'rel_diff': None, 'tol': None,
                                    'pass': True,
                                    'note': '存在性（Nconf≠基线）'})
                    continue
                ok = _rel_maxdiff([va], [vb]) < TOL_SUMMARY
                results.append({'item': f'summary meff.{had}_{mom}.{k}',
                                'rel_diff': _rel_maxdiff([va], [vb]),
                                'tol': TOL_SUMMARY, 'pass': ok,
                                'va': va, 'vb': vb})
    else:
        missing.append('analysis_summary.json')

    # ── E. 图表与报告产物存在性 ──
    artifacts = ['plots/meff_all_channels.png',
                 'plots/correlators_all_channels.png',
                 'plots/ratio_3pt_all_channels.png',
                 'analysis/disconnected/c0_proton.png',
                 'analysis/disconnected/c0_pion.png',
                 'analysis/disconnected/chi2_proton.png',
                 'analysis/disconnected/chi2_pion.png',
                 'analysis/disconnected/ratio_proton.png',
                 'analysis/disconnected/ratio_pion.png',
                 'analysis/disconnected/1_fit_report.txt',
                 'physics_report.tex', 'physics_report.pdf',
                 'physics_report.log', 'physics_report.aux',
                 'physics_report.out', 'physics_report.toc',
                 'run_config.json']
    for rel in artifacts:
        fa = os.path.join(run_dir, rel)
        fb = os.path.join(BASELINE_DIR, rel)
        if not (os.path.exists(fa) and os.path.exists(fb)):
            if not os.path.exists(fb):
                continue
            if smoke and rel.startswith('analysis/disconnected/'):
                print(f"  [warn] 冒烟模式跳过 disconnected 产物（Nconf<2）: {rel}")
                continue
            missing.append(rel)
            continue
        results.append({'item': rel, 'rel_diff': 0.0, 'tol': None,
                        'pass': True, 'exists': True})

    n_pass = sum(1 for r in results if r['pass'])
    n_fail = sum(1 for r in results if not r['pass'])
    if verbose:
        print(f"一致项 {n_pass}/{len(results)}，失败 {n_fail}，缺文件 {len(missing)}")
        for r in results:
            mark = 'PASS' if r['pass'] else 'FAIL'
            d = r.get('rel_diff')
            if r.get('shape_a') and r['item'].startswith(('conf', 'data/analysis',
                                                          'analysis/disconnected')):
                print(f"  {mark} {r['item']:64s} rel={d:.3e} "
                      f"{r['shape_a']}")
            else:
                print(f"  {mark} {r['item']:64s} "
                      f"{('rel=' + f'{d:.3e}') if d is not None else ''}")
        for m in missing:
            print(f"  MISSING {m}")

    out['summary'] = {'n_pass': n_pass, 'n_fail': n_fail,
                      'n_missing': len(missing), 'total': len(results)}
    out['results'] = results
    out['missing'] = missing
    with open(os.path.join(run_dir, 'test0_verify.json'), 'w') as f:
        json.dump(out, f, indent=2)
    return n_fail == 0 and not missing


def cmd_verify(args):
    run_dir = os.path.abspath(args.run_dir)
    if not os.path.isdir(run_dir):
        print(f"[error] 运行目录不存在: {run_dir}")
        sys.exit(2)
    conf_ids = [int(x) for x in args.conf_ids.split(',')] \
        if args.conf_ids else DEFAULT_CONF_IDS
    print(f"verify vs {BASELINE_DIR}")
    print(f"run_dir = {run_dir}, conf_ids = {conf_ids}")
    ok = verify_run(run_dir, conf_ids, {}, verbose=True)
    print(f"verify: {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


def cmd_check(args):
    run_dir = os.path.abspath(args.run_dir)
    vpath = os.path.join(run_dir, 'test0_verify.json')
    if not os.path.exists(vpath):
        print(f"[error] 先运行 verify: {vpath} 不存在")
        sys.exit(2)
    data = json.load(open(vpath))
    s = data['summary']
    print(f"[{args.label}] gate: n_fail=0 且 无缺文件")
    print(f"  n_pass={s['n_pass']}/{s['total']}  n_fail={s['n_fail']}  "
          f"missing={s['n_missing']}")
    if s['n_fail'] or s['n_missing']:
        for r in data['results']:
            if not r['pass']:
                print(f"  FAIL {r['item']} rel={r.get('rel_diff')}")
        for m in data['missing']:
            print(f"  MISSING {m}")
        sys.exit(1)
    sys.exit(0)


# ═══════════════════════════════════════════════════════════════════
# plots / report —— 单步重跑（调用 pyqcd）
# ═══════════════════════════════════════════════════════════════════

def cmd_plots(args):
    run_dir = os.path.abspath(args.run_dir)
    from pyqcd.pipeline._steps import step_plots
    from pyqcd.pipeline._config import CONF_IDS as CIDS
    step_plots({'conf_ids': CIDS}, run_dir, print)
    print(f"plots regenerated → {run_dir}/plots")


def cmd_report(args):
    run_dir = os.path.abspath(args.run_dir)
    from pyqcd.pipeline._steps import step_report
    summary_path = os.path.join(run_dir, 'analysis_summary.json')
    if not os.path.exists(summary_path):
        print(f"[error] {summary_path} 不存在，先运行 analysis")
        sys.exit(2)
    with open(summary_path) as f:
        summary = json.load(f)
    step_report({'conf_ids': summary.get('conf_ids', DEFAULT_CONF_IDS),
                 'precision': summary.get('precision', 'complex64'),
                 'Nev1': summary.get('nev1', 100)},
                run_dir, print, None, summary.get('timing_s', {}),
                summary.get('env'))
    print(f"report regenerated → {run_dir}/physics_report.pdf")


def cmd_collect(args):
    """汇总版本目录产物清单（test12 collect 风格）。"""
    run_dir = os.path.abspath(args.run_dir)
    tree = []
    for root, dirs, files in os.walk(run_dir):
        dirs.sort()
        rel = os.path.relpath(root, run_dir)
        for f in sorted(files):
            p = os.path.join(root, f)
            tree.append({'path': os.path.join(rel, f),
                         'bytes': os.path.getsize(p)})
    out = {'run_dir': run_dir, 'n_files': len(tree),
           'total_mb': round(sum(t['bytes'] for t in tree) / 2**20, 1)}
    out['files'] = tree
    with open(os.path.join(run_dir, 'test0_collect.json'), 'w') as f:
        json.dump(out, f, indent=2)
    print(f"n_files={out['n_files']}, total={out['total_mb']} MB → "
          f"{run_dir}/test0_collect.json")


# ═══════════════════════════════════════════════════════════════════
# 子命令分派
# ═══════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="test0 —— pyqcd 蒸馏管线一致性测试套件")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--outdir', default=None,
                        help='输出目录（默认 $TEST0_OUTDIR，再默认 v<ts>/）')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('env', parents=[common])
    p.set_defaults(func=cmd_env)

    p = sub.add_parser('run', parents=[common])
    p.add_argument('--conf-ids', default=None, help='逗号分隔；默认 10 组态')
    p.add_argument('--steps', default='all',
                   help='逗号列表: env,vertex,2pt,ope,3pt,4pt,analysis,plots,report')
    p.add_argument('--skip-3pt', action='store_true')
    p.add_argument('--skip-4pt', action='store_true')
    p.add_argument('--precision', default='complex64',
                   choices=['complex64', 'complex128'])
    p.add_argument('--nev1', type=int, default=None)
    p.add_argument('--channels', default='pp,pn,pion')
    p.add_argument('--fourpt-nev1', type=int, default=None)
    p.add_argument('--fourpt-tsep', type=int, default=None)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser('verify', parents=[common])
    p.add_argument('--run-dir', required=True)
    p.add_argument('--conf-ids', default=None)
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser('check', parents=[common])
    p.add_argument('--run-dir', required=True)
    p.add_argument('--label', default='test0 check')
    p.set_defaults(func=cmd_check)

    p = sub.add_parser('plots', parents=[common])
    p.add_argument('--run-dir', required=True)
    p.set_defaults(func=cmd_plots)

    p = sub.add_parser('report', parents=[common])
    p.add_argument('--run-dir', required=True)
    p.set_defaults(func=cmd_report)

    p = sub.add_parser('collect', parents=[common])
    p.add_argument('--run-dir', required=True)
    p.set_defaults(func=cmd_collect)

    args = ap.parse_args()
    if args.cmd in ('verify', 'check', 'plots', 'report', 'collect'):
        os.environ['TEST0_OUTDIR'] = os.path.abspath(args.run_dir)
    else:
        os.environ['TEST0_OUTDIR'] = resolve_outdir(args)
    args.func(args)


if __name__ == '__main__':
    main()
