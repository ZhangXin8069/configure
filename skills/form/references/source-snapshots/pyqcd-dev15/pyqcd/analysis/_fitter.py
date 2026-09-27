"""
统计拟合工具（独立实现，功能对齐 refer/huangcl/98_tools/analysis_tools.py 拟合部分）
====================================================================================

- `FitParams`：拟合参数 dataclass（p0 / prior / 拟合窗口 / svdcut / nex）。
- `covariance_sample_rank` / `covariance_effective_rank`：分别诊断原始样本
  协方差信息秩和 `gvar/lsqfit` 调节后的数据自由度。
- `fit_identifiability`：区分原始统计信息与 SVD 调节，执行统一可辨识门。
- `calc_chi2` / `calc_chi2_dof`：chi2 计算（支持 lsqfit 风格 svdcut 特征值截断）。
- `fit`：逐样本 lsqfit 非线性拟合封装（prior 优先、数值模型 Jacobian
  可辨识门、debug 模式 NaN 填充）。
- `make_summary_table`：ASCII 对齐表格（独立复现 PrettyTable 对齐风格，
  pyqcd 不引入 prettytable 依赖）。
- `fit_report_lines`：通用拟合报告行构造（头部/逐项/汇总表）。

统计基元 sem/resample/cov_mat 复用 pyqcd.analysis._disconnected（同包）。
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple, Union

import numpy as np

from ._disconnected import sem, cov_mat


AUTO_SVDCUT = 1.0e-12
JACOBIAN_RELATIVE_STEP = np.cbrt(np.finfo(np.float64).eps)
JACOBIAN_STABILITY_RTOL = 1.0e-3
JACOBIAN_RANK_RTOL = np.sqrt(np.finfo(np.float64).eps)
JACOBIAN_SIDE_RTOL = 1.0e-2
JACOBIAN_LOCAL_MIN_EXPONENT = -16
JACOBIAN_LOCAL_MAX_EXPONENT = 16
JACOBIAN_DIAGNOSTIC_EXPONENT = 52


@dataclass
class FitParams:
    """拟合参数。

    ``svdcut="auto"``（默认）显式使用 gvar 的稳健正调节尺度
    ``1e-12``；``None`` 表示严格不调节，奇异 covariance 会在进入
    lsqfit 前报错。数值正/负值分别沿用 gvar 的抬升/删除模语义。
    """

    p0: dict
    prior: dict = None
    dt_start: int = 0
    dt_end: int = 10
    svdcut: Union[float, str, None] = "auto"
    nex: int = 0   # FH 等 τ 方向两端各去掉的点数
    jacobian: Optional[Callable] = None
    # Optional exact real-parameter Jacobian: jacobian(x, p) ->
    # {parameter: (Ndata,)} or (Ndata, Nparam) ordered like p0.


def _correlation_eigensystem(cov: np.ndarray):
    """Validate a Hermitian covariance and return its active correlation modes."""
    matrix = np.asarray(cov)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("cov must be a square matrix")
    if not np.isfinite(matrix).all():
        raise ValueError("cov must contain only finite values")
    matrix = np.asarray(matrix, dtype=np.result_type(matrix.dtype, np.float64))
    hermitian = (matrix + matrix.conj().T) * 0.5
    scale_matrix = float(np.max(np.abs(matrix), initial=0.0))
    symmetry_tolerance = (
        scale_matrix * max(matrix.shape[0], 1) * np.finfo(np.float64).eps
    )
    if np.max(np.abs(matrix - matrix.conj().T), initial=0.0) > symmetry_tolerance:
        raise ValueError("cov must be Hermitian")

    diagonal = np.real_if_close(np.diag(hermitian))
    if np.iscomplexobj(diagonal):
        raise ValueError("cov diagonal must be real")
    diagonal = np.asarray(diagonal, dtype=np.float64)
    if np.any(diagonal < 0.0):
        raise ValueError("cov diagonal must be non-negative")
    active = diagonal > 0.0
    inactive = ~active
    if np.any(inactive) and (
            np.any(matrix[inactive, :] != 0.0)
            or np.any(matrix[:, inactive] != 0.0)):
        raise ValueError("cov must be positive semidefinite")
    if not np.any(active):
        return hermitian, active, np.empty(0), np.empty((0, 0)), np.empty(0)

    std = np.sqrt(diagonal[active])
    corr = hermitian[np.ix_(active, active)] / std[:, None] / std[None, :]
    corr = (corr + corr.conj().T) * 0.5
    eigval, eigvec = np.linalg.eigh(corr)
    largest = max(float(eigval[-1]), 0.0)
    tolerance = largest * corr.shape[0] * np.finfo(np.float64).eps
    if eigval[0] < -tolerance:
        raise ValueError("cov must be positive semidefinite")
    eigval = np.maximum(eigval, 0.0)
    return hermitian, active, eigval, eigvec, std


def _validate_svdcut(
    svdcut: Union[float, str, None],
) -> Optional[float]:
    if svdcut is None:
        return None
    if isinstance(svdcut, str):
        if svdcut == "auto":
            return AUTO_SVDCUT
        raise ValueError("svdcut string value must be 'auto'")
    if (isinstance(svdcut, (bool, np.bool_))
            or not np.isscalar(svdcut)
            or not np.isfinite(svdcut)
            or abs(float(svdcut)) >= 1.0):
        raise ValueError("svdcut must be a finite scalar with abs(svdcut) < 1")
    return float(svdcut)


@dataclass(frozen=True)
class _JacobianMetric:
    """Immutable covariance geometry reused by every sample Jacobian."""

    matrix: np.ndarray
    active: np.ndarray
    eigval: np.ndarray
    eigvec: np.ndarray
    std: np.ndarray
    retained: np.ndarray
    denominators: np.ndarray


def _covariance_sample_rank_from_eigensystem(eigensystem) -> int:
    """Return sample rank without repeating the covariance eigendecomposition."""
    _, active, eigval, _, _ = eigensystem
    if not np.any(active):
        return 0
    largest = max(float(eigval[-1]), 0.0)
    tolerance = largest * eigval.size * np.finfo(np.float64).eps
    return int(np.count_nonzero(eigval > tolerance))


def _covariance_effective_rank_from_eigensystem(
    eigensystem,
    svdcut: Union[float, str, None],
) -> int:
    """Return regulated rank from a previously computed eigensystem."""
    matrix, active, eigval, _, _ = eigensystem
    if matrix.shape[0] == 0 or not np.any(active):
        return 0
    if svdcut is None:
        return _covariance_sample_rank_from_eigensystem(eigensystem)
    resolved_svdcut = _validate_svdcut(svdcut)
    if resolved_svdcut == 0.0:
        return _covariance_sample_rank_from_eigensystem(eigensystem)
    if resolved_svdcut > 0.0:
        # gvar/lsqfit raises small correlation modes for a positive cut.
        return int(np.count_nonzero(active))
    cutoff = abs(resolved_svdcut) * max(float(eigval[-1]), 0.0)
    # gvar retains a mode exactly on a negative-cut boundary.
    return int(np.count_nonzero(eigval >= cutoff))


def _prepare_jacobian_metric(
    eigensystem,
    svdcut: Union[float, str, None],
) -> _JacobianMetric:
    """Precompute the covariance whitening metric used by rank checks."""
    matrix, active, eigval, eigvec, std = eigensystem
    resolved_svdcut = _validate_svdcut(svdcut)
    if eigval.size == 0:
        retained = np.empty(0, dtype=bool)
        denominators = np.empty(0, dtype=np.float64)
    elif resolved_svdcut is None or resolved_svdcut == 0.0:
        largest = max(float(eigval[-1]), 0.0)
        tolerance = largest * eigval.size * np.finfo(np.float64).eps
        retained = eigval > tolerance
        denominators = eigval[retained]
    elif resolved_svdcut > 0.0:
        largest = max(float(eigval[-1]), 0.0)
        cutoff = resolved_svdcut * largest
        retained = np.ones(eigval.shape, dtype=bool)
        denominators = np.maximum(eigval, cutoff)
    else:
        largest = max(float(eigval[-1]), 0.0)
        cutoff = abs(resolved_svdcut) * largest
        retained = eigval >= cutoff
        denominators = eigval[retained]

    if np.any(denominators <= 0.0):
        raise np.linalg.LinAlgError(
            "regulated covariance is singular while whitening model Jacobian"
        )
    return _JacobianMetric(
        matrix=matrix,
        active=active,
        eigval=eigval,
        eigvec=eigvec,
        std=std,
        retained=retained,
        denominators=denominators,
    )


def covariance_effective_rank(
    cov: np.ndarray,
    svdcut: Union[float, str, None] = None,
) -> int:
    """返回与当前 ``gvar/lsqfit`` SVD 语义一致的数据自由度。

    正 ``svdcut`` 在相关矩阵上抬升小本征值，不删除模；负值才删除
    小模。``"auto"`` 解析为 ``1e-12``；``None`` 严格不调节，返回
    原始样本协方差信息秩。
    """
    eigensystem = _correlation_eigensystem(cov)
    return _covariance_effective_rank_from_eigensystem(eigensystem, svdcut)


def covariance_sample_rank(cov: np.ndarray) -> int:
    """返回 SVD 调节前、按相关矩阵尺度计算的样本信息秩。"""
    eigensystem = _correlation_eigensystem(cov)
    return _covariance_sample_rank_from_eigensystem(eigensystem)


def fit_identifiability(
    n_data: int,
    n_params: int,
    effective_rank: int,
    sample_rank: Optional[int] = None,
    has_prior: bool = False,
) -> Tuple[bool, str]:
    """统一判断相关拟合是否可执行，并返回数据可辨识状态说明。

    返回布尔值保持既有“是否允许进入拟合”语义。prior 可以约束原本由
    数据无法确定的方向，因此 prior 分支允许拟合，但明确标记为
    ``prior_constrained``，不能据此宣称数据本身可辨识。
    """
    if n_data <= 0 or effective_rank <= 0:
        return False, "fit has no data degrees of freedom"
    if sample_rank is not None and sample_rank <= 0:
        return False, "sample covariance has no fluctuating mode"
    if has_prior:
        return True, "prior_constrained: data identifiability not established"
    if n_data <= n_params:
        return False, f"Ndata={n_data} must exceed Nparam={n_params}"
    if effective_rank <= n_params:
        return (
            False,
            f"fit data dof={effective_rank} must exceed Nparam={n_params}",
        )
    if sample_rank is not None and sample_rank < n_params:
        return (
            False,
            f"sample covariance rank={sample_rank} is below "
            f"Nparam={n_params}",
        )
    return True, "identifiable"


def calc_chi2(y_data: np.ndarray, y_fit: np.ndarray, cov: np.ndarray,
              svdcut: Union[float, str, None] = None) -> float:
    """``diff† C^-1 diff``，使用 Hermitian 与 lsqfit SVD 语义。"""
    data = np.asarray(y_data)
    fitted = np.asarray(y_fit)
    if data.shape != fitted.shape:
        raise ValueError("y_data and y_fit must have the same shape")
    with np.errstate(invalid="ignore", over="ignore"):
        diff = (data - fitted).reshape(-1)
    try:
        residual_is_finite = np.isfinite(diff).all()
    except TypeError as error:
        raise ValueError(
            "calc_chi2 residual must contain only finite numeric values"
        ) from error
    if not residual_is_finite:
        raise ValueError("calc_chi2 residual must contain only finite values")
    matrix, active, eigval, eigvec, std = _correlation_eigensystem(cov)
    if matrix.shape != (diff.size, diff.size):
        raise ValueError("cov shape must match flattened data size")

    if svdcut is None:
        if np.min(np.linalg.eigvalsh(matrix), initial=np.inf) <= 0.0:
            raise np.linalg.LinAlgError(
                "svdcut=None requires a strictly positive definite covariance"
            )
        chi2 = diff.conj() @ np.linalg.solve(matrix, diff)
    else:
        svdcut = _validate_svdcut(svdcut)
        if not np.all(active):
            raise ValueError("calc_chi2 requires positive covariance diagonal")
        transformed = eigvec.conj().T @ (diff / std)
        cutoff = abs(svdcut) * max(float(eigval[-1]), 0.0)
        if svdcut >= 0.0:
            regulated = np.maximum(eigval, cutoff)
            if np.any(regulated <= 0.0):
                raise np.linalg.LinAlgError("regulated covariance is singular")
            chi2 = np.sum(np.abs(transformed) ** 2 / regulated)
        else:
            retained = eigval >= cutoff
            chi2 = np.sum(np.abs(transformed[retained]) ** 2 / eigval[retained])

    chi2 = np.real_if_close(chi2)
    if np.iscomplexobj(chi2):
        raise ValueError("Hermitian chi2 has a non-negligible imaginary part")
    return float(chi2)


def calc_chi2_dof(y_data: np.ndarray, y_fit: np.ndarray, cov: np.ndarray,
                  n_params: int,
                  svdcut: Union[float, str, None] = None):
    """按调节后 covariance 有效秩计算 ``chi2/dof``。"""
    dof = covariance_effective_rank(cov, svdcut) - n_params
    if dof <= 0:
        raise ValueError("calc_chi2_dof requires positive effective dof")
    chi2 = calc_chi2(y_data, y_fit, cov, svdcut)
    return chi2 / dof, chi2, dof


def _require_finite_array(name: str, values) -> np.ndarray:
    """Return ``values`` as an array or reject non-numeric/non-finite input."""
    array = np.asarray(values)
    try:
        finite = np.isfinite(array).all()
    except TypeError as error:
        raise ValueError(
            f"{name} must contain only finite numeric values"
        ) from error
    if not finite:
        raise ValueError(f"{name} must contain only finite values")
    return array


def _evaluate_finite_model(
    model: Callable,
    x_coor,
    parameters: dict,
    n_data: int,
) -> np.ndarray:
    """Evaluate a numeric model and enforce the fit vector contract."""
    output = _require_finite_array(
        "model output", model(x_coor, parameters))
    if output.shape != (n_data,):
        raise ValueError(
            "model output size/shape must match the number of y_coor data points"
        )
    return output


def _whiten_model_jacobian(
    jacobian: np.ndarray,
    cov: np.ndarray,
    svdcut: Union[float, str, None],
    metric: Optional[_JacobianMetric] = None,
) -> np.ndarray:
    """Apply the same Hermitian correlation-mode metric used by ``lsqfit``."""
    if metric is None:
        metric = _prepare_jacobian_metric(
            _correlation_eigensystem(cov), svdcut)
    if jacobian.shape[0] != metric.matrix.shape[0]:
        raise ValueError("model Jacobian row count must match covariance size")
    if not np.any(metric.active):
        return np.empty((0, jacobian.shape[1]), dtype=jacobian.dtype)

    projected = metric.eigvec.conj().T @ (
        jacobian[metric.active] / metric.std[:, None])
    if metric.denominators.size == 0:
        return np.empty((0, jacobian.shape[1]), dtype=jacobian.dtype)
    return projected[metric.retained] / np.sqrt(metric.denominators)[:, None]


def _relative_column_change(first: np.ndarray, second: np.ndarray) -> float:
    """Return a scale-free change metric for two derivative estimates."""
    numerator = np.linalg.norm(second - first)
    denominator = max(
        np.linalg.norm(first), np.linalg.norm(second),
        np.finfo(np.float64).tiny,
    )
    return float(numerator / denominator)


@dataclass(frozen=True)
class _FiniteDifferenceProbe:
    """One real-parameter finite-difference probe at a given step."""

    h: float
    forward: np.ndarray
    backward: np.ndarray
    central: np.ndarray


def _real_parameter_scalar(parameters: dict, name: str) -> float:
    """Validate and return one scalar parameter as a real number."""
    value_array = _require_finite_array(
        f"fit parameter {name}", parameters[name])
    if value_array.size != 1:
        raise ValueError(f"fit parameter {name} must be a scalar")
    value = value_array.reshape(-1)[0]
    if np.iscomplexobj(value):
        if abs(float(np.imag(value))) > 0.0:
            raise ValueError(
                f"fit parameter {name} must be real for numerical Jacobian"
            )
        value = np.real(value)
    value = float(value)
    if not np.isfinite(value):
        raise ValueError(f"fit parameter {name} must contain only finite values")
    return value


def _finite_difference_probe(
    model: Callable,
    x_coor,
    parameters: dict,
    name: str,
    n_data: int,
    value: float,
    h: float,
    base_output: np.ndarray,
) -> Optional[_FiniteDifferenceProbe]:
    """Evaluate both real one-sided perturbations and their three estimates."""
    with np.errstate(over="ignore", invalid="ignore"):
        plus_value = value + h
        minus_value = value - h
    if not np.isfinite(plus_value) or not np.isfinite(minus_value):
        return None

    plus_parameters = dict(parameters)
    minus_parameters = dict(parameters)
    plus_parameters[name] = plus_value
    minus_parameters[name] = minus_value

    # Validation errors from either perturbed evaluation deliberately escape.
    forward_output = _evaluate_finite_model(
        model, x_coor, plus_parameters, n_data)
    backward_output = _evaluate_finite_model(
        model, x_coor, minus_parameters, n_data)
    plus_response = forward_output - base_output
    minus_response = base_output - backward_output
    if (not np.any(np.abs(plus_response) > 0.0)
            and not np.any(np.abs(minus_response) > 0.0)):
        return None

    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        forward = plus_response / h
        backward = minus_response / h
        central = (forward_output - backward_output) / (2.0 * h)
    if (not np.isfinite(forward).all()
            or not np.isfinite(backward).all()
            or not np.isfinite(central).all()):
        return None
    return _FiniteDifferenceProbe(h, forward, backward, central)


def _probe_scale_norm(probe: _FiniteDifferenceProbe) -> float:
    """Magnitude used to recognize derivatives converging to a stationary point."""
    return max(
        float(np.linalg.norm(probe.forward)),
        float(np.linalg.norm(probe.backward)),
        float(np.linalg.norm(probe.central)),
    )


def _looks_like_stationary_point(probes: List[_FiniteDifferenceProbe]) -> bool:
    """Recognize O(h**q), q>0, one-sided residues rather than a tangent."""
    if len(probes) < 3:
        return False
    candidate = probes[:min(5, len(probes))]
    norms = np.asarray([_probe_scale_norm(probe) for probe in candidate])
    steps = np.asarray([probe.h for probe in candidate])
    if np.any(norms <= np.finfo(np.float64).tiny):
        return False
    with np.errstate(divide="ignore", invalid="ignore"):
        slopes = np.diff(np.log(norms)) / np.diff(np.log(steps))
    if not np.isfinite(slopes).all():
        return False
    # A smooth stationary point has a positive power of h; a kink has a
    # nonzero O(h**0) one-sided limit.  The lower bound also excludes noisy
    # flat estimates from being called stationary.
    return bool(np.all(slopes >= 0.5) and np.median(slopes) <= 8.0)


def _has_far_parameter_response(
    model: Callable,
    x_coor,
    parameters: dict,
    name: str,
    n_data: int,
    value: float,
    base_output: np.ndarray,
) -> bool:
    """Separate an exactly independent parameter from an unresolved column.

    The local ladder is the only source of a derivative.  If it has no
    response, a wide, non-derivative dependency probe is used: an exactly
    independent parameter remains unchanged, while a real-only tiny column
    eventually changes the rounded output.  A response here is evidence for
    ``numerically indeterminate``, never a derivative estimate.
    """
    def dependency_output(candidate_parameters):
        """Evaluate a non-derivative probe without promoting overflow.

        Local finite-difference evaluations remain strict.  These wide
        probes only distinguish a rounded-away response from an exactly zero
        local column, so a non-finite value outside the finite model domain is
        unusable evidence rather than a fit-input failure.  Shape and type
        violations still propagate.
        """
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            output = np.asarray(model(x_coor, candidate_parameters))
        if output.shape != (n_data,):
            raise ValueError(
                "model output size/shape must match the number of "
                "y_coor data points"
            )
        try:
            finite = np.isfinite(output).all()
        except TypeError as error:
            raise ValueError(
                "model output must contain only finite numeric values"
            ) from error
        return output if finite else None

    scale = max(1.0, abs(value))
    for exponent in (0, 8, 16, 24, 32, 40, JACOBIAN_DIAGNOSTIC_EXPONENT):
        with np.errstate(over="ignore", invalid="ignore"):
            h = scale * (2.0 ** exponent)
            plus_value = value + h
            minus_value = value - h
        if (not np.isfinite(h) or not np.isfinite(plus_value)
                or not np.isfinite(minus_value)):
            continue
        plus_parameters = dict(parameters)
        minus_parameters = dict(parameters)
        plus_parameters[name] = plus_value
        minus_parameters[name] = minus_value
        plus_output = dependency_output(plus_parameters)
        minus_output = dependency_output(minus_parameters)
        if ((plus_output is not None
             and np.any(np.abs(plus_output - base_output) > 0.0))
                or (minus_output is not None
                    and np.any(np.abs(base_output - minus_output) > 0.0))):
            return True
    return False


def _finite_difference_column(
    model: Callable,
    x_coor,
    parameters: dict,
    name: str,
    n_data: int,
    base_output: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Estimate a real-parameter column with multi-scale one-sided checks."""
    value = _real_parameter_scalar(parameters, name)
    if base_output is None:
        base_output = _evaluate_finite_model(model, x_coor, parameters, n_data)
    base_step = JACOBIAN_RELATIVE_STEP * max(1.0, float(abs(value)))

    probes: List[_FiniteDifferenceProbe] = []
    stable_candidates = []
    for exponent in range(
            JACOBIAN_LOCAL_MIN_EXPONENT,
            JACOBIAN_LOCAL_MAX_EXPONENT + 1):
        h = base_step * (2.0 ** exponent)
        probe = _finite_difference_probe(
            model, x_coor, parameters, name, n_data, value, h, base_output)
        if probe is None:
            continue
        probes.append(probe)
        if len(probes) < 2:
            continue
        previous, current = probes[-2:]
        previous_side = _relative_column_change(
            previous.forward, previous.backward)
        current_side = _relative_column_change(
            current.forward, current.backward)
        if (previous_side <= JACOBIAN_SIDE_RTOL
                and current_side <= JACOBIAN_SIDE_RTOL
                and _relative_column_change(
                    previous.central, current.central)
                <= JACOBIAN_STABILITY_RTOL):
            stability = _relative_column_change(
                previous.central, current.central)
            stable_candidates.append((
                max(previous_side, current_side, stability),
                current.central,
            ))

    if stable_candidates:
        # The first acceptable pair can sit in the cancellation-dominated
        # tiny-step regime.  Select the best balance over the full ladder;
        # curvature makes large-step side errors grow, while roundoff makes
        # overly small-step estimates noisy.
        return min(stable_candidates, key=lambda item: item[0])[1]

    if _looks_like_stationary_point(probes):
        return np.zeros(
            n_data, dtype=np.result_type(base_output.dtype, np.float64))

    if (len(probes) >= 3
            and all(
                _relative_column_change(
                    probe.forward, probe.backward) > JACOBIAN_SIDE_RTOL
                for probe in probes[:min(4, len(probes))]
            )):
        raise ValueError(
            f"model is nondifferentiable at parameter {name}: "
            "left/right finite differences disagree (kink)"
        )

    if probes:
        raise ValueError(
            f"model Jacobian column for parameter {name} is "
            "numerically indeterminate: no stable real finite-difference "
            "derivative was resolved"
        )
    far_response = _has_far_parameter_response(
        model, x_coor, parameters, name, n_data, value, base_output)
    detail = (
        "response is below the local floating-point resolution"
        if far_response else
        "no finite black-box probe can prove an exactly zero local column"
    )
    raise ValueError(
        f"model Jacobian column for parameter {name} is "
        f"numerically indeterminate: {detail}; provide an analytic Jacobian"
    )


