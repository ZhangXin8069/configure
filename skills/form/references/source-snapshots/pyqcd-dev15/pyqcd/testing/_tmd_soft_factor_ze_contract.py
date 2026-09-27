"""TMD soft-factor / Z_E 入口的独立契约测试。"""
from __future__ import annotations

import unittest

import numpy as np

from pyqcd.gauge import wilson_rectangle
from pyqcd.renorm import (
    CF,
    fm_to_GeV,
    gammaE,
    pi,
    Z_E,
    alpha_s,
    fit_staple_plateau,
    msbar_tmd_reference_matrix_element,
    rapidity_subtraction,
    scan_staple_length,
    sdr_renormalized_tmd,
    soft_factor_rectangle,
    soft_function_intrinsic,
    soft_subtraction,
    soft_subtraction_factor,
    short_distance_renormalization_factor,
    sqrt_Z_E,
    tmd_matching_hybrid,
)
from pyqcd.tools import set_backend


def _weak_abelian_rectangle_gauge(length=4, phi=0.01):
    """构造弱 Abelian SU(3) 背景，保证矩形圈为正实且非平凡。"""
    diag = np.array([0.5, -0.5, 0.0], dtype=np.float64)
    gauge = np.broadcast_to(
        np.eye(3, dtype=np.complex128),
        (length, length, length, length, 4, 3, 3),
    ).copy()

    for y in range(length):
        gauge[0, 0, y, :, 0] = np.diag(
            np.exp(-1j * phi * y * diag))
    for x in range(length):
        gauge[0, 0, length - 1, x, 1] = np.diag(
            np.exp(1j * phi * length * x * diag))
    return gauge


def _to_numpy(value):
    if hasattr(value, "detach"):
        return value.detach().cpu().numpy()
    if hasattr(value, "get"):
        return value.get()
    return np.asarray(value)


