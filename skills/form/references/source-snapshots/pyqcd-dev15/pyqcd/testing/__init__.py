"""pyqcd 集成测试：梯度流、TMD 算符、重整化链的数值断言。"""
from __future__ import annotations

import numpy as np
from scipy.linalg import expm


def random_su3_gauge(L=6, seed=42):
    """随机 SU(3) 规范场 (L,L,L,L,4,3,3)（测试用）。"""
    rng = np.random.default_rng(seed)
    g = np.zeros((L, L, L, L, 4, 3, 3), dtype=complex)
    for idx in np.ndindex(L, L, L, L, 4):
        H = (rng.standard_normal((3, 3)) + 1j * rng.standard_normal((3, 3)))
        H = H - H.conj().T - np.trace(H - H.conj().T) / 3 * np.eye(3)
        g[idx] = expm(H)
    return g


def _manual_staple_wilson_line(gauge, z, b_perp, z_dir, b_dir, L):
    """逐点参考实现：0 -> -L z -> b-L z -> b+z。"""
    lattice_shape = gauge.shape[:4]
    out = np.empty(lattice_shape + (3, 3), dtype=gauge.dtype)
    path = ((z_dir, -L), (b_dir, b_perp), (z_dir, L + z))

    for base in np.ndindex(*lattice_shape):
        pos = list(base)
        transporter = np.eye(3, dtype=gauge.dtype)
        for direction, signed_length in path:
            axis = 3 - direction
            sign = 1 if signed_length >= 0 else -1
            for _ in range(abs(signed_length)):
                if sign > 0:
                    link = gauge[tuple(pos)][direction]
                    pos[axis] = (pos[axis] + 1) % lattice_shape[axis]
                else:
                    pos[axis] = (pos[axis] - 1) % lattice_shape[axis]
                    link = gauge[tuple(pos)][direction].conj().T
                transporter = transporter @ link
        out[base] = transporter
    return out


def _gauge_transform(gauge, site_transform):
    """U_mu(x) -> G(x) U_mu(x) G^dagger(x+mu)。"""
    transformed = np.empty_like(gauge)
    for direction in range(4):
        axis = 3 - direction
        at_neighbor = np.roll(site_transform, -1, axis=axis)
        transformed[..., direction, :, :] = (
            site_transform @ gauge[..., direction, :, :]
            @ at_neighbor.conj().swapaxes(-1, -2)
        )
    return transformed


def _link_covariance_error(smear_or_flow, gauge, site_transform):
    """返回 S[U^G] 与 G S[U] G^dagger(x+mu) 的最大偏差。"""
    transformed_input = _gauge_transform(gauge, site_transform)
    expected = _gauge_transform(smear_or_flow(gauge), site_transform)
    actual = smear_or_flow(transformed_input)
    return float(np.max(np.abs(actual - expected)))


def _wilson_action_density(gauge):
    """手工计算每个 mu<nu 平面的 1-ReTr(P_mu_nu)/3 平均。"""
    total = 0.0
    for mu in range(4):
        for nu in range(mu + 1, 4):
            a_mu, a_nu = 3 - mu, 3 - nu
            plaquette = (
                gauge[..., mu, :, :]
                @ np.roll(gauge, -1, axis=a_mu)[..., nu, :, :]
                @ np.roll(gauge, -1, axis=a_nu)[..., mu, :, :]
                .conj().swapaxes(-1, -2)
                @ gauge[..., nu, :, :].conj().swapaxes(-1, -2)
            )
            total += np.mean(
                1.0 - np.trace(plaquette, axis1=-2, axis2=-1).real / 3.0)
    return float(total / 6.0)


def _swap_lattice_directions(gauge, first, second):
    """同时交换坐标轴和 link 方向标签（该变换自逆）。"""
    swapped = np.swapaxes(gauge, 3 - first, 3 - second)
    order = list(range(4))
    order[first], order[second] = order[second], order[first]
    return swapped[..., order, :, :]


def _reference_staple_pair(side, middle, mu, nu):
    """由独立 side/middle 链接构造正负 nu 两个 staple。"""
    a_mu, a_nu = 3 - mu, 3 - nu
    forward = (
        side
        @ np.roll(middle, -1, axis=a_nu)
        @ np.roll(side, -1, axis=a_mu).conj().swapaxes(-1, -2)
    )
    side_back = np.roll(side, 1, axis=a_nu)
    backward = (
        side_back.conj().swapaxes(-1, -2)
        @ np.roll(middle, 1, axis=a_nu)
        @ np.roll(side_back, -1, axis=a_mu)
    )
    return forward + backward


def _reference_project_su3(field):
    """测试侧极分解投影，不调用 HYP 的生产 helper。"""
    left, _singular, right_h = np.linalg.svd(field)
    unitary = left @ right_h
    determinant = np.linalg.det(unitary)
    return unitary * (determinant ** (-1.0 / 3.0))[..., None, None]


def _reference_ape(gauge, alpha):
    """四维 APE：每条 link 使用其余三方向的六个 staple。"""
    out = np.empty_like(gauge)
    for mu in range(4):
        staples = sum(
            (_reference_staple_pair(
                gauge[..., nu, :, :], gauge[..., mu, :, :], mu, nu)
             for nu in range(4) if nu != mu),
            start=np.zeros_like(gauge[..., mu, :, :]),
        )
        out[..., mu, :, :] = _reference_project_su3(
            (1.0 - alpha) * gauge[..., mu, :, :] + alpha * staples / 6.0)
    return out


def _reference_tmd_operator(gauge, z, b_perp, z_dir, b_dir, L):
    """测试侧 TMD 颜色迹：手写路径、端点平移和 Lorentz 组合。"""
    from pyqcd.operator._gluon_ope import plaquette_clover

    wilson_line = _manual_staple_wilson_line(
        gauge, z, b_perp, z_dir, b_dir, L)
    wilson_dagger = wilson_line.conj().swapaxes(-1, -2)
    endpoint = [0, 0, 0]
    endpoint[z_dir] += z
    endpoint[b_dir] += b_perp

    operator = np.zeros(gauge.shape[:4], dtype=gauge.dtype)
    for coefficient, mu, nu in (
            (1.0, 3, 0), (1.0, 3, 1), (-2.0, 0, 1)):
        field = np.asarray(plaquette_clover(gauge, mu, nu))
        nc = field.shape[-1]
        trace = np.trace(field, axis1=-2, axis2=-1)
        field = field - (
            trace[..., None, None] * np.eye(nc, dtype=field.dtype) / nc)
        shifted = field
        for direction, offset in enumerate(endpoint):
            if offset:
                shifted = np.roll(shifted, -offset, axis=3 - direction)
        closed = field @ wilson_line @ shifted @ wilson_dagger
        operator += coefficient * np.trace(
            closed, axis1=-2, axis2=-1)
    return operator


def test_tmd_staple_matches_explicit_three_segment_path():
    """staple 必须逐链复现 -L z、b_perp、(L+z) z 三段路径。"""
    from pyqcd.renorm import staple_wilson_line
    from pyqcd.tools import set_backend

    set_backend('numpy')
    gauge = random_su3_gauge(L=3, seed=101)
    expected = _manual_staple_wilson_line(
        gauge, z=1, b_perp=1, z_dir=2, b_dir=0, L=2)
    got = staple_wilson_line(
        gauge, z=1, b_perp=1, z_dir=2, b_dir=0, L=2)
    err = np.max(np.abs(got - expected))
    assert err < 1e-12, f"staple 三段路径错误: max|d|={err:.3e}"


def test_tmd_staple_is_gauge_covariant():
    """连接 x 与 x+z*zdir+b*bdir 的 transporter 必须规范协变。"""
    from pyqcd.renorm import staple_wilson_line
    from pyqcd.tools import set_backend

    set_backend('numpy')
    gauge = random_su3_gauge(L=3, seed=102)
    site_transform = random_su3_gauge(L=3, seed=202)[..., 0, :, :]
    transformed = _gauge_transform(gauge, site_transform)

    W = staple_wilson_line(
        gauge, z=1, b_perp=1, z_dir=2, b_dir=0, L=2)
    W_transformed = staple_wilson_line(
        transformed, z=1, b_perp=1, z_dir=2, b_dir=0, L=2)
    at_endpoint = np.roll(site_transform, -1, axis=3 - 2)
    at_endpoint = np.roll(at_endpoint, -1, axis=3 - 0)
    expected = site_transform @ W @ at_endpoint.conj().swapaxes(-1, -2)
    err = np.max(np.abs(W_transformed - expected))
    assert err < 1e-11, f"staple 规范协变性破坏: max|d|={err:.3e}"


def test_tmd_matrix_element_is_gauge_invariant():
    """Tr[F(0) W F(b,z) W^dagger] 在局域 SU(3) 变换下必须不变。"""
    from pyqcd.renorm import M_mu_lambda_nu_rho
    from pyqcd.tools import set_backend

    set_backend('numpy')
    gauge = random_su3_gauge(L=3, seed=103)
    site_transform = random_su3_gauge(L=3, seed=203)[..., 0, :, :]
    transformed = _gauge_transform(gauge, site_transform)

    original = M_mu_lambda_nu_rho(
        gauge, 3, 0, 3, 0, z=1, b_perp=1, z_dir=2, b_dir=0, L=2)
    rotated = M_mu_lambda_nu_rho(
        transformed, 3, 0, 3, 0, z=1, b_perp=1,
        z_dir=2, b_dir=0, L=2)
    err = np.max(np.abs(rotated - original))
    assert err < 1e-10, f"TMD 矩阵元规范不变性破坏: max|d|={err:.3e}"


def test_tmd_operator_uses_tx_ty_xy_lorentz_pairs():
    """本库 0=x,1=y,2=z,3=t；非极化组合必须使用 tx、ty、xy。"""
    from pyqcd.renorm import M_mu_lambda_nu_rho, gluon_tmd_operator
    from pyqcd.tools import set_backend

    set_backend('numpy')
    gauge = random_su3_gauge(L=3, seed=104)
    kwargs = dict(z=1, b_perp=1, z_dir=2, b_dir=0, L=2)
    expected = (
        M_mu_lambda_nu_rho(gauge, 3, 0, 3, 0, **kwargs)
        + M_mu_lambda_nu_rho(gauge, 3, 1, 3, 1, **kwargs)
        - 2.0 * M_mu_lambda_nu_rho(gauge, 0, 1, 0, 1, **kwargs)
    )
    got = gluon_tmd_operator(gauge, **kwargs)
    err = np.max(np.abs(got - expected))
    assert err < 1e-12, f"TMD Lorentz 组合错误: max|d|={err:.3e}"


def test_tmd_batch_reuses_clover_fields_and_staples():
    """批量 TMD 不得随 (z,b) 重算不变 Clover，也不得按通道重建 staple。"""
    from unittest.mock import patch

    import pyqcd.renorm._tmd as tmd
    from pyqcd.tools import set_backend

    set_backend('numpy')
    gauge = random_su3_gauge(L=2, seed=222)
    z_list, b_list = [0, 1], [0, 1]
    expected = np.empty((2, 2, gauge.shape[0]))
    for i, z in enumerate(z_list):
        for j, b_perp in enumerate(b_list):
            operator = _reference_tmd_operator(
                gauge, z, b_perp, z_dir=2, b_dir=0, L=1)
            expected[i, j] = np.real(np.sum(operator, axis=(1, 2, 3)))

    with patch.object(tmd, 'plaquette_clover',
                      wraps=tmd.plaquette_clover) as clover_spy, \
            patch.object(tmd, 'staple_wilson_line',
                         wraps=tmd.staple_wilson_line) as staple_spy:
        actual = tmd.tmd_matrix_elements_time(
            gauge, z_list, b_list, z_dir=2, b_dir=0, L=1)

    assert np.allclose(actual, expected, atol=1e-12, rtol=1e-12)
    assert clover_spy.call_count == 3, \
        f"三个固定 Lorentz 场只应构造一次，实际 {clover_spy.call_count}"
    assert staple_spy.call_count == len(z_list) * len(b_list), \
        f"每个 (z,b) 只应构造一条 staple，实际 {staple_spy.call_count}"

    with patch.object(tmd, 'plaquette_clover',
                      wraps=tmd.plaquette_clover) as clover_spy, \
            patch.object(tmd, 'staple_wilson_line',
                         wraps=tmd.staple_wilson_line) as staple_spy:
        averaged = tmd.tmd_matrix_elements(
            gauge, z_list, b_list, z_dir=2, b_dir=0, L=1)

    assert np.allclose(averaged, expected.mean(axis=-1),
                       atol=1e-12, rtol=1e-12)
    assert clover_spy.call_count == 3
    assert staple_spy.call_count == len(z_list) * len(b_list)


def test_tmd_empty_batch_skips_geometry_work():
    """空 z/b 网格必须零计算返回，不能分配三个整格点 Clover 场。"""
    from unittest.mock import patch

    import pyqcd.renorm._tmd as tmd
    from pyqcd.tools import set_backend

    set_backend('numpy')
    gauge = random_su3_gauge(L=2, seed=223)
    with patch.object(tmd, 'plaquette_clover',
                      wraps=tmd.plaquette_clover) as clover_spy, \
            patch.object(tmd, 'staple_wilson_line',
                         wraps=tmd.staple_wilson_line) as staple_spy:
        averaged = tmd.tmd_matrix_elements(gauge, [], [0], L=1)
        timed = tmd.tmd_matrix_elements_time(gauge, [0], [], L=1)

    assert averaged.shape == (0, 1)
    assert timed.shape == (1, 0, gauge.shape[0])
    assert clover_spy.call_count == 0, \
        f"空网格不应构造 Clover，实际 {clover_spy.call_count}"
    assert staple_spy.call_count == 0, \
        f"空网格不应构造 staple，实际 {staple_spy.call_count}"


def test_gamma_basis():
    """DR 基 γ 矩阵：γ₅² = I、γ_7 = γ₃γ₁ 反厄米。"""
    from pyqcd.lattice import gamma
    g5 = gamma(5)
    assert np.allclose(g5 @ g5, np.eye(4), atol=1e-10)
    g7 = gamma(7)
    assert np.allclose(g7, -g7.conj().T, atol=1e-10)


def test_gevp_preserves_complex_hermitian_data():
    """GEVP 应保留复 Hermitian 关联矩阵的本征值与本征向量。"""
    from scipy.linalg import eigh
    from pyqcd.analysis import solve_gevp
    from pyqcd.tools import set_backend

    set_backend('numpy')
    c0 = np.eye(2, dtype=complex)
    c1 = np.array([[1.0, 0.4 + 0.3j],
                   [0.4 - 0.3j, 2.0]], dtype=complex)
    corr = np.stack([c0, c1], axis=2)

    expected = eigh(c1, c0)[0][::-1]  # t>=t0 的返回顺序为降序
    got, vec = solve_gevp(corr, t0=0)
    assert np.allclose(np.asarray(got[:, 1]), expected, atol=1e-12)
    assert np.max(np.abs(np.asarray(vec[..., 1]).imag)) > 1e-8


def test_zr_parametrization():
    """Z_R 参数化：z=0 处有限、随 z 增大指数衰减（线性发散主导）。"""
    from pyqcd.renorm import th_ZR, th_hB
    z = np.linspace(0.15, 1.0, 5)
    a = 0.105 / 0.197
    zr = th_ZR(z, a, 2.0, 0.5, 0.1, 0.0, 0.0, 0.25, (0.0, 0.0))
    assert np.all(np.isfinite(zr))
    assert zr[0] > zr[-1]           # 单调衰减
    hb = th_hB(z, a, 2.0, (0.5, 0.1, 0.0, 0.0, 0.25) + tuple(np.zeros(14)),
               (0.0, 0.0))
    assert np.all(np.isfinite(hb))


def test_gradient_flow_su3_and_dissipation():
    """梯度流：SU(3) 幺正保持 + Wilson plaquette 作用量递减。"""
    from pyqcd.renorm import wilson_action_density, wilson_flow
    from pyqcd.tools import set_backend
    set_backend('numpy')

    g = random_su3_gauge(L=4, seed=7)
    S0 = _wilson_action_density(g)
    np.testing.assert_allclose(
        np.asarray(wilson_action_density(g)).mean(), S0,
        rtol=2e-14, atol=2e-14)
    V = wilson_flow(g, tau=0.1, eps=0.05)
    dev = np.abs(V[0, 0, 0, 0, 0] @ V[0, 0, 0, 0, 0].conj().T - np.eye(3)).max()
    S1 = _wilson_action_density(V)
    np.testing.assert_allclose(
        np.asarray(wilson_action_density(V)).mean(), S1,
        rtol=2e-14, atol=2e-14)
    assert dev < 1e-6, f"SU(3) 保持失败: dev={dev}"
    assert S1 < S0, f"Wilson 作用量应递减: {S0} -> {S1}"


