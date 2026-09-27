"""VdV/VVV interleaved-f8 binary reader contract tests.

This module is intentionally independent from ``pyqcd.testing.__init__`` and
the main conftest dispatcher.  Run it with::

    python -m pyqcd.testing._io_binary_contract -v
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import pyqcd.tools._io as io_module
from pyqcd.tools import readin_vdv_all, readin_vvv, readin_vvv_all


_FLOAT_DTYPES = {
    "native": np.dtype("=f8"),
    "little": np.dtype("<f8"),
    "big": np.dtype(">f8"),
}


def _write_interleaved(path, values, byteorder="native"):
    """Write a small, deterministic [real, imag] float64 fixture."""
    values = np.asarray(values, dtype=np.complex128)
    pairs = np.empty(values.shape + (2,), dtype=_FLOAT_DTYPES[byteorder])
    pairs[..., 0] = values.real
    pairs[..., 1] = values.imag
    pairs.tofile(path)


class VertexProductBinaryContractTests(unittest.TestCase):
    """Behavioral contract for VdV and both VVV storage layouts."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.Nt, self.nev, self.nev1 = 2, 3, 2

        vdv_real = np.arange(self.Nt * self.nev**2, dtype=np.float64)
        self.vdv = vdv_real.reshape(self.Nt, self.nev, self.nev)
        self.vdv = self.vdv + 1j * (100.0 + self.vdv)

        vvv_real = np.arange(
            self.Nt * self.nev**3, dtype=np.float64)
        self.vvv = vvv_real.reshape(
            self.Nt, self.nev, self.nev, self.nev)
        self.vvv = self.vvv + 1j * (1000.0 + self.vvv)

    def tearDown(self):
        self._tmp.cleanup()

    def _vdv_path(self, momentum=(0, 0, 0)):
        px, py, pz = momentum
        return self.root / f"VdaggerV.Px{px}Py{py}Pz{pz}.conf77"

    def _vvv_block_path(self, momentum=(0, 0, 0)):
        px, py, pz = momentum
        return self.root / f"VVV.Px{px}Py{py}Pz{pz}.conf77"

    def _vvv_slice_path(self, t, momentum=(0, 0, 0)):
        px, py, pz = momentum
        return self.root / f"VVV.t{t:03d}.Px{px}Py{py}Pz{pz}.conf77"

    def _write_complete_fixture(self, byteorder="native", momentum=(0, 0, 0)):
        _write_interleaved(
            self._vdv_path(momentum), self.vdv, byteorder)
        _write_interleaved(
            self._vvv_block_path(momentum), self.vvv, byteorder)
        for t in range(self.Nt):
            _write_interleaved(
                self._vvv_slice_path(t, momentum), self.vvv[t], byteorder)

    def _assert_expected_arrays(self, got_vdv, got_block, got_slices):
        expected_vdv = self.vdv[:, :self.nev1, :self.nev1]
        expected_vvv = self.vvv[
            :, :self.nev1, :self.nev1, :self.nev1]
        self.assertEqual(got_vdv.shape, expected_vdv.shape)
        self.assertEqual(got_block.shape, expected_vvv.shape)
        self.assertEqual(got_slices.shape, expected_vvv.shape)
        self.assertEqual(got_vdv.dtype, np.dtype(np.complex128))
        self.assertEqual(got_block.dtype, np.dtype(np.complex128))
        self.assertEqual(got_slices.dtype, np.dtype(np.complex128))
        np.testing.assert_array_equal(got_vdv, expected_vdv)
        np.testing.assert_array_equal(got_block, expected_vvv)
        np.testing.assert_array_equal(got_slices, expected_vvv)
        np.testing.assert_array_equal(got_block, got_slices)

    def test_default_native_layout_remains_backward_compatible(self):
        """Removing the native default would break existing binary files."""
        self._write_complete_fixture()
        self._assert_expected_arrays(
            readin_vdv_all(
                str(self.root), self.nev, self.nev1, self.Nt, 77),
            readin_vvv(
                str(self.root), self.nev, self.nev1, self.Nt, 77),
            readin_vvv_all(
                str(self.root), self.nev1, self.Nt, 77),
        )

    def test_explicit_little_and_big_endian_round_trip(self):
        """Ignoring explicit byte order would corrupt one endian fixture."""
        for byteorder in ("little", "big"):
            with self.subTest(byteorder=byteorder):
                self._write_complete_fixture(byteorder)
                self._assert_expected_arrays(
                    readin_vdv_all(
                        str(self.root), self.nev, self.nev1, self.Nt, 77,
                        byteorder=byteorder),
                    readin_vvv(
                        str(self.root), self.nev, self.nev1, self.Nt, 77,
                        byteorder=byteorder),
                    readin_vvv_all(
                        str(self.root), self.nev1, self.Nt, 77,
                        byteorder=byteorder),
                )

    def test_rejects_trailing_bytes_and_unpaired_float64(self):
        """Partial f8 data must fail before any reshape or truncation."""
        path = self._vdv_path()
        _write_interleaved(path, self.vdv)
        with path.open("ab") as stream:
            stream.write(b"x")
        with self.assertRaisesRegex(ValueError, "multiple of 8 bytes"):
            readin_vdv_all(
                str(self.root), self.nev, self.nev1, self.Nt, 77)

        _write_interleaved(path, self.vdv)
        with path.open("ab") as stream:
            np.asarray([0.0], dtype="=f8").tofile(stream)
        with self.assertRaisesRegex(ValueError, "complete complex f8 pair"):
            readin_vdv_all(
                str(self.root), self.nev, self.nev1, self.Nt, 77)

    def test_rejects_truncated_or_nonfactorable_shapes(self):
        """Wrong counts must not be accepted through rounded Nev inference."""
        _write_interleaved(self._vdv_path(), self.vdv)
        with self.assertRaisesRegex(ValueError, "Nev"):
            readin_vdv_all(
                str(self.root), self.nev + 1, self.nev1, self.Nt, 77)

        truncated = self.vvv.reshape(-1)[:-1]
        _write_interleaved(self._vvv_block_path(), truncated)
        with self.assertRaisesRegex(ValueError, "Nev"):
            readin_vvv(
                str(self.root), self.nev, self.nev1, self.Nt, 77)

        invalid_cube = np.arange(10) + 1j * np.arange(10)
        _write_interleaved(self._vvv_slice_path(0), invalid_cube)
        with self.assertRaisesRegex(ValueError, "t000.*Nev|Nev.*t000"):
            readin_vvv_all(
                str(self.root), self.nev1, 1, 77)

    def test_rejects_invalid_dimensions_momentum_and_byteorder(self):
        """Silent slicing or %%i coercion must not alter requested indices."""
        with self.assertRaisesRegex(ValueError, "nev1"):
            readin_vdv_all(str(self.root), self.nev, 0, self.Nt, 77)
        with self.assertRaisesRegex(ValueError, "nev1.*Nev"):
            readin_vdv_all(
                str(self.root), self.nev, self.nev + 1, self.Nt, 77)
        with self.assertRaisesRegex(ValueError, "Nt"):
            readin_vvv_all(str(self.root), self.nev1, 0, 77)
        with self.assertRaisesRegex(ValueError, "Px"):
            readin_vdv_all(
                str(self.root), self.nev, self.nev1, self.Nt, 77,
                Px=0.5)
        with self.assertRaisesRegex(ValueError, "byteorder"):
            readin_vvv_all(
                str(self.root), self.nev1, self.Nt, 77,
                byteorder="auto")

    def test_signed_integer_momentum_is_preserved_in_filename(self):
        """Rejecting physical negative lattice momentum would narrow the API."""
        momentum = (-1, 2, -3)
        self._write_complete_fixture(momentum=momentum)
        got = readin_vdv_all(
            str(self.root), self.nev, self.nev1, self.Nt, 77,
            Px=momentum[0], Py=momentum[1], Pz=momentum[2])
        np.testing.assert_array_equal(
            got, self.vdv[:, :self.nev1, :self.nev1])

    def test_readers_do_not_use_whole_file_fromfile(self):
        """Reintroducing np.fromfile would restore full-source allocation."""
        self._write_complete_fixture()
        with patch.object(
                io_module.np, "fromfile",
                side_effect=AssertionError("whole-file read is forbidden")):
            self._assert_expected_arrays(
                readin_vdv_all(
                    str(self.root), self.nev, self.nev1, self.Nt, 77),
                readin_vvv(
                    str(self.root), self.nev, self.nev1, self.Nt, 77),
                readin_vvv_all(
                    str(self.root), self.nev1, self.Nt, 77),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
