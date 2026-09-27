"""
Pipeline Configuration — docker-v20260805
==========================================

Central configuration for the PyQCD GPU pipeline (docker-v20260805).

This version generalizes docker-v20260803 (central config + sush/lqcddb-style
lib/ + LaTeX report) and extends it to a FULL distillation toolkit (as in
docker-v20260804):

  - Vertex functions:  VdV (meson vertex), VVV (baryon vertex)
  - Wick contraction + dynamic contraction (sush lqcddb engine)
  - Correlators:       2pt (pp / pn), OPE (gluon), 3pt (PJN), 4pt (PJNNJNp)
  - Statistical analysis: Jackknife / meff / ratio_3p in the style of
    examples/huangcl/02_ratio/code_1.py
  - Pion & proton at P=(0,0,0) and P=(0,0,2)
  - 10 configurations: 6250, 6450, 6650, 6850, 7050, 7250, 7450, 7650, 7850, 8050

Ensemble: beta6.20_mu-0.2770_ms-0.2400_L24x72
Lattice:  24³×72, a ≈ 0.1053 fm, a⁻¹ ≈ 1.874 GeV, β = 6.20
"""

import os

# ═══════════════════════════════════════════════════════════════════
# Lattice Ensemble Parameters
# ═══════════════════════════════════════════════════════════════════

ENSEMBLE = "beta6.20_mu-0.2770_ms-0.2400_L24x72"
NX = 24          # Spatial lattice size (isotropic)
NY = 24
NZ = 24
NT = 72          # Temporal lattice size
ALttc = 0.1053   # Lattice spacing in fm
A_INV = 0.1973269804 / ALttc  # Inverse lattice spacing in GeV (~1.874 GeV)
FM2GEV = 0.1973269804         # ℏc in GeV·fm

# ═══════════════════════════════════════════════════════════════════
# Configuration IDs — 10 configs (user-specified)
# ═══════════════════════════════════════════════════════════════════

CONF_IDS = [6250, 6450, 6650, 6850, 7050,
            7250, 7450, 7650, 7850, 8050]

# ═══════════════════════════════════════════════════════════════════
# Data Paths (HPC cluster filesystem)
# ═══════════════════════════════════════════════════════════════════

BASE_EIGEN_DIR = "/public/group/lqcd/eigensystem"
BASE_PERAM_DIR = "/public/group/lqcd/perambulators"
BASE_GAUGE_DIR = "/public/group/lqcd/configurations/CLOVER"

EIGEN_DIR = f"{BASE_EIGEN_DIR}/{ENSEMBLE}"
PERAM_DIR = f"{BASE_PERAM_DIR}/{ENSEMBLE}/light"
GAUGE_DIR = f"{BASE_GAUGE_DIR}/{ENSEMBLE}"

# ═══════════════════════════════════════════════════════════════════
# Distillation Parameters
# ═══════════════════════════════════════════════════════════════════

NEV = 100         # Number of Laplacian eigenvectors (data contains 100)
NEV1 = 100        # Truncation for VVV / baryon contractions (memory control)
                  # Use a smaller value (e.g. 60) for fast GPU smoke tests.

# ═══════════════════════════════════════════════════════════════════
# Momentum List — [Pz, Py, Px] in units of 2π/L
# ═══════════════════════════════════════════════════════════════════
# VdV (meson vertex) sink momenta; VVV (baryon vertex) sink momenta.
# Momentum index 0 = P=(0,0,0), index 1 = P=(0,0,2).

MOM_SINK_VDV = [
    [0, 0, 0],       # Rest frame — required
    [0, 0, 2],       # Pz = 2 — required for the gluon-PDF / dispersion check
]

MOM_SINK_VVV = [
    [0, 0, 0],       # Rest frame
    [0, 0, 2],       # Pz = 2
]

# Analysis momenta (label → [Pz, Py, Px]) for pion & proton
ANALYSIS_MOMENTA = {
    'pion':   {'P000': [0, 0, 0], 'P002': [0, 0, 2]},
    'proton': {'P000': [0, 0, 0], 'P002': [0, 0, 2]},
}

