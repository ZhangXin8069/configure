"""
胶子 TMD-PDF 提取（梯度流重整化方案）——本库核心目标
====================================================

参照 /root/PyQCD/refer/papers/gluon_tmd_gradient_flow_continuum.tex 构造：

1. 伴随表示下的胶子准 TMD 算符（Eq.:M_adj_tmd）：
       M^{μλ;νρ}(z, b⊥) = F^{μλ}(z, b⊥)·U_{adj}(staple)·F^{νρ}(0)

2. 基础表示格点实现（Eq.:staple_wilson, Eq.:M_fund_tmd）：
       W_⊏(z, b⊥) = U_z†((z+L)n̂_z + b⊥, b⊥)·U_⊥((z+L)n̂_z+b⊥, (z+L)n̂_z)
                     ·U_z((z+L)n̂_z, z n̂_z)
       M(x) = Tr[ F(x)·W_⊏(x,y)·F(y)·W_⊏†(x,y) ],
       y = x + z n̂_z + b⊥

3. 可乘性重整化组合（Eq.:O_mult_tmd）：令 i,j 为 z_dir 之外的两个空间方向，
       O(z, b⊥) = M^{ti;ti} + M^{tj;tj} − 2·M^{ij;ij}
   该组合的一圈 UV 反常量纲使整体（至少一圈水平）乘法可重整化；
   共线极限 b⊥→0 约化为胶子准 PDF 算符。

4. 不变振幅（Eq.:Mpp_extract_tmd, Eq.:Mpp_PDF_tmd）：
       M^{ti;it}(z,b⊥) + M^{ji;ij}(z,b⊥) = 2 p₀² M_pp(ν, b⊥)
       −M_pp(ν, b⊥) = ½ ∫₋₁¹ dx e^{−ixν} x·g(x, b⊥)

5. 梯度流重整化：先用 Wilson flow（_gradient_flow.wilson_flow）把规范场
   演化到无量纲流时间 ``tau=t/a²``（如物理 ``t=3a²`` 对应 ``tau=3``），再计算上述算符——
   Monahan–Orginos 2017 / NieMiera et al. 2025 的自重整化方案。

6. b⊥ 依赖的软函数 / Collins–Soper 核：TMD 重整化需软函数 S(b⊥)，
   本模块提供从准 TMD 矩阵元比值提取 CS 核的框架（LPC 2020 方案）。
"""
from __future__ import annotations

import numpy as np

from ..tools._backend import get_backend
from ..analysis._ratio_fit import fit_constant_window


def _to_cpu(x):
    """后端无关的 GPU→CPU 转换（运行时取后端，兼容 numpy/cupy/torch）。"""
    asnumpy = getattr(get_backend(), 'asnumpy', None)
    if asnumpy is not None:
        return asnumpy(x)
    return np.asarray(x)
from ..operator._gluon_ope import plaquette_clover, compute_dual_field_strength
from ._gradient_flow import wilson_flow


# ═══════════════════════════════════════════════════════════════════
# 基础表示 staple Wilson 线
# ═══════════════════════════════════════════════════════════════════

def _validate_spatial_directions(z_dir, b_dir):
    """校验并规范化 TMD 的纵向/横向空间方向。"""
    directions = []
    for name, value in (("z_dir", z_dir), ("b_dir", b_dir)):
        if (isinstance(value, (bool, np.bool_))
                or not isinstance(value, (int, np.integer))):
            raise ValueError(
                f"{name} 必须是非布尔空间整数 0=x, 1=y, 2=z")
        value = int(value)
        if value not in (0, 1, 2):
            raise ValueError(
                f"{name} 必须是空间方向 0=x, 1=y, 2=z")
        directions.append(value)
    if directions[0] == directions[1]:
        raise ValueError("staple 的纵向与横向方向必须不同")
    return tuple(directions)


