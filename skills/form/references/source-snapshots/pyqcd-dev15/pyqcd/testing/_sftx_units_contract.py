"""SFTX flow-time dimensional contracts."""
from __future__ import annotations

import unittest

import numpy as np

from pyqcd.renorm import sftx_gluon_matching_coeff


HBARC_GEV_FM = 0.1973269804


class SftxUnitsContract(unittest.TestCase):
    def test_tau_and_lattice_spacing_match_explicit_gev_inverse_square(self):
        """把无量纲 tau 直接放进 log(2 mu^2 t) 会产生约 30% 偏差。"""
        tau = 3.0
        a_fm = 0.1
        mu_gev = 2.0
        expected_t = tau * (a_fm / HBARC_GEV_FM) ** 2

        try:
            via_lattice = sftx_gluon_matching_coeff(
                mu=mu_gev, tau=tau, a_fm=a_fm)
            via_physical = sftx_gluon_matching_coeff(
                mu=mu_gev, t_gev_m2=expected_t)
        except Exception as exc:
            self.fail(f'SFTX 缺少显式流时间单位接口: {exc}')

        self.assertAlmostEqual(expected_t, 0.7704568388, places=9)
        np.testing.assert_allclose(via_lattice, via_physical,
                                   rtol=0.0, atol=2e-15)

    def test_ambiguous_mixed_and_nonpositive_times_are_rejected(self):
        """无单位位置参数或两套单位混用不得悄悄进入对数。"""
        with self.assertRaises(TypeError):
            sftx_gluon_matching_coeff(0.1, 2.0)
        invalid = (
            {},
            {'tau': 3.0},
            {'a_fm': 0.1},
            {'t_gev_m2': 0.8, 'tau': 3.0, 'a_fm': 0.1},
            {'t_gev_m2': 0.0},
        )
        for arguments in invalid:
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    sftx_gluon_matching_coeff(mu=2.0, **arguments)


if __name__ == '__main__':
    unittest.main(verbosity=2)
