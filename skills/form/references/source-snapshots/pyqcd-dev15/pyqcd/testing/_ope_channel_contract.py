"""TDD contracts for explicit straight-line gluon OPE channels.

This contract is intentionally standalone because the task write boundary does
not include the central registry.  Run it directly with::

    python -m pyqcd.testing._ope_channel_contract

The direct z=0 oracles distinguish ``F.F`` from ``F.Ftilde``.  No relation
between the +z and -z nonlocal operators is assumed beyond their common local
z=0 limit.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import h5py
import numpy as np


_SHAPE = (2, 2, 2, 2)
_COMPONENTS = ((0, 1), (3, 0), (3, 1))


def _random_su3_gauge(seed=7311, dtype=np.complex128):
    """Small periodic SU(3) fixture in the repository's tzyx layout."""
    rng = np.random.default_rng(seed)
    gauge = np.empty(_SHAPE + (4, 3, 3), dtype=dtype)
    for index in np.ndindex(*_SHAPE, 4):
        matrix = rng.normal(size=(3, 3)) + 1j * rng.normal(size=(3, 3))
        q, r = np.linalg.qr(matrix)
        phase = np.diag(r)
        phase = np.divide(
            phase, np.abs(phase),
            out=np.ones_like(phase), where=np.abs(phase) > 0)
        q = q @ np.diag(phase)
        q *= np.linalg.det(q) ** (-1.0 / 3.0)
        gauge[index] = q.astype(dtype, copy=False)
    return gauge


def _near_identity_su3_gauge(seed, epsilon=0.12, dtype=np.complex128):
    """Fixed-seed nontrivial near-identity SU(3) fixture in tzyx layout."""
    rng = np.random.default_rng(seed)
    gauge = np.empty(_SHAPE + (4, 3, 3), dtype=dtype)
    identity = np.eye(3, dtype=np.complex128)
    for index in np.ndindex(*_SHAPE, 4):
        matrix = rng.normal(size=(3, 3)) + 1j * rng.normal(size=(3, 3))
        hermitian = (matrix + matrix.conj().T) / 2.0
        hermitian -= np.trace(hermitian) * identity / 3.0
        eigenvalues, eigenvectors = np.linalg.eigh(hermitian)
        phases = np.exp(1j * epsilon * eigenvalues)
        unitary = (eigenvectors * phases) @ eigenvectors.conj().T
        unitary *= np.linalg.det(unitary) ** (-1.0 / 3.0)
        gauge[index] = unitary.astype(dtype, copy=False)
    return gauge


def _random_su3_field(seed=7312):
    """Local SU(3) matrices used for a gauge-transformation oracle."""
    rng = np.random.default_rng(seed)
    field = np.empty(_SHAPE + (3, 3), dtype=np.complex128)
    for index in np.ndindex(*_SHAPE):
        matrix = rng.normal(size=(3, 3)) + 1j * rng.normal(size=(3, 3))
        q, r = np.linalg.qr(matrix)
        phase = np.diag(r)
        phase = np.divide(
            phase, np.abs(phase),
            out=np.ones_like(phase), where=np.abs(phase) > 0)
        q = q @ np.diag(phase)
        q *= np.linalg.det(q) ** (-1.0 / 3.0)
        field[index] = q
    return field


def _gauge_transform(gauge, transformation):
    """Apply U_mu(x) -> G(x) U_mu(x) G(x+mu)^dagger."""
    transformed = np.empty_like(gauge)
    for mu in range(4):
        axis = 3 - mu
        g_forward = np.roll(transformation, -1, axis=axis)
        transformed[..., mu, :, :] = (
            transformation @ gauge[..., mu, :, :] @ g_forward.conj().transpose(
                0, 1, 2, 3, 5, 4))
    return transformed


def _epsilon4(i, j, k, l):
    if len({i, j, k, l}) != 4:
        return 0
    values = (i, j, k, l)
    inversions = sum(
        values[left] > values[right]
        for left in range(4) for right in range(left + 1, 4))
    return -1 if inversions % 2 else 1


def _canonical_pair(mu, nu):
    return (mu, nu) if mu < nu else (nu, mu)


def _signed_field(fields, mu, nu):
    field = fields[_canonical_pair(mu, nu)]
    return field if mu < nu else -field


