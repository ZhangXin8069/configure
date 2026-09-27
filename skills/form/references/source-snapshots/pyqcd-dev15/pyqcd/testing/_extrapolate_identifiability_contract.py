"""Behavioral contracts for continuum-extrapolation identifiability."""

from __future__ import annotations

import unittest
import copy

import numpy as np


class ExtrapolateIdentifiabilityContractTests(unittest.TestCase):
    @staticmethod
    def _single_ensemble_rows():
        """Eight momenta do not separate constant-a and constant-mpi terms."""
        from pyqcd.renorm import hR_form

        x = np.array([0.25])
        true_par = np.array([0.37, -0.21, 0.0, 0.0,
                             0.12, 0.0, 0.08, 0.0])
        rows = []
        for pz in range(1, 9):
            a, mpi, L = 0.5, 0.20, 24
            value = hR_form((a, float(pz), mpi, L), true_par)
            rows.append({
                "x": x,
                "hR": np.full((1, 12), value),
                "a": a,
                "pz": float(pz),
                "mpi": mpi,
                "L": L,
            })
        return rows

    @staticmethod
    def _single_ensemble_nonboot_rows():
        """The original eight-parameter route receives scalar x samples."""
        from pyqcd.renorm import hR_form

        x = np.array([0.25])
        true_par = np.array([0.37, -0.21, 0.04, -0.03,
                             0.12, 0.05, 0.08, -0.02])
        rows = []
        for pz in range(1, 9):
            a, mpi, L = 0.5, 0.20, 24
            value = hR_form((a, float(pz), mpi, L), true_par)
            rows.append({
                "x": x,
                "hR": np.array([value]),
                "a": a,
                "pz": float(pz),
                "mpi": mpi,
                "L": L,
            })
        return rows

    @staticmethod
    def _identifiable_nonboot_rows():
        """Twelve varied ensembles identify every original eight-parameter term."""
        from pyqcd.renorm import hR_form

        rng = np.random.default_rng(20260831)
        x = np.array([0.35])
        true_par = np.array([0.43, -0.31, 0.17, -0.06,
                             0.09, 0.12, -0.24, 0.07])
        rows = []
        ensembles = zip(
            rng.uniform(0.25, 0.75, 12),
            rng.uniform(1.1, 3.5, 12),
            rng.uniform(0.14, 0.32, 12),
            rng.integers(20, 64, 12),
        )
        for a, pz, mpi, L in ensembles:
            value = hR_form((a, pz, mpi, float(L)), true_par)
            rows.append({
                "x": x,
                "hR": np.array([value + 2.0e-4 * rng.normal()]),
                "a": a,
                "pz": pz,
                "mpi": mpi,
                "L": float(L),
            })
        return rows, x, true_par[0]

    @staticmethod
    def _identifiable_rows():
        """Two x points on a four-direction ensemble design with bootstrap noise."""
        from pyqcd.renorm import hR_form

        rng = np.random.default_rng(20260830)
        x = np.array([0.20, 0.45])
        parameters = (
            np.array([0.31, -0.14, 0.0, 0.0, 0.08, 0.0, 0.19, 0.0]),
            np.array([0.58, 0.22, 0.0, 0.0, -0.05, 0.0, -0.11, 0.0]),
        )
        ensembles = (
            (0.45, 1.2, 0.15, 24),
            (0.45, 1.8, 0.15, 24),
            (0.50, 1.5, 0.20, 28),
            (0.55, 2.0, 0.20, 32),
            (0.60, 1.2, 0.25, 24),
            (0.60, 2.2, 0.25, 32),
        )
        rows = []
        for a, pz, mpi, L in ensembles:
            centre = np.array([
                hR_form((a, pz, mpi, L), par) for par in parameters])
            rows.append({
                "x": x,
                "hR": centre[:, None] + 2.0e-3 * rng.standard_normal((2, 64)),
                "a": a,
                "pz": pz,
                "mpi": mpi,
                "L": L,
            })
        return rows, x, np.array([par[0] for par in parameters])

    def test_rank_deficient_single_ensemble_fails_before_fit(self):
        """Removing the design-rank gate would restore a pseudoinverse result."""
        from pyqcd.renorm import fit_hR_PDF_extrap_boot

        with self.assertRaisesRegex(
                ValueError, r"design rank=2, required rank=4"):
            fit_hR_PDF_extrap_boot(self._single_ensemble_rows())

    def test_rank_deficient_eight_parameter_route_fails_before_fit(self):
        """Calling lstsq first would hide the original route's bad design."""
        from pyqcd.renorm import fit_hR_PDF_extrap

        with self.assertRaisesRegex(
                ValueError,
                r"design rank=4, required rank=8; data dof=0 must be positive"):
            fit_hR_PDF_extrap(self._single_ensemble_nonboot_rows())

    def test_exactly_determined_design_fails_the_positive_dof_gate(self):
        """Four independent rows identify no residual data degree of freedom."""
        from pyqcd.renorm import fit_hR_PDF_extrap_boot

        rows, _, _ = self._identifiable_rows()
        with self.assertRaisesRegex(
                ValueError,
                r"design rank=4, required rank=4; data dof=0 must be positive"):
            fit_hR_PDF_extrap_boot(rows[:4])

    def test_identifiable_multi_ensemble_data_recovers_two_truths(self):
        """A full-rank four-parameter design preserves finite bootstrap bands."""
        from pyqcd.renorm import fit_hR_PDF_extrap_boot

        rows, x, expected_xg0 = self._identifiable_rows()
        actual_x, mean, std, samples = fit_hR_PDF_extrap_boot(
            rows, return_samples=True)

        np.testing.assert_allclose(actual_x, x, rtol=0.0, atol=0.0)
        self.assertTrue(np.all(np.isfinite(mean)))
        self.assertTrue(np.all(np.isfinite(std)))
        self.assertTrue(np.all(std > 0.0))
        self.assertTrue(np.all(np.isfinite(samples)))
        np.testing.assert_allclose(mean, expected_xg0, rtol=0.0, atol=0.02)

    def test_identifiable_eight_parameter_route_recovers_xg0(self):
        """A full-rank original-route fixture has a finite residual error band."""
        from pyqcd.renorm import fit_hR_PDF_extrap

        rows, x, expected_xg0 = self._identifiable_nonboot_rows()
        actual_x, mean, std = fit_hR_PDF_extrap(rows)

        np.testing.assert_allclose(actual_x, x, rtol=0.0, atol=0.0)
        self.assertTrue(np.isfinite(mean[0]))
        self.assertTrue(np.isfinite(std[0]) and std[0] > 0.0)
        self.assertAlmostEqual(mean[0], expected_xg0, delta=0.02)

    def test_nonfinite_observation_is_rejected_with_row_context(self):
        """NaN hR 不能穿过 lstsq 静默生成 NaN 外推带。"""
        from pyqcd.renorm import fit_hR_PDF_extrap

        rows, _, _ = self._identifiable_nonboot_rows()
        rows = copy.deepcopy(rows)
        rows[0]['hR'][0] = np.nan
        with self.assertRaisesRegex(ValueError, r'row 0.*hR|hR.*row 0'):
            fit_hR_PDF_extrap(rows)

    def test_boot_rejects_nonfinite_and_inconsistent_replica_axes(self):
        """所有 ensemble 必须使用有限且相同数量的 replica。"""
        from pyqcd.renorm import fit_hR_PDF_extrap_boot

        rows, _, _ = self._identifiable_rows()
        nonfinite = copy.deepcopy(rows)
        nonfinite[1]['hR'][0, 3] = np.nan
        with self.assertRaisesRegex(ValueError, r'row 1.*hR|hR.*row 1'):
            fit_hR_PDF_extrap_boot(nonfinite)

        mismatched = copy.deepcopy(rows)
        mismatched[2]['hR'] = mismatched[2]['hR'][:, :-1]
        with self.assertRaisesRegex(ValueError, 'replica'):
            fit_hR_PDF_extrap_boot(mismatched)

    def test_nonfinite_ensemble_coordinate_is_rejected(self):
        from pyqcd.renorm import fit_hR_PDF_extrap_boot

        rows, _, _ = self._identifiable_rows()
        rows = copy.deepcopy(rows)
        rows[3]['pz'] = np.inf
        with self.assertRaisesRegex(ValueError, r'row 3.*pz|pz.*row 3'):
            fit_hR_PDF_extrap_boot(rows)


if __name__ == "__main__":
    unittest.main(verbosity=2)