def _jacobian_matrix_rank(
    jacobian: np.ndarray,
    cov: np.ndarray,
    svdcut: Union[float, str, None],
    metric: Optional[_JacobianMetric] = None,
) -> int:
    """Rank of one validated real-parameter Jacobian in the fit metric."""
    whitened = _whiten_model_jacobian(
        jacobian, cov, svdcut, metric=metric)
    if whitened.shape[0] == 0:
        return 0

    column_norm = np.linalg.norm(whitened, axis=0)
    scaled = np.zeros_like(whitened)
    nonzero = column_norm > np.finfo(np.float64).tiny
    scaled[:, nonzero] = whitened[:, nonzero] / column_norm[nonzero]

    # Parameters are real even when the Hermitian data metric is complex.
    rank_matrix = np.vstack((scaled.real, scaled.imag))
    singular_values = np.linalg.svd(rank_matrix, compute_uv=False)
    if singular_values.size == 0:
        return 0
    tolerance = (
        singular_values[0]
        * max(rank_matrix.shape)
        * JACOBIAN_RANK_RTOL
    )
    return int(np.count_nonzero(singular_values > tolerance))


def _numerical_model_jacobian_rank(
    model: Callable,
    x_coor,
    parameters: dict,
    param_names: List[str],
    cov: np.ndarray,
    svdcut: Union[float, str, None],
    n_data: int,
    metric: Optional[_JacobianMetric] = None,
) -> int:
    """Rank of the covariance-whitened, column-scaled local model Jacobian.

    Parameters are always perturbed as real variables.  The derivative probe
    checks both one-sided estimates and a central estimate over a multi-scale
    local ladder.  A symmetric ``b**3`` residue at ``b=0`` therefore tends to
    zero as ``h**2`` and is not promoted to an identifiable tangent direction.
    ``metric`` is optional so existing direct callers keep the old signature;
    ``fit`` supplies the precomputed covariance metric for every sample.
    """
    columns = []
    base_output = _evaluate_finite_model(model, x_coor, parameters, n_data)
    for name in param_names:
        derivative = _finite_difference_column(
            model, x_coor, parameters, name, n_data, base_output)
        columns.append(_require_finite_array("model Jacobian", derivative))

    if not columns:
        return 0
    jacobian = np.column_stack(columns)
    return _jacobian_matrix_rank(
        jacobian, cov, svdcut, metric=metric)


