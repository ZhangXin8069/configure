"""4150 费米子 runner 的最小契约测试。

该测试先于 runner 实现编写；它只依赖本地工作区，不读取外部真实数据。
运行方式：

    python -m pyqcd.testing.comparisons.donghx.verify_4150_fermion_runner
"""

from __future__ import annotations

from pathlib import Path
import tempfile

import numpy as np

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "run_4150_fermion.py"


def test_runner_file_exists():
    """runner 必须作为可直接执行的 cmp1 入口存在。"""
    assert RUNNER.is_file(), f"missing implementation: {RUNNER}"


def test_compare_selected_marks_large_difference_as_diff():
    """超过比较容差的已存在参考数组不能被误报为 pass。"""
    from .cases_4150_fermion import (
        FermionConfig,
        compare_selected,
        selected_pairs,
    )

    config = FermionConfig(nx=2, nt=4, nev=2, delta_t_min=1, delta_t_max=1)
    reference = np.zeros((config.nt, config.nt, 4, 4), dtype=complex)
    actual = reference.copy()
    actual[1, 0, 0, 0] = 1.0
    result = compare_selected(reference, actual, selected_pairs(config))
    assert result["status"] == "diff"


def test_reference_comparison_marks_nev_mismatch_unverified():
    """Nev 不同的截断不能与 Nev=100 成品做数值算法比较。"""
    from .cases_4150_fermion import FermionConfig, reference_output_paths
    from .run_4150_fermion import _compare_reference

    config = FermionConfig(nx=2, nt=4, nev=8, delta_t_min=1, delta_t_max=1)
    contract = np.zeros((config.nt, config.nt, 4, 4), dtype=complex)
    nopol = np.zeros((config.nt, config.nt), dtype=complex)
    with tempfile.TemporaryDirectory() as directory:
        ref_paths = reference_output_paths(directory, config)
        np.save(ref_paths["contract"], contract)
        np.save(ref_paths["nopol_pp"], nopol)
        records = _compare_reference(
            contract, nopol, config, Path(directory)
        )
    assert records[0]["status"] == "unverified"
    assert records[0]["reason"] == "nev_mismatch"
    assert records[1]["status"] == "unverified"
    assert records[1]["reason"] == "nev_mismatch"


def test_reference_comparison_uses_explicit_complex64_tolerance():
    """complex64 参考产物的小量舍入差异需以显式容差记录而非误报。"""
    from .cases_4150_fermion import FermionConfig, reference_output_paths
    from .run_4150_fermion import _compare_reference

    config = FermionConfig(nx=2, nt=4, nev=100, delta_t_min=1, delta_t_max=1)
    reference_contract = np.zeros((config.nt, config.nt, 4, 4), dtype=np.complex64)
    actual_contract = reference_contract.astype(np.complex128)
    reference_contract[1, 0, 0, 0] = 1.0
    actual_contract[1, 0, 0, 0] = 1.0 + 1e-6
    reference_nopol = np.zeros((config.nt, config.nt), dtype=np.complex64)
    actual_nopol = reference_nopol.astype(np.complex128)
    reference_nopol[1, 0] = 1.0
    actual_nopol[1, 0] = 1.0 + 1e-6
    with tempfile.TemporaryDirectory() as directory:
        paths = reference_output_paths(directory, config)
        np.save(paths["contract"], reference_contract)
        np.save(paths["nopol_pp"], reference_nopol)
        records = _compare_reference(
            actual_contract, actual_nopol, config, Path(directory)
        )
    assert records[0]["status"] == "pass"
    assert records[0]["tolerance"] == 1e-5
    assert records[1]["status"] == "pass"
    assert records[1]["tolerance"] == 1e-5


def test_overall_status_downgrades_unverified_comparison():
    """有未验证比较时，runner 总状态不能误报为全链 pass。"""
    from .run_4150_fermion import aggregate_comparison_status

    assert aggregate_comparison_status([
        {"status": "pass"},
        {"status": "unverified", "reason": "reference_output_missing"},
    ]) == "unverified"


def test_vvv_cache_reuse_checks_shape_and_dtype():
    """匹配的本地 VVV 缓存可复用，错误形状不能误读。"""
    from .cases_4150_fermion import FermionConfig
    from .run_4150_fermion import _load_vvv_cache

    config = FermionConfig(nx=2, nt=4, nev=3, delta_t_min=1,
                           delta_t_max=1)
    times = (0, 1)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "vvv.npy"
        np.save(path, np.zeros((2, 3, 3, 3), dtype=np.complex128))
        loaded = _load_vvv_cache(path, config, times)
        assert loaded is not None
        assert loaded[1]["cache_reused"] is True
        np.save(path, np.zeros((2, 3, 3, 2), dtype=np.complex128))
        assert _load_vvv_cache(path, config, times) is None


