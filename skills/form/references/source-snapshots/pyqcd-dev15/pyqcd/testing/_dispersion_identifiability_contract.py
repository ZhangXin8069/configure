"""Behavioral contracts for the three-parameter dispersion fit.

This module is intentionally run directly while the dispersion guard is being
developed.  It does not modify the central test registry.
"""

import unittest
import warnings
from unittest.mock import patch

import numpy as np


class DispersionIdentifiabilityContractTests(unittest.TestCase):
    """Contracts for an identifiable, positivity-constrained E-space fit."""

    a_gev = 0.5
    pz = np.array([0.0, 1.0, 2.0, 3.0])
    truth = (0.91, 1.07, -0.12)

    def _energies(self, pz=None):
        from pyqcd.analysis._dispersion import pz_to_gev_lattice, th_E0

        pz = self.pz if pz is None else np.asarray(pz, dtype=float)
        momentum = pz_to_gev_lattice(pz, 24, self.a_gev)
        return th_E0(momentum, *self.truth, self.a_gev)

    def test_nonfinite_input_is_rejected_before_optimization(self):
        from pyqcd.analysis._dispersion import fit_dispersion

        with patch(
                "scipy.optimize.minimize",
                side_effect=AssertionError("invalid data reached optimizer")):
            with self.assertRaisesRegex(ValueError, "finite"):
                fit_dispersion(
                    [self._energies()[0], np.nan, self._energies()[2],
                     self._energies()[3]],
                    self.pz, self.a_gev,
                )

    def test_two_momenta_fail_rank_gate_and_suggest_check(self):
        from pyqcd.analysis._dispersion import fit_dispersion

        # E(0) fixes m; one nonzero |p| only fixes one k2/k3 combination.
        pz = np.array([0.0, 2.0])
        with patch(
                "scipy.optimize.minimize",
                side_effect=AssertionError("rank-deficient data reached optimizer")):
            with self.assertRaisesRegex(
                    ValueError, "rank=2.*dispersion_check.*independent momenta"):
                fit_dispersion(self._energies(pz), pz, self.a_gev)

    def test_exactly_determined_three_points_have_zero_dof_but_are_identifiable(self):
        from pyqcd.analysis._dispersion import fit_dispersion

        pz = np.array([0.0, 1.0, 2.0])
        fitted, diagnostics = fit_dispersion(
            self._energies(pz), pz, self.a_gev,
            errors=np.full(pz.size, 1.0e-3), return_diagnostics=True,
        )

        np.testing.assert_allclose(fitted, self.truth, rtol=1.0e-7, atol=1.0e-7)
        self.assertEqual(diagnostics["jacobian_rank"], 3)
        self.assertEqual(diagnostics["dof"], 0)
        self.assertFalse(diagnostics["goodness_of_fit_available"])
        self.assertTrue(np.isnan(diagnostics["reduced_chi2"]))

    def test_identifiable_synthetic_data_recovers_truth_with_covariance(self):
        from pyqcd.analysis._dispersion import fit_dispersion

        fitted, diagnostics = fit_dispersion(
            self._energies(), self.pz, self.a_gev,
            errors=np.full(self.pz.size, 1.0e-3), return_diagnostics=True,
        )

        np.testing.assert_allclose(fitted, self.truth, rtol=1.0e-8, atol=1.0e-8)
        self.assertTrue(diagnostics["success"])
        self.assertEqual(diagnostics["jacobian_rank"], 3)
        self.assertEqual(diagnostics["dof"], 1)
        self.assertTrue(np.isfinite(diagnostics["covariance"]).all())
        self.assertTrue(np.isfinite(diagnostics["singular_values"]).all())
        self.assertTrue(
            np.isfinite(diagnostics["scaled_singular_values"]).all())
        self.assertEqual(diagnostics["likelihood_space"], "energy")
        self.assertTrue(np.isfinite(diagnostics["scaled_condition"]))
        self.assertLess(
            diagnostics["scaled_condition"], diagnostics["condition_limit"])
        self.assertTrue(diagnostics["covariance_valid"])

    def test_adversarial_energies_keep_positive_mass_without_sqrt_warnings(self):
        from pyqcd.analysis._dispersion import (
            fit_dispersion, pz_to_gev_lattice, th_E0,
        )

        # The E-space optimum drives the two middle predictions onto the
        # positivity boundary; an unconstrained Gaussian covariance would
        # therefore assign substantial weight to forbidden E² < 0 values.
        energies = np.array([1.0, 1.0e-3, 1.0e-3, 5.0])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            fitted, diagnostics = fit_dispersion(
                energies, self.pz, self.a_gev, return_diagnostics=True,
            )
            predictions = th_E0(
                pz_to_gev_lattice(self.pz, 24, self.a_gev),
                *fitted, self.a_gev,
            )

        self.assertEqual(caught, [])
        self.assertGreater(fitted[0], 0.0)
        self.assertTrue(np.isfinite(predictions).all())
        self.assertTrue(np.all(predictions > 0.0))
        self.assertTrue(np.isfinite(diagnostics["condition"]))
        self.assertTrue(diagnostics["constraint_active"])
        self.assertFalse(diagnostics["covariance_valid"])
        self.assertTrue(np.isnan(diagnostics["covariance"]).all())

    def test_column_scaling_prevents_false_ill_conditioned_rejection(self):
        from pyqcd.analysis._dispersion import (
            fit_dispersion, pz_to_gev_lattice, th_E0,
        )

        pz = 1.0e-2 * self.pz
        fitted, diagnostics = fit_dispersion(
            self._energies(pz), pz, self.a_gev,
            errors=np.full(pz.size, 1.0e-3), return_diagnostics=True,
        )
        predictions = th_E0(
            pz_to_gev_lattice(pz, 24, self.a_gev), *fitted, self.a_gev,
        )

        np.testing.assert_allclose(
            predictions, self._energies(pz), rtol=1.0e-8, atol=1.0e-10)
        self.assertGreaterEqual(
            diagnostics["condition"], diagnostics["condition_limit"])
        self.assertLess(
            diagnostics["scaled_condition"], diagnostics["condition_limit"])
        self.assertEqual(diagnostics["jacobian_rank"], 3)

    def test_large_relative_error_uses_reference_energy_space_likelihood(self):
        from pyqcd.analysis._dispersion import (
            fit_dispersion, pz_to_gev_lattice, th_E0,
        )

        energies = np.array([0.2, 1.1, 1.4, 1.8])
        errors = np.array([0.5, 0.05, 0.05, 0.05])
        expected_energy_fit = np.array(
            [0.95340570, 1.00174680, -0.09579931])
        old_delta_method_fit = np.array(
            [0.73135012, 1.71393934, -1.02754008])

        fitted, diagnostics = fit_dispersion(
            energies, self.pz, self.a_gev, errors=errors,
            return_diagnostics=True,
        )
        momentum = pz_to_gev_lattice(self.pz, 24, self.a_gev)
        fitted_prediction = th_E0(momentum, *fitted, self.a_gev)
        old_prediction = th_E0(
            momentum, *old_delta_method_fit, self.a_gev)
        fitted_chi2 = np.sum(((fitted_prediction - energies) / errors) ** 2)
        old_chi2 = np.sum(((old_prediction - energies) / errors) ** 2)

        np.testing.assert_allclose(
            fitted, expected_energy_fit, rtol=2.0e-6, atol=2.0e-6)
        self.assertEqual(diagnostics["likelihood_space"], "energy")
        self.assertLess(fitted_chi2, old_chi2 - 1.0)


if __name__ == "__main__":
    unittest.main()
