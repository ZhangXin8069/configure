"""
准 TMD-PDF 提取链：傅里叶变换、混合方案匹配、软函数/CS 核、SFTX
=================================================================

依据 refer/papers/gluon_tmd_gradient_flow_continuum.tex 实现：

1. 准 TMD-PDF（Eq.:quasi_tmd）：
       x·g̃(x, b⊥, Pz) = (1/𝒩)·∫dz/(2πPz) e^{−ixzPz}·hR(z, b⊥, Pz)
       𝒩 = (Pz)²/(Pt)²

2. 混合方案匹配（Eq.:matching_tmd）：
       x·g̃(x, b⊥, Pz) = ∫(dy/|y|)·C^hybrid(x/y, λs, μ/(yPz))
                          ·[y·g(y,b⊥)/√S_I(b⊥,μ)]·exp[½ln(ζz/ζ)·K(b⊥,μ)]

3. CS 核（LPC 2020 方案）：K(b⊥) 从不同 Pz 的准 TMD 矩阵元比值提取
       K(b⊥) ≈ ln[hR(Pz₁)/hR(Pz₂)] / ln(Pz₁/Pz₂)

4. SFTX 匹配系数（Suzuki 2013 / Mereghetti 2022，1 圈）：
       O_MS(μ) = [1 + α_s/(4π)·c(t,μ)]·O_flow(t)
"""
from __future__ import annotations

import numpy as np

from ._const import CA, CF, gammaE, pi, b0
from ._ensembles import fm_to_GeV
from ._matching import _matching_kernels, A_s_run


def quasi_tmd_pdf(hR_z, z_grid, b_perp, pz_gev, p_t=None, x_grid=None,
                  n_pts=2048, z_max=None):
    """准 TMD-PDF（Eq.:quasi_tmd）。

    Args:
        hR_z: 正半轴重整化矩阵元 hR(z, b⊥, Pz)，形状 (nz, nb)
            或 (nz,)；负半轴按 hR(-z)=hR(z)* 作 Hermitian 延拓。
        z_grid: 非负 z 网格（fm）。
        b_perp: b⊥ 网格（fm）。
        pz_gev: Pz（GeV）。
        p_t: 核子能量分量 Pt（GeV）；None 时取 √(M²+Pz²)，M=0.94。
        x_grid: x 网格（默认 −1.5..1.5，256 点）。
        n_pts: 在输入 z 支撑上作均匀细化后的积分点数（至少 2）。
        z_max: 积分截断 z（fm；默认 z_grid 的最大值）。
    Returns:
        (x_grid, xg(x, b⊥))。
    """
    hR_z = np.asarray(hR_z)
    input_is_real = not np.iscomplexobj(hR_z)
    z_fm = np.asarray(z_grid, dtype=float)
    if hR_z.ndim == 1:
        hR_z = hR_z[:, None]
    if z_fm.ndim != 1 or len(z_fm) < 2:
        raise ValueError("z_grid 必须是一维且至少含两个点")
    if hR_z.ndim != 2 or hR_z.shape[0] != len(z_fm):
        raise ValueError("hR_z 的 z 维必须与 z_grid 一致")
    if not (np.all(np.isfinite(z_fm)) and np.all(np.isfinite(hR_z))):
        raise ValueError("hR_z 与 z_grid 必须有限")
    if not (isinstance(n_pts, (int, np.integer)) and not isinstance(n_pts, bool)
            and n_pts >= 2):
        raise ValueError("n_pts 必须是至少为 2 的整数")

    order = np.argsort(z_fm)
    z_fm = z_fm[order]
    hR_z = hR_z[order]
    if np.any(np.diff(z_fm) <= 0.0):
        raise ValueError("z_grid 不能含重复点")
    if z_fm[0] < 0.0:
        raise ValueError(
            "quasi_tmd_pdf 接收非负 z 半轴；负半轴由 Hermitian 延拓生成")
    if z_fm[0] != 0.0:
        raise ValueError("quasi_tmd_pdf 的 z_grid 必须从 z=0 开始")

    if x_grid is None:
        x_grid = np.linspace(-1.5, 1.5, 256)
    x_grid = np.asarray(x_grid, dtype=float)
    if z_max is None:
        z_max_fm = z_fm[-1]
    else:
        z_max_fm = float(z_max)
        if not np.isfinite(z_max_fm):
            raise ValueError("z_max 必须是有限的 fm 长度")
    if z_max_fm < z_fm[0]:
        raise ValueError("z_max 不能小于 z_grid 的最小 fm 值")
    z_upper_fm = min(z_max_fm, z_fm[-1])

    if p_t is None:
        M_N = 0.94
        p_t = np.sqrt(M_N ** 2 + pz_gev ** 2)
    norm = (pz_gev ** 2) / (p_t ** 2)

    # 接口截断始终在 fm 完成；仅在积分网格确定后统一换算 GeV^-1。
    z_int_fm = np.linspace(z_fm[0], z_upper_fm, n_pts)
    hr_dtype = np.result_type(hR_z.dtype, np.float64)
    hr = np.empty((n_pts, hR_z.shape[1]), dtype=hr_dtype)
    for b_index in range(hR_z.shape[1]):
        if input_is_real:
            hr[:, b_index] = np.interp(
                z_int_fm, z_fm, hR_z[:, b_index])
        else:
            hr[:, b_index] = (
                np.interp(z_int_fm, z_fm, hR_z[:, b_index].real)
                + 1j * np.interp(
                    z_int_fm, z_fm, hR_z[:, b_index].imag))
    zz = z_int_fm / fm_to_GeV

    # 正半轴数据按 h(-z)=h(z)* 延拓：
    # ∫_{-L}^{L} dz exp(-ikz)h(z)
    #   = 2∫_0^L dz [cos(kz) Re h(z) + sin(kz) Im h(z)]。
    phase = np.multiply.outer(x_grid, zz * pz_gev)
    sine = np.sin(phase) if not input_is_real else None
    np.cos(phase, out=phase)
    dz = np.diff(zz)
    weights = np.empty_like(zz)
    weights[0] = 0.5 * dz[0]
    weights[-1] = 0.5 * dz[-1]
    weights[1:-1] = 0.5 * (dz[:-1] + dz[1:])
    hr *= weights[:, None]
    integral = phase @ hr.real
    if sine is not None:
        integral += sine @ hr.imag
    integral *= 2.0
    out = integral / (2.0 * pi * pz_gev) / norm
    if hR_z.shape[1] == 1:
        out = out[:, 0]
    return x_grid, out