def _model_jacobian_rank(
    model: Callable,
    x_coor,
    parameters: dict,
    param_names: List[str],
    cov: np.ndarray,
    svdcut: Union[float, str, None],
    n_data: int,
    jacobian: Optional[Callable] = None,
    metric: Optional[_JacobianMetric] = None,
) -> int:
    """Return local rank from an exact Jacobian or conservative differences.

    ``jacobian`` receives ``(x_coor, parameters)`` and returns either a
    ``{parameter: (Ndata,)}`` mapping or an ``(Ndata, Nparam)`` matrix whose
    columns follow ``param_names``.  Without it, a black-box column that
    produces no finite response is reported as numerically indeterminate
    rather than silently classified as zero.
    """
    if jacobian is None:
        return _numerical_model_jacobian_rank(
            model,
            x_coor,
            parameters,
            param_names,
            cov,
            svdcut,
            n_data,
            metric=metric,
        )

    _evaluate_finite_model(model, x_coor, parameters, n_data)
    for name in param_names:
        _real_parameter_scalar(parameters, name)
    raw_jacobian = jacobian(x_coor, parameters)
    if isinstance(raw_jacobian, Mapping):
        if set(raw_jacobian) != set(param_names):
            raise ValueError(
                "analytic model Jacobian mapping keys must match fit parameters"
            )
        columns = []
        for name in param_names:
            column = _require_finite_array(
                f"analytic model Jacobian column {name}",
                raw_jacobian[name],
            )
            if column.shape != (n_data,):
                raise ValueError(
                    "analytic model Jacobian mapping columns must each have "
                    f"shape ({n_data},)"
                )
            columns.append(column)
        matrix = np.column_stack(columns)
    else:
        matrix = _require_finite_array(
            "analytic model Jacobian", raw_jacobian)
    expected_shape = (n_data, len(param_names))
    if matrix.shape != expected_shape:
        raise ValueError(
            "analytic model Jacobian shape must be "
            f"{expected_shape}, got {matrix.shape}"
        )
    return _jacobian_matrix_rank(
        matrix, cov, svdcut, metric=metric)