def staple_wilson_line(U, z, b_perp, z_dir=2, b_dir=0, L=None):
    """构造 staple Wilson 线 W_⊏(z, b⊥)（Eq.:staple_wilson）。

    W_⊏ = U_z†((z+L)n̂_z + b⊥, b⊥) · U_⊥((z+L)n̂_z + b⊥, (z+L)n̂_z)
          · U_z((z+L)n̂_z, z n̂_z)

    Args:
        U: 规范场 (Nt,Nz,Ny,Nx,4,3,3)。
        z: 纵向分离（格点单位）。
        b_perp: 横向位移（格点单位）。
        z_dir: 纵向方向（2=z 轴，默认）。
        b_dir: 横向方向（0=x 轴，1=y 轴；默认 0）。
        L: staple 臂长（默认 = z）。
    Returns:
        W_⊏，形状 (Nt,Nz,Ny,Nx,3,3)，逐格点（x 为起点）。
    """
    cp = get_backend()
    z_dir, b_dir = _validate_spatial_directions(z_dir, b_dir)
    if L is None:
        L = abs(z)
    if L < 0:
        raise ValueError("staple 臂长 L 必须非负")

    # Zhang et al. (2022) Eq. (12):
    #   eta1 = -s L zhat,
    #   eta2 = s b bhat - L zhat,
    #   eta3 = b bhat + [-L + s(L+z)] zhat.
    # 因而 W 从 x 连到 x + b*bhat + z*zhat，按顺序走三段
    # -L zhat -> b bhat -> (L+z) zhat。
    nc = U.shape[-1]
    W = cp.broadcast_to(cp.eye(nc, dtype=U.dtype), U.shape[:4] + (nc, nc))
    displacement = [0, 0, 0]
    for direction, signed_length in (
            (z_dir, -L), (b_dir, b_perp), (z_dir, L + z)):
        W = _path_product(U, W, direction, signed_length, displacement)

    return W


def _shift_spatial(field, displacement):
    """返回 ``field(x + displacement)``；方向序为 x,y,z。"""
    cp = get_backend()
    shifted = field
    for direction, offset in enumerate(displacement):
        if offset:
            shifted = cp.roll(shifted, -offset, axis=3 - direction)
    return shifted


def _path_product(U, W, direction, signed_length, displacement):
    """从当前位移沿一个有向空间段累乘链接，并原位更新位移。"""
    cp = get_backend()
    step = 1 if signed_length >= 0 else -1
    for _ in range(abs(signed_length)):
        if step > 0:
            link = _shift_spatial(U[..., direction, :, :], displacement)
            displacement[direction] += 1
        else:
            displacement[direction] -= 1
            link = _shift_spatial(U[..., direction, :, :], displacement)
            link = cp.swapaxes(link.conj(), -1, -2)
        W = cp.einsum("...ab,...bc->...ac", W, link)
    return W


# ═══════════════════════════════════════════════════════════════════
# 基础表示 TMD 矩阵元
# ═══════════════════════════════════════════════════════════════════

def M_mu_lambda_nu_rho(U, mu, lam, nu, rho, z, b_perp, z_dir=2, b_dir=0,
                       L=None, compute_dtype=None,
                       color_normalization='fundamental_trace'):
    """M^{μλ;νρ}(z, b⊥)（Eq.:M_fund_tmd）：逐格点色迹（未空间求和）。

    对 ``y=x+z n̂_z+b⊥``，返回
    ``Tr[F^{νρ}(x) W_⊏(x,y) F^{μλ}(y) W_⊏†(x,y)]``；调用方按需再对
    空间或时空求和。这个顺序显式保留两个端点，Wilson 线不能相邻抵消。
    """
    cp = get_backend()
    z_dir, b_dir = _validate_spatial_directions(z_dir, b_dir)
    if compute_dtype is None:
        compute_dtype = U.dtype

    F_mu = plaquette_clover(U, mu, lam)
    F_nu = plaquette_clover(U, nu, rho)

    W = staple_wilson_line(U, z, b_perp, z_dir, b_dir, L)

    return _matrix_element_from_fields(
        F_mu, F_nu, W, z, b_perp, z_dir, b_dir,
        color_normalization=color_normalization)


def _color_normalization_factor(color_normalization):
    """基础迹约定与标准伴随分量约定之间的显式因子。"""
    factors = {'fundamental_trace': 1.0, 'adjoint': 2.0}
    try:
        return factors[color_normalization]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            "color_normalization 必须是 'fundamental_trace' 或 'adjoint'") \
            from exc


