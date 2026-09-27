from argparse import Namespace
"""顶点函数：VdV / VVV 动量投影顶点、相位因子；本征模压缩（蒸馏降维）。"""
from ._vertex import (
    phase_exp_2pt, phase_exp_3pt, Mom_VdV_sink_t, Mom_VVV_sink_t,
    VdV_sink_t_link, sink2src, momsmear_phase, apply_momentum_smearing,
)
from ._eigcompress import (
    inner_product, check_orthonormal, normalize, orthnormal_append,
    create_noise, compress_matrix_V1, compress_matrix_V2,
    compress_matrix_V3, compress_matrix_V4, create_omega_accelerate,
)

__all__ = [
    "phase_exp_2pt", "phase_exp_3pt", "Mom_VdV_sink_t", "Mom_VVV_sink_t",
    "VdV_sink_t_link", "sink2src", "momsmear_phase",
    "apply_momentum_smearing",
    "inner_product", "check_orthonormal", "normalize", "orthnormal_append",
    "create_noise", "compress_matrix_V1", "compress_matrix_V2",
    "compress_matrix_V3", "compress_matrix_V4", "create_omega_accelerate",
]

Namespace.__module__ = "pyqcd.vertex"
