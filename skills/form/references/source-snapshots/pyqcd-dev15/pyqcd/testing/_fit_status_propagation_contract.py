"""Behavioral contracts for product-level correlated-fit status propagation.

Run directly with ``python pyqcd/testing/_fit_status_propagation_contract.py``.

The tests deliberately patch only the external ``lsqfit`` solver.  The input
sample covariance remains full rank, while the solver returns a finite model
point with ``c1=0`` and ``dE=0``.  For the ratio and two-state energy models
this makes model-Jacobian columns linearly dependent.  A product layer that
trusts finite ``pmean`` values, or only checks covariance rank, therefore fails
the behavioral assertions below.
"""

from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import numpy as np


def _full_rank_samples(nsample, ndata, seed, scale=0.02):
    """Return centered samples whose covariance has ``ndata`` directions."""
    rng = np.random.default_rng(seed)
    base = np.linspace(0.2, 0.8, ndata, dtype=np.float64)
    for _ in range(8):
        samples = base + scale * rng.standard_normal((nsample, ndata))
        centered = samples - samples.mean(axis=0)
        if np.linalg.matrix_rank(centered) == ndata:
            return samples
    raise AssertionError("fixture failed to construct a full-rank covariance")


class _FiniteDegenerateFit:
    """Finite fake solver result whose two-state amplitude is zero."""

    def __init__(self, p0):
        self.pmean = {}
        for name, value in p0.items():
            try:
                value = float(np.asarray(value))
            except (TypeError, ValueError):
                value = 0.25
            if not np.isfinite(value):
                value = 0.25
            self.pmean[name] = value
        if "c1" in self.pmean:
            self.pmean["c1"] = 0.0
        if "dE" in self.pmean:
            self.pmean["dE"] = 0.0
        self.chi2 = 1.0
        self.dof = 1.0

    def format(self, maxline=True):
        return "fake finite degenerate fit"


class _FiniteIdentifiableFit:
    """Finite fake solver result with a non-degenerate two-state point."""

    def __init__(self, p0):
        self.pmean = {}
        for name, value in p0.items():
            try:
                value = float(np.asarray(value))
            except (TypeError, ValueError):
                value = 0.25
            if not np.isfinite(value):
                value = 0.25
            self.pmean[name] = value
        self.chi2 = 1.0
        self.dof = 1.0

    def format(self, maxline=True):
        return "fake identifiable fit"


def _finite_degenerate_solver(*args, **kwargs):
    del args
    p0 = kwargs.get("p0")
    if p0 is None:
        prior = kwargs.get("prior", {})
        p0 = {
            name: getattr(value, "mean", value)
            for name, value in prior.items()
        }
    return _FiniteDegenerateFit(p0)


def _finite_identifiable_solver(*args, **kwargs):
    del args
    p0 = kwargs.get("p0")
    if p0 is None:
        prior = kwargs.get("prior", {})
        p0 = {
            name: getattr(value, "mean", value)
            for name, value in prior.items()
        }
    return _FiniteIdentifiableFit(p0)


class _PriorFit:
    pyqcd_fit_status = "prior_constrained"
    pyqcd_data_identifiable = None
    chi2 = 1.0
    dof = 2.0

    def format(self, maxline=True):
        return "fake prior-constrained fit"


class _PracticalFit:
    pyqcd_fit_status = "practically_unidentifiable"
    pyqcd_fit_reason = (
        "condition number is diagnostically large; practical identifiability "
        "was not established")
    chi2 = 1.0
    dof = 2.0

    def format(self, maxline=True):
        return "fake practically-unidentifiable fit"


