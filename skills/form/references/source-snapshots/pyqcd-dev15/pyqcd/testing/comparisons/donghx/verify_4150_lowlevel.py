"""4150 低层对象 runner 的受控测试入口。"""

import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

from ..common.harness import Case
from .cases_4150_lowlevel import build, controlled_checks
from .run_4150_lowlevel import _execute


def test_controlled_checks_have_expected_shapes():
    result = controlled_checks()
    assert result["phase_shape"] == [24, 24, 24]
    assert result["vdv_shape"][-2:] == [4, 4]
    assert result["vvv_shape"] == [1, 4, 4, 4]
    assert result["finite"] is True


def test_execute_sets_status_before_success_path():
    case = Case("status", "controlled", "status initialization",
                lambda: np.array([1.0]), lambda: np.array([1.0]))
    result = _execute(case)
    assert result["status"] == "pass"


def test_real_case_builder_accepts_timeout_cases():
    cases = build(4150)
    assert {case.cid for case in cases} >= {"4150-CLOVER", "4150-OPE"}


def main():
    test_controlled_checks_have_expected_shapes()
    test_execute_sets_status_before_success_path()
    test_real_case_builder_accepts_timeout_cases()
    print("verify_4150_lowlevel: PASS 3/3")


if __name__ == "__main__":
    main()
