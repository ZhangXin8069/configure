"""Public regression contracts for the scalar/multi-b invariant amplitude."""
from __future__ import annotations

import unittest

import numpy as np

from pyqcd.renorm import invariant_amplitude


class InvariantAmplitudeContract(unittest.TestCase):
    """Keep legacy 1-D output while supporting an explicit b_perp axis."""

    def test_one_dimensional_input_keeps_legacy_shape(self):
        matrix = np.array([1.0 + 0.2j, 0.8 - 0.1j, 0.4 + 0.05j, 0.2])
        result = invariant_amplitude(
            matrix, np.array([0.0, 0.37]), np.array([0.1]))

        self.assertEqual(result.shape, (2,))
        self.assertTrue(np.isfinite(result).all())

    def test_two_dimensional_input_returns_x_by_b_shape(self):
        matrix = np.array([1.0 + 0.2j, 0.8 - 0.1j, 0.4 + 0.05j, 0.2])
        matrix_2d = np.column_stack((matrix, 2.0 * matrix))
        x_grid = np.array([0.0, 0.37])

        scalar = invariant_amplitude(matrix, x_grid, np.array([0.1]))
        result = invariant_amplitude(
            matrix_2d, x_grid, np.array([0.1, 0.2]))

        self.assertEqual(result.shape, (2, 2))
        np.testing.assert_allclose(result[:, 0], scalar)
        np.testing.assert_allclose(result[:, 1], 2.0 * scalar)

    def test_single_b_and_zero_x_boundary_keeps_two_axes(self):
        matrix = np.ones((4, 1), dtype=complex)
        result = invariant_amplitude(
            matrix, np.array([0.0]), np.array([0.0]))

        self.assertEqual(result.shape, (1, 1))
        self.assertTrue(np.isfinite(result).all())


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        InvariantAmplitudeContract)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
