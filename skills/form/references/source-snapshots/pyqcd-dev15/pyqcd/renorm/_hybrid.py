"""
混合方案重整化 + λ 外推 + 傅里叶变换（移植 zengch fit_hR_big_lambda_new.py）。

混合方案（Ji 2021, arXiv:2105.10539；A Hybrid Renormalization Scheme）：
    z < z_s：  hR(z, Pz) = hB(z, Pz) / hB(z, Pz=0)          （比值方案，短距）
    z ≥ z_s：  hR(z, Pz) = [hB(z, Pz) / Z_R(z)] · η_s       （自重整化，长距）
    其中 η_s = Z_R(z_s) / hB(z_s, Pz=0) = T_s。

λ 外推：hR(λ) ~ l₁·λ^{−a₁}·e^{−λ/λ₀}（大 λ 的解析尾巴，压制傅里叶截断振荡）。

准 PDF：hR(x, Pz) = (2/(2π))·∫dλ hR(λ)·cos(x·λ)。
"""
from __future__ import annotations

import numpy as np

from ._const import pi
from ._ensembles import fm_to_GeV, a_len_set, Nl_set, pz_to_gev


def hR_z_Pz(z_, Pz_, hR_pz, hR_0, zs, zr_fit, conf):
    """混合方案拼接：返回 (λ, hR(λ))。

    Args:
        z_:    z 数组（fm）
        Pz_:   格点单位动量
        hR_pz: hB(z, Pz) 数组（逐 bootstrap 样本：shape (nz, nboot) 或 (nz,)）
        hR_0:  hB(z, Pz=0)
        zs:    拼接点 z_s（fm）
        zr_fit: 自重整化 Z_R(z) 数组（与 z_ 同形）
        conf:  系综名（查 a_len_set/Nl_set 求 Pz_GeV）
    Returns:
        (λ, hR(λ))，λ = z_GeV · Pz_GeV。
    """
    z_ = np.asarray(z_, dtype=float)
    hR_pz = np.asarray(hR_pz, dtype=float)
    hR_0 = np.asarray(hR_0, dtype=float)
    zr_fit = np.asarray(zr_fit, dtype=float)

    pz_gev = pz_to_gev(Pz_, conf)
    z_gev = z_ / fm_to_GeV
    lambda_ = z_gev * pz_gev

    res = np.zeros_like(hR_pz, dtype=float)
    mask = z_ < zs

    if hR_pz.ndim == 1:
        res[mask] = hR_pz[mask] / hR_0[mask]
        eta_s = zr_fit[~mask][0] / hR_0[~mask][0]
        res[~mask] = (hR_pz[~mask] / zr_fit[~mask]) * eta_s
    else:
        res[mask] = hR_pz[mask] / hR_0[mask, :]
        eta_s = (zr_fit[~mask][0] / hR_0[~mask][0])
        res[~mask] = (hR_pz[~mask] / zr_fit[~mask][:, None]) * eta_s

    return lambda_, res


def hR_lambda_fit_form(lambda_, l1_, a1_, lambda0_):
    """大 λ 外推解析形式（Eq.8）。"""
    return l1_ * lambda_ ** (-a1_) * np.exp(-lambda_ / lambda0_)


