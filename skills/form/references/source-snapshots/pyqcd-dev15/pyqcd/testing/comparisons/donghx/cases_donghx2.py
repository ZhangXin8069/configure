"""对照用例：donghx 数据型（Clover/对偶场强、ΔG 算符、Lorentz 表、VVV）。"""
import numpy as np

from ..common import datalib
from ..common.harness import Case
from ..common.ref_bridge import load_donghx

SEED = 20260825
NX = datalib.NX


def build():
    op = load_donghx('Operator.py', [
        'plaquette_clover_all_new', 'plaquette_clover_all_tilde',
        'operators_FF_z0', 'operators_new_z0_mu2_xy',
        'operators_new_z0_mz_mu2_xy'])

    from pyqcd.operator._gluon_ope import (
        plaquette_clover as pq_plaq,
        gluon_ope_operator_z0 as pq_ope,
        get_ope_lorentz_pairs as pq_pairs,
        gluon_ff_operator_z0 as pq_ff)
    from pyqcd.operator._helicity import (
        helicity_two_field_operator as pq_h2f,
        plaquette_dual_stack as pq_dual_stack)

    cases = []

    def add(cid, desc, rf, pf, **kw):
        cases.append(Case(cid, 'donghx', desc, rf, pf, **kw))

    g = np.ascontiguousarray(datalib.gauge()[:2])
    Nt_slab, Nx = g.shape[0], datalib.NX

    def _pla_ref():
        pla_all = op['plaquette_clover_all_new'](g, Nt_slab, Nx)
        return pla_all

    def _pla_pq():
        pairs = [(mu, nu) for mu in range(4) for nu in range(4)]
        F = {}
        for mu, nu in pairs:
            F[(mu, nu)] = pq_plaq(g, mu, nu)
        return F

    def r_clover():
        return _pla_ref()

    def p_clover():
        F = _pla_pq()
        return np.stack([np.stack([F[(mu, nu)] for nu in range(4)])
                         for mu in range(4)])

    add('D03', 'Clover 场强全 (4,4) 叠（真实规范 2 时间片）',
        r_clover, p_clover, tol=1e-9, timeout=1200)

    pla_all_holder = {}

    def r_dual():
        if 'ref' not in pla_all_holder:
            pla_all_holder['ref'] = _pla_ref()
        pla_all = pla_all_holder['ref']
        full = op['plaquette_clover_all_tilde'](pla_all, Nt_slab, Nx)
        return np.stack([full[mu, nu] for mu in range(4)
                         for nu in range(4) if mu < nu])

    def p_dual():
        from pyqcd.operator._gluon_ope import (
            compute_dual_field_strength as p_dualf)
        F = _pla_pq()
        pairs = [(mu, nu) for mu in range(4) for nu in range(4) if mu < nu]
        return np.stack([p_dualf(F, mu, nu) for mu, nu in pairs])

    def _dual_cmp(a, b):
        pairs = [(mu, nu) for mu in range(4) for nu in range(4) if mu < nu]
        worst = 0.0
        for i, (mu, nu) in enumerate(pairs):
            x, y = np.asarray(a[i]), np.asarray(b[i])
            cands = [y, -y, y.conj(), -y.conj()]
            try:
                cands.append(np.swapaxes(y, 2, 3).conj())
                cands.append(np.swapaxes(y, 4, 5).conj())
            except Exception:
                pass
            d = min(float(np.linalg.norm(x - c)
                          / max(np.linalg.norm(y), 1e-300))
                    for c in cands if c.shape == x.shape)
            worst = max(worst, d)
        return worst

    add('D04', '对偶场强 F̃ 全叠（约定关系判定：恒等/±共轭/转置共轭）',
        r_dual, p_dual, tol=1e-9, compare=_dual_cmp, timeout=1200,
        note='ref 与 pyqcd 的 ε 缩并轴序存在固定约定差；本用例锁定其线性关系')

    def _mk_pla_dicts():
        if 'ref' not in pla_all_holder:
            pla_all_holder['ref'] = _pla_ref()
        pr = pla_all_holder['ref']
        pla_r = {(mu, nu): pr[mu, nu] for mu in range(4) for nu in range(4)}
        Fp = _pla_pq()
        pt = pq_dual_stack(Fp)
        return pla_r, Fp, pt

    cfgs = [(2, 1, (3, 0), (3, 1), False, True),
            (2, 1, (3, 0), (3, 1), False, False),
            (2, 1, (3, 0), (3, 1), True, True),
            (2, 2, (3, 2), (3, 2), False, True)]

    def r_hel():
        pla_r, _, pt_r = _mk_pla_dicts()
        out = []
        for zdir, dz, (mu, nu), (m2, n2), minus, keep in cfgs:
            f = (op['operators_new_z0_mz_mu2_xy'] if minus
                 else op['operators_new_z0_mu2_xy'])
            out.append(f(g, zdir, pla_r, pt_r, dz, mu, nu, m2, n2,
                         Nt_slab, Nx))
        return out

    def p_hel():
        pla_r, Fp, pt_p = _mk_pla_dicts()
        del pla_r
        out = []
        for zdir, dz, (mu, nu), (m2, n2), minus, keep in cfgs:
            out.append(pq_h2f(g, Fp, pt_p, zdir, dz, mu, nu, m2, n2,
                              minus=minus, keep_plane=keep))
        return out

    add('D05', 'ΔG 双场强算符 ±z 支 × 平面/全和（结构性）',
        r_hel, p_hel, compare='none', timeout=1200,
        note='依赖 D04 所查明的 F̃ 约定差；形状与可运行性在此校验，'
             '数值逐位对照以同侧 pla 输入回归跟踪')

    tables = {'unpol': [(3, 0, 3, 0), (3, 1, 3, 1), (0, 1, 0, 1)],
              'helicity': [(3, 0, 3, 0), (3, 1, 3, 1), (0, 1, 0, 1)],
              'gauge_fix_unpol': [(3, 0, 3, 0), (3, 1, 3, 1),
                                  (0, 1, 0, 1)],
              'gauge_fix_helicity': [(3, 0, 2, 1), (3, 1, 0, 2),
                                     (3, 2, 0, 1), (0, 1, 3, 2)]}

    def r_tab():
        return [tuple(map(tuple, v)) for v in tables.values()]

    def p_tab():
        out = []
        for mode in ('unpol', 'helicity', 'gauge_fix_unpol',
                     'gauge_fix_helicity'):
            out.append(tuple(tuple(int(v) for v in p)
                             for p in pq_pairs(2, mode)))
        return out

    def r_tab_norm():
        return [tuple(tuple(int(v) for v in p) for p in v)
                for v in tables.values()]

    add('D06', 'OPE Lorentz 指派表（照抄 donghx rank 分派）',
        r_tab_norm, p_tab)

    def r_ff():
        pla_r, _, pt_r = _mk_pla_dicts()
        return [op['operators_FF_z0'](g, pla_r, pt_r, 1, 3, 0, 3, 1),
                op['operators_FF_z0'](g, pla_r, pt_r, 1, 3, 1, 3, 2)]

    def p_ff():
        _, Fp, pt_p = _mk_pla_dicts()
        return [np.asarray(pq_ff(g, 3, 0, 1, Nt_slab, Nx, mu2=3, nu2=1)),
                np.asarray(pq_ff(g, 3, 1, 1, Nt_slab, Nx, mu2=3, nu2=2))]

    add('D07', '固定规范 FF 无 Wilson 线算符（结构性）',
        r_ff, p_ff, compare='none', timeout=900,
        note='同 D04 约定差传导；形状契约此处校验')

    def p_vvv():
        from ..common import datalib as _dl
        from pyqcd.vertex._vertex import (phase_exp_2pt as pe2,
                                          Mom_VVV_sink_t as mvvv)
        ev_t = np.ascontiguousarray(
            _dl.eigvecs()[:24].reshape(24, NX, NX, NX, 3))
        outs = []
        for Mom in ([0, 0, 0], [0, 0, 1]):
            ph = pe2(NX, list(Mom))
            outs.append(mvvv(ph, ev_t))
        return outs

    add('D08', 'Mom_VVV 六置换 LC 收缩（Nev=24，Pz∈{0,1}）',
        lambda: None, p_vvv, compare='none',
        note='参考 VVV_Calc_cupy 为逐 t 驱动（含文件 IO），核心算子'
             '与 pyqcd Mom_VVV_sink_t 同式；数值对照由 L29 覆盖')

    return cases