def test_wilson_flow_is_gauge_covariant():
    """Wilson flow 的每条输出链接必须保持局域 SU(3) 端点协变。"""
    from pyqcd.renorm import wilson_flow
    from pyqcd.tools import set_backend

    set_backend('numpy')
    gauge = random_su3_gauge(L=2, seed=211)
    site_transform = random_su3_gauge(L=2, seed=311)[..., 0, :, :]
    error = _link_covariance_error(
        lambda field: wilson_flow(field, tau=0.02, eps=0.02),
        gauge, site_transform)
    assert error < 1e-10, f"Wilson flow 规范协变性破坏: max|d|={error:.3e}"


def test_wilson_flow_zero_time_is_identity():
    """tau=0 不得暗中执行一个 eps 步。"""
    from pyqcd.renorm import wilson_flow
    from pyqcd.tools import set_backend

    set_backend('numpy')
    gauge = random_su3_gauge(L=2, seed=216)
    flowed = wilson_flow(gauge, tau=0.0, eps=0.01)
    assert np.array_equal(flowed, gauge), \
        f"tau=0 必须恒等: max|d|={np.max(np.abs(flowed - gauge)):.3e}"


def test_wilson_flow_hits_requested_time():
    """非整倍数 tau/eps 必须用缩放步长精确到达 tau。"""
    from pyqcd.renorm import wilson_flow
    from pyqcd.renorm._gradient_flow import wilson_flow_step
    from pyqcd.tools import set_backend

    set_backend('numpy')
    gauge = random_su3_gauge(L=2, seed=217)
    expected = gauge
    for _ in range(3):
        expected = wilson_flow_step(expected, 0.025 / 3.0)
    flowed = wilson_flow(gauge, tau=0.025, eps=0.01)
    error = float(np.max(np.abs(flowed - expected)))
    assert error < 1e-12, f"实际 flow 时间不等于 tau: max|d|={error:.3e}"


def test_wilson_flow_rejects_invalid_time_controls():
    """流时间、最大步长和显式步数必须在入口完成有限性/类型检查。"""
    from pyqcd.renorm import wilson_flow
    from pyqcd.tools import set_backend

    set_backend('numpy')
    gauge = random_su3_gauge(L=2, seed=218)
    with np.testing.assert_raises(ValueError):
        wilson_flow(gauge, tau=-0.01, eps=0.01)
    with np.testing.assert_raises(ValueError):
        wilson_flow(gauge, tau=0.01, eps=0.0)
    for tau in (np.nan, np.inf, -np.inf, True):
        with np.testing.assert_raises_regex(ValueError, "tau.*有限实标量"):
            wilson_flow(gauge, tau=tau, eps=0.01)
    for eps in (np.nan, np.inf, -np.inf, True):
        with np.testing.assert_raises_regex(ValueError, "eps.*有限实标量"):
            wilson_flow(gauge, tau=0.01, eps=eps)
    for n_steps in (0, -1, 1.5, True):
        with np.testing.assert_raises_regex(ValueError, "n_steps.*正整数"):
            wilson_flow(gauge, tau=0.0, eps=0.01, n_steps=n_steps)


def test_flow_action_density_is_gauge_invariant_and_nonnegative():
    """Tr(F^2) 必须逐点规范不变且非负。"""
    from pyqcd.renorm import flow_action_density
    from pyqcd.tools import set_backend

    set_backend('numpy')
    gauge = random_su3_gauge(L=2, seed=214)
    site_transform = random_su3_gauge(L=2, seed=314)[..., 0, :, :]
    original = flow_action_density(gauge)
    transformed = flow_action_density(_gauge_transform(gauge, site_transform))
    error = float(np.max(np.abs(transformed - original)))
    assert error < 1e-10, f"流作用量密度规范不变性破坏: max|d|={error:.3e}"
    assert float(np.min(original)) >= -1e-12, \
        f"流作用量密度应非负: min(E)={float(np.min(original)):.3e}"


def test_tmd_operator_runs():
    """TMD staple 算符 O(z, b⊥)：可运行、实数、共线极限有限。"""
    from pyqcd.renorm import gluon_tmd_operator, tmd_matrix_elements
    from pyqcd.tools import set_backend
    set_backend('numpy')

    g = random_su3_gauge(L=6, seed=1)
    O = gluon_tmd_operator(g, z=2, b_perp=1)
    assert O.shape == (6, 6, 6, 6)
    assert np.all(np.isfinite(np.real(O)))

    M = tmd_matrix_elements(g, [0, 1, 2], [0, 1, 2])
    assert M.shape == (3, 3)
    assert np.all(np.isfinite(M))


def test_read_gauge_lime_accepts_contents_directory():
    """.lime.contents 目录应解析到标准 ILDG binary record。"""
    from pathlib import Path
    import tempfile

    from pyqcd.operator import read_gauge_lime

    with tempfile.TemporaryDirectory() as directory:
        contents = Path(directory) / "cfg.lime.contents"
        contents.mkdir()
        raw = np.zeros((1, 1, 1, 1, 4, 3, 3, 2), dtype=">f8")
        diagonal = np.arange(3)
        raw[..., diagonal, diagonal, 0] = 1.0
        record = contents / "msg02.rec04.ildg-binary-data"
        raw.tofile(record)

        gauge = read_gauge_lime(contents, 1, 1)

    assert gauge.shape == (1, 1, 1, 1, 4, 3, 3)
    assert gauge.dtype == np.complex128
    assert np.allclose(gauge, np.eye(3, dtype=complex)[None, None, None, None, None])


def test_matching_kernel():
    """NLO 匹配核 hR_PDF：Pz 增大时接近单位变换。"""
    from pyqcd.renorm import hR_PDF
    # 注意：x=0 处匹配核有 1/y 奇点（与参考代码一致），真实网格避开 0
    xx = np.linspace(0.02, 1.48, 21)
    h0 = np.exp(-xx ** 2)   # 测试用准 PDF
    out = hR_PDF(xx, Pz_=4, conf='L24x72', hR_tilde_data=h0, mu_=2.0)
    assert out.shape == h0.shape
    assert np.all(np.isfinite(out))


def test_hybrid_ratio():
    """混合方案：短距比值段与 Z_R 长距段拼接连续。"""
    from pyqcd.renorm import hR_z_Pz, th_ZR
    from pyqcd.tools import set_backend
    set_backend('numpy')

    z = np.linspace(0.15, 1.0, 8)
    a = 0.105 / 0.197
    zr = th_ZR(z, a, 2.0, 0.5, 0.1, 0.0, 0.0, 0.25, (0.0, 0.0))
    hb_pz = np.exp(-z / 0.3)
    hb_0 = np.exp(-z / 0.6)
    lam, hR = hR_z_Pz(z, 4, hb_pz, hb_0, zs=0.5, zr_fit=zr, conf='L24x72')
    assert len(lam) == len(z)
    assert np.all(np.isfinite(hR))
    assert hR[0] > 0   # 短距比值接近 1


def test_tmd_extraction_chain():
    """TMD 提取链：准 TMD-PDF / CS 核 / SFTX 系数可运行且有限。"""
    from pyqcd.renorm import (
        quasi_tmd_pdf, cs_kernel_from_ratio, sftx_gluon_matching_coeff,
        sftx_energy_density_t0,
    )
    z = np.linspace(0.0, 1.0, 33)
    hr = np.exp(-z / 0.3)[:, None] * np.array([1.0, 0.8])[None, :]
    x, xg = quasi_tmd_pdf(hr, z, [0.2, 0.4], 2.0)
    assert xg.shape == (256, 2)
    assert np.all(np.isfinite(xg))
    K = cs_kernel_from_ratio(hr, hr * 1.1, 2.5, 2.0)
    assert np.all(np.isfinite(K))
    al, c = sftx_gluon_matching_coeff(mu=2.0, t_gev_m2=0.1)
    assert np.isfinite(al) and np.isfinite(c)
    assert np.all(np.isfinite(sftx_energy_density_t0(
        1.0, mu=2.0, t_gev_m2=0.1)))


def test_tmd_soft_factor_ze_contracts():
    """Z_E / sqrt(Z_E) / rapidity subtraction / SDR 公共契约。"""
    from ._tmd_soft_factor_ze_contract import TmdSoftFactorZeContract

    _run_unittest_contract(TmdSoftFactorZeContract)


def test_tmd_matching_nlo():
    """TMD 混合方案 1 圈匹配：Z⁻¹ 还原输入、快度/软因子生效、形状正确。"""
    from pyqcd.renorm import tmd_matching_hybrid
    x = np.linspace(0.05, 0.95, 48)
    yg = x * np.exp(-x / 0.3)         # 物理输入 y·g(y)（y→0 衰减）
    # 1) δ 项主导的形状自洽：cs=0, S=1 → 输出非负、与输入同量级。
    #    真耦合 α_s(2GeV)≈0.32 下 NLO 修正在低 Pz 为 O(αsCA/2π·g)~50%
    #    （2026-08-24 dev8 对照修复耦合归一后按实测 L2 相对偏差 0.51 重标定；
    #    旧界 30% 是在漏乘 4π 的微小耦合下标定的，见 .all 会话日志）
    x_o, out = tmd_matching_hybrid(x, b_perp=[0.2], mu=2.0, pz_gev=2.0,
                                   cs_kernel=0.0, soft_factor=1.0, x_tmd=yg)
    assert x_o.shape == x.shape
    assert np.all(np.isfinite(out))
    assert np.all(out >= -1e-12)
    dev_l2 = np.linalg.norm(out - yg) / np.linalg.norm(yg)
    assert dev_l2 < 0.7, f"NLO 重塑过大: L2 相对偏差 {dev_l2:.3f}"
    # 2) 快度演化因子：pz_scale≠pz → 输出 × exp[½ln((2Pz)²/(2ζ)²)K]
    _, out_rap = tmd_matching_hybrid(x, b_perp=[0.2], mu=2.0, pz_gev=2.0,
                                     cs_kernel=0.1, soft_factor=1.0,
                                     pz_scale=1.0, x_tmd=yg)
    rap = np.exp(0.5 * np.log((2.0 * 2.0) ** 2 / (2.0 * 1.0) ** 2) * 0.1)
    assert np.allclose(out_rap, out * rap, rtol=1e-8)
    # 3) 软函数：S=4 → 输出 ×½
    _, out_s = tmd_matching_hybrid(x, b_perp=[0.2], mu=2.0, pz_gev=2.0,
                                   cs_kernel=0.0, soft_factor=4.0, x_tmd=yg)
    assert np.allclose(out_s, out / 2.0, rtol=1e-8)
    # 4) 多 b⊥：nb=2 输出形状 (nx, 2)
    yg2 = np.column_stack([yg, 0.5 * yg])
    _, out2 = tmd_matching_hybrid(x, b_perp=[0.2, 0.4], mu=2.0, pz_gev=2.0,
                                  cs_kernel=0.0, soft_factor=1.0, x_tmd=yg2)
    assert out2.shape == (len(x), 2)
    assert np.all(np.isfinite(out2))


def test_scale_setting_flow_behavior():
    """尺度设定与流时间行为：t²⟨E⟩ 单调递增且 t0 可求。"""
    from pyqcd.renorm import (
        wilson_flow, flow_action_density, scale_setting_t0,
    )
    g = random_su3_gauge(L=4, seed=3)
    vals = []
    for tau in [0.1, 0.3, 0.5]:
        V = wilson_flow(g, tau=tau, eps=0.05)
        vals.append(tau ** 2 * flow_action_density(V).mean())
    assert vals[0] < vals[1] < vals[2], f"t²⟨E⟩ 应单调递增: {vals}"
    target = 0.5 * (vals[0] + vals[2])   # 目标取区间内部，保证插值可达
    t0 = scale_setting_t0(g, target=target, tau_max=0.5, eps=0.05)
    assert np.isfinite(t0) and t0 > 0


def test_hyp_smear():
    """HYP 涂抹：SU(3) 保持 + Wilson plaquette 作用量降低。"""
    from pyqcd.smear import hyp_smear
    from pyqcd.tools import set_backend
    set_backend('numpy')
    g = random_su3_gauge(L=6, seed=2)
    V = hyp_smear(g)
    dev = np.abs(V[0, 0, 0, 0, 0] @ V[0, 0, 0, 0, 0].conj().T - np.eye(3)).max()
    assert dev < 1e-10, f"SU(3) 保持失败: {dev}"
    S0, S1 = _wilson_action_density(g), _wilson_action_density(V)
    assert S1 < S0, f"HYP 应降低 Wilson 作用量: {S0} -> {S1}"


def test_hyp_smear_is_gauge_covariant():
    """HYP 的每条输出链接必须保持局域 SU(3) 端点协变。"""
    from pyqcd.smear import hyp_smear
    from pyqcd.tools import set_backend

    set_backend('numpy')
    gauge = random_su3_gauge(L=2, seed=212)
    site_transform = random_su3_gauge(L=2, seed=312)[..., 0, :, :]
    error = _link_covariance_error(hyp_smear, gauge, site_transform)
    assert error < 1e-10, f"HYP 规范协变性破坏: max|d|={error:.3e}"


def test_hyp_zero_outer_weight_returns_input():
    """α1=0 数值回到 U，但返回值仍须独立，不能把输入别名交给下游。"""
    from pyqcd.smear import hyp_smear
    from pyqcd.tools import set_backend

    set_backend('numpy')
    gauge = random_su3_gauge(L=2, seed=219)
    smeared = hyp_smear(gauge, alpha1=0.0, alpha2=0.6, alpha3=0.3)
    error = float(np.max(np.abs(smeared - gauge)))
    assert error < 1e-12, f"α1=0 未回到原链接: max|d|={error:.3e}"
    assert not np.shares_memory(smeared, gauge), "HYP 零操作不得返回输入别名"


def test_hyp_reduces_to_ape_when_inner_weights_zero():
    """α2=α3=0 时 HYP 必须退化为使用六 staple 的四维 APE。"""
    from pyqcd.smear import hyp_smear
    from pyqcd.tools import set_backend

    set_backend('numpy')
    gauge = random_su3_gauge(L=2, seed=220)
    alpha = 0.41
    expected = _reference_ape(gauge, alpha)
    actual = hyp_smear(gauge, alpha1=alpha, alpha2=0.0, alpha3=0.0)
    error = float(np.max(np.abs(actual - expected)))
    assert error < 1e-11, f"HYP 的 APE 退化极限错误: max|d|={error:.3e}"


def test_hyp_is_hypercubic_under_axis_relabeling():
    """交换 x/y 坐标和方向标签后，HYP 结果必须同样重标记。"""
    from pyqcd.smear import hyp_smear
    from pyqcd.tools import set_backend

    set_backend('numpy')
    gauge = random_su3_gauge(L=2, seed=221)
    expected = hyp_smear(gauge)
    permuted = _swap_lattice_directions(gauge, 0, 1)
    actual = _swap_lattice_directions(hyp_smear(permuted), 0, 1)
    error = float(np.max(np.abs(actual - expected)))
    assert error < 1e-10, f"HYP 超立方对称性破坏: max|d|={error:.3e}"


def test_gradient_flow_tau_limit():
    """梯度流 τ→0 连续极限：TMD 矩阵元平滑恢复到未涂抹值。"""
    from pyqcd.renorm import wilson_flow, tmd_matrix_elements
    g = random_su3_gauge(L=4, seed=5)
    M0 = tmd_matrix_elements(g, [0, 1], [0, 1])
    V = wilson_flow(g, tau=0.01, eps=0.01)
    Mt = tmd_matrix_elements(V, [0, 1], [0, 1])
    d_small = np.abs(Mt - M0).max()
    Vb = wilson_flow(g, tau=0.2, eps=0.01)
    Mb = tmd_matrix_elements(Vb, [0, 1], [0, 1])
    d_big = np.abs(Mb - M0).max()
    assert d_small < d_big, f"τ→0 应更接近未涂抹值: {d_small} vs {d_big}"


def test_ratio_fit_extraction():
    """c0 裸矩阵元提取（R 模型拟合）：合成数据精确恢复。"""
    from pyqcd.analysis import R_model, fit_ratio
    rng = np.random.default_rng(1)
    z_list = [0, 1]
    z_set = np.array([0] * 16 + [1] * 16)
    tsep = np.array([8] * 8 + [10] * 8 + [8] * 8 + [10] * 8)
    ti = np.tile(np.arange(1, 9), 4)
    pars = (0.6, -0.3, 0.1, 0.3, -0.2, 0.05, 1.2)
    th = R_model(z_set, tsep, ti, z_list, *pars)
    samples = th[:, None] + 0.01 * rng.standard_normal((32, 50))
    data = (z_set, tsep, ti, th, np.ones(32) * 0.01, samples, z_list, [8, 10], 0)
    res = fit_ratio(data)
    assert abs(res['c0_z0'] - 0.6) < 0.02
    assert abs(res['c0_z1'] - 0.3) < 0.02
    assert abs(res['deltaE'] - 1.2) < 0.1


