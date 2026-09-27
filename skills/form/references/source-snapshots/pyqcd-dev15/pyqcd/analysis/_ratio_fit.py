"""
裸矩阵元 c0(z) 提取（移植 zengch fit_ratio.py 核心逻辑）
=========================================================

比值模型（R(dt, dtau, z)）：
    z = z₀:  R = c0_z0 + c1_z0·(e^{−dE(tsep−ti)} + e^{−dE·ti}) + c2_z0·e^{−dE·tsep}
    z = z₁:  R = c0_z1 + c1_z1·(e^{−dE(tsep−ti)} + e^{−dE·ti}) + c2_z1·e^{−dE·tsep}

c0(z) 即坐标空间裸矩阵元（后续重整化/匹配的输入）。逐重采样样本拟合。
"""
from __future__ import annotations

import numpy as np


def covariance_matrix_inv(samples, resam_type='boot'):
    """重采样样本协方差的逆（samples 布局 (n_points, n_samples)）。

    jackknife：cov = Σ(x̄ − x_i)(x̄ − x_i)ᵀ·(n−1)/n（均值协方差，delete-one 约定）；
    bootstrap：cov = Σ(x̄ − x_i)(x̄ − x_i)ᵀ/n。
    """
    s = np.asarray(samples, dtype=float)
    if s.ndim == 1:
        s = s[:, None]
    n_samples = s.shape[1]
    mean = s.mean(axis=1)
    diff = (s - mean[:, None]).T        # (n_samples, n_points)
    if resam_type == 'jack':
        cov = np.matmul(diff.T, diff) / n_samples * (n_samples - 1)
    else:   # bootstrap
        cov = np.matmul(diff.T, diff) / n_samples
    return np.linalg.inv(cov)


def _ratio_fit_design(z_, tsep_, ti_, z_list_):
    """预计算比值拟合所需的掩码和时间差。"""
    z_arr = np.asarray(z_)
    tsep_arr = np.asarray(tsep_, dtype=float)
    ti_arr = np.asarray(ti_, dtype=float)
    z_list = tuple(z_list_)
    if len(z_list) < 2:
        raise ValueError('z_list 至少需要两个取值')

    mask0 = (z_arr == z_list[0])
    mask1 = (z_arr == z_list[1])
    if not np.all(mask0 | mask1):
        raise ValueError(f'z 只允许 {z_list[0]} 或 {z_list[1]}')

    return {
        'z': z_arr,
        'tsep': tsep_arr,
        'ti': ti_arr,
        'dt': tsep_arr - ti_arr,
        'mask0': mask0,
        'mask1': mask1,
        'z_list': z_list,
    }


def _ratio_model_from_design(par, design):
    """按预计算设计评估 R 模型。"""
    (c0_z0, c1_z0, c2_z0,
     c0_z1, c1_z1, c2_z1,
     deltaE) = np.asarray(par, dtype=float)
    res = np.zeros_like(np.asarray(design['ti'], dtype=float))
    exp_dt = np.exp(-deltaE * design['dt'])
    exp_ti = np.exp(-deltaE * design['ti'])
    exp_tsep = np.exp(-deltaE * design['tsep'])

    mask0 = design['mask0']
    if np.any(mask0):
        res[mask0] = (c0_z0
                      + c1_z0 * (exp_dt[mask0] + exp_ti[mask0])
                      + c2_z0 * exp_tsep[mask0])

    mask1 = design['mask1']
    if np.any(mask1):
        res[mask1] = (c0_z1
                      + c1_z1 * (exp_dt[mask1] + exp_ti[mask1])
                      + c2_z1 * exp_tsep[mask1])
    return res