# ═══════════════════════════════════════════════════════════════════
# Hadron Operator Definitions (sush lqcddb operator DSL, DR basis)
# ═══════════════════════════════════════════════════════════════════
# Format: ['|', quark1, quark2, gamma, quark3, '|']
#   'u','d'      = quarks; 'u^d','d^d' = anti-quarks
#   'gamma_5'    = γ₅,  'gamma_7' = γ₃γ₁ (≈ Cγ₅ diquark in DR basis)
#   '|'          = hadron separator

# Pion: π⁺ = ū γ₅ d
PION_SINK = ['|', 'u^d', 'gamma_5', 'd', '|']
PION_SRC  = ['|', 'd^d', 'gamma_5', 'u', '|']

# Proton: p = ε_{abc} (u^T C γ₅ d) u
PROTON_SINK = ['|', 'u', 'u', 'gamma_7', 'd', '|']
PROTON_SRC  = ['|', 'u^d', 'gamma_7', 'd^d', 'u^d', '|']

# Neutron: n = ε_{abc} (d^T C γ₅ d) u
NEUTRON_SINK = ['|', 'd', 'd', 'gamma_7', 'u', '|']
# Proper Hermitian conjugate of the neutron operator
NEUTRON_SRC  = ['|', 'u^d', 'gamma_7', 'd^d', 'd^d', '|']

# 2pt channels requested by the user: pp (proton-proton), pn (proton-neutron)
# NOTE: proton (uud) and neutron (udd) differ in flavor content, so the
# proton→neutron two-point function is *identically zero* in exact SU(2) QCD
# (there is no u-count matched by ū-count). We nevertheless compute it with the
# neutron operator at the source, as in sush's contraction.pn.2pt example, and
# report the (expected) vanishing result. The physically relevant non-zero
# cross-check is pp (proton-proton) — the main channel used for meff / ratio.
PP_SINK = PROTON_SINK
PP_SRC  = PROTON_SRC
PN_SINK = PROTON_SINK
PN_SRC  = NEUTRON_SRC
NN_SINK = NEUTRON_SINK
NN_SRC  = NEUTRON_SRC

# ═══════════════════════════════════════════════════════════════════
# 3pt operators — Proton( sink ) — Vector current — Nucleon( source )
# ═══════════════════════════════════════════════════════════════════
# Vector current J_μ = ū γ_μ d  (isovector, flavor-changing)

PJN_SINK = ['|', 'u', 'u', 'gamma_7', 'd', '|']
PJN_CURR = ['|', 'u^d', 'gamma_mu', 'd', '|']
PJN_SRC  = ['|', 'u^d', 'gamma_7', 'd^d', 'd^d', '|']

# Pion 3pt with a flavour-diagonal u-quark vector current ūγ_μu
PION3_SINK = PION_SINK
PION3_CURR = ['|', 'u^d', 'gamma_mu', 'u', '|']
PION3_SRC  = PION_SRC

# ═══════════════════════════════════════════════════════════════════
# 4pt operators — PJNNJNp (sush contraction.PJNNJNp-.4pt topology)
# ═══════════════════════════════════════════════════════════════════
# The NJNp topology: sink = neutron (1 hadron), source = proton + pion
# (2 hadrons), current J_μ in between. This flavour assignment balances
# exactly:  u/ū = 2/2, d/d̄ = 3/3.
#   sink  n   = ['|','d','u','gamma_7','d','|']            (udd)
#   src   p̄ π = ['|','u^d','gamma_7','d^d','d^d','|','|','d^d','gamma_5','u','|']
#   curr  J   = ['|','u^d','gamma_mu','d','|']

PJNNJNP_SINK = ['|', 'd', 'u', 'gamma_7', 'd', '|']   # neutron (udd)
PJNNJNP_SRC  = ['|', 'u^d', 'gamma_7', 'd^d', 'd^d', '|',
                '|', 'd^d', 'gamma_5', 'u', '|']      # proton-conj + pion
