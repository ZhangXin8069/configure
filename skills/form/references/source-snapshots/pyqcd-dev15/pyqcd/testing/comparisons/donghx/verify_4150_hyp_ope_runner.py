"""4150 HYP OPE runner 的最小契约测试。"""

from __future__ import annotations

from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent


def test_hyp_record_map_points_to_explicit_ildg_record():
    from .run_4150_hyp_ope import HYP_RECORDS

    assert set(HYP_RECORDS) == {"3d1", "3d3", "3d5", "4d10"}
    for path in HYP_RECORDS.values():
        assert path.name == "msg02.rec04.ildg-binary-data"


def test_reference_case_mapping_uses_zero_transverse_slice():
    from .run_4150_hyp_ope import reference_case

    case = reference_case("z", 0, 1)
    assert case["path"].name == "ops_mu0_nu1_dz12_dx5_conf4150.npy"
    assert case["axis"] == (slice(None), slice(None), 0)


def test_compare_line_detects_shape_and_numerical_difference():
    from .run_4150_hyp_ope import compare_line

    reference = np.zeros((3, 2), dtype=complex)
    actual = reference.copy()
    actual[1, 1] = 1.0
    result = compare_line(reference, actual, tolerance=1e-12)
    assert result["status"] == "diff"
    assert result["shape"] == [3, 2]
    assert result["max_abs"] == 1.0


def test_contract_runner_entrypoint_executes_all_checks():
    """契约入口应实际执行三项测试，而不是仅定义测试函数。"""
    assert run(emit=False) == 3


def run(*, emit=True):
    """Run the local contract checks and return the number executed."""
    tests = [
        test_hyp_record_map_points_to_explicit_ildg_record,
        test_reference_case_mapping_uses_zero_transverse_slice,
        test_compare_line_detects_shape_and_numerical_difference,
    ]
    for test in tests:
        test()
    if emit:
        print(f"verify_4150_hyp_ope_runner: PASS {len(tests)}/{len(tests)}")
    return len(tests)


if __name__ == "__main__":
    run()