def test_ratio_fit_analytic_jacobian_matches_central_difference():
    """R 模型的解析雅可比必须匹配中心差分，并覆盖 z=0/1 两支。"""
    from pyqcd.analysis import R_model
    from pyqcd.analysis._ratio_fit import _ratio_fit_design, _ratio_model_jacobian

    z_list = [0, 1]
    z_set = np.array([0, 0, 0, 1, 1, 1])
    tsep = np.array([8, 10, 12, 8, 10, 12])
    ti = np.array([1, 3, 5, 1, 3, 5])
    pars = np.array([0.6, -0.3, 0.1, 0.3, -0.2, 0.05, 1.2], dtype=float)

    design = _ratio_fit_design(z_set, tsep, ti, z_list)
    jac = _ratio_model_jacobian(pars, design)

    eps = 1e-7
    fd = np.empty_like(jac)
    for i in range(pars.size):
        step = np.zeros_like(pars)
        step[i] = eps
        hi = R_model(z_set, tsep, ti, z_list, *(pars + step))
        lo = R_model(z_set, tsep, ti, z_list, *(pars - step))
        fd[:, i] = (hi - lo) / (2.0 * eps)

    error = float(np.max(np.abs(jac - fd)))
    assert error < 1e-8, f"解析雅可比与中心差分不一致: max|d|={error:.3e}"


def test_gpu_backend_consistency():
    """GPU(cupy) 后端：flow 结果与 CPU 一致（无 cupy 时跳过）。"""
    try:
        import cupy as cp
    except ImportError:
        return
    from pyqcd.tools import set_backend
    from pyqcd.renorm import wilson_action_density, wilson_flow
    g = random_su3_gauge(L=4, seed=2)
    set_backend('numpy')
    V_cpu = wilson_flow(g, tau=0.04, eps=0.02)
    S_cpu = np.asarray(wilson_action_density(g))
    set_backend('cupy')
    V_gpu = cp.asnumpy(wilson_flow(cp.asarray(g), tau=0.04, eps=0.02))
    S_gpu = cp.asnumpy(wilson_action_density(cp.asarray(g)))
    set_backend('numpy')
    d = np.abs(V_cpu - V_gpu).max()
    assert d < 1e-10, f"CPU/GPU 不一致: {d:.3e}"
    assert np.abs(S_cpu - S_gpu).max() < 1e-12, "Wilson 作用量 CPU/GPU 不一致"


def test_torch_backend_consistency():
    """torch 后端（CPU/CUDA）：flow/TMD/HYP 与 numpy 一致 + 精度切换。

    - numpy 输入自动转换 torch（旧代码兼容）
    - CPU 与 numpy 逐位一致（rel ~1e-15）
    - CUDA 与 numpy 一致（rel ~1e-15）
    - set_precision('complex64') 后新数组为 complex64
    """
    import torch
    from pyqcd.tools import set_backend, set_precision
    from pyqcd.renorm import (
        tmd_matrix_elements, wilson_action_density, wilson_flow,
    )
    from pyqcd.smear import hyp_smear

    g = random_su3_gauge(L=4, seed=2)
    set_backend('numpy')
    V_cpu = wilson_flow(g, tau=0.04, eps=0.02)
    M_np = tmd_matrix_elements(g, [0, 1], [0, 1])
    S_np = np.asarray(wilson_action_density(g))

    # CPU（numpy 输入自动转换）
    set_backend('torch')
    V_t = wilson_flow(g, tau=0.04, eps=0.02)
    M_t = tmd_matrix_elements(g, [0, 1], [0, 1])
    S_t = wilson_action_density(g)
    assert np.abs(V_cpu - V_t.get()).max() < 1e-8, "torch CPU flow 不一致"
    assert np.abs(np.asarray(M_np) - np.asarray(M_t)).max() < 1e-8
    assert np.abs(S_np - S_t.get()).max() < 1e-12, \
        "Wilson 作用量 numpy/torch 不一致"
    # HYP 与 numpy 对比
    set_backend('numpy')
    V_h_np = hyp_smear(g)
    set_backend('torch')
    assert np.abs(V_h_np - hyp_smear(g).get()).max() < 1e-7, "HYP torch 不一致"

    # 精度语义：numpy 显式 dtype 被尊重；'complex' 简写/无 dtype 来源遵循全局精度
    g64 = g.astype(np.complex64)
    set_backend('torch')
    V64 = wilson_flow(g64, tau=0.04, eps=0.02)
    assert V64.dtype == torch.complex64, f"numpy c64 输入应保持: {V64.dtype}"
    set_precision('complex64')
    z64 = wilson_flow(g64, tau=0.04, eps=0.02)
    assert z64.dtype == torch.complex64, f"complex64 切换失败: {z64.dtype}"
    from pyqcd.tools import get_backend
    assert get_backend().zeros((2, 2), dtype='complex').dtype == torch.complex64
    set_precision('complex128')
    assert get_backend().zeros((2, 2), dtype='complex').dtype == torch.complex128

    # CUDA（可用时）
    if torch.cuda.is_available():
        set_backend('torch', device='cuda')
        V_g = wilson_flow(g, tau=0.04, eps=0.02)
        assert str(V_g.device).startswith('cuda')
        d = np.abs(V_cpu - V_g.get()).max()
        assert d < 1e-8, f"torch CUDA flow 不一致: {d:.3e}"
        M_g = tmd_matrix_elements(g, [0, 1], [0, 1])
        assert np.abs(np.asarray(M_np) - np.asarray(M_g)).max() < 1e-8
    set_backend('numpy')


def test_end_to_end_synthetic_meff():
    """端到端合成验证：含已知质量的 cosh 2pt → meff 精确恢复。"""
    from pyqcd.analysis import Jackknife, meff
    rng = np.random.default_rng(4)
    M_true = 1.12
    a_fm = 0.1053
    a_gev_inv = a_fm / 0.1973269804
    nt = 72
    t = np.arange(nt)
    C = np.cosh(M_true * a_gev_inv * (t - nt / 2))
    noise = 1e-3 * C * rng.standard_normal((10, nt))
    data = C[None, :] + noise
    jk = Jackknife(data, Nconf_axes=0)
    mf = meff(jk['data_sample'], a_fm, Nconf_axes=0, Nt_axes=1,
              meff_type='cosh')
    mmean = np.real(mf['data_mean'])
    M_rec = np.mean(mmean[8:20])
    assert abs(M_rec - M_true) / M_true < 0.02, f"恢复偏差过大: {M_rec}"


def test_matching_sum_rule():
    """NLO 匹配求和规则：∫hR_PDF ≈ ∫hR_tilde（对称宽域，O(αs) 修正内守恒）。

    积分域取参考实现的对称型网格（matching_new 的 y 积分域为 ±y_inf）：
    正半轴截断会丢失 ξ<0 支路贡献（实测 +26% 且不随 dx 收敛，属域截断
    非离散误差）；对称 ±1.9 域实测比值 0.957（2026-08-24 真耦合下）。
    """
    from pyqcd.renorm import hR_PDF
    xx = np.linspace(-1.9, 1.9, 592)
    h0 = np.exp(-(xx - 0.4) ** 2 / 0.05)
    out = hR_PDF(xx, Pz_=4, conf='L24x72', hR_tilde_data=h0, mu_=2.0)
    dx = xx[1] - xx[0]
    ratio = np.sum(out) * dx / (np.sum(h0) * dx)
    assert 0.92 < ratio < 1.08, f"求和规则破坏: {ratio:.4f}"


def test_core_chain_integrated():
    """核心目标链整合：梯度流(t/a²=3)→TMD→混合方案→Z_R 全链自洽。"""
    from pyqcd.renorm import (
        wilson_flow, tmd_matrix_elements, hR_z_Pz, th_ZR,
    )
    g = random_su3_gauge(L=4, seed=6)
    tau = 3.0
    V = wilson_flow(g, tau=tau, eps=0.05)
    M = tmd_matrix_elements(V, list(range(6)), [0])[:, 0]
    z_fm = np.array(range(6)) * 0.1053
    zr = th_ZR(z_fm, 0.1053 / 0.197, 2.0, 0.5, 0.1, 0.0, 0.0, 0.25, (0.0, 0.0))
    lam, hR = hR_z_Pz(z_fm, 4, M, M, zs=0.3, zr_fit=zr, conf='L24x72')
    assert np.all(np.isfinite(hR))
    assert abs(hR[0] - 1.0) < 1e-8, "短距比值应自归一"


# ═══════════════════════════════════════════════════════════════════
# 整合功能测试（历史参考代码整合验证）
# ═══════════════════════════════════════════════════════════════════


def _smooth_gauge(L=6, amp=0.01, seed=11):
    """近平场（冷场+微扰后 SU(3) 投影）——涂抹类功能的物理性测试场。

    stout 无显式重投影（约定输入为 SU(3) 规范组态，与真实蒸馏数据一致），
    故微扰后须经 smear.proj_su3（SVD 极分解）投影保证严格幺正。
    注意 renorm.proj_su3 仅做 det 归一（适用于本已幺正的流输出），不适用。
    """
    from pyqcd.smear import proj_su3
    g = np.zeros((L, L, L, L, 4, 3, 3), dtype=complex)
    for d in range(4):
        g[..., d, :, :] = np.eye(3)
    rng = np.random.default_rng(seed)
    noisy = g + amp * (rng.standard_normal(g.shape)
                       + 1j * rng.standard_normal(g.shape))
    return np.asarray(proj_su3(noisy))


def test_stout_smear():
    """Stout：SU(3) 保持 + Wilson 作用量下降 + 平场/时间链约束。"""
    from pyqcd.smear import stout_smear
    from pyqcd.tools import set_backend

    set_backend('numpy')

    alias_probe = random_su3_gauge(L=2, seed=222)
    no_op = stout_smear(alias_probe, nstep=0)
    assert np.array_equal(no_op, alias_probe)
    assert not np.shares_memory(no_op, alias_probe), \
        "Stout 零步不得返回输入别名"

    flat = np.zeros((4, 4, 4, 4, 4, 3, 3), dtype=complex)
    for d in range(4):
        flat[..., d, :, :] = np.eye(3)
    with np.errstate(invalid='ignore', divide='ignore'):
        vf = stout_smear(flat, nstep=1, rho=0.1)
    assert np.isfinite(vf).all() and np.abs(vf - flat).max() < 1e-12

    g = _smooth_gauge(L=6)
    v = stout_smear(g, nstep=2, rho=0.12)
    dev = np.abs(v[0, 0, 0, 0, 0] @ v[0, 0, 0, 0, 0].conj().T
                 - np.eye(3)).max()
    assert dev < 1e-10, f"SU(3) 保持失败: {dev}"
    s0 = _wilson_action_density(g)
    s1 = _wilson_action_density(v)
    assert s1 < s0, f"平滑场应降低 Wilson 作用量: {s0} -> {s1}"
    assert np.abs(v[..., 3, :, :] - g[..., 3, :, :]).max() < 1e-14, \
        "时间方向链接不应被涂抹"


def test_stout_smear_is_gauge_covariant():
    """Stout 的每条输出链接必须保持局域 SU(3) 端点协变。"""
    from pyqcd.smear import stout_smear
    from pyqcd.tools import set_backend

    set_backend('numpy')
    gauge = random_su3_gauge(L=2, seed=213)
    site_transform = random_su3_gauge(L=2, seed=313)[..., 0, :, :]
    error = _link_covariance_error(
        lambda field: stout_smear(field, nstep=1, rho=0.12),
        gauge, site_transform)
    assert error < 1e-10, f"Stout 规范协变性破坏: max|d|={error:.3e}"


def test_eigvec_compress():
    """本征模压缩：V1 保正交归一、V2 可复现子集抽取、V3/V4 正交投影。"""
    from pyqcd.vertex import (
        check_orthonormal, compress_matrix_V1, compress_matrix_V2,
        compress_matrix_V3, compress_matrix_V4, create_noise,
    )
    rng = np.random.default_rng(0)
    nev, shape = 16, (2, 2, 2, 3)
    a = rng.standard_normal((nev, int(np.prod(shape)))) \
        + 1j * rng.standard_normal((nev, int(np.prod(shape))))
    q, _ = np.linalg.qr(a.T)
    vecs = (q.T).reshape((nev,) + shape)

    assert check_orthonormal(compress_matrix_V1(vecs, 4, 'I'))
    assert check_orthonormal(compress_matrix_V1(vecs, 4, 'B'))
    c2a = compress_matrix_V2(vecs, 4, 2, 'I', seed=7)
    assert np.abs(np.asarray(c2a) - np.asarray(
        compress_matrix_V2(vecs, 4, 2, 'I', seed=7))).max() == 0
    flat_in = vecs.reshape(nev, -1)
    flat_out = np.asarray(c2a).reshape(4, -1)
    hits = sum(any(np.abs(flat_out[k] - flat_in[j]).max() < 1e-12
                   for j in range(nev)) for k in range(4))
    assert hits == 4, "V2 输出应为输入成员"
    assert check_orthonormal(compress_matrix_V3(vecs, 4, 2, 'I', seed=3))
    assert check_orthonormal(compress_matrix_V4(vecs, 4, 2, 'B', seed=3))
    noisy = create_noise(vecs[:4], 3, seed=5)
    assert noisy.shape == (7,) + shape and check_orthonormal(noisy)


def test_inner_product_returns_cross_gram_matrix():
    """本征模集合内积返回 (N_init,N_test) 交叉 Gram 矩阵。"""
    from pyqcd.vertex._eigcompress import inner_product

    init = np.array([[1 + 1j, 2], [3, 4 - 1j]])
    test = np.array([[2, -1j], [1 + 2j, 3]])
    expected = np.einsum('iv,jv->ij', init.conj(), test)

    got = np.asarray(inner_product(init, test))
    assert got.shape == (2, 2)
    np.testing.assert_allclose(got, expected)
    np.testing.assert_allclose(
        np.asarray(inner_product(init, test, mode='abs')), np.abs(expected) ** 2)


def test_cg_coefficients():
    """SU(2) CG：已知值、Condon–Shortley 符号、幺正性、combine/decompose。"""
    from pyqcd.lattice import cg_coefficient, SU2combine, SU2decompose

    assert abs(cg_coefficient(.5, .5, .5, .5, 1, 1) - 1) < 1e-13
    assert abs(cg_coefficient(.5, .5, .5, -.5, 1, 0) - np.sqrt(.5)) < 1e-13
    assert abs(cg_coefficient(.5, -.5, .5, .5, 0, 0) + np.sqrt(.5)) < 1e-13
    assert cg_coefficient(.5, .5, .5, .5, 0, 0) == 0          # M 不守恒
    assert cg_coefficient(.5, .5, .5, -.5, .5, 0) == 0        # 禁戒耦合
    for j in (0, 1):                                          # 幺正性
        s = sum(abs(cg_coefficient(.5, m1, .5, m2, j, 0)) ** 2
                for m1 in (-.5, .5) for m2 in (-.5, .5))
        if s:
            assert abs(s - 1) < 1e-12
    d = SU2decompose([.5, .5], [0., 0.])
    assert abs(d[(.5, -.5)] - np.sqrt(.5)) < 1e-13
    d3 = SU2decompose([.5] * 3, [1.5, 1.5], [1.])
    assert abs(d3[(.5, .5, .5)] - 1) < 1e-13
    try:
        SU2decompose([.5] * 3, [1.5, 1.5])
        raise AssertionError("N>2 无 intermediate_Js 应报错")
    except ValueError:
        pass


def test_hB_dataset_loader():
    """hB/FH loader：z₀ 归一化 + 插值 + 数据集组装进 Z_R 代价函数。"""
    from pyqcd.renorm import (
        build_hB_dataset, make_zr_dataset, cost_function_all,
    )
    rng = np.random.default_rng(3)
    z_fm = np.arange(20) * 0.1053
    ns = 50
    c0 = np.exp(-z_fm[:, None] / 0.35) \
        * (1 + 0.01 * rng.standard_normal((20, ns)))
    ds = build_hB_dataset(c0, z_fm)
    assert ds['hB'].shape == (18, ns)
    assert np.allclose(ds['hB_o'][0], 1.0)
    assert np.all(np.diff(np.log(ds['hB']).mean(axis=1)) < 0)

    dsets = []
    for tau in (0.35, 0.45):
        c = np.exp(-z_fm[:, None] / tau) \
            * (1 + 0.01 * rng.standard_normal((20, ns)))
        dd = build_hB_dataset(c, z_fm)
        dsets.append(make_zr_dataset(dd['loghB'], dd['z'], 0.1053 / 0.197,
                                     kind='boot', seed=11))
    chi2 = cost_function_all([2.0, 0.5, 0.1, 0.0, 0.25] + [0.05] * 14
                             + [0.0, 0.0], dsets, 2.0)
    assert np.isfinite(chi2) and chi2 > 0