def quasi_pdf_gluon(h_z, z_grid, pz_gev, x_grid=None):
    """collinear 胶子准 PDF（sin 变换通道，照抄 zhangxin
    gluon_pdf_full_workflow.fourier_transform_to_quasi_pdf）。

        g̃(x, Pz) = (2Pz/x)·∫₀^{z_max} dz h(z, Pz)·sin(x·Pz·z)

    反对称部分（非极化胶子 collinear 准 PDF）用 sin 变换；x≈0 保护置 0
    （原版 abs(x)<1e-15 分支）。与 ``quasi_tmd_pdf`` 的 cos 变换（TMD
    约定、b⊥ 依赖）互补：b⊥ 积分极限下的交叉校验通道。

    Args:
        h_z: 坐标空间矩阵元 h(z, Pz)，形状 (nz,)（实部参与积分）。
        z_grid: z 网格（fm，内部转 GeV⁻¹）。
        pz_gev: Pz（GeV）。
        x_grid: Bjorken x 网格（默认 −1.5..1.5，256 点）。
    Returns:
        (x_grid, g̃(x)) 形状 (nx,)。
    """
    h = np.asarray(h_z, dtype=float).real
    z = np.asarray(z_grid, dtype=float) / fm_to_GeV   # fm → GeV⁻¹
    if z.ndim != 1 or z.size < 2:
        raise ValueError("z_grid 必须是一维且至少含两个点")
    if z[0] != 0.0:
        raise ValueError("quasi_pdf_gluon 的 z_grid 必须从 z=0 开始")
    if x_grid is None:
        x_grid = np.linspace(-1.5, 1.5, 256)
    x_grid = np.asarray(x_grid, dtype=float)

    small = np.abs(x_grid) < 1e-15
    xv = np.where(small, 1.0, x_grid)                 # 防除零，末尾回填 0
    integrand = h[None, :] * np.sin(np.outer(xv, pz_gev * z))
    trapezoid = getattr(np, "trapezoid", None)
    if trapezoid is None:                              # NumPy < 1.20
        trapezoid = np.trapz
    integral = trapezoid(integrand, z, axis=1)         # 与原版梯形法等价
    out = (2.0 * pz_gev / xv) * integral
    out[small] = 0.0
    return x_grid, out