def _matrix_element_from_fields(F_mu, F_nu, W, z, b_perp, z_dir, b_dir,
                                color_normalization='fundamental_trace'):
    """逐点投影 Clover 到 su(Nc)，再闭合双场强颜色迹。"""
    cp = get_backend()
    z_dir, b_dir = _validate_spatial_directions(z_dir, b_dir)
    F_mu = _traceless_color_field(F_mu)
    F_nu = _traceless_color_field(F_nu)

    endpoint = [0, 0, 0]
    endpoint[z_dir] += z
    endpoint[b_dir] += b_perp
    F_mu_shift = _shift_spatial(F_mu, endpoint)
    W_dagger = cp.swapaxes(W.conj(), -1, -2)

    # W 从 x 连到 x+z+b，故闭合颜色指标为
    # Tr[F_nu(x) W(x,x+z+b) F_mu(x+z+b) W†(x,x+z+b)]。
    t1 = cp.einsum("...ab,...bc->...ac", F_nu, W)
    t2 = cp.einsum("...ab,...bc->...ac", F_mu_shift, W_dagger)
    fundamental_trace = cp.einsum("...ab,...ba->...", t1, t2)
    return (_color_normalization_factor(color_normalization)
            * fundamental_trace)


def _traceless_color_field(field):
    """逐格点投影 ``field`` 到 su(Nc) 的 traceless 色矩阵部分。"""
    cp = get_backend()
    nc = field.shape[-1]
    trace = cp.einsum("...aa->...", field)
    identity = cp.eye(nc, dtype=field.dtype)
    return field - trace[..., None, None] * identity / nc


def _tmd_clover_fields(U, z_dir, b_dir):
    """返回纵向 ``z_dir`` 对应的两个 transverse 场与平面场。"""
    z_dir, _ = _validate_spatial_directions(z_dir, b_dir)
    i, j = (direction for direction in (0, 1, 2)
            if direction != z_dir)
    return (
        plaquette_clover(U, 3, i),
        plaquette_clover(U, 3, j),
        plaquette_clover(U, i, j),
    )


def _gluon_tmd_operator_from_fields(
        fields, W, z, b_perp, z_dir, b_dir,
        color_normalization='fundamental_trace'):
    """复用 transverse Clover 场与单条 staple 计算非极化 TMD 组合。"""
    F_ti, F_tj, F_ij = fields
    M_titi = _matrix_element_from_fields(
        F_ti, F_ti, W, z, b_perp, z_dir, b_dir, color_normalization)
    M_tjtj = _matrix_element_from_fields(
        F_tj, F_tj, W, z, b_perp, z_dir, b_dir, color_normalization)
    M_ijij = _matrix_element_from_fields(
        F_ij, F_ij, W, z, b_perp, z_dir, b_dir, color_normalization)
    return M_titi + M_tjtj - 2.0 * M_ijij


def gluon_tmd_operator(U, z, b_perp, z_dir=2, b_dir=0, L=None,
                       color_normalization='fundamental_trace'):
    """可乘性组合 O = M^{ti;ti} + M^{tj;tj} − 2M^{ij;ij}。

    ``i,j`` 动态取 ``z_dir`` 之外的两个空间方向；``z_dir=2`` 时即历史
    ``tx/ty/xy`` 组合（Eq.:O_mult_tmd）。

    Returns:
        逐格点 O 值，形状 (Nt,Nz,Ny,Nx)。
    """
    # Lorentz 方向沿用组态链接顺序 0=x, 1=y, 2=z, 3=t。
    z_dir, b_dir = _validate_spatial_directions(z_dir, b_dir)
    fields = _tmd_clover_fields(U, z_dir, b_dir)
    W = staple_wilson_line(U, z, b_perp, z_dir, b_dir, L)
    return _gluon_tmd_operator_from_fields(
        fields, W, z, b_perp, z_dir, b_dir, color_normalization)


def tmd_matrix_elements(U, z_list, b_list, z_dir=2, b_dir=0, L=None,
                        spatial_sum=True,
                        color_normalization='fundamental_trace'):
    """批量计算 O(z, b⊥)：返回 (nz, nb) 实数数组（逐 t 时间片均分后求和）。

    胶子 TMD transverse 组合 O = M^{ti;ti} + M^{tj;tj} − 2M^{ij;ij} 为实数值
    （每项 M 的虚部在色迹 + 空间求和后归零）。同一批次必须共享固定
    staple 臂长；``L=None`` 时统一取 ``max(abs(z_list))``。
    """
    cp = get_backend()
    z_dir, b_dir = _validate_spatial_directions(z_dir, b_dir)
    out = np.zeros((len(z_list), len(b_list)), dtype=np.float64)
    if len(z_list) == 0 or len(b_list) == 0:
        return out
    batch_L = max(abs(z) for z in z_list) if L is None else L
    fields = _tmd_clover_fields(U, z_dir, b_dir)
    for i, z in enumerate(z_list):
        for j, b in enumerate(b_list):
            W = staple_wilson_line(U, z, b, z_dir, b_dir, batch_L)
            O = _gluon_tmd_operator_from_fields(
                fields, W, z, b, z_dir, b_dir, color_normalization)
            if spatial_sum:
                val = _to_cpu(cp.sum(O, axis=(1, 2, 3)))
            else:
                val = _to_cpu(O)
            out[i, j] = np.real(np.mean(val))  # 时间片平均
    return out


