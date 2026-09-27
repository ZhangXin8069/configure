"""Wilson-flow 能量密度归一化的独立弱场 oracle。"""
from __future__ import annotations

import unittest

import numpy as np


def _uniform_abelian_xy_field(generator_diag, flux_angle, length=8):
    """构造周期 Abelian SU(3) 场，使每个 (0,1) plaquette 为 exp(i phi T)。

    链接取

        U_0(y, x) = exp(-i phi y T),
        U_1(L-1, x) = exp(i phi L x T),

    其余链接为单位阵。测试中的 ``flux_angle`` 分别满足 T3/T8 的周期
    量子化条件，因此边界 plaquette 与内部 plaquette 完全相同。
    """
    generator_diag = np.asarray(generator_diag, dtype=np.float64)
    gauge = np.empty((1, 1, length, length, 4, 3, 3),
                     dtype=np.complex128)
    gauge[...] = np.eye(3, dtype=np.complex128)

    for y in range(length):
        gauge[0, 0, y, :, 0] = np.diag(
            np.exp(-1j * flux_angle * y * generator_diag))
    for x in range(length):
        gauge[0, 0, length - 1, x, 1] = np.diag(
            np.exp(1j * flux_angle * length * x * generator_diag))
    return gauge


def _assert_single_uniform_clover_component(test_case, gauge, expected_diag):
    """验证测试夹具确实给出唯一且均匀的解析 Clover 分量。"""
    from pyqcd.operator._gluon_ope import plaquette_clover

    expected = np.broadcast_to(np.diag(expected_diag), gauge.shape[:4] + (3, 3))
    actual = np.asarray(plaquette_clover(gauge, 0, 1))
    np.testing.assert_allclose(actual, expected, rtol=2e-13, atol=2e-13)

    for mu in range(4):
        for nu in range(mu + 1, 4):
            if (mu, nu) == (0, 1):
                continue
            other = np.asarray(plaquette_clover(gauge, mu, nu))
            test_case.assertLess(float(np.max(np.abs(other))), 2e-13)


class FlowActionDensityNormalizationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pyqcd.tools import set_backend

        set_backend("numpy")

    def test_single_t3_component_has_standard_half_f_squared_energy(self):
        """mu<nu 仅有 F=f*T3 时，E 必须为 f^2/2，不能再乘 1/4。"""
        from pyqcd.renorm import flow_action_density

        length = 8
        t3_diag = np.array([0.5, -0.5, 0.0])
        phi = 4.0 * np.pi / length**2
        gauge = _uniform_abelian_xy_field(t3_diag, phi, length)

        # 四叶定义 -i/8 sum(P-P^dagger) 对该场精确给出
        # F_01 = sin(phi*T3) = f*T3，f = 2 sin(phi/2)。
        f = 2.0 * np.sin(phi / 2.0)
        expected_field_diag = f * t3_diag
        _assert_single_uniform_clover_component(
            self, gauge, expected_field_diag)

        # 独立连续规范：E=1/4 sum_{mu,nu,a} F^a_munu F^a_munu=f^2/2。
        expected_energy = 0.5 * f**2
        actual = np.asarray(flow_action_density(gauge))
        np.testing.assert_allclose(
            actual, expected_energy, rtol=5e-13, atol=5e-14)

    def test_finite_a_clover_trace_is_excluded_from_su3_energy(self):
        """有限-a Clover 的单位阵分量不得混入 SU(3) 能量密度。"""
        from pyqcd.renorm import flow_action_density

        length = 8
        sqrt3 = np.sqrt(3.0)
        t8_diag = np.array([1.0, 1.0, -2.0]) / (2.0 * sqrt3)
        phi = 4.0 * np.pi * sqrt3 / length**2
        gauge = _uniform_abelian_xy_field(t8_diag, phi, length)

        # F_01=sin(phi*T8)=diag(u,u,v)。非线性 sin 在有限-a 产生
        # 2u+v != 0；标准 SU(3) 场强取其 traceless 部分。
        u = np.sin(phi / (2.0 * sqrt3))
        v = -np.sin(phi / sqrt3)
        expected_field_diag = np.array([u, u, v])
        _assert_single_uniform_clover_component(
            self, gauge, expected_field_diag)

        trace_part = (2.0 * u + v) / 3.0
        self.assertGreater(abs(trace_part), 1e-6)
        expected_energy = 2.0 * (u - v)**2 / 3.0
        actual = np.asarray(flow_action_density(gauge))
        np.testing.assert_allclose(
            actual, expected_energy, rtol=5e-13, atol=5e-14)


if __name__ == "__main__":
    unittest.main(verbosity=2)
