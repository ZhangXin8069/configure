"""NLO 胶子匹配 x 网格的公共入口契约。"""
from __future__ import annotations

import unittest
import warnings
from unittest.mock import patch

import numpy as np

from pyqcd.renorm import hR_PDF


def _normal_grid_fixture():
    """返回已避开零节点的现有 NLO 匹配型输入。"""
    x = np.linspace(0.02, 1.48, 21)
    return x, np.exp(-x ** 2)


class MatchingGridContract(unittest.TestCase):
    def test_exact_zero_node_is_rejected_without_runtime_warning(self):
        """无主值离散化时，x=0 必须在数值核前被公共入口拒绝。"""
        x = np.array([-0.4, 0.0, 0.4])
        h0 = np.exp(-x ** 2)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with patch(
                    "pyqcd.renorm._matching.A_s_run",
                    side_effect=AssertionError(
                        "zero-grid validation must precede coupling work")), \
                    patch(
                        "pyqcd.renorm._matching._matching_kernels",
                        side_effect=AssertionError(
                            "zero-grid validation must precede kernel work")):
                with self.assertRaisesRegex(
                        ValueError, "zero.*avoid|avoid.*zero"):
                    hR_PDF(
                        x, Pz_=4, conf="L24x72",
                        hR_tilde_data=h0, mu_=2.0)

        runtime_warnings = [
            item for item in caught if issubclass(item.category, RuntimeWarning)
        ]
        self.assertEqual(runtime_warnings, [])

    def test_normal_zero_avoiding_grid_remains_finite_without_runtime_warning(self):
        """正常避零网格仍给出有限 NLO 匹配结果且不泄漏 RuntimeWarning。"""
        x, h0 = _normal_grid_fixture()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            out = hR_PDF(x, Pz_=4, conf="L24x72", hR_tilde_data=h0, mu_=2.0)

        self.assertTrue(np.isfinite(out).all())
        runtime_warnings = [
            item for item in caught if issubclass(item.category, RuntimeWarning)
        ]
        self.assertEqual(runtime_warnings, [])

    def test_zero_coupling_keeps_the_identity_matching_contract(self):
        """alpha_s=0 时 Z=I，匹配必须精确保留避零网格上的输入。"""
        x, h0 = _normal_grid_fixture()

        with patch("pyqcd.renorm._matching.A_s_run", return_value=0.0):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                out = hR_PDF(
                    x, Pz_=4, conf="L24x72", hR_tilde_data=h0, mu_=2.0)

        np.testing.assert_allclose(out, h0, rtol=0.0, atol=0.0)
        runtime_warnings = [
            item for item in caught if issubclass(item.category, RuntimeWarning)
        ]
        self.assertEqual(runtime_warnings, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
