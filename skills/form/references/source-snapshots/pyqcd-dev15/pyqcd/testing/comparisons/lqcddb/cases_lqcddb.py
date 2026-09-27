"""对照用例：lqcddb ↔ pyqcd（纯函数/统计/IO；数据型用例见后续批次）。"""
import os
import tempfile

import numpy as np

from ..common import datalib
from ..common.harness import Case
from ..common.ref_bridge import load_lqcddb

SEED = 20260825


def _rng():
    return np.random.default_rng(SEED)


def build():
    L = load_lqcddb()
    from lqcddb.io.write_date import check_files_existence as ref_cfe
    from lqcddb.io.write_date import readin_eigvecs as ref_reig
    from pyqcd.lattice._gamma import gamma as pq_gamma
    from pyqcd.lattice._sigma import sigma as pq_sigma
    from pyqcd.lattice._sigma import Mom_times_sigma as pq_mom_sigma
    from pyqcd.tools._base import levi_civita_tensor as pq_lc
    from pyqcd.tools._base import creat_mom_list as pq_moms
    from pyqcd.tools._base import cached_contract as pq_cc
    from pyqcd.tools._base import clear_cache as pq_clear
    from pyqcd.contraction._autowick import wick_contraction as pq_wick
    from pyqcd.contraction._autowick import identify_equivalent_diagrams as pq_ident
    from pyqcd.contraction._seqperam import seq_peram as pq_seqperam
    from pyqcd.analysis._analyse import Jackknife as pq_jk
    from pyqcd.analysis._analyse import meff as pq_meff
    from pyqcd.analysis._analyse import Mom2GeV as pq_m2g
    from pyqcd.tools._io import write_data_ascii as pq_wascii
    from pyqcd.tools._io import read_data_ascii as pq_rascii
    from pyqcd.pipeline._validate import check_files_existence as pq_cfe
    from pyqcd.tools._io import safe_save as pq_ssave
    from pyqcd.tools._io import readin_eigvecs as pq_reig

    cases = []

    def add(cid, desc, rf, pf, **kw):
        cases.append(Case(cid, 'lqcddb', desc, rf, pf, **kw))

    add('L01', 'DR 基 gamma 表 i=0..17',
        lambda: [np.asarray(L.gamma(i)) for i in range(18)],
        lambda: [np.asarray(pq_gamma(i)) for i in range(18)], tol=1e-12)

    moms = [[0, 0, 0], [0, 0, 1], [1, -1, 2], [2, 3, 4]]

    def r_sigma():
        out = [L.sigma(i) for i in range(4)]
        for m in moms:
            for u4 in (False, True):
                out.append(L.Mom_times_sigma(list(m), upto4dim=u4))
        return out

    def p_sigma():
        out = [pq_sigma(i) for i in range(4)]
        for m in moms:
            for u4 in (False, True):
                out.append(pq_mom_sigma(list(m), upto4dim=u4))
        return out

    add('L02', 'Pauli sigma 与归一化 p.sigma', r_sigma, p_sigma, tol=1e-12)

    add('L03', 'Levi-Civita 张量 n=3',
        lambda: np.asarray(L.levi_civita_tensor(3)),
        lambda: np.asarray(pq_lc(3)), tol=1e-14)

    def r_moms():
        return [L.creat_mom_list([0, 0, 1]),
                L.creat_mom_list([1, 1, -2]),
                L.creat_mom_list([0, 0, 1], fix_Q2=True),
                L.creat_mom_list([1, 1, -2], fix_Q2=True),
                L.creat_mom_list([[0, 0, 1], [1, 1, 0]]),
                L.creat_mom_list(np.array([0, 2, 2])),
                L.creat_mom_list([0, 0, 2], only_g0=True)]

    def p_moms():
        return [pq_moms([0, 0, 1]),
                pq_moms([1, 1, -2]),
                pq_moms([0, 0, 1], fix_Q2=True),
                pq_moms([1, 1, -2], fix_Q2=True),
                pq_moms([[0, 0, 1], [1, 1, 0]]),
                pq_moms(np.array([0, 2, 2])),
                pq_moms([0, 0, 2], only_g0=True)]

    add('L04', '动量壳列表生成（立方壳+fix_Q2+only_g0 全语义）',
        r_moms, p_moms, tol=0.0,
        note='原 pyqcd 缺立方壳/only_g0，已按参照修复对齐')

    A = _rng().normal(size=(6, 6)) + 1j * _rng().normal(size=(6, 6))
    B = _rng().normal(size=(6, 8)) + 1j * _rng().normal(size=(6, 8))

    def r_contract():
        L.clear_cache()
        return [L.cached_contract('ij,jk->ik', A, B),
                L.cached_contract('ab,bc,cd->ad', A, A, A),
                L.cached_contract('ij,jk->k', A, B)]

    def p_contract():
        pq_clear()
        return [pq_cc('ij,jk->ik', A, B),
                pq_cc('ab,bc,cd->ad', A, A, A),
                pq_cc('ij,jk->k', A, B)]

    add('L05', 'cached_contract 缓存收缩 x3 + clear_cache',
        r_contract, p_contract, tol=1e-13)

    SINK = ['|', 'u', 'u', 'gamma_7', 'd', '|']
    SRC = ['|', 'u^d', 'gamma_7', 'd^d', 'u^d', '|']

    add('L06', 'Wick 收缩 质子 2pt 单图',
        lambda: L.wick_contraction(sink_operators=list(SINK),
                                   source_operators=list(SRC),
                                   Cpt='2pt', curr_operators=[]),
        lambda: pq_wick(list(SINK), list(SRC), [], '2pt'), tol=0.0)

    D_SINK2 = ['|', 'd', 'u', 'gamma_7', 'd', '|',
               '|', 'd^d', 'gamma_5', 'u', '|']
    D_SRC2 = ['|', 'u^d', 'gamma_7', 'd^d', 'd^d', '|',
              '|', 'u^d', 'gamma_5', 'd', '|']

    def r_ident():
        d1 = L.wick_contraction(sink_operators=list(SINK),
                                source_operators=list(SRC), Cpt='2pt',
                                curr_operators=[])
        d2 = L.wick_contraction(sink_operators=['|', 'u', 'u', 'gamma_7', 'd', '|'],
                                source_operators=['|', 'u^d', 'gamma_7', 'd^d', 'u^d', '|',
                                                  '|', 'u^d', 'gamma_5', 'u', '|'],
                                Cpt='2pt', curr_operators=[])
        d8 = L.wick_contraction(sink_operators=list(D_SINK2),
                                source_operators=list(D_SRC2), Cpt='2pt',
                                curr_operators=[])
        groups = L.identify_equivalent_diagrams(d1, d2, d8)
        return [sorted(g) for g in groups]

    def p_ident():
        d1 = pq_wick(list(SINK), list(SRC), [], '2pt')
        d2 = pq_wick(['|', 'u', 'u', 'gamma_7', 'd', '|'],
                     ['|', 'u^d', 'gamma_7', 'd^d', 'u^d', '|',
                      '|', 'u^d', 'gamma_5', 'u', '|'], [], '2pt')
        d8 = pq_wick(list(D_SINK2), list(D_SRC2), [], '2pt')
        groups = pq_ident(d1, d2, d8)
        return [sorted(g) for g in groups]

    add('L07', '等价图识别 identify_equivalent_diagrams', r_ident, p_ident)

    peram8 = datalib.peram(nev1=8)
    add('L08', '顺序传播子 seq_peram（真实 peram Nev1=8）',
        lambda: L.seq_peram(peram8), lambda: pq_seqperam(peram8), tol=1e-12)

    data = _rng().normal(size=(10, 48))
    add('L09', 'Jackknife 样本+协方差',
        lambda: L.Jackknife(data), lambda: pq_jk(data), tol=1e-12)

    t = np.arange(48)
    clean = 1.0 * np.exp(-0.25 * t) + 0.4 * np.exp(-0.55 * t)
    c2 = clean[None, :] + 0.01 * _rng().normal(size=(10, 48))
    jk_sample = np.asarray(L.Jackknife(c2)['data_sample'])

    def _meff_cmp(a, b):
        worst = 0.0
        for da, db in zip(a, b):
            for k in da:
                x = np.asarray(da[k], dtype=float)
                y = np.asarray(db[k], dtype=float)
                if np.any(np.isnan(y) & ~np.isnan(x)):
                    return float('inf')
                m = ~(np.isnan(x) | np.isnan(y))
                if not m.any():
                    continue
                denom = max(np.linalg.norm(y[m]), 1e-300)
                worst = max(worst, float(np.linalg.norm(x[m] - y[m]) / denom))
        return worst

    def r_meff():
        return [L.meff(jk_sample, 1.0, meff_type='log'),
                L.meff(jk_sample, 1.0, meff_type='cosh')]

    def p_meff():
        return [pq_meff(jk_sample, 1.0, meff_type='log'),
                pq_meff(jk_sample, 1.0, meff_type='cosh')]

    add('L10', '有效质量 meff log+cosh（合成谱）', r_meff, p_meff,
        tol=5e-3, compare=_meff_cmp,
        note='fm2GeV 常数比例 0.998343；cosh 支路 pyqcd 有意加 arccosh 定义域 clamp（仅填边界 NaN）')

    def r_m2g():
        return [L.Mom2GeV(24, 0.1053, [[0, 0, 1], [0, 0, 2]], [0.94]),
                L.Mom2GeV(24, 0.1053, [0, 1, 1], 0.94)]

    def p_m2g():
        return [pq_m2g(24, 0.1053, [[0, 0, 1], [0, 0, 2]], [0.94]),
                pq_m2g(24, 0.1053, [0, 1, 1], 0.94)]

    add('L11', '色散能量 Mom2GeV', r_m2g, p_m2g, tol=3e-3,
        note='fm2GeV 有意差异: pyqcd 用精确 ħc=0.197327, lqcddb 截断 0.197')

    tmpdir = tempfile.mkdtemp(prefix='pyqcd_comparison_ascii_')
    f1 = os.path.join(tmpdir, 'ref.dat')
    f2 = os.path.join(tmpdir, 'pyqcd.dat')
    asc = _rng().normal(size=(5, 8)) + 1j * _rng().normal(size=(5, 8))

    def r_ascii():
        L.write_data_ascii(asc, T=8, L=24, filename=f1, complex=True)
        return pq_rascii(f1)[0]

    def p_ascii():
        pq_wascii(asc, T=8, L=24, filename=f2, is_complex=True)
        return pq_rascii(f2)[0]

    add('L12', 'L.Liu ASCII 写读往返（双方文件互读）', r_ascii, p_ascii,
        tol=1e-13, note='%.32e/%.32f 格式微差，按解析值比对')

    tpl = datalib.EIG_ROOT + '/{conf_id}/eigvecs_t000_{conf_id}'
    conf_ids = [6250, 6450, 999999]

    def r_cfe():
        ex, mi = ref_cfe([tpl], conf_id=conf_ids)
        return sorted(map(str, ex)), sorted(map(str, mi))

    def p_cfe():
        ex, mi = pq_cfe([tpl], conf_id=conf_ids)
        return sorted(map(str, ex)), sorted(map(str, mi))

    add('L13', '模板文件守卫 check_files_existence（真实目录+缺失项）',
        r_cfe, p_cfe)

    arr_s = _rng().normal(size=(4, 5)) + 1j * _rng().normal(size=(4, 5))
    s1 = os.path.join(tmpdir, 'ref_safe.npy')
    s2 = os.path.join(tmpdir, 'pq_safe.npy')

    def r_ssave():
        L.safe_save(s1, arr_s, fallback_dirs=[tmpdir])
        return np.load(s1)

    def p_ssave():
        pq_ssave(s2, arr_s, fallback_dirs=[tmpdir])
        return np.load(s2)

    add('L14', 'safe_save 保存+回退', r_ssave, p_ssave, tol=0.0)

    eigpath = os.path.join(datalib.EIG_ROOT, str(datalib.CONF),
                           f'eigvecs_t000_{datalib.CONF}')
    add('L15', 'readin_eigvecs 二进制读取（真实文件）',
        lambda: ref_reig(eigpath, 24),
        lambda: pq_reig(eigpath, 24), tol=0.0)

    return cases
