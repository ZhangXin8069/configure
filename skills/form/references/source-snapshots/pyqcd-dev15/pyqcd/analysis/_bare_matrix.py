"""
03_bare_matrix 功能：三方向裸矩阵元 ratio + 平均 + 拟合 + 画图（独立实现）
==========================================================================

功能对齐 refer/huangcl/03_bare_matrix/code_bare_matrix.py：

- compute：对 x/y/z 三个方向分别读 2pt 切片（momsmear2{P}{dir} 的动量置换）
  与对应方向 OPE 组合（z: (0,1)/(3,0)/(3,1)；x: (1,2)/(3,1)/(3,2)；
  y: (2,0)/(3,2)/(3,0)）→ 各自 ratio → 三方向平均 → ratio_dtmax{}.npy。
- fit：模型 R = c0 + c1·e^{−dE·dtau} + c1·e^{−dE·(dt−dtau)}，
  拟合目录 tsep{start}_{end}_nex{nex} → 0_fit_data.npz + 1_fit_report.txt。
- plot：ratio.png / c0.png / chi2.png（复用 _ratio2pt 的画图）。

核心计算与 _ratio2pt 共享（load_raw/compute_ratio/do_fit_and_report/
plot_ratio_fits），仅方向参数（OPE 组合、动量置换、目录命名）不同。
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import numpy as np

from ._disconnected import model_ratio
from ._fitter import FitParams
from ._ratio2pt import (PlotParamsRatio, SampleParams2pt, compute_ratio,
                        do_fit_and_report, load_raw, plot_ratio_fits)

def dir_momentum(Px, Py, Pz, dir):
    """方向动量置换约定（公开助手，test6/repro_04 整合项）。

    x: (Pz, Px, Py)；y: (Py, Pz, Px)；z: (Px, Py, Pz)
    （与 _dir_spec 及 refer/huangcl code_bare_matrix.py 一致）。
    """
    if dir == 'x':
        return Pz, Px, Py
    if dir == 'y':
        return Py, Pz, Px
    if dir == 'z':
        return Px, Py, Pz
    raise ValueError(f"unknown dir: {dir}")


def _dir_spec(sampa: SampleParams2pt, dir: str):
    """    各方向: (动量置换 (Px,Py,Pz), OPE 组合 (mu1,nu1), 数据子目录名)。

    动量置换约定见 dir_momentum（公开助手）。
    """
    Px, Py, Pz = sampa.Px, sampa.Py, sampa.Pz
    if dir == 'x':
        return dir_momentum(Px, Py, Pz, 'x'), (1, 2), 'xdir'
    if dir == 'y':
        return dir_momentum(Px, Py, Pz, 'y'), (2, 0), 'ydir'
    if dir == 'z':
        return dir_momentum(Px, Py, Pz, 'z'), (0, 1), 'zdir'
    raise ValueError(f"unknown dir: {dir}")


def compute_ratio_dir(data_root, sampa: SampleParams2pt, dir: str,
                      jack: bool, verbose=True) -> np.ndarray:
    """计算单个方向的 ratio（动量置换 + 该方向 OPE 组合）。"""
    mom, tdir, sub = _dir_spec(sampa, dir)
    Px, Py, Pz = mom
    mu1, nu1 = tdir

    mom_tag = f"Px{Px}Py{Py}Pz{Pz}"
    _corr = np.zeros((sampa.Nconf, sampa.Nt, sampa.Nt), dtype=complex)
    _ope_01 = np.zeros((sampa.Nconf, sampa.Nx, sampa.Nt), dtype=complex)
    _ope_30 = np.zeros((sampa.Nconf, sampa.Nx, sampa.Nt), dtype=complex)
    _ope_31 = np.zeros((sampa.Nconf, sampa.Nx, sampa.Nt), dtype=complex)
    for i, conf_id in enumerate(sampa.conf_ids):
        corr_path = os.path.join(
            data_root, sampa.conf_name, f"momsmear{sampa.Pz}{dir}",
            str(conf_id),
            f"twopt_slice_pp_{mom_tag}_eginphase2_Cg5g4_nopol_ss_conf{conf_id}.npy")
        _corr[i] = np.load(corr_path)
        ope_dir = os.path.join(data_root, sampa.conf_short, sub,
                               str(conf_id))
        _ope_01[i] = np.load(os.path.join(
            ope_dir, f"ops_mu{mu1}_nu{nu1}_dz{sampa.Nx}_conf{conf_id}.npz"))["ops"]
        _ope_30[i] = np.load(os.path.join(
            ope_dir, f"ops_mu3_nu{mu1}_dz{sampa.Nx}_conf{conf_id}.npz"))["ops"]
        _ope_31[i] = np.load(os.path.join(
            ope_dir, f"ops_mu3_nu{nu1}_dz{sampa.Nx}_conf{conf_id}.npz"))["ops"]

    if verbose:
        print(f"load finish ({dir}), 2pt shape: {_corr.shape}")

    # 组合 OPE 后复用 _ratio2pt 的核心相对时间/真空扣除计算
    ratio = _ratio_from_raw(_corr, _ope_01, _ope_30, _ope_31,
                            sampa, jack, verbose=verbose)
    return ratio


def _ratio_from_raw(_corr, _ope_01, _ope_30, _ope_31, sampa, jack,
                    verbose=True):
    """相对时间构造 + 重采样 + 真空扣除 ratio（与 02_ratio 核心一致）。"""
    from ._ratio2pt import ope_combine
    from ._disconnected import resample

    _ope = ope_combine(_ope_01, _ope_30, _ope_31)   # (Nconf, tau, z)

    _corr2_rel = np.zeros((sampa.Nconf, sampa.Nt, sampa.dt_max), dtype=complex)
    _ope_rel = np.zeros((sampa.Nconf, sampa.Nt, sampa.dt_max, sampa.Nx),
                        dtype=complex)
    for ti in range(sampa.Nt):
        corr2_shift = np.roll(_corr[:, :, ti], shift=-ti, axis=1)
        _corr2_rel[:, ti, :] = corr2_shift[:, :sampa.dt_max]
        ope_shift = np.roll(_ope, shift=-ti, axis=1)
        _ope_rel[:, ti, :, :] = ope_shift[:, :sampa.dt_max, :]

    _corr3 = np.zeros((sampa.Nconf, sampa.Nt, sampa.dt_max,
                       sampa.dt_max, sampa.Nx), dtype=complex)
    for _dt in range(sampa.dt_max):
        for _dtau in range(_dt + 1):
            _corr3[:, :, _dt, _dtau, :] = (
                _ope_rel[:, :, _dtau, :] * _corr2_rel[:, :, _dt][:, :, None])

    corr2 = resample(_corr2_rel, jack, sampa.Nsample)
    ope = resample(_ope_rel, jack, sampa.Nsample)
    corr3 = resample(_corr3, jack, sampa.Nsample)

    corr3_disc = corr3 - corr2[:, :, :, None, None] * ope[:, :, None, :, :]
    eps = 1e-30
    ratio = np.mean(corr3_disc / (corr2[:, :, :, None, None] + eps), axis=1).real
    if verbose:
        print(f"ratio shape: {ratio.shape}")
    return ratio


def run_bare_matrix(data_root, out_root, sampa: SampleParams2pt,
                    fitpa_list, plotpa: PlotParamsRatio, jack: bool = False,
                    parts=(1, 3), verbose=True) -> dict:
    """03_bare_matrix 全链：三方向 ratio + 平均 → fit（多窗口）→ plot。"""
    ratio_dir = os.path.join(out_root, sampa.conf_short, f"Pz{sampa.Pz}")
    os.makedirs(ratio_dir, exist_ok=True)
    ratio_path = os.path.join(ratio_dir, f"ratio_dtmax{sampa.dt_max}.npy")
    result = {"saved": []}

    if parts[0] <= 1:
        time0 = time.perf_counter()
        ratio = np.zeros((sampa.Nsample, sampa.dt_max, sampa.dt_max, sampa.Nx))
        for _dir in ["x", "y", "z"]:
            ratio += compute_ratio_dir(data_root, sampa, _dir, jack,
                                       verbose=verbose)
        ratio /= 3
        np.save(ratio_path, ratio)
        if verbose:
            print(f"ratio saved to {ratio_path}")
            print(f"Peak Memory: {_peak_gb():.3f} GB")
            print(f"spend time: {time.perf_counter() - time0:.2f}s\n")
    else:
        ratio = np.load(ratio_path)
        if verbose:
            print("===== skip compute ratio, loading ratio from file =====")
            print(f"ratio loaded, shape: {ratio.shape}")
    result["ratio"] = ratio

    for _fitpa in fitpa_list:
        _fit_dir = os.path.join(ratio_dir,
                                f"tsep{_fitpa.dt_start}_{_fitpa.dt_end}"
                                f"_nex{_fitpa.nex}")
        os.makedirs(_fit_dir, exist_ok=True)
        if parts[0] <= 2:
            time0 = time.perf_counter()
            fit_result = do_fit_and_report(ratio, _fitpa, sampa, _fit_dir,
                                           jack, verbose=verbose)
            if verbose:
                print(f"spend time: {time.perf_counter() - time0:.2f}s\n")
        else:
            fit_result = dict(np.load(os.path.join(_fit_dir, "0_fit_data.npz")))
        result.setdefault("fit_results", {})[f"tsep{_fitpa.dt_start}_{_fitpa.dt_end}_nex{_fitpa.nex}"] = fit_result

        if parts[0] <= 3:
            result["saved"] += plot_ratio_fits(
                ratio, fit_result, sampa, _fitpa, plotpa, _fit_dir, jack,
                verbose=verbose)
    return result


def _peak_gb():
    from ._plots import get_peak_memory_gb
    return get_peak_memory_gb()