def fit(
    y_coor: np.ndarray,
    x_coor,
    model: Callable,
    fitpa: FitParams,
    jackknife: bool = False,
    debug: bool = False,
    debugNfit: Optional[int] = 20,
):
    """对每个样本做 lsqfit 非线性拟合。

    Parameters
    ----------
    y_coor : (Nsample, Ndata) 数据数组。
    x_coor : 拟合点坐标（传给 lsqfit 的 data）。
    model : model(x, p) -> np.ndarray。
    fitpa : FitParams；prior 非空时优先使用 prior，否则退化为 p0。
    jackknife : 协方差是否用 jackknife 公式。
    debug : 只拟合前 debugNfit 个样本（协方差仍用全部样本），
            未拟合条目填 NaN，返回数组恒为 Nsample 大小。

    Returns
    -------
    (fit_result, cov, cond, last_fit_info)
        fit_result: {参数名: (Nsample,), "chi2": (Nsample,)}；
        cov: 协方差矩阵；cond: 条件数；last_fit_info: 最后一个样本的 lsqfit 对象。
        该对象附加 ``pyqcd_fit_status`` 与 ``pyqcd_data_identifiable``，
        不改变既有四元返回解包。若 ``Ndata <= Nparam``、截断后的
        covariance 有效秩不足，或无 prior 解处的白化模型 Jacobian
        秩不足，对应结果保持 NaN；没有任何可辨识解时
        ``last_fit_info`` 为 None。
    """
    import gvar as gv
    import lsqfit

    y_coor = np.asarray(y_coor)
    if y_coor.ndim != 2:
        raise ValueError("y_coor must be a two-dimensional sample matrix")
    Nsample, Ndata = y_coor.shape
    if Nsample == 0:
        raise ValueError("y_coor must contain at least one sample")
    y_coor = _require_finite_array("y_coor", y_coor)
    if np.iscomplexobj(y_coor):
        raise ValueError(
            "complex y_coor is not supported; explicitly stack real/imag "
            "components with a matching covariance"
        )
    _require_finite_array("x_coor", x_coor)

    use_prior = fitpa.prior is not None and len(fitpa.prior) > 0
    param_names = list(fitpa.p0.keys())
    if use_prior and set(fitpa.prior.keys()) != set(param_names):
        raise ValueError("prior and p0 must have the same parameter keys")
    n_params = len(param_names)
    _evaluate_finite_model(model, x_coor, fitpa.p0, Ndata)

    Nfit = min(debugNfit, Nsample) if debug else Nsample

    fit_result = {name: np.full(Nsample, np.nan) for name in param_names}
    fit_result["chi2"] = np.full(Nsample, np.nan)

    cov, cond = cov_mat(y_coor, jackknife=jackknife)
    resolved_svdcut = _validate_svdcut(fitpa.svdcut)
    covariance_eigensystem = _correlation_eigensystem(cov)
    effective_rank = _covariance_effective_rank_from_eigensystem(
        covariance_eigensystem, resolved_svdcut)
    sample_rank = _covariance_sample_rank_from_eigensystem(
        covariance_eigensystem)
    identifiable, _ = fit_identifiability(
        y_coor.shape[1], n_params, effective_rank,
        sample_rank=sample_rank, has_prior=use_prior)
    if not identifiable:
        return fit_result, cov, cond, None
    if resolved_svdcut is None and sample_rank < y_coor.shape[1]:
        raise ValueError(
            "svdcut=None disables SVD regulation but encountered a singular covariance; "
            "use svdcut='auto' or an explicit nonzero cut")
    jacobian_metric = _prepare_jacobian_metric(
        covariance_eigensystem, resolved_svdcut)

    last_fit_info = None
    for _id in range(Nfit):
        y_gvar = gv.gvar(y_coor[_id], cov)
        if use_prior:
            _fit = lsqfit.nonlinear_fit(
                data=(x_coor, y_gvar), prior=fitpa.prior,
                fcn=model, svdcut=resolved_svdcut)
        else:
            _fit = lsqfit.nonlinear_fit(
                data=(x_coor, y_gvar), p0=fitpa.p0,
                fcn=model, svdcut=resolved_svdcut)

        parameter_values = {}
        for name in param_names:
            value = _require_finite_array(
                f"fit parameter {name}", _fit.pmean[name])
            if value.size != 1:
                raise ValueError(f"fit parameter {name} must be a scalar")
            parameter_values[name] = value.reshape(-1)[0]

        fitted = _evaluate_finite_model(
            model, x_coor, parameter_values, Ndata)
        with np.errstate(invalid="ignore", over="ignore"):
            residual = y_coor[_id].reshape(-1) - fitted
        _require_finite_array("fit residual", residual)

        if not use_prior:
            model_rank = _model_jacobian_rank(
                model,
                x_coor,
                parameter_values,
                param_names,
                cov,
                resolved_svdcut,
                Ndata,
                jacobian=fitpa.jacobian,
                metric=jacobian_metric,
            )
            if model_rank < n_params:
                continue
            _fit.pyqcd_fit_status = "identifiable"
            _fit.pyqcd_data_identifiable = True
        else:
            _fit.pyqcd_fit_status = "prior_constrained"
            _fit.pyqcd_data_identifiable = None

        dof = _require_finite_array("fit dof", _fit.dof).reshape(-1)[0]
        if dof <= 0:
            raise ValueError("fit dof must be positive")
        chi2_dof = _fit.chi2 / dof
        _require_finite_array("fit chi2/dof", chi2_dof)

        for name in param_names:
            fit_result[name][_id] = parameter_values[name]
        fit_result["chi2"][_id] = chi2_dof
        last_fit_info = _fit

    return fit_result, cov, cond, last_fit_info


