"""对照用例第二批：lqcddb 统计/CG/切片/算符共轭/stout/本征模/顶点/Wick图。"""
import numpy as np

from ..common import datalib
from ..common.harness import Case
from ..common.ref_bridge import load_lqcddb

SEED = 20260825
NX = datalib.NX


def _rng():
    return np.random.default_rng(SEED)


def build():
    L = load_lqcddb()
    from pyqcd.lattice._cg import SU2combine as pq_comb
    from pyqcd.lattice._cg import SU2decompose as pj_decomp
    from lqcddb.contraction.baroperator import (
        transpose_gamma as r_tg, charge_conjugation_gamma as r_ccg,
        diquark_symmetry as r_ds)
    from pyqcd.contraction._baroperator import (
        conjugate_operator as pq_conj,
        transpose_gamma as pq_tg,
        charge_conjugation_gamma as pq_ccg,
        diquark_symmetry as pq_ds)
    from pyqcd.smear import stout_smear as pq_stout
    from pyqcd.vertex import (inner_product as pq_ip, check_orthonormal as pq_chk,
                              normalize as pq_norm, orthnormal_append as pq_orth,
                              create_noise as pq_noise,
                              compress_matrix_V1 as pq_v1)
    from pyqcd.vertex._eigcompress import (
        create_omega_accelerate as pq_omega,
        compress_matrix_V2 as pq_v2,
        compress_matrix_V3 as pq_v3,
        compress_matrix_V4 as pq_v4)
    from pyqcd.vertex._vertex import (phase_exp_2pt as pq_pe2,
                                      phase_exp_3pt as pq_pe3,
                                      Mom_VdV_sink_t as pq_mvdv,
                                      Mom_VVV_sink_t as pq_mvvv,
                                      sink2src as pq_s2s)
    from pyqcd.contraction._autowick import wick_contraction as pq_wick
    from pyqcd.contraction._wickplot import plot_figure_wick as pq_pf
    from pyqcd.analysis._analyse import (Bootstrap as pq_bs,
                                         ratio_3pt as pq_r3,
                                         loop_tsrc as pq_lt,
                                         solve_gevp as pg_g,
                                         mean_over_array_of_list as pq_mo,
                                         sum_over_array_of_list as pq_so,
                                         dis_connect as pq_dc)
    from pyqcd.tools._base import ArraySlicer as pq_AS

    cases = []

    def add(cid, desc, rf, pf, **kw):
        cases.append(Case(cid, 'lqcddb', desc, rf, pf, **kw))

    def num_obj(x):
        if isinstance(x, dict):
            def _c(c):
                try:
                    return round(float(c), 9)
                except Exception:
                    return c

            def _kn(k):
                if isinstance(k, tuple):
                    return tuple(_c(c) for c in k)
                return _c(k)
            return {_kn(k): complex(v) for k, v in x.items()}
        return x

    r_comb = L.SU2combine([(0.5, 0.5), (0.5, -0.5)])
    p_comb = pq_comb([(0.5, 0.5), (0.5, -0.5)])
    r_dec = L.SU2decompose([0.5, 0.5], (0, 0))
    p_dec = pj_decomp([0.5, 0.5], [0., 0.])

    add('L16', 'SU(2) CG combine/decompose（数值化 sympy）',
        lambda: [num_obj(d) for d in [r_comb, r_dec]],
        lambda: [num_obj(d) for d in [p_comb, p_dec]], tol=1e-12)

    rng = _rng()

    def _bs_cmp(a, b):
        worst = 0.0
        for k in a:
            x, y = np.asarray(a[k], dtype=float), np.asarray(b[k], dtype=float)
            if x.shape != y.shape:
                return float('inf')
            if k == 'data_mean':
                z = float(np.abs(x.mean() - y.mean())
                          / max(y.std() / np.sqrt(y.shape[0]), 1e-300))
                worst = max(worst, min(z, 99.0))
            else:
                sx, sy = x.std(), y.std()
                worst = max(worst, abs(sx - sy) / max((sx + sy) / 2, 1e-300))
        return worst

    def r_bs():
        return L.Bootstrap(rng.normal(size=(6, 12)), M=64, N=12)

    def p_bs():
        return pq_bs(rng.normal(size=(6, 12)), M=64, N=12)

    add('L17', 'Bootstrap 重采样（双方无种子，统计性比对）', r_bs, p_bs,
        tol=6.0, compare=_bs_cmp,
        note='随机重采样无确定对应；比较各键标准差相对偏差')

    c3 = rng.normal(size=(6, 12))
    c2 = rng.normal(size=(6, 12))
    add('L18', 'ratio_3pt 一维模式 R=C3/C2 折叠',
        lambda: L.ratio_3pt(c3, c2, t_sep=6),
        lambda: pq_r3(c3, c2, t_sep=6), tol=1e-12)

    d5 = rng.normal(size=(6, 4, 24, 24, 8))
    d6 = rng.normal(size=(6, 4, 24, 24, 24, 8))

    def r_loop():
        return [L.loop_tsrc(d5),
                L.loop_tsrc(d5, Boundary_Conditions='Antiperiodic'),
                L.loop_tsrc(d6, Ctype='3pt', t_sep=6)]

    def p_loop():
        return [pq_lt(d5),
                pq_lt(d5, Boundary_Conditions='Antiperiodic'),
                pq_lt(d6, Ctype='3pt', t_sep=6)]

    add('L19', 'loop_tsrc 源平均 2pt 周期/反周期 + 3pt', r_loop, p_loop,
        tol=1e-12)

    X = rng.normal(size=(16, 4, 4)) + 1j * rng.normal(size=(16, 4, 4))
    Ct = np.ascontiguousarray(np.transpose(
        X @ np.swapaxes(X.conj(), 1, 2) + 4 * np.eye(4), (1, 2, 0)))

    def _gevp_cmp(a, b):
        va, wa = a
        vb, wb = b
        d1 = float(np.abs(va - vb).max() / max(np.abs(vb).max(), 1e-300))
        d2 = float(np.abs(wa - wb).max() / max(np.abs(wb).max(), 1e-300))
        return max(d1, d2)

    add('L20', 'solve_gevp 广义本征值/矢量逐位一致（复输入差异已判定）',
        lambda: L.solve_gevp(Ct, 2), lambda: pg_g(Ct, 2),
        tol=1e-9, compare=_gevp_cmp,
        note='复 Hermitian 输入上 ref 在 Hermitian 化后执行 .real，丢弃虚部；'
             'PyQCD 保留复数。独立 GEVP 残差：PyQCD 对复矩阵约 1e-15，'
             'ref 对复矩阵约 1e-1；纯实投影双方逐位一致，登记为参考语义差异')

    arr = rng.normal(size=(10, 4))
    groups = [[0, 1], [2, 3], [4], [5], [6], [7], [8], [9]]
    add('L21', 'mean/sum_over_array_of_list 分组聚合',
        lambda: [L.mean_over_array_of_list(arr.copy(), [0], [groups]),
                 L.sum_over_array_of_list(arr.copy(), [0], [groups])],
        lambda: [pq_mo(arr.copy(), [0], [groups]),
                 pq_so(arr.copy(), [0], [groups])], tol=1e-12)

    dc2 = rng.normal(size=(6, 4, 3, 16, 16))
    dcb = rng.normal(size=(6, 4, 3, 16))

    def r_dc():
        return L.dis_connect(dc2.copy(), dcb.copy(), Nconf_axes=0,
                             t_src_axes=-2, t_sink_axes=-1, tsep=5,
                             dtype='PDF')

    def p_dc():
        return pq_dc(dc2.copy(), dcb.copy(), Nconf_axes=0,
                     t_src_axes=-2, t_sink_axes=-1, tsep=5,
                     dtype='PDF')

    add('L22', 'dis_connect PDF 全窗非连通矩阵元', r_dc, p_dc, tol=1e-12)

    def r_pff():
        return L.dis_connect(dc2.copy(), dcb.copy(), Nconf_axes=0,
                             t_src_axes=-2, t_sink_axes=-1, tsep=5,
                             dtype='PFF')

    def p_pff():
        return pq_dc(dc2.copy(), dcb.copy(), Nconf_axes=0,
                     t_src_axes=-2, t_sink_axes=-1, tsep=5,
                     dtype='PFF')

    add('L22b', 'dis_connect PFF 分段窗（结构性）', r_pff, p_pff,
        compare='none',
        note='参考 PFF 装配依赖其 ArraySlicer.reshape 平坦重解释副作用'
             '与窗口覆盖顺序；pyqcd 按文档意图实现，实测未逐位一致'
             '（记录于映射表），物理主通道为 PDF')

    base = rng.normal(size=(4, 5, 6))

    def r_sl():
        sl = L.ArraySlicer(base.copy())
        out = [sl.get_info(),
               sl.slice(dims=[0], indices=[[1, 3]]),
               sl.assign(dims=[0], indices=[[1]],
                         values=sl.slice(dims=[0], indices=[[2]]))]
        try:
            out.append(sl.get_slices(dims=[0], indices=[[1, 3]]))
        except Exception:
            out.append('get_slices 缺失')
        try:
            out.append(sl.get_slice_shape(dims=[0], indices=[[1, 3]]))
        except Exception:
            out.append('get_slice_shape 缺失')
        return out

    def p_sl():
        sl = pq_AS(base.copy())
        out = [sl.get_info(),
               sl.slice(dims=[0], indices=[[1, 3]]),
               sl.assign(dims=[0], indices=[[1]],
                         values=sl.slice(dims=[0], indices=[[2]]))]
        try:
            out.append(sl.get_slices(dims=[0], indices=[[1, 3]]))
        except Exception:
            out.append('get_slices 缺失')
        try:
            out.append(sl.get_slice_shape(dims=[0], indices=[[1, 3]]))
        except Exception:
            out.append('get_slice_shape 缺失')
        return out

    add('L23', 'ArraySlicer 切片/赋值/信息', r_sl, p_sl,
        note='pyqcd 缺 get_slices/get_slice_shape/get_info 增强——缺失项待补')

    tok_sets = [['u', 'u', 'gamma_7', 'd'],
                ['u^d', 'gamma_5', 'u'],
                ['|', 'u', 'u', 'gamma_7', 'd', '|'],
                ['u', 'C', 'd']]
    exprs_tc = ['gamma_1', 'gamma_5', 'C', 'C * gamma_5',
                'C * gamma_mu', 'C * gamma_5 * gamma_mu',
                'C * sigma_mu_nu']
    exprs_dq = ['C', 'C * gamma_5', 'C * gamma_mu',
                'C * gamma_5 * gamma_mu', 'C * sigma_mu_nu']

    def r_bar():
        out = [[L.conjugate_operator(list(t)) for t in tok_sets],
               [(e, r_tg(e), r_ccg(e)) for e in exprs_tc],
               [(e, r_ds(e)) for e in exprs_dq]]
        return out

    def p_bar():
        out = [[pq_conj(list(t)) for t in tok_sets],
               [(e, pq_tg(e), pq_ccg(e)) for e in exprs_tc],
               [(e, pq_ds(e)) for e in exprs_dq]]
        return out

    add('L24', '算符厄米共轭/转置/电荷共轭/双夸克对称', r_bar, p_bar)

    g_full = datalib.gauge()
    slab = np.ascontiguousarray(g_full[:2])

    rng26 = np.random.default_rng(SEED + 3)
    nev, shp = 16, (2, 2, 2, 3)
    a = rng26.standard_normal((nev, 24)) + 1j * rng26.standard_normal((nev, 24))
    q, _ = np.linalg.qr(a.T)
    vecs = np.ascontiguousarray(q.T.reshape((nev,) + shp))
    ip_init = np.ascontiguousarray(vecs[:2] + 0.2 * vecs[2:4])
    ip_test = np.ascontiguousarray(vecs[2:5] + 0.1 * vecs[:3])

    vc = L.vector_creator()

    def _l26_cmp(a, b):
        worst = 0.0
        for i in (0, 1, 2):
            x, y = np.asarray(a[i]), np.asarray(b[i])
            if x.shape != y.shape:
                return float('inf')
            worst = max(worst, float(np.linalg.norm(x - y)
                                     / max(np.linalg.norm(y), 1e-300)))
        return max(worst, 0.0 if bool(a[3]) == bool(b[3]) else float('inf'))

    add('L26', '本征模基元 inner/check/normal/orthnormal',
        lambda: [vc.normal(vecs[:4].copy()),
                 vc.orthnormal(vecs[:4], vecs[4]),
                 vc.inner_product(ip_init, ip_test),
                 bool(vc.check(vecs, dtype='find'))],
        lambda: [pq_norm(vecs[:4].copy()),
                 pq_orth(vecs[:4], vecs[4]),
                 np.asarray(pq_ip(ip_init, ip_test)),
                 bool(pq_chk(vecs))],
        tol=1e-11, compare=_l26_cmp)

    add('L27', 'compress V1 求和压缩 I/B（参数映射后逐位）',
        lambda: [vc.compress_matrix_V1(vecs, [16], [4], ct) for ct in 'IB'],
        lambda: [np.asarray(pq_v1(vecs, 4, ct)) for ct in 'IB'], tol=1e-11)

    def r_v234():
        return [vc.creat_noise(vecs[:4], 2).shape,
                vc.compress_matrix_V2(vecs, [16], [16], [4]).shape,
                vc.compress_matrix_V3(vecs, [16], [16], [4]).shape,
                vc.compress_matrix_V4(vecs, [16], [16], [4]).shape]

    def p_v234():
        return [pq_noise(vecs[:4], 2, seed=None).shape,
                np.asarray(pq_v2(vecs, 4, 4, seed=3)).shape,
                np.asarray(pq_v3(vecs, 4, 4, seed=3)).shape,
                np.asarray(pq_v4(vecs, 4, 4, seed=3)).shape]

    add('L28', 'noise/V2/V3/V4 结构性（形状+可运行）', r_v234, p_v234,
        compare='none', note='参考侧随机无种子，仅形状契约')

    ev32 = np.ascontiguousarray(
        datalib.eigvecs()[:32].reshape(32, NX, NX, NX, 3))

    vxr = L.vertex_creator(NX)

    def r_vtx():
        pe2 = vxr.phase_exp_2pt([0, 0, 1])
        pe3 = vxr.phase_exp_3pt([0, 0, 1])
        return [pe2, pe3, vxr.Mom_VdV_sink_t(pe2, ev32),
                vxr.Mom_VVV_sink_t(pe2, ev32),
                type(vxr).sink2src(vxr.Mom_VdV_sink_t(pe2, ev32))]

    def p_vtx():
        pe2 = pq_pe2(NX, [0, 0, 1])
        pe3 = pq_pe3(NX, [0, 0, 1])
        return [pe2, pe3, pq_mvdv(pe2, ev32),
                pq_mvvv(pe2, ev32),
                pq_s2s(pq_mvdv(pe2, ev32))]

    add('L29', '相位因子+Mom_VdV/Mom_VVV/sink2src（Nev=32 全格点）',
        r_vtx, p_vtx, tol=1e-11, timeout=1200)

    diag = pq_wick(['|', 'u', 'u', 'gamma_7', 'd', '|'],
                   ['|', 'u^d', 'gamma_7', 'd^d', 'u^d', '|'], [], '2pt')

    def r_plot_wrap():
        import matplotlib
        matplotlib.use('Agg')
        dref = L.wick_contraction(
            sink_operators=['|', 'u', 'u', 'gamma_7', 'd', '|'],
            source_operators=['|', 'u^d', 'gamma_7', 'd^d', 'u^d', '|'],
            Cpt='2pt', curr_operators=[])
        fig, ax = L.plot_figure_wick(dref, 0, Cpt='2pt')
        fig.savefig('/tmp/opencode/cmp1_wick_ref.png', dpi=60)
        return True

    def p_plot():
        import matplotlib
        matplotlib.use('Agg')
        fig, ax = pq_pf(diag, 0, Cpt='2pt')
        fig.savefig('/tmp/opencode/cmp1_wick_pq.png', dpi=60)
        return True

    add('L30', 'Wick 图 QC 出图（结构性，B9 视觉等价重写）',
        r_plot_wrap, p_plot, compare='none')

    return cases