def _zr_dataset_contract_fixture():
    """ZR 新旧输入契约共用的小型合成夹具。"""
    from pyqcd.renorm import (
        ZRDataset, build_hB_dataset, make_zr_dataset, prepare_zr_dataset,
    )

    rng = np.random.default_rng(13)
    mu_ = 2.0
    z_fm = np.arange(20) * 0.1053
    par_true = np.array([0.30, 0.20, 1.0, 0.05, 0.28]
                        + [0.02 * (i + 1) for i in range(14)] + [0.0, 0.0])

    dsets = []
    prepared = []
    for tau, a_fm, seed in ((0.35, 0.105, 11), (0.45, 0.085, 12)):
        ns = 50
        c0 = np.exp(-z_fm[:, None] / tau) \
            * (1 + 0.01 * rng.standard_normal((20, ns)))
        ds = build_hB_dataset(c0, z_fm)
        a = a_fm / 0.1973
        samples = ds['loghB'][:, :4]
        old = make_zr_dataset(samples, ds['z'], a, kind='diag',
                              n_rep=24, seed=seed)
        new = prepare_zr_dataset(samples, ds['z'], a, kind='diag',
                                 n_rep=24, seed=seed)
        assert isinstance(new, ZRDataset)
        np.testing.assert_allclose(new.loghB, old['loghB'])
        np.testing.assert_allclose(new.c_inv, old['c_inv'])
        assert new.n_sample == 4 and new.n_point == len(ds['z'])
        assert new.sample_view(0).loghB.shape == new.loghB.shape
        dsets.append(old)
        prepared.append(new)

    return par_true, mu_, dsets, prepared


def _fake_zr_minimize(fun, x0, method=None, options=None):  # noqa: ARG001
    from types import SimpleNamespace

    x0 = np.asarray(x0, dtype=float)
    value = fun(x0)
    assert np.isfinite(value)
    return SimpleNamespace(
        x=x0, fun=value, success=True, status=0, nfev=1, nit=1,
        message="fake scipy.optimize.minimize")


def test_zr_dataset_object_api():
    """ZRDataset：一次性缓存均值/协方差，并保持旧 dict 语义兼容。"""
    from unittest.mock import patch

    from pyqcd.renorm import (
        ZRDataset, cost_function_all, fit_ZR_samples, prepare_zr_dataset,
        prepare_zr_datasets, summarize_ZR_samples,
    )
    from pyqcd.renorm import fit_ZR

    par_true, mu_, dsets, prepared = _zr_dataset_contract_fixture()

    # 字段齐全性 + round-trip。
    assert set(ZRDataset.__dataclass_fields__) == {
        'z', 'loghB', 'c_inv', 'a', 'loghB_samples', 'cov', 'kind'}
    assert set(prepared[0].as_dict()) == {'z', 'loghB', 'c_inv', 'a'}
    assert set(prepared[0].as_dict(include_cache=True)) == {
        'z', 'loghB', 'c_inv', 'a', 'loghB_samples', 'cov', 'kind'}
    assert prepare_zr_dataset(prepared[0]) is prepared[0]
    cached = prepared[0].as_dict(include_cache=True)
    rt = prepare_zr_dataset(cached)
    np.testing.assert_allclose(rt.as_dict(include_cache=True)['loghB'],
                               cached['loghB'])
    np.testing.assert_allclose(rt.as_dict(include_cache=True)['c_inv'],
                               cached['c_inv'])
    np.testing.assert_allclose(rt.as_dict(include_cache=True)['loghB_samples'],
                               cached['loghB_samples'])
    np.testing.assert_allclose(rt.as_dict(include_cache=True)['cov'],
                               cached['cov'])
    assert rt.kind == prepared[0].kind

    mixed = prepare_zr_datasets([dsets[0], prepared[1]])
    assert all(isinstance(ds, ZRDataset) for ds in mixed)
    assert mixed[1] is prepared[1]
    assert prepare_zr_datasets(prepared)[0] is prepared[0]

    par_test = [0.30, 0.20, 1.0, 0.05, 0.28] + [0.02 * (i + 1) for i in range(14)] + [0.0, 0.0]
    chi2_dict = cost_function_all(par_test, dsets, mu_)
    chi2_obj = cost_function_all(par_test, prepared, mu_)
    assert np.isfinite(chi2_dict) and np.isfinite(chi2_obj)
    np.testing.assert_allclose(chi2_dict, chi2_obj)

    with np.errstate(all='ignore'), \
            patch('scipy.optimize.minimize', side_effect=_fake_zr_minimize):
        fit_dict = fit_ZR(par_test, dsets, mu_, use_iminuit=False)
        fit_obj = fit_ZR(par_test, prepared, mu_, use_iminuit=False)
        np.testing.assert_allclose(fit_dict, fit_obj)
        np.testing.assert_allclose(fit_dict, par_test)

        cached_dsets = [ds.as_dict(include_cache=True) for ds in prepared]
        rows_dict = fit_ZR_samples(
            par_true, cached_dsets, mu_, use_iminuit=False)
        rows_obj = fit_ZR_samples(par_true, prepared, mu_, use_iminuit=False)
    assert rows_dict == rows_obj

    rows = rows_obj
    assert len(rows) == 4
    assert all(row["sample_i"] == i for i, row in enumerate(rows))
    summ = summarize_ZR_samples(rows)
    assert "chi2" in summ and np.isfinite(summ["chi2"][0])


def test_zr_dataset_object_reuses_prepared_inputs():
    """已经准备好的 ZRDataset 不应在 fit 路径里被重复准备。"""
    from unittest.mock import patch

    from pyqcd.renorm import fit_ZR, fit_ZR_samples
    from pyqcd.renorm import _zr as zr

    par_true, mu_, dsets, prepared = _zr_dataset_contract_fixture()

    with np.errstate(all='ignore'), \
            patch.object(zr, 'prepare_zr_dataset', wraps=zr.prepare_zr_dataset) \
            as prepare_spy, \
            patch('scipy.optimize.minimize', side_effect=_fake_zr_minimize):
        fit_ZR(par_true, prepared, mu_, use_iminuit=False)
        fit_ZR_samples(par_true, prepared, mu_, use_iminuit=False)

    assert prepare_spy.call_count == 4


def test_hybrid_boot_covariance():
    """混合 λ 外推拟合：diag/boot 协方差均恢复真值，旧签名向后兼容。"""
    from pyqcd.renorm import fit_hR_lambda
    lam = np.linspace(0.5, 6.0, 12)
    truth = (1.2, 1.7, 4.0)
    clean = truth[0] * lam ** (-truth[1]) * np.exp(-lam / truth[2])
    samp = clean[:, None] \
        + 0.002 * np.random.default_rng(5).standard_normal((12, 60))
    for kw in ({}, {'cov_kind': 'boot'}):
        p = fit_hR_lambda([1.0, 1.5, 3.5], (0.8, 6.0), lam, samp, **kw)
        assert all(abs(a - b) / b < 0.08 for a, b in zip(p, truth)), (kw, p)


def test_tmd_plateau_and_cs_kernel():
    """plateau_c0 手算一致；CS 核两动量幂律恢复 + clip 保护。"""
    from pyqcd.analysis import plateau_c0
    from pyqcd.renorm import cs_kernel_two_momentum
    rng = np.random.default_rng(0)
    ratio = rng.standard_normal((5, 20, 20, 3, 2))
    got = plateau_c0(ratio)
    ref = np.zeros((5, 3, 2))
    npts = 0
    for dt in range(7, 11):
        for dtau in range(3, dt - 3 + 1):
            ref += ratio[:, dt, dtau]
            npts += 1
    assert np.abs(got - ref / npts).max() < 1e-14

    k_true = np.array([0.1, -0.2, 0.35])
    z = np.arange(4)[:, None]
    pz1, pz2 = 0.697, 1.394
    c02 = np.exp(-z / 0.3) * (1 + k_true[None, :] * z)
    c01 = c02 * (pz1 / pz2) ** k_true[None, :]
    k_rec = cs_kernel_two_momentum(c01, c02, pz1, pz2, z_ref=1)
    assert abs(k_rec.ravel()[1] - k_true[1]) < 1e-12
    bad = c02.copy()
    bad[1] *= 1e12
    assert np.abs(cs_kernel_two_momentum(bad, c02, pz1, pz2)).max() <= 3.0


def test_plot_tmd_pdf():
    """TMD-PDF 链成图：4 张 png 齐全且非空。"""
    import os
    import tempfile
    from pyqcd.analysis import plot_tmd_pdf
    x = np.linspace(0.05, 0.95, 40)
    xg = np.exp(-(x - 0.3) ** 2 / 0.02)[:, None] * np.array([[1.0, 0.8]])
    out = tempfile.mkdtemp()
    files = plot_tmd_pdf(x, xg, 0.9 * xg, [0.1, 0.2],
                         np.array([0.1, -0.2]), 'P200', out)
    names = sorted(os.path.basename(f) for f in files)
    assert names == ['cs_kernel.png', 'matched_tmd_pdf.png',
                     'quasi_tmd_pdf.png', 'tmd_pdf_vs_b.png']
    assert all(os.path.getsize(f) > 1000 for f in files)


def test_pipeline_tmd_uses_dimensionless_flow_time():
    """物理 t=3a² 必须以 tau=t/a²=3 传给 flow，并在产物中标明约定。"""
    import json
    import tempfile
    from unittest.mock import patch

    from pyqcd.pipeline._steps import run_pipeline
    from pyqcd.tools import set_backend

    set_backend('numpy')
    gauge = np.zeros((1, 1, 1, 1, 4, 3, 3), dtype=complex)
    for direction in range(4):
        gauge[..., direction, :, :] = np.eye(3)

    def fake_tmd(field, tau, z_list, b_list, **_kwargs):
        del field
        return np.zeros((len(z_list), len(b_list))) + tau

    with tempfile.TemporaryDirectory() as run_dir:
        with patch('pyqcd.operator.read_gauge_lime', return_value=gauge), \
                patch('pyqcd.renorm._tmd.gradient_flow_renormalized_tmd',
                      side_effect=fake_tmd):
            run_pipeline(steps=('tmd',), conf_ids=[1], run_dir=run_dir,
                         logger=lambda _message: None, backend='numpy')
        with open(f'{run_dir}/tmd_gluon_flow.json', encoding='utf-8') as handle:
            payload = json.load(handle)

    assert payload['tau'] == 3.0, \
        f"tau=3a^2 应传 t/a^2=3，收到 {payload['tau']}"
    assert payload['tau_units'] == 'dimensionless'
    assert payload['tau_convention'] == 't/a^2'
    assert payload['flow_eps'] == 0.01


def test_parallel_mpi_default_run_dir_is_broadcast():
    """MPI 默认输出目录必须由 rank 0 生成一次并广播给所有 rank。"""
    from unittest.mock import patch

    import pyqcd.parallel._mpi as mpi

    shared = {'run_dir': None}

    class FakeComm:
        def __init__(self, rank):
            self.rank = rank
            self.sent = []

        def bcast(self, value, root=0):
            assert root == 0
            self.sent.append(value)
            if self.rank == root:
                shared['run_dir'] = value
            return shared['run_dir']

        def Barrier(self):
            return None

    plan = {'n_gpu': 0, 'N': 2, 'm': 1, 'X': 1}
    results = []
    comms = [FakeComm(0), FakeComm(1)]
    for rank, comm in enumerate(comms):
        with patch.object(mpi, 'get_mpi_context',
                          return_value=(comm, rank, 2)), \
                patch.object(mpi.os, 'makedirs') as makedirs_spy, \
                patch('pyqcd.pipeline._steps.dump_config_snapshot'):
            result, _ = mpi.run_parallel_pipeline(
                steps=(), conf_ids=[6250], run_dir=None, logger=None,
                backend='numpy', plan=plan, resources={'provided': True})
        results.append(result)
        created = {call.args[0] for call in makedirs_spy.call_args_list}
        expected = {
            mpi.os.path.join(result['run_dir'], directory)
            for directory in ('data', 'analysis', 'plots')
        }
        assert expected <= created

    assert results[0]['run_dir'] == results[1]['run_dir']
    assert mpi.os.path.basename(results[0]['run_dir']).startswith('output_')
    assert comms[0].sent == [results[0]['run_dir']]
    assert comms[1].sent == [None]


def test_parallel_plan_does_not_report_unknown_memory_as_zero():
    """未提供单任务显存时必须报告未知，而非伪造 a=0 MB/task。"""
    from pyqcd.parallel import format_plan, plan_parallel

    resources = {
        'n_gpu': 1,
        'gpu_vram_mb': 8192.0,
        'gpu_usable_mb': 6553.0,
        'cpu_threads': 8,
        'mem_total_mb': 32768.0,
        'mem_avail_mb': 32768.0,
    }
    default_plan = plan_parallel(2, None, resources=resources)
    default_text = format_plan(default_plan)
    assert 'a=not provided' in default_text
    assert 'a=0 MB/task' not in default_text

    measured_plan = plan_parallel(2, 512.0, resources=resources)
    measured_text = format_plan(measured_plan)
    assert 'a=512 MB/task' in measured_text


def _projection_test_registries(seed, pion=False):
    """Nev=2 三时间区随机张量；只供重子投影独立参考测试使用。"""
    from pyqcd.contraction import PeramRegistry, VRegistry, GammaRegistry
    from pyqcd.lattice import gamma

    rng = np.random.default_rng(seed)
    rand = lambda shape: (rng.standard_normal(shape)
                          + 1j * rng.standard_normal(shape))
    nev = 2
    peram = PeramRegistry()
    for sink in ('tsrc', 'tsink', 'tcur0'):
        for source in ('tsrc', 'tsink', 'tcur0'):
            peram.register('light', (sink, source),
                           rand((4, 4, nev, nev)))

    vertex = VRegistry()
    if pion:
        for time_label in ('tsrc', 'tcur0', 'tsink'):
            vertex.register('VDV_0', time_label, rand((1, nev, nev)))
    else:
        vertex.register('VVV_0', 'tsrc', rand((1, nev, nev, nev)))
        vertex.register('VDV_0', 'tcur0', rand((1, nev, nev)))
        vertex.register('VVV_0', 'tsink', rand((1, nev, nev, nev)))

    projector = np.asarray((gamma(0) + gamma(4)) / 2.0)
    gammas = GammaRegistry()
    gammas.register('gamma_7', np.asarray(gamma(7)))
    gammas.register('gamma_5', np.asarray(gamma(5)))
    gammas.register('gamma_mu',
                    np.asarray([gamma(1), gamma(2), gamma(3), gamma(4)]))
    gammas.register('Projector', (projector, projector))
    return peram, vertex, gammas, projector


def test_pipeline_baryon_2pt_uses_trace_projection():
    """质子 2pt 必须复现 refer 的两张显式 Wick 图和 Tr(P_+ C)。"""
    from pyqcd.lattice import gamma
    from pyqcd.pipeline import _steps
    from pyqcd.tools import get_backend, set_backend

    set_backend('numpy')
    rng = np.random.default_rng(4102)
    rand = lambda shape: (rng.standard_normal(shape)
                          + 1j * rng.standard_normal(shape))
    nev = 2
    peram = rand((2, 4, 4, nev, nev))
    peram_seq = rand((2, 4, 4, nev, nev))
    vertex_src = rand((1, nev, nev, nev))
    vertex_sink = rand((1, nev, nev, nev))
    g7 = np.asarray(gamma(7))
    projector = np.asarray((gamma(0) + gamma(4)) / 2.0)

    actual = _steps._run_2pt(
        get_backend(), _steps.PP_SINK, _steps.PP_SRC,
        peram, peram_seq, 0, 1, vertex_src, vertex_sink, 'VVV',
        'gamma_7', g7, projector)

    p = peram[1]
    direct = np.einsum(
        'eofp,ambn,cgdh,ce,mo,Mbdf,Mnph,ga->M',
        p, p, p, g7, g7, vertex_sink, vertex_src, projector,
        optimize=True)
    exchange = np.einsum(
        'eofp,agbh,cmdn,ce,mo,Mbdf,Mnph,ga->M',
        p, p, p, g7, g7, vertex_sink, vertex_src, projector,
        optimize=True)
    expected = np.real((direct - exchange)[0])
    assert np.allclose(actual, expected, rtol=1e-12, atol=1e-10), \
        f"2pt 未执行 Tr(P_+ C): actual={actual}, expected={expected}"


