from argparse import Namespace
"""管线编排：集中配置 + 步骤调度（蒸馏→OPE→分析→梯度流 TMD）。"""
from ._config import (
    ENSEMBLE, NX, NY, NZ, NT, ALttc, A_INV, FM2GEV, CONF_IDS,
    NEV, NEV1, MOM_SINK_VDV, MOM_SINK_VVV, DELTA_Z, Z_DIR, OPE_COMPONENTS,
    PRECISION, T_SEP, T_SEP_3PT, PION_SINK, PION_SRC, PROTON_SINK, PROTON_SRC,
    NEUTRON_SINK, NEUTRON_SRC, PP_SINK, PP_SRC, PN_SINK, PN_SRC,
    PJN_SINK, PJN_CURR, PJN_SRC,
)
from ._runner import make_run_dir, step_env, step_tmd, run_pipeline
from ._gradient_flow_gluon import run_gradient_flow_gluon_ope
from ._validate import (
    progress_log, ProgressLog, check_raw_data, check_input_arrays,
    check_files_existence,
)

__all__ = [
    "check_files_existence",
    "ENSEMBLE", "NX", "NY", "NZ", "NT", "ALttc", "A_INV", "FM2GEV", "CONF_IDS",
    "NEV", "NEV1", "MOM_SINK_VDV", "MOM_SINK_VVV", "DELTA_Z", "Z_DIR",
    "OPE_COMPONENTS", "PRECISION", "T_SEP", "T_SEP_3PT",
    "PION_SINK", "PION_SRC", "PROTON_SINK", "PROTON_SRC",
    "NEUTRON_SINK", "NEUTRON_SRC", "PP_SINK", "PP_SRC", "PN_SINK", "PN_SRC",
    "PJN_SINK", "PJN_CURR", "PJN_SRC",
    "make_run_dir", "step_env", "step_tmd", "run_pipeline",
    "run_gradient_flow_gluon_ope",
    "progress_log", "ProgressLog", "check_raw_data", "check_input_arrays",
]

Namespace.__module__ = "pyqcd.pipeline"