def cs_kernel_from_ratio(hR_pz1, hR_pz2, pz1, pz2):
    """CS 核提取（LPC 2020 比值法）。

    K(b⊥) = ln[hR(z=z₀, b⊥, Pz₁)/hR(z=z₀, b⊥, Pz₂)] / ln(Pz₁/Pz₂)

    Args:
        hR_pz1/hR_pz2: 两动量下的重整化矩阵元（(nz, nb) 或 (nz,)）。
        pz1/pz2: 动量（GeV）。
    Returns:
        K(b⊥) 数组（沿 z=0 提取；若 z 维首点噪声大可用 z=z₀ 索引）。
    """
    h1 = np.asarray(hR_pz1, dtype=float)
    h2 = np.asarray(hR_pz2, dtype=float)
    if h1.ndim == 1:
        h1, h2 = h1[:, None], h2[:, None]
    ratio = h1[0] / h2[0]           # z=0 处（b⊥ 依赖保留）
    return np.log(np.maximum(ratio, 1e-30)) / np.log(pz1 / pz2)


def cs_kernel_two_momentum(c01, c02, pz1_gev, pz2_gev, z_ref=1,
                           k_clip=(-3.0, 3.0)):
    """两动量 c0 比值 CS 核提取——工程封装（整合 test9 示例内联实现）。

    与 cs_kernel_from_ratio 的差异：
        1) 直接吃裸 c0(z,b)（未经 z₀ 归一化，避免归一点噪声放大）；
        2) z_ref 可选参考 z 索引（默认 1：z=0 处 c0≡1 无信息，
           z=1 为最低含 Wilson 线信息的分离）；
        3) k_clip 数值保护：噪声使 |K| 越界时截断
           （CS 核物理量级 |K| ≲ O(1) GeV²·fm² 量级，|K|>3 视为噪声）。

    Args:
        c01/c02: 两动量裸矩阵元 (nz, nb) 或 (nb,)（同 z 网格）。
        pz1_gev/pz2_gev: 两动量（GeV）。
        z_ref: 参考 z 行索引（负数按 Python 惯例回绕）。
        k_clip: (K_min, K_max) 截断区间；None 则不截断。
    Returns:
        K(b⊥) 数组（沿所选 z 行）。
    """
    a = np.asarray(c01, dtype=float)
    b_ = np.asarray(c02, dtype=float)
    if a.ndim == 1:
        a, b_ = a[None, :], b_[None, :]
    if a.shape != b_.shape:
        raise ValueError(f"c01/c02 形状不一致: {a.shape} vs {b_.shape}")
    z_ref = int(z_ref if z_ref >= 0 else len(a) + z_ref)
    if not (0 <= z_ref < len(a)):
        raise ValueError(f"z_ref={z_ref} 超出 z 维 [0, {len(a)-1}]")
    ratio = a[z_ref] / b_[z_ref]
    k = np.log(np.maximum(ratio, 1e-30)) / np.log(pz1_gev / pz2_gev)
    return np.clip(k, *k_clip) if k_clip is not None else k


def soft_function_intrinsic(R_square, b_perp, mu=2.0):
    """内禀软函数 S_I(b⊥, μ)（从平方比值矩阵元提取的框架）。

    S_I(b⊥) = R²(b⊥)/R²(b⊥→0) 型归一（文献中常取短距归一化），
    此处实现通用归一化框架：输入逐 b⊥ 的比值矩阵元，输出归一化软函数。
    """
    R = np.asarray(R_square, dtype=float)
    return R / R[0]


