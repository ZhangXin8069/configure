"""公开 ``pyqcd.operator.staple_operator`` 的物理契约回归测试。"""
from __future__ import annotations

import unittest

import numpy as np

from pyqcd.operator import plaquette_clover, staple_operator
from pyqcd.testing import _gauge_transform, random_su3_gauge
from pyqcd.tools import set_backend


ERRORS: dict[str, float] = {}


def _manual_traceless(field):
    """测试侧逐点手算 F -> F - Tr(F) I / Nc。"""
    nc = field.shape[-1]
    trace = np.trace(field, axis1=-2, axis2=-1)
    identity = np.eye(nc, dtype=field.dtype)
    return field - trace[..., None, None] * identity / nc


def _run_public_operator(*args, **kwargs):
    """把公开 API 的运行时崩溃转成契约断言失败，保留原异常为原因。"""
    try:
        return np.asarray(staple_operator(*args, **kwargs))
    except Exception as exc:
        raise AssertionError(
            f"staple_operator 必须返回逐格点双局域量，实际异常: {exc}"
        ) from exc


def _manual_staple(gauge, z, b_perp, z_dir, b_dir, *, L=None,
                   legacy_axes=False):
    """逐点构造 x -> x-Lz -> x-Lz+b -> x+z+b。"""
    lattice_shape = gauge.shape[:4]
    out = np.empty(lattice_shape + gauge.shape[-2:], dtype=gauge.dtype)
    if L is None:
        L = abs(z)
    path = ((z_dir, -L), (b_dir, b_perp), (z_dir, L + z))

    for base in np.ndindex(*lattice_shape):
        pos = list(base)
        transporter = np.eye(gauge.shape[-1], dtype=gauge.dtype)
        for direction, signed_length in path:
            axis = 1 + direction if legacy_axes else 3 - direction
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


def _shift_to_endpoint(field, z, b_perp, z_dir, b_dir):
    endpoint = [0, 0, 0]
    endpoint[z_dir] += z
    endpoint[b_dir] += b_perp
    shifted = field
    for direction, offset in enumerate(endpoint):
        if offset:
            shifted = np.roll(shifted, -offset, axis=3 - direction)
    return shifted


def _manual_same_pair_bilocal(gauge, mu, nu, z, b_perp, z_dir, b_dir,
                              L=None):
    """独立几何参考：Tr[F(x) W(x,y) F(y) W^dagger(x,y)]。"""
    field = _manual_traceless(
        np.asarray(plaquette_clover(gauge, mu, nu)))
    shifted = _shift_to_endpoint(field, z, b_perp, z_dir, b_dir)
    wilson = _manual_staple(gauge, z, b_perp, z_dir, b_dir, L=L)
    closed = field @ wilson @ shifted @ wilson.conj().swapaxes(-1, -2)
    return np.trace(closed, axis1=-2, axis2=-1)


class StapleOperatorContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        set_backend("numpy")

    def test_explicit_three_segment_path_and_endpoint(self):
        """公开 API 必须运行并复现三段路径及 y=x+z*zdir+b*bdir 端点。"""
        gauge = random_su3_gauge(L=3, seed=701)
        expected = _manual_same_pair_bilocal(
            gauge, 3, 1, z=1, b_perp=1, z_dir=2, b_dir=0)
        actual = _run_public_operator(
            gauge, 3, 1, z=1, b_perp=1, z_dir=2, b_dir=0)

        self.assertEqual(actual.shape, gauge.shape[:4])
        error = float(np.max(np.abs(actual - expected)))
        ERRORS["three_segment_endpoint"] = error
        self.assertLess(error, 1e-11)

    def test_public_operator_accepts_fixed_staple_length(self):
        """公开入口必须允许扫描调用者固定 rapidity-regulator 臂长。"""
        gauge = random_su3_gauge(L=3, seed=700)
        expected = _manual_same_pair_bilocal(
            gauge, 3, 1, z=1, b_perp=1, z_dir=2, b_dir=0, L=2)
        actual = _run_public_operator(
            gauge, 3, 1, z=1, b_perp=1, z_dir=2, b_dir=0, L=2)
        legacy = _run_public_operator(
            gauge, 3, 1, z=1, b_perp=1, z_dir=2, b_dir=0)

        error = float(np.max(np.abs(actual - expected)))
        sensitivity = float(np.max(np.abs(actual - legacy)))
        ERRORS["explicit_fixed_length"] = error
        ERRORS["fixed_length_sensitivity"] = sensitivity
        self.assertGreater(sensitivity, 1e-6)
        self.assertLess(error, 1e-11)

    def test_public_operator_exposes_adjoint_color_normalization(self):
        """公开算符必须显式区分参考代码基础迹与理论伴随约定。"""
        gauge = random_su3_gauge(L=3, seed=699)
        fundamental = _run_public_operator(
            gauge, 3, 1, z=1, b_perp=1, L=2,
            color_normalization='fundamental_trace')
        adjoint = _run_public_operator(
            gauge, 3, 1, z=1, b_perp=1, L=2,
            color_normalization='adjoint')
        np.testing.assert_allclose(adjoint, 2.0 * fundamental,
                                   rtol=0.0, atol=0.0)

    def test_local_gauge_invariance(self):
        """双场强闭合色迹在逐点 SU(3) 规范变换下必须不变。"""
        gauge = random_su3_gauge(L=3, seed=702)
        site_transform = random_su3_gauge(L=3, seed=802)[..., 0, :, :]
        transformed = _gauge_transform(gauge, site_transform)

        original = _run_public_operator(
            gauge, 3, 0, z=1, b_perp=1, z_dir=2, b_dir=1)
        rotated = _run_public_operator(
            transformed, 3, 0, z=1, b_perp=1, z_dir=2, b_dir=1)
        error = float(np.max(np.abs(rotated - original)))
        ERRORS["gauge_invariance"] = error
        self.assertLess(error, 1e-10)

    def test_zero_separation_is_local_field_strength_square(self):
        """z=b=0 时 W=1、y=x，故 M=Tr[F_mu_nu(x)^2]。"""
        gauge = random_su3_gauge(L=3, seed=703)
        field = _manual_traceless(
            np.asarray(plaquette_clover(gauge, 3, 0)))
        expected = np.trace(field @ field, axis1=-2, axis2=-1)
        actual = _run_public_operator(
            gauge, 3, 0, z=0, b_perp=0, z_dir=2, b_dir=0)

        error = float(np.max(np.abs(actual - expected)))
        ERRORS["zero_separation"] = error
        self.assertLess(error, 1e-12)

    def test_direction_labels_use_tzyx_lattice_axes(self):
        """link 方向 0=x,1=y,2=z 必须映射到数组轴 3-dir。"""
        gauge = random_su3_gauge(L=3, seed=704)
        expected = _manual_same_pair_bilocal(
            gauge, 3, 1, z=1, b_perp=1, z_dir=0, b_dir=2)
        actual = _run_public_operator(
            gauge, 3, 1, z=1, b_perp=1, z_dir=0, b_dir=2)
        error = float(np.max(np.abs(actual - expected)))
        ERRORS["direction_axes"] = error

        correct_wilson = _manual_staple(
            gauge, 1, 1, z_dir=0, b_dir=2)
        legacy_wilson = _manual_staple(
            gauge, 1, 1, z_dir=0, b_dir=2, legacy_axes=True)
        fixture_sensitivity = float(np.max(
            np.abs(correct_wilson - legacy_wilson)))
        ERRORS["axis_fixture_sensitivity"] = fixture_sensitivity

        self.assertLess(error, 1e-11)
        self.assertGreater(fixture_sensitivity, 1e-3)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        StapleOperatorContract)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print("numeric errors:")
        for name, value in sorted(ERRORS.items()):
            print(f"  {name}: {value:.3e}")
    raise SystemExit(0 if result.wasSuccessful() else 1)
