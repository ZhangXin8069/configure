"""管线：蒸馏计算 + 胶子 OPE + 统计分析 + 梯度流重整化 TMD 的 9 步调度。

编排实现见 ``_steps.py``（照抄冻结蒸馏基线逻辑、
自包含调用 pyqcd 子包）；本模块提供向后兼容的调度入口：

    1. env     环境检查
    2. vertex  顶点函数（VdV/VVV）
    3. 2pt     2pt 关联函数（pp/pn/pion）
    4. ope     胶子 OPE 算符（Clover F̃ + Wilson 线）
    5. 3pt     PJN 3pt
    6. 4pt     PJNNJNp 4pt
    7. analysis Jackknife/meff/ratio
    8. plots   绘图
    9. report  LaTeX 报告
    10. tmd    梯度流重整化胶子 TMD-PDF（本库核心目标，新增）
"""
from __future__ import annotations

import json
import os

from . import _config as _pipeline_config
from ._config import (
    CONF_IDS, NEV, NEV1, PRECISION, NT, NX, ALttc, FM2GEV, T_SEP,
    DELTA_Z, Z_DIR, OPE_COMPONENTS, LOGS_DIR, PLOTS_DIR,
    get_gauge_path,
)
from ._steps import run_pipeline as _run_pipeline_full
from ._run_dir import reserve_unique_run_dir


def make_run_dir(tag: str = None) -> str:
    """原子创建本轮唯一输出目录并初始化标准子目录。"""
    run_dir = reserve_unique_run_dir(_pipeline_config.OUTPUT_DIR, tag=tag)
    os.makedirs(os.path.join(run_dir, 'data'), exist_ok=True)
    os.makedirs(os.path.join(run_dir, 'plots'), exist_ok=True)
    os.makedirs(os.path.join(run_dir, 'analysis'), exist_ok=True)
    return run_dir


def step_env(conf_ids=CONF_IDS):
    """环境检查：GPU/数据路径。返回环境信息 dict。"""
    info = {
        'conf_ids': conf_ids,
        'precision': PRECISION,
        'nx': NX, 'nt': NT,
        'gauge_dir': os.path.dirname(get_gauge_path(conf_ids[0])),
    }
    try:
        import cupy  # noqa: F401
        info['gpu'] = 'cupy'
    except ImportError:
        info['gpu'] = 'numpy'
    return info


def step_tmd(config, run_dir, gauge, tau, z_list, b_list,
             z_dir=Z_DIR, eps=0.01, staple_length=None,
             color_normalization='fundamental_trace'):
    """梯度流重整化胶子 TMD-PDF 矩阵元（核心目标）。"""
    from ..renorm._gradient_flow import flow_action_density, wilson_flow
    from ..renorm._tmd import tmd_matrix_elements
    from ._tmd9 import _resolve_staple_length

    # Wilson flow 是本步骤的主导成本；同一流场同时供 TMD 与 t²E 使用。
    staple_length = _resolve_staple_length(z_list, staple_length)
    V = wilson_flow(gauge, tau, eps=eps)
    out = tmd_matrix_elements(
        V, z_list, b_list, z_dir=z_dir, b_dir=0, L=staple_length,
        color_normalization=color_normalization)
    t2E = tau ** 2 * flow_action_density(V).mean()
    result = {
        'O_z_b': out.tolist(),
        'tau': tau,
        'tau_convention': 't/a^2',
        'flow_eps': eps,
        't2E': float(t2E),
        'z_list': z_list,
        'b_list': b_list,
        'staple_length': staple_length,
        'color_normalization': color_normalization,
    }
    with open(os.path.join(run_dir, 'tmd_gluon_flow.json'), 'w') as f:
        json.dump(result, f, indent=2)
    return out


def run_pipeline(steps=('env', 'vertex', '2pt', 'ope', '3pt', '4pt',
                        'analysis', 'plots', 'report'),
                 conf_ids=None, run_dir=None, logger=print, **kw):
    """9 步（+tmd）管线调度，委托 _steps.run_pipeline 完整实现。

    与冻结蒸馏基线 run_pipeline.py 输出结构一致；
    计算全部调用 pyqcd 子包（自包含）。返回 dict:
    {'run_dir', 'timing', 'summary', 'meff', 'ratio_conn'}。
    """
    conf_ids = conf_ids or CONF_IDS
    return _run_pipeline_full(steps=steps, conf_ids=conf_ids,
                              run_dir=run_dir, logger=logger, **kw)
