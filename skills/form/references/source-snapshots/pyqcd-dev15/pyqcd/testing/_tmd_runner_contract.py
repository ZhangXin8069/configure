"""TMD 管线编排的性能与元数据回归测试。"""
from __future__ import annotations

import json
import tempfile
from unittest.mock import Mock, patch

import numpy as np


def test_step_tmd_reuses_one_flowed_gauge(tmp_path=None):
    """一次 step_tmd 只能执行一次 Wilson flow，并复用同一流场。"""
    import tempfile

    from pyqcd.pipeline._runner import step_tmd

    gauge = np.zeros((1, 1, 1, 1, 4, 3, 3), dtype=np.complex128)
    gauge[..., :, :, :] = np.eye(3, dtype=np.complex128)
    flowed = gauge.copy()
    flowed[..., 0, 0, 0] = 2.0
    expected = np.array([[8.0]], dtype=np.float64)

    flow = Mock(return_value=flowed)
    def encode_staple_length(_flowed, _z_list, _b_list, **kwargs):
        factor = 2.0 if kwargs['color_normalization'] == 'adjoint' else 1.0
        return np.array([[factor * float(kwargs['L'])]], dtype=np.float64)

    matrix_elements = Mock(side_effect=encode_staple_length)
    action_density = Mock(return_value=np.ones(gauge.shape[:4]))

    def run(run_dir):
        with patch("pyqcd.renorm._gradient_flow.wilson_flow", flow), \
                patch("pyqcd.renorm._tmd.wilson_flow", flow), \
                patch("pyqcd.renorm._tmd.tmd_matrix_elements",
                      matrix_elements), \
                patch("pyqcd.renorm._gradient_flow.flow_action_density",
                      action_density):
            actual = step_tmd(
                {}, run_dir, gauge, tau=3.0, z_list=[0], b_list=[0],
                z_dir=2, eps=0.05, staple_length=4,
                color_normalization='adjoint')
        with open(f"{run_dir}/tmd_gluon_flow.json", encoding="utf-8") as handle:
            payload = json.load(handle)
        return actual, payload

    if tmp_path is None:
        with tempfile.TemporaryDirectory() as run_dir:
            actual, payload = run(run_dir)
    else:
        actual, payload = run(str(tmp_path))

    assert flow.call_count == 1, \
        f"同一管线步骤重复执行 Wilson flow: {flow.call_count} 次"
    assert matrix_elements.call_count == 1
    assert matrix_elements.call_args.args[0] is flowed
    assert action_density.call_count == 1
    assert action_density.call_args.args[0] is flowed
    assert np.array_equal(actual, expected)
    assert payload["tau"] == 3.0
    assert payload["tau_convention"] == "t/a^2"
    assert payload["t2E"] == 9.0
    assert payload["staple_length"] == 4
    assert payload["color_normalization"] == 'adjoint'


def test_tmd_ope_cache_distinguishes_fixed_staple_length():
    """改变 staple 臂长必须计算独立产物，不能命中旧 regulator 缓存。"""
    from pyqcd.pipeline import _tmd9
    from pyqcd.tools import set_backend

    set_backend('numpy')
    gauge = np.broadcast_to(
        np.eye(3, dtype=np.complex128),
        (1, 1, 1, 1, 4, 3, 3),
    ).copy()

    def encode_contract(_gauge, z_list, b_list, z_dir=2, b_dir=0, L=None,
                        color_normalization='fundamental_trace'):
        marker = 1.0 if color_normalization == 'fundamental_trace' else 2.0
        return np.full(
            (len(z_list), len(b_list), _gauge.shape[0]),
            10.0 * float(L) + marker,
        )

    with tempfile.TemporaryDirectory() as run_dir, \
            patch.object(_tmd9, 'flow_gauge_for_config',
                         return_value=gauge), \
            patch.object(_tmd9, 'tmd_matrix_elements_time',
                         side_effect=encode_contract):
        first = _tmd9.compute_tmd_ope_time(
            7, run_dir, None, [0, 1], [0], precision='complex128',
            staple_length=1)
        second = _tmd9.compute_tmd_ope_time(
            7, run_dir, None, [0, 1], [0], precision='complex128',
            staple_length=2)
        adjoint = _tmd9.compute_tmd_ope_time(
            7, run_dir, None, [0, 1], [0], precision='complex128',
            staple_length=1, color_normalization='adjoint')

    np.testing.assert_array_equal(first['tmd'], np.full((2, 1, 1), 11.0))
    np.testing.assert_array_equal(second['tmd'], np.full((2, 1, 1), 21.0))
    np.testing.assert_array_equal(adjoint['tmd'], np.full((2, 1, 1), 12.0))
