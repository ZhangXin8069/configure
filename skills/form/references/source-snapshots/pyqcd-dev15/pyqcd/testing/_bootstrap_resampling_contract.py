"""Contract tests for axis-aware, chunked bootstrap resampling.

Run directly while developing the resampling implementation::

    python -m pyqcd.testing._bootstrap_resampling_contract
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings

import numpy as np

try:
    import torch
except ImportError:  # pragma: no cover - 由 skip 明确记录依赖缺失
    torch = None

try:
    import cupy as cp
except ImportError:  # pragma: no cover - 由 skip 明确记录依赖缺失
    cp = None
    _CUPY_AVAILABLE = False
else:
    try:
        _CUPY_AVAILABLE = cp.cuda.runtime.getDeviceCount() > 0
    except Exception:  # pragma: no cover - 由 skip 明确记录运行时缺失
        _CUPY_AVAILABLE = False


def _legacy_bootstrap(corr, n_sample, seed):
    """Reference for the pre-extension axis-0 bootstrap implementation."""
    rng = np.random.default_rng(seed=seed)
    n_conf = corr.shape[0]
    indices = rng.integers(0, n_conf, size=(n_sample, n_conf))
    return corr[indices].mean(1)


def _axis_bootstrap_reference(corr, axis, n_sample, seed):
    """Reference bootstrap with only the sample axis moved to the front."""
    sample_first = np.moveaxis(corr, axis, 0)
    rng = np.random.default_rng(seed=seed)
    n_conf = sample_first.shape[0]
    indices = rng.integers(0, n_conf, size=(n_sample, n_conf))
    return sample_first[indices].mean(1)


def _population_sem_cases():
    """Hand-derived population-SEM fixtures for real and complex data."""
    return (
        (
            "real",
            np.array([
                [1.0, 2.0],
                [3.0, 6.0],
                [5.0, 10.0],
                [7.0, 14.0],
            ], dtype=np.float64),
            np.array([np.sqrt(5.0), 2.0 * np.sqrt(5.0)]),
            np.array([np.sqrt(15.0), 2.0 * np.sqrt(15.0)]),
        ),
        (
            "complex",
            np.array([
                [1.0 + 1.0j, 2.0 + 2.0j],
                [1.0 - 1.0j, 2.0 - 2.0j],
                [-1.0 + 1.0j, -2.0 + 2.0j],
                [-1.0 - 1.0j, -2.0 - 2.0j],
            ], dtype=np.complex128),
            np.array([np.sqrt(2.0), 2.0 * np.sqrt(2.0)]),
            np.array([np.sqrt(6.0), 2.0 * np.sqrt(6.0)]),
        ),
    )


class _RecordingRng:
    """Small default_rng replacement that records integer batch shapes."""

    def __init__(self, backing):
        self._backing = backing
        self.shapes = []
        self.values = []

    def integers(self, *args, **kwargs):
        values = self._backing.integers(*args, **kwargs)
        self.shapes.append(tuple(values.shape))
        self.values.append(np.array(values, copy=True))
        return values


class BootstrapResamplingContractTests(unittest.TestCase):
    def _resample_with_new_api(self, *args, **kwargs):
        """Turn a missing keyword API into a useful RED assertion."""
        from pyqcd.analysis._disconnected import resample

        try:
            return resample(*args, **kwargs)
        except TypeError as error:
            self.fail(f"new resample API is unavailable: {error}")

    def test_new_axis_chunk_and_rng_keywords_are_supported(self):
        from pyqcd.analysis._disconnected import resample

        data = np.arange(2 * 3 * 4, dtype=np.float64).reshape(2, 3, 4)
        calls = (
            ("axis", lambda: resample(
                data, False, 4, 0, axis=1)),
            ("chunk_size", lambda: resample(
                data, False, 4, 0, chunk_size=2)),
            ("rng", lambda: resample(
                data, False, 4, rng=np.random.default_rng(1))),
        )
        for name, call in calls:
            with self.subTest(keyword=name):
                try:
                    result = call()
                except TypeError as error:
                    self.fail(f"new {name} API is unavailable: {error}")
                self.assertEqual(result.shape[0], 4)

    def test_axis_bootstrap_moves_resamples_to_axis_zero(self):
        from pyqcd.analysis._disconnected import resample

        data = np.arange(2 * 3 * 4, dtype=np.float64).reshape(2, 3, 4)
        expected = _axis_bootstrap_reference(data, axis=1, n_sample=5, seed=7)
        actual = self._resample_with_new_api(
            data, jackknife=False, Nsample=5, seed=7, axis=1, chunk_size=2)

        self.assertEqual(actual.shape, (5, 2, 4))
        np.testing.assert_array_equal(actual, expected)

    def test_negative_axis_matches_manual_four_dimensional_reference(self):
        from pyqcd.analysis._disconnected import resample

        data = np.arange(2 * 3 * 4 * 5, dtype=np.float64).reshape(
            2, 3, 4, 5)
        sample_first = np.moveaxis(data, -2, 0)
        rng = np.random.default_rng(29)
        indices = rng.integers(
            0, sample_first.shape[0], size=(6, sample_first.shape[0]))
        expected = sample_first[indices].mean(1)

        actual = resample(
            data, jackknife=False, Nsample=6, seed=29,
            axis=-2, chunk_size=2)

        self.assertEqual(actual.shape, (6, 2, 3, 5))
        np.testing.assert_array_equal(actual, expected)

    def test_default_and_positional_seed_bootstrap_match_legacy_exactly(self):
        from pyqcd.analysis._disconnected import resample

        data = np.linspace(-2.0, 3.0, 4 * 3).reshape(4, 3)
        expected_default = _legacy_bootstrap(data, n_sample=9, seed=0)
        actual_default = resample(data, False, 9)
        expected_positional = _legacy_bootstrap(data, n_sample=9, seed=19)
        actual_positional = resample(data, False, 9, 19)

        np.testing.assert_array_equal(actual_default, expected_default)
        np.testing.assert_array_equal(actual_positional, expected_positional)

    def test_legacy_jackknife_still_ignores_Nsample_and_seed(self):
        from pyqcd.analysis._disconnected import resample

        data = np.arange(4 * 3, dtype=np.float64).reshape(4, 3)
        expected = (data.shape[0] * data.mean(0) - data) / (data.shape[0] - 1)
        actual = resample(data, jackknife=True, Nsample=99, seed=123)

        np.testing.assert_array_equal(actual, expected)

    def test_legacy_jackknife_ignores_unused_Nsample_values(self):
        from pyqcd.analysis._disconnected import resample

        data = np.arange(4 * 2, dtype=np.float64).reshape(4, 2)
        expected = (data.shape[0] * data.mean(0) - data) / (data.shape[0] - 1)
        for unused_nsample in (None, 0, -1, 1.5):
            with self.subTest(Nsample=unused_nsample):
                actual = resample(
                    data, jackknife=True, Nsample=unused_nsample)
                np.testing.assert_array_equal(actual, expected)

    def test_all_chunk_sizes_have_the_same_seeded_sequence(self):
        from pyqcd.analysis._disconnected import resample

        data = np.arange(5 * 2, dtype=np.float64).reshape(5, 2)
        outputs = {}
        for chunk_size in (1, 2, 11, None):
            outputs[chunk_size] = self._resample_with_new_api(
                data, False, 11, seed=23, chunk_size=chunk_size)

        for chunk_size in (1, 2, 11):
            np.testing.assert_array_equal(outputs[chunk_size], outputs[None])

    def test_chunking_preserves_the_full_rng_index_sequence(self):
        from pyqcd.analysis import _disconnected as disconnected

        data = np.arange(5 * 2, dtype=np.float64).reshape(5, 2)
        recording_rng = _RecordingRng(np.random.default_rng(314))
        with patch.object(
                disconnected.np.random, "default_rng",
                return_value=recording_rng):
            actual = self._resample_with_new_api(
                data, False, 7, seed=314, chunk_size=2)

        expected_rng = np.random.default_rng(314)
        expected_indices = expected_rng.integers(
            0, data.shape[0], size=(7, data.shape[0]))
        expected = data[expected_indices].mean(1)

        np.testing.assert_array_equal(
            np.concatenate(recording_rng.values, axis=0), expected_indices)
        np.testing.assert_array_equal(actual, expected)

    def test_generator_is_consumed_directly_and_keeps_state_semantics(self):
        from pyqcd.analysis._disconnected import resample

        data = np.arange(4 * 3, dtype=np.float64).reshape(4, 3)
        expected_rng = np.random.default_rng(202)
        expected_indices = expected_rng.integers(
            0, data.shape[0], size=(7, data.shape[0]))
        expected = data[expected_indices].mean(1)

        actual_rng = np.random.default_rng(202)
        actual = self._resample_with_new_api(
            data, False, 7, rng=actual_rng, chunk_size=2)

        np.testing.assert_array_equal(actual, expected)
        np.testing.assert_array_equal(
            actual_rng.integers(0, 100, size=12),
            expected_rng.integers(0, 100, size=12),
        )

    def test_explicit_seed_cannot_be_combined_with_rng(self):
        from pyqcd.analysis._disconnected import resample

        for seed in (0, None, 19):
            with self.subTest(seed=seed):
                with self.assertRaises(ValueError):
                    resample(
                        np.ones((3, 2)), jackknife=False, Nsample=4,
                        seed=seed, rng=np.random.default_rng(17))

    def test_jackknife_rejects_bootstrap_chunk_size(self):
        from pyqcd.analysis._disconnected import resample

        with self.assertRaisesRegex(
                ValueError, "chunk_size is only valid for bootstrap"):
            resample(np.ones((3, 2)), jackknife=True, chunk_size=2)

    def test_jackknife_rejects_bootstrap_rng(self):
        from pyqcd.analysis._disconnected import resample

        with self.assertRaisesRegex(
                ValueError, "rng is only valid for bootstrap"):
            resample(
                np.ones((3, 2)), jackknife=True,
                rng=np.random.default_rng(19))

    def test_chunking_limits_each_index_tensor_without_rss_assumptions(self):
        from pyqcd.analysis import _disconnected as disconnected

        data = np.arange(4 * 2, dtype=np.float64).reshape(4, 2)
        backing = np.random.default_rng(303)
        recording_rng = _RecordingRng(backing)
        with patch.object(
                disconnected.np.random, "default_rng",
                return_value=recording_rng) as factory:
            actual = self._resample_with_new_api(
                data, False, 7, seed=31, chunk_size=2)

        factory.assert_called_once_with(seed=31)
        self.assertEqual(actual.shape, (7, 2))
        self.assertEqual(recording_rng.shapes, [(2, 4), (2, 4), (2, 4), (1, 4)])
        self.assertLessEqual(max(shape[0] for shape in recording_rng.shapes), 2)
        self.assertTrue(all(shape[1] == data.shape[0]
                            for shape in recording_rng.shapes))

    def test_complex_bootstrap_preserves_values_and_dtype(self):
        from pyqcd.analysis._disconnected import resample

        data = np.array([
            [1.0 + 2.0j, 3.0 - 4.0j],
            [-2.0 + 0.5j, 1.0 + 1.5j],
            [4.0 - 3.0j, -1.0 + 2.0j],
        ], dtype=np.complex64)
        expected = _legacy_bootstrap(data, n_sample=6, seed=41)
        actual = self._resample_with_new_api(
            data, False, 6, seed=41, chunk_size=2)

        self.assertEqual(actual.dtype, np.dtype(np.complex64))
        np.testing.assert_array_equal(actual, expected)

    @unittest.skipIf(torch is None, "PyTorch 不可用")
    def test_torch_bootstrap_preserves_backend_and_dtype(self):
        from pyqcd.analysis._disconnected import resample

        data = torch.arange(4 * 3, dtype=torch.float32).reshape(4, 3)
        expected_rng = np.random.default_rng(61)
        expected_indices = expected_rng.integers(
            0, data.shape[0], size=(5, data.shape[0]))
        expected = data.detach().cpu().numpy()[expected_indices].mean(1)

        actual = resample(data, jackknife=False, Nsample=5, seed=61)

        self.assertIsInstance(actual, torch.Tensor)
        self.assertEqual(actual.dtype, torch.float32)
        np.testing.assert_array_equal(actual.detach().cpu().numpy(), expected)

    @unittest.skipIf(torch is None, "PyTorch 不可用")
    def test_torch_tril_supports_compute_ratio_and_numpy_diagonal_semantics(self):
        """compute_ratio must use an exported torch tril with k/diagonal aliases."""
        from pyqcd.analysis._ratio2pt import SampleParams2pt, compute_ratio
        from pyqcd.tools import get_backend, set_backend

        conf_ids = [11, 12]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for offset, conf_id in enumerate(conf_ids, start=1):
                corr_dir = root / "ratio_full" / "momsmear2z" / str(conf_id)
                corr_dir.mkdir(parents=True)
                corr = np.full(
                    (4, 4), 1.0 + 0.25j * offset, dtype=np.complex128)
                np.save(
                    corr_dir
                    / ("twopt_slice_pp_Px0Py0Pz1_eginphase2_Cg5g4_"
                       f"nopol_ss_conf{conf_id}.npy"),
                    corr,
                )

                ope_dir = root / "ratio" / "zdir" / str(conf_id)
                ope_dir.mkdir(parents=True)
                for mu, nu, scale in ((0, 1, 1.0), (3, 0, 0.25),
                                      (3, 1, -0.5)):
                    ops = np.array([[1.0, 2.0, 3.0, 4.0]], dtype=np.complex128)
                    np.savez(
                        ope_dir / f"ops_mu{mu}_nu{nu}_dz1_conf{conf_id}.npz",
                        ops=scale * offset * ops,
                    )

            params = SampleParams2pt(
                conf_short="ratio", conf_name="ratio_full",
                conf_ids=conf_ids, Nt=4, Nx=1, Px=0, Py=0, Pz=1,
                Nsample=4, dt_max=3,
            )

            set_backend("numpy")
            numpy_ratio = compute_ratio(root, params, jack=False, verbose=False)

            try:
                set_backend("torch", device="cpu")
                xp = get_backend()
                torch_ratio = compute_ratio(
                    root, params, jack=False, verbose=False)
                np.testing.assert_allclose(
                    torch_ratio, numpy_ratio, rtol=0.0, atol=1.0e-12)
                self.assertIn("tril", xp.__all__)

                matrix = torch.arange(9, dtype=torch.float32).reshape(3, 3)
                for kwargs, diagonal in (({"k": 1}, 1),
                                         ({"diagonal": -1}, -1)):
                    with self.subTest(kwargs=kwargs):
                        actual = xp.tril(matrix, **kwargs)
                        expected = torch.as_tensor(
                            np.tril(matrix.numpy(), k=diagonal))
                        self.assertIsInstance(actual, torch.Tensor)
                        self.assertEqual(actual.dtype, matrix.dtype)
                        self.assertEqual(actual.device, matrix.device)
                        torch.testing.assert_close(actual, expected)

                if torch.cuda.is_available():
                    cuda_matrix = matrix.to("cuda:0")
                    cuda_actual = xp.tril(cuda_matrix, k=1)
                    self.assertEqual(cuda_actual.device, cuda_matrix.device)
                    self.assertEqual(cuda_actual.dtype, cuda_matrix.dtype)
                    torch.testing.assert_close(
                        cuda_actual.cpu(), torch.as_tensor(
                            np.tril(matrix.numpy(), k=1)))
            finally:
                set_backend("numpy")

    @unittest.skipIf(torch is None, "PyTorch 不可用")
    def test_bool_jackknife_matches_numpy_bernoulli_oracle_as_float(self):
        """NumPy and Torch bool observables are promoted before jackknife math."""
        from pyqcd.analysis._disconnected import resample

        data_np = np.array([
            [True, False, True],
            [False, False, True],
            [True, True, False],
            [False, True, False],
        ], dtype=np.bool_)
        data_float = data_np.astype(np.float64)
        expected = (
            data_float.shape[0] * data_float.mean(axis=0) - data_float
        ) / (data_float.shape[0] - 1)

        numpy_actual = resample(data_np, jackknife=True)
        torch_actual = resample(torch.as_tensor(data_np), jackknife=True)

        self.assertEqual(numpy_actual.dtype, np.dtype(np.float64))
        self.assertIsInstance(torch_actual, torch.Tensor)
        self.assertEqual(torch_actual.dtype, torch.float64)
        np.testing.assert_array_equal(numpy_actual, expected)
        np.testing.assert_array_equal(torch_actual.cpu().numpy(), expected)

    @unittest.skipIf(torch is None, "PyTorch 不可用")
    def test_torch_integer_resampling_uses_nan_capable_mean_dtype(self):
        from pyqcd.analysis._disconnected import resample

        data_np = np.arange(4 * 3, dtype=np.int64).reshape(4, 3)
        data = torch.as_tensor(data_np)

        expected_rng = np.random.default_rng(73)
        indices = expected_rng.integers(0, data_np.shape[0], size=(5, 4))
        expected_bootstrap = data_np[indices].mean(1)
        expected_jackknife = (4 * data_np.mean(0) - data_np) / 3

        actual_bootstrap = resample(
            data, jackknife=False, Nsample=5, seed=73, chunk_size=2)
        actual_jackknife = resample(data, jackknife=True)

        self.assertEqual(actual_bootstrap.dtype, torch.float64)
        self.assertEqual(actual_jackknife.dtype, torch.float64)
        np.testing.assert_array_equal(
            actual_bootstrap.cpu().numpy(), expected_bootstrap)
        np.testing.assert_array_equal(
            actual_jackknife.cpu().numpy(), expected_jackknife)

    @unittest.skipIf(torch is None, "PyTorch 不可用")
    def test_torch_sem_preserves_backend_and_dtype(self):
        from pyqcd.analysis._disconnected import sem

        data = torch.arange(4 * 3, dtype=torch.float32).reshape(4, 3)
        expected = np.std(data.numpy(), axis=0, ddof=0)

        actual = sem(data, jackknife=False)

        self.assertIsInstance(actual, torch.Tensor)
        self.assertEqual(actual.dtype, torch.float32)
        np.testing.assert_array_equal(actual.detach().cpu().numpy(),
                                      expected)

    @unittest.skipIf(torch is None, "PyTorch 不可用")
    def test_torch_sem_matches_numpy_population_contract(self):
        from pyqcd.analysis._disconnected import sem

        for name, data, expected_plain, expected_jackknife in (
                _population_sem_cases()):
            for jackknife, expected in (
                    (False, expected_plain), (True, expected_jackknife)):
                with self.subTest(kind=name, jackknife=jackknife):
                    numpy_actual = sem(data, jackknife=jackknife)
                    torch_actual = sem(
                        torch.as_tensor(data), jackknife=jackknife)

                    np.testing.assert_allclose(
                        numpy_actual, expected, rtol=0.0, atol=1.0e-14)
                    self.assertIsInstance(torch_actual, torch.Tensor)
                    self.assertEqual(torch_actual.dtype, torch.float64)
                    np.testing.assert_allclose(
                        torch_actual.cpu().numpy(), expected,
                        rtol=0.0, atol=1.0e-14)

    @unittest.skipUnless(_CUPY_AVAILABLE, "CuPy CUDA 不可用")
    def test_cupy_sem_preserves_backend_and_dtype(self):
        from pyqcd.analysis._disconnected import sem

        data = cp.arange(4 * 3, dtype=cp.float32).reshape(4, 3)
        expected = data.std(0)

        actual = sem(data, jackknife=False)

        self.assertIsInstance(actual, cp.ndarray)
        self.assertEqual(actual.dtype, cp.float32)
        np.testing.assert_array_equal(actual.get(), expected.get())

    @unittest.skipUnless(_CUPY_AVAILABLE, "CuPy CUDA 不可用")
    def test_cupy_sem_matches_numpy_population_contract(self):
        from pyqcd.analysis._disconnected import sem

        for name, data, expected_plain, expected_jackknife in (
                _population_sem_cases()):
            for jackknife, expected in (
                    (False, expected_plain), (True, expected_jackknife)):
                with self.subTest(kind=name, jackknife=jackknife):
                    numpy_actual = sem(data, jackknife=jackknife)
                    cupy_actual = sem(
                        cp.asarray(data), jackknife=jackknife)

                    np.testing.assert_allclose(
                        numpy_actual, expected, rtol=0.0, atol=1.0e-14)
                    self.assertIsInstance(cupy_actual, cp.ndarray)
                    self.assertEqual(cupy_actual.dtype, cp.float64)
                    np.testing.assert_allclose(
                        cupy_actual.get(), expected,
                        rtol=0.0, atol=1.0e-14)

    @unittest.skipUnless(_CUPY_AVAILABLE, "CuPy CUDA 不可用")
    def test_cupy_bootstrap_preserves_backend_and_dtype(self):
        from pyqcd.analysis._disconnected import resample

        data = cp.arange(4 * 3, dtype=cp.float32).reshape(4, 3)
        expected_rng = np.random.default_rng(67)
        expected_indices = expected_rng.integers(
            0, data.shape[0], size=(5, data.shape[0]))
        expected = data.get()[expected_indices].mean(1)

        actual = resample(data, jackknife=False, Nsample=5, seed=67)

        self.assertIsInstance(actual, cp.ndarray)
        self.assertEqual(actual.dtype, cp.float32)
        np.testing.assert_array_equal(actual.get(), expected)

    def test_single_configuration_bootstrap_is_defined(self):
        from pyqcd.analysis._disconnected import resample

        data = np.array([[1.0 + 2.0j, -3.0 + 4.0j]], dtype=np.complex128)
        actual = self._resample_with_new_api(
            data, False, 5, seed=53, chunk_size=1)

        self.assertEqual(actual.shape, (5, 2))
        np.testing.assert_array_equal(actual, np.repeat(data, 5, axis=0))

    def test_default_jackknife_remains_bitwise_compatible(self):
        from pyqcd.analysis._disconnected import resample

        data = np.array([
            [1.0 + 0.5j, 2.0 - 1.0j],
            [3.0 - 2.0j, -1.0 + 4.0j],
            [0.5 + 3.0j, 5.0 + 2.0j],
        ], dtype=np.complex128)
        expected = (data.shape[0] * data.mean(0) - data) / (data.shape[0] - 1)
        actual = resample(data)

        np.testing.assert_array_equal(actual, expected)

    def test_nonzero_axis_jackknife_also_returns_resample_axis_zero(self):
        from pyqcd.analysis._disconnected import resample

        data = np.arange(2 * 3 * 4, dtype=np.float64).reshape(2, 3, 4)
        sample_first = np.moveaxis(data, 1, 0)
        expected = (
            sample_first.shape[0] * sample_first.mean(0) - sample_first
        ) / (sample_first.shape[0] - 1)
        actual = self._resample_with_new_api(data, axis=1)

        self.assertEqual(actual.shape, (3, 2, 4))
        np.testing.assert_array_equal(actual, expected)

    def test_single_configuration_jackknife_keeps_nan_contract(self):
        from pyqcd.analysis._disconnected import resample

        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            actual = resample(np.array([[1.0, 2.0]]), jackknife=True)

        self.assertEqual(actual.shape, (1, 2))
        self.assertTrue(np.isnan(actual).all())

    def test_single_configuration_jackknife_preserves_mean_dtype(self):
        from pyqcd.analysis._disconnected import resample

        for dtype in (np.float32, np.complex64):
            with self.subTest(dtype=dtype):
                data = np.ones((1, 2), dtype=dtype)
                actual = resample(data, jackknife=True)

                self.assertEqual(actual.dtype, np.dtype(dtype))
                self.assertTrue(np.isnan(actual).all())

    def test_single_configuration_integer_jackknife_promotes_for_nan(self):
        from pyqcd.analysis._disconnected import resample

        data = np.array([[1, 2]], dtype=np.int64)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            actual = resample(data, jackknife=True)

        self.assertEqual(actual.dtype, np.dtype(np.float64))
        self.assertTrue(np.isnan(actual).all())

    @unittest.skipIf(torch is None, "PyTorch 不可用")
    def test_single_configuration_torch_integer_jackknife_promotes_for_nan(self):
        from pyqcd.analysis._disconnected import resample

        data = torch.tensor([[1, 2]], dtype=torch.int64)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            actual = resample(data, jackknife=True)

        self.assertIsInstance(actual, torch.Tensor)
        self.assertEqual(actual.dtype, torch.float64)
        self.assertTrue(torch.isnan(actual).all().item())

    def test_single_sample_sem_preserves_numpy_std_dtype(self):
        from pyqcd.analysis._disconnected import sem

        expected_dtypes = (
            (np.float32, np.float32),
            (np.complex64, np.float32),
        )
        for input_dtype, expected_dtype in expected_dtypes:
            with self.subTest(dtype=input_dtype):
                actual = sem(np.ones((1, 2), dtype=input_dtype))

                self.assertEqual(actual.dtype, np.dtype(expected_dtype))
                self.assertTrue(np.isnan(actual).all())

    def test_rejects_empty_sample_axis(self):
        from pyqcd.analysis._disconnected import resample

        try:
            resample(np.empty((2, 0, 3)), False, 2, axis=1)
        except ValueError as error:
            self.assertIn("at least one configuration", str(error))
        except Exception as error:
            self.fail(f"empty sample axis raised the wrong exception: {error!r}")
        else:
            self.fail("empty sample axis was accepted")

    def test_rejects_scalar_input(self):
        from pyqcd.analysis._disconnected import resample

        try:
            resample(np.array(1.0), False, 2)
        except ValueError as error:
            self.assertIn("sample axis", str(error))
        except Exception as error:
            self.fail(f"scalar input raised the wrong exception: {error!r}")
        else:
            self.fail("scalar input was accepted")

    def test_rejects_missing_or_nonpositive_bootstrap_count(self):
        from pyqcd.analysis._disconnected import resample

        for n_sample in (None, 0, -1):
            with self.subTest(Nsample=n_sample):
                with self.assertRaises(ValueError):
                    resample(np.ones((3, 2)), False, n_sample)

    def test_rejects_noninteger_or_out_of_range_axis(self):
        from pyqcd.analysis._disconnected import resample

        for axis in (3, -4, 0.5, True):
            with self.subTest(axis=axis):
                with self.assertRaises((TypeError, ValueError)):
                    resample(np.ones((2, 3, 4)), False, 2, axis=axis)

    def test_rejects_nonpositive_or_noninteger_chunk_size(self):
        from pyqcd.analysis._disconnected import resample

        for chunk_size in (0, -1, 1.5, True):
            with self.subTest(chunk_size=chunk_size):
                with self.assertRaises((TypeError, ValueError)):
                    resample(
                        np.ones((3, 2)), False, 2, chunk_size=chunk_size)

    def test_rejects_non_generator_rng(self):
        from pyqcd.analysis._disconnected import resample

        invalid_rngs = (np.random.RandomState(0), 1, object())
        for rng in invalid_rngs:
            with self.subTest(rng_type=type(rng).__name__):
                with self.assertRaises(TypeError):
                    resample(np.ones((3, 2)), False, 2, rng=rng)


if __name__ == "__main__":
    unittest.main()
