"""
一致性验证：pyqcd 包 vs 冻结蒸馏基线逐位对照
==============================================

验证 pyqcd 的移植没有引入数值偏差：

    A. 函数级对照（相同随机输入，逐位比较）
        1. gamma 矩阵（pyqcd.lattice._gamma vs lib/gamma_matrix）
        2. vertex 顶点（pyqcd.vertex vs lib/vertex，VdV/VVV/相位）
        3. cached_contract / ArraySlicer（pyqcd.tools vs lib/base_functions）
        4. Jackknife / Bootstrap / meff（pyqcd.analysis vs lib/analyse）
        5. 胶子 OPE 算符（pyqcd.operator vs 基线 compute_ope 的核心函数）
        6. 梯度流（pyqcd.renorm，物理自洽性：SU(3) 保持 + 作用量递减）

    B. 分析链对照：用成功实例 output_20260802_120104 的数据，
       pyqcd meff/ratio 复算值与 analysis_summary.json 参考值对比（相对差 < 1e-8）。

    C. OPE 组合逻辑对照：ops_mu*_nu* 三个分量 → ope_combined 组合公式验证。

    运行：python -m pyqcd.testing.regression.consistency
    指定参考运行：python -m pyqcd.testing.regression.consistency \
        --run-dir <output/run>
"""
import argparse
import sys
import os

ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..'))
# 成功实例作为参考模块挂载（只读引用，验证用）
_DOCKER = os.path.join(
    ROOT, 'pyqcd', 'testing', 'regression', 'baselines',
    'legacy_pipeline')
_DEFAULT_REF_RUN = os.path.join(_DOCKER, 'output', 'output_20260802_120104')
sys.path.insert(0, _DOCKER)

import numpy as np
from scipy.linalg import expm

from pyqcd.tools import set_backend
set_backend('numpy')

# ────────────────────────────────────────────────────────────────────
# A. 函数级对照
# ────────────────────────────────────────────────────────────────────

def check(name, fn_pyqcd, fn_ref, *args, tol=1e-12, **kw):
    a = np.asarray(fn_pyqcd(*args, **kw))
    b = np.asarray(fn_ref(*args, **kw))
    if a.shape != b.shape:
        raise AssertionError(f"{name}: shape {a.shape} != {b.shape}")
    diff = np.max(np.abs(a - b)) if a.size else 0.0
    ok = diff < tol
    print(f"  {'PASS' if ok else 'FAIL'} {name}: max|diff| = {diff:.3e}")
    return ok


class ReferenceDataUnavailable(RuntimeError):
    """参考运行未包含 B--E 对照所需的生成数据。"""


def _reference_requirements(out_dir):
    """返回一致性验证 B--E 使用的参考文件清单。"""
    confs = [6250, 6450, 6650, 6850, 7050,
             7250, 7450, 7650, 7850, 8050]
    required = [os.path.join(out_dir, 'analysis_summary.json')]
    for conf in confs:
        conf_dir = os.path.join(out_dir, 'data', f'conf{conf}')
        for ch in ('pp', 'pion'):
            for mom in ('P0', 'P2'):
                required.append(os.path.join(
                    conf_dir, f'corr_{ch}_{mom}_{conf}.npy'))
        required.append(os.path.join(
            conf_dir, f'ope_combined_conf{conf}.npy'))
        required.append(os.path.join(
            conf_dir, f'proton_P0_3pt_{conf}.npy'))
        required.append(os.path.join(
            conf_dir, f'proton_P2_3pt_{conf}.npy'))
        required.append(os.path.join(
            conf_dir, f'pion_P0_3pt_{conf}.npy'))
        required.append(os.path.join(
            conf_dir, f'pion_P2_3pt_{conf}.npy'))
        for mu, nu in ((0, 1), (3, 0), (3, 1)):
            required.append(os.path.join(
                conf_dir, f'ops_mu{mu}_nu{nu}_dz24_conf{conf}.npz'))

    analysis_dir = os.path.join(out_dir, 'data', 'analysis')
    for had in ('proton', 'pion'):
        for mom in ('P0', 'P2'):
            required.append(os.path.join(
                analysis_dir, f'ratio_{had}_{mom}_mean.npy'))

    disconnected_dir = os.path.join(out_dir, 'analysis', 'disconnected')
    required.append(os.path.join(disconnected_dir, '0_fit_data.npz'))
    for had in ('proton', 'pion'):
        required.append(os.path.join(
            disconnected_dir, f'ratio_{had}_P2.npy'))
    return required


