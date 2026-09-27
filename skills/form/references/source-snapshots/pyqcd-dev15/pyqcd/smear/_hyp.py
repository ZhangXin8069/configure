"""
HYP 涂抹（Hasenfratz--Knechtli 2001）
=======================================

标准四维 HYP 使用三级排除方向结构：

    bar V_{mu;nu rho} = Proj[(1-alpha3) U_mu
                              + alpha3/2 sum_{+-eta != mu,nu,rho} staple]
    tilde V_{mu;nu}   = Proj[(1-alpha2) U_mu
                              + alpha2/4 sum_{+-rho != mu,nu} staple(bar V)]
    V_mu              = Proj[(1-alpha1) U_mu
                              + alpha1/6 sum_{+-nu != mu} staple(tilde V)]

每一层都以原始 ``U_mu`` 为基链接；标准参数为
``(alpha1, alpha2, alpha3) = (0.75, 0.6, 0.3)``。
"""
from __future__ import annotations

import numpy as np

from ..tools._backend import get_backend


def proj_su3(A):
    """投影到 SU(3)：极分解 A = U·Σ·V† → P = U·V†，再 det 归一。

    用 SVD 实现（numpy 批量 eigh 的特征向量相位在不同数组形状下
    不一致，SVD 的 U·V† 构造更稳健）。
    """
    cp = get_backend()
    U, _S, Vh = cp.linalg.svd(A)
    P = cp.matmul(U, Vh)
    det = cp.linalg.det(P)
    return P * (det ** (-1.0 / 3.0))[..., None, None]


def _staple_pair(side, middle, mu, nu):
    """由 ``side``(nu 向) 与 ``middle``(mu 向) 构造正负 nu staple。"""
    cp = get_backend()
    e = cp.einsum
    a_mu, a_nu = 3 - mu, 3 - nu

    # 正向：side(x) middle(x+nu) side^dagger(x+mu)
    t1 = e("...ab,...bc->...ac", side, cp.roll(middle, -1, axis=a_nu))
    t1 = e("...ab,...cb->...ac", t1,
           cp.roll(side, -1, axis=a_mu).conj())
    # 反向：side^dagger(x-nu) middle(x-nu) side(x-nu+mu)
    side_back = cp.roll(side, 1, axis=a_nu)
    t2 = e("...ba,...bc->...ac", side_back.conj(),
           cp.roll(middle, 1, axis=a_nu))
    t2 = e("...ab,...bc->...ac", t2,
           cp.roll(side_back, -1, axis=a_mu))
    return t1 + t2


def _v3_key(direction, excluded_a, excluded_b):
    """V3 对两个排除方向对称，使用规范化字典键避免稠密空槽。"""
    return (direction,) + tuple(sorted((excluded_a, excluded_b)))


def hyp_smear(U, alpha1=0.75, alpha2=0.6, alpha3=0.3):
    """标准四维 HYP 涂抹（完整三级排除方向结构）。

    Args:
        U: 规范场 (Nt,Nz,Ny,Nx,4,3,3)。
    Returns:
        涂抹后的规范场 V1 (Nt,Nz,Ny,Nx,4,3,3)（SU(3) 保持）。
    """
    cp = get_backend()
    U = cp.asarray(U)
    Nd = 4

    if alpha1 == 0.0:
        # 零操作仍返回独立结果，保持“输入不被修改/输出可安全持有”的
        # 所有权契约；避免下游原地写输出时反向污染原始规范场。
        return U + cp.zeros_like(U)

    # 第 3 层：bar V_{mu;nu rho}。每组排除方向只剩一个 eta，含正反两项。
    V3 = {}
    if alpha2 != 0.0 and alpha3 != 0.0:
        for mu in range(Nd):
            others = [direction for direction in range(Nd) if direction != mu]
            for i, nu in enumerate(others):
                for rho in others[i + 1:]:
                    eta = next(direction for direction in range(Nd)
                               if direction not in (mu, nu, rho))
                    staples = _staple_pair(
                        U[..., eta, :, :], U[..., mu, :, :], mu, eta)
                    V3[_v3_key(mu, nu, rho)] = proj_su3(
                        (1.0 - alpha3) * U[..., mu, :, :]
                        + (alpha3 / 2.0) * staples)

    def v3(direction, excluded_a, excluded_b):
        if alpha3 == 0.0:
            return U[..., direction, :, :]
        return V3[_v3_key(direction, excluded_a, excluded_b)]

    # 第 2 层：tilde V_{mu;nu}，rho 遍历另两个方向（共四个正反 staple）。
    V2 = {}
    for mu in range(Nd):
        for nu in range(Nd):
            if nu == mu:
                continue
            if alpha2 == 0.0:
                V2[(mu, nu)] = U[..., mu, :, :]
                continue
            acc = None
            for rho in range(Nd):
                if rho == mu or rho == nu:
                    continue
                staples = _staple_pair(
                    v3(rho, nu, mu), v3(mu, rho, nu), mu, rho)
                acc = staples if acc is None else acc + staples
            V2[(mu, nu)] = proj_su3(
                (1.0 - alpha2) * U[..., mu, :, :]
                + (alpha2 / 4.0) * acc)
    del V3

    # 第 1 层：V_mu，nu 遍历其余三个方向（共六个正反 staple）。
    V1 = cp.zeros_like(U)
    for mu in range(Nd):
        acc = None
        for nu in range(Nd):
            if nu == mu:
                continue
            staples = _staple_pair(
                V2[(nu, mu)], V2[(mu, nu)], mu, nu)
            acc = staples if acc is None else acc + staples
        V1[..., mu, :, :] = proj_su3(
            (1.0 - alpha1) * U[..., mu, :, :]
            + (alpha1 / 6.0) * acc)
    return V1
