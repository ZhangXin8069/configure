"""
连续极限 / 物理点联合外推（移植 zengch fit_pz_a_extrapolatiing.py 核心逻辑）。

逐 x 联合外推 ansatz：
    f(x; a, Pz, mπ, L) = xg₀(x) + a²·f(x) + a⁴·l(x) + a²Pz²·h(x)
                         + d(x)/Pz² + b(x)/Pz + k(x)·(mπ² − mπ,phy²)
                         + c(x)·e^{−L·a·mπ}
"""
from __future__ import annotations

import numpy as np

from ._ensembles import a_len_set, Nl_set, pion_mass_set, MPI_PHYSICAL


def _validate_extrap_rows(rows, *, bootstrap):
    """Validate ensemble rows before any design or linear-algebra operation."""
    if not isinstance(rows, (list, tuple)) or len(rows) == 0:
        raise ValueError("rows 必须是非空系综数据列表")
    replica_count = None
    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"row {row_index} 必须是 dict")
        missing = [name for name in ('x', 'hR', 'a', 'pz', 'mpi', 'L')
                   if name not in row]
        if missing:
            raise ValueError(f"row {row_index} 缺少字段 {missing}")
        x_values = np.asarray(row['x'], dtype=float)
        if x_values.ndim != 1 or x_values.size == 0 \
                or not np.isfinite(x_values).all():
            raise ValueError(f"row {row_index} x 必须是一维有限非空数组")
        hR = np.asarray(row['hR'])
        valid_ndim = hR.ndim in ((1, 2) if bootstrap else (1,))
        if not valid_ndim or hR.shape[0] != x_values.size:
            shape = '(nx, n_rep)' if bootstrap else '(nx,)'
            raise ValueError(f"row {row_index} hR 必须为 {shape} 且匹配 x")
        if hR.size == 0 or not np.isfinite(hR).all():
            raise ValueError(f"row {row_index} hR 必须全部有限")
        if bootstrap:
            n_rep = hR.shape[1] if hR.ndim == 2 else 1
            if n_rep == 0:
                raise ValueError(f"row {row_index} replica 轴不得为空")
            if replica_count is None:
                replica_count = n_rep
            elif n_rep != replica_count:
                raise ValueError(
                    f"row {row_index} replica 数 {n_rep} 与 "
                    f"首行 {replica_count} 不一致")
        for name in ('a', 'pz', 'mpi', 'L'):
            value = row[name]
            if (isinstance(value, (bool, np.bool_))
                    or not np.isscalar(value)
                    or not np.isfinite(value)):
                raise ValueError(f"row {row_index} {name} 必须是有限实标量")
        if float(row['pz']) == 0.0:
            raise ValueError(f"row {row_index} pz 不得为零")


def hR_form(var, par):
    """外推形式（在固定 x 处对 a, Pz, mπ, L 做线性拟合）。

    Args:
        var: (a_, pz_, mpi, L_)——格距(GeV⁻¹)、Pz(格点单位)、mπ(GeV)、L(格点)
        par: (xg0, fx, lx, hx, dx, bx, kx, cx) 8 个拟合系数
    """
    a_, pz_, mpi, L_ = var
    xg0_, fx_, lx_, hx_, dx_, bx_, kx_, cx_ = par
    return (xg0_
            + a_ ** 2 * fx_ + a_ ** 4 * lx_
            + a_ ** 2 * pz_ ** 2 * hx_
            + dx_ / pz_ ** 2 + bx_ / pz_
            + kx_ * (mpi ** 2 - MPI_PHYSICAL ** 2)
            + cx_ * np.exp(-L_ * a_ * mpi))


def build_fit_data(conf_set, note_name_set, pz_set, loader):
    """收集多系综数据（x, hR_PDF, a, Pz_GeV, mπ, L）。

    Args:
        conf_set: 系综名列表
        note_name_set: 数据备注名列表（与 conf_set 对齐）
        pz_set: 每系综的 Pz 列表
        loader: 回调 conf, note_name, pz → (xx, hR_PDF, a_GeV⁻¹, Pz_GeV, mπ_GeV, Nl)
    Returns:
        list of dict(x=..., hR=..., a=..., pz=..., mpi=..., L=...)
    """
    rows = []
    for conf, note, pz_list in zip(conf_set, note_name_set, pz_set):
        for pz in pz_list:
            xx, hR, a_len, pz_gev, mpi, nl = loader(conf, note, pz)
            if xx is None:
                continue
            rows.append(dict(x=xx, hR=hR, a=a_len, pz=pz_gev,
                             mpi=mpi, L=nl))
    return rows


