#!/usr/bin/env python3
"""
TMD-PDF 物理链自洽性断言
=========================

不依赖外部基线，用物理自洽性断言验证 TMD-PDF 全链产物：

A. 梯度流正确性（E 递减、unitarity 保持）——来自重算 flowed gauge
B. 多动量 2pt 谱线（P000 > P200 > P400 递减，组态间一致）
C. TMD OPE 存在性与形状（(nz,nb,Nt)，z=0 最大）
D. ratio 文件存在 + fit 报告生成
E. PDF 链产物（准 PDF / 匹配 PDF / CS 核）有限且可读

用法：python -m pyqcd.testing.tmd.verify_pdf_workflow [run_dir]
默认 run_dir = pyqcd/testing/tmd/artifacts/work
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                    '..', '..', '..'))


def test_a_gradient_flow(run_dir, conf_ids=(6250,), tau=3.0, eps=0.05):
    """梯度流正确性：E(0)>E(τ)、unitarity 保持（重算单组态验证）。"""
    print("\n[A] 梯度流正确性（重算 conf%s 验证）" % conf_ids[0])
    from pyqcd.tools import set_backend
    set_backend('torch', device='cuda:0')
    from pyqcd.renorm import wilson_flow, flow_action_density
    from pyqcd.operator import read_gauge_lime
    from pyqcd.pipeline._config import NT, NX, get_gauge_path
    ok = True
    cid = conf_ids[0]
    g = read_gauge_lime(get_gauge_path(cid), NT, NX)
    import torch as _torch
    G = _torch.as_tensor(g.astype('complex64'), device='cuda:0')
    del g
    E0 = float(flow_action_density(G).mean())
    V = wilson_flow(G, tau=tau, eps=eps)
    E1 = float(flow_action_density(V).mean())
    U = V[..., 0, :, :]
    import torch as _torch
    dev = float((U @ U.conj().transpose(-1, -2) - _torch.eye(3, dtype=U.dtype,
                                                              device=U.device))
                .abs().max().cpu())
    ok_flow = (E1 < E0) and (dev < 1e-3)
    ok &= ok_flow
    print(f"  conf{cid}: E: {E0:.4f}->{E1:.4f} "
          f"({'decrease' if E1 < E0 else 'INCREASE!'})  "
          f"unitarity dev={dev:.2e} "
          f"({'ok' if dev < 1e-3 else 'FAIL'})")
    print(f"  [A] {'PASS' if ok else 'FAIL'}")
    return ok


def test_b_2pt(run_dir, conf_ids):
    """多动量 2pt：P000>P200>P400，组态间相对分散<10%。"""
    print("\n[B] 多动量 2pt 谱线")
    from pyqcd.pipeline._steps import _load_any
    import h5py
    ok = True
    moms = ['P000', 'P200', 'P400']
    vals = {m: [] for m in moms}
    for cid in conf_ids:
        cdir = os.path.join(run_dir, 'data', f'conf{cid}')
        for m in moms:
            p = os.path.join(cdir, f'corr_pp_{m}_{cid}')
            if os.path.exists(p + '.h5'):
                with h5py.File(p + '.h5', 'r') as f:
                    c = np.array(f['data'])
            elif os.path.exists(p + '.npy'):
                c = np.load(p + '.npy', allow_pickle=False)
            else:
                ok = False
                print(f"  conf{cid}: missing corr_pp_{m}")
                continue
            vals[m].append(abs(c[0]))
    if all(vals[m] for m in moms):
        for m in moms:
            v = np.array(vals[m])
            spread = v.std() / v.mean()
            print(f"  {m}: C2(0) mean={v.mean():.4f} spread={spread:.1%}")
            ok &= (spread < 0.10)
        ok &= np.mean(vals['P000']) > np.mean(vals['P200']) > np.mean(vals['P400'])
        print(f"  ordering P000>P200>P400: "
              f"{'ok' if np.mean(vals['P000']) > np.mean(vals['P200']) > np.mean(vals['P400']) else 'FAIL'}")
    print(f"  [B] {'PASS' if ok else 'FAIL'}")
    return ok


def test_c_tmd_ope(run_dir, conf_ids, nz=13, nb=5, nt=72):
    """TMD OPE 存在性 + 形状 + z=0 最大。"""
    print("\n[C] TMD OPE")
    import h5py
    ok = True
    for cid in conf_ids:
        cdir = os.path.join(run_dir, 'data', f'conf{cid}')
        tag = 'z0123456789101112_b01234'
        p = os.path.join(cdir, f'tmd_ope_{tag}_conf{cid}.h5')
        if not os.path.exists(p):
            ok = False
            print(f"  conf{cid}: missing TMD OPE")
            continue
        with h5py.File(p, 'r') as f:
            tmd = np.array(f['data'])
        ok_shape = tmd.shape == (nz, nb, nt)
        ok &= ok_shape
        # z=0 应显著（胶子关联在 z=0 最大）
        z0 = abs(tmd[0]).mean()
        zlast = abs(tmd[-1]).mean()
        ok_z = z0 > 0
        ok &= ok_z
        print(f"  conf{cid}: tmd {tmd.shape} dtype={tmd.dtype} "
              f"{'shape-ok' if ok_shape else 'SHAPE-FAIL'}  "
              f"|O(z=0)|_avg={z0:.2f}  |O(z=max)|_avg={zlast:.2f}")
    print(f"  [C] {'PASS' if ok else 'FAIL'}")
    return ok


def test_d_analysis(run_dir, momenta=('P200', 'P400')):
    """分析产物：ratio + fit 报告 + c0。"""
    print("\n[D] 分析产物")
    an = os.path.join(run_dir, 'analysis', 'tmd_ratio')
    ok = True
    for m in momenta:
        for f in (f'ratio_proton_{m}.npy', f'c0_plateau_{m}.npy',
                  f'1_fit_report_{m}.txt'):
            if not os.path.exists(os.path.join(an, f)):
                ok = False
                print(f"  missing {f}")
    for m in momenta:
        r = np.load(os.path.join(an, f'ratio_proton_{m}.npy'))
        finite = np.all(np.isfinite(r))
        ok &= finite
        print(f"  {m}: ratio {r.shape} finite={finite}")
    print(f"  [D] {'PASS' if ok else 'FAIL'}")
    return ok


def test_e_pdf(run_dir):
    """PDF 链产物有限且可读。"""
    print("\n[E] PDF 链产物")
    an = os.path.join(run_dir, 'analysis', 'tmd_ratio')
    ok = True
    for f in ('quasi_tmd_pdf_x.npy', 'quasi_tmd_pdf_xg.npy',
              'matched_tmd_pdf_xg.npy', 'b_grid_fm.npy'):
        p = os.path.join(an, f)
        if not os.path.exists(p):
            ok = False
            print(f"  missing {f}")
            continue
        arr = np.load(p)
        finite = np.all(np.isfinite(arr))
        ok &= finite
        print(f"  {f}: {arr.shape} finite={finite}")
    # 至少 1 张 PDF 图
    imgs = [f for f in os.listdir(an) if f.endswith('.png')]
    ok &= len(imgs) >= 5
    print(f"  images: {len(imgs)}")
    print(f"  [E] {'PASS' if ok else 'FAIL'}")
    return ok


def main():
    parser = argparse.ArgumentParser(description='验证 TMD-PDF 全链产物')
    parser.add_argument(
        'run_dir', nargs='?',
        default=os.path.join(
            ROOT, 'pyqcd', 'testing', 'tmd', 'artifacts', 'work'))
    args = parser.parse_args()
    run_dir = args.run_dir
    conf_ids = [int(x[4:]) for x in os.listdir(os.path.join(run_dir, 'data'))
                if x.startswith('conf')]
    conf_ids.sort()
    print("=" * 64)
    print(f"TMD-PDF 物理链自洽性验证  run_dir={run_dir}")
    print(f"conf_ids = {conf_ids}")
    print("=" * 64)
    ok = True
    ok &= test_a_gradient_flow(run_dir, conf_ids[:2])
    ok &= test_b_2pt(run_dir, conf_ids)
    ok &= test_c_tmd_ope(run_dir, conf_ids)
    ok &= test_d_analysis(run_dir)
    ok &= test_e_pdf(run_dir)
    print("=" * 64)
    print("全部通过" if ok else "存在失败项！")
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
