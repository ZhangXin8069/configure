"""参考 donghx schema-v2 梯度流胶子 OPE/ratio 的独立契约。"""
from __future__ import annotations

import tempfile
import unittest

import numpy as np
from scipy.linalg import expm


_SHAPE = (2, 2, 2, 2)


def _near_identity_su3(seed=20260909, strength=0.12):
    rng = np.random.default_rng(seed)
    gauge = np.empty(_SHAPE + (4, 3, 3), dtype=np.complex128)
    for index in np.ndindex(*_SHAPE, 4):
        matrix = rng.normal(size=(3, 3)) + 1j * rng.normal(size=(3, 3))
        antihermitian = matrix - matrix.conj().T
        antihermitian -= (
            np.trace(antihermitian) * np.eye(3, dtype=np.complex128) / 3.0
        )
        gauge[index] = expm(strength * antihermitian)
    return gauge


def _site_transform(seed=20260910):
    return _near_identity_su3(seed=seed, strength=0.2)[..., 0, :, :]


def _gauge_transform(gauge, transformation):
    transformed = np.empty_like(gauge)
    for direction in range(4):
        axis = 3 - direction
        forward = np.roll(transformation, -1, axis=axis)
        transformed[..., direction, :, :] = (
            transformation @ gauge[..., direction, :, :]
            @ forward.conj().swapaxes(-1, -2)
        )
    return transformed