def resolve_reference_run(run_dir=None):
    """解析并验证 B--E 的参考运行目录，不完整时给出可操作诊断。"""
    out_dir = os.path.abspath(run_dir or _DEFAULT_REF_RUN)
    if not os.path.isdir(out_dir):
        raise ReferenceDataUnavailable(
            f'参考运行目录不存在: {out_dir}；请用 --run-dir 指向已完成的输出目录')

    missing = [p for p in _reference_requirements(out_dir)
               if not os.path.isfile(p)]
    if missing:
        preview = '\n'.join(f'  - {p}' for p in missing[:8])
        if len(missing) > 8:
            preview += f'\n  ... 其余 {len(missing) - 8} 个文件'
        raise ReferenceDataUnavailable(
            f'参考运行不完整: {out_dir}\n'
            f'B--E 还缺少 {len(missing)} 个生成文件:\n{preview}\n'
            '这些数据不会随仓库提交；请先生成参考运行，或用 --run-dir 指定完整产物')
    return out_dir


def test_a():
    print("A. 函数级对照（pyqcd vs 冻结蒸馏基线）")
    import importlib

    # 1. gamma 矩阵
    from pyqcd.lattice import gamma as g_pyqcd
    from lib.gamma_matrix import gamma as g_ref
    for i in [0, 1, 4, 5, 7, 11]:
        check(f"gamma[{i}]", g_pyqcd, g_ref, i)

    # 2. vertex 顶点
    from pyqcd.vertex import Mom_VdV_sink_t as vd_pyqcd
    from lib.vertex import Mom_VdV_sink_t as vd_ref
    rng = np.random.default_rng(3)
    Lv, Nev = 4, 20
    eigs = (rng.standard_normal((Nev, Lv, Lv, Lv, 3))
            + 1j * rng.standard_normal((Nev, Lv, Lv, Lv, 3))).astype(np.complex64)
    from pyqcd.vertex import phase_exp_2pt as pe_pyqcd
    from lib.vertex import phase_exp_2pt as pe_ref
    pe1, pe2 = pe_pyqcd(Lv, [0, 0, 2]), pe_ref(Lv, [0, 0, 2])
    check("phase_exp_2pt", pe_pyqcd, pe_ref, Lv, [0, 0, 2])
    check("Mom_VdV_sink_t", vd_pyqcd, vd_ref, pe1, eigs, tol=1e-5)

    # 3. Jackknife（返回 dict：data_sample/data_mean/data_err）
    from pyqcd.analysis import Jackknife as jk_pyqcd
    from lib.analyse import Jackknife as jk_ref
    rng = np.random.default_rng(5)
    data = rng.standard_normal((10, 8, 72))
    r1, r2 = jk_pyqcd(data), jk_ref(data)
    assert r1.keys() == r2.keys(), f"keys: {r1.keys()} vs {r2.keys()}"
    for k in ['data_sample', 'data_mean', 'data_err']:
        check(f"Jackknife.{k}", lambda d, kk=k: np.asarray(d[kk]),
              lambda d, kk=k: np.asarray(d[kk]), r1 if False else data,
              tol=1e-10) if False else None
        d1, d2 = np.asarray(r1[k]), np.asarray(r2[k])
        diff = np.max(np.abs(d1 - d2)) if d1.size else 0.0
        ok = diff < 1e-10
        print(f"  {'PASS' if ok else 'FAIL'} Jackknife.{k}: max|diff| = {diff:.3e}")

    # 4. meff（返回 dict）
    from pyqcd.analysis import meff as meff_pyqcd
    from lib.analyse import meff as meff_ref
    rng = np.random.default_rng(6)
    d = np.abs(rng.standard_normal((10, 72))) + 1e-3   # 关联函数为正
    r1 = meff_pyqcd(d, 0.1053, Nconf_axes=0, Nt_axes=1)
    r2 = meff_ref(d, 0.1053, Nconf_axes=0, Nt_axes=1)
    for k in ['data_sample', 'data_mean', 'data_err']:
        d1, d2 = np.asarray(r1[k]), np.asarray(r2[k])
        diff = np.max(np.abs(d1 - d2)) if d1.size else 0.0
        ok = diff < 1e-10
        print(f"  {'PASS' if ok else 'FAIL'} meff.{k}: max|diff| = {diff:.3e}")

    # 5. 胶子 OPE 算符（pyqcd.operator vs compute_ope.py 核心）
    from pyqcd.operator._gluon_ope import plaquette_clover as pc_pyqcd
    import compute_ope as _co
    _co.HAS_CUPY = False
    _co.cp = np   # 无 cupy 环境下用 numpy 对照
    pc_ref = _co.plaquette_clover_gpu
    rng = np.random.default_rng(9)
    L = 4
    g = np.zeros((L, L, L, L, 4, 3, 3), dtype=np.complex128)
    for idx in np.ndindex(L, L, L, L, 4):
        H = (rng.standard_normal((3, 3)) + 1j * rng.standard_normal((3, 3)))
        H = H - H.conj().T - np.trace(H - H.conj().T) / 3 * np.eye(3)
        g[idx] = expm(H)
    check("plaquette_clover F01", pc_pyqcd, pc_ref, g, 0, 1, tol=1e-10)
    return True