class TmdSoftFactorZeContract(unittest.TestCase):
    """把 Z_E / sqrt(Z_E) / rapidity subtraction 压成最小公共契约。"""

    @classmethod
    def setUpClass(cls):
        set_backend("numpy")

    def tearDown(self):
        set_backend("numpy")

    def test_public_ze_api_matches_wilson_rectangle_geometry(self):
        """Z_E 族入口必须与 gauge.wilson_rectangle 完全同义。"""
        gauge = _weak_abelian_rectangle_gauge(length=4, phi=0.01)

        self.assertIs(soft_factor_rectangle, Z_E)
        self.assertIs(soft_subtraction_factor, sqrt_Z_E)
        self.assertIs(soft_subtraction, rapidity_subtraction)

        rectangle = np.asarray(wilson_rectangle(
            gauge, 2, 3, 0, 1, average=False))
        ze_local = np.asarray(Z_E(gauge, 2, 3, 0, 1, average=False))
        ze_mean = np.asarray(Z_E(gauge, 2, 3, 0, 1, average=True))
        rectangle_mean = np.asarray(wilson_rectangle(
            gauge, 2, 3, 0, 1, average=True))
        sqrt_ze = np.asarray(sqrt_Z_E(gauge, 2, 3, 0, 1))
        matrix_element = np.array([8.0, 12.0], dtype=float)
        subtracted = np.asarray(rapidity_subtraction(
            matrix_element, gauge, 2, 3, 0, 1))

        self.assertEqual(rectangle.shape, (4, 4, 4, 4))
        self.assertTrue(np.isrealobj(rectangle))
        self.assertGreater(float(np.min(rectangle)), 0.0)
        np.testing.assert_allclose(ze_local, rectangle, rtol=0.0, atol=0.0)
        np.testing.assert_allclose(ze_mean, rectangle_mean, rtol=0.0, atol=0.0)
        np.testing.assert_allclose(sqrt_ze, np.sqrt(rectangle_mean),
                                   rtol=1e-14, atol=1e-14)
        np.testing.assert_allclose(
            subtracted, matrix_element / np.sqrt(rectangle_mean),
            rtol=1e-14, atol=1e-14)

    def test_soft_function_normalizes_raw_rectangle_data_at_reference_point(self):
        """soft_function_intrinsic 只做参考点归一，不混入额外实现语义。"""
        gauge = _weak_abelian_rectangle_gauge(length=4, phi=0.01)
        b_grid = np.array([1, 2, 3], dtype=int)
        ze = np.array([
            float(wilson_rectangle(gauge, 2, b, 0, 1, average=True))
            for b in b_grid
        ])

        soft = soft_function_intrinsic(ze, b_perp=b_grid, mu=2.0)
        scaled = soft_function_intrinsic(7.0 * ze, b_perp=b_grid, mu=2.0)

        self.assertEqual(soft.shape, ze.shape)
        self.assertTrue(np.all(ze > 0.0))
        np.testing.assert_allclose(soft[0], 1.0, rtol=0.0, atol=0.0)
        np.testing.assert_allclose(soft, ze / ze[0], rtol=0.0, atol=0.0)
        np.testing.assert_allclose(scaled, soft, rtol=0.0, atol=0.0)
        np.testing.assert_allclose(np.sqrt(soft)[0], 1.0, rtol=0.0, atol=0.0)

    def test_rapidity_subtraction_enters_matching_only_through_sqrt_soft_factor(self):
        """tmd_matching_hybrid 必须把 soft_factor 作为 sqrt 分母消费。"""
        x = np.array([0.10, 0.30, 0.50, 0.70])
        y = x.copy()
        x_tmd = np.column_stack([
            np.exp(-1.0 * x),
            1.5 * np.exp(-1.2 * x),
            0.7 * np.exp(-0.8 * x),
        ])
        soft = np.array([1.0, 1.44, 2.25], dtype=float)

        _, baseline = tmd_matching_hybrid(
            x, y_grid=y, b_perp=[1, 2, 3], mu=2.0, pz_gev=2.5,
            cs_kernel=0.0, soft_factor=np.ones_like(soft),
            pz_scale=2.5, x_tmd=x_tmd)
        _, actual = tmd_matching_hybrid(
            x, y_grid=y, b_perp=[1, 2, 3], mu=2.0, pz_gev=2.5,
            cs_kernel=0.0, soft_factor=soft, pz_scale=2.5, x_tmd=x_tmd)

        expected = baseline / np.sqrt(soft)[None, :]
        np.testing.assert_allclose(actual, expected, rtol=1e-14, atol=1e-14)

    def test_msbar_reference_matrix_element_matches_doc_formula(self):
        """短距离参考矩阵元必须逐项复现文档 Eq. MS_matrix。"""
        z_fm = np.array([0.1, 0.2], dtype=float)
        b_fm = np.array([0.15, 0.25], dtype=float)
        mu = 2.0

        z = z_fm / fm_to_GeV
        b = b_fm / fm_to_GeV
        bracket = (
            0.5
            + 1.5 * np.log(mu ** 2 * (b ** 2 + z ** 2)
                           * np.exp(gammaE) / 4.0)
            - 2.0 * (z / b) * np.arctan(z / b)
        )
        expected = 1.0 + alpha_s(mu) * CF / (2.0 * pi) * bracket
        actual = np.asarray(msbar_tmd_reference_matrix_element(
            z_fm, b_fm, mu=mu))

        np.testing.assert_allclose(actual, expected, rtol=1e-14, atol=1e-14)
        with self.assertRaisesRegex(ValueError, "b_perp"):
            msbar_tmd_reference_matrix_element(0.1, 0.0, mu=mu)

        try:
            import torch
        except ImportError:
            return

        set_backend("torch", device="cpu")
        torch_result = _to_numpy(msbar_tmd_reference_matrix_element(
            torch.as_tensor(z_fm), torch.as_tensor(b_fm), mu=mu))
        np.testing.assert_allclose(torch_result, expected,
                                   rtol=1e-14, atol=1e-14)

    def test_sdr_factor_and_renormalized_tmd_close_ze_chain(self):
        """Z_O 与 h/Z_O 必须和显式 sqrt(Z_E) 减除一致。"""
        gauge = _weak_abelian_rectangle_gauge(length=4, phi=0.01)
        target = np.array([8.0, 12.0], dtype=float)
        reference = np.array([6.0, 9.0], dtype=float)
        msbar = np.array([3.0, 6.0], dtype=float)

        target_ze = np.asarray(Z_E(gauge, 1, 2, 0, 1, average=True))
        reference_ze = np.asarray(Z_E(gauge, 2, 3, 0, 1, average=True))
        target_sub = np.asarray(rapidity_subtraction(
            target, gauge, 1, 2, 0, 1, average=True))
        reference_sub = np.asarray(rapidity_subtraction(
            reference, gauge, 2, 3, 0, 1, average=True))

        expected_factor = reference_sub / msbar
        actual_factor = np.asarray(short_distance_renormalization_factor(
            reference, reference_ze, msbar))
        np.testing.assert_allclose(
            actual_factor, expected_factor, rtol=1e-14, atol=1e-14)

        expected = target_sub / expected_factor
        actual = np.asarray(sdr_renormalized_tmd(
            target, reference, target_ze, reference_ze, msbar))
        np.testing.assert_allclose(actual, expected, rtol=1e-14, atol=1e-14)

    def test_sdr_broadcasting_and_invalid_inputs_are_explicit(self):
        """SDR 入口必须广播一致，并对零/非有限分母报错。"""
        target = np.array([[12.0], [18.0]], dtype=float)
        reference = np.array([6.0, 10.0], dtype=float)
        target_ze = np.array([[4.0], [9.0]], dtype=float)
        reference_ze = np.array([16.0, 25.0], dtype=float)
        msbar = 2.0

        expected_factor = reference / np.sqrt(reference_ze) / msbar
        expected = target / np.sqrt(target_ze) / expected_factor
        actual = np.asarray(sdr_renormalized_tmd(
            target, reference, target_ze, reference_ze, msbar))
        self.assertEqual(actual.shape, (2, 2))
        np.testing.assert_allclose(actual, expected, rtol=1e-14, atol=1e-14)

        with self.assertRaisesRegex(ValueError, "reference_soft_factor.*0"):
            short_distance_renormalization_factor(reference, 0.0, 2.0)
        with self.assertRaisesRegex(ValueError, "msbar_reference.*0"):
            short_distance_renormalization_factor(reference, 4.0, 0.0)
        with self.assertRaisesRegex(ValueError, "有限"):
            sdr_renormalized_tmd(
                np.array([np.nan, 4.0]), reference, 4.0, 4.0, 2.0)

    def test_rectangle_backend_can_be_evaluated_on_torch_cpu(self):
        """若 Torch 可用，矩形圈原语必须和 NumPy 在 CPU 上一致。"""
        try:
            import torch
        except ImportError:
            raise unittest.SkipTest("torch is unavailable")

        gauge_np = _weak_abelian_rectangle_gauge(length=3, phi=0.02)
        set_backend("numpy")
        expected = np.asarray(wilson_rectangle(
            gauge_np, 1, 2, 0, 1, average=False))

        set_backend("torch", device="cpu")
        gauge_torch = torch.from_numpy(gauge_np)
        actual = wilson_rectangle(gauge_torch, 1, 2, 0, 1, average=False)

        np.testing.assert_allclose(_to_numpy(actual), expected,
                                   rtol=1e-12, atol=1e-12)

    def test_staple_length_scan_and_plateau_fit_contract(self):
        """L 扫描与 L->infty 平台拟合必须给出可解释结果。"""
        L_values = np.array([7, 5, 6], dtype=int)
        values = np.array([
            [1.0, 2.0, 3.0, 4.0],
            [2.0, 0.0, 1.0, 3.0],
            [4.0, 1.0, 0.0, 2.0],
        ], dtype=float)

        scan = scan_staple_length(L_values, values)
        np.testing.assert_array_equal(scan["L_values"], np.array([5, 6, 7]))
        np.testing.assert_allclose(scan["values"], values[[1, 2, 0]])
        self.assertEqual(scan["value_shape"], (4,))

        fit = fit_staple_plateau(scan, window=(5, 7))
        self.assertEqual(fit["fit_status"], "identifiable")
        self.assertEqual(fit["n_L_window"], 3)
        self.assertTrue(np.isfinite(fit["plateau"]))
        np.testing.assert_allclose(fit["plateau"], fit["c0"])

        generated = scan_staple_length(
            [2, 4, 3], measure_fn=lambda L: np.array([L, L + 1], dtype=float))
        np.testing.assert_array_equal(generated["L_values"],
                                      np.array([2, 3, 4]))
        np.testing.assert_allclose(
            generated["values"],
            np.array([[2.0, 3.0], [3.0, 4.0], [4.0, 5.0]], dtype=float))

        failed = fit_staple_plateau(scan, window=(5, 5))
        self.assertEqual(
            failed["fit_status"], "statistically_unidentifiable")
        self.assertIn("至少需要 2 个 L 点", failed["fit_reason"])


def test_tmd_soft_factor_ze_contracts():
    """Z_E / sqrt(Z_E) / rapidity subtraction 的总入口契约。"""
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        TmdSoftFactorZeContract)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    test_tmd_soft_factor_ze_contracts()
