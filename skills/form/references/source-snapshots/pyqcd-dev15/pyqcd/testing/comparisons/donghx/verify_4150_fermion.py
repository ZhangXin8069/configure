"""4150 费米子缩并适配层的受控回归测试。

参考公式在测试中独立写出，避免测试只重复生产实现本身。运行方式：

    python -m pyqcd.testing.comparisons.donghx.verify_4150_fermion
"""

from __future__ import annotations

import numpy as np


def _donghx_reference(peram, vvv_sink, vvv_source, inter_projector):
    """直接对应 donghx 2pt Cg5g4 的两项 opt_einsum 公式。"""
    transformed = np.einsum(
        "gh,hkbe,jk->gjbe",
        inter_projector,
        peram,
        inter_projector,
    )
    term1 = np.einsum(
        "abc,gjad,gjbe,ilcf,def->il",
        vvv_sink,
        peram,
        transformed,
        peram,
        vvv_source,
    )
    term2 = np.einsum(
        "abc,glaf,gjbe,ijcd,def->il",
        vvv_sink,
        peram,
        transformed,
        peram,
        vvv_source,
    )
    return term1 - term2


def test_cg5g4_matches_donghx_two_term_formula():
    """显式 Cg5g4 适配层必须逐元素复现 donghx 的两项缩并。"""
    from pyqcd.contraction._donghx import contract_donghx_2pt_pair
    from pyqcd.lattice._gamma import gamma
    from pyqcd.tools import set_backend

    set_backend("numpy")
    rng = np.random.default_rng(4150)
    nev = 3
    peram = rng.normal(size=(4, 4, nev, nev)) \
        + 1j * rng.normal(size=(4, 4, nev, nev))
    vvv_sink = rng.normal(size=(nev, nev, nev)) \
        + 1j * rng.normal(size=(nev, nev, nev))
    vvv_source = rng.normal(size=(nev, nev, nev)) \
        + 1j * rng.normal(size=(nev, nev, nev))
    projector = np.asarray(gamma(7) @ gamma(4))

    expected = _donghx_reference(peram, vvv_sink, vvv_source, projector)
    actual = np.asarray(contract_donghx_2pt_pair(
        peram, vvv_sink, vvv_source, variant="Cg5g4"
    ))

    assert actual.shape == (4, 4)
    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)


def test_cg5g4_rejects_incompatible_peram_shape():
    """固定时间对的 peram 必须显式保留四个 Dirac 轴。"""
    from pyqcd.contraction._donghx import contract_donghx_2pt_pair

    with np.testing.assert_raises(ValueError):
        contract_donghx_2pt_pair(
            np.zeros((4, 3, 3), dtype=complex),
            np.zeros((3, 3, 3), dtype=complex),
            np.zeros((3, 3, 3), dtype=complex),
            variant="Cg5g4",
        )


def test_parity_and_boundary_has_donghx_sign_convention():
    """P±=(1±γ₄)/2 后沿反周期边界翻转指定时间半平面。"""
    from pyqcd.contraction import parity_and_boundary
    from pyqcd.tools import set_backend

    set_backend("numpy")
    nt = 3
    values = np.arange(nt * nt, dtype=float).reshape(nt, nt) + 1.0
    matrix = np.zeros((nt, nt, 4, 4), dtype=complex)
    matrix[..., np.arange(4), np.arange(4)] = values[..., None]

    pp, pm = parity_and_boundary(matrix, nt)
    expected_pp = 2.0 * values.copy()
    expected_pm = 2.0 * values.copy()
    expected_pp[np.triu_indices(nt, k=1)] *= -1.0
    expected_pm[np.tril_indices(nt, k=-1)] *= -1.0
    np.testing.assert_allclose(pp, expected_pp)
    np.testing.assert_allclose(pm, expected_pm)


def run():
    tests = [
        test_cg5g4_matches_donghx_two_term_formula,
        test_cg5g4_rejects_incompatible_peram_shape,
        test_parity_and_boundary_has_donghx_sign_convention,
    ]
    for test in tests:
        test()
    print(f"verify_4150_fermion: PASS {len(tests)}/{len(tests)}")


if __name__ == "__main__":
    run()