def tmd_matrix_elements_time(
        U, z_list, b_list, z_dir=2, b_dir=0, L=None,
        color_normalization='fundamental_trace'):
    """批量计算 O(z, b⊥) 逐时间片（空间求和保留 t 轴）：返回 (nz, nb, Nt)。

    与 ``tmd_matrix_elements`` 的区别：不做时间片平均，保留每个 t 的
    空间求和值——供 disconnected 3pt 因子化 C3 = C2(dt)·OPE(dtau, z, b)
    使用（OPE(dtau, z, b) 需要逐时间片的算符矩阵元）。

    Returns:
        out: (nz, nb, Nt) 实数数组（每项为 Σ_{x,y,z} O(z,b⊥)(t)）。
    """
    cp = get_backend()
    z_dir, b_dir = _validate_spatial_directions(z_dir, b_dir)
    Nt = U.shape[0]
    out = np.zeros((len(z_list), len(b_list), Nt), dtype=np.float64)
    if len(z_list) == 0 or len(b_list) == 0:
        return out
    batch_L = max(abs(z) for z in z_list) if L is None else L
    fields = _tmd_clover_fields(U, z_dir, b_dir)
    for i, z in enumerate(z_list):
        for j, b in enumerate(b_list):
            W = staple_wilson_line(U, z, b, z_dir, b_dir, batch_L)
            O = _gluon_tmd_operator_from_fields(
                fields, W, z, b, z_dir, b_dir, color_normalization)
            val = _to_cpu(cp.sum(O, axis=(1, 2, 3)))
            out[i, j] = np.real(val)
    return out


# ═══════════════════════════════════════════════════════════════════
# 梯度流重整化流程
# ═══════════════════════════════════════════════════════════════════

def gradient_flow_renormalized_tmd(U, tau, z_list, b_list, z_dir=2, b_dir=0,
                                   L=None, eps=0.01,
                                   color_normalization='fundamental_trace'):
    """梯度流重整化的 TMD 矩阵元（Monahan–Orginos 2017 方案）。

    Args:
        U: 初始规范场。
        tau: 无量纲流时间 ``t/a²``；NieMiera 方案的 ``t=3a²`` 传 3。
        z_list/b_list: 纵向/横向位移列表。
    Returns:
        O(z, b⊥) 矩阵（形状 (nz, nb)）。
    """
    z_dir, b_dir = _validate_spatial_directions(z_dir, b_dir)
    V = wilson_flow(U, tau, eps=eps)
    return tmd_matrix_elements(
        V, z_list, b_list, z_dir, b_dir, L,
        color_normalization=color_normalization)


def self_renormalized_ratio(O_z, O_z0, z_s=2):
    """自重整化比值：R(z, b⊥) = O(z, b⊥) / O(z_s, b⊥)（Z_R 方案）。

    Args:
        O_z: O(z, b⊥) 数组 (nz, nb)。
        O_z0: O(0 或 z_s, b⊥) 数组（同一 b⊥ 网格）。
        z_s: 参考点 z 索引（默认 2，即短距参考）。
    Returns:
        比值数组（与 O_z 同形）。
    """
    return O_z / O_z0[z_s][None, :]


# ═══════════════════════════════════════════════════════════════════
# 不变振幅与 CS 核
# ═══════════════════════════════════════════════════════════════════

