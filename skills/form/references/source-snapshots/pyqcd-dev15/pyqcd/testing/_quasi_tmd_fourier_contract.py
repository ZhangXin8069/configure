"""Independent Fourier contracts for :func:`quasi_tmd_pdf`.

The oracle integrates a literal complex linear coordinate-space matrix element
on a much finer grid.  It deliberately does not reuse the implementation's
truncation, interpolation, or quadrature path.
"""
from __future__ import annotations

import unittest
import warnings
from unittest.mock import patch

import numpy as np

from pyqcd.renorm import quasi_pdf_gluon, quasi_tmd_pdf, tmd_matching_hybrid


FM_TO_GEV = 0.197


def _matrix_element(z_fm: np.ndarray) -> np.ndarray:
    """Hermitian-compatible positive-axis h_R(z) with known values."""
    z_fm = np.asarray(z_fm, dtype=float)
    base = 1.0 + 0.35 * z_fm + 1j * (0.20 * z_fm)
    return base[:, None] * np.array([1.0, 0.65])[None, :]


def _independent_oracle(x_grid, z_max_fm, pz_gev, p_t, n_ref=131073):
    """Literal full-axis exponential integral after Hermitian extension."""
    z_positive_fm = np.linspace(0.0, z_max_fm, n_ref)
    h_positive = _matrix_element(z_positive_fm)
    z_fm = np.concatenate((-z_positive_fm[:0:-1], z_positive_fm))
    h = np.concatenate((np.conj(h_positive[:0:-1]), h_positive), axis=0)
    z_gev_inv = z_fm / FM_TO_GEV
    phase = np.exp(-1j * np.outer(x_grid, pz_gev * z_gev_inv))
    integral = np.trapezoid(phase[:, :, None] * h[None, :, :],
                            z_gev_inv, axis=1).real
    norm = pz_gev ** 2 / p_t ** 2
    return integral / (2.0 * np.pi * pz_gev * norm)