def fit_hR_lambda(par_ini, lambda_range, lamb, hR_data, cov_kind='diag',
                  n_boot=200, seed=0):
    """在 [lam_min, lam_max] 区间拟合外推参数 (l1, a1, λ₀)。

    Args:
        par_ini: (l1, a1, lambda0) 初值
        lambda_range: (lam_min, lam_max)
        lamb:  λ 数组（fm 单位换算后的 λ）
        hR_data: hR(λ)（逐样本：shape (nz, nboot) 或 (nz,)）
        cov_kind: 'diag' 对角方差（默认，向后兼容）；
                  'boot' 全协方差（bootstrap 样本列，pinv 防奇异；
                  照抄 zengch fit_hR_big_lambda_new.py 的
                  covariance_matrix(·,'boot') 用法，复现其系统误差评估）。
    Returns:
        拟合参数 (l1, a1, lambda0)。
    """
    lam_min, lam_max = lambda_range
    mask = (lamb >= lam_min) & (lamb <= lam_max)
    lamb_sel = lamb[mask]
    hR_sel = np.asarray(hR_data, dtype=float)[mask]

    if cov_kind not in ('diag', 'boot'):
        raise ValueError(f"未知 cov_kind: {cov_kind}")
    if hR_sel.ndim > 1:
        data_mean = hR_sel.mean(axis=1)
        if cov_kind == 'boot':
            from ._zr import boot_covariance
            c_inv = np.linalg.pinv(
                boot_covariance(hR_sel, n_rep=n_boot, seed=seed))
        else:
            std = hR_sel.std(axis=1)
            c_inv = np.diag(1.0 / np.maximum(std ** 2, 1e-30))
    else:
        if cov_kind == 'boot':
            raise ValueError("cov_kind='boot' 需要逐样本二维输入 (nz, nsample)")
        data_mean = hR_sel
        c_inv = np.diag(1.0 / np.maximum(
            np.ones_like(hR_sel) ** 2, 1e-30))

    def cost(par):
        l1_, a1_, lambda0_ = par
        th = hR_lambda_fit_form(lamb_sel, l1_, a1_, lambda0_)
        del_h = th - data_mean
        return del_h @ c_inv @ del_h / len(lamb_sel)

    from scipy.optimize import minimize
    res = minimize(cost, par_ini, method='Nelder-Mead',
                   options={'maxiter': 5000, 'xatol': 1e-6})
    return res.x


def hR_lambda(lambda_, Pz_, lambda_extra_, l1_fit_, a1_fit_, lambda0_fit_,
              zs, z_data, hR_pz, hR_0, zr_fit, conf):
    """插值 + 外推拼接的 hR(λ)：λ ≤ λ_extra 用插值，否则用外推尾巴。

    Pz_: 格点单位动量（内部经 pz_to_gev 转换为 GeV，与 zengch 原版一致）。
    """
    lambda_data, hR_data = hR_z_Pz(z_data, Pz_, hR_pz, hR_0, zs, zr_fit, conf)

    from scipy.interpolate import interp1d
    interp = interp1d(lambda_data, hR_data, kind='linear', axis=0,
                      bounds_error=False, fill_value='extrapolate')

    res = np.where(lambda_ <= lambda_extra_,
                   interp(lambda_),
                   hR_lambda_fit_form(lambda_, l1_fit_, a1_fit_, lambda0_fit_))
    return res


def hR_x(x_, Pz_, lambda_extra_, l1_fit_, a1_fit_, lambda0_fit_,
         zs, z_data, hR_pz, hR_0, zr_fit, conf):
    """傅里叶变换 → 准 PDF：hR(x) = (2/(2π))·∫dλ hR(λ)·cos(x·λ)。

    x_ 必须为向量；用快速余弦傅里叶（scipy 数值积分）。
    Pz_: 格点单位动量（内部经 pz_to_gev 转换为 GeV，与 zengch 原版一致）。"""
    lambda_max = 60.0   # 积分截断（足够大以覆盖外推尾巴）
    n = 4096
    lam = np.linspace(0.0, lambda_max, n)
    dlam = lam[1] - lam[0]

    hr = hR_lambda(lam, Pz_, lambda_extra_, l1_fit_, a1_fit_, lambda0_fit_,
                   zs, z_data, hR_pz, hR_0, zr_fit, conf)
    if hr.ndim > 1:
        # 逐样本余弦变换
        out = np.empty((len(x_), hr.shape[1]))
        for j in range(hr.shape[1]):
            out[:, j] = (2.0 / (2.0 * pi)) * dlam * (
                hr[:, j] @ np.cos(np.outer(x_, lam).T))
        return out
    return (2.0 / (2.0 * pi)) * dlam * (hr @ np.cos(np.outer(x_, lam).T))