def _ratio_model_jacobian(par, design):
    """R 模型对参数的解析雅可比（未加白化）。"""
    (c0_z0, c1_z0, c2_z0,
     c0_z1, c1_z1, c2_z1,
     deltaE) = np.asarray(par, dtype=float)
    n_data = int(np.asarray(design['ti']).size)
    jac = np.zeros((n_data, 7), dtype=float)
    exp_dt = np.exp(-deltaE * design['dt'])
    exp_ti = np.exp(-deltaE * design['ti'])
    exp_tsep = np.exp(-deltaE * design['tsep'])

    mask0 = design['mask0']
    if np.any(mask0):
        jac[mask0, 0] = 1.0
        jac[mask0, 1] = exp_dt[mask0] + exp_ti[mask0]
        jac[mask0, 2] = exp_tsep[mask0]
        jac[mask0, 6] = -(
            c1_z0 * design['dt'][mask0] * exp_dt[mask0]
            + c1_z0 * design['ti'][mask0] * exp_ti[mask0]
            + c2_z0 * design['tsep'][mask0] * exp_tsep[mask0])

    mask1 = design['mask1']
    if np.any(mask1):
        jac[mask1, 3] = 1.0
        jac[mask1, 4] = exp_dt[mask1] + exp_ti[mask1]
        jac[mask1, 5] = exp_tsep[mask1]
        jac[mask1, 6] = -(
            c1_z1 * design['dt'][mask1] * exp_dt[mask1]
            + c1_z1 * design['ti'][mask1] * exp_ti[mask1]
            + c2_z1 * design['tsep'][mask1] * exp_tsep[mask1])
    return jac


def R_model(z_, tsep_, ti_, z_list_, c0_z0, c1_z0, c2_z0,
            c0_z1, c1_z1, c2_z1, deltaE):
    """比值模型（zengch 公式）。"""
    design = _ratio_fit_design(z_, tsep_, ti_, z_list_)
    return _ratio_model_from_design(
        [c0_z0, c1_z0, c2_z0, c0_z1, c1_z1, c2_z1, deltaE], design)


def _whitener(c_inv):
    """返回 W，使 ``W.T @ W`` 等于协方差逆矩阵。"""
    c_inv = np.asarray(c_inv, dtype=float)
    try:
        return np.linalg.cholesky(c_inv).T
    except np.linalg.LinAlgError:
        # 允许轻微非对称/半正定的数值协方差；负特征值仍拒绝。
        sym = (c_inv + c_inv.T) / 2.0
        eigval, eigvec = np.linalg.eigh(sym)
        scale = max(float(np.max(np.abs(eigval))), 1.0)
        if np.min(eigval) < -1e-10 * scale:
            raise
        return np.sqrt(np.maximum(eigval, 0.0))[:, None] * eigvec.T


def _fit_one(y, z_set, tsep_set, ti_set, z_list, c_inv, par_ini=None,
             optimizer='least_squares', whitener=None, design=None):
    """单组数据（均值或单样本）最小二乘拟合。

    ``least_squares`` 通过协方差白化直接最小化同一个全协方差 χ²；
    ``nelder-mead`` 保留旧实现，便于回归对照和不定协方差的兼容。
    """
    if par_ini is None:
        par_ini = [0.5, -0.2, 0.0, 0.5, -0.2, 0.0, 0.3]
    if design is None:
        design = _ratio_fit_design(z_set, tsep_set, ti_set, z_list)

    if optimizer == 'nelder-mead':
        data_num = len(design['z'])

        def cost(par):
            th = _ratio_model_from_design(par, design)
            del_r = y - th
            return float(del_r.T @ c_inv @ del_r / data_num)

        from scipy.optimize import minimize
        res = minimize(cost, par_ini, method='Nelder-Mead',
                       options={'maxiter': 20000, 'xatol': 1e-8})
        return res.x

    if optimizer != 'least_squares':
        raise ValueError("optimizer must be 'least_squares' or 'nelder-mead'")

    if whitener is None:
        whitener = _whitener(c_inv)

    y = np.asarray(y, dtype=float)

    def residual(par):
        th = _ratio_model_from_design(par, design)
        return whitener @ (y - th)

    def jacobian(par):
        return -(whitener @ _ratio_model_jacobian(par, design))

    from scipy.optimize import least_squares
    res = least_squares(
        residual, np.asarray(par_ini, dtype=float), jac=jacobian, method='trf',
        max_nfev=2000, xtol=1e-10, ftol=1e-10, gtol=1e-10)
    if not res.success or not np.all(np.isfinite(res.x)):
        # 保留旧路径作为极端数据/数值退化时的安全回退。
        return _fit_one(y, z_set, tsep_set, ti_set, z_list, c_inv,
                        par_ini=par_ini, optimizer='nelder-mead',
                        design=design)
    return res.x


