"""
螺旋度（ΔG）道双场强 Wilson 线算符
====================================

整合 refer/donghx Operator.py 的 operators_new_z0_mu2_xy /
operators_new_z0_mz_mu2_xy 与 plaquette_clover_all_tilde 逻辑
（不 import refer/；后端适配层通用）：

    O(x) = Tr[ F_{μν}(x ± δz ẑ) · W∓(z→0) · F̃_{μ₂ν₂}(x) · W±(0→z) ]

即沿 z_dir 以 δz 分离的两个场强插入 F_{μν} 与对偶场强 F̃_{μ₂ν₂}，
由前后向 Wilson 线连接保持规范不变性——ΔG 螺旋度 OPE 的基元。
±z 两支（minus=True 取 −δz 方向）供下游对称组合。

方向约定与 pyqcd 全库一致：μ∈{0:x,1:y,2:z,3:t}，格点轴 = 3−μ
（donghx 原版同构，einsum 下标字母直迁）。空间求和默认仅压掉
垂直 z 的一根轴、保留横向平面（keep_plane=True，原版 _xy 语义）；
keep_plane=False 全求和回 (Nt,)（原版非 _xy 版语义）。
"""
from __future__ import annotations

import numpy as np

from ..tools._backend import get_backend
from ..lattice._constants import Nc
from ._gluon_ope import _TENSOR4


def plaquette_dual_stack(pla):
    """对 (4,4,…,3,3) 叠的每个 (μ,ν) 求 F̃_{μν} = ½Σε_{μνρσ}F_{ρσ}。

    照抄 donghx plaquette_clover_all_tilde 语义（Levi-Civita 查表复用
    operator/_gluon_ope._TENSOR4）。
    """
    cp = get_backend()
    result = {}
    for mu in range(4):
        for nu in range(4):
            if mu == nu:
                continue
            acc = None
            for rho in range(4):
                for sigma in range(4):
                    coeff = float(_TENSOR4[mu, nu, rho, sigma])
                    if abs(coeff) < 1e-10 or rho == sigma:
                        continue
                    if (rho, sigma) not in pla:
                        continue
                    term = coeff * cp.asarray(pla[(rho, sigma)])
                    acc = term if acc is None else acc + term
            if acc is not None:
                result[(mu, nu)] = acc
    return result


def helicity_two_field_operator(gauge, pla, pla_tilde, z_dir, delta_z,
                                mu, nu, mu2, nu2, minus=False,
                                keep_plane=True,
                                pla_t=None, pla_tilde_t=None):
    """双场强插入算符 Tr[F·W†·F̃·W]（ΔG OPE 基元）。

    Args:
        gauge: 规范场 (Nt,Nz,Ny,Nx,4,3,3)。
        pla: {(mu,nu): F_{μν}(…,3,3)}——预计算场强叠
             （None 时按需单对计算由调用方传入更高效；本函数不重复算 Clover）。
        pla_tilde: {(mu,nu): F̃_{μ₂ν₂}} 对偶叠（可经 plaquette_dual_stack 生成）。
        z_dir: Wilson 线方向索引 {0:x,1:y,2:z}（3=t 禁用）。
        delta_z: 分离距离（格点单位，>0）。
        mu, nu / mu2, nu2: 两插入的 Lorentz 指标对。
        minus: False 走 +δz 支（原版 operators_new_z0_mu2_xy）；
               True 走 −δz 支（_mz_mu2_xy）。
        keep_plane: True 保留横向平面（求和一根垂直轴 → (Nt,L,L)）；
                    False 全空间求和 → (Nt,)。
        pla_t/pla_tilde_t: 可选直接给定张量（优先于字典查表）。
    Returns:
        复数数组 (Nt,L,L) 或 (Nt,)。
    """
    cp = get_backend()
    e = cp.einsum
    if z_dir not in (0, 1, 2):
        raise ValueError(f"z_dir 须为 0/1/2（x/y/z），收到 {z_dir}")
    if delta_z < 0:
        raise ValueError("delta_z 须 ≥ 0")
    a_z = 3 - z_dir

    F1 = cp.asarray(pla_t if pla_t is not None else pla[(mu, nu)])
    F2 = cp.asarray(pla_tilde_t if pla_tilde_t is not None
                    else pla_tilde[(mu2, nu2)])
    Uz = gauge[..., z_dir, :, :]          # (…,3,3) z_dir 方向链接

    if not minus:
        # 正向支：F(x+δz) ← 链†(回程) — F̃(0) — 链(去程) → trace
        ope = cp.roll(F1, -delta_z, axis=a_z)
        for _dz in range(delta_z):
            links = cp.roll(Uz, -(delta_z - 1 - _dz), axis=a_z)
            ope = e("...ab,...cb->...ac", ope, links.conj())
        ope = e("...ab,...bc->...ac", ope, F2)
        for _dz in range(delta_z):
            ope = e("...ab,...bc->...ac", ope,
                    cp.roll(Uz, -_dz, axis=a_z))
    else:
        # 反向支（原版把 delta_z 取负后同一结构）
        d = -delta_z
        ope = cp.roll(F1, -d, axis=a_z)
        for _dz in range(0, d, -1):
            ope = e("...ab,...bc->...ac", ope,
                    cp.roll(Uz, -(d - _dz), axis=a_z))
        ope = e("...ab,...bc->...ac", ope, F2)
        for _dz in range(0, d, -1):
            ope = e("...ab,...cb->...ac", ope,
                    cp.roll(Uz, -_dz + 1, axis=a_z).conj())

    tr = e("...aa->...", ope)             # 色迹
    if keep_plane:
        return _sum_axis(tr, a_z)
    return _sum_all(tr)


def _sum_axis(arr, axis):
    """空间单轴求和（保留其余平面）。"""
    return get_backend().sum(arr, axis=axis)


def _sum_all(arr):
    """全空间求和 → (Nt,)。"""
    cp = get_backend()
    flat = arr.reshape(arr.shape[0], -1)
    return cp.sum(flat, axis=1)