def tmd_matching_hybrid(x_grid, y_grid=None, b_perp=None, mu=2.0, pz_gev=2.0,
                        cs_kernel=0.0, soft_factor=1.0, pz_scale=2.0,
                        x_tmd=None, lambda_s_fm=0.3):
    """混合方案 TMD 匹配（Eq.:matching_tmd 的离散实现，1 圈核）。

    x·g̃(x, b⊥) = ∫(dy/|y|)·C^hybrid(x/y, λs, μ/(yPz))
                  ·[y·g(y, b⊥)/√S_I(b⊥,μ)]·exp[½ln(ζz/ζ)·K(b⊥)]

    1 圈匹配核 C^hybrid(ξ) = δ(1−ξ) + (α_s C_A/2π)·g_xy(ξ)，其中
    g_xy 复用 _matching._matching_kernels 的胶子核 g_0..g_3（ξ<0/0<ξ<1/ξ>1
    分区 + g_0 的 Si 项，含 μ/(yPz) 标度与 λ_s 截断）。

    数值结构：Z_ij = δ_ij + (α_s C_A/2π)·dx·(x/|x|)·[g_ij/y_j
    − δ_ij·y_i·Σ_k(g_ik/y_k²)]，x·g̃ = Z⁻¹·[y·g/√S_I·e^{½ln(ζz/ζ)K}]
    ——与 _matching.hR_PDF 同构（矩阵形式自然处理 ξ=1 主值奇点，
    δ 项由 Z⁻¹ 的 LO 部分还原，匹配求和规则经 test_matching_sum_rule 验证）。

    Args:
        x_grid: 输出 x 网格（(0,1)）。
        y_grid: 积分 y 网格；None 时取 x_grid（匹配矩阵结构要求同维）。
        b_perp: b⊥（fm，标记用）。
        mu: 匹配标度（GeV）。
        pz_gev: Pz（GeV）。
        cs_kernel: K(b⊥)（标量或数组）。
        soft_factor: √S_I(b⊥)（标量或数组）。
        pz_scale: 参考快度标度 ζ 对应的动量（GeV）。
        x_tmd: 输入光锥 TMD y·g(y, b⊥)（数组，与 y_grid 同形）。
        lambda_s_fm: 大 λ 截断（fm，默认 0.3，同 _matching.hR_PDF）。
    Returns:
        (x_grid, x·g̃(x, b⊥))——1 圈匹配。
    """
    x = np.asarray(x_grid, dtype=float)
    y = x if y_grid is None else np.asarray(y_grid, dtype=float)
    if len(y) != len(x):
        raise ValueError("TMD 匹配矩阵结构要求 y 网格与 x 网格同维")
    yg = np.asarray(x_tmd)
    if yg.ndim == 1:
        yg = yg[:, None]
    nb = yg.shape[1]
    n = len(x)

    dx = x[1] - x[0]
    lambda_s = lambda_s_fm / fm_to_GeV * pz_gev
    # 与 _matching.hR_PDF 同构：A_s ≡ α_s/(4π)，×4π 还原真耦合
    # （zengch 端 matching*.py 均为 alpha_s = A_s(mu)*4π）
    alpha_s = A_s_run(mu) * 4.0 * pi

    # 匹配核矩阵：g_ij = g_xy(x_i / y_j)（1 圈硬核，含主值奇点）
    cxi = x[:, None] / y[None, :]
    g_ij = _matching_kernels(cxi, np.broadcast_to(y[None, :], cxi.shape),
                             pz_gev, mu, lambda_s)

    # Z_ij 结构（与 _matching.hR_PDF 同构）：
    #   c_alp_lo = diag(x/|x|)·dx·α_s C_A/(2π)
    #   m_ij     = g_ij/y_j − δ_ij·y_i·Σ_k(g_ik/y_k²)
    c_alp_lo = np.diag(x / np.abs(x)) * dx * alpha_s * CA / (2.0 * pi)
    m_ij = (g_ij / y[None, :]
            - np.eye(n) * (y[:, None]
                           * np.sum(g_ij / y[None, :] ** 2.0, axis=1)))
    z_ij = np.eye(n) + c_alp_lo @ m_ij
    z_inv = np.linalg.inv(z_ij)

    # 快度演化因子与软函数（逐 b⊥）
    K = np.asarray(cs_kernel, dtype=float).ravel()
    S = np.asarray(soft_factor, dtype=float).ravel()
    rap = np.exp(0.5 * np.log((2.0 * pz_gev) ** 2 / (2.0 * pz_scale) ** 2) * K)

    out = np.empty((n, nb), dtype=np.result_type(yg.dtype, z_inv.dtype,
                                                  rap.dtype, S.dtype))
    for j in range(nb):
        v = yg[:, j] * rap[j % rap.size] / np.sqrt(S[j % S.size])
        out[:, j] = z_inv @ v
    if nb == 1:
        out = out[:, 0]
    return x, out