def fit_ratio(data_for_fit, resam_type='boot', optimizer='least_squares'):
    """逐样本拟合比值，提取 c0(z₀)/c0(z₁) 与 deltaE。

    Args:
        data_for_fit: (z_set, tsep_set, ti_set, ratio_mean, err,
                       ratio_samples, z_list, t_sep_list, n_remove)
        resam_type: 'boot' or 'jack' covariance convention.
        optimizer: 'least_squares' (default) or 'nelder-mead' compatibility path.
    Returns:
        dict: {c0_z0, c1_z0, c2_z0, c0_z1, c1_z1, c2_z1, deltaE,
               c0_z0_err, c0_z1_err, deltaE_err}（逐样本均值与误差）
    """
    (z_set_, tsep_set_, ti_sep_set_, ratio_mean_set_, err_set,
     ratio_samples_fit_, z_list_, _t_sep_list_, _n_remove_) = data_for_fit
    design = _ratio_fit_design(z_set_, tsep_set_, ti_sep_set_, z_list_)
    c_inv = covariance_matrix_inv(ratio_samples_fit_, resam_type)
    whitener = _whitener(c_inv) if optimizer == 'least_squares' else None

    # 均值初始化 + χ²>2 换初值重试（对照原版 fit_ratio→fit_ratio_mean 链，
    # scipy 等价实现：取两轮初值中 χ² 更优者作为逐样本拟合起点）
    y_mean = np.asarray(ratio_mean_set_, dtype=float)
    par_ini = _fit_one(y_mean, z_set_, tsep_set_, ti_sep_set_, z_list_, c_inv,
                       optimizer=optimizer, whitener=whitener,
                       design=design)
    del_mean = y_mean - _ratio_model_from_design(par_ini, design)
    chi2_best = float(del_mean @ c_inv @ del_mean)
    if chi2_best / len(z_set_) > 2.0:
        alt = _fit_one(y_mean, z_set_, tsep_set_, ti_sep_set_, z_list_,
                       c_inv, par_ini=[0.5, -1.5, 0.0, 0.5, -1.5, 0.0,
                                       1.02788], optimizer=optimizer,
                       whitener=whitener, design=design)
        del_alt = y_mean - _ratio_model_from_design(alt, design)
        if float(del_alt @ c_inv @ del_alt) < chi2_best:
            par_ini = alt

    n_samples = ratio_samples_fit_.shape[1]
    fits = np.zeros((n_samples, 7))
    for sample_i in range(n_samples):
        y = ratio_samples_fit_[:, sample_i]
        fits[sample_i] = _fit_one(y, z_set_, tsep_set_, ti_sep_set_,
                                  z_list_, c_inv, par_ini=list(par_ini),
                                  optimizer=optimizer, whitener=whitener,
                                  design=design)

    mean = fits.mean(axis=0)
    err = fits.std(axis=0)
    if resam_type == 'jack':
        # jackknife 误差重标定 std×√(n−1)（原版 fit_ratio.py 同款）
        err = err * np.sqrt(n_samples - 1)
    keys = ['c0_z0', 'c1_z0', 'c2_z0', 'c0_z1', 'c1_z1', 'c2_z1', 'deltaE']
    return {k: mean[i] for i, k in enumerate(keys)} | \
        {f'{k}_err': err[i] for i, k in enumerate(keys)}


# ═══════════════════════════════════════════════════════════════════
# FH 常数拟合与自适应 t_sep 窗口（整合 zengch fit_ratio_FeynmenHellman_new）
# ═══════════════════════════════════════════════════════════════════

