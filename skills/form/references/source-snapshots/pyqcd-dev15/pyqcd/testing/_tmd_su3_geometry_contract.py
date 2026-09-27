"""TMD bilocal 的 su(3) 去迹与空间几何行为契约。"""
from __future__ import annotations

import unittest

import numpy as np

from pyqcd.operator import plaquette_clover, staple_operator
from pyqcd.renorm import (
    gluon_tmd_operator,
    tmd_matrix_elements,
    tmd_matrix_elements_time,
)
from pyqcd.renorm._tmd import _matrix_element_from_fields
from pyqcd.testing import random_su3_gauge
from pyqcd.tools import set_backend


ERRORS: dict[str, float] = {}


def _manual_traceless(field):
    """测试侧手算 F -> F - Tr(F) I / Nc。"""
    nc = field.shape[-1]
    trace = np.trace(field, axis1=-2, axis2=-1)
    identity = np.eye(nc, dtype=field.dtype)
    return field - trace[..., None, None] * identity / nc


def _manual_shift(field, z, b_perp, z_dir, b_dir):
    endpoint = [0, 0, 0]
    endpoint[z_dir] += z
    endpoint[b_dir] += b_perp
    shifted = field
    for direction, offset in enumerate(endpoint):
        if offset:
            shifted = np.roll(shifted, -offset, axis=3 - direction)
    return shifted


def _manual_bilocal(left, right, wilson, z, b_perp, z_dir, b_dir):
    """手写 Tr[right(x) W left(y) W^dagger]。"""
    shifted = _manual_shift(left, z, b_perp, z_dir, b_dir)
    closed = right @ wilson @ shifted @ wilson.conj().swapaxes(-1, -2)
    return np.trace(closed, axis1=-2, axis2=-1)


def _manual_staple(gauge, z, b_perp, z_dir, b_dir, L):
    """逐点手写 -L*zdir -> b*bdir -> (L+z)*zdir 三段路径。"""
    lattice_shape = gauge.shape[:4]
    nc = gauge.shape[-1]
    out = np.empty(lattice_shape + (nc, nc), dtype=gauge.dtype)
    path = ((z_dir, -L), (b_dir, b_perp), (z_dir, L + z))

    for base in np.ndindex(*lattice_shape):
        pos = list(base)
        transporter = np.eye(nc, dtype=gauge.dtype)
        for direction, signed_length in path:
            axis = 3 - direction
            step = 1 if signed_length >= 0 else -1
            for _ in range(abs(signed_length)):
                if step > 0:
                    link = gauge[tuple(pos)][direction]
                    pos[axis] = (pos[axis] + 1) % lattice_shape[axis]
                else:
                    pos[axis] = (pos[axis] - 1) % lattice_shape[axis]
                    link = gauge[tuple(pos)][direction].conj().T
                transporter = transporter @ link
        out[base] = transporter
    return out


def _relabel_spatial_axes(gauge, new_to_old):
    """同时重标记空间坐标轴与链接方向；new_to_old[new]=old。"""
    q = tuple(new_to_old)
    coordinate_axes = (0, 3 - q[2], 3 - q[1], 3 - q[0], 4, 5, 6)
    relabeled = np.transpose(gauge, coordinate_axes)
    return relabeled[..., list(q) + [3], :, :]


def _relabel_scalar_field(field, new_to_old):
    q = tuple(new_to_old)
    return np.transpose(field, (0, 3 - q[2], 3 - q[1], 3 - q[0]))


