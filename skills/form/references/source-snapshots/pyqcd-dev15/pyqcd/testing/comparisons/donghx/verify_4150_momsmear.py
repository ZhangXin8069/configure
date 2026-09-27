"""momentum-smear 4150 最终 2pt 输出级检查器的红绿测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def _literal_pplus() -> np.ndarray:
    """独立于被测实现的 DR 基 P+ 矩阵。"""
    return 0.5 * np.array(
        [
            [1, 0, 1, 0],
            [0, 1, 0, 1],
            [1, 0, 1, 0],
            [0, 1, 0, 1],
        ],
        dtype=np.complex128,
    )


def _literal_gamma(direction: int) -> np.ndarray:
    """独立于被测实现的 DR 基空间 γ 矩阵。"""
    matrices = {
        1: {
            (0, 3): 1j,
            (1, 2): 1j,
            (2, 1): -1j,
            (3, 0): -1j,
        },
        2: {
            (0, 3): -1.0,
            (1, 2): 1.0,
            (2, 1): 1.0,
            (3, 0): -1.0,
        },
        3: {
            (0, 2): 1j,
            (1, 3): -1j,
            (2, 0): -1j,
            (3, 1): 1j,
        },
    }
    if direction not in matrices:
        raise ValueError(direction)
    result = np.zeros((4, 4), dtype=np.complex128)
    for (row, col), value in matrices[direction].items():
        result[row, col] = value
    return result


def _literal_polar_projection(direction: int) -> np.ndarray:
    gamma5 = np.diag([1.0, 1.0, -1.0, -1.0]).astype(np.complex128)
    return _literal_pplus() @ (1j * _literal_gamma(direction) @ gamma5)


def _literal_projected(contract: np.ndarray, direction: int, indices: str = "li"):
    projected = np.einsum(
        f"{indices},yxil->yx",
        _literal_polar_projection(direction),
        contract,
    )
    sink, source = np.indices(projected.shape)
    projected = projected.copy()
    projected[sink < source] *= -1.0
    return projected


def _write_fixture(root: Path) -> tuple[np.ndarray, np.ndarray]:
    contract = np.zeros((4, 4, 4, 4), dtype=np.complex128)
    contract[1, 0, 0, 0] = 2.0 + 1.0j
    contract[0, 1, 1, 0] = -1.0 + 2.0j
    expected = np.einsum("li,yxil->yx", _literal_pplus(), contract)
    yy, xx = np.indices(expected.shape)
    expected = expected.copy()
    expected[yy < xx] *= -1.0
    np.save(
        root / "twopt_slice_pp_Px2Py0Pz0_eginphase2_Cg5g4_contract_conf4150.npy",
        contract,
    )
    np.save(
        root / "twopt_slice_pp_Px2Py0Pz0_eginphase2_Cg5g4_nopol_ss_conf4150.npy",
        expected,
    )
    np.save(
        root / "twopt_slice_pp_Px2Py0Pz0_eginphase2_Cg5g4_pol15_ss_conf4150.npy",
        _literal_projected(contract, 1),
    )
    return contract, expected


def test_parse_momsmear_filename_preserves_direction_and_phase():
    from .inspect_4150_momsmear import parse_output_filename

    parsed = parse_output_filename(
        "twopt_slice_pp_Px0Py0Pz2_eginphase-2_Cg5g4_contract_conf4150.npy"
    )
    assert parsed == {
        "momentum": [2, 0, 0],
        "phase": -2,
        "variant": "Cg5g4",
        "kind": "contract",
    }


def test_parse_implicit_variant_filename_without_guessing_operator():
    """momsmear0_Cg5 的无后缀文件应可解析但保留隐式变体。"""
    from .inspect_4150_momsmear import parse_output_filename

    parsed = parse_output_filename(
        "twopt_slice_pp_Px0Py0Pz0_eginphase0_contract_conf4150.npy"
    )
    assert parsed == {
        "momentum": [0, 0, 0],
        "phase": 0,
        "variant": "implicit",
        "kind": "contract",
    }


def test_projected_nopol_uses_pplus_and_antiperiodic_boundary_sign():
    from .inspect_4150_momsmear import compare_contract_nopol

    contract = np.zeros((4, 4, 4, 4), dtype=np.complex128)
    contract[1, 0, 0, 0] = 2.0 + 1.0j
    contract[0, 1, 1, 0] = -1.0 + 2.0j
    expected = np.einsum("li,yxil->yx", _literal_pplus(), contract)
    yy, xx = np.indices(expected.shape)
    expected = expected.copy()
    expected[yy < xx] *= -1.0
    result = compare_contract_nopol(contract, expected)
    assert result["status"] == "pass"
    assert result["max_abs"] == 0.0


def test_projected_polarization_uses_standard_li_spin_trace():
    from .inspect_4150_momsmear import compare_contract_polarization

    contract = np.zeros((4, 4, 4, 4), dtype=np.complex128)
    contract[1, 0, 0, 0] = 2.0 + 1.0j
    contract[0, 1, 1, 0] = -1.0 + 2.0j
    expected = _literal_projected(contract, 1)

    result = compare_contract_polarization(contract, expected, "pol15_ss")

    assert result["status"] == "pass"
    assert result["einsum_indices"] == "li"
    assert result["max_abs"] == 0.0


def test_polarization_reports_transposed_legacy_order_as_diagnostic_only():
    from .inspect_4150_momsmear import compare_contract_polarization

    contract = np.zeros((4, 4, 4, 4), dtype=np.complex128)
    contract[1, 0, 0, 0] = 2.0 + 1.0j
    contract[0, 1, 1, 0] = -1.0 + 2.0j
    legacy_output = _literal_projected(contract, 2, indices="il")

    result = compare_contract_polarization(contract, legacy_output, "pol25_ss")

    assert result["status"] == "diff"
    assert result["legacy_transposed"]["status"] == "pass"
    assert result["legacy_transposed"]["einsum_indices"] == "il"


def test_inspect_directory_groups_optional_polarizations_and_checks_projection():
    from .inspect_4150_momsmear import inspect_directory

    with tempfile.TemporaryDirectory(prefix="pyqcd_momsmear_") as tmp:
        root = Path(tmp)
        _write_fixture(root)
        report = inspect_directory(root)
    assert report["file_count"] == 3
    assert report["group_count"] == 1
    group = report["groups"][0]
    assert group["momentum"] == [0, 0, 2]
    assert group["phase"] == 2
    assert group["files"]["contract"]["shape"] == [4, 4, 4, 4]
    assert group["files"]["nopol_ss"]["shape"] == [4, 4]
    assert group["files"]["pol15_ss"]["shape"] == [4, 4]
    assert group["projection"]["status"] == "pass"
    assert group["polarizations"]["pol15_ss"]["status"] == "pass"


def test_inspect_directory_rejects_malformed_or_foreign_files():
    from .inspect_4150_momsmear import inspect_directory

    with tempfile.TemporaryDirectory(prefix="pyqcd_momsmear_") as tmp:
        root = Path(tmp)
        np.save(root / "unrelated.npy", np.zeros(2, dtype=np.float64))
        report = inspect_directory(root)
    assert report["file_count"] == 1
    assert report["unparsed_files"] == ["unrelated.npy"]


def run() -> None:
    tests = [
        test_parse_momsmear_filename_preserves_direction_and_phase,
        test_parse_implicit_variant_filename_without_guessing_operator,
        test_projected_nopol_uses_pplus_and_antiperiodic_boundary_sign,
        test_projected_polarization_uses_standard_li_spin_trace,
        test_polarization_reports_transposed_legacy_order_as_diagnostic_only,
        test_inspect_directory_groups_optional_polarizations_and_checks_projection,
        test_inspect_directory_rejects_malformed_or_foreign_files,
    ]
    for test in tests:
        test()
    print(f"verify_4150_momsmear: PASS {len(tests)}/{len(tests)}")


if __name__ == "__main__":
    run()