def fit_constant_window(c0_zt, kind='boot', seed=0):
    """常数 c0 的协方差加权窗口拟合（照抄 fit_ratio_mean_FeynmenHellman 核）。

    常数模型的全协方差 χ² 极小化有闭式解：
        c0 = (1ᵀC⁻¹d)/(1ᵀC⁻¹1)，χ² = (d−c0)ᵀC⁻¹(d−c0)/(n−1)
    与原版 Minuit 数值结果一致（无优化器依赖）。

    Args:
        c0_zt: (n_tsep, n_sample) 窗口内比值数据（逐重采样样本）。
        kind: 'boot'|'jack'（covariance_matrix_inv 语义）。
    Returns:
        dict(c0, c0_std(逐样本散布), chi2, chi2_nocov, c0_samples,
        n_data, n_sample, fit_status, fit_reason, sample_rank,
        effective_rank)。
    """
    d = np.asarray(c0_zt, dtype=float)
    if d.ndim != 2:
        raise ValueError("c0_zt 必须为 (n_tsep, n_sample) 二维数组")
    if d.shape[0] < 2 or d.shape[1] < 2:
        raise ValueError("常数拟合至少需要 2 个 t_sep 和 2 个样本")
    if not np.isfinite(d).all():
        raise ValueError("c0_zt 必须全部有限")

    n, n_sample = d.shape
    resam_type = 'boot' if kind == 'boot' else 'jack'

    def _failure(reason, sample_rank, effective_rank):
        return {
            'c0': np.nan,
            'c0_std': np.nan,
            'chi2': np.nan,
            'chi2_nocov': np.nan,
            'c0_samples': np.full(n_sample, np.nan),
            'n_data': int(n),
            'n_sample': int(n_sample),
            'fit_status': 'statistically_unidentifiable',
            'fit_reason': str(reason),
            'sample_rank': int(sample_rank),
            'effective_rank': int(effective_rank),
        }

    # The sample covariance is formed before attempting the inverse so that a
    # singular sample axis is reported as a statistical failure, rather than
    # leaking ``LinAlgError`` or being silently replaced by a pseudoinverse.
    centered = d - d.mean(axis=1, keepdims=True)
    covariance = centered @ centered.T / n_sample
    if resam_type == 'jack':
        covariance *= n_sample - 1

    try:
        from ._fitter import covariance_effective_rank, covariance_sample_rank
        sample_rank = int(covariance_sample_rank(covariance))
        effective_rank = int(covariance_effective_rank(covariance, None))
    except (np.linalg.LinAlgError, ValueError) as error:
        return _failure(
            f"sample covariance rank could not be established: {error}",
            0, 0)

    if sample_rank < n or effective_rank < n:
        return _failure(
            f"sample covariance rank={sample_rank}, effective rank="
            f"{effective_rank}; full rank {n} is required for the constant "
            "covariance inverse",
            sample_rank, effective_rank)

    try:
        c_inv = covariance_matrix_inv(d, resam_type=resam_type)
    except np.linalg.LinAlgError as error:
        return _failure(
            f"constant covariance inverse is unavailable: {error}",
            sample_rank, effective_rank)
    if not np.isfinite(c_inv).all():
        return _failure(
            "constant covariance inverse contains non-finite values",
            sample_rank, effective_rank)

    ones = np.ones(n)
    denom = ones @ c_inv @ ones
    if not np.isfinite(denom) or denom == 0.0:
        return _failure(
            "constant covariance inverse has an invalid constant-model "
            "normalization",
            sample_rank, effective_rank)
    c0 = (ones @ c_inv @ d.mean(axis=1)) / denom
    r = d.mean(axis=1) - c0
    chi2 = float(r @ c_inv @ r) / max(n - 1, 1)
    c_inv_nocov = np.diag(1.0 / np.maximum(d.std(axis=1) ** 2, 1e-30))
    chi2_nocov = float(r @ c_inv_nocov @ r) / max(n - 1, 1)
    # 逐样本重拟合（同闭式，逐列）
    per = c_inv @ d                       # (n, nsam)
    num = ones @ per                      # (nsam,)
    c0_samples = num / denom
    values = (c0, chi2, chi2_nocov, c0_samples)
    if not all(np.isfinite(value).all() for value in values):
        return _failure(
            "constant covariance fit produced non-finite values",
            sample_rank, effective_rank)
    return {'c0': float(c0), 'c0_std': float(np.std(c0_samples)),
            'chi2': chi2, 'chi2_nocov': chi2_nocov,
            'c0_samples': c0_samples, 'n_data': int(n),
            'n_sample': int(n_sample), 'fit_status': 'identifiable',
            'fit_reason': 'identifiable', 'sample_rank': sample_rank,
            'effective_rank': effective_rank}