def _alpha_s(mu, Lambda_QCD=0.23, nf=3.0):
    return 2.0 * np.pi / (b0(nf) * np.log(mu / Lambda_QCD))


# ═══════════════════════════════════════════════════════════════════
# SFTX：小流时展开匹配系数（梯度流 → MS-bar，1 圈）
# ═══════════════════════════════════════════════════════════════════

_HBARC_GEV_FM = 0.1973269804


def flow_time_gev_m2(tau, a_fm):
    """把 ``tau=t/a^2`` 与 ``a[fm]`` 换成物理流时间 ``t[GeV^-2]``。"""
    tau = float(tau)
    a_fm = float(a_fm)
    if not (np.isfinite(tau) and tau > 0.0):
        raise ValueError('tau 必须是有限正数')
    if not (np.isfinite(a_fm) and a_fm > 0.0):
        raise ValueError('a_fm 必须是有限正数')
    return tau * (a_fm / _HBARC_GEV_FM) ** 2


def _resolve_sftx_flow_time(t_gev_m2, tau, a_fm):
    explicit = t_gev_m2 is not None
    lattice = tau is not None or a_fm is not None
    if explicit == lattice:
        raise ValueError(
            '须且只能提供 t_gev_m2，或同时提供 tau 与 a_fm')
    if explicit:
        t_gev_m2 = float(t_gev_m2)
        if not (np.isfinite(t_gev_m2) and t_gev_m2 > 0.0):
            raise ValueError('t_gev_m2 必须是有限正数')
        return t_gev_m2
    if tau is None or a_fm is None:
        raise ValueError('tau 与 a_fm 必须同时提供')
    return flow_time_gev_m2(tau, a_fm)


def sftx_gluon_matching_coeff(*, mu, t_gev_m2=None, tau=None, a_fm=None,
                               Lambda_QCD=0.23, nf=3.0):
    """胶子算符的 SFTX 1 圈匹配系数（Suzuki 2013 / Mereghetti 2022）。

    O_MS(μ) = [1 + α_s(μ)/(4π)·c(t,μ)]·O_flow(t)

    c(t,μ) = 2·b₀·ln(2μ²t) + c₁
    其中 b₀ = 11 − 2Nf/3，c₁ = 2·b₀·γ_E 为常数项
    （胶子能量动量张量/双线性算符的 1 圈 SFTX 常数项，Suzuki 2013）。

    Args:
        mu: MS-bar 标度（GeV）。
        t_gev_m2: 物理流时间（GeV⁻²）。
        tau/a_fm: 或提供无量纲 ``tau=t/a²`` 与格距（fm），内部严格换算。
    Returns:
        (alpha_s/(4π), c(t,μ))——匹配系数。
    """
    t = _resolve_sftx_flow_time(t_gev_m2, tau, a_fm)
    al4pi = _alpha_s(mu, Lambda_QCD, nf) / (4.0 * np.pi)
    b0_ = b0(nf)
    # 1 圈 SFTX：O_MS(μ) = O_flow(t)·[1 + α_s/(4π)·(2b₀·ln(2μ²t) + 2b₀·γ_E)]
    c = 2.0 * b0_ * (np.log(2.0 * mu ** 2 * t) + gammaE)
    return al4pi, c


def sftx_energy_density_t0(E_t, *, mu, t_gev_m2=None, tau=None, a_fm=None,
                           Lambda_QCD=0.23, nf=3.0):
    """⟨E(t)⟩ 的 SFTX → MS-bar ⟨¼F²⟩(μ)（Suzuki 2013）。

    ⟨E(t)⟩ = 3(N²−1)/(16π²t²)·[1 + α_s/(4π)·(2b₀·ln(2μ²t) + c₂)]·(1 + O(t·⟨F²⟩/Nc))

    此处实现 ⟨¼F²⟩_MS = E(t)/[1 + α_s/(4π)·c(t)] 的 1 圈反解。
    """
    al4pi, c = sftx_gluon_matching_coeff(
        mu=mu, t_gev_m2=t_gev_m2, tau=tau, a_fm=a_fm,
        Lambda_QCD=Lambda_QCD, nf=nf)
    return np.asarray(E_t) / (1.0 + al4pi * c)
