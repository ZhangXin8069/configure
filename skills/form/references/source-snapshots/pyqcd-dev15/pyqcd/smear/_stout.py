"""
Stout 涂抹（Morningstar–Peardon 2004）——梯度流/HYP 之外的第三种 UV 正则化
============================================================================

照抄 refer/sush/lqcddb/src/lqcddb/base/smear_gauge.py 的生产实现逻辑，
适配 pyqcd 张量布局与后端适配层（numpy/cupy/torch 通用，不 import refer/）：

    staple 求和（空间平面）：
        C_μ(x) = Σ_{ν≠μ,空间} U_ν(x)·U_μ(x+ν̂)·U_ν†(x+μ̂)
                              + U_ν†(x−ν̂)·U_μ(x−ν̂)·U_ν(x−ν̂+μ̂)
    Ω = ρ·C·U†；Q = ½i(Ω† − Ω) − tr[½i(Ω† − Ω)]/Nc·I   （厄米无迹）
    exp(iQ)：SU(3) Cayley–Hamilton 参数化（c0=tr(Q³)/3, c1=tr(Q²)/2，
        u/w 由 arccos(c0/c0_max) 给出，f0/f1/f2 系数 + 小角 sinc 级数）
    U_new = exp(iQ)·U

时间方向链接不涂抹（仅空间 μ∈{0:x,1:y,2:z}）。真实蒸馏数据规范处理为
nstep=20、ρ=0.12（stout_smear_20_0.12 系综约定）。
"""
from __future__ import annotations

import numpy as np

from ..tools._backend import get_backend
from ..lattice._constants import Nc


def _staple_pair(U, mu, nu):
    """(μ,ν) 空间平面的前后向 staple 贡献：S(U; μ, ν)。

    S = U_ν(x)·U_μ(x+ν̂)·U_ν†(x+μ̂) + U_ν†(x−ν̂)·U_μ(x−ν̂)·U_ν(x−ν̂+μ̂)

    pyqcd 方向约定：μ∈{0:x,1:y,2:z,3:t}，格点轴 = 3−μ
    （x↔axis3(Nx), y↔axis2(Ny), z↔axis1(Nz), t↔axis0(Nt)，与 _hyp 一致）。
    """
    cp = get_backend()
    e = cp.einsum
    a_mu, a_nu = 3 - mu, 3 - nu
    Um = U[..., mu, :, :]
    Un = U[..., nu, :, :]
    # 正向：U_ν(x)·U_μ(x+ν̂)·U_ν†(x+μ̂)
    t1 = e("...ab,...bc->...ac", Un, cp.roll(Um, -1, axis=a_nu))
    t1 = e("...ab,...cb->...ac", t1, cp.roll(Un, -1, axis=a_mu).conj())
    # 反向：U_ν†(x−ν̂)·U_μ(x−ν̂)·U_ν(x−ν̂+μ̂)
    t2 = e("...ba,...bc->...ac", cp.roll(Un, 1, axis=a_nu).conj(),
           cp.roll(Um, 1, axis=a_nu))
    t2 = e("...ab,...bc->...ac", t2,
           cp.roll(cp.roll(Un, 1, axis=a_nu), -1, axis=a_mu))
    return t1 + t2