PJNNJNP_CURR = ['|', 'u^d', 'gamma_mu', 'd', '|']      # vector current

# 4pt computation scope (the two-hadron-source contraction is the heaviest
# step; these defaults bound its GPU cost — configurable at runtime).
FOURPT_NEV1 = 60      # eigenvector truncation for the 4pt perams / vertices
FOURPT_TSEP = 6       # source-sink separation (reduced from 3pt's 12)
FOURPT_MOM  = [0]     # momenta to compute (0 = P=(0,0,0)); add 1 for Pz=2
FOURPT_SRC_STEP = 2   # sample every 2nd source time (bounded statistics)

# ═══════════════════════════════════════════════════════════════════
# 3pt / 4pt Analysis Parameters
# ═══════════════════════════════════════════════════════════════════

T_SEP = 12          # Source-sink separation for 3pt (lattice units)
T_SEP_3PT = 8       # 3pt/2pt ratio separation (matches v20260803 ratio_analysis)

# ═══════════════════════════════════════════════════════════════════
# OPE (Gluon Operator) Parameters
# ═══════════════════════════════════════════════════════════════════
# Disconnected gluon operator from gauge configs (donghx algorithm):
#   O(z) = Σ_{x⊥} Tr[ F_{μν}(x+z)·W†(z→0)·F̃_{μν}(x)·W(0→z) ]
# The three (μ,ν) components match Calc_ope_unpol.py with zdir=2 (z-axis).

DELTA_Z = 24        # Maximum Wilson-line displacement (z = 0..23)
Z_DIR = 2           # Wilson-line direction index (0=t, 1=z, 2=y, 3=x)
OPE_COMPONENTS = [(0, 1), (3, 0), (3, 1)]   # (μ,ν) pairs
# code_1.py combination: O = -O_30 - O_31 + 2·O_01

# ═══════════════════════════════════════════════════════════════════
# Precision
# ═══════════════════════════════════════════════════════════════════

PRECISION = 'complex64'   # single precision (default for this run)
                           # 'complex128' = double precision

# ═══════════════════════════════════════════════════════════════════
# Output Paths
# ═══════════════════════════════════════════════════════════════════

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_DIR, 'data')
PLOTS_DIR = os.path.join(PROJECT_DIR, 'plots')
LOGS_DIR = os.path.join(PROJECT_DIR, 'logs')
OUTPUT_DIR = os.path.join(PROJECT_DIR, 'output')
AGENT_LOGS_DIR = '/root/PyQCD/logs'   # central logs (user-specified)

# Create output directories
for _d in [DATA_DIR, PLOTS_DIR, LOGS_DIR, OUTPUT_DIR]:
    os.makedirs(_d, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════
# Path helpers
# ═══════════════════════════════════════════════════════════════════


def get_eigen_path(conf_id, t):
    """Full path to the eigenvector binary for (conf_id, time slice t)."""
    return f"{EIGEN_DIR}/{conf_id}/eigvecs_t{t:03d}_{conf_id}"


def get_peram_dir(conf_id):
    """Directory containing the perambulator binaries for a config."""
    return f"{PERAM_DIR}/{conf_id}"


def get_peram_file(conf_id, d_source, t_source):
    """Full path to one perambulator binary (d_source, t_source)."""
    return f"{PERAM_DIR}/{conf_id}/perams.{conf_id}.{d_source}.{t_source}"


def get_gauge_path(conf_id):
    """Full path to the .lime gauge configuration for a config."""
    return f"{GAUGE_DIR}/{ENSEMBLE}_cfg_{conf_id}.lime"


def conf_data_dir(run_dir, conf_id):
    """Per-config output directory under a run."""
    d = os.path.join(run_dir, 'data', f'conf{conf_id}')
    os.makedirs(d, exist_ok=True)
    return d
