from argparse import Namespace
"""重整化：自重整化 Z_R、混合方案、NLO 匹配、连续极限外推、梯度流、TMD 提取。

本子包提供核子胶子 TMD-PDF 重整化与提取链的数值构件（核心目标）：
    裸矩阵元 → 混合方案（比值 + 自重整化）→ λ 外推 → 傅里叶变换
    → NLO 匹配 → 连续极限外推，
并以梯度流（Wilson flow，Monahan–Orginos 方案）为 UV 正规化手段。接口齐全不等于
特定系综已完成物理闭环；CS 核、软因子、匹配阶数与连续极限仍须由调用方提供并验证。
"""
from ._const import CA, CF, gammaE, pi, alpha_s, A_s, b0
from ._ensembles import (
    fm_to_GeV, a_len_set, Nl_set, pion_mass_set, MPI_PHYSICAL, pz_to_gev,
)
from ._zr import (
    Z_MS, th_hB, th_ZR, cost_function, cost_function_all, fit_ZR,
    ZRDataset, build_hB_dataset, boot_covariance, prepare_zr_dataset,
    prepare_zr_datasets, make_zr_dataset,
    fit_ZR_samples, summarize_ZR_samples,
)
from ._hybrid import (
    hR_z_Pz, hR_lambda_fit_form, fit_hR_lambda, hR_lambda, hR_x,
)
from ._matching import hR_PDF, C_gluon_ratio, C, Si
from ._extrapolate import hR_form, build_fit_data, fit_hR_PDF_extrap, fit_hR_PDF_extrap_boot
from ._gradient_flow import (
    wilson_flow, wilson_flow_step, flow_derivative, staple_6,
    wilson_action_density, flow_action_density, scale_setting_t0, proj_su3,
)
from ._gradient_flow_quasi import (
    GEV_FM, FLOW_TO_QUASI_SCHEMA, coefficients,
    gradient_flow_to_quasi_coefficients, match_one,
    match_gradient_flow_ope_to_quasi,
)
from ._tmd import (
    staple_wilson_line, M_mu_lambda_nu_rho, gluon_tmd_operator,
    tmd_matrix_elements, tmd_matrix_elements_time,
    gradient_flow_renormalized_tmd,
    self_renormalized_ratio, invariant_amplitude, collins_soper_kernel,
    scan_staple_length, fit_staple_plateau,
)
from ._tmdextract import (
    quasi_tmd_pdf, quasi_pdf_gluon, cs_kernel_from_ratio, cs_kernel_two_momentum,
    soft_function_intrinsic, tmd_matching_hybrid, sftx_gluon_matching_coeff,
    sftx_energy_density_t0, flow_time_gev_m2,
)
from ._soft import (
    Z_E, sqrt_Z_E, rapidity_subtraction,
    msbar_tmd_reference_matrix_element,
    short_distance_renormalization_factor, sdr_renormalized_tmd,
    soft_factor_rectangle, soft_subtraction_factor, soft_subtraction,
)

__all__ = [
    # 常数
    "CA", "CF", "gammaE", "pi", "alpha_s", "A_s", "b0",
    # 系综
    "fm_to_GeV", "a_len_set", "Nl_set", "pion_mass_set", "MPI_PHYSICAL", "pz_to_gev",
    # 自重整化
    "Z_MS", "th_hB", "th_ZR", "cost_function", "cost_function_all", "fit_ZR",
    "ZRDataset", "build_hB_dataset", "boot_covariance",
    "prepare_zr_dataset", "prepare_zr_datasets", "make_zr_dataset",
    "fit_ZR_samples", "summarize_ZR_samples",
    # 混合方案
    "hR_z_Pz", "hR_lambda_fit_form", "fit_hR_lambda", "hR_lambda", "hR_x",
    # 匹配
    "hR_PDF", "C_gluon_ratio", "C", "Si",
    # 外推
    "hR_form", "build_fit_data", "fit_hR_PDF_extrap",
    "fit_hR_PDF_extrap_boot",
    # 梯度流
    "wilson_flow", "wilson_flow_step", "flow_derivative", "staple_6",
    "wilson_action_density", "flow_action_density", "scale_setting_t0",
    "proj_su3",
    "GEV_FM", "FLOW_TO_QUASI_SCHEMA", "coefficients",
    "gradient_flow_to_quasi_coefficients", "match_one",
    "match_gradient_flow_ope_to_quasi",
    # TMD
    "staple_wilson_line", "M_mu_lambda_nu_rho", "gluon_tmd_operator",
    "tmd_matrix_elements", "tmd_matrix_elements_time",
    "gradient_flow_renormalized_tmd",
    "self_renormalized_ratio", "invariant_amplitude", "collins_soper_kernel",
    "scan_staple_length", "fit_staple_plateau",
    "quasi_tmd_pdf", "quasi_pdf_gluon", "cs_kernel_from_ratio", "soft_function_intrinsic",
    "tmd_matching_hybrid", "sftx_gluon_matching_coeff",
    "sftx_energy_density_t0", "flow_time_gev_m2", "cs_kernel_two_momentum",
    # 矩形 Wilson 圈软因子 / rapidity subtraction
    "Z_E", "sqrt_Z_E", "rapidity_subtraction",
    "msbar_tmd_reference_matrix_element",
    "short_distance_renormalization_factor", "sdr_renormalized_tmd",
    "soft_factor_rectangle", "soft_subtraction_factor", "soft_subtraction",
]

Namespace.__module__ = "pyqcd.renorm"
