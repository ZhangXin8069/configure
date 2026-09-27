"""系综参数表：格距 a、格点尺寸 Nl、π 介子质量（照抄 zengch hB_data_FeynmenHellman.py 数据）。"""
import numpy as np

# 1 fm⁻¹ = 0.197 GeV（zengch 用 0.197）
fm_to_GeV = 0.197

# a 的单位：GeV⁻¹（= 0.105 fm / 0.197）
a_len_set = {
    'C24P29':        0.105 / fm_to_GeV,
    'L24x72':        0.105 / fm_to_GeV,
    'L32x64':        0.0897 / fm_to_GeV,
    'L32x96':        0.0775 / fm_to_GeV,
    'L48x144':       0.0519 / fm_to_GeV,
    'L36x108':       0.0688 / fm_to_GeV,
    'L32x64_C32P23': 0.105 / fm_to_GeV,
    'L32x64_C32P29': 0.105 / fm_to_GeV,
    'L48x96_C48P14': 0.105 / fm_to_GeV,
}

# 时间方向格点数（空间为 L，时间 = Nl × 3，LaMET 惯例）
Nl_set = {
    'C24P29': 24, 'L24x72': 24, 'L32x64': 32, 'L32x96': 32,
    'L48x144': 48, 'L36x108': 36, 'L32x64_C32P23': 32,
    'L32x64_C32P29': 32, 'L48x96_C48P14': 48,
}

# π 介子质量（GeV）
pion_mass_set = {
    'C24P29': 0.293, 'L24x72': 0.293, 'L32x64': 0.285, 'L32x96': 0.303,
    'L36x108': 0.297, 'L48x144': 0.317, 'L32x64_C32P23': 0.228,
    'L32x64_C32P29': 0.292, 'L48x96_C48P14': 0.136,
}

# 物理点 π 质量（GeV）
MPI_PHYSICAL = 0.135


def pz_to_gev(pz: int, conf: str) -> float:
    """格点单位动量 P_z → GeV：P_z·(2π)/(N_l · a)。"""
    return pz * 2.0 * np.pi / (Nl_set[conf] * a_len_set[conf])