class TmdSu3GeometryContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        set_backend("numpy")

    def tearDown(self):
        set_backend("numpy")

    def test_batch_default_uses_one_fixed_staple_length(self):
        """按 z 改变 staple 臂长会混合不同 rapidity regulator。"""
        gauge = random_su3_gauge(L=3, seed=7300)
        z_list = [0, 1, 2]
        b_list = [1]

        actual = tmd_matrix_elements_time(
            gauge, z_list, b_list, z_dir=2, b_dir=0)
        expected = tmd_matrix_elements_time(
            gauge, z_list, b_list, z_dir=2, b_dir=0, L=2)
        legacy = np.concatenate([
            tmd_matrix_elements_time(
                gauge, [z], b_list, z_dir=2, b_dir=0, L=abs(z))
            for z in z_list
        ], axis=0)

        fixed_error = float(np.max(np.abs(actual - expected)))
        legacy_sensitivity = float(np.max(np.abs(expected - legacy)))
        ERRORS["batch_fixed_staple"] = fixed_error
        ERRORS["batch_legacy_staple_sensitivity"] = legacy_sensitivity
        self.assertGreater(legacy_sensitivity, 1e-6)
        self.assertLess(fixed_error, 1e-10)

    def test_adjoint_color_normalization_is_twice_fundamental_trace(self):
        """标准生成元归一化下 F^a W_adj^ab F^b = 2 Tr[F W F W†]。"""
        field = np.zeros((1, 1, 1, 1, 3, 3), dtype=np.complex128)
        field[..., 0, 0] = 0.5
        field[..., 1, 1] = -0.5
        wilson = np.broadcast_to(
            np.eye(3, dtype=np.complex128), field.shape).copy()

        try:
            fundamental = np.asarray(_matrix_element_from_fields(
                field, field, wilson, z=0, b_perp=0, z_dir=2, b_dir=0,
                color_normalization='fundamental_trace'))
            adjoint = np.asarray(_matrix_element_from_fields(
                field, field, wilson, z=0, b_perp=0, z_dir=2, b_dir=0,
                color_normalization='adjoint'))
        except TypeError as exc:
            self.fail(f'缺少显式颜色归一化接口: {exc}')

        np.testing.assert_allclose(fundamental, 0.5, rtol=0.0, atol=0.0)
        np.testing.assert_allclose(adjoint, 1.0, rtol=0.0, atol=0.0)

    def test_identity_contamination_drops_out_of_bilocal(self):
        """F+c(x)I 不得改变逐点 su(3) bilocal，且保留 complex64。"""
        rng = np.random.default_rng(7301)
        shape = (1, 2, 2, 2, 3, 3)
        left = (rng.normal(size=shape) + 1j * rng.normal(size=shape)).astype(
            np.complex64)
        right = (rng.normal(size=shape) + 1j * rng.normal(size=shape)).astype(
            np.complex64)
        left = _manual_traceless(left)
        right = _manual_traceless(right)
        wilson = random_su3_gauge(L=2, seed=7302)[..., 0, :, :].astype(
            np.complex64)
        identity = np.eye(3, dtype=np.complex64)
        c_left = (rng.normal(size=shape[:4])
                  + 1j * rng.normal(size=shape[:4])).astype(np.complex64)
        c_right = (rng.normal(size=shape[:4])
                   + 1j * rng.normal(size=shape[:4])).astype(np.complex64)

        expected = _manual_bilocal(
            left, right, wilson, z=1, b_perp=1, z_dir=2, b_dir=0)
        clean = np.asarray(_matrix_element_from_fields(
            left, right, wilson, z=1, b_perp=1, z_dir=2, b_dir=0))
        polluted = np.asarray(_matrix_element_from_fields(
            left + c_left[..., None, None] * identity,
            right + c_right[..., None, None] * identity,
            wilson, z=1, b_perp=1, z_dir=2, b_dir=0))

        clean_error = float(np.max(np.abs(clean - expected)))
        pollution_error = float(np.max(np.abs(polluted - expected)))
        ERRORS["identity_clean"] = clean_error
        ERRORS["identity_pollution"] = pollution_error
        self.assertEqual(clean.dtype, np.dtype(np.complex64))
        self.assertEqual(polluted.dtype, np.dtype(np.complex64))
        self.assertLess(clean_error, 2e-5)
        self.assertLess(pollution_error, 2e-5)

    def test_public_staple_uses_traceless_clover(self):
        """operator.staple_operator 必须消费同一逐点去迹 bilocal。"""
        gauge = random_su3_gauge(L=2, seed=7303).astype(np.complex64)
        field_raw = np.asarray(plaquette_clover(gauge, 3, 1))
        field = _manual_traceless(field_raw)
        wilson = _manual_staple(
            gauge, z=1, b_perp=1, z_dir=2, b_dir=0, L=1)
        expected = _manual_bilocal(
            field, field, wilson, z=1, b_perp=1, z_dir=2, b_dir=0)
        raw_result = _manual_bilocal(
            field_raw, field_raw, wilson, z=1, b_perp=1,
            z_dir=2, b_dir=0)
        actual = np.asarray(staple_operator(
            gauge, 3, 1, z=1, b_perp=1, z_dir=2, b_dir=0))

        error = float(np.max(np.abs(actual - expected)))
        fixture_sensitivity = float(np.max(np.abs(raw_result - expected)))
        ERRORS["public_staple_traceless"] = error
        ERRORS["public_staple_trace_sensitivity"] = fixture_sensitivity
        self.assertEqual(actual.dtype, gauge.dtype)
        self.assertGreater(fixture_sensitivity, 1e-5)
        self.assertLess(error, 2e-5)

    def test_spatial_axis_relabeling_is_covariant_for_all_z_dirs(self):
        """空间轴与方向标签同步重标记后，局域标量及批量和必须协变。"""
        gauge = random_su3_gauge(L=2, seed=7304)
        base = np.asarray(gluon_tmd_operator(
            gauge, z=1, b_perp=1, z_dir=2, b_dir=0, L=1))
        base_time = tmd_matrix_elements_time(
            gauge, [1], [1], z_dir=2, b_dir=0, L=1)[0, 0]

        permutations = (
            (0, 1, 2),  # z_dir=2
            (2, 0, 1),  # z_dir=0
            (1, 2, 0),  # z_dir=1
        )
        for q in permutations:
            with self.subTest(new_to_old=q):
                relabeled = _relabel_spatial_axes(gauge, q)
                z_dir = q.index(2)
                b_dir = q.index(0)
                actual = np.asarray(gluon_tmd_operator(
                    relabeled, z=1, b_perp=1,
                    z_dir=z_dir, b_dir=b_dir, L=1))
                expected = _relabel_scalar_field(base, q)
                local_error = float(np.max(np.abs(actual - expected)))

                actual_time = tmd_matrix_elements_time(
                    relabeled, [1], [1], z_dir=z_dir,
                    b_dir=b_dir, L=1)[0, 0]
                batch_error = float(np.max(np.abs(actual_time - base_time)))
                ERRORS[f"axis_relabel_local_z{z_dir}"] = local_error
                ERRORS[f"axis_relabel_batch_z{z_dir}"] = batch_error
                self.assertLess(local_error, 1e-10)
                self.assertLess(batch_error, 1e-10)

    def test_invalid_boolean_and_conflicting_directions_are_rejected(self):
        """方向必须是非布尔空间整数，且 z_dir 与 b_dir 不得相同。"""
        gauge = random_su3_gauge(L=2, seed=7305)
        cases = (
            ("gluon_bool_z", lambda: gluon_tmd_operator(
                gauge, 0, 0, z_dir=True, b_dir=0, L=0)),
            ("batch_bool_b", lambda: tmd_matrix_elements(
                gauge, [], [0], z_dir=2, b_dir=False, L=0)),
            ("batch_time_bool_z", lambda: tmd_matrix_elements_time(
                gauge, [], [0], z_dir=np.bool_(False), b_dir=1, L=0)),
            ("operator_float", lambda: staple_operator(
                gauge, 3, 0, 0, 0, z_dir=2.0, b_dir=0)),
            ("invalid_label", lambda: gluon_tmd_operator(
                gauge, 0, 0, z_dir=3, b_dir=0, L=0)),
            ("conflict", lambda: staple_operator(
                gauge, 3, 0, 0, 0, z_dir=1, b_dir=1)),
        )
        for name, call in cases:
            with self.subTest(case=name):
                try:
                    call()
                except ValueError:
                    continue
                except Exception as exc:
                    self.fail(
                        f"应抛 ValueError，实际 {type(exc).__name__}: {exc}")
                else:
                    self.fail("应抛 ValueError，实际未拒绝")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        TmdSu3GeometryContract)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print("numeric errors:")
    for name, value in sorted(ERRORS.items()):
        print(f"  {name}: {value:.3e}")
    raise SystemExit(0 if result.wasSuccessful() else 1)
