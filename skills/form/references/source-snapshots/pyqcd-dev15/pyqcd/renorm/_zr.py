"""
自重整化因子 Z_R：全局参数化与拟合（移植 zengch fit_zr_new.py 核心逻辑）。

对应 arXiv:2510.17758 Eq.(3)-(8) 的混合方案自重整化：

    hB(z, Pz=0) 在短距离 (z ≤ z₁) 由 NLO MS-bar 因子 Z_MS 控制；
    长距离 (z > z₁) 由非微扰节点参数 g₁..g₁₄ 描述（th_hB 的分段 B(z)）。

    Z_R(z, a, μ) = exp[ k·z/(a·ln(aΛ)) + ½ln(1 + d/ln(aΛ))²
                       + 5C_A/(3b₀)·ln(ln(1/(aΛ))/ln(μ/Λ))
                       + (m₀ + m₂a²)·z + f·a + f₂·a² ]

其中线性发散项 k·z/a 为梯度流（或 Wilson 线）重整化所需的发散抵消，
对数重求和项对应 MS-bar 窗口。本模块把参数化函数与拟合代价函数做成
纯函数库（不依赖集群数据路径），数据由调用方以 dict 形式传入。
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from ._const import A_s, CA, gammaE, b0
from ._ensembles import fm_to_GeV


_B0_NF3 = b0(3.0)
_MS_BAR_DENOM = 4.0 * np.exp(-2.0 * gammaE)


@dataclass(frozen=True)
class ZRDataset:
    """Z_R 拟合用的单系综数据对象。

    ``loghB_samples`` 保留逐样本矩阵；``loghB``、``cov``、``c_inv`` 是由
    全样本一次性准备出的均值、协方差及其伪逆/对角逆，供全局拟合和
    逐样本重拟合复用。
    """

    z: np.ndarray
    loghB: np.ndarray
    c_inv: np.ndarray
    a: float
    loghB_samples: np.ndarray | None = None
    cov: np.ndarray | None = None
    kind: str = "precomputed"

    @property
    def n_point(self):
        return int(self.z.shape[0])

    @property
    def n_points(self):
        return self.n_point

    @property
    def n_sample(self):
        if self.loghB_samples is None or self.loghB_samples.ndim < 2:
            return 0
        return int(self.loghB_samples.shape[1])

    def __getitem__(self, key):
        return getattr(self, key)

    def as_dict(self, include_cache=False):
        """返回旧接口使用的 dict；默认只给出历史四字段。"""
        data = {
            "z": self.z,
            "loghB": self.loghB,
            "c_inv": self.c_inv,
            "a": self.a,
        }
        if include_cache:
            data.update({
                "loghB_samples": self.loghB_samples,
                "cov": self.cov,
                "kind": self.kind,
            })
        return data

    def to_dict(self, include_cache=False):
        return self.as_dict(include_cache=include_cache)

    def sample_view(self, sample_i):
        """用第 ``sample_i`` 个样本替代均值，复用同一个 ``c_inv``。"""
        if self.loghB_samples is None:
            raise ValueError("ZRDataset 不含 loghB_samples，无法逐样本取视图")
        return ZRDataset(
            z=self.z,
            loghB=self.loghB_samples[:, sample_i],
            c_inv=self.c_inv,
            a=self.a,
            loghB_samples=None,
            cov=self.cov,
            kind=self.kind,
        )


def Z_MS(z_gev, mu):
    """NLO MS-bar 重整化因子（z 单位 GeV⁻¹，μ 单位 GeV）。

    Z_MS = 1 + α_s·C_A/(4π)·[ (5/3)·ln( z²μ² / (4e^{−2γ_E}) ) + 3 ]
    """
    # A_s ≡ α_s/(4π)（zengch 惯例）。
    z_gev = np.asarray(z_gev, dtype=float)
    alpha_s = A_s_run(mu) * CA
    return 1.0 + alpha_s * (
        5.0 / 3.0 * np.log((z_gev ** 2 * mu ** 2) / _MS_BAR_DENOM) + 3.0
    )


def A_s_run(mu, Lambda_QCD=0.23, nf=3.0):
    """α_s/(4π) 1 圈运行耦合（zengch constant.py 的 A_s 语义）。"""
    return A_s(mu, Lambda_QCD, nf)


def th_hB(z_, a_, mu_, par_g_set, f_set, z1_fm=0.301):
    """对数 hB(z) 的理论参数化（Eq.7）：分段——z ≤ z₁ 用 Z_MS + 质量项，
    z > z₁ 用非微扰节点 g₁..g₁₄。

    Args:
        z_:   z 数组（fm）
        a_:   格距（GeV⁻¹）
        mu_:  重整化标度（GeV）
        par_g_set: (k, d, m0, m2, Lambda_QCD, g1..g14)
        f_set: (f1, f2) 离散化修正系数
    Returns:
        log hB，形状与 z_ 相同。
    """
    z_set_new_gev = np.asarray(z_, dtype=float) / fm_to_GeV
    k, d, m0, m2, lambda_qcd, *g_params = par_g_set
    g_params = np.asarray(g_params, dtype=float)
    a_sq = a_ ** 2.0
    f_set_arr = np.asarray(f_set, dtype=float)
    log_a_lambda = np.log(a_ * lambda_qcd)
    log_mu_lambda = np.log(mu_ / lambda_qcd)
    log_inv_a_lambda = -log_a_lambda
    z1_gev = z1_fm / fm_to_GeV
    ms_pref = A_s_run(mu_) * CA
    mu_sq = mu_ ** 2.0

    log_hb = (k * z_set_new_gev) / (a_ * log_a_lambda)
    log_hb += 5.0 * CA / (3.0 * _B0_NF3) * np.log(log_inv_a_lambda / log_mu_lambda)
    log_hb += np.log((1.0 + d / log_a_lambda) ** 2.0) / 2.0
    log_hb += f_set_arr[0] * a_ + f_set_arr[1] * a_sq

    short_mask = z_set_new_gev <= z1_gev
    short_count = int(np.count_nonzero(short_mask))
    if short_count:
        z_short = z_set_new_gev[short_mask]
        log_hb[short_mask] += np.log(1.0 + ms_pref * (
            5.0 / 3.0 * np.log((z_short ** 2 * mu_sq) / _MS_BAR_DENOM) + 3.0
        )) + (m0 + m2 * a_sq) * z_short
    if short_count != z_set_new_gev.size:
        log_hb[~short_mask] += g_params[:z_set_new_gev.size - short_count]
    return log_hb


def th_ZR(z_, a_, mu_, k, d, m0, m2, lambda_qcd, f_set):
    """Z_R 的指数参数化（Eq.5）：exp(线性发散 + 质量平移 + 对数重求和 + 离散化)。

    Args:
        z_:   z 数组（fm）
        a_:   格距（GeV⁻¹）
        mu_:  重整化标度（GeV）
        k, d, m0, m2, lambda_qcd: 拟合参数
        f_set: (f1, f2)
    Returns:
        Z_R(z)，形状与 z_ 相同。
    """
    z_set_new_gev = np.asarray(z_, dtype=float) / fm_to_GeV
    a_sq = a_ ** 2.0
    f_set_arr = np.asarray(f_set, dtype=float)
    log_a_lambda = np.log(a_ * lambda_qcd)
    log_mu_lambda = np.log(mu_ / lambda_qcd)
    log_inv_a_lambda = -log_a_lambda

    log_hb = (k * z_set_new_gev) / (a_ * log_a_lambda)
    log_hb += 5.0 * CA / (3.0 * _B0_NF3) * np.log(log_inv_a_lambda / log_mu_lambda)
    log_hb += np.log((1.0 + d / log_a_lambda) ** 2.0) / 2.0
    log_hb += (m0 + m2 * a_sq) * z_set_new_gev
    if f_set_arr.ndim == 1:
        log_hb += f_set_arr[0] * a_ + f_set_arr[1] * a_sq
    else:
        log_hb += np.sum(f_set_arr * np.array([a_, a_sq])[:, None], axis=0)
    return np.exp(log_hb)


def _cost_function_core(z_set_, hb_data, c_inv, a_, mu_, par_g_set,
                        f_set, z1_fm=0.301):
    data_num = len(z_set_)
    hb_th = th_hB(z_set_, a_, mu_, par_g_set, f_set, z1_fm)
    del_hb = hb_th - np.asarray(hb_data, dtype=float)
    chi2 = del_hb.T @ np.asarray(c_inv, dtype=float) @ del_hb
    return chi2 / data_num


def _cost_function_prepared(z_set_, hb_data, c_inv, a_, mu_, par_g_set,
                            f_set, z1_fm=0.301):
    data_num = len(z_set_)
    hb_th = th_hB(z_set_, a_, mu_, par_g_set, f_set, z1_fm)
    del_hb = hb_th - hb_data
    chi2 = del_hb.T @ c_inv @ del_hb
    return chi2 / data_num


def _cost_function_dataset(dataset, mu_, par_set, z1_fm=0.301):
    par_set = np.asarray(par_set, dtype=float)
    if dataset.loghB.ndim != 1:
        raise ValueError("cost_function 需要单系综一维 loghB")
    return _cost_function_prepared(
        dataset.z, dataset.loghB, dataset.c_inv, dataset.a, mu_,
        par_set[:19], par_set[19:], z1_fm,
    )


def cost_function(z_set_, hb_data=None, c_inv=None, a_=None, mu_=None,
                  par_set=None, z1_fm=0.301):
    """单系综 χ²（平均到每数据点）。

    兼容两种调用：
        1. 旧式数值路径：``cost_function(z, hb_data, c_inv, a, mu, par)``
        2. 新式数据对象：``cost_function(dataset_or_mapping, mu, par)``，
           其中 ``dataset_or_mapping`` 为 ``ZRDataset`` 或旧 mapping。

    Args:
        z_set_: z 数组（fm）
        hb_data: log hB 数据数组
        c_inv: 协方差逆矩阵
        a_: 格距（GeV⁻¹）
        mu_: 重整化标度（GeV）
        par_set: 前 19 个为 (k,d,m0,m2,Λ,g1..g14)，其余为 (f1,f2)
    """
    if isinstance(z_set_, (ZRDataset, Mapping)):
        dataset = _coerce_zr_dataset(z_set_)
        if mu_ is None and par_set is None:
            if hb_data is None or c_inv is None or a_ is not None:
                raise TypeError(
                    "cost_function(dataset, mu_, par_set) 只接受两个尾随参数"
                )
            mu_, par_set = hb_data, c_inv
        elif (par_set is not None and mu_ is None
              and hb_data is not None and c_inv is None and a_ is None):
            mu_ = hb_data
        elif (mu_ is not None and par_set is None
              and hb_data is None and c_inv is not None and a_ is None):
            par_set = c_inv
        elif (mu_ is None or par_set is None
              or hb_data is not None or c_inv is not None or a_ is not None):
            raise TypeError(
                "cost_function(dataset, mu_=..., par_set=...) 不接受数值数组参数"
            )
        return _cost_function_dataset(dataset, mu_, par_set, z1_fm)

    if any(v is None for v in (hb_data, c_inv, a_, mu_, par_set)):
        raise TypeError(
            "cost_function(z_set_, hb_data, c_inv, a_, mu_, par_set) "
            "需要六个数值参数"
        )
    par_set = np.asarray(par_set, dtype=float)
    return _cost_function_core(z_set_, hb_data, c_inv, a_, mu_,
                               par_set[:19], par_set[19:], z1_fm)


def _cost_function_all_prepared(par_set, datasets, mu_):
    par_set = np.asarray(par_set, dtype=float)
    par_g_set = par_set[:19]
    f_set = par_set[19:]
    chi2_sum = 0.0
    n_sum = 0
    for ds in datasets:
        if ds.loghB.ndim != 1:
            raise ValueError("cost_function_all 需要单系综一维 loghB")
        chi2 = _cost_function_prepared(
            ds.z, ds.loghB, ds.c_inv, ds.a, mu_, par_g_set, f_set)
        chi2_sum += chi2 * ds.n_points
        n_sum += ds.n_points
    dof = n_sum - len(par_set)
    return chi2_sum / dof


def cost_function_all(par_set, datasets, mu_):
    """多系综联合 χ²/dof。

    Args:
        par_set: 全部拟合参数（前 19 + f1,f2）
        datasets: [dict(z=..., loghB=..., c_inv=..., a=...), ...]
            或对应的 ``ZRDataset`` 序列/单个对象。
        mu_: 重整化标度（GeV）
    """
    return _cost_function_all_prepared(
        par_set, prepare_zr_datasets(datasets), mu_)


# ═══════════════════════════════════════════════════════════════════
# hB/FH 数据预处理 loader（整合 zengch hB_data_FeynmenHellman_new.py）
# ═══════════════════════════════════════════════════════════════════

def build_hB_dataset(c0_zx, z_fm, z_grid_new=None):
    """ratio c0(z) 数据 → z₀ 归一化 + 线性插值 hB 数据集。

    照抄 zengch hB_data_FeynmenHellman_new.py 的语义（去集群路径依赖）：
        1) hB_o_zn = c0(z) 原始（未归一化）
        2) hB_o    = c0 / c0(z=0)                     （z₀ 归一化）
        3) 线性插值到目标 z 网格 → hB、loghB

    Args:
        c0_zx: (nz, nsample) 或 (nz,)——FH 比值拟合的 c0(z)（逐样本）。
        z_fm:  与 c0_zx 第一维对应的 z 网格（fm）。
        z_grid_new: 目标插值网格（fm）；默认 arange(0.15, 1.05, 0.05)
                    （L48x144 类小体积系综可传至 0.95，同原版约定）。
    Returns:
        dict(z, loghB, hB, z_o, hB_o, hB_o_zn)——形状 (nz_new, nsample)
        或 (nz_new,)（跟随输入维数）。
    """
    from scipy.interpolate import interp1d

    hb_zn = np.atleast_2d(np.asarray(c0_zx, dtype=float))
    if hb_zn.shape[0] == 1 and np.ndim(c0_zx) == 1:
        hb_zn = hb_zn.T                      # (1, nz) 边角：按 (nz,) 处理
    z_o = np.asarray(z_fm, dtype=float)
    if hb_zn.shape[0] != len(z_o):
        raise ValueError(f"c0 首维 {hb_zn.shape[0]} 与 z 网格 {len(z_o)} 不一致")

    hb_o = hb_zn / hb_zn[0:1, :]             # z₀ 归一化
    if z_grid_new is None:
        z_grid_new = np.arange(0.15, 1.0 + 0.05, 0.05)
    interp = interp1d(z_o, hb_o, kind='linear', axis=0,
                      bounds_error=False, fill_value='extrapolate')
    hb_new = interp(np.asarray(z_grid_new, dtype=float))

    squeeze = np.ndim(c0_zx) == 1
    if squeeze:
        hb_new = hb_new[:, 0]
        return {'z': np.asarray(z_grid_new), 'loghB': np.log(hb_new),
                'hB': hb_new, 'z_o': z_o, 'hB_o': hb_o[:, 0],
                'hB_o_zn': hb_zn[:, 0]}
    return {'z': np.asarray(z_grid_new), 'loghB': np.log(hb_new),
            'hB': hb_new, 'z_o': z_o, 'hB_o': hb_o, 'hB_o_zn': hb_zn}


def boot_covariance(samples, n_rep=200, seed=0):
    """自助重采样协方差（照抄 zengch tool.covariance_matrix(·,'boot') 语义）。

    Args:
        samples: (n_point, n_sample)——逐 bootstrap/jackknife 样本。
        n_rep: 重采样次数（对样本轴有放回抽取）。
        seed: 可复现种子。
    Returns:
        (n_point, n_point) 协方差矩阵。
    """
    s = np.asarray(samples, dtype=float)
    rng = np.random.default_rng(seed)
    n_pt, n_sam = s.shape
    idx = rng.integers(0, n_sam, size=(n_rep, n_sam))
    replicates = s[:, idx].mean(axis=1).T          # (n_rep, n_point)
    return np.cov(replicates, rowvar=False)


def _as_loghB_samples(loghB_samples, z_fm):
    """把 loghB 输入规范到 (nz, nsample)，并校验 z 维。"""
    z_ = np.asarray(z_fm, dtype=float)
    s = np.asarray(loghB_samples, dtype=float)
    if z_.ndim != 1:
        raise ValueError("z_fm must be one-dimensional")
    if s.ndim == 1:
        if s.shape[0] != z_.shape[0]:
            raise ValueError(
                f"loghB 长度 {s.shape[0]} 与 z 网格 {z_.shape[0]} 不一致"
            )
        s = s[:, None]
    elif s.ndim == 2:
        if s.shape[0] != z_.shape[0]:
            raise ValueError(
                f"loghB 首维 {s.shape[0]} 与 z 网格 {z_.shape[0]} 不一致"
            )
    else:
        raise ValueError("loghB_samples must be one- or two-dimensional")
    return s, z_


def prepare_zr_dataset(dataset_or_loghB_samples, z_fm=None, a_gev_inv=None,
                       kind='boot', n_rep=200, seed=0):
    """一次性准备 Z_R 数据对象。

    两种调用方式：
    1. ``prepare_zr_dataset(mapping_or_ZRDataset)``：把旧 mapping / 旧输入
       标准化成 :class:`ZRDataset`；
    2. ``prepare_zr_dataset(loghB_samples, z_fm, a_gev_inv, ...)``：沿用旧
       样本矩阵构建路径，生成可复用的 :class:`ZRDataset`。
    """
    if z_fm is None and a_gev_inv is None:
        return _coerce_zr_dataset(
            dataset_or_loghB_samples, kind=kind, n_rep=n_rep, seed=seed)
    if z_fm is None or a_gev_inv is None:
        raise TypeError("prepare_zr_dataset 构建模式需要同时提供 z_fm 和 a_gev_inv")

    s, z_ = _as_loghB_samples(dataset_or_loghB_samples, z_fm)
    if kind == 'boot':
        cov = boot_covariance(s, n_rep=n_rep, seed=seed)
        c_inv = np.linalg.pinv(cov)
    elif kind == 'diag':
        var = s.var(axis=1)
        cov = np.diag(var)
        c_inv = np.diag(1.0 / np.maximum(var, 1e-30))
    else:
        raise ValueError(f"未知 kind: {kind}")
    return ZRDataset(
        z=z_,
        loghB=s.mean(axis=1),
        c_inv=c_inv,
        a=float(a_gev_inv),
        loghB_samples=s,
        cov=cov,
        kind=kind,
    )


def _coerce_zr_dataset(dataset, kind='boot', n_rep=200, seed=0):
    """把旧 dict 或新对象规范为 ZRDataset。"""
    if isinstance(dataset, ZRDataset):
        return dataset
    if not isinstance(dataset, Mapping):
        raise TypeError("ZR dataset must be a dict or ZRDataset")

    z_ = np.asarray(dataset['z'], dtype=float)
    a_ = float(dataset['a'])
    samples = dataset.get('loghB_samples')
    loghB = np.asarray(dataset['loghB'], dtype=float)
    if samples is not None:
        samples, z_ = _as_loghB_samples(samples, z_)
        loghB_mean = np.asarray(loghB, dtype=float)
        if loghB_mean.ndim != 1:
            loghB_mean = samples.mean(axis=1)
    elif loghB.ndim == 2:
        samples, z_ = _as_loghB_samples(loghB, z_)
        loghB_mean = samples.mean(axis=1)
    elif loghB.ndim == 1:
        if loghB.shape[0] != z_.shape[0]:
            raise ValueError(
                f"loghB 长度 {loghB.shape[0]} 与 z 网格 {z_.shape[0]} 不一致"
            )
        samples = None
        loghB_mean = loghB
    else:
        raise ValueError("loghB must be one- or two-dimensional")

    c_inv = dataset.get('c_inv')
    cov = dataset.get('cov')
    if c_inv is None:
        if samples is None:
            raise ValueError("旧 dict 若不含 c_inv，必须提供 loghB 样本矩阵")
        return prepare_zr_dataset(samples, z_, a_, kind=kind,
                                  n_rep=n_rep, seed=seed)
    return ZRDataset(
        z=z_,
        loghB=loghB_mean,
        c_inv=np.asarray(c_inv, dtype=float),
        a=a_,
        loghB_samples=samples,
        cov=None if cov is None else np.asarray(cov, dtype=float),
        kind=dataset.get('kind', 'precomputed'),
    )


def prepare_zr_datasets(datasets, kind='boot', n_rep=200, seed=0):
    """批量规范化 Z_R 数据集，供 ``fit_ZR`` / ``fit_ZR_samples`` 复用。"""
    if isinstance(datasets, (ZRDataset, Mapping)):
        return [prepare_zr_dataset(datasets, kind=kind, n_rep=n_rep, seed=seed)]
    if (isinstance(datasets, tuple) and len(datasets) == 3
            and not isinstance(datasets[0], (ZRDataset, Mapping))):
        return [prepare_zr_dataset(
            datasets[0], datasets[1], datasets[2],
            kind=kind, n_rep=n_rep, seed=seed,
        )]
    prepared = []
    for ds in datasets:
        if isinstance(ds, tuple) and len(ds) == 3:
            prepared.append(prepare_zr_dataset(
                ds[0], ds[1], ds[2], kind=kind, n_rep=n_rep, seed=seed))
        else:
            prepared.append(prepare_zr_dataset(
                ds, kind=kind, n_rep=n_rep, seed=seed))
    return prepared


def make_zr_dataset(loghB_samples, z_fm, a_gev_inv, kind='boot',
                    n_rep=200, seed=0):
    """组装 fit_ZR / cost_function_all 所需数据集 dict。

    Args:
        loghB_samples: (nz, nsample)——归一化 log hB 的逐样本数组
                       （build_hB_dataset 输出的 loghB）。
        z_fm: z 网格（fm，与第一维对应）。
        a_gev_inv: 格距（GeV⁻¹，a_fm/fm_to_GeV）。
        kind: 'boot' 自助协方差（pinv 防奇异）/ 'diag' 对角方差。
    Returns:
        dict(z, loghB(均值), c_inv, a)——直接可入 datasets 列表。
    """
    return prepare_zr_dataset(
        loghB_samples, z_fm, a_gev_inv, kind=kind, n_rep=n_rep, seed=seed,
    ).to_dict()


def _fit_ZR_prepared(par_ini, datasets, mu_, use_iminuit=True):
    par_name = ('k', 'd', 'm0', 'm2', 'Lambda_QCD',
                'g1', 'g2', 'g3', 'g4', 'g5', 'g6', 'g7', 'g8',
                'g9', 'g10', 'g11', 'g12', 'g13', 'g14', 'f1', 'f2')

    def cost(par):
        return _cost_function_all_prepared(par, datasets, mu_)

    if use_iminuit:
        try:
            from iminuit import Minuit
            m = Minuit(cost, par_ini, name=par_name)
            m.limits['k'] = (None, None)
            m.limits['d'] = (None, None)
            m.limits['m0'] = (None, None)
            m.limits['m2'] = (None, None)
            m.limits['Lambda_QCD'] = (0, None)
            m.fixed['f1', 'f2', 'm2'] = True
            m.migrad()
            return np.array(m.values)
        except ImportError:
            pass  # 回退到 scipy

    from scipy.optimize import minimize
    res = minimize(cost, par_ini, method='Nelder-Mead',
                   options={'maxiter': 5000, 'xatol': 1e-6})
    return res.x


def fit_ZR(par_ini, datasets, mu_, use_iminuit=True):
    """全局拟合 Z_R 参数（iminuit 或 scipy 回退）。

    Args:
        par_ini: 参数初值（长度 ≥ 21：k,d,m0,m2,Λ,g1..g14,f1,f2）
        datasets: [dict(z, loghB, c_inv, a), ...] 或 [ZRDataset, ...]
        mu_: 重整化标度（GeV）
    Returns:
        拟合参数数组（m.values）。
    """
    return _fit_ZR_prepared(
        par_ini, prepare_zr_datasets(datasets), mu_, use_iminuit=use_iminuit)


# ═══════════════════════════════════════════════════════════════════
# 逐样本重拟合环（整合 zengch fit_zr_new.fit_ZR 的 bootstrap 样本循环）
# ═══════════════════════════════════════════════════════════════════

_ZR_PAR_NAMES = ('k', 'd', 'm0', 'm2', 'Lambda_QCD',
                 'g1', 'g2', 'g3', 'g4', 'g5', 'g6', 'g7', 'g8',
                 'g9', 'g10', 'g11', 'g12', 'g13', 'g14', 'f1', 'f2')


def fit_ZR_samples(par_ini, dataset_samples, mu_, use_iminuit=True):
    """Z_R 参数误差的逐样本重拟合环（照抄 zengch fit_zr_new.fit_ZR 样本循环）。

    对每个 bootstrap/jackknife 样本 i：以各系综 loghB 矩阵的第 i 列为
    "均值"数据重跑全局拟合，收集参数分布 → 均值±std（原版逐行写 CSV）。
    协方差 c_inv 与原版一致地跨样本固定（由全体样本的 std 构建后传入）。

    Args:
        par_ini: 参数初值（长度 ≥ 21）。
        dataset_samples: [dict(z, loghB=(nz,n_rep) 样本矩阵, c_inv, a), ...]
            或 [ZRDataset, ...]；单样本 ``loghB`` 也可直接视为一列。
            n_rep 取各系综的最小列数（原版取第一系综列数，此处更稳健）。
        mu_: 重整化标度（GeV）。
    Returns:
        list[dict]：每样本一行（sample_i, k, d, m0, m2, Lambda_QCD,
        g1..g14, f1, f2, chi2）；单个样本拟合失败记 NaN 并告警继续
        （对原版行为的唯一偏离，防单坏样本中断整环）。
    """
    dataset_samples = prepare_zr_datasets(dataset_samples)
    if any(ds.loghB_samples is None for ds in dataset_samples):
        raise ValueError("fit_ZR_samples requires loghB sample matrices")
    n_rep = min(ds.n_sample for ds in dataset_samples)
    rows = []
    for i in range(n_rep):
        datasets_i = [ds.sample_view(i) for ds in dataset_samples]
        try:
            par_fit = _fit_ZR_prepared(par_ini, datasets_i, mu_,
                                       use_iminuit=use_iminuit)
            chi2 = _cost_function_all_prepared(par_fit, datasets_i, mu_)
        except Exception as exc:  # noqa: BLE001 —— 单坏样本不中断整环
            print(f"[fit_ZR_samples] sample {i} failed: {exc}")
            par_fit = np.full(len(_ZR_PAR_NAMES), np.nan)
            chi2 = np.nan
        row = {"sample_i": i}
        row.update({name: float(val)
                    for name, val in zip(_ZR_PAR_NAMES, par_fit)})
        row["chi2"] = float(chi2) if np.isfinite(chi2) else np.nan
        rows.append(row)
    return rows


def summarize_ZR_samples(rows):
    """逐样本拟合结果的参数分布汇总（mean/std；原版以 CSV 供人工统计）。"""
    keys = [k for k in rows[0].keys() if k != "sample_i"]
    summary = {}
    for key in keys:
        vals = np.array([r[key] for r in rows], dtype=float)
        vals = vals[np.isfinite(vals)]
        summary[key] = (float(np.mean(vals)) if vals.size else np.nan,
                        float(np.std(vals)) if vals.size else np.nan)
    return summary


ZRDataset.__module__ = "pyqcd.renorm"