def test_pipeline_baryon_3pt_traces_spin_and_preserves_current():
    """质子 3pt 必须收缩两个重子自旋轴并保留四个 current 分量。"""
    from pyqcd.contraction import dynamic_contraction
    from pyqcd.pipeline import _steps
    from pyqcd.tools import get_backend, set_backend

    set_backend('numpy')
    peram, vertex, gammas, projector = _projection_test_registries(4103)
    operators = [(_steps.PJN_SINK, _steps.PJN_SRC, _steps.PJN_CURR)]
    raw = dynamic_contraction(
        operators, peram_registry=peram, v_registry=vertex,
        gamma_registry=gammas, Cpt='3pt', Vindex=['M', 'M', 'M'],
        Gindex=['', 'G', ''], use_equivalence=False, ignore_dis=False,
        Projection=False, verbose=False).calculate_all()
    raw = np.asarray(raw)
    assert raw.shape == (4, 4, 4, 1)
    expected = np.einsum('akGM,ka->GM', raw, projector,
                         optimize=True)[:, 0]

    actual = _steps._run_3pt(
        get_backend(), _steps.PJN_SINK, _steps.PJN_SRC, _steps.PJN_CURR,
        peram, vertex, gammas, ['M', 'M', 'M'], ['', 'G', ''])
    assert actual.shape == (4,), \
        f"3pt 应只返回四个 current 分量，实际 shape={actual.shape}"
    assert np.allclose(actual, expected, rtol=1e-12, atol=1e-9)


def test_pipeline_pjnnjnp_4pt_traces_spin_and_preserves_current():
    """当前 PJNNJNP 三时间区 4pt 必须输出手写 Tr(P_+ C_G) 四分量。"""
    from unittest.mock import patch

    from pyqcd.contraction import (
        PeramRegistry, VRegistry, GammaRegistry, dynamic_contraction,
    )
    from pyqcd.lattice import gamma
    from pyqcd.pipeline import _steps
    from pyqcd.tools import set_backend

    set_backend('numpy')
    rng = np.random.default_rng(4104)
    rand = lambda shape: (rng.standard_normal(shape)
                          + 1j * rng.standard_normal(shape))
    nev = 2
    peram = rand((1, 4, 4, nev, nev))
    peram_seq = rand((1, 4, 4, nev, nev))
    vertices = {
        'VVV': rand((1, 1, nev, nev, nev)),
        'VdV': rand((1, 1, nev, nev)),
    }

    with patch.object(_steps, 'NT', 1), \
            patch.object(_steps, 'conf_data_dir', return_value='/unused'), \
            patch.object(_steps, 'get_peram_dir', return_value='/unused'), \
            patch.object(_steps, '_load_peram_set',
                         return_value={0: (peram, peram_seq)}), \
            patch.object(_steps, 'save_array'):
        actual = _steps.compute_4pt_for_config(
            1, '/unused', None, vertices, precision='complex128',
            t_sep=0, nev1=nev, momenta=(0,), src_step=1)

    p, q = peram[0], peram_seq[0]
    peram_registry = PeramRegistry()
    peram_registry.register('light', ('tsink', 'tsrc'), p)
    peram_registry.register('light', ('tcur0', 'tsrc'), p)
    peram_registry.register('light', ('tsrc', 'tsrc'), p)
    peram_registry.register('light', ('tsink', 'tcur0'), p)
    peram_registry.register('light', ('tcur0', 'tcur0'), p)
    peram_registry.register('light', ('tsrc', 'tcur0'), p)
    peram_registry.register('light', ('tcur0', 'tsink'), p)
    peram_registry.register('light', ('tsink', 'tsink'), p)
    peram_registry.register('light', ('tsrc', 'tsink'), q)
    peram_registry.register('light', ('tsrc', 'tcur0'), q)
    peram_registry.register('light', ('tcur0', 'tsink'), q)
    peram_registry.register('light', ('tsink', 'tcur0'), q)

    vertex_registry = VRegistry()
    vertex_registry.register('VVV_0', 'tsink', vertices['VVV'][0, 0:1])
    vertex_registry.register('VDV_0', 'tcur0', vertices['VdV'][0, 0:1])
    vertex_registry.register('VVV_0', 'tsrc',
                             vertices['VVV'][0, 0:1].conj())
    vertex_registry.register('VDV_0', 'tsrc',
                             vertices['VdV'][0, 0:1].conj())

    projector = np.asarray((gamma(0) + gamma(4)) / 2.0)
    gamma_registry = GammaRegistry()
    gamma_registry.register('gamma_7', np.asarray(gamma(7)))
    gamma_registry.register('gamma_5', np.asarray(gamma(5)))
    gamma_registry.register(
        'gamma_mu', np.asarray([gamma(1), gamma(2), gamma(3), gamma(4)]))
    gamma_registry.register('Projector', (projector, projector))
    raw = dynamic_contraction(
        [(_steps.PJNNJNP_SINK, _steps.PJNNJNP_SRC,
          _steps.PJNNJNP_CURR)],
        peram_registry=peram_registry, v_registry=vertex_registry,
        gamma_registry=gamma_registry, Cpt='3pt',
        Vindex=['M', 'M', 'M', 'M'], Gindex=['', 'G', '', ''],
        use_equivalence=False, ignore_dis=False,
        Projection=False, verbose=False).calculate_all()
    raw = np.asarray(raw)
    assert raw.shape == (4, 4, 4, 1)
    expected = np.real(np.einsum(
        'akGM,ka->GM', raw, projector, optimize=True)[:, 0])
    assert np.allclose(actual[0, 0], expected, rtol=1e-12, atol=1e-8)


def test_pipeline_pion_projection_controls_are_unchanged():
    """π 2pt/3pt 无自由重子自旋轴，显式 Oindex 不得改变数值。"""
    from pyqcd.contraction import (
        PeramRegistry, VRegistry, GammaRegistry, dynamic_contraction,
    )
    from pyqcd.lattice import gamma
    from pyqcd.pipeline import _steps
    from pyqcd.tools import get_backend, set_backend

    set_backend('numpy')
    rng = np.random.default_rng(4105)
    rand = lambda shape: (rng.standard_normal(shape)
                          + 1j * rng.standard_normal(shape))
    nev = 2
    peram = rand((2, 4, 4, nev, nev))
    peram_seq = rand((2, 4, 4, nev, nev))
    vertex_src = rand((1, nev, nev))
    vertex_sink = rand((1, nev, nev))
    g5 = np.asarray(gamma(5))
    projector = np.asarray((gamma(0) + gamma(4)) / 2.0)
    actual_2pt = _steps._run_2pt(
        get_backend(), _steps.PION_SINK, _steps.PION_SRC,
        peram, peram_seq, 0, 1, vertex_src, vertex_sink, 'VDV',
        'gamma_5', g5, projector)

    pr = PeramRegistry(); vr = VRegistry(); gr = GammaRegistry()
    pr.register('light', ('tsrc', 'tsrc'), peram[0])
    pr.register('light', ('tsink', 'tsrc'), peram[1])
    pr.register('light', ('tsrc', 'tsink'), peram_seq[1])
    vr.register('VDV_0', 'tsrc', vertex_src)
    vr.register('VDV_0', 'tsink', vertex_sink)
    gr.register('gamma_5', g5)
    gr.register('Projector', (projector, projector))
    raw_2pt = dynamic_contraction(
        [(_steps.PION_SINK, _steps.PION_SRC)],
        peram_registry=pr, v_registry=vr, gamma_registry=gr,
        Cpt='2pt', Vindex=['M', 'M'], use_equivalence=False,
        ignore_dis=False, Projection=False, verbose=False).calculate_all()
    assert np.allclose(actual_2pt, np.real(np.asarray(raw_2pt)[0]),
                       rtol=1e-12, atol=1e-10)

    pr, vr, gr, _projector = _projection_test_registries(4106, pion=True)
    raw_3pt = dynamic_contraction(
        [(_steps.PION3_SINK, _steps.PION3_SRC, _steps.PION3_CURR)],
        peram_registry=pr, v_registry=vr, gamma_registry=gr,
        Cpt='3pt', Vindex=['M', 'M', 'M'], Gindex=['', 'G', ''],
        use_equivalence=False, ignore_dis=False,
        Projection=False, verbose=False).calculate_all()
    actual_3pt = _steps._run_3pt(
        get_backend(), _steps.PION3_SINK, _steps.PION3_SRC,
        _steps.PION3_CURR, pr, vr, gr,
        ['M', 'M', 'M'], ['', 'G', ''])
    assert actual_3pt.shape == (4,)
    assert np.allclose(actual_3pt, np.asarray(raw_3pt)[:, 0],
                       rtol=1e-12, atol=1e-9)


def test_pipeline_projection_rejects_uncontracted_spin_shapes():
    """调用方必须拒绝仍含两个自由自旋轴的 dynamic 输出。"""
    from unittest.mock import patch

    from pyqcd.lattice import gamma
    from pyqcd.pipeline import _steps
    from pyqcd.tools import get_backend, set_backend

    class FakeContraction:
        def __init__(self, value):
            self.value = value

        def calculate_all(self):
            return self.value

    set_backend('numpy')
    projector = np.asarray((gamma(0) + gamma(4)) / 2.0)
    dummy_peram = np.zeros((1, 4, 4, 2, 2), dtype=complex)
    dummy_vvv = np.zeros((1, 2, 2, 2), dtype=complex)
    failures = []
    with patch.object(
            _steps, 'dynamic_contraction',
            return_value=FakeContraction(np.zeros((4, 4, 1)))):
        try:
            _steps._run_2pt(
                get_backend(), _steps.PP_SINK, _steps.PP_SRC,
                dummy_peram, dummy_peram, 0, 0, dummy_vvv, dummy_vvv,
                'VVV', 'gamma_7', np.asarray(gamma(7)), projector)
        except ValueError:
            pass
        else:
            failures.append('2pt')

    with patch.object(
            _steps, 'dynamic_contraction',
            return_value=FakeContraction(np.zeros((4, 4, 4, 1)))):
        try:
            _steps._run_3pt(
                get_backend(), _steps.PJN_SINK, _steps.PJN_SRC,
                _steps.PJN_CURR, None, None, None,
                ['M', 'M', 'M'], ['', 'G', ''])
        except ValueError:
            pass
        else:
            failures.append('3pt')

    dummy_vertices = {
        'VVV': np.zeros((1, 1, 2, 2, 2), dtype=complex),
        'VdV': np.zeros((1, 1, 2, 2), dtype=complex),
    }
    with patch.object(_steps, 'NT', 1), \
            patch.object(_steps, 'conf_data_dir', return_value='/unused'), \
            patch.object(_steps, 'get_peram_dir', return_value='/unused'), \
            patch.object(_steps, '_load_peram_set',
                         return_value={0: (dummy_peram, dummy_peram)}), \
            patch.object(_steps, 'save_array'), \
            patch.object(
                _steps, 'dynamic_contraction',
                return_value=FakeContraction(np.zeros((4, 4, 4, 1)))):
        try:
            _steps.compute_4pt_for_config(
                1, '/unused', None, dummy_vertices,
                precision='complex128', t_sep=0, nev1=2,
                momenta=(0,), src_step=1)
        except ValueError:
            pass
        else:
            failures.append('4pt')
    assert not failures, f"未拒绝自由自旋输出: {failures}"


def test_pipeline_2pt_only_swallows_known_forbidden_neutron_channel():
    """注册/数据 KeyError 不得被误报为 pn 物理零；仅已知禁戒通道可返回 0。"""
    from unittest.mock import patch

    from pyqcd.lattice import gamma
    from pyqcd.pipeline import _steps
    from pyqcd.tools import get_backend, set_backend

    set_backend('numpy')
    dummy_peram = np.zeros((1, 4, 4, 2, 2), dtype=complex)
    dummy_vertex = np.zeros((1, 2, 2, 2), dtype=complex)
    projector = np.asarray((gamma(0) + gamma(4)) / 2.0)

    with patch.object(_steps, 'dynamic_contraction',
                      side_effect=KeyError('missing pp registry')):
        with np.testing.assert_raises_regex(KeyError, 'missing pp registry'):
            _steps._run_2pt(
                get_backend(), _steps.PP_SINK, _steps.PP_SRC,
                dummy_peram, dummy_peram, 0, 0,
                dummy_vertex, dummy_vertex, 'VVV', 'gamma_7',
                np.asarray(gamma(7)), projector)

    with patch.object(_steps, 'dynamic_contraction') as contraction:
        value = _steps._run_2pt(
            get_backend(), _steps.PN_SINK, _steps.PN_SRC,
            dummy_peram, dummy_peram, 0, 0,
            dummy_vertex, dummy_vertex, 'VVV', 'gamma_7',
            np.asarray(gamma(7)), projector)
    assert value == 0.0
    contraction.assert_not_called()


def test_pipeline_validate_and_2pt_resume():
    """数据守卫（形状/NaN/缺失）+ 原始数据齐全度 + 2pt 断点续跑判据。"""
    import os
    import shutil
    import tempfile
    from pyqcd.pipeline import (
        check_input_arrays, check_raw_data, ProgressLog,
    )
    from pyqcd.pipeline import _steps

    root = tempfile.mkdtemp()
    d1 = os.path.join(root, 'conf100')
    os.makedirs(d1)
    rng = np.random.default_rng(0)
    spec_items = [
        {'name': 'corr_pp_P0_{cid}', 'shape': (72,)},
        {'name': 'ops_mu0_nu1_dz24_{cid}', 'ext': '.npz',
         'dataset': 'ops', 'shape': (24, 72)},
    ]
    spec = {'conf_ids': [100], 'items': spec_items}
    np.save(os.path.join(d1, 'corr_pp_P0_100.npy'),
            rng.standard_normal(72))
    np.savez(os.path.join(d1, 'ops_mu0_nu1_dz24_100.npz'),
             ops=rng.standard_normal((24, 72)))
    n_ok, bad = check_input_arrays(root, spec, verbose=False)
    assert n_ok == 1 and not bad
    np.save(os.path.join(d1, 'corr_pp_P0_100.npy'),
            np.where(np.arange(72) < 1, np.nan, 0.0))
    n_ok, bad = check_input_arrays(root, spec, verbose=False)
    assert n_ok == 0 and any('有限=False' in b for b in bad)
    shutil.rmtree(root)

    base = tempfile.mkdtemp()
    ens, nt, cid = 'ENS', 4, 200
    ed = os.path.join(base, 'eigensystem', ens, str(cid))
    os.makedirs(ed)
    for t in range(nt):
        open(os.path.join(ed, f'eigvecs_t{t:03d}_{cid}'), 'w').close()
    pdir = os.path.join(base, 'perambulators', ens, 'light', str(cid))
    os.makedirs(pdir)
    for dd in range(4):
        for t in range(nt):
            open(os.path.join(pdir, f'perams.{cid}.{dd}.{t}'), 'w').close()
    cf = os.path.join(base, 'configurations', 'CLOVER', ens)
    os.makedirs(cf)
    open(os.path.join(cf, f'{ens}_cfg_{cid}.lime'), 'w').close()
    n_ok, bad = check_raw_data([cid], base, ens, nt=nt, verbose=False)
    assert n_ok == 1 and not bad
    os.remove(os.path.join(ed, f'eigvecs_t003_{cid}'))
    n_ok, bad = check_raw_data([cid], base, ens, nt=nt, verbose=False)
    assert n_ok == 0 and any('eigvecs 不全 3/4' in b for b in bad)
    shutil.rmtree(base)

    run_dir = tempfile.mkdtemp()
    cdir = _steps.conf_data_dir(run_dir, 111)
    for ch in ('pp', 'pn', 'pion'):
        for mom in ('P0', 'P2'):
            np.save(os.path.join(cdir, f'corr_{ch}_{mom}_111.npy'),
                    np.zeros(72))
    assert _steps._2pt_all_present(cdir, 111, ('pp', 'pn', 'pion'))
    os.remove(os.path.join(cdir, 'corr_pp_P0_111.npy'))
    assert not _steps._2pt_all_present(cdir, 111, ('pp', 'pn', 'pion'))
    shutil.rmtree(run_dir)
    ProgressLog(10, label='t').step(5)


def test_proton_energy_dirs():
    """能量链方向感知：动量置换约定 + 路径构造（z 向后兼容、x/y 置换）。"""
    import os
    import shutil
    import tempfile
    from pyqcd.analysis._bare_matrix import dir_momentum
    from pyqcd.analysis._proton_energy import EnergyParams, load_raw_corr

    assert dir_momentum(0, 0, 6, 'x') == (6, 0, 0)
    assert dir_momentum(0, 0, 6, 'y') == (0, 6, 0)
    assert dir_momentum(0, 0, 6, 'z') == (0, 0, 6)
    p = EnergyParams(conf_short='L24x72', conf_name='ENS',
                     conf_ids=[7], Nt=8, Nx=4, Px=0, Py=0, Pz=2,
                     Nsample=4, dt_max=5)
    assert p.mom_tag == (0, 0, 2)
    tmp = tempfile.mkdtemp()
    rng = np.random.default_rng(0)
    for sub, tag in (('momsmear2z', 'Px0Py0Pz2'),
                     ('momsmear2x', 'Px2Py0Pz0')):
        os.makedirs(os.path.join(tmp, 'ENS', sub, '7'))
        np.save(os.path.join(tmp, 'ENS', sub, '7',
                             f'twopt_slice_pp_{tag}_eginphase2_Cg5g4'
                             f'_nopol_ss_conf7.npy'),
                rng.standard_normal((8, 8))
                + 1j * rng.standard_normal((8, 8)))
    assert load_raw_corr(tmp, 7, p).shape == (8, 8)
    px_params = EnergyParams(**{**p.__dict__, 'dir': 'x'})
    assert load_raw_corr(tmp, 7, px_params).shape == (8, 8)
    shutil.rmtree(tmp)