def _raw_plaquette_clover(gauge, mu, nu):
    """Test-side raw four-leaf Clover from the tzyx gauge layout.

    The link direction ``mu`` occupies coordinate axis ``3 - mu`` because
    gauge coordinates are ``(t, z, y, x, mu, color, color)`` and
    ``mu=(0, 1, 2, 3)`` means ``(x, y, z, t)``.  A positive coordinate shift
    therefore uses ``np.roll(..., -1, axis=3-mu)``.  The four explicit paths
    below are P_{mu,nu}, P_{nu,-mu}, P_{-mu,-nu}, and P_{-nu,mu}; no
    production field-strength or path helper is involved.
    """
    reverse = mu > nu
    if reverse:
        mu, nu = nu, mu
    axis_mu = 3 - mu
    axis_nu = 3 - nu
    u_mu = gauge[..., mu, :, :]
    u_nu = gauge[..., nu, :, :]

    def dagger(value):
        return value.conj().swapaxes(-1, -2)

    # P_{mu,nu}(x): +mu, +nu, -mu, -nu.
    p1 = u_mu @ np.roll(u_nu, -1, axis=axis_mu)
    p1 = p1 @ dagger(np.roll(u_mu, -1, axis=axis_nu))
    p1 = p1 @ dagger(u_nu)

    # P_{nu,-mu}(x): +nu, -mu, -nu, +mu.
    u_mu_nu_minus_mu = np.roll(u_mu, -1, axis=axis_nu)
    u_mu_nu_minus_mu = np.roll(u_mu_nu_minus_mu, 1, axis=axis_mu)
    p2 = u_nu @ dagger(u_mu_nu_minus_mu)
    p2 = p2 @ dagger(np.roll(u_nu, 1, axis=axis_mu))
    p2 = p2 @ np.roll(u_mu, 1, axis=axis_mu)

    # P_{-mu,-nu}(x): -mu, -nu, +mu, +nu.
    u_nu_minus_mu_minus_nu = np.roll(u_nu, 1, axis=axis_mu)
    u_nu_minus_mu_minus_nu = np.roll(
        u_nu_minus_mu_minus_nu, 1, axis=axis_nu)
    u_mu_minus_mu_minus_nu = np.roll(u_mu, 1, axis=axis_mu)
    u_mu_minus_mu_minus_nu = np.roll(
        u_mu_minus_mu_minus_nu, 1, axis=axis_nu)
    p3 = dagger(np.roll(u_mu, 1, axis=axis_mu))
    p3 = p3 @ dagger(u_nu_minus_mu_minus_nu)
    p3 = p3 @ u_mu_minus_mu_minus_nu
    p3 = p3 @ np.roll(u_nu, 1, axis=axis_nu)

    # P_{-nu,mu}(x): -nu, +mu, +nu, -mu.
    u_nu_plus_mu_minus_nu = np.roll(u_nu, -1, axis=axis_mu)
    u_nu_plus_mu_minus_nu = np.roll(
        u_nu_plus_mu_minus_nu, 1, axis=axis_nu)
    p4 = dagger(np.roll(u_nu, 1, axis=axis_nu))
    p4 = p4 @ np.roll(u_mu, 1, axis=axis_nu)
    p4 = p4 @ u_nu_plus_mu_minus_nu
    p4 = p4 @ dagger(u_mu)

    antihermitian = sum(
        (plaquette - dagger(plaquette)
         for plaquette in (p1, p2, p3, p4)),
        start=np.zeros_like(p1))
    field = -1j * antihermitian / 8.0
    return -field if reverse else field


def _direct_legacy_plus_oracle(gauge, mu, nu, z_dir, delta_z):
    """Independent +z F.Ftilde roll/matrix oracle for docker legacy semantics."""
    fields = {
        pair: _raw_plaquette_clover(gauge, *pair)
        for pair in ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))}
    first = _signed_field(fields, mu, nu)
    dual = None
    for rho in range(4):
        for sigma in range(4):
            coefficient = 0.5 * _epsilon4(mu, nu, rho, sigma)
            if coefficient == 0:
                continue
            term = coefficient * _signed_field(fields, rho, sigma)
            dual = term if dual is None else dual + term

    axis = 3 - z_dir
    links = gauge[..., z_dir, :, :]
    expected = np.zeros((delta_z, _SHAPE[0]), dtype=np.float64)
    for zi in range(delta_z):
        if zi == 0:
            transported = first @ dual
        else:
            transported = np.roll(first, -zi, axis=axis)
            for step in range(zi):
                link_dagger = np.roll(
                    links, -(zi - 1 - step), axis=axis).conj()
                link_dagger = link_dagger.swapaxes(-1, -2)
                transported = transported @ link_dagger
            transported = transported @ dual
            for step in range(zi):
                transported = transported @ np.roll(links, -step, axis=axis)
        trace = np.trace(transported, axis1=-2, axis2=-1)
        expected[zi] = np.sum(trace, axis=(1, 2, 3)).real
    return expected