def test_cg5_reference_name_has_no_redundant_suffix():
    """Cg5 参考文件沿用默认名，Cg5g4 才带显式变体后缀。"""
    from .cases_4150_fermion import FermionConfig, reference_output_paths

    cg5 = reference_output_paths("/tmp/ref", FermionConfig(variant="Cg5"))
    cg5g4 = reference_output_paths("/tmp/ref", FermionConfig(variant="Cg5g4"))
    assert cg5["contract"].name.endswith("eginphase0_contract_conf4150.npy")
    assert "eginphase0_Cg5g4_contract" in cg5g4["contract"].name


def test_nonzero_momentum_smear_requires_direction():
    """非零动量涂抹不能在缺失空间方向时退化为未涂抹。"""
    from .cases_4150_fermion import FermionConfig

    try:
        FermionConfig(momentum_smear=2)
    except ValueError as exc:
        assert "direction" in str(exc)
    else:
        raise AssertionError("nonzero momentum_smear must require a direction")


def test_momentum_smear_vector_matches_donghx_sign_convention():
    """2x/−2z 的相位向量按参考代码使用 ``phase=-mom_smear``。"""
    from .cases_4150_fermion import FermionConfig

    assert FermionConfig(momentum_smear=2, momentum_smear_dir="x").momentum_smear_vector == (0, 0, -2)
    assert FermionConfig(momentum_smear=-2, momentum_smear_dir="z").momentum_smear_vector == (2, 0, 0)
    assert FermionConfig().momentum_smear_vector == (0, 0, 0)


def test_momentum_smear_applies_phase_to_each_eigenvector():
    """VVV 输入 eigenvector 的每个色分量都应乘空间相位。"""
    from .cases_4150_fermion import FermionConfig
    from .run_4150_fermion import _apply_momentum_smear

    config = FermionConfig(nx=4, momentum_smear=2, momentum_smear_dir="x")
    eig = np.ones((1, 4, 4, 4, 3), dtype=np.complex128)
    got = _apply_momentum_smear(eig, config)
    expected = np.exp(1j * np.pi * np.arange(4))
    assert np.allclose(got[0, 0, 0, :, 0], expected)
    assert np.allclose(got[0, ..., 1], got[0, ..., 0])


def test_momentum_smear_requires_explicit_independent_peram_root():
    """非零涂抹必须显式传入独立 perambulator 根目录。"""
    from .cases_4150_fermion import FermionConfig
    from .run_4150_fermion import _select_peram_root

    config = FermionConfig(nx=2, momentum_smear=2, momentum_smear_dir="x")
    try:
        _select_peram_root(config, Path("/ordinary/peram"), None)
    except ValueError as exc:
        assert "独立" in str(exc)
    else:
        raise AssertionError("momentum-smear run must require a separate peram root")


def test_momentum_smear_cache_namespace_is_distinct():
    """普通与动量涂抹 VVV 缓存不得共享文件名。"""
    from .cases_4150_fermion import FermionConfig
    from .run_4150_fermion import _vvv_cache_filename

    ordinary = _vvv_cache_filename(FermionConfig(), (0, 1))
    smeared = _vvv_cache_filename(
        FermionConfig(momentum_smear=2, momentum_smear_dir="x"), (0, 1)
    )
    smeared_override = _vvv_cache_filename(
        FermionConfig(momentum_smear=2, momentum_smear_dir="x",
                      momentum_smear_phase=2), (0, 1)
    )
    assert ordinary != smeared
    assert "smearx2_phase-2" in smeared
    assert smeared != smeared_override


def run():
    tests = [
        test_runner_file_exists,
        test_compare_selected_marks_large_difference_as_diff,
        test_reference_comparison_marks_nev_mismatch_unverified,
        test_reference_comparison_uses_explicit_complex64_tolerance,
        test_overall_status_downgrades_unverified_comparison,
        test_vvv_cache_reuse_checks_shape_and_dtype,
        test_cg5_reference_name_has_no_redundant_suffix,
        test_nonzero_momentum_smear_requires_direction,
        test_momentum_smear_vector_matches_donghx_sign_convention,
        test_momentum_smear_applies_phase_to_each_eigenvector,
        test_momentum_smear_requires_explicit_independent_peram_root,
        test_momentum_smear_cache_namespace_is_distinct,
    ]
    for test in tests:
        test()
    print(f"verify_4150_fermion_runner: PASS {len(tests)}/{len(tests)}")


if __name__ == "__main__":
    run()
