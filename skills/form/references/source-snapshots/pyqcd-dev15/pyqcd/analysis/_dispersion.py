"""
色散关系拟合（移植 zengch fit_E0.py 核心逻辑）
================================================

    E(Pz) = √( m² + k₂·Pz² + k₃·Pz⁴·a² )

从多个动量的有效能量 E0(Pz) 拟合核子质量 m 与色散系数 k₂、k₃。
"""
from __future__ import annotations

import numpy as np

from ..renorm._ensembles import Nl_set


def pz_to_gev_lattice(pz, nl, a_gev):
    """格点单位动量 → GeV：Pz·(2π)/(N_l·a)。"""
    return pz * 2.0 * np.pi / (nl * a_gev)


def th_E0(Pz_gev, m, k2, k3, a_gev):
    """色散关系参数化（Pz_gev 单位 GeV；k₃ 项为 O(a²) 离散化修正）。"""
    return np.sqrt(m ** 2 + k2 * Pz_gev ** 2 + k3 * Pz_gev ** 4 * a_gev ** 2)


def fit_dispersion(E0_list, Pz_list, a_gev, errors=None, conf=None,
                   return_diagnostics=False):
    """在能量空间拟合 ``(m, k2, k3)``，并约束所有预测能量为正。

    Args:
        E0_list: 有效能量数组（GeV，逐 Pz）。
        Pz_list: 动量数组（格点单位）。
        a_gev: 格距（GeV⁻¹）。
        errors: 逐点误差（可选，用于加权）。
        conf: 系综名（用于 N_l 查表；默认 24）。
        return_diagnostics: 若为真，额外返回优化状态、Jacobian 谱和协方差。
    Returns:
        默认返回 ``(m, k2, k3)``；``return_diagnostics=True`` 时返回
        ``((m, k2, k3), diagnostics)``。

    Raises:
        ValueError: 输入非有限，或列缩放后的设计矩阵不可辨识。
        RuntimeError: 优化失败或未得到物理上为正的预测能量平方。
    """
    E0 = np.asarray(E0_list, dtype=float)
    pz_lat = np.asarray(Pz_list, dtype=float)
    if E0.ndim != 1 or pz_lat.ndim != 1:
        raise ValueError("E0_list and Pz_list must be one-dimensional")
    if E0.size != pz_lat.size:
        raise ValueError("E0_list and Pz_list must have the same length")
    if E0.size == 0:
        raise ValueError("at least one dispersion data point is required")
    if not np.isfinite(E0).all() or not np.isfinite(pz_lat).all():
        raise ValueError("dispersion inputs must be finite")
    if not np.isfinite(a_gev) or a_gev <= 0.0:
        raise ValueError("a_gev must be finite and positive")
    if np.any(E0 <= 0.0):
        raise ValueError("E0_list must contain positive energies")

    nl = Nl_set.get(conf, 24) if conf else 24
    pz_gev = pz_to_gev_lattice(pz_lat, nl, a_gev)
    if not np.isfinite(pz_gev).all():
        raise ValueError("converted dispersion momenta must be finite")

    design = np.column_stack(
        (np.ones_like(pz_gev), pz_gev ** 2,
         pz_gev ** 4 * a_gev ** 2))
    if not np.isfinite(design).all():
        raise ValueError("dispersion design matrix must be finite")

    if errors is None:
        errors = np.ones_like(E0)
    errors = np.asarray(errors, dtype=float)
    if errors.shape != E0.shape:
        raise ValueError("errors must have the same one-dimensional shape as E0_list")
    if not np.isfinite(errors).all() or np.any(errors <= 0.0):
        raise ValueError("errors must be finite and positive")

    # Identifiability belongs to the momentum design, not to an E²
    # delta-method likelihood.  Weight rows by the supplied E-space errors,
    # then scale every column before evaluating rank or conditioning.
    weighted_design = design / errors[:, None]
    if not np.isfinite(weighted_design).all():
        raise ValueError("weighted dispersion design must be finite")
    singular_values = np.linalg.svd(weighted_design, compute_uv=False)
    n_params = weighted_design.shape[1]
    column_scale = np.linalg.norm(weighted_design, axis=0)
    safe_column_scale = np.where(column_scale > 0.0, column_scale, 1.0)
    scaled_weighted_design = weighted_design / safe_column_scale
    scaled_singular_values = np.linalg.svd(
        scaled_weighted_design, compute_uv=False)
    precision = np.finfo(weighted_design.dtype)
    rank_tolerance = (
        precision.eps * max(scaled_weighted_design.shape)
        * scaled_singular_values[0]
    )
    jacobian_rank = int(np.count_nonzero(
        scaled_singular_values > rank_tolerance))
    if jacobian_rank < n_params:
        raise ValueError(
            f"dispersion design rank={jacobian_rank} is below 3; use "
            "dispersion_check or provide more independent momenta")
    dof = E0.size - n_params
    condition = float(singular_values[0] / singular_values[-1])
    scaled_condition = float(
        scaled_singular_values[0] / scaled_singular_values[-1])
    condition_limit = float(1.0 / np.sqrt(precision.eps))
    if not np.isfinite(scaled_condition) or \
            scaled_condition >= condition_limit:
        raise ValueError(
            "column-scaled dispersion design is ill-conditioned for double "
            f"precision: condition={scaled_condition:.6e}, "
            f"limit={condition_limit:.6e}; "
            "use dispersion_check or provide better separated momenta")

    # Optimize theta=(m²,k2,k3) so positivity remains a linear constraint,
    # but evaluate residuals in E space exactly as the reference fit does.
    energy2 = E0 ** 2
    prediction_scale = float(np.max(energy2))
    positive_floor = np.sqrt(precision.eps) * prediction_scale
    initial_theta = np.array([max(0.9 ** 2, 2.0 * positive_floor),
                              1.0, 0.0])
    initial_scaled = initial_theta * safe_column_scale
    scaled_design = design / safe_column_scale

    def residual(scaled_theta):
        predicted_energy2 = scaled_design @ scaled_theta
        predicted_energy = np.sqrt(
            np.maximum(predicted_energy2, positive_floor))
        return (predicted_energy - E0) / errors

    def objective(scaled_theta):
        values = residual(scaled_theta)
        return 0.5 * np.dot(values, values)

    def gradient(scaled_theta):
        predicted_energy2 = scaled_design @ scaled_theta
        predicted_energy = np.sqrt(
            np.maximum(predicted_energy2, positive_floor))
        jacobian = scaled_design / (
            2.0 * predicted_energy[:, None] * errors[:, None])
        return jacobian.T @ residual(scaled_theta)

    from scipy.optimize import LinearConstraint, minimize
    theta0_row = np.array(
        [[1.0 / safe_column_scale[0], 0.0, 0.0]])
    positive_matrix = np.vstack((theta0_row, scaled_design))
    positive_parameters_and_predictions = LinearConstraint(
        positive_matrix,
        np.full(E0.size + 1, positive_floor),
        np.full(E0.size + 1, np.inf),
    )
    res = minimize(
        objective, initial_scaled, method="SLSQP", jac=gradient,
        constraints=positive_parameters_and_predictions,
        options={"ftol": 1.0e-12, "maxiter": 2000},
    )
    if not res.success:
        raise RuntimeError(f"dispersion optimization failed: {res.message}")
    theta = res.x / safe_column_scale
    predicted_energy2 = design @ theta
    if not np.isfinite(theta).all() or not np.isfinite(predicted_energy2).all():
        raise RuntimeError("dispersion optimization produced non-finite values")
    if theta[0] <= 0.0 or np.any(predicted_energy2 <= 0.0):
        raise RuntimeError(
            "dispersion optimization did not preserve positive squared "
            "energies")

    mass = np.sqrt(theta[0])
    predicted_energy = np.sqrt(predicted_energy2)
    constraint_values = np.concatenate(([theta[0]], predicted_energy2))
    constraint_slack = constraint_values - positive_floor
    active_tolerance = 10.0 * positive_floor
    active_constraints = constraint_slack <= active_tolerance
    constraint_active = bool(np.any(active_constraints))

    # The ordinary inverse-curvature covariance is meaningful only for an
    # interior optimum.  At an active inequality boundary it would assign
    # probability to forbidden predictions, so expose NaNs instead.
    covariance_valid = not constraint_active
    if covariance_valid:
        model_jacobian = np.column_stack((
            mass / predicted_energy,
            design[:, 1] / (2.0 * predicted_energy),
            design[:, 2] / (2.0 * predicted_energy),
        )) / errors[:, None]
        _, covariance_singular_values, right_vectors = np.linalg.svd(
            model_jacobian, full_matrices=False)
        covariance = (
            right_vectors.T * (1.0 / covariance_singular_values ** 2)
        ) @ right_vectors
        covariance = 0.5 * (covariance + covariance.T)
        if not np.isfinite(covariance).all():
            raise RuntimeError("dispersion covariance is not finite")
    else:
        covariance = np.full((n_params, n_params), np.nan)

    residual_values = residual(res.x)
    chi2 = float(np.dot(residual_values, residual_values))
    goodness_of_fit_available = dof > 0
    reduced_chi2 = chi2 / dof if goodness_of_fit_available else np.nan

    fitted = (mass, theta[1], theta[2])
    if not return_diagnostics:
        return fitted
    return fitted, {
        "success": bool(res.success),
        "likelihood_space": "energy",
        "jacobian_rank": int(jacobian_rank),
        "dof": int(dof),
        "chi2": chi2,
        "reduced_chi2": reduced_chi2,
        "goodness_of_fit_available": goodness_of_fit_available,
        "covariance": covariance,
        "covariance_valid": covariance_valid,
        "constraint_active": constraint_active,
        "active_constraints": active_constraints,
        "constraint_slack": constraint_slack,
        "positive_floor": positive_floor,
        "predicted_energy": predicted_energy,
        "singular_values": singular_values,
        "condition": condition,
        "condition_limit": condition_limit,
        "column_scale": column_scale,
        "scaled_singular_values": scaled_singular_values,
        "scaled_condition": scaled_condition,
    }


def dispersion_check(E0_P0, E0_P2, pz_gev, m_ref=None):
    """色散关系核对：k₂_eff = (E(Pz)² − E(0)²)/Pz²，返回 (k₂_eff, 偏差%)。"""
    k2_eff = (E0_P2 ** 2 - E0_P0 ** 2) / pz_gev ** 2
    dev = abs(k2_eff - 1.0) * 100
    return k2_eff, dev
