"""对照用例：donghx ↔ pyqcd（首批：γ 表、ASCII IO；数据型用例见后续批次）。"""
import os
import tempfile

import numpy as np

from ..common import datalib
from ..common.harness import Case
from ..common.ref_bridge import load_donghx

SEED = 20260825


def build():
    cases = []
    dh_gamma = load_donghx('gamma_matrix_cupy_DR.py', ['gamma'])
    dh_io = load_donghx('input_output_4_cupy.py', ['write_data_ascii'])

    from pyqcd.lattice._gamma import gamma as pq_gamma
    from pyqcd.tools._io import write_data_ascii as pq_wascii
    from pyqcd.tools._io import read_data_ascii as pq_rascii

    def add(cid, desc, rf, pf, **kw):
        cases.append(Case(cid, 'donghx', desc, rf, pf, **kw))

    def r_dgamma():
        out = []
        for i in range(18):
            g = dh_gamma['gamma'](i)
            out.append(np.asarray(g.get()) if hasattr(g, 'get') else np.asarray(g))
        return out

    def p_dgamma():
        return [np.asarray(pq_gamma(i)) for i in range(18)]

    add('D01', 'DR 基 gamma 表（cupy 版 → numpy 比对）', r_dgamma, p_dgamma,
        tol=1e-12)

    rng = np.random.default_rng(SEED)
    tmpdir = tempfile.mkdtemp(prefix='pyqcd_comparison_donghx_io_')
    f1 = os.path.join(tmpdir, 'dh_ref.dat')
    f2 = os.path.join(tmpdir, 'dh_pq.dat')
    asc = rng.normal(size=(5, 8)) + 1j * rng.normal(size=(5, 8))

    def r_dascii():
        dh_io['write_data_ascii'](asc, T=8, L=24, filename=f1, complex=True)
        return pq_rascii(f1)[0]

    def p_dascii():
        pq_wascii(asc, T=8, L=24, filename=f2, is_complex=True)
        return pq_rascii(f2)[0]

    add('D02', 'donghx ASCII 写 vs pyqcd 写（解析值互比）', r_dascii, p_dascii,
        tol=1e-13, note='%.32f/%.32e 格式微差')

    return cases
