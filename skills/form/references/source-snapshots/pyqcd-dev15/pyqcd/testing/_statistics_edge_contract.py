"""Regression contracts for statistical boundary conditions.

This module is intentionally not registered in the central test runner.  Run it
directly while the statistics-boundary patch is developed and reviewed.
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings

import numpy as np


class HermitianStatisticsContractTests(unittest.TestCase):
    def test_complex_samples_covariance_orientation_matches_hermitian_chi2(self):
        from pyqcd.analysis._disconnected import cov_mat
        from pyqcd.analysis._fitter import calc_chi2

        direction = np.array([1.0, 1.0j])
        samples = np.stack([direction, -direction])
        cov, _ = cov_mat(samples, jackknife=False)

        expected = np.array([
            [1.0, -1.0j],
            [1.0j, 1.0],
        ])
        np.testing.assert_allclose(cov, expected, rtol=0.0, atol=1.0e-15)
        for svdcut in (-1.0e-6, 1.0e-6):
            with self.subTest(svdcut=svdcut):
                self.assertAlmostEqual(
                    calc_chi2(
                        direction,
                        np.zeros_like(direction),
                        cov,
                        svdcut=svdcut,
                    ),
                    1.0,
                    places=12,
                )

    def test_tiny_covariance_uses_relative_hermitian_tolerance(self):
        from pyqcd.analysis._fitter import covariance_sample_rank

        # The antisymmetric part is 10% of the covariance scale.  An absolute
        # O(eps) tolerance would incorrectly accept it only because all entries
        # happen to be much smaller than one.
        cov = np.array([
            [1.0e-30, 2.0e-31],
            [1.0e-31, 1.0e-30],
        ])
        with self.assertRaisesRegex(ValueError, "Hermitian"):
            covariance_sample_rank(cov)

    def test_zero_variance_rejects_every_nonzero_covariance_coupling(self):
        from pyqcd.analysis._disconnected import _repair_covariance_roundoff
        from pyqcd.analysis._fitter import covariance_sample_rank

        # For a PSD covariance, C_ii=0 implies C_ij=0 for every j.  Keep the
        # fixture tiny so an absolute scale floor cannot hide the violation.
        cov = np.array([
            [0.0, 1.0e-31],
            [1.0e-31, 1.0e-30],
        ])
        validators = (
            covariance_sample_rank,
            _repair_covariance_roundoff,
        )
        for validator in validators:
            with self.subTest(validator=validator.__name__):
                with self.assertRaisesRegex(ValueError, "positive semidefinite"):
                    validator(cov)

    def test_complex_hermitian_covariance_keeps_imaginary_rank_information(self):
        from pyqcd.analysis._fitter import (
            covariance_effective_rank,
            covariance_sample_rank,
        )

        # Eigenvalues are exactly 0 and 2.  Dropping the imaginary
        # off-diagonal entries incorrectly changes the sample rank to two.
        cov = np.array([[1.0, 1.0j], [-1.0j, 1.0]])
        self.assertEqual(covariance_sample_rank(cov), 1)
        self.assertEqual(covariance_effective_rank(cov, svdcut=1.0e-6), 2)
        self.assertEqual(covariance_effective_rank(cov, svdcut=-1.0e-6), 1)

    def test_zero_svdcut_keeps_original_sample_rank(self):
        from pyqcd.analysis._disconnected import cov_mat
        from pyqcd.analysis._fitter import (
            covariance_effective_rank,
            covariance_sample_rank,
        )

        direction = np.array([1.0, 1.0j])
        samples = np.stack([direction, -direction])
        cov, _ = cov_mat(samples, jackknife=False)

        self.assertEqual(covariance_sample_rank(cov), 1)
        self.assertEqual(covariance_effective_rank(cov, svdcut=0.0), 1)

    @staticmethod
    def _rank_two_sample_covariance():
        from pyqcd.analysis._disconnected import cov_mat

        samples = np.array([
            [1.0, 0.0, 1.0],
            [-1.0, 0.0, -1.0],
            [0.0, 1.0, 1.0],
            [0.0, -1.0, -1.0],
        ])
        return cov_mat(samples, jackknife=False)[0]

    def test_negative_svdcut_dof_uses_retained_covariance_rank(self):
        from pyqcd.analysis._fitter import calc_chi2_dof

        cov = self._rank_two_sample_covariance()
        data = np.array([1.0, 0.0, 1.0])
        chi2_dof, chi2, dof = calc_chi2_dof(
            data,
            np.zeros_like(data),
            cov,
            n_params=1,
            svdcut=-1.0e-6,
        )

        self.assertEqual(dof, 1)
        self.assertAlmostEqual(chi2_dof, chi2, places=14)

    def test_nonpositive_effective_dof_is_rejected(self):
        from pyqcd.analysis._fitter import calc_chi2_dof

        cov = self._rank_two_sample_covariance()
        data = np.array([1.0, 0.0, 1.0])
        with self.assertRaisesRegex(ValueError, "positive.*dof"):
            calc_chi2_dof(
                data,
                np.zeros_like(data),
                cov,
                n_params=2,
                svdcut=-1.0e-6,
            )

    def test_pure_imaginary_residual_has_nonzero_hermitian_chi2(self):
        from pyqcd.analysis._fitter import calc_chi2

        residual = np.array([1.0j, 0.0j])
        cov = np.eye(2, dtype=np.complex128)
        self.assertAlmostEqual(
            calc_chi2(residual, np.zeros(2, dtype=np.complex128), cov),
            1.0,
            places=14,
        )

    def test_materially_non_psd_covariance_is_rejected(self):
        from pyqcd.analysis._fitter import covariance_sample_rank

        with self.assertRaisesRegex(ValueError, "positive semidefinite"):
            covariance_sample_rank(np.array([[1.0, 2.0], [2.0, 1.0]]))


class SingleConfigurationContractTests(unittest.TestCase):
    @staticmethod
    def _single_configuration_inputs(nt=6, nz=1, nb=None):
        t = np.arange(nt, dtype=np.float64)
        corr = np.exp(-0.25 * t) + 0.01
        corr_2pt = {
            11: {
                "corr_pp_P2": corr,
                "corr_pion_P2": 0.8 * corr,
                "corr_pp_P200": corr,
            }
        }
        values = np.sin(0.4 * t)[None, :]
        if nb is None:
            ope = {11: {"combined": values}}
        else:
            ope = {11: {"tmd": values[:, None, :]}}
        return corr_2pt, ope

    @staticmethod
    def _write_single_configuration_files(root: Path):
        nt = 6
        conf_id = 11
        conf_name = "single_full"
        conf_short = "single"
        t = np.arange(nt, dtype=np.float64)
        corr_t = np.exp(-0.25 * t) + 0.01
        corr = np.empty((nt, nt), dtype=np.complex128)
        for source in range(nt):
            corr[:, source] = np.roll(corr_t, source)

        corr_dir = root / conf_name / "momsmear2z" / str(conf_id)
        corr_dir.mkdir(parents=True)
        np.save(
            corr_dir
            / "twopt_slice_pp_Px0Py0Pz2_eginphase2_Cg5g4_nopol_ss_conf11.npy",
            corr,
        )

        ope_dir = root / conf_short / "zdir" / str(conf_id)
        ope_dir.mkdir(parents=True)
        tau = np.arange(nt, dtype=np.float64)
        for mu, nu, phase in ((0, 1, 0.0), (3, 0, 0.2), (3, 1, 0.4)):
            ops = np.sin(0.3 * tau + phase)[None, :]
            np.savez(
                ope_dir / f"ops_mu{mu}_nu{nu}_dz1_conf{conf_id}.npz",
                ops=ops,
            )
        return conf_short, conf_name, conf_id

    def test_delete_one_jackknife_single_configuration_returns_nan(self):
        from pyqcd.analysis._disconnected import resample

        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            sample = resample(np.array([[1.0, 2.0]]), jackknife=True)
        self.assertEqual(sample.shape, (1, 2))
        self.assertTrue(np.isnan(sample).all())

    def test_sem_rejects_empty_sample_axis(self):
        from pyqcd.analysis._disconnected import sem

        with self.assertRaisesRegex(ValueError, "at least one sample"):
            sem(np.empty((0, 2, 3)), jackknife=True)

    def test_sem_single_sample_returns_same_output_shape_nan(self):
        from pyqcd.analysis._disconnected import sem

        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            error = sem(np.ones((1, 2, 3)), jackknife=True)
        self.assertEqual(error.shape, (2, 3))
        self.assertTrue(np.isnan(error).all())

    def test_ratio2pt_single_configuration_persists_unidentifiable_status(self):
        from pyqcd.analysis._fitter import FitParams
        from pyqcd.analysis._ratio2pt import (
            PlotParamsRatio,
            SampleParams2pt,
            run_ratio2pt,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            conf_short, conf_name, conf_id = self._write_single_configuration_files(root)
            params = SampleParams2pt(
                conf_short=conf_short,
                conf_name=conf_name,
                conf_ids=[conf_id],
                Nt=6,
                Nx=1,
                Px=0,
                Py=0,
                Pz=2,
                Nsample=1,
                dt_max=5,
            )
            fit_params = FitParams(
                p0={"c0": 0.2, "c1": 0.1, "dE": 0.5},
                dt_start=2,
                dt_end=4,
                nex=1,
                svdcut=1.0e-6,
            )
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                result = run_ratio2pt(
                    root,
                    root / "ratio_out",
                    params,
                    [fit_params],
                    PlotParamsRatio(z_list=[0], dt_list=[2, 3, 4]),
                    jack=True,
                    parts=(1, 2),
                    verbose=False,
                )
            fit_result = next(iter(result["fit_results"].values()))
            report = next((root / "ratio_out").rglob("1_fit_report.txt")).read_text()

        self.assertEqual(caught, [])
        self.assertTrue(np.isnan(result["ratio"]).all())
        for name in ("c0", "c1", "dE", "chi2"):
            self.assertTrue(np.isnan(fit_result[name]).all())
        self.assertEqual(
            str(fit_result["fit_status"]), "statistically_unidentifiable")
        self.assertIn("statistically_unidentifiable", report)
        self.assertIn("sample covariance rank = 0", report)

    def test_energy_single_configuration_persists_unidentifiable_status(self):
        from pyqcd.analysis._proton_energy import EnergyParams, run_energy

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            conf_short, conf_name, conf_id = self._write_single_configuration_files(root)
            params = EnergyParams(
                conf_short=conf_short,
                conf_name=conf_name,
                conf_ids=[conf_id],
                Nt=6,
                Nx=1,
                Px=0,
                Py=0,
                Pz=2,
                Nsample=1,
                dt_max=5,
                dt_start=1,
                dt_end=4,
            )
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                result = run_energy(
                    root,
                    root / "energy_out",
                    params,
                    jack=True,
                    parts=(1, 2),
                    verbose=False,
                )
            report = next((root / "energy_out").rglob("2_fit_report.txt")).read_text()

        self.assertEqual(caught, [])
        self.assertTrue(np.isnan(result["corr2"]).all())
        for name in ("c0", "c1", "E0", "dE", "chi2"):
            self.assertTrue(np.isnan(result["fit"][name]).all())
        self.assertEqual(
            str(result["fit"]["fit_status"]),
            "statistically_unidentifiable",
        )
        self.assertIn("statistically_unidentifiable", report)
        self.assertIn("sample covariance rank = 0", report)

    def test_disconnected_single_configuration_persists_unidentifiable_status(self):
        from pyqcd.analysis._disconnected import run_disconnected_ratio

        corr_2pt, ope = self._single_configuration_inputs()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_disconnected_ratio(
                corr_2pt,
                ope,
                [11],
                tmpdir,
                logger=lambda _message: None,
                NT=6,
                NX=1,
                dt_max=5,
                dt_start=2,
                dt_end=4,
                cut=2,
            )
            report = (
                Path(tmpdir) / "analysis" / "disconnected" / "1_fit_report.txt"
            ).read_text()

        for channel in ("proton", "pion"):
            self.assertTrue(np.isnan(result[channel]["ratio"]).all())
            for name in ("c0", "c1", "dE", "chi2"):
                self.assertTrue(np.isnan(result[channel][name]).all())
        self.assertIn("statistically_unidentifiable", report)
        self.assertIn("sample covariance rank = 0", report)

    def test_tmd_single_configuration_saves_nan_plateau_and_fit_status(self):
        from pyqcd.analysis._tmd_ratio import run_disconnected_tmd_ratio

        corr_2pt, ope = self._single_configuration_inputs(nb=1)
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_disconnected_tmd_ratio(
                corr_2pt,
                ope,
                [11],
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
            saved = np.load(out_dir / "0_fit_data_P200.npz")
            report = (out_dir / "1_fit_report_P200.txt").read_text()
            plateau = np.load(out_dir / "c0_plateau_P200.npy")

        for name in ("c0", "c1", "dE", "chi2", "c0_plateau"):
            self.assertTrue(np.isnan(result[name]).all())
        self.assertTrue(np.isnan(plateau).all())
        self.assertEqual(str(saved["fit_status"]), "statistically_unidentifiable")
        self.assertEqual(int(saved["effective_rank"]), 0)
        self.assertEqual(int(saved["sample_rank"]), 0)
        self.assertIn("Nconf=1", str(saved["fit_reason"]))
        self.assertIn("statistically_unidentifiable", report)
        self.assertIn("effective covariance rank = 0", report)
        self.assertIn("sample covariance rank = 0", report)
        self.assertIn("Nconf=1", report)

    def test_test9_extended_single_configuration_skips_direct_energy_fit(self):
        from pyqcd.analysis._test9_extended import generate_test6_style_plots

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data_dir = root / "test9" / "data" / "conf11"
            data_dir.mkdir(parents=True)
            corr = np.exp(-0.25 * np.arange(72, dtype=np.float64)) + 0.01
            np.save(data_dir / "corr_pp_P200_11.npy", corr)

            generate_test6_style_plots(
                root / "test9",
                root / "out",
                [11],
                ["P200"],
                logger=lambda _message: None,
            )
            out_dir = root / "out" / "1_result" / "L24x72" / "Pz2"
            saved = np.load(out_dir / "1_fit_data.npz")
            report = (out_dir / "2_fit_report.txt").read_text()

        self.assertEqual(str(saved["fit_status"]), "statistically_unidentifiable")
        self.assertEqual(int(saved["effective_rank"]), 0)
        self.assertEqual(int(saved["sample_rank"]), 0)
        self.assertIn("Nconf=1", str(saved["fit_reason"]))
        for direction in ("x", "y", "z", "ave"):
            for name in ("c0", "c1", "E0", "dE", "chi2"):
                self.assertTrue(np.isnan(saved[f"{name}_{direction}"]).all())
        self.assertIn("statistically_unidentifiable", report)
        self.assertIn("effective covariance rank = 0", report)
        self.assertIn("sample covariance rank = 0", report)
        self.assertIn("Nconf=1", report)

    def test_test9_extended_two_to_four_configs_skip_direct_fit(self):
        from pyqcd.analysis._test9_extended import generate_test6_style_plots

        for nconf in range(2, 5):
            with self.subTest(nconf=nconf), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                conf_ids = list(range(11, 11 + nconf))
                t = np.arange(72, dtype=np.float64)
                for offset, conf_id in enumerate(conf_ids):
                    data_dir = root / "test9" / "data" / f"conf{conf_id}"
                    data_dir.mkdir(parents=True)
                    corr = (
                        np.exp(-(0.25 + 0.003 * offset) * t)
                        * (1.0 + 0.001 * offset * np.cos(0.3 * t))
                        + 0.01
                    )
                    np.save(data_dir / f"corr_pp_P200_{conf_id}.npy", corr)

                with patch(
                        "lsqfit.nonlinear_fit",
                        side_effect=AssertionError(
                            "Nconf=2..4 must fail the rank gate before lsqfit")):
                    generate_test6_style_plots(
                        root / "test9",
                        root / "out",
                        conf_ids,
                        ["P200"],
                        logger=lambda _message: None,
                    )

                out_dir = root / "out" / "1_result" / "L24x72" / "Pz2"
                saved = np.load(out_dir / "1_fit_data.npz")
                report = (out_dir / "2_fit_report.txt").read_text()

                self.assertEqual(
                    str(saved["fit_status"]),
                    "statistically_unidentifiable",
                )
                for direction in ("x", "y", "z", "ave"):
                    self.assertEqual(
                        str(saved[f"fit_status_{direction}"]),
                        "statistically_unidentifiable",
                    )
                    self.assertLess(int(saved[f"sample_rank_{direction}"]), 4)
                    for name in ("c0", "c1", "E0", "dE", "chi2"):
                        self.assertTrue(
                            np.isnan(saved[f"{name}_{direction}"]).all())
                self.assertIn("statistically_unidentifiable", report)
                self.assertRegex(report, rf"Nconf\s*:\s*{nconf}")


class PlateauContractTests(unittest.TestCase):
    def test_plateau_empty_window_returns_nan(self):
        from pyqcd.analysis._tmd_ratio import plateau_c0

        ratio = np.ones((3, 4, 4, 1, 1), dtype=np.float64)
        result = plateau_c0(
            ratio,
            dt_max=4,
            dt_start=7,
            dt_end=10,
            cut=2,
        )
        self.assertEqual(result.shape, (3, 1, 1))
        self.assertTrue(np.isnan(result).all())

    def test_plateau_zero_fluctuation_channel_is_nan(self):
        from pyqcd.analysis._tmd_ratio import plateau_c0

        ratio = np.zeros((3, 6, 6, 2, 1), dtype=np.float64)
        ratio[:, :, :, 0, 0] = 2.0
        ratio[:, :, :, 1, 0] = np.arange(3, dtype=np.float64)[:, None, None]

        result = plateau_c0(
            ratio,
            dt_max=6,
            dt_start=2,
            dt_end=4,
            cut=2,
        )

        self.assertTrue(np.isnan(result[:, 0, 0]).all())
        self.assertTrue(np.isfinite(result[:, 1, 0]).all())


class FitWindowValidationTests(unittest.TestCase):
    def test_ratio_fit_rejects_negative_nex(self):
        from pyqcd.analysis._fitter import FitParams
        from pyqcd.analysis._ratio2pt import fit_x_coor

        params = FitParams(
            p0={'c0': 0.2, 'c1': 0.1, 'dE': 0.5},
            dt_start=2, dt_end=3, nex=-1)
        with self.assertRaisesRegex(ValueError, 'nex'):
            fit_x_coor(params)

    def test_energy_fit_rejects_negative_or_out_of_range_window(self):
        import tempfile

        from pyqcd.analysis._proton_energy import EnergyParams, do_fit

        base = dict(
            conf_short='L', conf_name='L', conf_ids=list(range(6)),
            Nt=8, Nx=2, Px=0, Py=0, Pz=0, Nsample=6, dt_max=5,
        )
        corr2 = np.ones((6, 5))
        for start, end in ((-1, 3), (1, 5), (4, 3)):
            with self.subTest(window=(start, end)), \
                    tempfile.TemporaryDirectory() as out_dir:
                params = EnergyParams(**base, dt_start=start, dt_end=end)
                with self.assertRaisesRegex(ValueError, 'dt'):
                    do_fit(corr2, params, out_dir, jack=True, verbose=False)


class CovarianceRoundoffContractTests(unittest.TestCase):
    def test_roundoff_repair_rejects_relative_nonhermitian_before_averaging(self):
        from pyqcd.analysis._disconnected import _repair_covariance_roundoff

        cov = np.array([
            [1.0e-30, 5.0e-31],
            [4.0e-31, 1.0e-30],
        ])
        with self.assertRaisesRegex(ValueError, "Hermitian"):
            _repair_covariance_roundoff(cov)

    def test_roundoff_repair_preserves_exact_zero_mode(self):
        from pyqcd.analysis._disconnected import _repair_covariance_roundoff
        from pyqcd.analysis._fitter import covariance_sample_rank

        cov = np.ones((2, 2), dtype=np.float64)
        repaired = _repair_covariance_roundoff(cov)

        self.assertEqual(float(np.linalg.eigvalsh(repaired)[0]), 0.0)
        self.assertEqual(covariance_sample_rank(repaired), 1)

    def test_roundoff_repair_preserves_known_kernel_with_mixed_null_spectrum(self):
        """Roundoff validation must not turn an exact covariance kernel positive."""
        from pyqcd.analysis._disconnected import _repair_covariance_roundoff
        from pyqcd.analysis._fitter import covariance_sample_rank

        cov = np.ones((6, 6), dtype=np.float64)
        null_vector = np.array([1.0, -1.0, 0.0, 0.0, 0.0, 0.0])
        repaired = _repair_covariance_roundoff(cov)

        np.testing.assert_array_equal(
            repaired @ null_vector, np.zeros_like(null_vector))
        self.assertEqual(covariance_sample_rank(repaired), 1)

    def test_roundoff_negative_correlation_mode_does_not_poison_lsqfit(self):
        import gvar as gv

        from pyqcd.analysis._disconnected import model_ratio
        from pyqcd.analysis._fitter import FitParams, covariance_sample_rank, fit

        rng = np.random.default_rng(0)
        central = 0.01 + 0.002 * rng.normal(size=(40, 1))
        samples = central + 1.0e-13 * rng.normal(size=(40, 14))
        x_coor = [
            (dt, dtau)
            for dt in range(3, 7)
            for dtau in range(1, dt)
        ]
        params = FitParams(
            p0={"c0": 0.05, "c1": -0.02, "dE": 0.5},
            prior={
                "c0": gv.gvar(0.05, 0.5),
                "c1": gv.gvar(-0.02, 1.0),
                "dE": gv.gvar(0.5, 0.3),
            },
            svdcut="auto",
        )

        result, cov, _, last_fit = fit(
            samples, x_coor, model_ratio, params, jackknife=True)

        diagonal = np.diag(cov)
        scale = np.sqrt(diagonal)
        corr = cov / scale[:, None] / scale[None, :]
        eigenvalues = np.linalg.eigvalsh((corr + corr.T) * 0.5)
        tolerance = (
            eigenvalues[-1] * eigenvalues.size * np.finfo(np.float64).eps)
        self.assertGreaterEqual(eigenvalues[0], -tolerance)
        self.assertEqual(covariance_sample_rank(cov), 1)
        self.assertIsNotNone(last_fit)
        for values in result.values():
            self.assertTrue(np.isfinite(values).all())

    def test_near_rank_one_roundoff_remains_usable_by_gvar(self):
        """A Gram covariance must stay numerically PSD after gvar rescales it."""
        import gvar as gv

        from pyqcd.analysis._disconnected import model_ratio
        from pyqcd.analysis._fitter import FitParams, covariance_sample_rank, fit

        rng = np.random.default_rng(3)
        central = 0.01 + 0.002 * rng.normal(size=(40, 1))
        samples = central + 1.0e-14 * rng.normal(size=(40, 14))
        x_coor = [
            (dt, dtau)
            for dt in range(3, 7)
            for dtau in range(1, dt)
        ]
        params = FitParams(
            p0={"c0": 0.05, "c1": -0.02, "dE": 0.5},
            prior={
                "c0": gv.gvar(0.05, 0.5),
                "c1": gv.gvar(-0.02, 1.0),
                "dE": gv.gvar(0.5, 0.3),
            },
            svdcut="auto",
        )

        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            warnings.simplefilter("error", UserWarning)
            result, cov, _, last_fit = fit(
                samples, x_coor, model_ratio, params, jackknife=True)

        self.assertEqual(covariance_sample_rank(cov), 1)
        self.assertIsNotNone(last_fit)
        for values in result.values():
            self.assertTrue(np.isfinite(values).all())

    def test_strict_none_rejects_singular_covariance_before_lsqfit(self):
        """None means no SVD regulation and must fail clearly on a null space."""
        import gvar as gv

        from pyqcd.analysis._disconnected import model_ratio
        from pyqcd.analysis._fitter import FitParams, fit

        rng = np.random.default_rng(3)
        central = 0.01 + 0.002 * rng.normal(size=(40, 1))
        samples = central + 1.0e-14 * rng.normal(size=(40, 14))
        x_coor = [
            (dt, dtau)
            for dt in range(3, 7)
            for dtau in range(1, dt)
        ]
        params = FitParams(
            p0={"c0": 0.05, "c1": -0.02, "dE": 0.5},
            prior={
                "c0": gv.gvar(0.05, 0.5),
                "c1": gv.gvar(-0.02, 1.0),
                "dE": gv.gvar(0.5, 0.3),
            },
            svdcut=None,
        )

        with patch(
                "lsqfit.nonlinear_fit",
                side_effect=AssertionError(
                    "strict singular covariance reached lsqfit")):
            with self.assertRaisesRegex(
                    ValueError, "svdcut=None.*singular covariance"):
                fit(samples, x_coor, model_ratio, params, jackknife=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
