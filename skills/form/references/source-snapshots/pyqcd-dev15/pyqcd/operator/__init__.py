from argparse import Namespace
"""胶子算符：Clover 场强张量 + Wilson 线的非定域胶子 OPE 算符（梯度流 TMD-PDF 的核心）。

本模块实现 donghx 的胶子 OPE 构造（``compute_ope.py`` 照抄逻辑），
并扩展提供 ``staple`` 型 Wilson 线算符（TMD 用，b_⊥ 方向位移）。
"""
from ._gluon_ope import (
    FieldStrengthCache, OPEChannelSpec, plaquette_clover,
    compute_dual_field_strength, gluon_ope_operator_z0, gluon_ope_channel,
    gluon_ff_operator_z0,
    get_ope_lorentz_pairs, staple_operator,
    read_gauge_lime, resolve_ildg_binary_record,
)
from ._helicity import (
    plaquette_dual_stack, helicity_two_field_operator,
)
from ._gradient_flow_gluon_ope import (
    OPE_SCHEMA as GRADIENT_FLOW_OPE_SCHEMA,
    OPE_STATUS as GRADIENT_FLOW_OPE_STATUS,
    FIELD_PROJECTIONS as GRADIENT_FLOW_FIELD_PROJECTIONS,
    CHANNELS as GRADIENT_FLOW_CHANNELS,
    ORIENTATIONS as GRADIENT_FLOW_ORIENTATIONS,
    COMPONENTS as GRADIENT_FLOW_COMPONENTS,
    OPE_AXES as GRADIENT_FLOW_OPE_AXES,
    flowed_gluon_ope, gradient_flow_gluon_ope,
    validate_gradient_flow_gluon_ope,
    select_gradient_flow_gluon_component,
    save_gradient_flow_gluon_ope, load_gradient_flow_gluon_ope,
)

__all__ = [
    "FieldStrengthCache", "OPEChannelSpec", "plaquette_clover",
    "compute_dual_field_strength", "gluon_ope_operator_z0",
    "gluon_ope_channel",
    "gluon_ff_operator_z0", "get_ope_lorentz_pairs", "staple_operator",
    "read_gauge_lime", "resolve_ildg_binary_record",
    "plaquette_dual_stack", "helicity_two_field_operator",
    "GRADIENT_FLOW_OPE_SCHEMA", "GRADIENT_FLOW_OPE_STATUS",
    "GRADIENT_FLOW_FIELD_PROJECTIONS", "GRADIENT_FLOW_CHANNELS",
    "GRADIENT_FLOW_ORIENTATIONS", "GRADIENT_FLOW_COMPONENTS",
    "GRADIENT_FLOW_OPE_AXES", "flowed_gluon_ope",
    "gradient_flow_gluon_ope", "validate_gradient_flow_gluon_ope",
    "select_gradient_flow_gluon_component",
    "save_gradient_flow_gluon_ope", "load_gradient_flow_gluon_ope",
]

Namespace.__module__ = "pyqcd.operator"
