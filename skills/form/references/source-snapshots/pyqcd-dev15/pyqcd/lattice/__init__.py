"""格点基础：物理常数、DeGrand-Rossi γ 矩阵、Pauli σ 矩阵。"""
from argparse import Namespace

from ._constants import Nc, Ns, Nd, fm2GeV, LATTICE_SPACING, INV_LATTICE_SPACING
from ._gamma import gamma, GAMMA_PROPERTIES, tran_indx_to_gamma
from ._sigma import sigma, Mom_times_sigma
from ._cg import cg_coefficient, SU2combine, SU2decompose

__all__ = [
    "Nc", "Ns", "Nd", "fm2GeV", "LATTICE_SPACING", "INV_LATTICE_SPACING",
    "gamma", "GAMMA_PROPERTIES", "tran_indx_to_gamma",
    "sigma", "Mom_times_sigma",
    "cg_coefficient", "SU2combine", "SU2decompose",
]

Namespace.__module__ = "pyqcd.lattice"
