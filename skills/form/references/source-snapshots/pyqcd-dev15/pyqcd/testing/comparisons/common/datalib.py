"""真实数据加载助手：eigvecs/perambulators/gauge（进程内 memo + 磁盘缓存）。"""
import os

import numpy as np

CACHE = '/tmp/opencode/cmp1_cache'
CONF = 6250
EIG_ROOT = ('/public/group/lqcd/eigensystem/'
            'beta6.20_mu-0.2770_ms-0.2400_L24x72')
PERAM_ROOT = ('/public/group/lqcd/perambulators/'
              'beta6.20_mu-0.2770_ms-0.2400_L24x72/light')
GAUGE_DIR = ('/public/group/lqcd/configurations/CLOVER/'
             'beta6.20_mu-0.2770_ms-0.2400_L24x72')
NX, NT = 24, 72

_memo = {}


def configure(conf=CONF, cache_dir=CACHE):
    """Select a configuration for a comparison run and clear stale arrays."""
    global CONF, CACHE
    CONF = int(conf)
    CACHE = str(cache_dir)
    _memo.clear()


def eigvecs(conf=CONF, t=0):
    key = ('eig', conf, t)
    if key not in _memo:
        from pyqcd.tools import readin_eigvecs
        path = os.path.join(EIG_ROOT, str(conf), f'eigvecs_t{t:03d}_{conf}')
        _memo[key] = readin_eigvecs(path, NX)
    return _memo[key]


def peram(conf=CONF, nev1=8):
    key = ('peram', conf, nev1)
    if key not in _memo:
        from pyqcd.tools import readin_peram
        _memo[key] = readin_peram(os.path.join(PERAM_ROOT, str(conf)),
                                  str(conf), NT, nev1)
    return _memo[key]


def gauge(conf=CONF):
    key = ('gauge', conf)
    if key not in _memo:
        p = os.path.join(CACHE, f'gauge_{conf}.npy')
        if os.path.exists(p):
            _memo[key] = np.load(p)
        else:
            from pyqcd.operator._gluon_ope import read_gauge_lime
            lime = os.path.join(
                GAUGE_DIR,
                f'beta6.20_mu-0.2770_ms-0.2400_L24x72_cfg_{conf}.lime')
            g = read_gauge_lime(lime, NT, NX)
            os.makedirs(CACHE, exist_ok=True)
            np.save(p, g)
            _memo[key] = g
    return _memo[key]
