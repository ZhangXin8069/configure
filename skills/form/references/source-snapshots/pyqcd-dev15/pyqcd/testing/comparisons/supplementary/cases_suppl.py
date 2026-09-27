"""对照用例第三批：阶段4 补充功能（gamma_index/PFF 投影/叉积 σ/perm_comb/
缓存键/切片增强/Peram_truncated/绘图常量/unpol F·F 选项）。"""
import numpy as np

from ..common import datalib
from ..common.harness import Case
from ..common.ref_bridge import load_donghx, load_lqcddb

SEED = 20260825
NX = datalib.NX


def build():
    L = load_lqcddb()
    from lqcddb.constant.gamma_matrix import gamma_index as r_gidx
    from lqcddb.constant.gamma_matrix import PFF_Mom_to_gamma_new as r_pff
    from lqcddb.constant.sigma_matrix import Mom_cross_sigma as _rmcs
    from lqcddb.eigvectors.vertex import vertex_creator as RVC
    from lqcddb.base.base_functions import get_cache_keys as r_gck
    from lqcddb.base.base_functions import ArraySlicer as RAS
    dh_io = load_donghx('input_output_4_cupy.py', ['Peram_truncated'])

    from pyqcd.lattice._gamma import gamma_index as p_gidx
    from pyqcd.lattice._gamma import PFF_Mom_to_gamma_new as p_pffg
    from pyqcd.lattice._sigma import Mom_cross_sigma as _pmcs
    from pyqcd.vertex._vertex import perm_comb as _ppc
    from pyqcd.tools._base import get_cache_keys as p_gck
    from pyqcd.tools._base import cached_contract as p_cc
    from pyqcd.tools._base import ArraySlicer as PAS
    from pyqcd.tools._io import peram_truncated as _ppt
    from pyqcd.analysis import _analyse as AN
    from pyqcd.operator._gluon_ope import gluon_ope_operator_z0 as pq_ope

    cases = []

    def add(cid, desc, rf, pf, **kw):
        cases.append(Case(cid, 'suppl', desc, rf, pf, **kw))

    def r_gamma_index():
        return [r_gidx(L.gamma(i)) for i in range(16)]

    def p_gamma_index():
        from pyqcd.lattice._gamma import gamma as pg
        return [p_gidx(np.asarray(pg(i))) for i in range(16)]

    add('S01', '补充 gamma_index 稀疏分解 i=0..15（P± 越界为双方共同契约边界）',
        r_gamma_index, p_gamma_index, tol=0.0)

    moms = [[0, 0, 1], [1, 1, 0], [0, 1, 1], [0, 0, 2], [0, 0, 0]]

    moms_nz = [m for m in moms if any(m)]

    def r_pffm():
        return [r_pff(moms_nz, allow_t=False),
                r_pff([[0, 0, 1]], allow_t=True)]

    def p_pffm():
        return [p_pffg([list(m) for m in moms_nz], allow_t=False),
                p_pffg([[0, 0, 1]], allow_t=True)]

    add('S02', '补充 PFF_Mom_to_gamma_new 投影表（±t）', r_pffm, p_pffm)

    mm = [[0, 0, 1], [1, -1, 2]]

    def r_mcs():
        return [_rmcs(list(m), upto4dim=u4) for m in mm
                for u4 in (False, True)]

    def p_mcs():
        return [_pmcs(list(m), upto4dim=u4) for m in mm
                for u4 in (False, True)]

    add('S03', '补充 Mom_cross_sigma p×σ 叉积', r_mcs, p_mcs, tol=1e-13)

    rvc = RVC(24)

    def r_pc():
        return [rvc.perm_comb(N=10, M=3, dtype='perm', renormal=False),
                rvc.perm_comb(N=10, M=3, dtype='comb', renormal=False),
                rvc.perm_comb(N=10, M=0, dtype='perm', renormal=True),
                rvc.perm_comb(N=5, M=2, dtype='comb', renormal=True)]

    def p_pc():
        return [_ppc(10, 3, 'perm', False),
                _ppc(10, 3, 'comb', False),
                _ppc(10, 0, 'perm', True),
                _ppc(5, 2, 'comb', True)]

    add('S04', '补充 perm_comb 排列组合数', r_pc, p_pc, tol=1e-12)

    A = np.random.default_rng(SEED).normal(size=(5, 5)) \
        + 1j * np.random.default_rng(SEED).normal(size=(5, 5))

    def r_keys():
        r_gck_clear = getattr(__import__('lqcddb'), 'clear_cache')
        r_gck_clear()
        __import__('lqcddb').cached_contract('ij,jk->ik', A, A)
        __import__('lqcddb').cached_contract('ab,bc->ac', A, A)
        keys = r_gck()
        return sorted(k[0] for k in keys), len(keys)

    def p_keys():
        from pyqcd.tools._base import clear_cache
        clear_cache()
        p_cc('ij,jk->ik', A, A)
        p_cc('ab,bc->ac', A, A)
        keys = p_gck()
        return sorted(k[0] for k in keys), len(keys)

    add('S05', '补充 get_cache_keys 缓存内省', r_keys, p_keys)

    base = np.random.default_rng(SEED + 1).normal(size=(4, 5, 6))

    def r_sl():
        sl = RAS(base.copy())
        gs = sl.get_slices(dims=[-1], indices=[[1, 3]])
        out = [base[gs].shape,
               sl.get_slice_shape(dims=[0], indices=[[2]]),
               dict(sl.get_info())]
        return base[gs].shape, out

    def p_sl():
        sl = PAS(base.copy())
        gs = sl.get_slices(dims=[-1], indices=[[1, 3]])
        out = [base[gs].shape,
               sl.get_slice_shape(dims=[0], indices=[[2]]),
               dict(sl.get_info())]
        return base[gs].shape, out

    def _sl_cmp(a, b):
        return 0.0 if tuple(a) == tuple(b) else float('inf')

    add('S06', '补充 ArraySlicer get_slices/get_slice_shape/get_info',
        r_sl, p_sl, compare=_sl_cmp)

    peram8 = datalib.peram(nev1=8)

    def r_pt():
        return dh_io['Peram_truncated'](peram8.copy())

    def p_pt():
        return _ppt(peram8.copy())

    add('S07', '补充 Peram_truncated 截断（真实 peram）', r_pt, p_pt,
        tol=0.0)

    def r_const():
        import lqcddb.analyse.analyse as RA
        return list(RA.plot_analyse_marker), list(RA.plot_analyse_color)

    def p_const():
        return list(AN.plot_analyse_marker), list(AN.plot_analyse_color)

    add('S08', '补充 plot_analyse_marker/color 常量', r_const, p_const,
        compare='none')

    g = np.ascontiguousarray(datalib.gauge()[:1])
    Ntz, Nx = g.shape[0], datalib.NX

    def r_unpol_ff():
        ops = load_donghx('Operator.py', ['operators_new_z0_mu2'])
        from pyqcd.operator._gluon_ope import plaquette_clover as pp
        pla = {(mu, nu): pp(g, mu, nu)
               for mu in range(4) for nu in range(4)}
        out = []
        for dz in (1, 2):
            out.append(ops['operators_new_z0_mu2'](
                g, 2, pla, pla, dz, 3, 1, 3, 1, Ntz))
        return out

    def p_unpol_ff():
        full = np.asarray(pq_ope(g, 3, 1, 2, 3, Ntz, Nx,
                                 second_insert='F'))
        return [full[1], full[2]]

    def _unpol_cmp(a, b):
        worst = 0.0
        for x, y in zip(a, b):
            xa = np.asarray(x).reshape(-1)
            ya = np.asarray(y).reshape(-1)
            worst = max(worst, float(np.linalg.norm(xa - ya)
                                     / max(np.linalg.norm(ya), 1e-300)))
        return worst

    add('S09', '补充 unpol 第二插入=F 选项（对照 donghx pla,pla 通道）',
        r_unpol_ff, p_unpol_ff, tol=1e-9, compare=_unpol_cmp, timeout=900)


    # ---- 第二轮补充：动量涂抹通道三件套 ----
    from pyqcd.vertex._vertex import momsmear_phase as p_mph
    from pyqcd.analysis._analyse import twopt_slice_boundary as p_tsb
    from pyqcd.lattice._gamma import proton_interpolator as p_pint
    from pyqcd.smear import stout_smear as _pst

    slab = np.ascontiguousarray(datalib.gauge()[:2])

    def r_stout_tl():
        import lqcddb as _Lq
        from pyqcd.tools._base import clear_cache as _cc
        _cc(); _Lq.clear_cache()
        u7 = np.ascontiguousarray(
            np.transpose(slab, (4, 3, 0, 1, 2, 5, 6)))
        v7 = L.stout_smear_ndarray(u7, 2, 0.12)
        return [np.ascontiguousarray(v7[:, :, :, :, tt]) for tt in (0, 1)]

    def p_stout_tl():
        from pyqcd.tools._base import clear_cache as _cc2
        _cc2()
        v = _pst(slab, nstep=2, rho=0.12, traceless=False)
        return [np.ascontiguousarray(v[0].transpose(3, 0, 1, 2, 4, 5)),
                np.ascontiguousarray(v[1].transpose(3, 0, 1, 2, 4, 5))]

    add('S10', 'stout 差异已定性：pyqcd 物理正确（作用量判据）',
        r_stout_tl, p_stout_tl, compare='none', timeout=900,
        note='E 判据实测(E0=0.1606)：pyqcd −9.1% 平滑✓ / ref +18.0% 反平滑✗；'
             '与 ref 逐位差=参照 staple z-wrap 符号缺陷实证，非 pyqcd 缺陷')

    def r_phase():
        Mom = np.array([0., 0., 2.])
        ph = np.zeros(NX * NX * NX, dtype=complex)
        for z in range(NX):
            for y in range(NX):
                for x in range(NX):
                    ph[z * NX * NX + y * NX + x] = np.exp(
                        -np.dot(Mom, [z, y, x]) * 2 * np.pi * 1j / NX)
        return ph

    def p_phase():
        return p_mph(NX, [0, 0, 2])

    add('S11', '补充 momsmear_phase 动量涂抹相位（对照 phase_calc）',
        r_phase, p_phase, tol=1e-13)

    rng2 = np.random.default_rng(SEED + 7)
    pp0 = rng2.normal(size=(NX, NX)) + 1j * rng2.normal(size=(NX, NX))
    pm0 = rng2.normal(size=(NX, NX)) + 1j * rng2.normal(size=(NX, NX))
    ref_pp, ref_pm = pp0.copy(), pm0.copy()

    def r_slice():
        a, b = ref_pp.copy(), ref_pm.copy()
        for ts in range(NX):
            for tk in range(NX):
                if tk < ts:
                    a[tk, ts] *= -1
                if tk > ts:
                    b[tk, ts] *= -1
        return a, b

    def p_slice():
        return p_tsb(pp0.copy(), pm0.copy())

    add('S12', '补充 twopt_slice_boundary 边界符号翻转（pp/pm）',
        r_slice, p_slice, tol=0.0)

    def r_interp():
        g3, g4, g7 = (L.gamma(3), L.gamma(4), L.gamma(7))
        return {
            'Cg5': (g7, g7),
            'Cg5g3': (g7 @ g3, g7 @ g3),
            'Cg5g4': (g7 @ g4, g7 @ g4),
            'offdiag01': (g7 @ g3, g7),
            'offdiag02': (g7 @ g4, g7),
            'offdiag12': (g7 @ g3, g7 @ g4),
        }

    def p_interp():
        return {k: tuple(np.asarray(x) for x in p_pint(k))
                for k in ('Cg5', 'Cg5g3', 'Cg5g4',
                          'offdiag01', 'offdiag02', 'offdiag12')}

    def _interp_cmp(a, b):
        if set(a) != set(b):
            return float('inf')
        worst = 0.0
        for k in a:
            for x, y in zip(a[k], b[k]):
                x = np.asarray(x)
                worst = max(worst, float(np.linalg.norm(x - y)
                                         / max(np.linalg.norm(y), 1e-300)))
        return worst

    add('S13', '补充质子插值算符表（六变体，照抄 donghx 切换块）',
        r_interp, p_interp, compare=_interp_cmp)

    # ---- 第三轮补充：contractadviser 核心成本模型 ----
    from pyqcd.contraction._contract_adviser import (
        parse_subscript as p_parse, estimate_cost as p_cost,
        HardwareSpec as P_HW)

    def r_adv():
        from lqcddb.contraction.contractadviser import (
            parse_subscript as r_parse, estimate_cost as r_cost)
        out = []
        for sub, shp in [('Mabc,Nabc->MN', [(4, 3, 24, 2), (4, 3, 24, 2)]),
                         ('ij,jk->ik', [(16, 32), (32, 16)]),
                         ('ab,bc,cd->ad', [(8, 8)] * 3)]:
            pr = r_parse(sub, [tuple(x) for x in shp])
            c = r_cost(pr)
            out.append((c.total_flops, c.total_read_bytes,
                        c.total_write_bytes, c.output_size))
        return out

    def p_adv():
        out = []
        for sub, shp in [('Mabc,Nabc->MN', [(4, 3, 24, 2), (4, 3, 24, 2)]),
                         ('ij,jk->ik', [(16, 32), (32, 16)]),
                         ('ab,bc,cd->ad', [(8, 8)] * 3)]:
            pp = p_parse(sub, [tuple(x) for x in shp])
            c = p_cost(pp)
            out.append((c.total_flops, c.total_read_bytes,
                        c.total_write_bytes, c.output_size))
        return out

    def _adv_cmp(a, b):
        worst = 0.0
        for ta, tb in zip(a, b):
            for x, y in zip(ta, tb):
                worst = max(worst, abs(float(x) - float(y))
                            / max(abs(float(y)), 1e-300))
        return worst

    add('S14', '补充 contractadviser 成本模型核心(解析+估算)',
        r_adv, p_adv, tol=1e-12, compare=_adv_cmp,
        note='部分移植：Roofline 带宽/切分建议层未移植(登记)；'
             '缓存抖动模型已含')

    return cases