def fit_hR_PDF_extrap(rows, x_grid=None, fitter='lm', max_x=1.0):
    """逐 x 拟合外推参数（8 参数线性拟合，scipy.linalg.lstsq）。

    Args:
        rows: build_fit_data 的输出
        x_grid: 目标 x 网格（默认取所有数据公共 x 网格）
    Returns:
        (x_grid, xg0(x), 外推误差带 std(x))。
    """
    _validate_extrap_rows(rows, bootstrap=False)
    if x_grid is None:
        x_grid = rows[0]['x']
    x_grid = np.asarray(x_grid, dtype=float)
    if x_grid.ndim != 1 or not np.isfinite(x_grid).all():
        raise ValueError("x_grid 必须是一维有限数组")
    mask_x = (x_grid >= 0) & (x_grid <= max_x)
    x_grid = x_grid[mask_x]

    xg0 = np.zeros_like(x_grid)
    xg0_std = np.zeros_like(x_grid)

    for i, x_val in enumerate(x_grid):
        A_rows, b_vec = [], []
        for r in rows:
            idx = np.where(np.abs(r['x'] - x_val) < 1e-4)[0]
            if len(idx) == 0:
                continue
            j = idx[0]
            hR_val = np.atleast_1d(r['hR'])[j]
            var = (r['a'], r['pz'], r['mpi'], r['L'])
            A_rows.append(_extrap_design_row(*var))
            b_vec.append(hR_val)

        A = np.asarray(A_rows, dtype=float).reshape(-1, len(_EXTRAP_PAR_NAMES))
        _require_extrap_identifiable(
            A, len(_EXTRAP_PAR_NAMES), x_val, "fit_hR_PDF_extrap")
        b = np.array(b_vec)
        coef, *_ = np.linalg.lstsq(A, b, rcond=None)
        resid = b - A @ coef
        dof = max(len(b) - 8, 1)
        chi2 = np.sum(resid ** 2) / dof
        xg0[i] = coef[0]
        xg0_std[i] = np.sqrt(chi2) * np.sqrt(np.linalg.inv(A.T @ A)[0, 0])

    return x_grid, xg0, xg0_std


def _extrap_design_row(a_, pz_, mpi, L_):
    """8 参数线性模型的单个设计行 [1, a², a⁴, a²pz², 1/pz², 1/pz,
    mπ²−mπ,phy², e^{−L·a·mπ}]（与 hR_form 逐项对应）。"""
    return np.array([
        1.0,
        a_ ** 2, a_ ** 4, a_ ** 2 * pz_ ** 2,
        pz_ ** -2, pz_ ** -1,
        mpi ** 2 - MPI_PHYSICAL ** 2,
        np.exp(-L_ * a_ * mpi),
    ])


_EXTRAP_PAR_NAMES = ('xg0', 'fx', 'lx', 'hx', 'dx', 'bx', 'kx', 'cx')
_EXTRAP_FREE_IDX = (0, 1, 4, 6)   # 原版 Minuit fixed lx/hx/bx/cx → 仅 xg0/fx/dx/kx 自由


def _require_extrap_identifiable(A, n_params, x_val, fit_name):
    """Reject a rank-deficient or exactly determined extrapolation design."""
    n_data = A.shape[0]
    design_rank = int(np.linalg.matrix_rank(A))
    data_dof = n_data - n_params
    if design_rank < n_params or data_dof <= 0:
        raise ValueError(
            f"{fit_name} statistically unidentifiable at x={x_val:.6g}: "
            f"design rank={design_rank}, required rank={n_params}; "
            f"data dof={data_dof} must be positive "
            f"(Ndata={n_data}, Nparam={n_params})")