def fh_adaptive_windows(delta, t_sep_vals, t_do0, t_up0, chi2_limit=1.5,
                        t_floor=None, z_max=None, kind='boot', seed=0,
                        verbose=False, logger=print):
    """χ² 上限驱动的逐 z 自适应 t_sep 窗口滑动（c0_vs_z_FeynmenHellman 语义）。

    每 z 从上一 z 收敛窗起步：窗口宽度取初始窗包含的 t_sep 点数，χ² 超限则
    按严格递增的真实 t_sep 索引右移；未超限则按索引尝试左移一步收紧
    （下界保护 t_floor，仍超限即回退）。
    小 z（< z_direct=6）直接沿用初始窗（原版约定：z≤5 不滑窗）。

    Args:
        delta: (nz, n_tsep, n_sample) 比值数据。
        t_sep_vals: (n_tsep,) 严格递增且无重复的真实 t_sep 值
            （与第二维逐项对应）。
        t_do0/t_up0: 初始窗口 [下, 上]（含端点，按 t_sep_vals 取值）。
        chi2_limit: 右移触发的 χ² 上限。
        t_floor: 窗口下界（None 时取 min(t_sep_vals)）。
    Returns:
        records: [{'z', 't_do', 't_up', 'fit'(fit_constant_window dict),
                  'status'('chi2_accepted'|'chi2_exceeded'|fit status),
                  'fit_status', 'fit_reason'}]
    """
    delta = np.asarray(delta, dtype=float)
    t_vals = np.asarray(t_sep_vals, dtype=int)
    if delta.ndim != 3:
        raise ValueError("delta 必须为 (nz, n_tsep, n_sample) 三维数组")
    if t_vals.ndim != 1 or np.any(np.diff(t_vals) <= 0):
        raise ValueError("t_sep_vals must be one-dimensional and strictly increasing")
    if delta.shape[1] != t_vals.size:
        raise ValueError(
            "delta 的 t_sep 轴必须与 t_sep_vals 长度一致")
    if not np.isfinite(delta).all():
        raise ValueError("delta 必须全部有限")
    t_floor = int(t_floor) if t_floor is not None else int(t_vals.min())
    z_total = delta.shape[0] if z_max is None else min(z_max,
                                                       delta.shape[0])
    records = []
    initial = np.flatnonzero((t_vals >= t_do0) & (t_vals <= t_up0))
    if initial.size < 2:
        raise ValueError(
            f"初始窗口 [{t_do0},{t_up0}] 内不足 2 个 t_sep")
    window_size = int(initial.size)
    last_start = int(initial[0])

    def _bounds(start):
        return (int(t_vals[start]),
                int(t_vals[start + window_size - 1]))

    def _fit(z, start):
        return fit_constant_window(
            delta[z, start:start + window_size], kind=kind, seed=seed)

    def _fit_is_usable(fit):
        return (fit.get('fit_status') in ('identifiable', 'prior_constrained')
                and np.isfinite(fit.get('chi2', np.nan)))

    for z in range(z_total):
        start = last_start
        do, up = _bounds(start)
        fit = _fit(z, start)
        fit_status = str(fit.get('fit_status', 'unavailable'))
        if not _fit_is_usable(fit):
            status = fit_status
            records.append({
                'z': z, 't_do': do, 't_up': up, 'fit': fit,
                'status': status, 'fit_status': fit_status,
                'fit_reason': str(fit.get(
                    'fit_reason', 'fit status is unavailable')),
            })
            if verbose:
                logger(f"z={z}: window=[{do},{up}] status={status} "
                       f"reason={fit.get('fit_reason', 'unavailable')}")
            last_start = start
            continue
        if z >= 6:                        # 小 z 直接用初始/继承窗
            # 按真实 t_sep 索引右移；固定点数确保稀疏网格中的每个候选都合法。
            while fit['chi2'] > chi2_limit:
                next_start = start + 1
                if next_start + window_size > t_vals.size:
                    break
                start = next_start
                do, up = _bounds(start)
                fit = _fit(z, start)
                if not _fit_is_usable(fit):
                    break
            # 未超限则尝试左移一步收紧（超限回退）
            if _fit_is_usable(fit) and fit['chi2'] <= chi2_limit \
                    and start > 0 \
                    and t_vals[start - 1] >= t_floor:
                trial_start = start - 1
                trial = _fit(z, trial_start)
                if (_fit_is_usable(trial)
                        and trial['chi2'] <= chi2_limit):
                    start = trial_start
                    do, up = _bounds(start)
                    fit = trial
        fit_status = str(fit.get('fit_status', 'unavailable'))
        if not _fit_is_usable(fit):
            status = fit_status
        else:
            status = ('chi2_accepted' if fit['chi2'] <= chi2_limit
                  else 'chi2_exceeded')
        records.append({'z': z, 't_do': do, 't_up': up, 'fit': fit,
                        'status': status, 'fit_status': fit_status,
                        'fit_reason': str(fit.get(
                            'fit_reason', 'fit status is unavailable'))})
        if verbose:
            if _fit_is_usable(fit):
                logger(f"z={z}: window=[{do},{up}] "
                       f"c0={fit['c0']:.4g}±{fit['c0_std']:.2g} "
                       f"chi2={fit['chi2']:.3g} status={status}")
            else:
                logger(f"z={z}: window=[{do},{up}] status={status} "
                       f"reason={fit.get('fit_reason', 'unavailable')}")
        last_start = start
    return records
