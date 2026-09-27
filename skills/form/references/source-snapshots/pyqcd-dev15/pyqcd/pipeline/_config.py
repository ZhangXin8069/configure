"""
管线集中配置（照抄冻结蒸馏基线 `config.py`，路径归整到 PyQCD）。

系综：beta6.20_mu-0.2770_ms-0.2400_L24x72（24³×72, a≈0.1053 fm, a⁻¹≈1.874 GeV）。
"""
import os

# ═══════════════════════════════════════════════════════════════════
# 格点系综参数
# ═══════════════════════════════════════════════════════════════════

ENSEMBLE = "beta6.20_mu-0.2770_ms-0.2400_L24x72"
NX = 24
NY = 24
NZ = 24
NT = 72
ALttc = 0.1053        # 格距 fm
A_INV = 0.1973269804 / ALttc   # a⁻¹ ≈ 1.874 GeV
FM2GEV = 0.1973269804          # ℏc

# ═══════════════════════════════════════════════════════════════════
# 组态 ID（10 组态）
# ═══════════════════════════════════════════════════════════════════

CONF_IDS = [6250, 6450, 6650, 6850, 7050,
            7250, 7450, 7650, 7850, 8050]

# ═══════════════════════════════════════════════════════════════════
# 数据路径（集群文件系统）
# ═══════════════════════════════════════════════════════════════════

BASE_EIGEN_DIR = "/public/group/lqcd/eigensystem"
BASE_PERAM_DIR = "/public/group/lqcd/perambulators"
BASE_GAUGE_DIR = "/public/group/lqcd/configurations/CLOVER"

EIGEN_DIR = f"{BASE_EIGEN_DIR}/{ENSEMBLE}"
PERAM_DIR = f"{BASE_PERAM_DIR}/{ENSEMBLE}/light"
GAUGE_DIR = f"{BASE_GAUGE_DIR}/{ENSEMBLE}"

# ═══════════════════════════════════════════════════════════════════
# 蒸馏参数
# ═══════════════════════════════════════════════════════════════════

NEV = 100
NEV1 = 100

# ═══════════════════════════════════════════════════════════════════
# 动量列表（[Pz, Py, Px]，单位 2π/L）
# ═══════════════════════════════════════════════════════════════════

MOM_SINK_VDV = [[0, 0, 0], [0, 0, 2]]
MOM_SINK_VVV = [[0, 0, 0], [0, 0, 2]]

ANALYSIS_MOMENTA = {
    'pion':   {'P000': [0, 0, 0], 'P002': [0, 0, 2]},
    'proton': {'P000': [0, 0, 0], 'P002': [0, 0, 2]},
}

# ═══════════════════════════════════════════════════════════════════
# 强子算符（sush lqcddb 算符 DSL，DR 基）
# ═══════════════════════════════════════════════════════════════════

PION_SINK = ['|', 'u^d', 'gamma_5', 'd', '|']
PION_SRC = ['|', 'd^d', 'gamma_5', 'u', '|']

PROTON_SINK = ['|', 'u', 'u', 'gamma_7', 'd', '|']
PROTON_SRC = ['|', 'u^d', 'gamma_7', 'd^d', 'u^d', '|']

NEUTRON_SINK = ['|', 'd', 'd', 'gamma_7', 'u', '|']
NEUTRON_SRC = ['|', 'u^d', 'gamma_7', 'd^d', 'd^d', '|']

PP_SINK, PP_SRC = PROTON_SINK, PROTON_SRC
PN_SINK, PN_SRC = PROTON_SINK, NEUTRON_SRC
NN_SINK, NN_SRC = NEUTRON_SINK, NEUTRON_SRC

PJN_SINK = ['|', 'u', 'u', 'gamma_7', 'd', '|']
PJN_CURR = ['|', 'u^d', 'gamma_mu', 'd', '|']
PJN_SRC = ['|', 'u^d', 'gamma_7', 'd^d', 'd^d', '|']

PION3_SINK = PION_SINK
PION3_CURR = ['|', 'u^d', 'gamma_mu', 'u', '|']
PION3_SRC = PION_SRC

PJNNJNP_SINK = ['|', 'd', 'u', 'gamma_7', 'd', '|']
PJNNJNP_SRC = ['|', 'u^d', 'gamma_7', 'd^d', 'd^d', '|', '|', 'd^d', 'gamma_5', 'u', '|']
PJNNJNP_CURR = ['|', 'u^d', 'gamma_mu', 'd', '|']

FOURPT_NEV1 = 60
FOURPT_TSEP = 6
FOURPT_MOM = [0]
FOURPT_SRC_STEP = 2

# ═══════════════════════════════════════════════════════════════════
# 3pt/4pt 分析参数
# ═══════════════════════════════════════════════════════════════════

T_SEP = 12
T_SEP_3PT = 8

# ═══════════════════════════════════════════════════════════════════
# OPE（胶子算符）参数
# ═══════════════════════════════════════════════════════════════════

DELTA_Z = 24
Z_DIR = 2
OPE_COMPONENTS = [(0, 1), (3, 0), (3, 1)]

# ═══════════════════════════════════════════════════════════════════
# 精度
# ═══════════════════════════════════════════════════════════════════

PRECISION = 'complex64'

# ═══════════════════════════════════════════════════════════════════
# 输出路径（归整到 PyQCD 仓库根）
# ═══════════════════════════════════════════════════════════════════

_PROJECT_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..'))
DATA_DIR = os.path.join(_PROJECT_ROOT, 'data')
PLOTS_DIR = os.path.join(_PROJECT_ROOT, 'plots')
LOGS_DIR = os.path.join(_PROJECT_ROOT, 'logs')
OUTPUT_DIR = os.path.join(_PROJECT_ROOT, 'output')


def get_eigen_path(conf_id, t):
    return f"{EIGEN_DIR}/{conf_id}/eigvecs_t{t:03d}_{conf_id}"


def get_peram_dir(conf_id):
    return f"{PERAM_DIR}/{conf_id}"


def get_peram_file(conf_id, d_source, t_source):
    return f"{PERAM_DIR}/{conf_id}/perams.{conf_id}.{d_source}.{t_source}"


def get_gauge_path(conf_id):
    return f"{GAUGE_DIR}/{ENSEMBLE}_cfg_{conf_id}.lime"


def conf_data_dir(run_dir, conf_id):
    d = os.path.join(run_dir, 'data', f'conf{conf_id}')
    os.makedirs(d, exist_ok=True)
    return d