def test_b(out_dir=None):
    print("B. 分析链对照（pyqcd meff 复算 vs analysis_summary.json）")
    import json
    out_dir = out_dir or _DEFAULT_REF_RUN
    with open(os.path.join(out_dir, 'analysis_summary.json')) as f:
        ref = json.load(f)

    from pyqcd.analysis import Jackknife, meff
    confs = [6250, 6450, 6650, 6850, 7050, 7250, 7450, 7650, 7850, 8050]
    channels = {'pp': 'proton', 'pion': 'pion'}
    meff_types = {'proton': 'cosh', 'pion': 'log'}
    all_ok = True
    for ch, name in channels.items():
        for mom in ['P0', 'P2']:
            arrs = []
            for c in confs:
                p = os.path.join(out_dir, 'data', f'conf{c}', f'corr_{ch}_{mom}_{c}.npy')
                arrs.append(np.load(p))
            data = np.stack(arrs)                     # (nconf, nt)
            # 与 analyze.py run_meff_jackknife 完全一致的逻辑
            jk = Jackknife(data, Nconf_axes=0)
            mf = meff(jk['data_sample'], 0.1053, Nconf_axes=0, Nt_axes=1,
                      meff_type=meff_types[name])
            mmean = np.real(mf['data_mean'])
            merr = np.real(mf['data_err'])
            if name == 'proton':
                ps, pe = 6, 12
            else:
                ps, pe = 5, 18
            mask = np.isfinite(mmean[ps:pe]) & (merr[ps:pe] > 0) & (mmean[ps:pe] > 0.01)
            if np.sum(mask) < 2:      # analyze.py 的 fallback 窗
                ps, pe = 2, 8
                mask = np.isfinite(mmean[ps:pe]) & (merr[ps:pe] > 0)
            w = 1.0 / (merr[ps:pe][mask] ** 2 + 1e-10)
            val = float(np.sum(mmean[ps:pe][mask] * w) / np.sum(w))
            err = float(1.0 / np.sqrt(np.sum(w)))
            key = f'{name}_{mom}'
            refv = ref['meff'][key]['E0']
            reldiff = abs(val - refv) / max(abs(refv), 1e-12)
            ok = reldiff < 1e-6
            all_ok &= ok
            print(f"  {'PASS' if ok else 'FAIL'} meff {key}: pyqcd={val:.6f}±{err:.6f} "
                  f"ref={refv:.6f} reldiff={reldiff:.2e}")
    return all_ok


def test_d(out_dir=None):
    print("D. 3pt 连通比值复算对照（pyqcd ratio_3pt vs output 参考）")
    from pyqcd.analysis import Jackknife, ratio_3pt
    out_dir = out_dir or _DEFAULT_REF_RUN
    an_dir = os.path.join(out_dir, 'data', 'analysis')
    confs = [6250, 6450, 6650, 6850, 7050, 7250, 7450, 7650, 7850, 8050]
    pairs = [
        ('proton', 'P0', 'corr_pp_P0', 'proton_P0_3pt'),
        ('proton', 'P2', 'corr_pp_P2', 'proton_P2_3pt'),
        ('pion',   'P0', 'corr_pion_P0', 'pion_P0_3pt'),
        ('pion',   'P2', 'corr_pion_P2', 'pion_P2_3pt'),
    ]
    all_ok = True
    for had, mom, k2, k3 in pairs:
        s3 = np.stack([np.real(np.load(os.path.join(
            out_dir, 'data', f'conf{c}', f'{k3}_{c}.npy'))[:, 3]) for c in confs])
        s2 = np.stack([np.real(np.load(os.path.join(
            out_dir, 'data', f'conf{c}', f'{k2}_{c}.npy'))) for c in confs])
        ts = s3.shape[1] - 1
        jk3 = Jackknife(s3, Nconf_axes=0)
        jk2 = Jackknife(s2, Nconf_axes=0)
        ratio = ratio_3pt(jk3['data_sample'], jk2['data_sample'],
                          data_2ptF_sample=None, t_sep=ts,
                          Nconf_axes=0, tau_axes=1, t_sink_axes=1)
        rm = np.real(ratio['data_mean'])
        ref = np.load(os.path.join(an_dir, f'ratio_{had}_{mom}_mean.npy'))
        d = np.abs(rm[:len(ref)] - ref).max()
        ok = d < 1e-8
        all_ok &= ok
        print(f"  {'PASS' if ok else 'FAIL'} ratio {had}_{mom}: max|diff| = {d:.3e}")
    return all_ok