def invariant_amplitude(M_pp, x_grid, b_perp):
    """从不变振幅 M_pp(ν, b⊥) 傅里叶变换到胶子 TMD-PDF x·g(x, b⊥)（Eq.:Mpp_PDF_tmd）。

    −M_pp(ν, b⊥) = ½ ∫₋₁¹ dx e^{−ixν} x·g(x, b⊥)
    → x·g(x, b⊥) = −(1/π)·∫₀^∞ dν cos(xν)·2·Re[M_pp(ν,b⊥)]  （实部，奇偶性）

    Args:
        M_pp: 不变振幅（随 Ioffe 时间 ν 变化的数组，或 (nν, nb) 矩阵）。
        x_grid: x 网格（(0,1)）。
        b_perp: b⊥ 网格（用于维度标记，不参与计算）。
    Returns:
        xg(x, b⊥) 数组（形状 (len(x_grid), nb) 或 (len(x_grid),)）。
    """
    M_pp = np.asarray(M_pp, dtype=complex)
    if M_pp.ndim == 1:
        nν = len(M_pp)
        ν_grid = np.linspace(0, 2 * np.pi * nν, nν)  # Ioffe 时间网格
    else:
        nν, nb = M_pp.shape
        ν_grid = np.linspace(0, 2 * np.pi * nν, nν)

    dν = ν_grid[1] - ν_grid[0]
    out = np.zeros((len(x_grid), 1) if M_pp.ndim == 1
                   else (len(x_grid), nb))
    for i, x in enumerate(x_grid):
        cos_mat = np.cos(np.outer(x, ν_grid))  # (nx, nν)
        if M_pp.ndim == 1:
            out[i, 0] = -(1.0 / np.pi) * dν * np.sum(cos_mat * (-M_pp).real)
        else:
            for j in range(nb):
                out[i, j] = -(1.0 / np.pi) * dν * np.sum(
                    cos_mat * (-M_pp[:, j]).real)
    return out[..., 0] if M_pp.ndim == 1 else out


def collins_soper_kernel(R_b, b_list, z_list, pz_gev):
    """从准 TMD 矩阵元比值提取 Collins–Soper 核（LPC 2020 方案框架）。

    CS 核 γ_ζ(b⊥) 通过不同 P_z 下矩阵元比值的幂律行为提取：
        R(b⊥) = O(Pz₁, b⊥)/O(Pz₂, b⊥) ~ (Pz₁/Pz₂)^{γ_ζ(b⊥)·...}

    这里提供比值—斜率最小二乘框架：
        γ_ζ(b) = d ln R(b) / d ln(Pz)   （逐 b⊥）

    Args:
        R_b: 比值数组（(n_pz, nb)，不同 Pz 下的比值）。
        b_list: b⊥ 网格（fm）。
        z_list: 纵向位移（用于标记，不参与计算）。
        pz_gev: Pz 数组（GeV）。
    Returns:
        (γ_ζ(b), 逐 b 误差) —— 用 ln(Pz) 对 ln R 线性回归。
    """
    pz_gev = np.asarray(pz_gev, dtype=float)
    R_b = np.asarray(R_b, dtype=float)
    ln_pz = np.log(pz_gev)
    ln_R = np.log(R_b)  # (n_pz, nb)

    nb = R_b.shape[1]
    gamma = np.zeros(nb)
    gamma_err = np.zeros(nb)
    for j in range(nb):
        A = np.vstack([ln_pz, np.ones_like(ln_pz)]).T
        coef, res, *_ = np.linalg.lstsq(A, ln_R[:, j], rcond=None)
        gamma[j] = coef[0]
        gamma_err[j] = np.sqrt(np.sum(res ** 2) / max(len(ln_pz) - 2, 1))
    return gamma, gamma_err


# ═══════════════════════════════════════════════════════════════════
# staple 长度扫描与 L→∞ 平台外推
# ═══════════════════════════════════════════════════════════════════

def _staple_plateau_failure(reason, n_L, n_sample, L_values=None,
                            window=None):
    """构造可解释的 staple 平台拟合失败结果。"""
    L_values = np.asarray([] if L_values is None else L_values)
    return {
        'c0': np.nan,
        'c0_std': np.nan,
        'chi2': np.nan,
        'chi2_nocov': np.nan,
        'c0_samples': np.full(int(max(n_sample, 0)), np.nan, dtype=float),
        'n_data': int(max(n_L, 0)),
        'n_sample': int(max(n_sample, 0)),
        'fit_status': 'statistically_unidentifiable',
        'fit_reason': str(reason),
        'sample_rank': 0,
        'effective_rank': 0,
        'plateau': np.nan,
        'plateau_std': np.nan,
        'plateau_samples': np.full(int(max(n_sample, 0)), np.nan,
                                   dtype=float),
        'L_window': np.asarray(L_values, dtype=float),
        'L_window_bounds': None if window is None else tuple(window),
        'n_L_window': int(np.asarray(L_values).size),
    }