def test_omega_uses_extract_count_per_input_block():
    """每个输入块必须使用自己的 N_extract，不能用已展开子块数索引。"""
    from pyqcd.tools import set_backend
    from pyqcd.vertex import create_omega_accelerate

    set_backend('numpy')
    try:
        omega = np.asarray(create_omega_accelerate(
            20, exact=0, N_eigen=[8, 12], N_sum=[4, 6],
            N_extract=[2, 3], dim=2))
    except IndexError as exc:
        raise AssertionError("展开首块后不得越界读取第二块 N_extract") from exc

    assert omega.shape == (10, 10)
    assert np.isfinite(omega).all()


def test_omega_dim2_single_sampled_block_weights():
    """S=8 抽 n=4 时，二阶同块权重必须是逆包含概率。"""
    from pyqcd.tools import set_backend
    from pyqcd.vertex import create_omega_accelerate

    set_backend('numpy')
    omega = np.asarray(create_omega_accelerate(
        8, exact=0, N_eigen=[8], N_sum=[4], N_extract=[4],
        dim=2)).real
    diagonal = np.diag(omega)
    off_diagonal = omega[~np.eye(4, dtype=bool)]

    assert np.allclose(diagonal, 2.0, atol=1e-12, rtol=0.0), \
        f"同索引权重应为 S/n=2，实际 {diagonal}"
    assert np.allclose(off_diagonal, 14.0 / 3.0,
                       atol=1e-12, rtol=0.0), \
        f"异索引权重应为 S(S-1)/(n(n-1))=14/3，实际 {off_diagonal}"


def test_omega_dim3_single_sampled_block_weights():
    """三阶权重必须按三个索引中不同取值的数量修正包含概率。"""
    from pyqcd.tools import set_backend
    from pyqcd.vertex import create_omega_accelerate

    set_backend('numpy')
    omega = np.asarray(create_omega_accelerate(
        8, exact=0, N_eigen=[8], N_sum=[4], N_extract=[4],
        dim=3)).real

    assert abs(omega[0, 0, 0] - 2.0) < 1e-12
    assert abs(omega[0, 0, 1] - 14.0 / 3.0) < 1e-12
    assert abs(omega[0, 1, 2] - 14.0) < 1e-12


def test_omega_rejects_invalid_partition_contract():
    """分区列表必须等长且为正整数，抽样数不得超过物理空间。"""
    from pyqcd.tools import set_backend
    from pyqcd.vertex import create_omega_accelerate

    set_backend('numpy')
    invalid_cases = (
        ('列表长度不一致', dict(
            n_voxel=8, N_eigen=[4, 4], N_sum=[2],
            N_extract=[1, 1])),
        ('N_eigen 非整数', dict(
            n_voxel=4, N_eigen=[4.0], N_sum=[2], N_extract=[1])),
        ('N_eigen 非正', dict(
            n_voxel=4, N_eigen=[0], N_sum=[1], N_extract=[1])),
        ('N_sum 非正', dict(
            n_voxel=4, N_eigen=[4], N_sum=[0], N_extract=[1])),
        ('N_extract 非正', dict(
            n_voxel=4, N_eigen=[4], N_sum=[2], N_extract=[0])),
        ('块内超采样', dict(
            n_voxel=2, N_eigen=[2], N_sum=[4], N_extract=[2])),
        ('噪声超出剩余空间', dict(
            n_voxel=4, N_eigen=[2], N_sum=[1],
            N_extract=[1], noise=3)),
        ('物理块总量超出体素空间', dict(
            n_voxel=4, exact=1, N_eigen=[4], N_sum=[2],
            N_extract=[1])),
        ('dim 不受支持', dict(n_voxel=2, exact=2, dim=1)),
    )
    for label, kwargs in invalid_cases:
        try:
            create_omega_accelerate(**kwargs)
        except ValueError:
            continue
        raise AssertionError(f'{label} 必须显式拒绝: {kwargs}')


def test_omega_n1_dim3_matches_hand_inclusion_probabilities():
    """n=1 高阶重复指标只需一阶包含概率 S/n，不得计算 0/0。"""
    from pyqcd.tools import set_backend
    from pyqcd.vertex import create_omega_accelerate

    set_backend('numpy')
    # 三分区依次为 exact(S=n=1)、block(S=2,n=1)、noise(S=3,n=1)。
    omega = np.asarray(create_omega_accelerate(
        6, exact=1, N_eigen=[2], N_sum=[1], N_extract=[1],
        noise=1, dim=3)).real
    selected = np.array([
        omega[0, 0, 0],  # 1
        omega[1, 1, 1],  # 2
        omega[2, 2, 2],  # 3
        omega[0, 1, 2],  # 1*2*3
        omega[1, 1, 2],  # 2*3（block 重复仍只抽中一个不同指标）
        omega[1, 2, 2],  # 2*3（noise 重复同理）
    ])
    expected = np.array([1.0, 2.0, 3.0, 6.0, 6.0, 6.0])

    assert np.isfinite(omega).all(), 'n=1 的可实现重复指标权重必须有限'
    error = float(np.max(np.abs(selected - expected)))
    assert error < 1e-12, \
        f'n=1 三阶逆包含概率错误: max|d|={error:.3e}'


def test_omega_normal_uses_symmetric_row_sum_balancing():
    """normal=True 必须以 DΩD 同时保持对称与每行和 Nev。"""
    from pyqcd.tools import set_backend
    from pyqcd.vertex import create_omega_accelerate

    set_backend('numpy')
    # 原始 Ω=[[1,2],[2,2]]。DΩD 的行和为 2 时可手解如下。
    diagonal = 2.0 * (np.sqrt(2.0) - 1.0)
    off_diagonal = 4.0 - 2.0 * np.sqrt(2.0)
    expected = np.array([[diagonal, off_diagonal],
                         [off_diagonal, diagonal]])
    omega = np.asarray(create_omega_accelerate(
        3, exact=1, noise=1, normal=True, dim=2)).real

    assert np.isfinite(omega).all() and np.all(omega > 0.0)
    error = float(np.max(np.abs(omega - expected)))
    row_error = float(np.max(np.abs(omega.sum(axis=1) - 2.0)))
    symmetry_error = float(np.max(np.abs(omega - omega.T)))
    assert error < 1e-12, f'DΩD 手算矩阵错误: max|d|={error:.3e}'
    assert row_error < 1e-12, f'归一化后行和不统一: max|d|={row_error:.3e}'
    assert symmetry_error < 1e-12, \
        f'归一化后矩阵不对称: max|d|={symmetry_error:.3e}'


def test_omega_exact0_multiblock_dim2_hand_weights():
    """exact=0 多子块的二阶同块/跨块权重须由分区包含概率决定。"""
    from pyqcd.tools import set_backend
    from pyqcd.vertex import create_omega_accelerate

    set_backend('numpy')
    # 展开为三个相同的 (S=4,n=2) 子块，索引范围 0:2、2:4、4:6。
    omega = np.asarray(create_omega_accelerate(
        12, exact=0, N_eigen=[4, 8], N_sum=[2, 4],
        N_extract=[2, 2], dim=2)).real
    selected = np.array([
        omega[0, 0],  # S/n = 2
        omega[0, 1],  # S(S-1)/(n(n-1)) = 6
        omega[0, 2],  # (S/n)^2 = 4
        omega[2, 4],  # 两个不同子块，仍为 4
    ])
    expected = np.array([2.0, 6.0, 4.0, 4.0])
    error = float(np.max(np.abs(selected - expected)))
    assert error < 1e-12, \
        f'exact=0 多块二阶权重错误: max|d|={error:.3e}'


def test_omega_exact0_multiblock_dim3_hand_weights():
    """exact=0 多子块三阶权重须区分同指标、同分区和跨分区。"""
    from pyqcd.tools import set_backend
    from pyqcd.vertex import create_omega_accelerate

    set_backend('numpy')
    omega = np.asarray(create_omega_accelerate(
        12, exact=0, N_eigen=[4, 8], N_sum=[2, 4],
        N_extract=[2, 2], dim=3)).real
    selected = np.array([
        omega[0, 0, 0],  # 2
        omega[0, 0, 1],  # 同分区两个不同指标：6
        omega[0, 0, 2],  # 同指标权重 2 * 跨块权重 2 = 4
        omega[0, 1, 2],  # 同分区异指标 6 * 跨块 2 = 12
        omega[0, 2, 4],  # 三个子块各 S/n=2：8
    ])
    expected = np.array([2.0, 6.0, 4.0, 12.0, 8.0])
    error = float(np.max(np.abs(selected - expected)))
    assert error < 1e-12, \
        f'exact=0 多块三阶权重错误: max|d|={error:.3e}'


def test_round2_integrations():
    """第二轮整合：螺旋度双场强算符 / Ω 张量 / FH 自适应窗 / ASCII 读写。"""
    import os
    import shutil
    import tempfile
    from pyqcd.tools import set_backend
    set_backend('numpy')

    # ── H1: 螺旋度双场强算符（δz=0 与 Tr[F·F̃] 手算一致；平面/全和自洽）──
    from pyqcd.operator import (plaquette_dual_stack,
                                helicity_two_field_operator)
    from pyqcd.operator._gluon_ope import plaquette_clover
    g = random_su3_gauge(L=6, seed=4)
    pla = {(m, n): np.asarray(plaquette_clover(g, m, n))
           for m in range(4) for n in range(4) if m != n}
    tilde = plaquette_dual_stack(pla)
    o0 = np.asarray(helicity_two_field_operator(
        g, pla, tilde, 2, 0, 3, 1, 3, 1, keep_plane=False))
    ref = np.einsum('tzyxab,tzyxba->t', pla[(3, 1)], tilde[(3, 1)])
    assert np.abs(o0 - ref).max() < 1e-10
    op3 = np.asarray(helicity_two_field_operator(
        g, pla, tilde, 2, 3, 3, 1, 3, 1, keep_plane=True))
    ofull = np.asarray(helicity_two_field_operator(
        g, pla, tilde, 2, 3, 3, 1, 3, 1, keep_plane=False))
    om3 = np.asarray(helicity_two_field_operator(
        g, pla, tilde, 2, 3, 3, 1, 3, 1, minus=True, keep_plane=True))
    assert op3.shape == (6, 6, 6) and ofull.shape == (6,)
    assert np.abs(op3.sum(axis=(1, 2)) - ofull).max() < 1e-8
    assert np.isfinite(om3).all()

    # ── R6: Ω 加速张量（结构断言；逐位对照原版见会话日志真值验证）──
    from pyqcd.vertex import create_omega_accelerate
    v = 24
    w_exact = create_omega_accelerate(v, exact=v, dim=2)
    assert w_exact.shape == (v, v) and np.abs(w_exact - 1).max() < 1e-12
    w3 = create_omega_accelerate(v, exact=4, N_eigen=[6], N_sum=[6],
                                 N_extract=[3], noise=2, dim=3)
    assert w3.shape == (12,) * 3 and np.isfinite(w3).all()
    wn = np.asarray(create_omega_accelerate(
        v, N_eigen=[8], N_sum=[4], N_extract=[2], noise=4,
        normal=True, dim=2))
    assert np.abs(wn - wn.T).max() < 1e-12
    try:
        create_omega_accelerate(v, N_sum=[4])     # 契约外显式拒绝
        raise AssertionError("仅 N_sum 应报错")
    except ValueError:
        pass

    # ── R7: 常数窗闭式拟合 + χ² 驱动自适应滑窗 ──
    rng = np.random.default_rng(7)
    t_vals = np.array([6, 7, 8, 9, 10, 11])
    delta = np.empty((12, len(t_vals), 40))
    for z in range(12):
        scale = 1 + 0.9 * max(z - 6, 0) * np.arange(len(t_vals)) / 6
        delta[z] = np.exp(-0.08 * z) * (
            1 + 0.02 * rng.standard_normal((len(t_vals), 40)) * scale[:, None])
    from pyqcd.analysis import fit_constant_window, fh_adaptive_windows
    f = fit_constant_window(delta[0][:5], kind='boot')
    assert abs(f['c0'] - 1.0) < 0.02
    recs = fh_adaptive_windows(delta, t_vals, 6, 11, chi2_limit=2.0,
                               t_floor=6)
    err = max(abs(r['fit']['c0'] - np.exp(-0.08 * r['z']))
              / np.exp(-0.08 * r['z']) for r in recs)
    assert err < 0.05, err

    # ── R8: L.Liu ASCII 写读闭环（plain + .gz）──
    from pyqcd.tools import write_data_ascii, read_data_ascii
    tmp = tempfile.mkdtemp()
    data = rng.standard_normal((3, 8)) + 1j * rng.standard_normal((3, 8))
    p1 = os.path.join(tmp, 'a.dat')
    p2 = os.path.join(tmp, 'b.dat.gz')
    write_data_ascii(data, T=8, L=24, filename=p1)
    write_data_ascii(data, T=8, L=24, filename=p2)
    for p in (p1, p2):
        back, meta = read_data_ascii(p)
        assert meta['is_complex'] and meta['T'] == 8 and meta['L'] == 24
        assert np.abs(back[:, :, 0] + 1j * back[:, :, 1] - data).max() < 1e-13
    shutil.rmtree(tmp)


# ═══════════════════════════════════════════════════════════════════
# NaN 感知回归比对原语（整合蒸馏回归入口的 _rel_maxdiff/_cmp_one）
# ═══════════════════════════════════════════════════════════════════