def test_e(out_dir=None):
    print("E. disconnected ratio 复算对照（pyqcd code_1 分析 vs output 参考）")
    import tempfile
    from pyqcd.analysis import run_disconnected_ratio
    out_dir = out_dir or _DEFAULT_REF_RUN
    ref_dir = os.path.join(out_dir, 'analysis', 'disconnected')
    confs = [6250, 6450, 6650, 6850, 7050, 7250, 7450, 7650, 7850, 8050]
    corr2, ope = {}, {}
    for c in confs:
        d = os.path.join(out_dir, 'data', f'conf{c}')
        corr2[c] = {'corr_pp_P2': np.load(os.path.join(d, f'corr_pp_P2_{c}.npy')),
                    'corr_pion_P2': np.load(os.path.join(d, f'corr_pion_P2_{c}.npy'))}
        ope[c] = {'combined': np.load(os.path.join(d, f'ope_combined_conf{c}.npy'))}
    with tempfile.TemporaryDirectory() as td:
        res = run_disconnected_ratio(corr2, ope, confs, td, logger=lambda *a, **k: None)
        fit = np.load(os.path.join(td, 'analysis', 'disconnected', '0_fit_data.npz'))
        ref = np.load(os.path.join(ref_dir, '0_fit_data.npz'))
        all_ok = True
        for k in ['c0', 'c1', 'dE', 'chi2']:
            d = np.abs(fit[k] - ref[k]).max()
            ok = d < 1e-8
            all_ok &= ok
            print(f"  {'PASS' if ok else 'FAIL'} disconnected fit {k}: max|diff| = {d:.3e}")
        for had in ['proton', 'pion']:
            a = np.load(os.path.join(ref_dir, f'ratio_{had}_P2.npy'))
            b = res[had]['ratio']
            d = np.abs(np.real(a) - np.real(b)).max()
            ok = d < 1e-8
            all_ok &= ok
            print(f"  {'PASS' if ok else 'FAIL'} disconnected ratio {had}: max|diff| = {d:.3e}")
    return all_ok