def _normalize_staple_scan(L_values, values=None, *, measure_fn=None,
                           measure_args=(), measure_kwargs=None,
                           axis=0, sort=True):
    """把 staple 扫描输入规整为 ``(L_values, values)``。"""
    if measure_kwargs is None:
        measure_kwargs = {}

    L_arr = np.asarray(L_values)
    if L_arr.ndim != 1:
        raise ValueError("L_values 必须是一维数组")
    if L_arr.size == 0:
        raise ValueError("L_values 不能为空")
    if not np.issubdtype(L_arr.dtype, np.number):
        raise ValueError("L_values 必须是数值数组")
    if np.iscomplexobj(L_arr):
        raise ValueError("L_values 不能是复数数组")
    if not np.isfinite(L_arr).all():
        raise ValueError("L_values 必须全部有限")

    if measure_fn is not None and values is not None:
        raise ValueError("measure_fn 与 values 不能同时提供")

    if measure_fn is not None:
        try:
            stacked = [measure_fn(L, *measure_args, **measure_kwargs)
                       for L in L_arr]
        except Exception as exc:
            raise ValueError(
                f"measure_fn 在 staple 扫描中失败: {exc}") from exc
        try:
            values_arr = np.stack(stacked, axis=0)
        except ValueError as exc:
            raise ValueError(
                "measure_fn 在不同 L 上返回了不一致的形状") from exc
    else:
        if values is None:
            raise ValueError("values 与 measure_fn 至少需要提供一个")
        values_arr = np.asarray(values)
        if values_arr.ndim == 0:
            if L_arr.size != 1:
                raise ValueError(
                    "标量 values 只允许与单个 L_values 配对")
            values_arr = values_arr.reshape(1)
        else:
            if not isinstance(axis, (int, np.integer)):
                raise ValueError("axis 必须是整数")
            axis = int(axis)
            if axis < -values_arr.ndim or axis >= values_arr.ndim:
                raise ValueError("axis 超出 values 的维度范围")
            values_arr = np.moveaxis(values_arr, axis, 0)

    if values_arr.shape[0] != L_arr.size:
        raise ValueError(
            "values 的 staple 轴长度必须与 L_values 长度一致")

    if sort:
        order = np.argsort(L_arr, kind='stable')
        L_arr = L_arr[order]
        values_arr = values_arr[order]
        if np.any(np.diff(L_arr) == 0):
            raise ValueError("L_values 不能含有重复项")
    elif np.any(np.diff(L_arr) <= 0):
        raise ValueError("L_values 必须严格递增，或启用 sort=True")

    return L_arr, values_arr


def scan_staple_length(L_values, values=None, *, measure_fn=None,
                       measure_args=(), measure_kwargs=None,
                       axis=0, sort=True):
    """规范化或计算 staple 长度扫描数据。

    两种用法：
        1. 直接传入预计算 ``values``，其中 staple 轴由 ``axis`` 指定；
        2. 传入 ``measure_fn(L, *measure_args, **measure_kwargs)``，对每个
           L 自动计算并堆叠扫描结果。

    Args:
        L_values: 一维 staple 臂长列表。
        values: 预计算扫描值；若使用 ``measure_fn`` 则应为 ``None``。
        measure_fn: 可调用对象，逐个 L 评估并返回标量或数组。
        axis: ``values`` 中对应 L 轴的位置；会被移动到最前面。
        sort: 是否按 L 升序排序并同步重排 values。
    Returns:
        dict:
            - ``L_values``: 形状 ``(n_L,)``。
            - ``values``: 形状 ``(n_L, ...)``。
            - ``n_L``: 扫描点数。
            - ``value_shape``: 单个 L 上的值形状。
    """
    L_arr, values_arr = _normalize_staple_scan(
        L_values, values, measure_fn=measure_fn,
        measure_args=measure_args, measure_kwargs=measure_kwargs,
        axis=axis, sort=sort)
    return {
        'L_values': L_arr,
        'values': values_arr,
        'n_L': int(L_arr.size),
        'value_shape': tuple(values_arr.shape[1:]),
        'sorted': bool(sort),
    }