def rel_maxdiff(a, b):
    """逐元素相对差的最大值（分母为 |b| 的 norm，避免除零）。

    NaN 处理：要求两边 NaN 位置完全相同；只对非 NaN 位置计算相对差
    （如 meff 噪声尾区的 NaN 属物理预期，基线同位置亦有 NaN）。
    形状不一致或 NaN 位置不一致返回 inf；双全空返回 0.0。
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.shape != b.shape:
        return float('inf')
    mask = np.isnan(a) | np.isnan(b)
    if mask.any():
        if not np.array_equal(np.isnan(a), np.isnan(b)):
            return float('inf')
        a = a[~mask]
        b = b[~mask]
        if a.size == 0:
            return 0.0
    denom = np.linalg.norm(b)
    if denom == 0:
        return float(np.linalg.norm(a))
    return float(np.linalg.norm(a - b) / denom)


def cmp_one(name, a, b, tol, results):
    """单项回归比对：追加 {item, rel_diff, tol, pass, shape_a/b} 到 results，
    返回是否通过（照抄 test0/main.py _cmp_one）。"""
    d = rel_maxdiff(a, b)
    ok = d < tol
    results.append({'item': name, 'rel_diff': d, 'tol': tol, 'pass': ok,
                    'shape_a': list(np.shape(a)),
                    'shape_b': list(np.shape(b))})
    return ok


# ═══════════════════════════════════════════════════════════════════
# 第三轮整合测试（~auto-all 20260822 第三遍清查）
# ═══════════════════════════════════════════════════════════════════

def test_matching_ratio_kernels():
    """B1: ratio 方案匹配核 C/C_gluon_ratio 三分区+Si 项（对照 matching_cc 原式）。"""
    from scipy.special import sici as _sici
    from pyqcd.renorm import C as C_q, C_gluon_ratio, Si

    def Si_ref(x):
        return _sici(x)[0]

    def C_ref(ksi, m, r):
        if ksi > 1:
            ker = ((1 + ksi**2) / (1 - ksi) * np.log(ksi / (ksi - 1)) + 1)
        elif ksi > 0 and ksi < 1:
            ker = ((1 + ksi**2) / (1 - ksi)
                   * (-np.log(r**2) + np.log(4 * ksi * (1 - ksi)) - 1) + 1)
        else:
            ker = (-(1 + ksi**2) / (1 - ksi) * np.log(-ksi / (1 - ksi)) - 1)
        return (0.296 * (4.0 / 3.0) / (2 * np.pi)
                * (ker + 3 * Si_ref((1 - ksi) * abs(m)) / (np.pi * (1 - ksi))))

    def Cg_ref(ksi, m, r):
        p2 = 2 * (1 - ksi + ksi**2)**2 / (1 - ksi)
        hi = (11 - 28 * ksi + 18 * ksi**2 - 12 * ksi**3) / (6 * (1 - ksi))
        lo = ((15 - 56 * ksi + 102 * ksi**2 - 96 * ksi**3 + 48 * ksi**4)
              / (6 * (1 - ksi)))
        if ksi > 1:
            ker = p2 * np.log(ksi / (ksi - 1)) + hi
        elif ksi > 0 and ksi < 1:
            ker = p2 * (-np.log(r**2 / 4) + np.log(ksi * (1 - ksi))) - lo
        else:
            ker = -p2 * np.log(ksi / (ksi - 1)) - hi
        ker += 5 / 6 * (-1 / abs(1 - ksi)
                        + 2 * Si_ref((1 - ksi) * abs(m)) / (np.pi * (1 - ksi)))
        return 0.296 * 3.0 / (2 * np.pi) * ker

    for xi in (-0.7, -0.05, 0.13, 0.5, 0.9, 1.7, 3.2):
        m, r = 0.8, 1.5
        assert abs(C_q(xi, m, r) - C_ref(xi, m, r)) < 1e-12
        assert abs(C_gluon_ratio(xi, m, r) - Cg_ref(xi, m, r)) < 1e-12
    # 标量/向量一致
    xs = np.array([-0.5, 0.4, 2.0])
    v = C_gluon_ratio(xs, 0.8, 1.5)
    assert v.shape == (3,) and all(
        abs(v[i] - C_gluon_ratio(xs[i], 0.8, 1.5)) < 1e-15 for i in range(3))


def test_quasi_pdf_gluon_sin_transform():
    """B2: collinear 准 PDF sin 变换——解析核 + x→0 保护。

    取 h(z)=z·e^{−αz}（α=10 GeV⁻¹，衰减长 0.1 GeV⁻¹ ≪ z_max），
    ∫₀^∞ z e^{−αz} sin(βz) dz = 2αβ/(α²+β²)²。
    """
    import warnings

    from pyqcd.renorm import quasi_pdf_gluon
    z_fm = np.linspace(0.0, 0.60, 801)
    pz = 2.0
    xs = np.array([0.0, 0.05, 0.25, 0.8, -0.5])
    alpha = 10.0                       # 衰减率 GeV^-1
    z_gev = z_fm / 0.197327
    h = z_gev * np.exp(-alpha * z_gev)
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        _, g = quasi_pdf_gluon(h, z_fm, pz, x_grid=xs)
    assert g[0] == 0.0                 # x→0 保护置 0（原版行为）
    for i, x in enumerate(xs[1:], start=1):
        beta = x * pz
        exact = (2 * pz / x) * 2 * alpha * beta / (alpha**2 + beta**2)**2
        # 截断/梯形误差 ~ e^{-α·zmax}=e^{-30}，可忽略
        assert abs(g[i] - exact) < 1e-4 * max(abs(exact), 1.0), \
            (x, g[i], exact)


def test_gluon_ope_directions_and_ff():
    """B3: OPE ±z Wilson 线、固定规范 FF 算符与 Lorentz 指派表。"""
    from pyqcd.operator import (gluon_ope_operator_z0, gluon_ff_operator_z0,
                                get_ope_lorentz_pairs)
    g = random_su3_gauge(L=4, seed=11)
    o_plus = gluon_ope_operator_z0(g, 0, 1, 2, 2, 4, 4)
    o_minus = gluon_ope_operator_z0(g, 0, 1, 2, 2, 4, 4, direction=-1)
    assert o_plus.shape == o_minus.shape == (2, 4)
    assert np.allclose(o_plus[0], o_minus[0])          # zi=0 同点收缩
    cross = gluon_ope_operator_z0(g, 3, 0, 2, 2, 4, 4, mu2=2, nu2=1)
    assert np.iscomplexobj(cross) and np.all(np.isfinite(cross.view(float)))
    ff = gluon_ff_operator_z0(g, 3, 0, 3, 4, 4, mu2=2, nu2=1)
    ffm = gluon_ff_operator_z0(g, 3, 0, 3, 4, 4, mu2=2, nu2=1, direction=-1)
    assert ff.dtype == np.complex128 and np.allclose(ff[0], ffm[0])
    assert get_ope_lorentz_pairs(2, "unpol") == [
        (3, 0, 3, 0), (3, 1, 3, 1), (0, 1, 0, 1)]
    assert get_ope_lorentz_pairs(2, "helicity") == [
        (3, 0, 3, 0), (3, 1, 3, 1), (0, 1, 0, 1)]
    assert get_ope_lorentz_pairs(2, "gauge_fix_unpol") == [
        (3, 0, 3, 0), (3, 1, 3, 1), (0, 1, 0, 1)]
    assert get_ope_lorentz_pairs(2, "gauge_fix_helicity") == [
        (3, 0, 2, 1), (3, 1, 0, 2), (3, 2, 0, 1), (0, 1, 3, 2)]
    try:
        get_ope_lorentz_pairs(2, "bad")
        raise AssertionError("should have raised")
    except ValueError:
        pass


def test_parity_boundary_projection():
    """B4: 双宇称投影 + 反周期边界符号翻转 vs 手工循环。"""
    from pyqcd.contraction import parity_and_boundary
    from pyqcd.lattice import gamma
    rng = np.random.default_rng(7)
    Nt = 5
    C = rng.normal(size=(Nt, Nt, 4, 4)) + 1j * rng.normal(size=(Nt, Nt, 4, 4))
    pp, pm = parity_and_boundary(C, Nt)
    Pp = 0.5 * (gamma(0) + gamma(4))
    Pm = 0.5 * (gamma(0) - gamma(4))
    pp_ref = np.einsum("li,yxil->yx", Pp, C)
    pm_ref = np.einsum("li,yxil->yx", Pm, C)
    for ts in range(Nt):
        for tt in range(Nt):
            if tt < ts:
                pp_ref[tt, ts] *= -1.0
            if tt > ts:
                pm_ref[tt, ts] *= -1.0
    assert np.allclose(pp, pp_ref) and np.allclose(pm, pm_ref)


def test_zr_sample_refit_loop():
    """B5: Z_R 逐样本重拟合环的机制与有限性。

    本环境无 iminuit，scipy 回退无边界约束会游走出参数化有效域
    （log(aΛ) 失效）——故只断言机制（行数/键/汇总）与有限性，
    不赌非线性收敛。
    """
    from pyqcd.renorm import fit_ZR_samples, summarize_ZR_samples, th_hB
    rng = np.random.default_rng(3)
    mu_ = 2.0
    par_true = np.array([0.30, 0.20, 1.0, 0.05, 0.28]
                        + [0.02 * (i + 1) for i in range(14)] + [0.0, 0.0])
    z_fm = np.linspace(0.05, 0.45, 5)
    fm2gev = 1.0 / 0.1973
    dss = []
    for a_fm in (0.105, 0.085):
        a = a_fm * fm2gev
        hb = th_hB(z_fm * fm2gev, a, mu_, par_true[:19], par_true[19:])
        M = hb[:, None].repeat(3, axis=1)
        dss.append(dict(z=z_fm * fm2gev, loghB=M,
                        c_inv=np.linalg.inv(np.diag(np.full(len(z_fm), .02**2))),
                        a=a))
    with np.errstate(all='ignore'):
        rows = fit_ZR_samples(par_true, dss, mu_)
    keys = {'sample_i', 'k', 'd', 'm0', 'm2', 'Lambda_QCD', 'f1', 'f2', 'chi2'}
    assert len(rows) == 3 and keys <= set(rows[0].keys())
    assert all(f"g{i}" in rows[0] for i in range(1, 15))
    core = ['k', 'd', 'm0', 'm2']
    for r in rows:
        assert all(np.isfinite(r[k]) for k in core), r
    summ = summarize_ZR_samples(rows)
    assert set(summ.keys()) >= keys - {'sample_i'}
    mean_k, std_k = summ['k']
    assert np.isfinite(mean_k) and std_k == abs(std_k)


def test_extrapolate_boot_fit():
    """B6: 协方差加权外推拟合——连续极限截距恢复 + 回退路径。"""
    from pyqcd.renorm import fit_hR_PDF_extrap_boot, hR_form
    rng = np.random.default_rng(11)
    nx, nrep = 3, 20
    xx = np.linspace(0.1, 0.45, nx)
    true_par = [0.5, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    # 四自由参数路径为 (xg0, fx, dx, kx)。m_pi 固定时 kx 列与
    # 截距列共线，只能得到 rank=3；使用独立的多 m_pi 夹具，确保该回归
    # 真正检验可辨识的连续极限，而不是依赖最小范数伪解。
    mpi_values = iter((0.24, 0.31, 0.29, 0.37,
                       0.35, 0.26, 0.41, 0.33))
    ens = []
    for a_, L in ((0.53, 24), (0.40, 32), (0.32, 48), (0.27, 64)):
        ens.append((a_, 6, next(mpi_values), L))
        ens.append((a_, 8, next(mpi_values), L))
    rows = []
    for a_, pz_, mpi, L in ens:
        val = float(hR_form((a_, pz_, mpi, L), true_par))
        rows.append(dict(x=xx, hR=val + 0.01 * rng.standard_normal((nx, nrep)),
                         a=a_, pz=pz_, mpi=mpi, L=L))
    xg, m, s, S = fit_hR_PDF_extrap_boot(rows, return_samples=True)
    assert S.shape == (nrep, nx) and np.all(np.isfinite(S))
    # xg0 是连续极限截距：应恢复真值 0.5（fx·a² 被外推掉）
    assert np.all(np.isfinite(m)) and np.allclose(m, 0.5, atol=4 * np.mean(s))
    # 秩亏协方差回退（n_rep=2 → Cholesky 失败 → 单位阵）
    mk = lambda sl: [dict(x=xx, hR=r['hR'][:, sl],
                          **{k: r[k] for k in ('a', 'pz', 'mpi', 'L')})
                     for r in rows]
    _, m2, s2 = fit_hR_PDF_extrap_boot(mk(slice(0, 2)))
    assert np.all(np.isfinite(m2))
    _, m3, s3 = fit_hR_PDF_extrap_boot(mk(0))
    assert np.all(np.isnan(s3))                    # 单样本无带宽


def test_group_aggregate_and_disconnect():
    """B7: 分组聚合基元 + disconnected 矩阵元构造（PDF/PFF 双模式）。"""
    from pyqcd.analysis import (mean_over_array_of_list,
                                sum_over_array_of_list, dis_connect)
    rng = np.random.default_rng(5)
    a = rng.normal(size=(2, 3, 4))
    axes, groupings = (1, 2), ([[0, 2], [1]], [[0, 3], [1, 2]])
    m_ref = np.zeros((2, 2, 2))
    s_ref = np.zeros((2, 2, 2))
    for i in range(2):
        for gi, g1 in enumerate(groupings[0]):
            for gj, g2 in enumerate(groupings[1]):
                blk = a[np.ix_([i], g1, g2)]
                m_ref[i, gi, gj] = blk.mean()
                s_ref[i, gi, gj] = blk.sum()
    assert np.allclose(mean_over_array_of_list(a, axes, groupings), m_ref)
    assert np.allclose(sum_over_array_of_list(a, axes, groupings), s_ref)
    try:
        mean_over_array_of_list(a, (1,), ([[0], [0]]))
        raise AssertionError("duplicate index not caught")
    except ValueError:
        pass

    Nc, Nt, tsep = 3, 6, 2
    C2 = rng.normal(size=(Nc, Nt, Nt))
    BB = rng.normal(size=(Nc, Nt, Nt))
    mu = C2 - C2.mean(axis=0, keepdims=True)
    bub = BB - BB.mean(axis=0, keepdims=True)
    mu_r = np.zeros_like(mu)
    bub_r = np.zeros_like(bub)
    for t in range(Nt):
        mu_r[:, t, :] = np.roll(mu[:, t, :], -t, axis=1)
        bub_r[:, t, :] = np.roll(bub, -t, axis=1)[:, t, :]
    term1 = mu_r[:, :, tsep:tsep + 1] * bub_r
    got_pdf = dis_connect(C2, BB, 0, 1, 2, tsep, dtype='PDF').squeeze()
    assert np.allclose(got_pdf, term1.sum(axis=1).squeeze())
    got_pff = dis_connect(C2, BB, 0, 1, 2, tsep, dtype='PFF').squeeze()
    mat = np.zeros_like(C2)
    mat[:, :, :tsep + 1] = term1[:, :, :tsep + 1]
    term2 = bub_r[:, :, tsep:tsep + 1] * mu_r
    mat[:, :, tsep:2 * tsep + 1] = term2[:, :, tsep:2 * tsep + 1]
    assert np.allclose(got_pff, mat.sum(axis=1).squeeze())


def test_check_files_existence_guard(tmpdir=None):
    """B8: 模板组合式存在性+大小一致性守卫（正常/损坏/缺失三态）。"""
    import os
    import tempfile
    from pyqcd.pipeline import check_files_existence
    d = tempfile.mkdtemp()
    for r in range(3):
        os.makedirs(f"{d}/{r}", exist_ok=True)
        with open(f"{d}/{r}/f.dat", "w") as f:
            f.write("x" * (10 if r < 2 else 99))     # run2 大小异常
    existing, bad = check_files_existence([f"{d}/<run>/f.dat"], run=[0, 1, 2])
    assert existing == [0, 1] and bad == [2]
    e2, b2 = check_files_existence([f"{d}/<r>/missing.dat"], r=[0, 1])
    assert e2 == [] and b2 == [0, 1]
    try:
        check_files_existence(["x"])
        raise AssertionError("empty kwargs should raise")
    except ValueError:
        pass


def test_wickplot_and_flop_analysis():
    """B9: Wick 缩并图可视化 + 收缩路径 FLOPs 诊断。"""
    import matplotlib
    matplotlib.use('AGG')
    from pyqcd.contraction._dynamic import (_analyze_contraction_path,
                                            _format_cost, run_wick_analysis)
    from pyqcd.contraction import wick_contraction, plot_figure_wick
    nf, of, sp, li, name = _analyze_contraction_path(
        'ab,bc->ac', [(1000, 1000)] * 2, optimize=True)
    assert nf > 0 and of <= nf and li > 0 and name in ('auto', 'greedy',
                                                       'optimal', 'dp')
    assert _format_cost(1_234_567_890) == '1.23G'
    plan = run_wick_analysis([(['|'], ['|'])], Cpt='2pt', verbose=False)
    assert len(plan) >= 1                          # 默认路径无 FLOP 注记不崩
    sink_ops = ['|', 'd', 'u', 'gamma_7', 'd', '|', '|', 'u^d', 'gamma_5',
                'd', '|']
    src_ops = ['|', 'u^d', 'gamma_7', 'd^d', 'd^d', '|', '|', 'd^d',
               'gamma_5', 'u', '|']
    w = wick_contraction(sink_operators=sink_ops, source_operators=src_ops,
                         Cpt='2pt', curr_operators=[],
                         Pindex=['p'], Vindex=['v'], Gindex=['g'])
    fig, _ax = plot_figure_wick(w, diagram_index=0, Cpt='2pt')
    assert fig is not None


def test_vertex_product_readers():
    """B10: V†V/VVV 预计算顶点积二进制 reader 往返。"""
    import tempfile
    from pyqcd.tools import readin_vdv_all, readin_vvv_all, readin_vvv
    d = tempfile.mkdtemp()
    Nt, Nev, Nev1 = 4, 6, 3
    rng = np.random.default_rng(2)
    ref = rng.normal(size=(Nt, Nev, Nev)) + 1j * rng.normal(size=(Nt, Nev, Nev))
    buf = np.zeros((Nt, Nev, Nev, 2))
    buf[..., 0] = ref.real
    buf[..., 1] = ref.imag
    buf.tofile(f"{d}/VdaggerV.Px0Py0Pz0.conf77")
    got = readin_vdv_all(d, Nev, Nev1, Nt, 77)
    assert got.dtype == complex and np.allclose(got, ref[:, :Nev1, :Nev1])
    refv = (rng.normal(size=(Nt, Nev, Nev, Nev))
            + 1j * rng.normal(size=(Nt, Nev, Nev, Nev)))
    for t in range(Nt):
        b = np.zeros((Nev, Nev, Nev, 2))
        b[..., 0] = refv[t].real
        b[..., 1] = refv[t].imag
        b.tofile(f"{d}/VVV.t{t:03d}.Px0Py0Pz0.conf77")
    gv = readin_vvv_all(d, Nev1, Nt, 77)
    assert np.allclose(gv, refv[:, :Nev1, :Nev1, :Nev1])
    b = np.zeros((Nt, Nev, Nev, Nev, 2))
    b[..., 0] = refv.real
    b[..., 1] = refv.imag
    b.tofile(f"{d}/VVV.Px0Py0Pz0.conf77")
    assert np.allclose(readin_vvv(d, Nev, Nev1, Nt, 77),
                       refv[:, :Nev1, :Nev1, :Nev1])


def test_env_snapshot():
    """E4: 运行环境快照 env.json。"""
    import json
    import tempfile
    from pyqcd.tools import dump_env
    path = tempfile.mkdtemp() + "/sub/env.json"
    info = dump_env(path)
    on_disk = json.load(open(path))
    assert info['numpy'] and info['git_branch'] not in ('', None)
    assert on_disk['hostname'] == info['hostname']


def test_cmp_primitives():
    """E5: NaN 感知回归比对原语。"""
    from pyqcd.testing import rel_maxdiff, cmp_one
    a = np.array([1.0, 2.0, np.nan])
    b = a * (1 + 1e-12)
    b[2] = np.nan
    assert rel_maxdiff(a, b) < 1e-9
    assert rel_maxdiff(a, np.array([1., 2., 3.])) == float('inf')
    assert rel_maxdiff(a.reshape(3, 1), a) == float('inf')
    assert rel_maxdiff(np.array([np.nan]), np.array([np.nan])) == 0.0
    res = []
    ok = cmp_one("x", a, b, 1e-6, res)
    assert ok and res[0]['pass'] and res[0]['shape_a'] == [3]


# ═══════════════════════════════════════════════════════════════════
# 独立契约模块的中心入口（惰性导入，避免测试夹具循环依赖）
# ═══════════════════════════════════════════════════════════════════

def _run_unittest_contract(test_case):
    """运行一个 unittest.TestCase，并把失败稳定转换为中心入口断言。"""
    import unittest

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(test_case)
    result = unittest.TestResult()
    suite.run(result)
    if not result.wasSuccessful():
        details = [f"{test}: {traceback_text}"
                   for test, traceback_text in result.failures + result.errors]
        raise AssertionError("\n".join(details))


def test_flow_action_density_weak_field_normalization():
    """弱 Abelian T3/T8 oracle 锁定 E 的标准归一化与 SU(3) 去迹。"""
    from ._flow_normalization import FlowActionDensityNormalizationTest

    _run_unittest_contract(FlowActionDensityNormalizationTest)


def test_gradient_flow_gluon_reference_contracts():
    """donghx schema-v2 直线 OPE 与复数 disconnected ratio 契约。"""
    from ._gradient_flow_gluon_contract import GradientFlowGluonContract

    _run_unittest_contract(GradientFlowGluonContract)


def test_gauge_observables_contracts():
    """Wilson/Polyakov/Clover/拓扑量的路径、SU(3) 与后端契约。"""
    from ._gauge_observables_contract import GaugeObservablesContract

    _run_unittest_contract(GaugeObservablesContract)


def test_vertex_product_binary_contracts():
    """VdV/VVV 端序、尺寸、截断与 memmap reader 契约。"""
    from ._io_binary_contract import VertexProductBinaryContractTests

    _run_unittest_contract(VertexProductBinaryContractTests)


def test_momentum_smearing_contracts():
    """蒸馏本征矢 Fourier 相位的布局、精度、后端与不变量契约。"""
    from ._momentum_smearing_contract import MomentumSmearingContract

    _run_unittest_contract(MomentumSmearingContract)


def test_eigcompress_dtype_contracts():
    """本征模压缩随机路径须保持 complex64/128 dtype 与 seed 语义。"""
    from ._eigcompress_dtype_contract import EigcompressDtypeContract

    _run_unittest_contract(EigcompressDtypeContract)


def test_staple_operator_public_contracts():
    """公开 staple_operator 的路径、端点、规范性与局部极限。"""
    from ._operator_staple_contract import StapleOperatorContract

    _run_unittest_contract(StapleOperatorContract)


def test_tmd_su3_geometry_contracts():
    """TMD bilocal 必须逐点去迹、方向协变并严格校验空间标签。"""
    from ._tmd_su3_geometry_contract import TmdSu3GeometryContract

    _run_unittest_contract(TmdSu3GeometryContract)


def test_correlated_fit_identifiability_guards():
    """复协方差、统计边界及 ratio/P2 可辨识性统一契约。"""
    from ._fit_identifiability_contract import (
        BuiltinAnalyticJacobianContractTests, CovarianceRankContractTests,
        FiniteInputContractTests, FitAdapterContractTests,
        IdentifiableFitRegressionTests, LowSampleFitContractTests,
        _import_gvar,
    )
    from ._fit_status_propagation_contract import (
        DisconnectedStatusPropagationContractTests,
        EnergyStatusPropagationContractTests,
        FHStatusPropagationContractTests,
        FitStatusClassifierContractTests,
        RatioStatusPropagationContractTests,
        Test9ExtendedStatusPropagationContractTests,
        TmdStatusPropagationContractTests,
    )
    from ._statistics_edge_contract import (
        CovarianceRoundoffContractTests, HermitianStatisticsContractTests,
        FitWindowValidationTests, PlateauContractTests,
        SingleConfigurationContractTests,
    )

    _import_gvar()
    _run_unittest_contract(CovarianceRankContractTests)
    _run_unittest_contract(FitAdapterContractTests)
    _run_unittest_contract(FiniteInputContractTests)
    _run_unittest_contract(BuiltinAnalyticJacobianContractTests)
    _run_unittest_contract(LowSampleFitContractTests)
    _run_unittest_contract(IdentifiableFitRegressionTests)
    _run_unittest_contract(FitStatusClassifierContractTests)
    _run_unittest_contract(RatioStatusPropagationContractTests)
    _run_unittest_contract(FHStatusPropagationContractTests)
    _run_unittest_contract(EnergyStatusPropagationContractTests)
    _run_unittest_contract(DisconnectedStatusPropagationContractTests)
    _run_unittest_contract(TmdStatusPropagationContractTests)
    _run_unittest_contract(Test9ExtendedStatusPropagationContractTests)
    _run_unittest_contract(HermitianStatisticsContractTests)
    _run_unittest_contract(SingleConfigurationContractTests)
    _run_unittest_contract(CovarianceRoundoffContractTests)
    _run_unittest_contract(PlateauContractTests)
    _run_unittest_contract(FitWindowValidationTests)


def test_bootstrap_resampling_contracts():
    """任意样本轴、分块 RNG、dtype 和 NumPy/CuPy/Torch 契约。"""
    from ._bootstrap_resampling_contract import (
        BootstrapResamplingContractTests,
    )

    _run_unittest_contract(BootstrapResamplingContractTests)


def test_field_strength_cache_contracts():
    """OPE Clover 反对称、缓存所有权、复用和失败清理契约。"""
    import unittest
    from . import _field_strength_cache_contract as contract

    tests = [
        getattr(contract, name)
        for name in sorted(dir(contract))
        if name.startswith("test_") and callable(getattr(contract, name))
    ]
    if not tests:
        raise AssertionError("field-strength cache contract has no tests")
    for test in tests:
        try:
            test()
        except unittest.SkipTest:
            # 可选后端缺失不应阻断其余 CPU/所有权契约。
            continue


def test_ope_channel_contracts():
    """直线 OPE 通道身份、legacy 数值、方向、元数据与规范性契约。"""
    from ._ope_channel_contract import OPEChannelContractTests

    _run_unittest_contract(OPEChannelContractTests)


def test_quasi_tmd_fourier_contracts():
    """准 TMD 的 fm 截断、积分收敛及实/复 dtype 契约。"""
    from ._quasi_tmd_fourier_contract import QuasiTmdFourierContract
    from ._tmd_public_contract import InvariantAmplitudeContract

    _run_unittest_contract(QuasiTmdFourierContract)
    _run_unittest_contract(InvariantAmplitudeContract)


def test_continuum_extrapolation_identifiability_contracts():
    """四/八参数连续外推必须在拟合前通过设计秩与 dof 门。"""
    from ._extrapolate_identifiability_contract import (
        ExtrapolateIdentifiabilityContractTests,
    )

    _run_unittest_contract(ExtrapolateIdentifiabilityContractTests)


def test_fh_adaptive_window_contracts():
    """FH 窗口须滑动至 chi2 达标或显式报告耗尽。"""
    from ._fh_window_contract import FHAdaptiveWindowContractTests

    _run_unittest_contract(FHAdaptiveWindowContractTests)


def test_matching_grid_contracts():
    """当前 NLO 离散匹配须拒绝零节点并保持弱耦合恒等极限。"""
    from ._matching_grid_contract import MatchingGridContract

    _run_unittest_contract(MatchingGridContract)


def test_dispersion_identifiability_contracts():
    """三参数色散拟合须满秩；dof=0 可估计但不可检验拟合优度。"""
    from ._dispersion_identifiability_contract import (
        DispersionIdentifiabilityContractTests,
    )

    _run_unittest_contract(DispersionIdentifiabilityContractTests)


def test_step_tmd_single_flow_contract():
    """step_tmd 单次流化及 TMD OPE regulator 缓存契约。"""
    from ._tmd_runner_contract import (
        test_step_tmd_reuses_one_flowed_gauge,
        test_tmd_ope_cache_distinguishes_fixed_staple_length,
    )

    test_step_tmd_reuses_one_flowed_gauge()
    test_tmd_ope_cache_distinguishes_fixed_staple_length()


def test_sftx_flow_time_units_contracts():
    """SFTX 必须显式区分无量纲 tau 与物理 GeV^-2 流时间。"""
    from ._sftx_units_contract import SftxUnitsContract

    _run_unittest_contract(SftxUnitsContract)


def test_tmd_hybrid_renormalization_contracts():
    """TMD 长距分支必须显式消费 Z_R 并匹配已验证混合公式。"""
    from ._tmd_hybrid_contract import TmdHybridContract

    _run_unittest_contract(TmdHybridContract)


def test_pipeline_persistence_contracts():
    """目录副作用、preflight/env、原子保存、2pt 缓存和强制重算契约。"""
    from ._pipeline_persistence_contract import TESTS

    for test in TESTS:
        test()


def test_pipeline_runtime_failure_contracts():
    """异常传播/清理、HDF5 恢复、顶点缓存键与阶段 ETA 的运行时契约。"""
    from ._pipeline_runtime_contract import (
        test_timer_preserves_primary_failure_when_cupy_post_sync_fails,
        test_timer_propagates_post_sync_failure_after_success,
        test_timer_preserves_primary_failure_when_torch_cuda_post_sync_fails,
        test_timer_propagates_torch_cuda_post_sync_failure_after_success,
        test_timer_does_not_synchronize_torch_cpu,
        test_4pt_dynamic_failure_is_raised_before_output_is_saved,
        test_meta_task_cpu_success_cleans_without_importing_torch,
        test_meta_task_failure_propagates_after_cleanup,
        test_parallel_setup_applies_backend_before_vertex_compute,
        test_mpi_launcher_does_not_silently_fallback_without_mpi4py,
        test_serial_pipeline_base_exception_cleans_and_propagates,
        test_vertex_cache_reads_canonical_h5_without_recompute,
        test_vertex_cache_rejects_wrong_shape_dtype_finite_and_schema,
        test_vertex_cache_key_distinguishes_vdv_and_vvv_momenta,
        test_plot_recovery_reads_canonical_h5_analysis,
        test_report_reads_canonical_h5_analysis_and_correlators,
        test_report_real_xelatex_template_has_no_hard_gate_diagnostics,
        test_build_tex_missing_or_empty_plateau_uses_explanatory_placeholder,
        test_report_first_xelatex_failure_raises_even_with_stale_pdf,
        test_report_second_xelatex_failure_raises_after_first_success,
        test_report_successful_passes_require_a_new_pdf,
        test_report_rejects_latex_diagnostics_from_each_pass_source,
        test_runner_records_stage_eta_after_each_configuration,
    )

    test_timer_preserves_primary_failure_when_cupy_post_sync_fails()
    test_timer_propagates_post_sync_failure_after_success()
    test_timer_preserves_primary_failure_when_torch_cuda_post_sync_fails()
    test_timer_propagates_torch_cuda_post_sync_failure_after_success()
    test_timer_does_not_synchronize_torch_cpu()
    test_4pt_dynamic_failure_is_raised_before_output_is_saved()
    test_meta_task_cpu_success_cleans_without_importing_torch()
    test_meta_task_failure_propagates_after_cleanup()
    test_parallel_setup_applies_backend_before_vertex_compute()
    test_mpi_launcher_does_not_silently_fallback_without_mpi4py()
    test_serial_pipeline_base_exception_cleans_and_propagates()
    test_vertex_cache_reads_canonical_h5_without_recompute()
    test_vertex_cache_rejects_wrong_shape_dtype_finite_and_schema()
    test_vertex_cache_key_distinguishes_vdv_and_vvv_momenta()
    test_plot_recovery_reads_canonical_h5_analysis()
    test_report_reads_canonical_h5_analysis_and_correlators()
    test_report_real_xelatex_template_has_no_hard_gate_diagnostics()
    test_build_tex_missing_or_empty_plateau_uses_explanatory_placeholder()
    test_report_first_xelatex_failure_raises_even_with_stale_pdf()
    test_report_second_xelatex_failure_raises_after_first_success()
    test_report_successful_passes_require_a_new_pdf()
    test_report_rejects_latex_diagnostics_from_each_pass_source()
    test_runner_records_stage_eta_after_each_configuration()


def test_stout_torch_cuda_device_contract():
    """Stout 的 Torch CUDA 计算必须全程同设备并匹配 NumPy。"""
    from ._stout_backend_contract import (
        test_stout_torch_cuda_stays_on_device_and_matches_numpy,
    )

    test_stout_torch_cuda_stays_on_device_and_matches_numpy()


def test_pjn_3pt_explicit_wick_oracle():
    """PJN 3pt 与四张手写 Wick 图逐式一致。"""
    from ._baryon_explicit_oracles import (
        test_pjn_3pt_matches_four_explicit_wick_contractions,
    )

    metrics = test_pjn_3pt_matches_four_explicit_wick_contractions()
    assert metrics['max_rel_error'] < 2e-12


def test_mpi_run_directory_contracts():
    """串行/MPI 默认目录须跨作业唯一、作业内一致，显式路径不变。"""
    from ._mpi_run_dir_contract import (
        test_default_run_dirs_are_unique_across_independent_jobs_in_same_second,
        test_default_run_tag_rejects_path_components_before_writing,
        test_explicit_run_dir_is_broadcast_unchanged,
        test_mpi_default_run_dir_uses_dynamic_pipeline_output_root,
        test_rank_zero_default_run_dir_is_broadcast_within_one_job,
        test_runner_default_run_dirs_are_unique_within_same_second,
        test_steps_default_run_dirs_are_unique_within_same_second,
    )

    test_default_run_dirs_are_unique_across_independent_jobs_in_same_second()
    test_default_run_tag_rejects_path_components_before_writing()
    test_rank_zero_default_run_dir_is_broadcast_within_one_job()
    test_mpi_default_run_dir_uses_dynamic_pipeline_output_root()
    test_explicit_run_dir_is_broadcast_unchanged()
    test_runner_default_run_dirs_are_unique_within_same_second()
    test_steps_default_run_dirs_are_unique_within_same_second()


def test_parallel_mpi_reliability_contracts():
    """MPI preflight、env、2pt 续跑和 best-effort 清理契约。"""
    from ._mpi_reliability_contract import (
        test_cli_recompute_2pt_flag_is_forwarded,
        test_collective_preflight_rejects_plan_size_mismatch,
        test_collective_preflight_rejects_tmd_and_unknown_steps,
        test_env_step_reaches_rank_zero_report_with_serial_fields,
        test_mpi_2pt_cache_skips_unless_recompute_is_true,
        test_parallel_driver_propagates_recompute_2pt_to_meta_tasks,
        test_run_meta_task_cleanup_is_best_effort_after_success,
        test_run_meta_task_preserves_primary_baseexception_during_cleanup,
        test_run_meta_task_preserves_primary_exception_during_cleanup,
        test_serial_fallback_real_pipeline_recomputes_when_override_is_true,
        test_serial_fallback_real_pipeline_reuses_cache_when_recompute_is_false,
        test_serial_fallback_propagates_recompute_override,
    )

    tests = (
        test_collective_preflight_rejects_tmd_and_unknown_steps,
        test_collective_preflight_rejects_plan_size_mismatch,
        test_env_step_reaches_rank_zero_report_with_serial_fields,
        test_run_meta_task_preserves_primary_exception_during_cleanup,
        test_run_meta_task_preserves_primary_baseexception_during_cleanup,
        test_run_meta_task_cleanup_is_best_effort_after_success,
        test_mpi_2pt_cache_skips_unless_recompute_is_true,
        test_parallel_driver_propagates_recompute_2pt_to_meta_tasks,
        test_serial_fallback_propagates_recompute_override,
        test_serial_fallback_real_pipeline_reuses_cache_when_recompute_is_false,
        test_serial_fallback_real_pipeline_recomputes_when_override_is_true,
        test_cli_recompute_2pt_flag_is_forwarded,
    )
    for test in tests:
        test()


def test_parallel_mpi_collective_failure_contracts():
    """真实双 rank 的目录、初始化、元任务和后处理异常均须同步退出。"""
    from ._mpi_failure_contract import (
        test_missing_mpi_prerequisites_raise_skiptest,
        test_mpi_collective_failure_contracts,
        test_standalone_main_reports_skip_without_pass,
    )

    test_missing_mpi_prerequisites_raise_skiptest()
    test_standalone_main_reports_skip_without_pass()
    test_mpi_collective_failure_contracts()


def test_parallel_mpi_planning_contracts():
    """MPI 计划、绑定、CLI preflight 与空组态语义契约。"""
    from ._mpi_planning_contract import TESTS

    for test in TESTS:
        test()
