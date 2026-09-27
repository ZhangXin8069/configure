"""Statistical-identifiability contracts for correlated fits."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings

import numpy as np


def _import_gvar():
    """Import the optional gvar dependency or skip the calling contract."""
    try:
        import gvar
    except ImportError as exc:
        raise unittest.SkipTest(
            "optional dependency gvar is unavailable") from exc
    return gvar


class CovarianceRankContractTests(unittest.TestCase):
    @staticmethod
    def _near_singular_correlation():
        cov = np.full((3, 3), 1.0 - 1.0e-5)
        np.fill_diagonal(cov, 1.0)
        return cov

    def test_effective_rank_matches_positive_and_negative_gvar_svdcut(self):
        """Positive cuts lift correlation modes; only negative cuts drop them."""
        from pyqcd.analysis._fitter import covariance_effective_rank

        cov = self._near_singular_correlation()
        self.assertEqual(covariance_effective_rank(cov, svdcut=1.0e-4), 3)
        self.assertEqual(covariance_effective_rank(cov, svdcut=-1.0e-4), 1)

    def test_negative_svdcut_keeps_mode_exactly_at_cutoff_like_gvar(self):
        """Changing the retained comparison from >= to > must fail this test."""
        gv = _import_gvar()
        from pyqcd.analysis._fitter import (
            calc_chi2,
            covariance_effective_rank,
        )

        cov = np.array([[1.0, 0.5], [0.5, 1.0]])
        residual = np.array([1.0, -1.0])
        cut = -1.0 / 3.0
        regulated = gv.regulate(gv.gvar(np.zeros(2), cov), svdcut=cut)
        expected = float(
            residual @ np.linalg.solve(gv.evalcov(regulated), residual)
        )

        self.assertEqual(covariance_effective_rank(cov, svdcut=cut), 2)
        self.assertAlmostEqual(
            calc_chi2(residual, np.zeros(2), cov, svdcut=cut),
            expected,
            places=12,
        )

    def test_calc_chi2_without_svdcut_rejects_tiny_negative_mode(self):
        """A tolerance-level negative covariance mode must not yield negative chi2."""
        from pyqcd.analysis._fitter import calc_chi2

        cov = np.array([
            [1.0, 1.0 + 2.0e-16],
            [1.0 + 2.0e-16, 1.0],
        ])
        with self.assertRaisesRegex(
                (ValueError, np.linalg.LinAlgError),
                r"strictly positive definite|positive definite",
        ):
            calc_chi2(np.array([1.0, -1.0]), np.zeros(2), cov, svdcut=None)

    def test_sample_rank_is_separate_from_regulated_fit_dof(self):
        from pyqcd.analysis._fitter import covariance_sample_rank

        rank_one = np.outer([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        self.assertEqual(covariance_sample_rank(rank_one), 1)
        self.assertEqual(
            covariance_sample_rank(self._near_singular_correlation()), 3)

    def test_calc_chi2_matches_gvar_positive_svd_regularization(self):
        gv = _import_gvar()
        from pyqcd.analysis._fitter import calc_chi2

        cov = self._near_singular_correlation()
        residual = np.array([0.2, -0.1, 0.05])
        regulated = gv.regulate(
            gv.gvar(np.zeros(3), cov), svdcut=1.0e-4)
        expected = float(
            residual @ np.linalg.solve(gv.evalcov(regulated), residual))
        actual = calc_chi2(residual, np.zeros(3), cov, svdcut=1.0e-4)
        np.testing.assert_allclose(actual, expected, rtol=1.0e-11, atol=1.0e-10)

    def test_identifiability_reason_distinguishes_point_count_from_rank(self):
        """An exactly determined fit fails the dof gate, not the rank gate."""
        from pyqcd.analysis._fitter import fit_identifiability

        self.assertEqual(
            fit_identifiability(
                n_data=3, n_params=3, effective_rank=3, sample_rank=3),
            (False, "Ndata=3 must exceed Nparam=3"),
        )
        self.assertEqual(
            fit_identifiability(
                n_data=6, n_params=3, effective_rank=2, sample_rank=3),
            (False, "fit data dof=2 must exceed Nparam=3"),
        )
        self.assertEqual(
            fit_identifiability(
                n_data=6, n_params=3, effective_rank=6, sample_rank=2),
            (False, "sample covariance rank=2 is below Nparam=3"),
        )
        self.assertEqual(
            fit_identifiability(
                n_data=6, n_params=3, effective_rank=6, sample_rank=3),
            (True, "identifiable"),
        )

    def test_prior_status_does_not_claim_data_identifiability(self):
        """A permitted prior fit is not evidence for data identifiability."""
        from pyqcd.analysis._fitter import fit_identifiability

        permitted, reason = fit_identifiability(
            n_data=5,
            n_params=2,
            effective_rank=5,
            sample_rank=5,
            has_prior=True,
        )

        self.assertTrue(permitted)
        self.assertIn("prior_constrained", reason)
        self.assertNotEqual(reason, "identifiable")


class FitAdapterContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _import_gvar()

    @staticmethod
    def _linear_model(x, p):
        return p["a"] + p["b"] * np.asarray(x)

    @staticmethod
    def _degenerate_sum_model(x, p):
        return np.ones(len(x)) * (p["a"] + p["b"])

    def test_full_rank_covariance_does_not_hide_degenerate_model_jacobian(self):
        """Two free parameters multiplying the same column are unidentifiable."""
        from pyqcd.analysis._fitter import (
            FitParams,
            covariance_sample_rank,
            fit,
        )

        rng = np.random.default_rng(831)
        x = np.arange(5, dtype=float)
        samples = 0.7 + 0.02 * rng.normal(size=(32, x.size))
        params = FitParams(
            p0={"a": 0.2, "b": 0.5},
            svdcut=1.0e-6,
        )

        result, cov, _, last_fit = fit(
            samples, x, self._degenerate_sum_model, params)

        self.assertEqual(covariance_sample_rank(cov), x.size)
        self.assertIsNone(last_fit)
        for values in result.values():
            self.assertTrue(np.isnan(values).all())

    def test_prior_and_p0_parameter_keys_must_match(self):
        gv = _import_gvar()
        from pyqcd.analysis._fitter import FitParams, fit

        rng = np.random.default_rng(104)
        samples = rng.normal(size=(8, 4))
        params = FitParams(
            p0={"a": 0.0},
            prior={"b": gv.gvar(0.0, 1.0)},
            svdcut=1.0e-6,
        )
        with self.assertRaisesRegex(ValueError, "same parameter keys"):
            fit(samples, np.arange(4), self._linear_model, params)

    def test_prior_fit_reports_lsqfit_chi2_per_dof(self):
        gv = _import_gvar()
        from pyqcd.analysis._fitter import FitParams, fit

        rng = np.random.default_rng(105)
        x = np.arange(5, dtype=float)
        central = 0.4 - 0.07 * x
        samples = central + 0.02 * rng.normal(size=(12, x.size))
        params = FitParams(
            p0={"a": 0.3, "b": -0.05},
            prior={
                "a": gv.gvar(0.0, 0.5),
                "b": gv.gvar(0.0, 0.5),
            },
            svdcut=1.0e-6,
        )
        result, _, _, last_fit = fit(
            samples, x, self._linear_model, params)

        self.assertIsNotNone(last_fit)
        self.assertAlmostEqual(
            result["chi2"][-1], last_fit.chi2 / last_fit.dof, places=12)
        self.assertEqual(
            getattr(last_fit, "pyqcd_fit_status", None),
            "prior_constrained",
        )
        sentinel = object()
        self.assertIsNone(
            getattr(last_fit, "pyqcd_data_identifiable", sentinel)
        )

    def test_cubic_stationary_parameter_is_not_counted_as_a_direction(self):
        from pyqcd.analysis._fitter import _numerical_model_jacobian_rank

        x = np.arange(5, dtype=np.float64)

        def cubic_model(coordinates, parameters):
            return (parameters["a"]
                    + parameters["b"] ** 3 * np.asarray(coordinates))

        rank = _numerical_model_jacobian_rank(
            cubic_model,
            x,
            {"a": 1.0, "b": 0.0},
            ["a", "b"],
            np.eye(x.size),
            1.0e-6,
            x.size,
        )

        self.assertEqual(rank, 1)

    def test_zero_amplitude_exponential_has_a_zero_local_direction(self):
        """A vanished amplitude makes its decay rate locally unidentifiable.

        Wide dependency diagnostics may leave the finite model domain, but
        that must not turn the exact local zero column into an overflow error.
        """
        from pyqcd.analysis._fitter import _model_jacobian_rank

        x = np.arange(5, dtype=np.float64)

        def zero_amplitude_model(coordinates, parameters):
            coordinates = np.asarray(coordinates)
            return (parameters["offset"]
                    + parameters["amplitude"]
                    * np.exp(-parameters["rate"] * coordinates))

        def zero_amplitude_jacobian(coordinates, parameters):
            coordinates = np.asarray(coordinates)
            decay = np.exp(-parameters["rate"] * coordinates)
            return np.column_stack((
                np.ones_like(coordinates),
                decay,
                -parameters["amplitude"] * coordinates * decay,
            ))

        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            rank = _model_jacobian_rank(
                zero_amplitude_model,
                x,
                {"offset": 0.2, "amplitude": 0.0, "rate": 0.5},
                ["offset", "amplitude", "rate"],
                np.eye(x.size),
                1.0e-6,
                x.size,
                jacobian=zero_amplitude_jacobian,
            )

        self.assertEqual(rank, 2)

    def test_nonholomorphic_conjugate_model_keeps_both_real_directions(self):
        """Real parameters must not infer rank from a holomorphic probe."""
        from pyqcd.analysis._fitter import _numerical_model_jacobian_rank

        x = np.arange(2, dtype=np.float64)

        def conjugate_model(_coordinates, parameters):
            a = parameters["a"]
            b = parameters["b"]
            return np.array([a + b, b + np.conj(b)])

        rank = _numerical_model_jacobian_rank(
            conjugate_model,
            x,
            {"a": 0.25, "b": -0.4},
            ["a", "b"],
            np.eye(x.size),
            1.0e-6,
            x.size,
        )

        self.assertEqual(rank, 2)

    def test_high_curvature_real_model_keeps_both_directions(self):
        """A high-curvature real model must refine its step, not zero a column."""
        from pyqcd.analysis._fitter import _numerical_model_jacobian_rank

        x = np.arange(5, dtype=np.float64)

        def high_curvature_model(coordinates, parameters):
            coordinates = np.asarray(coordinates)
            return parameters["a"] + np.sin(
                2.0e4 * parameters["b"]
            ) * coordinates

        rank = _numerical_model_jacobian_rank(
            high_curvature_model,
            x,
            {"a": 0.2, "b": 0.0},
            ["a", "b"],
            np.eye(x.size),
            1.0e-6,
            x.size,
        )

        self.assertEqual(rank, 2)

    def test_high_curvature_nonzero_expansion_point_keeps_both_directions(self):
        """The local ladder must refine below a curved nonzero expansion point."""
        from pyqcd.analysis._fitter import _numerical_model_jacobian_rank

        x = np.arange(5, dtype=np.float64)

        def high_curvature_model(coordinates, parameters):
            coordinates = np.asarray(coordinates)
            return parameters["a"] + np.sin(
                1.0e4 * parameters["b"]
            ) * coordinates

        rank = _numerical_model_jacobian_rank(
            high_curvature_model,
            x,
            {"a": 0.2, "b": 1.0e-4},
            ["a", "b"],
            np.eye(x.size),
            1.0e-6,
            x.size,
        )

        self.assertEqual(rank, 2)

    def test_analytic_jacobian_preserves_small_linear_term_under_curvature(self):
        """Dropping the analytic callback must collapse the tiny true direction."""
        from pyqcd.analysis._fitter import _model_jacobian_rank

        x = np.arange(5, dtype=np.float64)

        def curved_model(coordinates, parameters):
            coordinates = np.asarray(coordinates)
            b = parameters["b"]
            return parameters["a"] + (1.0e-12 * b + 1.0e8 * b**2) * coordinates

        def curved_jacobian(coordinates, parameters):
            coordinates = np.asarray(coordinates)
            return np.column_stack((
                np.ones_like(coordinates),
                (1.0e-12 + 2.0e8 * parameters["b"]) * coordinates,
            ))

        rank = _model_jacobian_rank(
            curved_model,
            x,
            {"a": 0.2, "b": 0.0},
            ["a", "b"],
            np.eye(x.size),
            1.0e-6,
            x.size,
            jacobian=curved_jacobian,
        )

        self.assertEqual(rank, 2)

    def test_black_box_invisible_nonzero_column_is_not_called_zero(self):
        """No finite probe can prove an unobserved black-box column is exactly zero."""
        from pyqcd.analysis._fitter import _numerical_model_jacobian_rank

        x = np.arange(5, dtype=np.float64)

        def invisible_model(coordinates, parameters):
            coordinates = np.asarray(coordinates)
            return 1.0e16 + 1.0e-320 * parameters["slope"] * coordinates

        with self.assertRaisesRegex(ValueError, r"numerically indeterminate"):
            _numerical_model_jacobian_rank(
                invisible_model,
                x,
                {"slope": 0.0},
                ["slope"],
                np.eye(x.size),
                1.0e-6,
                x.size,
            )

    def test_abs_kink_is_reported_as_nondifferentiable(self):
        from pyqcd.analysis._fitter import _numerical_model_jacobian_rank

        x = np.arange(4, dtype=np.float64)

        def abs_model(coordinates, parameters):
            return np.abs(parameters["a"]) * np.asarray(coordinates)

        with self.assertRaisesRegex(ValueError, r"nondifferentiable|kink"):
            _numerical_model_jacobian_rank(
                abs_model, x, {"a": 0.0}, ["a"], np.eye(x.size),
                1.0e-6, x.size,
            )

    def test_max_kink_is_reported_as_nondifferentiable(self):
        from pyqcd.analysis._fitter import _numerical_model_jacobian_rank

        x = np.arange(4, dtype=np.float64)

        def max_model(coordinates, parameters):
            return np.maximum(parameters["a"], 0.0) * np.asarray(coordinates)

        with self.assertRaisesRegex(ValueError, r"nondifferentiable|kink"):
            _numerical_model_jacobian_rank(
                max_model, x, {"a": 0.0}, ["a"], np.eye(x.size),
                1.0e-6, x.size,
            )

    def test_branch_kink_is_reported_as_nondifferentiable(self):
        from pyqcd.analysis._fitter import _numerical_model_jacobian_rank

        x = np.arange(4, dtype=np.float64)

        def branch_model(coordinates, parameters):
            coordinates = np.asarray(coordinates)
            value = parameters["a"]
            return value * coordinates if value >= 0.0 else -value * coordinates

        with self.assertRaisesRegex(ValueError, r"nondifferentiable|kink"):
            _numerical_model_jacobian_rank(
                branch_model, x, {"a": 0.0}, ["a"], np.eye(x.size),
                1.0e-6, x.size,
            )

    def test_real_only_underresolved_column_is_numerically_indeterminate(self):
        from pyqcd.analysis._fitter import _numerical_model_jacobian_rank

        x = np.arange(5, dtype=np.float64)

        def real_only_model(coordinates, parameters):
            coordinates = np.asarray(coordinates)
            # The cast deliberately discards complex probes.  The slope is
            # present, but below float64 resolution near the 1e16 offset for
            # every local probe used by the contract.  An exactly independent
            # parameter would also be unchanged by the wide dependency probe;
            # this model changes there, so silently returning a zero column is
            # forbidden.
            values = 1.0e16 + parameters["slope"] * coordinates
            return np.asarray(values, dtype=np.float64)

        with self.assertRaisesRegex(ValueError, r"numerically indeterminate"):
            _numerical_model_jacobian_rank(
                real_only_model,
                x,
                {"slope": 1.0e-12},
                ["slope"],
                np.eye(x.size),
                1.0e-6,
                x.size,
            )

    def test_small_scaled_column_survives_large_constant_offset(self):
        from pyqcd.analysis._fitter import _numerical_model_jacobian_rank

        x = np.arange(5, dtype=np.float64)

        def affine_model(coordinates, parameters):
            return (parameters["offset"]
                    + parameters["slope"] * np.asarray(coordinates))

        rank = _numerical_model_jacobian_rank(
            affine_model,
            x,
            {"offset": 1.0e12, "slope": 1.0e-12},
            ["offset", "slope"],
            np.eye(x.size),
            1.0e-6,
            x.size,
        )

        self.assertEqual(rank, 2)

    def test_near_degenerate_rank_boundary_is_explicit(self):
        from pyqcd.analysis._fitter import _numerical_model_jacobian_rank

        x = np.arange(5, dtype=np.float64)

        def model(coordinates, parameters, delta):
            coordinates = np.asarray(coordinates)
            return (parameters["a"] * coordinates
                    + parameters["b"] * (
                        coordinates + 0.5 * delta * coordinates ** 2))

        def rank_for(delta):
            return _numerical_model_jacobian_rank(
                lambda coordinates, parameters: model(
                    coordinates, parameters, delta),
                x,
                {"a": 1.0, "b": 1.0},
                ["a", "b"],
                np.eye(x.size),
                1.0e-6,
                x.size,
            )

        # This is a numerical policy boundary, not a claim of exact algebraic
        # dependence: 1e-6 is retained but ill-conditioned, while 5e-7 is
        # below the default sqrt(machine-epsilon) relative rank gate.
        self.assertEqual(rank_for(1.0e-6), 2)
        self.assertEqual(rank_for(5.0e-7), 1)

    def test_fit_reuses_covariance_eigensystem_across_samples(self):
        """The invariant whitening metric must be prepared once per fit."""
        from pyqcd.analysis._fitter import FitParams, fit

        rng = np.random.default_rng(9303)
        x = np.arange(5, dtype=np.float64)
        samples = 0.4 - 0.07 * x + 0.01 * rng.normal(size=(6, x.size))
        params = FitParams(
            p0={"a": 0.3, "b": -0.05},
            svdcut=1.0e-6,
        )

        from pyqcd.analysis import _fitter
        with patch(
                "pyqcd.analysis._fitter._correlation_eigensystem",
                wraps=_fitter._correlation_eigensystem,
        ) as eigensystem:
            fit(samples, x, self._linear_model, params)

        self.assertEqual(eigensystem.call_count, 1)

    def test_fit_uses_named_analytic_jacobian_without_numeric_probes(self):
        """Removing the FitParams callback route must re-enter the guarded probe."""
        from pyqcd.analysis._fitter import FitParams, fit

        rng = np.random.default_rng(9304)
        x = np.arange(5, dtype=np.float64)
        samples = 0.4 - 0.07 * x + 0.01 * rng.normal(size=(12, x.size))

        def named_jacobian(coordinates, _parameters):
            coordinates = np.asarray(coordinates)
            return {
                "b": coordinates,
                "a": np.ones_like(coordinates),
            }

        params = FitParams(
            p0={"b": -0.05, "a": 0.3},
            svdcut=1.0e-6,
            jacobian=named_jacobian,
        )
        with patch(
                "pyqcd.analysis._fitter._finite_difference_column",
                side_effect=AssertionError("numeric probe must not run"),
        ):
            result, _, _, last_fit = fit(
                samples, x, self._linear_model, params)

        self.assertIsNotNone(last_fit)
        self.assertEqual(last_fit.pyqcd_fit_status, "identifiable")
        for values in result.values():
            self.assertTrue(np.isfinite(values).all())


class FiniteInputContractTests(unittest.TestCase):
    @staticmethod
    def _linear_model(x, p):
        return p["a"] + p["b"] * np.asarray(x)

    @staticmethod
    def _samples():
        rng = np.random.default_rng(832)
        x = np.arange(4, dtype=float)
        central = 0.4 - 0.07 * x
        return x, central + 0.02 * rng.normal(size=(16, x.size))

    def _assert_descriptive_value_error(self, pattern, operation):
        try:
            operation()
        except Exception as error:  # Convert a wrong exception type into RED failure.
            self.assertIsInstance(error, ValueError)
            self.assertRegex(str(error), pattern)
        else:
            self.fail("expected a descriptive ValueError")

    def test_calc_chi2_rejects_nonfinite_residual(self):
        from pyqcd.analysis._fitter import calc_chi2

        self._assert_descriptive_value_error(
            r"residual.*finite",
            lambda: calc_chi2(
                np.array([np.nan, 0.0]),
                np.zeros(2),
                np.eye(2),
            ),
        )

    def test_fit_rejects_nonfinite_y_coordinates(self):
        from pyqcd.analysis._fitter import FitParams, fit

        x, samples = self._samples()
        samples[0, 0] = np.nan
        self._assert_descriptive_value_error(
            r"y_coor.*finite",
            lambda: fit(
                samples,
                x,
                self._linear_model,
                FitParams(p0={"a": 0.3, "b": -0.05}),
            ),
        )

    def test_fit_rejects_complex_y_until_real_imag_stacking_is_supported(self):
        """Removing the explicit complex-data guard would silently lose information."""
        from pyqcd.analysis._fitter import FitParams, fit

        x, samples = self._samples()
        complex_samples = samples.astype(np.complex128)
        complex_samples += 1j * (0.2 - 0.03 * x)[None, :]
        self._assert_descriptive_value_error(
            r"complex y_coor.*real/imag|complex y_coor.*not supported",
            lambda: fit(
                complex_samples,
                x,
                self._linear_model,
                FitParams(p0={"a": 0.3, "b": -0.05}),
            ),
        )

    def test_fit_rejects_single_sample_nonfinite_y_coordinates(self):
        from pyqcd.analysis._fitter import FitParams, fit

        x = np.arange(4, dtype=float)
        samples = np.zeros((1, x.size), dtype=float)
        samples[0, 0] = np.nan
        self._assert_descriptive_value_error(
            r"y_coor.*finite",
            lambda: fit(
                samples,
                x,
                self._linear_model,
                FitParams(p0={"a": 0.3, "b": -0.05}),
            ),
        )

    def test_fit_rejects_empty_sample_axis(self):
        from pyqcd.analysis._fitter import FitParams, fit

        x = np.arange(4, dtype=float)
        self._assert_descriptive_value_error(
            r"at least one sample|empty sample",
            lambda: fit(
                np.empty((0, x.size), dtype=float),
                x,
                self._linear_model,
                FitParams(p0={"a": 0.3, "b": -0.05}),
            ),
        )

    def test_fit_rejects_nonfinite_x_coordinates(self):
        from pyqcd.analysis._fitter import FitParams, fit

        x, samples = self._samples()
        x[2] = np.inf
        self._assert_descriptive_value_error(
            r"x_coor.*finite",
            lambda: fit(
                samples,
                x,
                self._linear_model,
                FitParams(p0={"a": 0.3, "b": -0.05}),
            ),
        )

    def test_fit_rejects_nonfinite_model_output(self):
        from pyqcd.analysis._fitter import FitParams, fit

        x, samples = self._samples()

        def nonfinite_model(coordinates, _parameters):
            return np.full(len(coordinates), np.nan)

        self._assert_descriptive_value_error(
            r"model output.*finite",
            lambda: fit(
                samples,
                x,
                nonfinite_model,
                FitParams(p0={"a": 0.3}),
            ),
        )

    def test_jacobian_perturbation_nonfinite_output_is_propagated(self):
        from pyqcd.analysis._fitter import _numerical_model_jacobian_rank

        x = np.arange(4, dtype=float)

        def perturbation_nan_model(coordinates, parameters):
            if parameters["a"] != 0.3:
                return np.full(len(coordinates), np.nan)
            return np.ones(len(coordinates))

        self._assert_descriptive_value_error(
            r"model output.*finite",
            lambda: _numerical_model_jacobian_rank(
                perturbation_nan_model,
                x,
                {"a": 0.3},
                ["a"],
                np.eye(x.size),
                1.0e-6,
                x.size,
            ),
        )

    def test_jacobian_perturbation_shape_error_is_propagated(self):
        from pyqcd.analysis._fitter import _numerical_model_jacobian_rank

        x = np.arange(4, dtype=float)

        def perturbation_shape_model(coordinates, parameters):
            if parameters["a"] != 0.3:
                return np.zeros(len(coordinates) + 1)
            return np.ones(len(coordinates))

        self._assert_descriptive_value_error(
            r"model output size.*number of y_coor",
            lambda: _numerical_model_jacobian_rank(
                perturbation_shape_model,
                x,
                {"a": 0.3},
                ["a"],
                np.eye(x.size),
                1.0e-6,
                x.size,
            ),
        )

    def test_calc_chi2_rejects_mismatched_shapes_before_subtraction(self):
        from pyqcd.analysis._fitter import calc_chi2

        self._assert_descriptive_value_error(
            r"same shape",
            lambda: calc_chi2(
                np.zeros(2), np.zeros((2, 1)), np.eye(2),
            ),
        )

    def test_cov_mat_rejects_empty_feature_axis(self):
        from pyqcd.analysis._disconnected import cov_mat

        self._assert_descriptive_value_error(
            r"cov_mat.*feature",
            lambda: cov_mat(np.empty((3, 0))),
        )


class BuiltinAnalyticJacobianContractTests(unittest.TestCase):
    """Closed-form production Jacobians must follow their named parameters."""

    def test_ratio_model_jacobian_matches_hand_derived_columns(self):
        from pyqcd.analysis._disconnected import model_ratio_jacobian

        x = [(4, 1), (4, 2)]
        p = {"dE": 0.4, "c0": 0.2, "c1": -0.3}
        dt = np.array([4.0, 4.0])
        dtau = np.array([1.0, 2.0])
        left = np.exp(-p["dE"] * dtau)
        right = np.exp(-p["dE"] * (dt - dtau))
        actual = model_ratio_jacobian(x, p)

        self.assertEqual(set(actual), set(p))
        np.testing.assert_allclose(actual["c0"], np.ones(2))
        np.testing.assert_allclose(actual["c1"], left + right)
        np.testing.assert_allclose(
            actual["dE"],
            -p["c1"] * (dtau * left + (dt - dtau) * right),
        )

    def test_energy_model_jacobian_matches_hand_derived_columns(self):
        from pyqcd.analysis._proton_energy import energy_model_jacobian

        t = np.array([0.0, 2.0])
        p = {"dE": 0.3, "c0": 0.7, "E0": 0.4, "c1": 0.2}
        ground = np.exp(-p["E0"] * t)
        excited = np.exp(-p["dE"] * t)
        corr = p["c0"] * ground * (1.0 + p["c1"] * excited)
        actual = energy_model_jacobian(t, p)

        self.assertEqual(set(actual), set(p))
        np.testing.assert_allclose(actual["c0"], ground * (1 + p["c1"] * excited))
        np.testing.assert_allclose(actual["c1"], p["c0"] * ground * excited)
        np.testing.assert_allclose(actual["E0"], -t * corr)
        np.testing.assert_allclose(
            actual["dE"], -t * p["c0"] * p["c1"] * ground * excited)

    def test_fh_model_jacobian_is_constant_column(self):
        from pyqcd.analysis._fh import fh_model_jacobian

        actual = fh_model_jacobian(np.array([2, 3, 4]), {"c0": 0.5})
        self.assertEqual(set(actual), {"c0"})
        np.testing.assert_array_equal(actual["c0"], np.ones(3))


class LowSampleFitContractTests(unittest.TestCase):
    @staticmethod
    def _two_configuration_inputs(nt=6, nz=1, nb=None):
        t = np.arange(nt, dtype=np.float64)
        corr_2pt = {}
        ope = {}
        for cid, shift in ((11, 0.0), (22, 0.03)):
            corr = np.exp(-(0.25 + shift) * t) + 0.01
            corr_2pt[cid] = {
                "corr_pp_P2": corr,
                "corr_pion_P2": 0.8 * corr,
                "corr_pp_P200": corr,
            }
            values = np.sin(0.4 * t + shift)[None, :]
            if nb is None:
                ope[cid] = {"combined": values}
            else:
                ope[cid] = {"tmd": values[:, None, :]}
        return corr_2pt, ope

    def test_ratio_fit_skips_rank_one_covariance_and_marks_report(self):
        from pyqcd.analysis._fitter import FitParams
        from pyqcd.analysis._ratio2pt import (
            SampleParams2pt, do_fit_and_report,
        )

        samples = SampleParams2pt(
            conf_short="rank_guard", conf_name="rank_guard", conf_ids=[1, 2],
            Nt=8, Nx=1, Px=0, Py=0, Pz=2, Nsample=2, dt_max=6,
        )
        fit_params = FitParams(
            p0={"c0": 0.2, "c1": 0.1, "dE": 0.5},
            dt_start=3, dt_end=4, nex=1, svdcut=1.0e-6,
        )
        ratio = np.zeros((2, 6, 6, 1), dtype=np.float64)
        for sample in range(2):
            for dt in range(3, 5):
                for dtau in range(1, dt):
                    ratio[sample, dt, dtau, 0] = (
                        0.2 + 0.1 * np.exp(-0.5 * dtau)
                        + 0.1 * np.exp(-0.5 * (dt - dtau))
                        + sample * 1.0e-3 * (1 + dt + dtau)
                    )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                    "lsqfit.nonlinear_fit",
                    side_effect=AssertionError("rank-deficient fit must be skipped")):
                result = do_fit_and_report(
                    ratio, fit_params, samples, tmpdir,
                    jack=True, verbose=False,
                )

            numeric_names = ("c0", "c1", "dE", "chi2")
            metadata_names = {
                "fit_status", "fit_reason", "fit_status_by_z",
                "fit_reason_by_z", "condition_number", "effective_rank",
                "sample_rank", "required_rank",
            }
            self.assertTrue(set(numeric_names).issubset(result))
            self.assertTrue(metadata_names.issubset(result))
            for name in numeric_names:
                self.assertTrue(np.isnan(result[name]).all())
            self.assertEqual(
                str(result["fit_status"]), "statistically_unidentifiable")

            saved = np.load(Path(tmpdir) / "0_fit_data.npz")
            self.assertTrue(set(numeric_names).issubset(saved.files))
            self.assertTrue(metadata_names.issubset(saved.files))
            report = (Path(tmpdir) / "1_fit_report.txt").read_text()
            self.assertIn("statistically_unidentifiable", report)
            self.assertIn("effective covariance rank = 5", report)
            self.assertIn("sample covariance rank = 1", report)
            self.assertIn("required parameter rank = 3", report)

    def test_energy_fit_skips_rank_one_covariance_and_marks_report(self):
        from pyqcd.analysis._proton_energy import EnergyParams, do_fit

        params = EnergyParams(
            conf_short="rank_guard", conf_name="rank_guard", conf_ids=[1, 2],
            Nt=10, Nx=4, Px=0, Py=0, Pz=2, Nsample=2, dt_max=9,
            dt_start=2, dt_end=7,
        )
        t = np.arange(params.dt_max, dtype=np.float64)
        central = 0.7 * np.exp(-0.4 * t) * (
            1.0 + 0.2 * np.exp(-0.3 * t))
        corr2 = np.stack([central, central * (1.0 + 1.0e-3 * t)])

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                    "lsqfit.nonlinear_fit",
                    side_effect=AssertionError("rank-deficient fit must be skipped")):
                result = do_fit(
                    corr2, params, tmpdir, jack=True, verbose=False,
                )

            numeric_names = ("c0", "c1", "E0", "dE", "chi2")
            metadata_names = {
                "fit_status", "fit_reason", "condition_number",
                "effective_rank", "sample_rank", "required_rank",
            }
            self.assertTrue(set(numeric_names).issubset(result))
            self.assertTrue(metadata_names.issubset(result))
            for name in numeric_names:
                self.assertTrue(np.isnan(result[name]).all())
            self.assertEqual(
                str(result["fit_status"]), "statistically_unidentifiable")

            saved = np.load(Path(tmpdir) / "1_fit_data.npz")
            self.assertTrue(set(numeric_names).issubset(saved.files))
            self.assertTrue(metadata_names.issubset(saved.files))
            report = (Path(tmpdir) / "2_fit_report.txt").read_text()
            self.assertIn("statistically_unidentifiable", report)
            self.assertIn("effective covariance rank = 6", report)
            self.assertIn("sample covariance rank = 1", report)
            self.assertIn("required parameter rank = 4", report)

    def test_disconnected_ratio_does_not_save_finite_low_rank_fit(self):
        from pyqcd.analysis._disconnected import run_disconnected_ratio

        corr_2pt, ope = self._two_configuration_inputs()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                    "lsqfit.nonlinear_fit",
                    side_effect=AssertionError("rank-deficient fit must be skipped")):
                result = run_disconnected_ratio(
                    corr_2pt, ope, [11, 22], tmpdir,
                    logger=lambda _message: None,
                    NT=6, NX=1, dt_max=5,
                    dt_start=2, dt_end=4, cut=2,
                )
            report = (Path(tmpdir) / "analysis" / "disconnected"
                      / "1_fit_report.txt").read_text()

        for channel in ("proton", "pion"):
            for name in ("c0", "c1", "dE", "chi2"):
                self.assertTrue(np.isnan(result[channel][name]).all())
        self.assertIn("statistically_unidentifiable", report)
        self.assertIn("effective covariance rank", report)

    def test_tmd_ratio_does_not_diagonalize_away_low_rank_status(self):
        from pyqcd.analysis._tmd_ratio import run_disconnected_tmd_ratio

        corr_2pt, ope = self._two_configuration_inputs(nb=1)
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                    "lsqfit.nonlinear_fit",
                    side_effect=AssertionError("rank-deficient fit must be skipped")):
                result = run_disconnected_tmd_ratio(
                    corr_2pt, ope, [11, 22], tmpdir,
                    logger=lambda _message: None,
                    NT=6, nz=1, nb=1, dt_max=5,
                    dt_start=2, dt_end=4, cut=2,
                    momentum="P200",
                )
            report = (Path(tmpdir) / "analysis" / "tmd_ratio"
                      / "1_fit_report_P200.txt").read_text()

        for name in ("c0", "c1", "dE", "chi2"):
            self.assertTrue(np.isnan(result["proton"][name]).all())
        self.assertIn("statistically_unidentifiable", report)
        self.assertIn("effective covariance rank", report)

    def test_tmd_identifiable_fit_keeps_full_hermitian_covariance(self):
        gv = _import_gvar()

        from pyqcd.analysis._tmd_ratio import run_disconnected_tmd_ratio

        t = np.arange(6, dtype=np.float64)
        corr_2pt = {}
        ope = {}
        conf_ids = list(range(4))
        for k in conf_ids:
            amplitude = k - 1.5
            corr = np.exp(-(0.22 + 0.012 * amplitude) * t) * (
                1.0 + 0.015 * amplitude * np.cos(0.7 * t)
            ) + 0.01
            corr_2pt[k] = {"corr_pp_P200": corr}
            values = (
                np.sin(0.4 * t + 0.13 * amplitude)
                + 0.04 * amplitude * np.cos(0.9 * t)
                + 0.01 * amplitude**2 * np.sin(0.2 * t)
            )
            ope[k] = {"tmd": values[None, None, :]}

        covariances = []
        svdcuts = []

        class FakeFit:
            def __init__(self, p0):
                self.pmean = dict(p0)
                self.chi2 = 1.0
                self.dof = 3

            @staticmethod
            def format(maxline=True):
                return f"fake fit maxline={maxline}"

        def fake_nonlinear_fit(*args, **kwargs):
            self.assertEqual(args, ())
            covariances.append(gv.evalcov(kwargs["data"][1]))
            svdcuts.append(kwargs["svdcut"])
            return FakeFit(kwargs["p0"])

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                    "lsqfit.nonlinear_fit",
                    side_effect=fake_nonlinear_fit,
            ), patch(
                    "pyqcd.analysis._fitter._finite_difference_column",
                    side_effect=AssertionError("TMD ratio must use analytic Jacobian"),
            ):
                run_disconnected_tmd_ratio(
                    corr_2pt,
                    ope,
                    conf_ids,
                    tmpdir,
                    logger=lambda _message: None,
                    NT=6,
                    nz=1,
                    nb=1,
                    dt_max=5,
                    dt_start=2,
                    dt_end=4,
                    cut=2,
                    momentum="P200",
                )

        self.assertGreater(len(covariances), 0)
        covariance = covariances[0]
        off_diagonal = covariance - np.diag(np.diag(covariance))
        self.assertGreater(np.max(np.abs(off_diagonal)), 1.0e-15)
        np.testing.assert_allclose(
            covariance,
            covariance.conj().T,
            rtol=0.0,
            atol=np.max(np.abs(covariance)) * 1.0e-14,
        )
        self.assertTrue(all(cut > 0.0 for cut in svdcuts))

    def test_tmd_fit_and_plateau_statuses_are_separate(self):
        from pyqcd.analysis._tmd_ratio import run_disconnected_tmd_ratio

        corr_2pt, ope = self._two_configuration_inputs(nb=1)
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_disconnected_tmd_ratio(
                corr_2pt,
                ope,
                [11, 22],
                tmpdir,
                logger=lambda _message: None,
                NT=6,
                nz=1,
                nb=1,
                dt_max=5,
                dt_start=2,
                dt_end=4,
                cut=2,
                momentum="P200",
            )["proton"]
            out_dir = Path(tmpdir) / "analysis" / "tmd_ratio"
            fit_saved = np.load(out_dir / "0_fit_data_P200.npz")
            plateau_status_path = out_dir / "c0_plateau_status_P200.npz"

            self.assertIn("fit_status", fit_saved.files)
            self.assertTrue(
                np.all(
                    np.asarray(fit_saved["fit_status"])
                    == "statistically_unidentifiable"
                )
            )
            self.assertTrue(plateau_status_path.is_file())
            plateau_saved = np.load(plateau_status_path)

            self.assertIn("fit_status", result)
            self.assertIn("plateau_status", result)
            self.assertEqual(
                result["fit_status"],
                "statistically_unidentifiable",
            )
            self.assertEqual(result["plateau_status"], "identifiable")
            self.assertTrue(np.isnan(result["c0"]).all())
            self.assertTrue(np.isfinite(result["c0_plateau"]).all())
            self.assertTrue(
                np.all(plateau_saved["plateau_status"] == "identifiable")
            )
            self.assertTrue(np.all(plateau_saved["plateau_sample_rank"] == 1))


class IdentifiableFitRegressionTests(unittest.TestCase):
    """The rank guard must not reject ordinary SVD-regularized ensembles."""

    def test_ratio_fit_remains_finite_when_retained_rank_covers_parameters(self):
        from pyqcd.analysis._fitter import FitParams
        from pyqcd.analysis._ratio2pt import (
            SampleParams2pt, do_fit_and_report,
        )

        rng = np.random.default_rng(9301)
        nsample = 8
        samples = SampleParams2pt(
            conf_short="rank_ok", conf_name="rank_ok",
            conf_ids=list(range(nsample)), Nt=8, Nx=1,
            Px=0, Py=0, Pz=2, Nsample=nsample, dt_max=6,
        )
        fit_params = FitParams(
            p0={"c0": 0.2, "c1": 0.1, "dE": 0.5},
            dt_start=3, dt_end=4, nex=1, svdcut=1.0e-6,
        )
        ratio = np.zeros((nsample, 6, 6, 1), dtype=np.float64)
        for sample in range(nsample):
            for dt in range(3, 5):
                for dtau in range(1, dt):
                    ratio[sample, dt, dtau, 0] = (
                        0.2 + 0.1 * np.exp(-0.5 * dtau)
                        + 0.1 * np.exp(-0.5 * (dt - dtau))
                        + 2.0e-4 * rng.normal()
                    )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                    "pyqcd.analysis._fitter._finite_difference_column",
                    side_effect=AssertionError("ratio must use analytic Jacobian"),
            ):
                result = do_fit_and_report(
                    ratio, fit_params, samples, tmpdir,
                    jack=True, verbose=False,
                )
            report = (Path(tmpdir) / "1_fit_report.txt").read_text()

        for name in ("c0", "c1", "dE", "chi2"):
            self.assertTrue(np.isfinite(result[name]).all())
        self.assertEqual(str(result["fit_status"]), "identifiable")
        self.assertIn("fit status = identifiable", report)

    def test_energy_fit_remains_finite_when_rank_covers_parameters(self):
        from pyqcd.analysis._proton_energy import EnergyParams, do_fit

        rng = np.random.default_rng(9302)
        nsample = 8
        params = EnergyParams(
            conf_short="rank_ok", conf_name="rank_ok",
            conf_ids=list(range(nsample)), Nt=10, Nx=4,
            Px=0, Py=0, Pz=2, Nsample=nsample, dt_max=9,
            dt_start=2, dt_end=7,
            p0={"c0": 0.7, "c1": 0.2, "E0": 0.4, "dE": 0.3},
        )
        t = np.arange(params.dt_max, dtype=np.float64)
        central = 0.7 * np.exp(-0.4 * t) * (
            1.0 + 0.2 * np.exp(-0.3 * t))
        corr2 = central[None, :] * (
            1.0 + 2.0e-4 * rng.normal(size=(nsample, params.dt_max)))

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                    "pyqcd.analysis._fitter._finite_difference_column",
                    side_effect=AssertionError("energy must use analytic Jacobian"),
            ):
                result = do_fit(
                    corr2, params, tmpdir, jack=True, verbose=False,
                )
            report = (Path(tmpdir) / "2_fit_report.txt").read_text()

        for name in ("c0", "c1", "E0", "dE", "chi2"):
            self.assertTrue(np.isfinite(result[name]).all())
        self.assertEqual(str(result["fit_status"]), "identifiable")
        self.assertIn("fit status = identifiable", report)

    def test_fh_fit_uses_analytic_jacobian_and_remains_finite(self):
        from pyqcd.analysis._fh import FHParams, do_fit_and_report
        from pyqcd.analysis._fitter import FitParams

        rng = np.random.default_rng(9305)
        fh = 0.45 + 2.0e-3 * rng.normal(size=(8, 6, 1))
        fit_params = FitParams(
            p0={"c0": 0.4}, dt_start=1, dt_end=4, svdcut=1.0e-6)
        params = FHParams(conf_short="rank_ok", P=2, z_list=[0])

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                    "pyqcd.analysis._fitter._finite_difference_column",
                    side_effect=AssertionError("FH must use analytic Jacobian"),
            ):
                do_fit_and_report(
                    fh, tmpdir, fit_params, params, verbose=False)
            saved = np.load(Path(tmpdir) / "fit_dt1_4.npz")
            report = (Path(tmpdir) / "report_dt1_4.txt").read_text()

        self.assertTrue(np.isfinite(saved["c0"]).all())
        self.assertTrue(np.isfinite(saved["chi2"]).all())
        self.assertEqual(str(saved["fit_status"]), "identifiable")
        self.assertIn("fit status = identifiable", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