def _canonical_json(payload):
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False)


def _spec(**overrides):
    from pyqcd.operator import OPEChannelSpec

    values = dict(
        mode="custom",
        mu=3,
        nu=0,
        mu2=3,
        nu2=0,
        z_dir=2,
        second_insert="Ftilde",
        direction=1,
        sum_kind="full",
        normalization="bare_spatial_sum",
        output_projection="complex",
        field_projection="legacy_untraced",
    )
    values.update(overrides)
    return OPEChannelSpec(**values)


class OPEChannelContractTests(unittest.TestCase):
    def setUp(self):
        from pyqcd.tools import set_backend

        set_backend("numpy")

    def test_spec_is_frozen_explicit_and_json_serializable(self):
        from pyqcd.operator import OPEChannelSpec

        spec = _spec()
        with self.assertRaises(FrozenInstanceError):
            spec.direction = -1
        payload = spec.to_dict()
        self.assertEqual(
            set(payload), {
                "mode", "mu", "nu", "mu2", "nu2", "z_dir",
                "second_insert", "direction", "sum_kind", "normalization",
                "output_projection", "field_projection"})
        self.assertEqual(json.loads(json.dumps(payload)), payload)

    def test_spec_rejects_invalid_enums_bool_and_degenerate_pairs(self):
        from pyqcd.operator import OPEChannelSpec

        invalid = (
            {"mode": "bad"},
            {"second_insert": "dual"},
            {"direction": 0},
            {"direction": True},
            {"direction": 1.0},
            {"z_dir": 3},
            {"z_dir": True},
            {"sum_kind": "transverse"},
            {"normalization": "volume_mean"},
            {"output_projection": "imag"},
            {"field_projection": "traceless"},
            {"field_projection": True},
            {"mu": True},
            {"mu": 0, "nu": 0},
            {"mu2": 1, "nu2": 1},
            {"mode": "unpolarized", "second_insert": "Ftilde"},
            {"mode": "helicity", "second_insert": "F"},
            {"mode": "legacy_dual", "second_insert": "F"},
        )
        for values in invalid:
            with self.subTest(values=values):
                with self.assertRaises((TypeError, ValueError)):
                    OPEChannelSpec(**dict(
                        mode="custom", mu=3, nu=0, mu2=3, nu2=0,
                        z_dir=2, second_insert="Ftilde", direction=1,
                        sum_kind="full", normalization="bare_spatial_sum",
                        output_projection="complex",
                        field_projection="legacy_untraced", **values))

    def test_compute_dtype_is_complex_only_and_follows_complex_gauge_dtype(self):
        from pyqcd.operator import gluon_ope_channel, gluon_ope_operator_z0

        gauge = _random_su3_gauge(seed=73201)
        for gauge_dtype, expected_dtype in (
                (np.complex64, np.dtype("complex64")),
                (np.complex128, np.dtype("complex128"))):
            typed_gauge = gauge.astype(gauge_dtype)
            direct = gluon_ope_operator_z0(
                typed_gauge, 3, 0, 2, 1, _SHAPE[0], _SHAPE[3])
            channel = gluon_ope_channel(
                typed_gauge, _spec(), delta_z=1,
                Nt=_SHAPE[0], Nx=_SHAPE[3])
            self.assertEqual(direct.dtype, expected_dtype)
            self.assertEqual(channel.dtype, expected_dtype)

        invalid = (
            np.float32, np.dtype("float64"), np.bool_, np.dtype("bool"),
            object, np.dtype("O"), "float32")
        for compute_dtype in invalid:
            with self.subTest(entry="operator", compute_dtype=compute_dtype):
                with self.assertRaises((TypeError, ValueError)):
                    gluon_ope_operator_z0(
                        gauge, 3, 0, 2, 1, _SHAPE[0], _SHAPE[3],
                        compute_dtype=compute_dtype)

            with self.subTest(entry="channel", compute_dtype=compute_dtype):
                def should_not_run(*_args, **_kwargs):
                    raise AssertionError("invalid compute_dtype reached operator")

                with self.assertRaises((TypeError, ValueError)):
                    gluon_ope_channel(
                        gauge, _spec(), delta_z=1,
                        Nt=_SHAPE[0], Nx=_SHAPE[3],
                        compute_dtype=compute_dtype, _operator=should_not_run)

        with self.assertRaises((TypeError, ValueError)):
            gluon_ope_operator_z0(
                gauge.real.astype(np.float64), 3, 0, 2, 1,
                _SHAPE[0], _SHAPE[3])

    def test_compute_dtype_accepts_torch_complex_dtype_tokens(self):
        from pyqcd.operator import gluon_ope_operator_z0

        try:
            import torch
        except ImportError as exc:
            self.skipTest(f"torch 未安装: {exc}")

        gauge = _random_su3_gauge(seed=73202)
        for torch_dtype, expected_dtype in (
                (torch.complex64, np.dtype("complex64")),
                (torch.complex128, np.dtype("complex128"))):
            with self.subTest(compute_dtype=torch_dtype):
                actual = gluon_ope_operator_z0(
                    gauge, 3, 0, 2, 1, _SHAPE[0], _SHAPE[3],
                    compute_dtype=torch_dtype,
                    output_projection="complex")
                self.assertEqual(actual.dtype, expected_dtype)

    def test_lorentz_assignment_validates_spatial_direction_and_closed_mode(self):
        from pyqcd.operator import get_ope_lorentz_pairs

        expected = {
            "unpol": [
                (3, 0, 3, 0), (3, 1, 3, 1), (0, 1, 0, 1)],
            "helicity": [
                (3, 0, 3, 0), (3, 1, 3, 1), (0, 1, 0, 1)],
            "gauge_fix_unpol": [
                (3, 0, 3, 0), (3, 1, 3, 1), (0, 1, 0, 1)],
            "gauge_fix_helicity": [
                (3, 0, 2, 1), (3, 1, 0, 2),
                (3, 2, 0, 1), (0, 1, 3, 2)],
        }
        for mode, pairs in expected.items():
            self.assertEqual(get_ope_lorentz_pairs(2, mode), pairs)

        for bad_zdir in (-1, 3, True, False, 1.0, None):
            with self.subTest(zdir=bad_zdir):
                with self.assertRaises((TypeError, ValueError)):
                    get_ope_lorentz_pairs(bad_zdir, "unpol")

        for bad_mode in ("bad", "UNPOL", True, None, 1):
            with self.subTest(mode=bad_mode):
                with self.assertRaises((TypeError, ValueError)):
                    get_ope_lorentz_pairs(2, bad_mode)

    def test_z0_FF_matches_independent_direct_matrix_oracle(self):
        from pyqcd.operator import gluon_ope_channel

        gauge = _near_identity_su3_gauge(seed=7321)
        spec = _spec(second_insert="F", output_projection="complex")
        actual = gluon_ope_channel(
            gauge, spec, delta_z=1, Nt=_SHAPE[0], Nx=_SHAPE[3])
        field = _raw_plaquette_clover(gauge, 3, 0)
        direct = np.einsum("...ab,...ba->...", field, field)
        expected = np.sum(direct, axis=(1, 2, 3))
        np.testing.assert_allclose(actual[0], expected, rtol=0, atol=2e-13)

    def test_z0_FFtilde_matches_independent_direct_matrix_oracle(self):
        from pyqcd.operator import gluon_ope_channel

        gauge = _near_identity_su3_gauge(seed=7322)
        spec = _spec(second_insert="Ftilde", output_projection="complex")
        actual = gluon_ope_channel(
            gauge, spec, delta_z=1, Nt=_SHAPE[0], Nx=_SHAPE[3])

        fields = {
            pair: _raw_plaquette_clover(gauge, *pair)
            for pair in ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))}
        dual = None
        for rho in range(4):
            for sigma in range(4):
                coefficient = 0.5 * _epsilon4(3, 0, rho, sigma)
                if coefficient == 0:
                    continue
                term = coefficient * _signed_field(fields, rho, sigma)
                dual = term if dual is None else dual + term
        first = _signed_field(fields, 3, 0)
        direct = np.einsum("...ab,...ba->...", first, dual)
        expected = np.sum(direct, axis=(1, 2, 3))
        np.testing.assert_allclose(actual[0], expected, rtol=0, atol=2e-13)

    def test_nonzero_plus_z_legacy_roll_oracle_covers_three_component_combination(self):
        from pyqcd.operator import OPEChannelSpec, gluon_ope_channel

        gauge = _near_identity_su3_gauge(seed=73221)
        actual = {}
        expected = {}
        for component in ((3, 0), (3, 1), (0, 1)):
            spec = OPEChannelSpec(
                mode="legacy_dual", mu=component[0], nu=component[1],
                mu2=component[0], nu2=component[1], z_dir=2,
                second_insert="Ftilde", direction=1, sum_kind="full",
                normalization="bare_spatial_sum", output_projection="real",
                field_projection="legacy_untraced")
            actual[component] = gluon_ope_channel(
                gauge, spec, delta_z=2, Nt=_SHAPE[0], Nx=_SHAPE[3])
            expected[component] = _direct_legacy_plus_oracle(
                gauge, component[0], component[1], 2, 2)
            np.testing.assert_allclose(
                actual[component], expected[component], rtol=0, atol=3e-13)

        actual_combined = (
            -actual[(3, 0)] - actual[(3, 1)] + 2.0 * actual[(0, 1)])
        expected_combined = (
            -expected[(3, 0)] - expected[(3, 1)] + 2.0 * expected[(0, 1)])
        np.testing.assert_allclose(
            actual_combined, expected_combined, rtol=0, atol=5e-13)

    def test_projection_is_explicit_and_none_keeps_legacy_inference(self):
        from pyqcd.operator import gluon_ope_channel, gluon_ope_operator_z0
        import pyqcd.operator._gluon_ope as implementation

        gauge = _random_su3_gauge(seed=7323)
        legacy = gluon_ope_operator_z0(
            gauge, 3, 0, 2, 2, _SHAPE[0], _SHAPE[3])
        legacy_value = gluon_ope_channel(
            gauge, _spec(output_projection="real"), delta_z=2,
            Nt=_SHAPE[0], Nx=_SHAPE[3])
        np.testing.assert_allclose(legacy, legacy_value)
        complex_spec = _spec(
            mu2=3, nu2=1, second_insert="F", output_projection="complex")
        real_spec = _spec(
            mu2=3, nu2=1, second_insert="F", output_projection="real")
        def nonhermitian_field(_gauge, mu, nu, *_args, **_kwargs):
            del _gauge
            result = np.zeros(_SHAPE + (3, 3), dtype=np.complex128)
            result[..., 0, 0] = 1.0 + 2.0j * (1 + mu + nu)
            result[..., 0, 1] = 0.25j * (1 + mu)
            result[..., 1, 1] = 0.5 - 0.1j * (1 + nu)
            return result

        with patch.object(
                implementation, "_field_strength",
                side_effect=nonhermitian_field):
            complex_value = gluon_ope_channel(
                gauge, complex_spec, delta_z=2,
                Nt=_SHAPE[0], Nx=_SHAPE[3])
            real_value = gluon_ope_channel(
                gauge, real_spec, delta_z=2,
                Nt=_SHAPE[0], Nx=_SHAPE[3])
        np.testing.assert_allclose(real_value, complex_value.real)
        self.assertGreater(np.max(np.abs(complex_value[1].imag)), 1e-12)

    def test_direction_validation_and_local_plus_minus_limit(self):
        from pyqcd.operator import gluon_ope_channel, gluon_ope_operator_z0

        gauge = _random_su3_gauge(seed=7324)
        plus = gluon_ope_channel(
            gauge, _spec(direction=1), delta_z=2,
            Nt=_SHAPE[0], Nx=_SHAPE[3])
        minus = gluon_ope_channel(
            gauge, _spec(direction=-1), delta_z=2,
            Nt=_SHAPE[0], Nx=_SHAPE[3])
        np.testing.assert_allclose(plus[0], minus[0], rtol=0, atol=2e-13)
        self.assertEqual(plus.shape, minus.shape)
        for value in (0, 2, True, -1.0):
            with self.subTest(direction=value):
                with self.assertRaises((TypeError, ValueError)):
                    gluon_ope_operator_z0(
                        gauge, 3, 0, 2, 1, _SHAPE[0], _SHAPE[3],
                        direction=value)
        with self.assertRaises((TypeError, ValueError)):
            gluon_ope_operator_z0(
                gauge, 3, 0, 2, 1, _SHAPE[0], _SHAPE[3],
                second_insert="not-an-insert")
        with self.assertRaises((TypeError, ValueError)):
            gluon_ope_operator_z0(
                gauge, 3, 0, 2, 1, _SHAPE[0], _SHAPE[3],
                field_projection="traceless")

    def test_canonical_pairs_avoid_reverse_duplicate_calls_and_cache_regresses(self):
        from pyqcd.operator import (
            FieldStrengthCache, OPEChannelSpec, gluon_ope_channel)
        import pyqcd.operator._gluon_ope as implementation

        gauge = _random_su3_gauge(seed=7325)
        spec = OPEChannelSpec(
            mode="legacy_dual", mu=3, nu=0, mu2=3, nu2=0, z_dir=2,
            second_insert="Ftilde", direction=1, sum_kind="full",
            normalization="bare_spatial_sum", output_projection="real",
            field_projection="legacy_untraced")
        with patch.object(
                implementation, "plaquette_clover",
                wraps=implementation.plaquette_clover) as spy:
            uncached = gluon_ope_channel(
                gauge, spec, delta_z=2, Nt=_SHAPE[0], Nx=_SHAPE[3])
        self.assertEqual(spy.call_count, 2)

        cache = FieldStrengthCache(gauge, max_entries=2)
        with patch.object(
                implementation, "plaquette_clover",
                wraps=implementation.plaquette_clover) as spy:
            cached = gluon_ope_channel(
                gauge, spec, delta_z=2, Nt=_SHAPE[0], Nx=_SHAPE[3],
                field_strength_cache=cache)
        self.assertEqual(spy.call_count, 2)
        self.assertTrue(all(mu < nu for mu, nu in cache.cached_pairs))
        self.assertLessEqual(len(cache.cached_pairs), 2)
        np.testing.assert_allclose(cached, uncached, rtol=0, atol=2e-13)

    def test_field_strength_cache_is_publicly_importable(self):
        from pyqcd.operator import FieldStrengthCache
        import pyqcd.operator._gluon_ope as implementation

        self.assertIs(FieldStrengthCache, implementation.FieldStrengthCache)

    def test_pipeline_uses_explicit_legacy_specs_and_keeps_combination(self):
        from pyqcd.pipeline import _steps as steps
        import pyqcd.operator._gluon_ope as implementation
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _random_su3_gauge(seed=7326)
        with tempfile.TemporaryDirectory() as run_dir, \
                patch.object(steps, "HAS_CUPY", True), \
                patch.object(steps, "NT", _SHAPE[0]), \
                patch.object(steps, "NX", _SHAPE[3]), \
                patch.object(steps, "get_gauge_path", return_value="fixture"), \
                patch.object(steps, "read_gauge_lime", return_value=gauge), \
                patch.object(steps, "_validate_gauge"), \
                patch.object(steps, "save_tensor_h5"), \
                patch.object(steps, "save_array"), \
                patch.object(steps, "free_gpu_memory"), \
                patch.object(steps, "log_gpu_memory"), \
                patch.object(
                    steps, "gluon_ope_channel",
                    wraps=steps.gluon_ope_channel) as channel_spy:
            result = steps.compute_ope_for_config(
                7326, run_dir, logger=None, precision="complex128",
                delta_z=2, z_dir=2, components=_COMPONENTS)

        self.assertEqual(channel_spy.call_count, len(_COMPONENTS))
        for call, component in zip(channel_spy.call_args_list, _COMPONENTS):
            spec = call.args[1]
            self.assertEqual(spec.mode, "legacy_dual")
            self.assertEqual((spec.mu, spec.nu), component)
            self.assertEqual((spec.mu2, spec.nu2), component)
            self.assertEqual(spec.second_insert, "Ftilde")
            self.assertEqual(spec.direction, 1)
            self.assertEqual(spec.sum_kind, "full")
            self.assertEqual(spec.normalization, "bare_spatial_sum")
            self.assertEqual(spec.output_projection, "real")
            self.assertEqual(spec.field_projection, "legacy_untraced")
        self.assertEqual(result["combined_spec"]["mode"], "legacy_dual")
        self.assertEqual(
            result["combined_spec"]["coefficients"], [-1.0, -1.0, 2.0])
        self.assertEqual(len(result["channel_specs"]), len(_COMPONENTS))
        json.dumps(result["channel_specs"])
        expected = (
            -result["components"][(3, 0)]
            - result["components"][(3, 1)]
            + 2.0 * result["components"][(0, 1)])
        np.testing.assert_allclose(result["combined"], expected)

    def test_fresh_pipeline_writes_canonical_ope_metadata_attrs(self):
        from pyqcd.pipeline import _steps as steps

        gauge = _random_su3_gauge(seed=73261)
        with tempfile.TemporaryDirectory() as run_dir, \
                patch.object(steps, "HAS_CUPY", True), \
                patch.object(steps, "NT", _SHAPE[0]), \
                patch.object(steps, "NX", _SHAPE[3]), \
                patch.object(steps, "get_gauge_path", return_value="fixture"), \
                patch.object(steps, "read_gauge_lime", return_value=gauge), \
                patch.object(steps, "_validate_gauge"), \
                patch.object(steps, "free_gpu_memory"), \
                patch.object(steps, "log_gpu_memory"):
            result = steps.compute_ope_for_config(
                73261, run_dir, logger=None, precision="complex128",
                delta_z=2, z_dir=2, components=_COMPONENTS)
            combined_path = (
                Path(run_dir) / "data" / "conf73261" /
                "ope_combined_conf73261.h5")
            self.assertTrue(combined_path.exists())
            with h5py.File(combined_path, "r") as handle:
                self.assertEqual(handle.attrs["pyqcd_ope_metadata_schema"], "1")
                channel_text = handle.attrs["pyqcd_ope_channel_specs_json"]
                combined_text = handle.attrs["pyqcd_ope_combined_spec_json"]
            if isinstance(channel_text, bytes):
                channel_text = channel_text.decode("utf-8")
            if isinstance(combined_text, bytes):
                combined_text = combined_text.decode("utf-8")
            self.assertEqual(
                channel_text, _canonical_json(json.loads(channel_text)))
            self.assertEqual(
                combined_text, _canonical_json(json.loads(combined_text)))
            self.assertEqual(
                json.loads(channel_text), result["channel_specs"])
            self.assertEqual(
                json.loads(combined_text), result["combined_spec"])
            loaded = steps.load_ope(run_dir)
            self.assertEqual(loaded[73261]["metadata_status"], "validated")
            self.assertEqual(
                loaded[73261]["channel_specs"], result["channel_specs"])

    def test_component_files_without_strict_contract_are_recomputed(self):
        from pyqcd.pipeline import _steps as steps
        from pyqcd.tools import set_backend

        set_backend("numpy")
        gauge = _random_su3_gauge(seed=7327)
        with tempfile.TemporaryDirectory() as run_dir:
            cdir = Path(run_dir) / "data" / "conf7327"
            cdir.mkdir(parents=True)
            for mu, nu in _COMPONENTS:
                (cdir / f"ops_mu{mu}_nu{nu}_dz2_conf7327.h5").touch()

            with patch.object(steps, "HAS_CUPY", True), \
                    patch.object(steps, "NT", _SHAPE[0]), \
                    patch.object(steps, "NX", _SHAPE[3]), \
                    patch.object(steps, "get_gauge_path",
                                 return_value="fixture"), \
                    patch.object(steps, "read_gauge_lime",
                                 return_value=gauge), \
                    patch.object(steps, "_validate_gauge"), \
                    patch.object(steps, "free_gpu_memory"), \
                    patch.object(steps, "log_gpu_memory"), \
                    patch.object(
                        steps, "gluon_ope_channel",
                        wraps=steps.gluon_ope_channel) as channel_spy:
                result = steps.compute_ope_for_config(
                    7327, run_dir, logger=None, precision="complex128",
                    delta_z=2, z_dir=2, components=_COMPONENTS)

            self.assertEqual(channel_spy.call_count, len(_COMPONENTS))
            self.assertEqual(result["metadata_status"], "validated")
            for mu, nu in _COMPONENTS:
                path = cdir / f"ops_mu{mu}_nu{nu}_dz2_conf7327.h5"
                with h5py.File(path, "r") as handle:
                    self.assertIn("pyqcd_cache_contract_json", handle.attrs)

    def test_legacy_ope_is_load_only_and_not_a_compute_cache_hit(self):
        from pyqcd.pipeline import _steps as steps
        from pyqcd.tools import set_backend
        from pyqcd.tools._io import save_tensor_h5

        set_backend("numpy")
        gauge = _random_su3_gauge(seed=73271)
        with tempfile.TemporaryDirectory() as run_dir:
            cdir = Path(run_dir) / "data" / "conf73271"
            cdir.mkdir(parents=True)
            arrays = {
                pair: np.full((2, 2), complex(index + 1))
                for index, pair in enumerate(_COMPONENTS)}
            for pair, array in arrays.items():
                save_tensor_h5(
                    array,
                    cdir / f"ops_mu{pair[0]}_nu{pair[1]}_dz2_conf73271.h5")
            old_combined = (
                -arrays[(3, 0)] - arrays[(3, 1)] + 2 * arrays[(0, 1)])
            save_tensor_h5(
                old_combined, cdir / "ope_combined_conf73271.h5")

            legacy = steps.load_ope(run_dir)[73271]
            self.assertEqual(legacy["metadata_status"], "missing")

            with patch.object(steps, "HAS_CUPY", True), \
                    patch.object(steps, "NT", _SHAPE[0]), \
                    patch.object(steps, "NX", _SHAPE[3]), \
                    patch.object(steps, "get_gauge_path",
                                 return_value="fixture"), \
                    patch.object(steps, "read_gauge_lime",
                                 return_value=gauge), \
                    patch.object(steps, "_validate_gauge"), \
                    patch.object(steps, "free_gpu_memory"), \
                    patch.object(steps, "log_gpu_memory"), \
                    patch.object(
                        steps, "gluon_ope_channel",
                        wraps=steps.gluon_ope_channel) as channel_spy:
                result = steps.compute_ope_for_config(
                    73271, run_dir, logger=None, precision="complex128",
                    delta_z=2, z_dir=2, components=_COMPONENTS)

            self.assertEqual(channel_spy.call_count, len(_COMPONENTS))
            self.assertEqual(result["metadata_status"], "validated")
            refreshed = steps.load_ope(run_dir)[73271]
            self.assertEqual(refreshed["metadata_status"], "validated")

    def test_load_ope_rejects_noncanonical_or_incomplete_metadata_without_fabrication(self):
        from pyqcd.pipeline import _steps as steps

        with tempfile.TemporaryDirectory() as run_dir:
            cdir = Path(run_dir) / "data" / "conf73272"
            cdir.mkdir(parents=True)
            path = cdir / "ope_combined_conf73272.h5"
            with h5py.File(path, "w") as handle:
                handle.create_dataset("data", data=np.zeros((2, 2)))
                handle.attrs["pyqcd_ope_metadata_schema"] = "1"
                handle.attrs["pyqcd_ope_channel_specs_json"] = "{}"
                # Missing combined-spec attr is an invalid/incomplete cache.
            loaded = steps.load_ope(run_dir)

        self.assertEqual(loaded[73272]["metadata_status"], "invalid")
        self.assertNotIn("channel_specs", loaded[73272])
        self.assertNotIn("combined_spec", loaded[73272])

    def test_load_ope_reports_legacy_metadata_missing(self):
        from pyqcd.pipeline import _steps as steps

        with tempfile.TemporaryDirectory() as run_dir:
            cdir = Path(run_dir) / "data" / "conf7327"
            cdir.mkdir(parents=True)
            with h5py.File(cdir / "ope_combined_conf7327.h5", "w") as handle:
                handle.create_dataset("data", data=np.zeros((2, 2)))
            with patch.object(
                    steps, "_load_any",
                    return_value=np.zeros((2, 2), dtype=np.complex128)):
                loaded = steps.load_ope(run_dir)

        entry = loaded[7327]
        self.assertEqual(entry["metadata_status"], "missing")
        self.assertNotIn("channel_specs", entry)
        self.assertNotIn("combined_spec", entry)

    def test_full_sum_ope_is_invariant_under_local_gauge_transform(self):
        from pyqcd.operator import gluon_ope_channel

        gauge = _random_su3_gauge(seed=7328)
        transformed = _gauge_transform(gauge, _random_su3_field(seed=7329))
        spec = _spec(output_projection="complex", second_insert="Ftilde")
        original = gluon_ope_channel(
            gauge, spec, delta_z=2, Nt=_SHAPE[0], Nx=_SHAPE[3])
        transformed_value = gluon_ope_channel(
            transformed, spec, delta_z=2, Nt=_SHAPE[0], Nx=_SHAPE[3])
        np.testing.assert_allclose(
            transformed_value, original, rtol=3e-11, atol=3e-11)


if __name__ == "__main__":
    unittest.main(verbosity=2)