def fit_staple_plateau(scan_or_values, L_values=None, *, window=None,
                       kind='boot', seed=0, axis=0, sort=True):
    """对 staple 长度扫描做常数平台拟合，取 ``L→∞`` 外推值。

    Args:
        scan_or_values: ``scan_staple_length`` 返回的字典，或原始扫描数组。
        L_values: 当 ``scan_or_values`` 为数组时提供的一维 L 列表。
        window: ``(L_min, L_max)`` 的闭区间；``None`` 时使用全扫描。
        kind: ``'boot'`` 或 ``'jack'``，传给 ``fit_constant_window``。
        seed: 传给 ``fit_constant_window`` 的随机种子。
        axis: 数组输入时对应 L 轴的位置。
        sort: 数组输入时是否按 L 升序排序。

    Returns:
        与 ``fit_constant_window`` 风格一致的字典，并额外包含：
            - ``plateau`` / ``plateau_std`` / ``plateau_samples`` 别名；
            - ``L_window``：参与拟合的 L 值；
            - ``L_window_bounds``：窗口端点；
            - ``n_L_window``：窗口内点数。
    """
    if kind not in ('boot', 'jack'):
        raise ValueError("kind 必须是 'boot' 或 'jack'")

    if isinstance(scan_or_values, dict):
        if L_values is not None:
            raise ValueError("scan 字典输入时不应再额外提供 L_values")
        if 'L_values' not in scan_or_values or 'values' not in scan_or_values:
            raise ValueError("scan 字典必须包含 'L_values' 和 'values'")
        L_arr = np.asarray(scan_or_values['L_values'])
        values_arr = np.asarray(scan_or_values['values'])
    else:
        if L_values is None:
            raise ValueError("数组输入时必须提供 L_values")
        L_arr, values_arr = _normalize_staple_scan(
            L_values, scan_or_values, axis=axis, sort=sort)

    if values_arr.ndim == 1:
        values_arr = values_arr[:, None]
    if values_arr.ndim != 2:
        raise ValueError(
            "fit_staple_plateau 仅支持形状 (n_L, n_sample) 的扫描数组")
    if L_arr.ndim != 1 or L_arr.size != values_arr.shape[0]:
        raise ValueError("L_values 与 values 的 staple 轴长度不一致")
    if np.iscomplexobj(L_arr):
        raise ValueError("L_values 不能是复数数组")

    if not np.isfinite(L_arr).all():
        raise ValueError("L_values 必须全部有限")

    if window is None:
        mask = np.ones(L_arr.shape, dtype=bool)
        window_bounds = None
    else:
        if len(window) != 2:
            raise ValueError("window 必须是 (L_min, L_max) 二元组")
        lo, hi = window
        lo = -np.inf if lo is None else float(lo)
        hi = np.inf if hi is None else float(hi)
        if not np.isfinite(lo) and lo != -np.inf:
            raise ValueError("window 下界必须是有限数或 None")
        if not np.isfinite(hi) and hi != np.inf:
            raise ValueError("window 上界必须是有限数或 None")
        if lo > hi:
            raise ValueError("window 下界不能大于上界")
        mask = (L_arr >= lo) & (L_arr <= hi)
        window_bounds = (None if lo == -np.inf else lo,
                         None if hi == np.inf else hi)

    L_window = L_arr[mask]
    values_window = values_arr[mask]
    if np.iscomplexobj(values_window):
        imag_max = float(np.max(np.abs(np.imag(values_window))))
        if imag_max > 1e-12:
            return _staple_plateau_failure(
                f"staple scan window 包含复数值（最大虚部 {imag_max:.3g}）",
                L_window.size, values_window.shape[1], L_window, window_bounds)
        values_window = np.real(values_window)
    values_window = np.asarray(values_window, dtype=float)
    if L_window.size < 2:
        return _staple_plateau_failure(
            "staple plateau fit 至少需要 2 个 L 点",
            L_window.size, values_window.shape[1], L_window, window_bounds)
    if values_window.shape[1] < 2:
        return _staple_plateau_failure(
            "staple plateau fit 至少需要 2 个样本",
            L_window.size, values_window.shape[1], L_window, window_bounds)
    if not np.isfinite(values_window).all():
        return _staple_plateau_failure(
            "staple scan window 包含非有限值",
            L_window.size, values_window.shape[1], L_window, window_bounds)

    fit = fit_constant_window(values_window, kind=kind, seed=seed)
    fit['plateau'] = fit['c0']
    fit['plateau_std'] = fit['c0_std']
    fit['plateau_samples'] = fit['c0_samples']
    fit['L_window'] = L_window
    fit['L_window_bounds'] = window_bounds
    fit['n_L_window'] = int(L_window.size)
    return fit