class FitStatusClassifierContractTests(unittest.TestCase):
    def test_classifier_preserves_statuses_and_never_upgrades_prior(self):
        from pyqcd.analysis._disconnected import fit_status_from_samples

        finite = {
            "p": np.array([1.0, 1.1, 0.9]),
            "chi2": np.array([1.0, 1.1, 0.9]),
        }
        status, reason, mask = fit_status_from_samples(
            finite, _PriorFit(), has_prior=True)
        self.assertEqual(status, "prior_constrained")
        self.assertIn("data identifiability", reason)
        np.testing.assert_array_equal(mask, [True, True, True])

        status, reason, mask = fit_status_from_samples(
            finite, _PriorFit(), has_prior=False)
        self.assertEqual(status, "prior_constrained")
        self.assertIn("data identifiability", reason)
        np.testing.assert_array_equal(mask, [True, True, True])

        status, reason, mask = fit_status_from_samples(
            finite,
            type("Identifiable", (), {"pyqcd_fit_status": "identifiable"})(),
        )
        self.assertEqual(status, "identifiable")
        self.assertEqual(reason, "identifiable")
        np.testing.assert_array_equal(mask, [True, True, True])

        partial = {
            "p": np.array([1.0, np.nan, 0.9]),
            "chi2": np.array([1.0, np.nan, 0.9]),
        }
        status, reason, mask = fit_status_from_samples(
            partial,
            type("Identifiable", (), {"pyqcd_fit_status": "identifiable"})(),
        )
        self.assertEqual(status, "partially_identifiable")
        self.assertIn("finite", reason)
        np.testing.assert_array_equal(mask, [True, False, True])

        failed = {"p": np.array([np.nan, np.nan]),
                  "chi2": np.array([np.nan, np.nan])}
        status, reason, mask = fit_status_from_samples(failed, None)
        self.assertEqual(status, "statistically_unidentifiable")
        self.assertIn("model Jacobian/covariance", reason)
        np.testing.assert_array_equal(mask, [False, False])

    def test_classifier_preserves_explicit_practical_status_and_reason(self):
        from pyqcd.analysis._disconnected import (
            aggregate_fit_statuses, fit_status_from_samples,
        )

        finite = {
            "p": np.array([1.0, 1.1, 0.9]),
            "chi2": np.array([1.0, 1.1, 0.9]),
        }
        status, reason, mask = fit_status_from_samples(finite, _PracticalFit())
        self.assertEqual(status, "practically_unidentifiable")
        self.assertIn("condition number", reason)
        np.testing.assert_array_equal(mask, [True, True, True])

        aggregate, aggregate_reason = aggregate_fit_statuses(
            [status, status], [reason, reason])
        self.assertEqual(aggregate, "practically_unidentifiable")
        self.assertIn("condition number", aggregate_reason)


