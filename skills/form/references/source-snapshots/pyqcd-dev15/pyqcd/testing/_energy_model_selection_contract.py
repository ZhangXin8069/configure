"""Contract tests for data-driven one-/two-state proton-energy selection."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np


def _samples(model, *, n_sample, n_time, seed, relative_noise):
    rng = np.random.default_rng(seed)
    t = np.arange(n_time, dtype=np.float64)
    central = np.asarray(model(t), dtype=np.float64)
    noise = relative_noise * rng.normal(size=(n_sample, n_time))
    return central[None, :] * (1.0 + noise)


class EnergyModelSelectionContractTests(unittest.TestCase):
    def _params(self, *, n_sample, n_time, dt_start, dt_end, p0):
        from pyqcd.analysis._proton_energy import EnergyParams

        return EnergyParams(
            conf_short="model_selection",
            conf_name="model_selection",
            conf_ids=list(range(n_sample)),
            Nt=n_time,
            Nx=4,
            Px=0,
            Py=0,
            Pz=0,
            Nsample=n_sample,
            dt_max=n_time,
            dt_start=dt_start,
            dt_end=dt_end,
            p0=p0,
        )

    def test_aicc_selects_one_state_when_late_window_has_no_excited_signal(self):
        from pyqcd.analysis._proton_energy import do_fit

        n_sample, n_time = 24, 12
        corr2 = _samples(
            lambda t: 1.05 * np.exp(-1.1 * t),
            n_sample=n_sample,
            n_time=n_time,
            seed=4101,
            relative_noise=7.0e-3,
        )
        params = self._params(
            n_sample=n_sample,
            n_time=n_time,
            dt_start=6,
            dt_end=11,
            p0={"c0": 0.8, "c1": 0.2, "E0": 1.0, "dE": 0.5},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = do_fit(corr2, params, tmpdir, jack=False, verbose=False)
            saved = np.load(Path(tmpdir) / "1_fit_data.npz")
            report = (Path(tmpdir) / "2_fit_report.txt").read_text()

        self.assertEqual(str(result["selected_model"]), "one_state")
        self.assertEqual(int(result["status_schema_version"]), 2)
        self.assertEqual(str(result["ground_state_status"]), "identifiable")
        self.assertEqual(
            str(result["excited_state_status"]),
            "practically_unidentifiable",
        )
        self.assertTrue(np.isfinite(result["c0"]).all())
        self.assertTrue(np.isfinite(result["E0"]).all())
        self.assertTrue(np.isnan(result["c1"]).all())
        self.assertTrue(np.isnan(result["dE"]).all())
        parameter_status = dict(zip(
            result["parameter_names"].astype(str),
            result["parameter_status"].astype(str),
        ))
        self.assertEqual(parameter_status["E0"], "identifiable")
        self.assertEqual(
            parameter_status["dE"], "practically_unidentifiable")
        self.assertEqual(int(result["aicc_n_observations"]), 6)
        self.assertEqual(np.asarray(result["aicc_one_state"]).ndim, 0)
        self.assertEqual(np.asarray(result["aicc_two_state"]).ndim, 0)
        self.assertEqual(
            np.asarray(result["aicc_one_state_samples"]).shape,
            (n_sample,),
        )
        self.assertLess(
            float(np.nanmedian(result["aicc_one_state"])),
            float(np.nanmedian(result["aicc_two_state"])),
        )
        self.assertEqual(str(saved["selected_model"]), "one_state")
        self.assertIn("AICc selected model = one_state", report)

    def test_aicc_keeps_two_states_when_excited_signal_is_resolved(self):
        from pyqcd.analysis._proton_energy import do_fit

        n_sample, n_time = 32, 13
        corr2 = _samples(
            lambda t: (
                0.8 * np.exp(-0.24 * t)
                + 0.55 * np.exp(-0.95 * t)
            ),
            n_sample=n_sample,
            n_time=n_time,
            seed=4102,
            relative_noise=8.0e-4,
        )
        params = self._params(
            n_sample=n_sample,
            n_time=n_time,
            dt_start=1,
            dt_end=12,
            p0={"c0": 0.75, "c1": 0.65, "E0": 0.25, "dE": 0.65},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = do_fit(corr2, params, tmpdir, jack=False, verbose=False)

        self.assertEqual(str(result["selected_model"]), "two_state")
        self.assertEqual(np.asarray(result["aicc_two_state"]).ndim, 0)
        self.assertEqual(str(result["ground_state_status"]), "identifiable")
        self.assertEqual(str(result["excited_state_status"]), "identifiable")
        for name in ("c0", "c1", "E0", "dE", "chi2"):
            self.assertTrue(np.isfinite(result[name]).all(), name)
        self.assertLess(
            float(np.nanmedian(result["aicc_two_state"])),
            float(np.nanmedian(result["aicc_one_state"])),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