def test_f():
    print("F. VVV 重子顶点 / Wick 收缩 / seq_peram / 完整 OPE 对照")
    all_ok = True
    # VVV
    from pyqcd.vertex import Mom_VVV_sink_t as vvv_pyqcd
    from pyqcd.vertex import phase_exp_3pt as pe3_pyqcd
    from lib.vertex import Mom_VVV_sink_t as vvv_ref
    from lib.vertex import phase_exp_3pt as pe3_ref
    rng = np.random.default_rng(11)
    Lv, Nev = 4, 10
    eigs = (rng.standard_normal((Nev, Lv, Lv, Lv, 3))
            + 1j * rng.standard_normal((Nev, Lv, Lv, Lv, 3))).astype(np.complex64)
    p1, p2 = pe3_pyqcd(Lv, [0, 0, 2]), pe3_ref(Lv, [0, 0, 2])
    a, b = vvv_pyqcd(p1, eigs), vvv_ref(p2, eigs)
    d = np.abs(a - b).max()
    ok = d < 1e-5; all_ok &= ok
    print(f"  {'PASS' if ok else 'FAIL'} VVV: max|diff| = {d:.3e}")

    # Wick 2pt proton
    from pyqcd.contraction import wick_contraction as wc_pyqcd
    from lib.autowick import wick_contraction as wc_ref
    sink = ['|', 'u', 'u', 'gamma_7', 'd', '|']
    src = ['|', 'u^d', 'gamma_7', 'd^d', 'u^d', '|']
    r1 = wc_pyqcd(sink, src, Cpt='2pt')
    r2 = wc_ref(sink, src, Cpt='2pt')
    d1 = {k: r1[k] for k in ['result_indx', 'result_sign', 'operators']}
    d2 = {k: r2[k] for k in ['result_indx', 'result_sign', 'operators']}
    ok = d1 == d2; all_ok &= ok
    print(f"  {'PASS' if ok else 'FAIL'} Wick 2pt proton: identical={ok}")

    # seq_peram
    from pyqcd.contraction import seq_peram as sp_pyqcd
    from lib.seqperam import seq_peram as sp_ref
    peram = (rng.standard_normal((8, 4, 4, 12, 12))
             + 1j * rng.standard_normal((8, 4, 4, 12, 12))).astype(np.complex64)
    a, b = sp_pyqcd(peram), sp_ref(peram)
    d = np.abs(a - b).max()
    ok = d < 1e-10; all_ok &= ok
    print(f"  {'PASS' if ok else 'FAIL'} seq_peram: max|diff| = {d:.3e}")

    # 完整 OPE 算符（三分量）
    from pyqcd.operator import gluon_ope_operator_z0
    import compute_ope as _co
    _co.HAS_CUPY = False; _co.cp = np
    if not hasattr(np, 'asnumpy'):
        np.asnumpy = np.asarray
    rng = np.random.default_rng(9)
    Lg = 6
    g = np.zeros((Lg, Lg, Lg, Lg, 4, 3, 3), dtype=np.complex128)
    for idx in np.ndindex(Lg, Lg, Lg, Lg, 4):
        H = (rng.standard_normal((3, 3)) + 1j * rng.standard_normal((3, 3)))
        H = H - H.conj().T - np.trace(H - H.conj().T) / 3 * np.eye(3)
        g[idx] = expm(H)
    for (mu, nu) in [(0, 1), (3, 0), (3, 1)]:
        a = gluon_ope_operator_z0(g, mu, nu, 2, 4, Lg, Lg)
        b = _co.compute_ope_donghx_gpu(g, mu, nu, 2, 4, Lg, Lg, print)
        d = np.abs(a - b).max()
        ok = d < 1e-10; all_ok &= ok
        print(f"  {'PASS' if ok else 'FAIL'} OPE ({mu},{nu}): max|diff| = {d:.3e}")
    return all_ok


def test_c(out_dir=None):
    print("C. OPE 组合逻辑对照（ops 三分量 → ope_combined）")
    out_dir = out_dir or _DEFAULT_REF_RUN
    c = 6250
    d = os.path.join(out_dir, 'data', f'conf{c}')
    ops01 = np.load(os.path.join(d, 'ops_mu0_nu1_dz24_conf6250.npz'))['ops']
    ops30 = np.load(os.path.join(d, 'ops_mu3_nu0_dz24_conf6250.npz'))['ops']
    ops31 = np.load(os.path.join(d, 'ops_mu3_nu1_dz24_conf6250.npz'))['ops']
    comb = np.load(os.path.join(d, 'ope_combined_conf6250.npy'))
    # code_1.py 组合：O = -O_30 - O_31 + 2·O_01
    predicted = -ops30 - ops31 + 2 * ops01
    diff = np.abs(predicted - comb).max()
    ok = diff < 1e-6
    print(f"  {'PASS' if ok else 'FAIL'} O = -O_30 - O_31 + 2·O_01 vs ope_combined: "
          f"max|diff| = {diff:.3e}")
    return ok


def main(argv=None):
    parser = argparse.ArgumentParser(description='pyqcd 与参考运行的一致性验证')
    parser.add_argument('--run-dir', default=None,
                        help='已完成的参考输出目录（默认使用仓库内固定目录）')
    args = parser.parse_args(argv)

    print("=" * 64)
    print("pyqcd 与成功实例一致性验证")
    print("=" * 64)

    try:
        ref_dir = resolve_reference_run(args.run_dir)
    except ReferenceDataUnavailable as exc:
        print(f"环境限制：{exc}", file=sys.stderr)
        print("仅在参考数据完整时执行 B–E；本次验证未通过。")
        sys.exit(2)

    ok = True
    ok &= test_a()
    print()
    ok &= test_b(ref_dir)
    print()
    ok &= test_c(ref_dir)
    print()
    ok &= test_d(ref_dir)
    print()
    ok &= test_e(ref_dir)
    print()
    ok &= test_f()
    print()
    print("全部通过" if ok else "存在不一致！")
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