class GradientFlowGluonContract(unittest.TestCase):
    def setUp(self):
        from pyqcd.tools import set_backend

        set_backend("numpy")

    def test_schema_components_orientations_and_metadata(self):
        from pyqcd.operator import (
            GRADIENT_FLOW_COMPONENTS,
            GRADIENT_FLOW_FIELD_PROJECTIONS,
            GRADIENT_FLOW_OPE_AXES,
            GRADIENT_FLOW_OPE_SCHEMA,
            GRADIENT_FLOW_ORIENTATIONS,
            gradient_flow_gluon_ope,
            validate_gradient_flow_gluon_ope,
        )

        data, metadata = gradient_flow_gluon_ope(
            _near_identity_su3(), tau=0.0, epsilon=0.01, z_count=2,
            conf_id=4150,
        )
        validate_gradient_flow_gluon_ope(
            data, metadata, conf_id=4150, tau=0.0, epsilon=0.01
        )
        self.assertEqual(data.shape, (2, 2, 4, 6, 2, 2))
        self.assertEqual(data.dtype, np.dtype("complex128"))
        self.assertEqual(metadata["schema"], GRADIENT_FLOW_OPE_SCHEMA)
        self.assertEqual(metadata["axes"], list(GRADIENT_FLOW_OPE_AXES))
        self.assertEqual(
            metadata["axis_labels"]["field_projection"],
            list(GRADIENT_FLOW_FIELD_PROJECTIONS),
        )
        self.assertEqual(
            metadata["axis_labels"]["z_orientation"],
            list(GRADIENT_FLOW_ORIENTATIONS),
        )
        self.assertEqual(
            metadata["axis_labels"]["component"],
            list(GRADIENT_FLOW_COMPONENTS),
        )
        self.assertEqual(metadata["input_scheme"], "thin_link_no_hyp_no_smear")
        self.assertEqual(metadata["flow"]["n_steps"], 0)

    def test_traceless_projection_matches_gauge_observable(self):
        from pyqcd.gauge import clover_field_strength
        from pyqcd.operator import flowed_gluon_ope, plaquette_clover

        gauge = _near_identity_su3(seed=7311)
        data = flowed_gluon_ope(gauge, z_count=1)
        raw = np.asarray(plaquette_clover(gauge, 3, 0))
        traceless = np.asarray(clover_field_strength(
            gauge, 3, 0, traceless=True
        ))
        expected = np.sum(
            np.einsum("...ab,...ba->...", traceless, traceless),
            axis=(1, 2, 3),
        )
        actual = data[1, 0, 0, 3, 0]
        np.testing.assert_allclose(actual, expected, rtol=0, atol=2e-12)
        self.assertGreater(
            float(np.max(np.abs(raw - traceless))), 1e-10,
            "随机有限-a 组态未体现 legacy 与 traceless 的区别",
        )

    def test_straight_wilson_line_full_sum_is_gauge_invariant(self):
        from pyqcd.operator import flowed_gluon_ope

        gauge = _near_identity_su3(seed=7312)
        transformed = _gauge_transform(gauge, _site_transform())
        original = flowed_gluon_ope(gauge, z_count=2)
        rotated = flowed_gluon_ope(transformed, z_count=2)
        np.testing.assert_allclose(rotated, original, rtol=0, atol=3e-11)
        np.testing.assert_allclose(
            original[:, :, 0, :, 0],
            original[:, :, 1, :, 0],
            rtol=0, atol=2e-12,
        )

    def test_six_component_identities_and_helicity_selector(self):
        from pyqcd.operator import (
            flowed_gluon_ope, select_gradient_flow_gluon_component,
        )

        data = flowed_gluon_ope(_near_identity_su3(seed=7313), z_count=2)
        np.testing.assert_allclose(
            data[:, :, :, 1], data[:, :, :, 3] + data[:, :, :, 4],
            rtol=0, atol=2e-12,
        )
        np.testing.assert_allclose(
            data[:, :, :, 2], 2.0 * data[:, :, :, 5],
            rtol=0, atol=2e-12,
        )
        np.testing.assert_allclose(
            data[:, 0, :, 0], data[:, 0, :, 1] - data[:, 0, :, 2],
            rtol=0, atol=2e-12,
        )
        np.testing.assert_allclose(
            data[:, 1, :, 0], data[:, 1, :, 1] + data[:, 1, :, 2],
            rtol=0, atol=2e-12,
        )
        physical = select_gradient_flow_gluon_component(
            data, channel="helicity", orientation="odd_difference",
            component="helicity_physical_T_minus_S",
        )
        expected = data[1, 1, 3, 1] - data[1, 1, 3, 2]
        np.testing.assert_allclose(physical, expected, rtol=0, atol=2e-12)
        np.testing.assert_allclose(
            data[:, :, 2], data[:, :, 0] + data[:, :, 1],
            rtol=0, atol=2e-12,
        )
        np.testing.assert_allclose(
            data[:, :, 3], data[:, :, 0] - data[:, :, 1],
            rtol=0, atol=2e-12,
        )

    def test_flow_step_default_and_epsilon_convergence(self):
        from pyqcd.operator import gradient_flow_gluon_ope

        gauge = _near_identity_su3(seed=7314)
        coarse, metadata = gradient_flow_gluon_ope(
            gauge, tau=0.02, z_count=2
        )
        fine, fine_metadata = gradient_flow_gluon_ope(
            gauge, tau=0.02, epsilon=0.005, z_count=2
        )
        self.assertEqual(metadata["flow"]["epsilon"], 0.01)
        self.assertEqual(metadata["flow"]["n_steps"], 2)
        self.assertEqual(fine_metadata["flow"]["n_steps"], 4)
        relative = np.linalg.norm((coarse - fine).ravel()) / max(
            np.linalg.norm(fine.ravel()), 1e-300
        )
        self.assertLess(relative, 1e-4)

    def test_flow_to_quasi_matches_reference_component_factors(self):
        from pyqcd.renorm import coefficients, match_one

        array = np.zeros((1, 2, 4, 6, 3, 1), dtype=np.complex128)
        array[0, 0, 0, 1, :, 0] = 2.0
        array[0, 0, 0, 2, :, 0] = 1.0
        matched, metadata = match_one(
            array, tau=0.5, a_fm=0.0775, mu_gev=2.0, alpha_s=0.25
        )
        _, c_perp, delta_m, _ = coefficients(
            0.5, 0.0775, 2.0, 0.25
        )
        line = np.exp(
            -delta_m * np.arange(3) * 0.0775 * 5.067730716
        )
        np.testing.assert_allclose(
            matched[0, 0, 0, 1, :, 0],
            2.0 * line / (c_perp * c_perp),
            rtol=0, atol=2e-14,
        )
        np.testing.assert_allclose(
            matched[0, 0, 0, 0, :, 0],
            matched[0, 0, 0, 1, :, 0]
            - matched[0, 0, 0, 2, :, 0],
            rtol=0, atol=2e-14,
        )
        self.assertEqual(
            metadata["status"], "flow_to_MSbar_quasi_operator_one_loop"
        )
        self.assertTrue(np.isfinite([
            metadata["c_parallel_perp"],
            metadata["c_perp_perp"],
            metadata["delta_m_GeV"],
            metadata["t_GeV_minus2"],
        ]).all())
        array[0, 1, 0, 1, :, 0] = 2.0
        array[0, 1, 0, 2, :, 0] = 1.0
        matched_h, metadata_h = match_one(
            array, tau=0.5, a_fm=0.0775, mu_gev=2.0, alpha_s=0.25
        )
        self.assertEqual(
            metadata_h["component_factors_helicity"],
            1.0 / metadata_h["c_perp_perp"],
        )
        np.testing.assert_allclose(
            matched_h[0, 1, 0, 0, :, 0],
            3.0 * line / metadata_h["c_perp_perp"],
            rtol=0, atol=2e-14,
        )

    def test_complex_ratio_uses_full_pol35_and_shared_nopol_denominator(self):
        from pyqcd.analysis import covariance_ratio_estimator

        rng = np.random.default_rng(7315)
        operator = rng.normal(size=(6, 3, 5)) + 1j * rng.normal(size=(6, 3, 5))
        pol35 = rng.normal(size=(6, 5, 2)) + 1j * rng.normal(size=(6, 5, 2))
        nopol = 4.0 + rng.normal(size=(6, 5, 2)) + 1j * rng.normal(size=(6, 5, 2))
        got = covariance_ratio_estimator(
            operator, pol35, True, denominator_correlator=nopol
        )
        mean_o = operator.mean(axis=0)
        mean_pol = pol35.mean(axis=0)
        c3 = (
            (operator[..., None] * pol35[:, None]).mean(axis=0)
            - mean_o[..., None] * mean_pol[None]
        ).mean(axis=1)
        c2 = nopol.mean(axis=(0, 1))
        np.testing.assert_allclose(got[0], c3, rtol=0, atol=3e-14)
        np.testing.assert_allclose(got[1], c2, rtol=0, atol=3e-14)
        np.testing.assert_allclose(
            got[0] / got[1][None, :], c3 / c2[None, :],
            rtol=0, atol=3e-14,
        )
        wrong = covariance_ratio_estimator(
            operator, pol35.imag, True, denominator_correlator=nopol
        )
        self.assertGreater(
            float(np.max(np.abs(wrong[0] - got[0]))), 1e-8,
            "丢弃 pol35 实部没有暴露 estimator 差异",
        )

    def test_ratio_axes_nopol_denominator_and_final_phase_projection(self):
        from pyqcd.analysis import (
            calculate_gradient_flow_ratios,
            physical_helicity_ratio,
            validate_gradient_flow_ratio_results,
        )

        rng = np.random.default_rng(7316)
        nconf, nt, nz = 5, 4, 2
        raw = rng.normal(size=(nconf, 2, 2, 3, nz, nt))
        raw = raw + 1j * rng.normal(size=raw.shape)
        raw[:, :, 1, :, 0] = raw[:, :, 0, :, 0]
        ope = np.empty((nconf, 2, 4, 3, nz, nt), dtype=np.complex128)
        for channel in range(2):
            for orientation in range(2):
                mt = raw[:, channel, orientation, 0]
                mi = raw[:, channel, orientation, 1]
                ope[:, channel, orientation, 1] = mt
                ope[:, channel, orientation, 2] = mi
                ope[:, channel, orientation, 0] = (
                    mt - mi if channel == 0 else mt + mi
                )
            ope[:, channel, 2] = ope[:, channel, 0] + ope[:, channel, 1]
            ope[:, channel, 3] = ope[:, channel, 0] - ope[:, channel, 1]
        twopt = (
            3.0 + rng.normal(size=(2, 1, nconf, 2, nt, 2))
            + 1j * rng.normal(size=(2, 1, nconf, 2, nt, 2))
        )
        result = calculate_gradient_flow_ratios(
            ope, twopt, [1, 2], do_jackknife=True
        )
        validate_gradient_flow_ratio_results(result, nconf=nconf)
        self.assertEqual(result["ratio"].shape, (2, 4, 3, 1, nz, 2, 3, 2))
        np.testing.assert_allclose(
            result["c2_mean"][0], result["c2_mean"][1], rtol=0, atol=0
        )
        phase = physical_helicity_ratio(result["ratio"])
        self.assertEqual(phase.shape, result["ratio"].shape[2:])
        self.assertTrue(np.isrealobj(phase))
        combined_phase = physical_helicity_ratio(
            result["ratio"], component="combined"
        )
        self.assertEqual(combined_phase.shape, result["ratio"].shape[3:])
        np.testing.assert_allclose(
            combined_phase, phase[0], rtol=0, atol=0
        )

    def test_npz_json_roundtrip_is_atomic_and_strict(self):
        from pyqcd.operator import (
            gradient_flow_gluon_ope, load_gradient_flow_gluon_ope,
            save_gradient_flow_gluon_ope,
        )

        data, metadata = gradient_flow_gluon_ope(
            _near_identity_su3(seed=7317), tau=0.0, z_count=1
        )
        with tempfile.TemporaryDirectory() as temporary:
            base = f"{temporary}/conf4150_tau0p000_eps0.010_zdir2"
            paths = save_gradient_flow_gluon_ope(base, data, metadata)
            self.assertTrue(all(path.endswith(suffix)
                                for path, suffix in zip(paths, (".npy", ".json"))))
            loaded, loaded_metadata = load_gradient_flow_gluon_ope(base)
        np.testing.assert_array_equal(loaded, data)
        self.assertEqual(loaded_metadata, metadata)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        GradientFlowGluonContract
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
