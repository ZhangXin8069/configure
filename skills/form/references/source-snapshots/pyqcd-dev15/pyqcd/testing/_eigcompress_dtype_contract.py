"""eigcompress 随机路径的 dtype、容差与可复现性契约。"""

import unittest

import numpy as np

from pyqcd.tools import set_backend, set_precision
from pyqcd.vertex._eigcompress import (
    compress_matrix_V3,
    compress_matrix_V4,
    create_noise,
)

try:
    import torch
except ImportError:  # pragma: no cover - 由 skip 明确记录缺失依赖
    torch = None


class EigcompressDtypeContract(unittest.TestCase):
    """complex64 不得被随机数组升精度，且合法舍入误差不得误报。"""

    def setUp(self):
        set_backend('numpy')
        shape = (16, 2, 2, 2, 2)
        self.vec64 = np.eye(16, dtype=np.complex64).reshape(shape)
        self.vec128 = np.eye(16, dtype=np.complex128).reshape(shape)
        self.c64_tol = max(1e-8, 16 * np.finfo(np.float32).eps)

    def tearDown(self):
        set_backend('numpy')
        if torch is not None:
            set_precision('complex128')

    def assertComplex64Orthonormal(self, vectors):
        flat = np.asarray(vectors).reshape(vectors.shape[0], -1)
        gram = flat @ flat.conj().T
        np.testing.assert_allclose(
            gram,
            np.eye(flat.shape[0], dtype=gram.dtype),
            rtol=0.0,
            atol=self.c64_tol,
        )

    def assertRuns(self, label, producer):
        try:
            return producer()
        except Exception as exc:
            self.fail(f'{label} 不应抛出 {type(exc).__name__}: {exc}')

    def test_numpy_create_noise_preserves_complex64_and_seed(self):
        first = create_noise(self.vec64[:4], 3, seed=5)
        second = create_noise(self.vec64[:4], 3, seed=5)

        self.assertEqual(first.dtype, np.dtype(np.complex64))
        np.testing.assert_array_equal(first, second)
        self.assertComplex64Orthonormal(first)

    def test_numpy_v3_accepts_complex64_roundoff(self):
        result = self.assertRuns(
            'NumPy V3 complex64',
            lambda: compress_matrix_V3(
                self.vec64, 4, 2, Ctype='I', seed=3,
            ),
        )

        self.assertEqual(result.dtype, np.dtype(np.complex64))
        self.assertComplex64Orthonormal(result)

    def test_numpy_v4_accepts_complex64_roundoff(self):
        result = self.assertRuns(
            'NumPy V4 complex64',
            lambda: compress_matrix_V4(
                self.vec64, 4, 2, Ctype='B', seed=3,
            ),
        )

        self.assertEqual(result.dtype, np.dtype(np.complex64))
        self.assertComplex64Orthonormal(result)

    @unittest.skipIf(torch is None, 'PyTorch 不可用')
    def test_torch_create_noise_runs_in_complex64(self):
        expected = create_noise(self.vec64[:4], 3, seed=5)
        set_backend('torch', device='cpu')
        set_precision('complex64')

        first = self.assertRuns(
            'Torch create_noise complex64',
            lambda: create_noise(self.vec64[:4], 3, seed=5),
        )
        second = self.assertRuns(
            'Torch create_noise complex64 repeat',
            lambda: create_noise(self.vec64[:4], 3, seed=5),
        )

        self.assertEqual(first.dtype, torch.complex64)
        np.testing.assert_array_equal(first.get(), second.get())
        np.testing.assert_allclose(
            first.get(), expected, rtol=0.0, atol=self.c64_tol,
        )

    @unittest.skipIf(torch is None, 'PyTorch 不可用')
    def test_torch_v3_runs_in_complex64(self):
        expected = compress_matrix_V3(
            self.vec64, 4, 2, Ctype='I', seed=3, check=False,
        )
        set_backend('torch', device='cpu')
        set_precision('complex64')

        first = self.assertRuns(
            'Torch V3 complex64',
            lambda: compress_matrix_V3(
                self.vec64, 4, 2, Ctype='I', seed=3,
            ),
        )
        second = self.assertRuns(
            'Torch V3 complex64 repeat',
            lambda: compress_matrix_V3(
                self.vec64, 4, 2, Ctype='I', seed=3,
            ),
        )

        self.assertEqual(first.dtype, torch.complex64)
        np.testing.assert_array_equal(first.get(), second.get())
        np.testing.assert_allclose(
            first.get(), expected, rtol=0.0, atol=self.c64_tol,
        )

    @unittest.skipIf(torch is None, 'PyTorch 不可用')
    def test_torch_v4_runs_in_complex64(self):
        expected = compress_matrix_V4(
            self.vec64, 4, 2, Ctype='B', seed=3, check=False,
        )
        set_backend('torch', device='cpu')
        set_precision('complex64')

        first = self.assertRuns(
            'Torch V4 complex64',
            lambda: compress_matrix_V4(
                self.vec64, 4, 2, Ctype='B', seed=3,
            ),
        )
        second = self.assertRuns(
            'Torch V4 complex64 repeat',
            lambda: compress_matrix_V4(
                self.vec64, 4, 2, Ctype='B', seed=3,
            ),
        )

        self.assertEqual(first.dtype, torch.complex64)
        np.testing.assert_array_equal(first.get(), second.get())
        np.testing.assert_allclose(
            first.get(), expected, rtol=0.0, atol=self.c64_tol,
        )

    def test_numpy_complex128_seeded_semantics_are_unchanged(self):
        producers = (
            lambda: create_noise(self.vec128[:4], 3, seed=5),
            lambda: compress_matrix_V3(
                self.vec128, 4, 2, Ctype='I', seed=3,
            ),
            lambda: compress_matrix_V4(
                self.vec128, 4, 2, Ctype='B', seed=3,
            ),
        )

        for producer in producers:
            with self.subTest(producer=producer):
                first = producer()
                second = producer()
                self.assertEqual(first.dtype, np.dtype(np.complex128))
                np.testing.assert_array_equal(first, second)


if __name__ == '__main__':
    unittest.main()