def fit_hR_PDF_extrap_boot(rows, x_grid=None, max_x=1.0,
                           return_samples=False):
    """协方差加权 + 逐样本误差带的联合外推拟合
    （照抄 zengch fit_pz_a_extrapolatiing.fit_hR_PDF_extrap 的 boot 路线）。

    与 :func:`fit_hR_PDF_extrap`（无权重 lstsq 全 8 参数、残差 std 误差）
    的三点差异，均忠实原版：
      1. 每个 x 点用全体样本的协方差逆加权（原版 covariance_matrix(·,'boot')
         后取逆；奇异时回退单位阵——原版打印"单位矩阵"但实际保留未逆矩阵，
         此处按其注释意图实现真回退并记录偏离）；
      2. 固定 lx/hx/bx/cx=0，仅 xg0/fx/dx/kx 自由（原版 Minuit fixed 约定）；
         线性模型下闭式 WLS 与 MIGRAD 同一估计量，故用正规方程实现；
      3. 逐样本循环拟合 → 参数与 χ² 样本分布 → xg0(x) 误差带。

    Args:
        rows: build_fit_data 输出；boot 路线要求每行 hR 形状 (nx, n_rep)
            （第 2 维为 bootstrap/jackknife 样本）。
        x_grid: 目标 x 网格（默认数据公共网格，过滤到 [0, max_x]）。
        return_samples: True 时额外返回逐样本 xg0 数组 (n_rep, nx)。
    Returns:
        (x_grid, xg0_mean(nx), xg0_std(nx)[, samples])。
    """
    _validate_extrap_rows(rows, bootstrap=True)
    if x_grid is None:
        x_grid = rows[0]['x']
    x_grid = np.asarray(x_grid, dtype=float)
    if x_grid.ndim != 1 or not np.isfinite(x_grid).all():
        raise ValueError("x_grid 必须是一维有限数组")
    mask_x = (x_grid >= 0) & (x_grid <= max_x)
    x_grid = x_grid[mask_x]

    n_free = len(_EXTRAP_FREE_IDX)

    # 预收集各 x 点的设计矩阵与样本矩阵 b (n_data, n_rep)
    per_x = []
    for i, x_val in enumerate(x_grid):
        A_rows, B_rows = [], []
        for r in rows:
            r_hR = np.asarray(r['hR'], dtype=float)
            idx = np.where(np.abs(r['x'] - x_val) < 1e-4)[0]
            if len(idx) == 0:
                continue
            j = idx[0]
            hR_j = np.atleast_2d(r_hR.T).T if r_hR.ndim == 1 else r_hR
            var = (r['a'], r['pz'], r['mpi'], r['L'])
            A_rows.append(_extrap_design_row(*var))
            B_rows.append(hR_j[j])
        A = np.asarray(A_rows, dtype=float).reshape(
            -1, len(_EXTRAP_PAR_NAMES))
        _require_extrap_identifiable(
            A[:, _EXTRAP_FREE_IDX], n_free, x_val,
            "fit_hR_PDF_extrap_boot")
        per_x.append((A, np.array(B_rows)))

    n_x = len(x_grid)
    used = [pack[1] for pack in per_x if pack is not None]
    n_rep = max((B.shape[1] for B in used), default=0)

    xg0_mean = np.full(n_x, np.nan)
    xg0_std = np.full(n_x, np.nan)
    chi2_mean = np.full(n_x, np.nan)
    samples_out = np.full((n_rep, n_x), np.nan)

    for i, pack in enumerate(per_x):
        if pack is None:
            continue
        A, B = pack
        if B.ndim == 1:
            B = B[:, None]
        b_mean = B.mean(axis=1)

        # 鲁棒加权最小二乘：协方差 Cholesky 白化 + SVD-lstsq
        # （与正规方程 (AfᵀCAf)⁻¹AfᵀCb 同一估计量，但避免显式求逆在
        #   病态条件下的静默失真；白化残差范数² ⇔ ΔᵀC⁻¹Δ）。
        # 协方差非正定（Cholesky 失败）→ 回退单位阵权重（原版注释意图）。
        cov = (np.cov(B, rowvar=True, ddof=1) if B.shape[1] > 1
               else np.eye(A.shape[0]))
        try:
            L = np.linalg.cholesky(cov)
            Aw = np.linalg.solve(L, A[:, _EXTRAP_FREE_IDX])
            Bw = np.linalg.solve(L, B)            # 逐样本列批量白化
            bw = np.linalg.solve(L, b_mean)
        except np.linalg.LinAlgError:
            print(f"[fit_hR_PDF_extrap_boot] x={x_grid[i]:.3f} "
                  "协方差非正定，回退单位阵")
            Aw = A[:, _EXTRAP_FREE_IDX]
            Bw, bw = B, b_mean

        coef_all, *_ = np.linalg.lstsq(Aw, Bw, rcond=None)    # (n_free, n_rep)
        coef_mean, *_ = np.linalg.lstsq(Aw, bw, rcond=None)
        resid = bw - Aw @ coef_mean
        dof = max(A.shape[0] - n_free, 1)
        chi2_mean[i] = float(resid @ resid / dof)
        xg0_mean[i] = float(coef_mean[0])

        samples_out[:B.shape[1], i] = coef_all[0]             # 逐样本 xg0 带
        xg0_std[i] = (float(np.std(samples_out[:B.shape[1], i]))
                      if B.shape[1] > 1 else np.nan)

    if return_samples:
        return x_grid, xg0_mean, xg0_std, samples_out
    return x_grid, xg0_mean, xg0_std