class QuasiTmdFourierContract(unittest.TestCase):
    """Unit and quadrature contracts for the cos-type quasi-TMD prototype."""

    def setUp(self):
        self.z_fm = np.linspace(0.0, 0.8, 17)
        self.h = _matrix_element(self.z_fm)
        self.x = np.array([-0.6, 0.0, 0.37, 0.91])
        self.pz = 2.3
        self.p_t = 2.7

    def test_quasi_tmd_rejects_nonzero_start_instead_of_truncating_integral(self):
        """积分公式从 z=0 开始，非零起点必须显式失败。"""
        with self.assertRaisesRegex(ValueError, r"z.?=.?0"):
            quasi_tmd_pdf(
                np.ones((2, 1)), np.array([0.2, 0.4]), [0.1],
                self.pz, p_t=self.p_t, x_grid=np.array([0.3]), n_pts=17)

    def test_quasi_pdf_gluon_rejects_nonzero_start_instead_of_truncating_integral(self):
        """sin 变换同样不得从非零首点开始积分。"""
        with self.assertRaisesRegex(ValueError, r"z.?=.?0"):
            quasi_pdf_gluon(
                np.ones(2), np.array([0.2, 0.4]), self.pz,
                x_grid=np.array([0.3]))

    def test_positive_half_axis_matches_literal_hermitian_full_axis(self):
        """漏掉 Hermitian 延拓的倍数或 sine 通道都会破坏全轴变换。"""
        z_positive = np.linspace(0.0, 0.8, 17)
        h_positive = (
            1.0 + 0.35 * z_positive
            + 1j * (0.20 * z_positive)
        )
        x_grid = np.array([-0.6, 0.0, 0.37, 0.91])

        _, actual = quasi_tmd_pdf(
            h_positive, z_positive, [0.2], self.pz, p_t=self.p_t,
            x_grid=x_grid, n_pts=4097)

        z_ref_positive = np.linspace(0.0, 0.8, 131073)
        h_ref_positive = (
            1.0 + 0.35 * z_ref_positive
            + 1j * (0.20 * z_ref_positive)
        )
        z_full_fm = np.concatenate(
            (-z_ref_positive[:0:-1], z_ref_positive))
        h_full = np.concatenate(
            (np.conj(h_ref_positive[:0:-1]), h_ref_positive))
        z_full = z_full_fm / FM_TO_GEV
        phase = np.exp(-1j * np.outer(x_grid, self.pz * z_full))
        expected = np.trapezoid(phase * h_full[None, :], z_full, axis=1)
        expected /= (
            2.0 * np.pi * self.pz
            * (self.pz ** 2 / self.p_t ** 2)
        )

        self.assertTrue(np.isrealobj(actual))
        np.testing.assert_allclose(actual, expected.real,
                                   rtol=3e-7, atol=3e-8)

    def test_explicit_fm_maximum_matches_default_and_hermitian_oracle(self):
        """z_max=max(z_grid) is an fm boundary and leaves the default unchanged."""
        x_default, actual_default = quasi_tmd_pdf(
            self.h, self.z_fm, [0.1, 0.3], self.pz, p_t=self.p_t,
            x_grid=self.x, n_pts=4097)
        x_explicit, actual_explicit = quasi_tmd_pdf(
            self.h, self.z_fm, [0.1, 0.3], self.pz, p_t=self.p_t,
            x_grid=self.x, n_pts=4097, z_max=float(np.max(self.z_fm)))
        expected = _independent_oracle(
            self.x, float(np.max(self.z_fm)), self.pz, self.p_t)

        np.testing.assert_array_equal(x_default, self.x)
        np.testing.assert_array_equal(x_explicit, self.x)
        np.testing.assert_allclose(actual_explicit, actual_default,
                                   rtol=0.0, atol=0.0)
        self.assertTrue(np.isrealobj(actual_default))
        np.testing.assert_allclose(actual_default, expected,
                                   rtol=3e-7, atol=3e-8)

    def test_fm_cutoff_and_npts_refinement_follow_independent_oracle(self):
        """The fm cutoff is applied before conversion and n_pts refines the integral."""
        z_max_fm = 0.4
        _, coarse = quasi_tmd_pdf(
            self.h, self.z_fm, [0.1, 0.3], self.pz, p_t=self.p_t,
            x_grid=self.x, n_pts=9, z_max=z_max_fm)
        _, fine = quasi_tmd_pdf(
            self.h, self.z_fm, [0.1, 0.3], self.pz, p_t=self.p_t,
            x_grid=self.x, n_pts=4097, z_max=z_max_fm)
        expected = _independent_oracle(self.x, z_max_fm, self.pz, self.p_t)

        self.assertGreater(float(np.max(np.abs(fine - coarse))), 1e-5)
        np.testing.assert_allclose(fine, expected, rtol=3e-7, atol=3e-8)

    def test_npts_two_is_a_valid_endpoint_rule_and_smaller_or_noninteger_fails(self):
        """The two-endpoint rule is exact; invalid refinement counts are rejected."""
        _, endpoint = quasi_tmd_pdf(
            self.h, self.z_fm, [0.1, 0.3], self.pz, p_t=self.p_t,
            x_grid=self.x, n_pts=2)
        z_gev_inv = np.array([self.z_fm[0], self.z_fm[-1]]) / FM_TO_GEV
        dz = z_gev_inv[1] - z_gev_inv[0]
        weights = np.array([0.5 * dz, 0.5 * dz])
        argument = np.outer(self.x, self.pz * z_gev_inv)
        weighted = weights[:, None] * self.h[[0, -1]]
        expected = 2.0 * (
            np.cos(argument) @ weighted.real
            + np.sin(argument) @ weighted.imag
        )
        expected /= 2.0 * np.pi * self.pz * (self.pz ** 2 / self.p_t ** 2)

        self.assertEqual(endpoint.shape, (len(self.x), 2))
        self.assertTrue(np.all(np.isfinite(endpoint)))
        np.testing.assert_allclose(endpoint, expected, rtol=2e-15, atol=2e-15)
        for n_pts in (0, 1, 2.5):
            with self.subTest(n_pts=n_pts):
                with self.assertRaises(ValueError):
                    quasi_tmd_pdf(
                        self.h, self.z_fm, [0.1, 0.3], self.pz,
                        p_t=self.p_t, x_grid=self.x, n_pts=n_pts)

    def test_fourier_quadrature_has_no_deprecation_warning(self):
        """The production Fourier quadrature must not depend on deprecated NumPy APIs."""
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            _, actual = quasi_tmd_pdf(
                self.h, self.z_fm, [0.1, 0.3], self.pz, p_t=self.p_t,
                x_grid=self.x, n_pts=257)
        self.assertTrue(np.all(np.isfinite(actual)))

    def test_real_quasi_output_enters_matching_without_complex_warning(self):
        """纯实 h_R 的链路保持实 dtype，匹配层不得触发复数降维警告。"""
        real_h = self.h.real
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            x, quasi = quasi_tmd_pdf(
                real_h, self.z_fm, [0.1, 0.3], self.pz, p_t=self.p_t,
                x_grid=np.array([0.2, 0.4, 0.6]), n_pts=257)
            _, matched = tmd_matching_hybrid(
                x, pz_gev=self.pz, pz_scale=self.pz, cs_kernel=0.0,
                soft_factor=1.0, x_tmd=quasi)

        self.assertTrue(np.isrealobj(quasi))
        self.assertTrue(np.isrealobj(matched))
        complex_warnings = [
            item for item in caught
            if "Casting complex values to real" in str(item.message)
        ]
        self.assertEqual(complex_warnings, [])

    def test_complex_matching_identity_limit_preserves_imaginary_channel(self):
        """α_s=0、无快度和 soft=1 时 Z^{-1}=I，复 TMD 必须原样保留。"""
        x = np.array([0.2, 0.4, 0.6])
        x_tmd = np.array([
            [0.3 + 0.2j, 0.1 - 0.5j],
            [0.7 - 0.1j, 0.4 + 0.3j],
            [0.9 + 0.6j, 0.2 - 0.4j],
        ])
        with patch("pyqcd.renorm._tmdextract.A_s_run", return_value=0.0):
            x_out, actual = tmd_matching_hybrid(
                x, pz_gev=self.pz, pz_scale=self.pz, cs_kernel=0.0,
                soft_factor=1.0, x_tmd=x_tmd)

        np.testing.assert_array_equal(x_out, x)
        self.assertTrue(np.iscomplexobj(actual))
        np.testing.assert_allclose(actual, x_tmd, rtol=0.0, atol=0.0)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        QuasiTmdFourierContract)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
