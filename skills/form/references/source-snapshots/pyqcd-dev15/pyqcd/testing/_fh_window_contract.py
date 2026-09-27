"""Behavioral contracts for FH adaptive constant-fit windows.

Run directly with ``python pyqcd/testing/_fh_window_contract.py``.
"""

import unittest

import numpy as np


class FHAdaptiveWindowContractTests(unittest.TestCase):
    @staticmethod
    def _delta_for_z6(base, seed, t_vals=None):
        """Make full-rank resamples with a hand-specified z=6 time profile."""
        rng = np.random.default_rng(seed)
        if t_vals is None:
            t_vals = np.arange(6, 11)
        t_vals = np.asarray(t_vals, dtype=int)
        delta = np.empty((7, t_vals.size, 80))
        delta[:6] = 1.0 + 0.03 * rng.standard_normal((6, t_vals.size, 80))
        delta[6] = (np.asarray(base, dtype=float)[:, None]
                    + 0.03 * rng.standard_normal((t_vals.size, 80)))
        return delta, t_vals

    def test_retries_rightward_until_a_later_accepted_window(self):
        """Removing two early contaminated t_sep values reaches [8,10]."""
        from pyqcd.analysis import fh_adaptive_windows

        # [6,8] and [7,9] are non-constant, while [8,10] is a plateau.
        delta, t_vals = self._delta_for_z6([0.0, 0.0, 10.0, 10.0, 10.0], 61)
        record = fh_adaptive_windows(
            delta, t_vals, 6, 8, chi2_limit=1.5, t_floor=6, z_max=7)[-1]

        self.assertEqual((record['t_do'], record['t_up']), (8, 10))
        self.assertLessEqual(record['fit']['chi2'], 1.5)
        self.assertEqual(record.get('status'), 'chi2_accepted')

    def test_sparse_tsep_skips_gaps_and_reaches_later_accepted_window(self):
        """Sparse grids slide by data index until the later plateau is tested."""
        from pyqcd.analysis import fh_adaptive_windows

        # Two-point windows by data index are [6,7], [7,10], [10,11].
        # The first two are non-constant; only the last is a plateau.
        delta, t_vals = self._delta_for_z6(
            [0.0, 10.0, 5.0, 5.0], 64, [6, 7, 10, 11])
        record = fh_adaptive_windows(
            delta, t_vals, 6, 7, chi2_limit=1.5, t_floor=6, z_max=7)[-1]

        self.assertEqual((record['t_do'], record['t_up']), (10, 11))
        self.assertLessEqual(record['fit']['chi2'], 1.5)
        self.assertEqual(record.get('status'), 'chi2_accepted')

    def test_keeps_an_initial_window_that_already_meets_chi2_limit(self):
        """An accepted initial window is returned unchanged and marked accepted."""
        from pyqcd.analysis import fh_adaptive_windows

        delta, t_vals = self._delta_for_z6([3.0, 3.0, 3.0, 3.0, 3.0], 62)
        record = fh_adaptive_windows(
            delta, t_vals, 6, 8, chi2_limit=1.5, t_floor=6, z_max=7)[-1]

        self.assertEqual((record['t_do'], record['t_up']), (6, 8))
        self.assertLessEqual(record['fit']['chi2'], 1.5)
        self.assertEqual(record.get('status'), 'chi2_accepted')

    def test_reports_exhausted_window_when_no_accepted_window_exists(self):
        """The final legal window remains visibly rejected instead of accepted."""
        from pyqcd.analysis import fh_adaptive_windows

        delta, t_vals = self._delta_for_z6([0.0, 0.0, 10.0, 0.0, 10.0], 63)
        record = fh_adaptive_windows(
            delta, t_vals, 6, 8, chi2_limit=1.5, t_floor=6, z_max=7)[-1]

        self.assertEqual((record['t_do'], record['t_up']), (8, 10))
        self.assertGreater(record['fit']['chi2'], 1.5)
        self.assertEqual(record.get('status'), 'chi2_exceeded')

    def test_rejects_unsorted_or_duplicate_tsep_values(self):
        """Index windows require one strictly increasing coordinate per data row."""
        from pyqcd.analysis import fh_adaptive_windows

        invalid_grids = ([6, 10, 7, 11], [6, 7, 7, 10])
        for t_vals in invalid_grids:
            with self.subTest(t_vals=t_vals):
                delta, t_vals = self._delta_for_z6(
                    [3.0, 3.0, 3.0, 3.0], 65, t_vals)
                with self.assertRaisesRegex(ValueError, 'strictly increasing'):
                    fh_adaptive_windows(
                        delta, t_vals, 6, 7, chi2_limit=1.5,
                        t_floor=6, z_max=1)

    def test_constant_fit_preserves_documented_tsep_sample_axes(self):
        """``(n_tsep,n_sample)=(3,2)`` returns a real rank failure."""
        from pyqcd.analysis import fit_constant_window

        data = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
        result = fit_constant_window(data)
        self.assertEqual(result['n_data'], 3)
        self.assertEqual(result['c0_samples'].shape, (2,))
        self.assertEqual(result['fit_status'],
                         'statistically_unidentifiable')
        self.assertTrue(np.isnan(result['c0']).all())
        self.assertTrue(np.isnan(result['c0_std']).all())
        self.assertTrue(np.isnan(result['chi2']).all())
        self.assertTrue(np.isnan(result['chi2_nocov']).all())
        self.assertTrue(np.isnan(result['c0_samples']).all())
        self.assertLess(result['sample_rank'], result['n_data'])
        self.assertEqual(result['effective_rank'], result['sample_rank'])
        self.assertTrue(result['fit_reason'])

    def test_constant_fit_rejects_square_sample_axis_without_pseudoinverse(self):
        """A square sample matrix still has at most ``n_tsep-1`` covariance rank."""
        from pyqcd.analysis import fit_constant_window

        data = np.array([
            [0.0, 1.0, 2.0],
            [1.0, 2.0, 4.0],
            [2.0, 3.0, 6.0],
        ])
        result = fit_constant_window(data)
        self.assertEqual(result['n_data'], 3)
        self.assertEqual(result['fit_status'],
                         'statistically_unidentifiable')
        self.assertLess(result['sample_rank'], 3)
        self.assertTrue(np.isnan(result['c0_samples']).all())

    def test_constant_fit_rejects_repeated_samples_with_rank_metadata(self):
        """Repeated resamples are unavailable, not a successful zero-mode fit."""
        from pyqcd.analysis import fit_constant_window

        data = np.array([
            [1.0, 1.0, 1.0, 1.0],
            [2.0, 2.0, 2.0, 2.0],
            [3.0, 3.0, 3.0, 3.0],
        ])
        result = fit_constant_window(data)
        self.assertEqual(result['fit_status'],
                         'statistically_unidentifiable')
        self.assertEqual(result['sample_rank'], 0)
        self.assertEqual(result['effective_rank'], 0)
        for name in ('c0', 'c0_std', 'chi2', 'chi2_nocov'):
            self.assertTrue(np.isnan(result[name]))
        self.assertTrue(np.isnan(result['c0_samples']).all())

    def test_constant_fit_keeps_full_rank_closed_form_values(self):
        """A genuinely full-rank input retains the covariance-weighted result."""
        from pyqcd.analysis import fit_constant_window

        data = np.array([
            [1.0, 1.2, 0.9, 1.1],
            [1.4, 1.1, 1.2, 1.3],
        ])
        result = fit_constant_window(data)

        centered = data - data.mean(axis=1, keepdims=True)
        cov = centered @ centered.T / data.shape[1]
        cov_inv = np.linalg.inv(cov)
        ones = np.ones(data.shape[0])
        denom = ones @ cov_inv @ ones
        expected_samples = (ones @ cov_inv @ data) / denom
        expected_c0 = float(expected_samples.mean())
        residual = data.mean(axis=1) - expected_c0
        expected_chi2 = float(residual @ cov_inv @ residual)
        expected_chi2 /= data.shape[0] - 1
        diag_inv = np.diag(1.0 / data.std(axis=1) ** 2)
        expected_nocov = float(residual @ diag_inv @ residual)
        expected_nocov /= data.shape[0] - 1

        self.assertEqual(result['fit_status'], 'identifiable')
        self.assertEqual(result['sample_rank'], 2)
        self.assertEqual(result['effective_rank'], 2)
        np.testing.assert_allclose(result['c0_samples'], expected_samples)
        np.testing.assert_allclose(result['c0'], expected_c0)
        np.testing.assert_allclose(result['c0_std'],
                                   np.std(expected_samples))
        np.testing.assert_allclose(result['chi2'], expected_chi2)
        np.testing.assert_allclose(result['chi2_nocov'], expected_nocov)

    def test_adaptive_window_propagates_statistical_failure_without_sliding(self):
        """A failed constant fit stops chi2-driven window motion immediately."""
        from pyqcd.analysis import fh_adaptive_windows

        delta = np.ones((7, 5, 3), dtype=float)
        record = fh_adaptive_windows(
            delta, [6, 7, 8, 9, 10], 6, 8, chi2_limit=1.5,
            t_floor=6, z_max=7)[-1]

        self.assertEqual((record['t_do'], record['t_up']), (6, 8))
        self.assertEqual(record['fit']['fit_status'],
                         'statistically_unidentifiable')
        self.assertEqual(record['fit_status'],
                         'statistically_unidentifiable')
        self.assertEqual(record['status'], 'statistically_unidentifiable')
        self.assertTrue(np.isnan(record['fit']['c0']))

    def test_adaptive_window_rejects_tsep_axis_mismatch(self):
        """delta 第二轴必须与 t_sep_vals 一一对应。"""
        from pyqcd.analysis import fh_adaptive_windows

        delta = np.ones((2, 4, 8))
        with self.assertRaisesRegex(ValueError, 't_sep'):
            fh_adaptive_windows(delta, [6, 7, 8], 6, 7)


if __name__ == '__main__':
    unittest.main()
