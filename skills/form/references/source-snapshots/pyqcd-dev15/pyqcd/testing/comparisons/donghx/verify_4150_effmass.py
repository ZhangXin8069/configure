"""聚合 2pt 资产检查器的受控测试。"""

from __future__ import annotations

import numpy as np


def test_time_difference_sum_uses_sink_minus_source_modulo():
    """时间汇总应按 (t_sink - t_source) mod Nt，而不是反向差。"""
    from .inspect_4150_effmass import time_difference_sum

    matrix = np.zeros((4, 4), dtype=np.complex128)
    matrix[1, 0] = 2.0 + 1.0j
    matrix[0, 1] = 3.0 - 2.0j
    matrix[3, 1] = 5.0 + 4.0j

    actual = time_difference_sum(matrix)
    expected = np.array(
        [0.0 + 0.0j, 2.0 + 1.0j, 5.0 + 4.0j, 3.0 - 2.0j],
        dtype=np.complex128,
    )
    np.testing.assert_array_equal(actual, expected)


def test_matrix_stack_finds_exact_4150_row():
    """raw 聚合中精确的 4150 行应被定位，而非只报告形状一致。"""
    from .inspect_4150_effmass import compare_matrix_stack

    reference = np.array(
        [[1.0 + 2.0j, 0.0], [3.0 - 1.0j, 4.0 + 0.5j]],
        dtype=np.complex64,
    )
    stack = np.zeros((3, 2, 2), dtype=np.complex128)
    stack[0] = reference * 2
    stack[2] = reference

    result = compare_matrix_stack(stack, reference)
    assert result["best_index"] == 2
    assert result["rel_l2"] == 0.0
    assert result["status"] == "pass"


def test_time_stack_compares_after_widened_accumulation():
    """complex64 raw 矩阵的时间汇总应先升宽，避免累加舍入制造假差异。"""
    from .inspect_4150_effmass import compare_time_stack, time_difference_sum

    reference = np.zeros((4, 4), dtype=np.complex64)
    reference[1, 0] = np.complex64(1.25 + 0.5j)
    reference[0, 1] = np.complex64(2.5 - 1.25j)
    reference[3, 1] = np.complex64(4.0 + 2.0j)
    expected = time_difference_sum(reference)

    stack = np.zeros((3, 4), dtype=np.complex128)
    stack[0] = expected * 2.0
    stack[2] = expected

    result = compare_time_stack(stack, reference)
    assert result["best_index"] == 2
    assert result["rel_l2"] == 0.0
    assert result["status"] == "pass"


def run() -> None:
    tests = [
        test_time_difference_sum_uses_sink_minus_source_modulo,
        test_matrix_stack_finds_exact_4150_row,
        test_time_stack_compares_after_widened_accumulation,
    ]
    for test in tests:
        test()
    print(f"verify_4150_effmass: PASS {len(tests)}/{len(tests)}")


if __name__ == "__main__":
    run()