def make_summary_table(field_names: List[str], rows: List[List[str]],
                       align: Optional[Dict[str, str]] = None) -> str:
    """ASCII 对齐表格（PrettyTable 风格，无外部依赖）。

    Parameters
    ----------
    field_names : 列名列表。
    rows : 每行各列字符串。
    align : {列名: 'l'|'c'|'r'}，缺省居中。
    """
    n_cols = len(field_names)
    colw = [len(str(f)) for f in field_names]
    for r in rows:
        for i in range(n_cols):
            colw[i] = max(colw[i], len(str(r[i])))

    def _fmt(cell, w, a):
        cell = str(cell)
        if a == "l":
            return cell.ljust(w)
        if a == "r":
            return cell.rjust(w)
        return cell.center(w)

    align = align or {}
    border = "+" + "+".join("-" * (w + 2) for w in colw) + "+"
    head = "|" + "|".join(" " + _fmt(f, w, "c") + " "
                          for f, w in zip(field_names, colw)) + "|"
    lines = [border, head, border]
    for r in rows:
        line = "|" + "|".join(" " + _fmt(v, w, align.get(field_names[i], "c")) + " "
                              for i, (v, w) in enumerate(zip(r, colw))) + "|"
        lines.append(line)
    lines.append(border)
    return "\n".join(lines)


def fit_report_lines(title: str, header: Dict[str, object], sep: str = "=" * 72) -> List[str]:
    """拟合报告头部（分隔线 + 标题 + 关键设置）。"""
    lines = [sep, f"  {title}", sep]
    for k, v in header.items():
        lines.append(f"  {k:14s}: {v}")
    lines.append(sep)
    lines.append("")
    return lines