class RatioStatusPropagationContractTests(unittest.TestCase):
    def test_ratio_report_rejects_finite_degenerate_model_solution(self):
        from pyqcd.analysis._fitter import FitParams
        from pyqcd.analysis._ratio2pt import (
            SampleParams2pt,
            do_fit_and_report,
        )

        sampa = SampleParams2pt(
            conf_short="synthetic",
            conf_name="synthetic",
            conf_ids=list(range(10)),
            Nt=5,
            Nx=1,
            Px=0,
            Py=0,
            Pz=2,
            Nsample=10,
            dt_max=5,
        )
        fitpa = FitParams(
            p0={"c0": 0.2, "c1": -0.7, "dE": 0.4},
            dt_start=2,
            dt_end=3,
            nex=0,
            svdcut=1.0e-6,
        )
        x_coor = [(2, 0), (2, 1), (2, 2), (3, 0), (3, 1), (3, 2), (3, 3)]
        samples = _full_rank_samples(10, len(x_coor), 901)
        ratio = np.zeros((10, 5, 5, 1), dtype=np.float64)
        for index, (dt, dtau) in enumerate(x_coor):
            ratio[:, dt, dtau, 0] = samples[:, index]

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("lsqfit.nonlinear_fit",
                       side_effect=_finite_degenerate_solver):
                result = do_fit_and_report(
                    ratio, fitpa, sampa, tmpdir, jack=False, verbose=False)
            saved = np.load(Path(tmpdir) / "0_fit_data.npz")
            report = (Path(tmpdir) / "1_fit_report.txt").read_text()

        metadata = (
            "fit_status", "fit_reason", "effective_rank", "sample_rank",
            "required_rank", "condition_number", "fit_status_by_z",
            "fit_reason_by_z",
        )
        for name in metadata:
            self.assertIn(name, result)
            self.assertIn(name, saved.files)
        np.testing.assert_allclose(result["condition_number"],
                                   saved["condition_number"])
        self.assertEqual(result["fit_status"], "statistically_unidentifiable")
        self.assertEqual(str(saved["fit_status"]),
                         "statistically_unidentifiable")
        self.assertEqual(int(result["effective_rank"][0]), 7)
        self.assertEqual(int(result["sample_rank"][0]), 7)
        self.assertIn("model Jacobian/covariance", result["fit_reason"])
        for name in ("c0", "c1", "dE", "chi2"):
            self.assertTrue(np.isnan(result[name]).all())
            self.assertTrue(np.isnan(saved[name]).all())
        self.assertIn("statistically_unidentifiable", report)
        self.assertIn("model Jacobian/covariance", report)

    def test_ratio_plot_rejects_explicit_practical_unidentifiability(self):
        from pyqcd.analysis._fitter import FitParams
        from pyqcd.analysis._ratio2pt import (
            PlotParamsRatio, SampleParams2pt, plot_ratio_fits,
        )

        sampa = SampleParams2pt(
            conf_short="synthetic", conf_name="synthetic", conf_ids=[1, 2],
            Nt=4, Nx=1, Px=0, Py=0, Pz=2, Nsample=2, dt_max=3,
        )
        ratio = np.ones((2, 3, 3, 1), dtype=np.float64)
        fitpa = FitParams(
            p0={"c0": 0.2, "c1": 0.1, "dE": 0.5},
            dt_start=1, dt_end=2, nex=0,
        )
        fit_result = {
            "c0": np.ones((2, 1)),
            "chi2": np.ones((2, 1)),
            "fit_status": np.asarray("practically_unidentifiable"),
            "fit_status_by_z": np.asarray(["practically_unidentifiable"]),
            "fit_reason": np.asarray("condition number is diagnostically large"),
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("matplotlib.axes._axes.Axes.fill_between") as fill:
                plot_ratio_fits(
                    ratio, fit_result, sampa, fitpa,
                    PlotParamsRatio(z_list=[0], dt_list=[1, 2]),
                    tmpdir, jack=False, verbose=False)
            self.assertFalse(fill.called)


class FHStatusPropagationContractTests(unittest.TestCase):
    @staticmethod
    def _plot_data(nz=2):
        return {
            "c0": np.ones((4, nz), dtype=float),
            "chi2": np.ones((4, nz), dtype=float),
        }

    @staticmethod
    def _plot_params(nz=2):
        from pyqcd.analysis._fh import FHParams
        return FHParams(
            conf_short="synthetic", P=2, z_list=list(range(nz)),
            z_step=1,
        )

    def test_fh_parameter_plots_require_explicit_status_and_skip_missing(self):
        """Numeric-only FH fits are unavailable to both plotting entry points."""
        from pyqcd.analysis._fh import plot_para, plot_para_cmp
        from pyqcd.analysis._fitter import FitParams

        fitpa = FitParams(p0={"c0": 0.3}, dt_start=1, dt_end=3)
        data = self._plot_data()
        params = self._plot_params()
        output = StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pyqcd.analysis._fh.plot_errbar") as errbar, \
                    patch("pyqcd.analysis._fh.plot_scatter") as scatter, \
                    redirect_stdout(output):
                saved_one = plot_para(data, tmpdir, fitpa, params,
                                      verbose=True)
                saved_cmp = plot_para_cmp(
                    {"dt1_3": data}, tmpdir, params, [fitpa],
                    verbose=True)

        self.assertEqual(saved_one, [])
        self.assertEqual(saved_cmp, [])
        self.assertFalse(errbar.called)
        self.assertFalse(scatter.called)
        self.assertIn("unavailable", output.getvalue())

    def test_fh_parameter_plots_reject_bad_or_unknown_status_shapes(self):
        """Malformed and unknown per-z statuses cannot enable a plot."""
        from pyqcd.analysis._fh import plot_para
        from pyqcd.analysis._fitter import FitParams

        fitpa = FitParams(p0={"c0": 0.3}, dt_start=1, dt_end=3)
        params = self._plot_params()
        for status in (np.asarray(["identifiable"]),
                       np.asarray(["unknown", "unknown"])):
            with self.subTest(status=status.tolist()):
                data = self._plot_data()
                data["fit_status_by_z"] = status
                output = StringIO()
                with tempfile.TemporaryDirectory() as tmpdir:
                    with patch("pyqcd.analysis._fh.plot_errbar") as errbar, \
                            patch("pyqcd.analysis._fh.plot_scatter") as scatter, \
                            redirect_stdout(output):
                        saved = plot_para(
                            data, tmpdir, fitpa, params, verbose=True)
                self.assertEqual(saved, [])
                self.assertFalse(errbar.called)
                self.assertFalse(scatter.called)
                self.assertIn("unavailable", output.getvalue())

    def test_fh_single_configuration_stays_nan_and_is_reported(self):
        from pyqcd.analysis._fitter import FitParams
        from pyqcd.analysis._fh import FHParams, do_fit_and_report

        fh = np.ones((1, 5, 1), dtype=np.float64)
        fitpa = FitParams(
            p0={"c0": 0.3}, dt_start=1, dt_end=3, svdcut=1.0e-6)
        params = FHParams(conf_short="synthetic", P=2, z_list=[0])

        with tempfile.TemporaryDirectory() as tmpdir:
            do_fit_and_report(
                fh, tmpdir, fitpa, params, verbose=False)
            saved = np.load(Path(tmpdir) / "fit_dt1_3.npz")
            report = (Path(tmpdir) / "report_dt1_3.txt").read_text()

        self.assertTrue(np.isnan(saved["c0"]).all())
        self.assertTrue(np.isnan(saved["chi2"]).all())
        self.assertEqual(str(saved["fit_status"]),
                         "statistically_unidentifiable")
        self.assertIn("statistically_unidentifiable", report)
        self.assertIn("model Jacobian/covariance", report)

    def test_fh_report_preserves_prior_constrained_status(self):
        from pyqcd.analysis._fitter import FitParams
        from pyqcd.analysis._fh import FHParams, do_fit_and_report

        fh = np.ones((3, 5, 1), dtype=np.float64)
        fitpa = FitParams(
            p0={"c0": 0.3},
            prior={"c0": 0.3},
            dt_start=1,
            dt_end=3,
            svdcut=1.0e-6,
        )
        params = FHParams(conf_short="synthetic", P=2, z_list=[0])

        def fake_prior_fit(y_coor, x_coor, model, fitpa, jackknife=False,
                           debug=False, debugNfit=20):
            del x_coor, model, fitpa, jackknife, debug, debugNfit
            n_sample = np.asarray(y_coor).shape[0]
            return ({"c0": np.full(n_sample, 0.3),
                     "chi2": np.full(n_sample, 0.5)},
                    np.eye(3), 1.0, _PriorFit())

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pyqcd.analysis._fh.fit", side_effect=fake_prior_fit):
                do_fit_and_report(
                    fh, tmpdir, fitpa, params, verbose=False)
            saved = np.load(Path(tmpdir) / "fit_dt1_3.npz")
            report = (Path(tmpdir) / "report_dt1_3.txt").read_text()

        self.assertEqual(str(saved["fit_status"]), "prior_constrained")
        self.assertIn("prior_constrained", report)
        self.assertNotIn("fit status = identifiable", report)


class EnergyStatusPropagationContractTests(unittest.TestCase):
    def test_energy_falls_back_to_identifiable_one_state_at_degenerate_dE(self):
        from pyqcd.analysis._proton_energy import EnergyParams, do_fit

        params = EnergyParams(
            conf_short="synthetic",
            conf_name="synthetic",
            conf_ids=list(range(8)),
            Nt=6,
            Nx=1,
            Px=0,
            Py=0,
            Pz=2,
            Nsample=8,
            dt_max=6,
            dt_start=1,
            dt_end=5,
        )
        corr2 = _full_rank_samples(8, 6, 902, scale=0.01)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("lsqfit.nonlinear_fit",
                       side_effect=_finite_degenerate_solver):
                result = do_fit(corr2, params, tmpdir, jack=False,
                                verbose=False)
            saved = np.load(Path(tmpdir) / "1_fit_data.npz")
            report = (Path(tmpdir) / "2_fit_report.txt").read_text()

        metadata = ("fit_status", "fit_reason", "effective_rank",
                    "sample_rank", "required_rank", "condition_number")
        for name in metadata:
            self.assertIn(name, result)
            self.assertIn(name, saved.files)
        np.testing.assert_allclose(result["condition_number"],
                                   saved["condition_number"])
        self.assertEqual(result["fit_status"], "identifiable")
        self.assertEqual(str(saved["fit_status"]), "identifiable")
        self.assertEqual(result["selected_model"], "one_state")
        self.assertEqual(
            result["excited_state_status"],
            "practically_unidentifiable",
        )
        self.assertEqual(result["two_state_fit_status"],
                         "statistically_unidentifiable")
        self.assertIn("model Jacobian/covariance",
                      result["two_state_fit_reason"])
        self.assertEqual(int(result["effective_rank"]), 5)
        self.assertEqual(int(result["sample_rank"]), 5)
        self.assertIn("AICc selected one_state", result["fit_reason"])
        for name in ("c0", "E0", "chi2"):
            self.assertTrue(np.isfinite(result[name]).all())
            self.assertTrue(np.isfinite(saved[name]).all())
        for name in ("c1", "dE"):
            self.assertTrue(np.isnan(result[name]).all())
            self.assertTrue(np.isnan(saved[name]).all())
        self.assertIn("AICc selected model = one_state", report)

    def test_energy_one_state_selection_marks_finite_two_state_candidate_practical(self):
        """AICc model selection and the two-state status/reason/log agree."""
        from pyqcd.analysis._proton_energy import EnergyParams, do_fit

        params = EnergyParams(
            conf_short="synthetic", conf_name="synthetic",
            conf_ids=list(range(8)), Nt=6, Nx=1,
            Px=0, Py=0, Pz=2, Nsample=8, dt_max=6,
            dt_start=1, dt_end=5,
        )
        corr2 = _full_rank_samples(8, 6, 909, scale=0.01)
        output = StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("lsqfit.nonlinear_fit",
                       side_effect=_finite_identifiable_solver), \
                    redirect_stdout(output):
                result = do_fit(corr2, params, tmpdir, jack=False,
                                verbose=True)
            report = (Path(tmpdir) / "2_fit_report.txt").read_text()

        self.assertEqual(result["selected_model"], "one_state")
        self.assertEqual(result["two_state_fit_status"],
                         "practically_unidentifiable")
        self.assertIn("AICc selected one_state",
                      result["two_state_fit_reason"])
        self.assertIn("two_state_fit_status = practically_unidentifiable",
                      output.getvalue())
        self.assertNotIn(
            "two_state_fit_status = statistically_unidentifiable",
            output.getvalue())
        self.assertIn("two-state fit status = practically_unidentifiable",
                      report)
        self.assertIn("two-state fit reason = AICc selected one_state",
                      report)

    def test_fh_bestfit_requires_complete_explicit_status(self):
        """Bestfit must not use finite c0 from a numeric-only NPZ."""
        from pyqcd.analysis._fh import FHParams, run_fh
        from pyqcd.analysis._fitter import FitParams

        params = FHParams(
            conf_short="synthetic", P=2, z_list=[0, 1], z_step=1,
        )
        fitpa = FitParams(p0={"c0": 0.3}, dt_start=1, dt_end=2,
                          nex=0)
        with tempfile.TemporaryDirectory() as tmpdir:
            out_root = Path(tmpdir) / "out"
            out_dir = out_root / "synthetic" / "P2"
            fit_dir = out_dir / "fit_nex0" / "dt1_2"
            fit_dir.mkdir(parents=True)
            (out_dir / "fh").mkdir()
            np.save(out_dir / "fh" / "FH_nex0.npy",
                    np.ones((4, 4, 2), dtype=float))
            np.savez(
                fit_dir / "fit_dt1_2.npz",
                c0=np.ones((4, 2), dtype=float),
                chi2=np.ones((4, 2), dtype=float),
            )
            with patch("pyqcd.analysis._fh.plot_para", return_value=[]), \
                    patch("pyqcd.analysis._fh.plot_para_cmp", return_value=[]), \
                    patch("pyqcd.analysis._fh.plot_fh", return_value=[]) as plot_fh:
                result = run_fh(
                    str(Path(tmpdir) / "data"), str(out_root), params,
                    [fitpa],
                    bestfit_params={"dt_start": 1, "dt_end": 2,
                                    "nex": 0},
                    parts=(3, 3), verbose=False)

        self.assertEqual(result["saved"], [])
        self.assertFalse(plot_fh.called)

    def test_energy_plot_rejects_explicit_practical_unidentifiability(self):
        from pyqcd.analysis._proton_energy import EnergyParams, plot_eff_mass

        params = EnergyParams(
            conf_short="synthetic", conf_name="synthetic", conf_ids=[1, 2],
            Nt=4, Nx=1, Px=0, Py=0, Pz=2, Nsample=2, dt_max=4,
            dt_start=1, dt_end=2,
        )
        corr2 = np.exp(-0.2 * np.arange(4))[None, :].repeat(2, axis=0)
        fit_result = {
            "E0": np.ones(2),
            "chi2": np.ones(2),
            "fit_status": np.asarray("practically_unidentifiable"),
            "fit_reason": np.asarray("condition number is diagnostically large"),
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("matplotlib.axes._axes.Axes.fill_between") as fill:
                plot_eff_mass(
                    corr2, fit_result, params, tmpdir,
                    jack=False, verbose=False)
            self.assertFalse(fill.called)


def _disconnected_inputs(nconf=9, nt=6, nz=1, nb=1, seed=903):
    rng = np.random.default_rng(seed)
    t = np.arange(nt, dtype=np.float64)
    corr_2pt = {}
    ope = {}
    for offset in range(nconf):
        cid = 100 + offset
        corr = np.exp(-0.18 * t) * (
            1.0 + 0.04 * rng.standard_normal(nt))
        corr_2pt[cid] = {
            "corr_pp_P2": corr,
            "corr_pp_P200": corr,
            "corr_pion_P2": corr * (1.0 + 0.03 * rng.standard_normal(nt)),
        }
        combined = 0.2 + 0.04 * rng.standard_normal((nz, nt))
        ope[cid] = {
            "combined": combined,
            "tmd": combined[:, None, :].repeat(nb, axis=1),
        }
    return corr_2pt, ope, list(range(100, 100 + nconf))


class DisconnectedStatusPropagationContractTests(unittest.TestCase):
    def test_disconnected_ratio_does_not_persist_finite_degenerate_fit(self):
        from pyqcd.analysis._disconnected import run_disconnected_ratio

        corr_2pt, ope, conf_ids = _disconnected_inputs()
        calls = [0]

        def mixed_solver(*args, **kwargs):
            calls[0] += 1
            p0 = kwargs["p0"]
            if calls[0] <= len(conf_ids):
                return _FiniteIdentifiableFit(p0)
            return _FiniteDegenerateFit(p0)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("lsqfit.nonlinear_fit",
                       side_effect=mixed_solver):
                result = run_disconnected_ratio(
                    corr_2pt, ope, conf_ids, tmpdir,
                    logger=lambda _message: None,
                    NT=6,
                    NX=1,
                    dt_max=5,
                    dt_start=2,
                    dt_end=4,
                    cut=2,
                )
            out_dir = Path(tmpdir) / "analysis" / "disconnected"
            proton_saved = np.load(out_dir / "0_fit_data_proton.npz")
            pion_saved = np.load(out_dir / "0_fit_data_pion.npz")
            aggregate_saved = np.load(out_dir / "0_fit_data.npz")
            report = (out_dir / "1_fit_report.txt").read_text()

        self.assertEqual(result["proton"]["fit_status"], "identifiable")
        self.assertEqual(result["pion"]["fit_status"],
                         "statistically_unidentifiable")
        self.assertTrue(np.isfinite(proton_saved["c0"]).all())
        self.assertTrue(np.isnan(pion_saved["c0"]).all())
        self.assertEqual(str(aggregate_saved["fit_status"]),
                         "partially_identifiable")
        self.assertIn("fit_status_by_channel", aggregate_saved.files)
        self.assertIn("proton", report)
        self.assertIn("pion", report)
        self.assertIn("partially_identifiable", report)
        self.assertIn("model Jacobian/covariance", report)


class TmdStatusPropagationContractTests(unittest.TestCase):
    def test_tmd_ratio_does_not_persist_finite_degenerate_fit(self):
        from pyqcd.analysis._tmd_ratio import run_disconnected_tmd_ratio

        corr_2pt, ope, conf_ids = _disconnected_inputs(nz=1, nb=1)
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("lsqfit.nonlinear_fit",
                       side_effect=_finite_degenerate_solver):
                result = run_disconnected_tmd_ratio(
                    corr_2pt, ope, conf_ids, tmpdir,
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

        for name in ("c0", "c1", "dE", "chi2"):
            self.assertTrue(np.isnan(result[name]).all())
            self.assertTrue(np.isnan(saved[name]).all())
        self.assertEqual(result["fit_status"],
                         "statistically_unidentifiable")
        self.assertEqual(str(saved["fit_status"]),
                         "statistically_unidentifiable")
        self.assertIn("model Jacobian/covariance", report)


def _write_test9_corr(root, conf_ids, seed=904):
    rng = np.random.default_rng(seed)
    t = np.arange(72, dtype=np.float64)
    for offset, cid in enumerate(conf_ids):
        data_dir = Path(root) / "data" / f"conf{cid}"
        data_dir.mkdir(parents=True, exist_ok=True)
        corr = np.exp(-0.22 * t) * (
            1.0 + 0.02 * rng.standard_normal(t.size)
            + 0.001 * offset * np.cos(0.17 * t))
        np.save(data_dir / f"corr_pp_P200_{cid}.npy", corr)


class Test9ExtendedStatusPropagationContractTests(unittest.TestCase):
    def test_test9_extended_rejects_finite_degenerate_energy_solution(self):
        from pyqcd.analysis._test9_extended import generate_test6_style_plots

        conf_ids = list(range(100, 108))
        with tempfile.TemporaryDirectory() as tmpdir:
            test9_root = Path(tmpdir) / "test9"
            _write_test9_corr(test9_root, conf_ids)
            with patch("lsqfit.nonlinear_fit",
                       side_effect=_finite_degenerate_solver):
                generate_test6_style_plots(
                    str(test9_root), str(Path(tmpdir) / "out"),
                    conf_ids, ["P200"], logger=lambda _message: None)
            out_dir = Path(tmpdir) / "out" / "1_result" / "L24x72" / "Pz2"
            saved = np.load(out_dir / "1_fit_data.npz")
            report = (out_dir / "2_fit_report.txt").read_text()

        self.assertEqual(str(saved["fit_status"]),
                         "statistically_unidentifiable")
        self.assertIn("model Jacobian/covariance", str(saved["fit_reason"]))
        for direction in ("x", "y", "z", "ave"):
            self.assertEqual(str(saved[f"fit_status_{direction}"]),
                             "statistically_unidentifiable")
            for name in ("c0", "c1", "E0", "dE", "chi2"):
                self.assertTrue(np.isnan(saved[f"{name}_{direction}"]).all())
        self.assertIn("statistically_unidentifiable", report)

    def test_test9_solver_program_error_is_not_fit_failed_status(self):
        from pyqcd.analysis._test9_extended import generate_test6_style_plots

        conf_ids = list(range(120, 128))
        with tempfile.TemporaryDirectory() as tmpdir:
            test9_root = Path(tmpdir) / "test9"
            _write_test9_corr(test9_root, conf_ids, seed=905)
            with patch("lsqfit.nonlinear_fit",
                       side_effect=RuntimeError("solver programming error")):
                with self.assertRaisesRegex(RuntimeError,
                                            "solver programming error"):
                    generate_test6_style_plots(
                        str(test9_root), str(Path(tmpdir) / "out"),
                        conf_ids, ["P200"], logger=lambda _message: None)

    def test_test9_missing_tmd_ratio_skips_ratio_figure(self):
        from pyqcd.analysis._test9_extended import generate_test0_style_plots

        conf_ids = list(range(140, 148))
        messages = []
        with tempfile.TemporaryDirectory() as tmpdir:
            test9_root = Path(tmpdir) / "test9"
            _write_test9_corr(test9_root, conf_ids, seed=906)
            out_root = Path(tmpdir) / "out"
            generate_test0_style_plots(
                str(test9_root), str(out_root), conf_ids, ["P200"],
                logger=messages.append)
            ratio_plot = out_root / "plots" / "ratio_3pt_all_channels.png"

        self.assertFalse(ratio_plot.exists())
        self.assertTrue(any("ratio" in msg and "unavailable" in msg
                            for msg in messages))

    def test_test9_missing_fit_status_skips_c0_and_chi2_figures(self):
        from pyqcd.analysis._test9_extended import generate_test0_style_plots

        conf_ids = list(range(150, 158))
        messages = []
        with tempfile.TemporaryDirectory() as tmpdir:
            test9_root = Path(tmpdir) / "test9"
            _write_test9_corr(test9_root, conf_ids, seed=907)
            tmd_dir = test9_root / "analysis" / "tmd_ratio"
            tmd_dir.mkdir(parents=True)
            np.save(
                tmd_dir / "ratio_proton_P200.npy",
                np.ones((len(conf_ids), 20, 20, 13, 1), dtype=np.float64),
            )
            np.save(tmd_dir / "c0_mean_P200.npy",
                    np.ones((13, 1), dtype=np.float64))
            np.save(tmd_dir / "c0_err_P200.npy",
                    np.full((13, 1), 0.1, dtype=np.float64))
            # Numeric-only central artifact: c0/chi2 are finite but status is
            # absent, so they must not be presented as verified.
            np.savez(
                tmd_dir / "0_fit_data_P200.npz",
                c0=np.ones((len(conf_ids), 13, 1)),
                chi2=np.ones((len(conf_ids), 13, 1)),
            )
            out_root = Path(tmpdir) / "out"
            generate_test0_style_plots(
                str(test9_root), str(out_root), conf_ids, ["P200"],
                logger=messages.append)
            adir = out_root / "analysis" / "disconnected"

        self.assertFalse((adir / "c0_proton_P200.png").exists())
        self.assertFalse((adir / "chi2_proton_P200.png").exists())
        self.assertTrue(any("fit status" in msg and "unavailable" in msg
                            for msg in messages))

    def test_test9_all_prior_constrained_directions_are_aggregated_and_plotted(self):
        from pyqcd.analysis._test9_extended import generate_test6_style_plots

        conf_ids = list(range(160, 168))

        def fake_prior_fit(y_coor, x_coor, model, fitpa, jackknife=False,
                           debug=False, debugNfit=20):
            del x_coor, model, fitpa, jackknife, debug, debugNfit
            n_sample = np.asarray(y_coor).shape[0]
            return ({"c0": np.full(n_sample, 0.3),
                     "c1": np.full(n_sample, 0.2),
                     "E0": np.full(n_sample, 0.8),
                     "dE": np.full(n_sample, 0.4),
                     "chi2": np.full(n_sample, 0.5)},
                    np.eye(5), 1.0, _PriorFit())

        with tempfile.TemporaryDirectory() as tmpdir:
            test9_root = Path(tmpdir) / "test9"
            _write_test9_corr(test9_root, conf_ids, seed=908)
            out_root = Path(tmpdir) / "out"
            with patch("pyqcd.analysis._test9_extended.fit",
                       side_effect=fake_prior_fit):
                generate_test6_style_plots(
                    str(test9_root), str(out_root), conf_ids, ["P200"],
                    logger=lambda _message: None)
            out_dir = out_root / "1_result" / "L24x72" / "Pz2"
            saved = np.load(out_dir / "1_fit_data.npz")
            report = (out_dir / "2_fit_report.txt").read_text()
            plot_exists = (out_dir / "eff_mass.png").exists()

        self.assertEqual(str(saved["fit_status"]), "prior_constrained")
        for direction in ("x", "y", "z", "ave"):
            self.assertEqual(str(saved[f"fit_status_{direction}"]),
                             "prior_constrained")
        self.assertNotIn("partially_identifiable", report)
        self.assertIn("prior_constrained", report)
        self.assertTrue(plot_exists)


if __name__ == "__main__":
    unittest.main()