def stout_smear(gauge, nstep=20, rho=0.12, verbose=False, logger=None,
                traceless=True):
    """Stout 规范链接涂抹（空间三方向，时间方向保持）。

    Args:
        gauge: 规范场 (Nt,Nz,Ny,Nx,4,3,3)。
        nstep: 迭代次数（默认 20，对齐真实数据 stout_smear_20_0.12）。
        rho:   涂抹权重 ρ（默认 0.12）。
        verbose: 打印进度。
        logger: 日志函数（默认 print）。
    Returns:
        涂抹后的规范场 (Nt,Nz,Ny,Nx,4,3,3)（SU(3) 保持；输入不被修改）。
    """
    cp = get_backend()
    e = cp.einsum
    log = logger or print
    U = cp.asarray(gauge)
    if (isinstance(nstep, (bool, np.bool_))
            or not isinstance(nstep, (int, np.integer))
            or nstep < 0):
        raise ValueError(f"nstep 必须为非负整数，收到 {nstep!r}")
    if nstep == 0:
        return U + cp.zeros_like(U)
    eye = cp.eye(Nc, dtype=U.dtype)

    for step in range(nstep):
        U_new = cp.zeros_like(U)
        U_new[..., 3, :, :] = U[..., 3, :, :]     # 时间方向不涂抹
        for mu in range(3):                        # 空间 x/y/z
            acc = None
            for nu in range(3):
                if nu == mu:
                    continue
                s = _staple_pair(U, mu, nu)
                acc = s if acc is None else acc + s
            # Ω = ρ·C·U† → Q 厄米无迹
            Om = rho * e("...ab,...cb->...ac", acc, U[..., mu, :, :].conj())
            Q = 0.5j * (Om.conj().swapaxes(-1, -2) - Om)
            if traceless:
                tr = e("...aa->...", Q)
                Q = Q - eye * (tr / Nc)[..., None, None]
            # traceless=False：复刻 sush 参照行为（其迹扣除行作用于被丢弃的
            # 临时数组，Q 实际保留迹）——仅用于对照单测逐位复现

            # SU(3) Cayley–Hamilton：exp(iQ) = f0 I + f1 Q + f2 Q²
            # （Q≈0 的 `small` 格点处 f_denom=inf×0 产生 nan，随后被
            #   cp.where(small, …) 替换——errstate 抑制该良性警告）
            Q_sq = Q @ Q
            with np.errstate(invalid='ignore', divide='ignore'):
                c0 = cp.real(e("...aa->...", Q @ Q_sq)) / Nc
                c1 = cp.real(e("...aa->...", Q_sq)) / 2.0
                small = c1 < 1e-30                   # Q≈0 → exp(iQ)=I 保护
                c0_max = 2.0 * (c1 / 3.0) ** 1.5
                parity = cp.asarray(c0 < 0)
                c0_abs = cp.abs(c0)
                ratio = c0_abs / cp.maximum(c0_max, 1e-300)
                if traceless:
                    ratio = cp.clip(ratio, 0.0, 1.0)
                theta = cp.arccos(ratio)
                u = cp.sqrt(c1 / 3.0) * cp.cos(theta / 3.0)
                w = cp.sqrt(c1) * cp.sin(theta / 3.0)
                u_sq, w_sq = u ** 2, w ** 2
                e_iu_re, e_iu_im = cp.cos(u), cp.sin(u)
                e_2iu_re, e_2iu_im = cp.cos(2 * u), cp.sin(2 * u)
                cos_w = cp.cos(w)
                sinc_w = 1 - w_sq / 6 * (
                    1 - w_sq / 20 * (1 - w_sq / 42 * (1 - w_sq / 72)))
                large = cp.abs(w) > 0.05               # 大角精确 sinc 分支
                if bool(large.any()):
                    wl = w[large]
                    sinc_w[large] = cp.sin(wl) / wl
                f_denom = 1.0 / (9.0 * u_sq - w_sq)
                f0_re = ((u_sq - w_sq) * e_2iu_re
                         + e_iu_re * 8 * u_sq * cos_w
                         + e_iu_im * 2 * u * (3 * u_sq + w_sq) * sinc_w) * f_denom
                f0_im = ((u_sq - w_sq) * e_2iu_im
                         - e_iu_im * 8 * u_sq * cos_w
                         + e_iu_re * 2 * u * (3 * u_sq + w_sq) * sinc_w) * f_denom
                f1_re = (2 * u * e_2iu_re - e_iu_re * 2 * u * cos_w
                         + e_iu_im * (3 * u_sq - w_sq) * sinc_w) * f_denom
                f1_im = (2 * u * e_2iu_im + e_iu_im * 2 * u * cos_w
                         + e_iu_re * (3 * u_sq - w_sq) * sinc_w) * f_denom
                f2_re = (e_2iu_re - e_iu_re * cos_w
                         - e_iu_im * 3 * u * sinc_w) * f_denom
                f2_im = (e_2iu_im + e_iu_im * cos_w
                         - e_iu_re * 3 * u * sinc_w) * f_denom
            # c0<0 时 u/w 相位修正（sush 生产实现的等价符号翻转）
            if bool(parity.any()):
                f0_im = cp.asarray(f0_im)
                f1_re = cp.asarray(f1_re)
                f2_im = cp.asarray(f2_im)
                f0_im[parity] *= -1
                f1_re[parity] *= -1
                f2_im[parity] *= -1
            zero = cp.zeros_like(f0_re)
            one = cp.ones_like(f0_re)
            is_s = bool(small.any())
            f0_r = cp.where(small, one, f0_re) if is_s else f0_re
            f1_r = cp.where(small, zero, f1_re) if is_s else f1_re
            f2_r = cp.where(small, zero, f2_re) if is_s else f2_re
            f0_i = cp.where(small, zero, f0_im) if is_s else f0_im
            f1_i = cp.where(small, zero, f1_im) if is_s else f1_im
            f2_i = cp.where(small, zero, f2_im) if is_s else f2_im

            F = (f2_r + 1j * f2_i)[..., None, None] * Q_sq \
                + (f1_r + 1j * f1_i)[..., None, None] * Q \
                + (f0_r + 1j * f0_i)[..., None, None] * eye
            U_new[..., mu, :, :] = e("...ab,...bc->...ac",
                                     F, U[..., mu, :, :])
        U = U_new
        if verbose and (step + 1 == nstep or (step + 1) % max(nstep // 5, 1) == 0):
            from ..renorm._gradient_flow import flow_action_density
            log(f"  [stout] step {step + 1}/{nstep} "
                f"E={float(np.mean(flow_action_density(_np_view(U)))):.6g}")
    return U


def _np_view(U):
    """后端数组 → numpy（日志用）。"""
    if hasattr(U, 'get'):
        return U.get()
    return np.asarray(U)
