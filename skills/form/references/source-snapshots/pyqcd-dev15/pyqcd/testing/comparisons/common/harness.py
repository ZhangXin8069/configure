"""对照单测框架：参考实现 vs pyqcd 实现逐功能真实运行、计时与数值比对。"""
import json
import time
import traceback

import numpy as np


class Case:
    def __init__(self, cid, group, desc, run_ref, run_pq, tol=1e-10,
                 timeout=600, note='', compare='array'):
        self.cid = cid
        self.group = group
        self.desc = desc
        self.run_ref = run_ref
        self.run_pq = run_pq
        self.tol = tol
        self.timeout = timeout
        self.note = note
        self.compare = compare


def _leaf_diff(a, b):
    from pyqcd.testing import rel_maxdiff
    if isinstance(a, (str, bytes)) or isinstance(b, (str, bytes)):
        return 0.0 if a == b else float('inf')
    try:
        ca = np.asarray(a)
        cb = np.asarray(b)
        if ca.shape != cb.shape:
            return float('inf')
        if np.iscomplexobj(ca) or np.iscomplexobj(cb):
            fa = np.asarray(ca, dtype=complex)
            fb = np.asarray(cb, dtype=complex)
            denom = np.linalg.norm(fb)
            if denom == 0:
                return float(np.linalg.norm(fa))
            return float(np.linalg.norm(fa - fb) / denom)
        return rel_maxdiff(np.asarray(ca, dtype=np.float64),
                           np.asarray(cb, dtype=np.float64))
    except (TypeError, ValueError):
        return 0.0 if a == b else float('inf')


def _maxdiff(a, b):
    if isinstance(a, dict) or isinstance(b, dict):
        if not (isinstance(a, dict) and isinstance(b, dict)):
            return float('inf')
        if set(a) != set(b):
            return float('inf')
        return max((_maxdiff(a[k], b[k]) for k in a), default=0.0)
    if isinstance(a, (list, tuple)) or isinstance(b, (list, tuple)):
        if not isinstance(a, (list, tuple)) or not isinstance(b, (list, tuple)):
            return float('inf')
        if len(a) != len(b):
            return float('inf')
        return max((_maxdiff(x, y) for x, y in zip(a, b)), default=0.0)
    return _leaf_diff(a, b)


def run_case(case):
    rec = {'id': case.cid, 'group': case.group, 'desc': case.desc,
           'note': case.note}
    out_ref = None
    t_ref = t_pq = None
    try:
        t0 = time.perf_counter()
        out_ref = case.run_ref()
        t_ref = time.perf_counter() - t0
    except Exception:
        rec['status'] = 'ref_error'
        rec['err'] = traceback.format_exc()[-1200:]
    try:
        t0 = time.perf_counter()
        out_pq = case.run_pq()
        t_pq = time.perf_counter() - t0
    except Exception:
        rec['status'] = 'pq_error' if rec.get('status') != 'ref_error' else 'both_error'
        rec['err'] = traceback.format_exc()[-1200:]
        return rec
    rec['t_ref'] = round(t_ref, 4) if t_ref is not None else None
    rec['t_pq'] = round(t_pq, 4) if t_pq is not None else None
    if rec.get('status') == 'ref_error':
        return rec
    if case.compare == 'none':
        rec['diff'] = 0.0
        rec['pass'] = True
        rec['status'] = 'pass'
    elif callable(case.compare):
        d = case.compare(out_ref, out_pq)
        rec['diff'] = d
        rec["pass"] = bool(d <= case.tol)
        rec['status'] = 'pass' if rec['pass'] else 'diff'
    else:
        d = _maxdiff(out_ref, out_pq)
        rec['diff'] = d
        rec['pass'] = bool(d <= case.tol)
        rec['status'] = 'pass' if rec['pass'] else 'diff'
    if t_ref and t_pq:
        rec['speedup'] = round(t_ref / t_pq, 3)
    return rec


def summarize(results):
    n_pass = sum(1 for r in results if r['status'] == 'pass')
    lines = ['# 对照单测结果', '',
             '| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |',
             '|---|---|---|---|---|---|---|---|---|---|']
    for r in results:
        lines.append('| {status} | {id} | {group} | {desc} | {diff} | {tol} | {tr} | {tp} | {sp} | {note} |'.format(
            status=r['status'], id=r['id'], group=r['group'], desc=r['desc'],
            diff=r.get('diff', '-'), tol=r.get('tol', '-'),
            tr=r.get('t_ref', '-'), tp=r.get('t_pq', '-'),
            sp=r.get('speedup', '-') if r.get('speedup') is not None else '-',
            note=(r.get('note') or '') + (' ERR:' + r['err'][-160:] if 'err' in r else '')))
    lines.append('')
    lines.append(f'**PASS {n_pass}/{len(results)}**')
    return '\n'.join(lines)


def save_results(results, outdir):
    import os
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, 'results.json'), 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=1, default=str)
    with open(os.path.join(outdir, 'summary.md'), 'w') as f:
        f.write(summarize(results) + '\n')
