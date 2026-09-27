from argparse import Namespace
"""蒸馏收缩引擎：自动 Wick 收缩、重子算符、顺序传播子、动态收缩。"""
from argparse import Namespace

from ._autowick import wick_contraction, identify_equivalent_diagrams
from ._baroperator import (
    split_hadrons, classify_structure, conjugate_operator, dagger_quark,
    parity_and_boundary,
)
from ._seqperam import seq_peram
from ._donghx import contract_donghx_2pt_pair
from ._wickplot import plot_figure_wick
from ._dynamic import PeramRegistry, VRegistry, GammaRegistry, dynamic_contraction, clear_plan_cache

__all__ = [
    "wick_contraction", "identify_equivalent_diagrams",
    "split_hadrons", "classify_structure", "conjugate_operator", "dagger_quark",
    "parity_and_boundary",
    "seq_peram", "contract_donghx_2pt_pair", "plot_figure_wick",
    "PeramRegistry", "VRegistry", "GammaRegistry", "dynamic_contraction",
    "clear_plan_cache",
]

Namespace.__module__ = "pyqcd.contraction"
