"""
PyQCD GPU Pipeline Library (docker-v20260803)
=====================================================

Standalone distillation contraction framework adapted from lqcddb.
All modules are self-contained — no imports from lqcddb.

Modules
-------
- backend: GPU/CPU backend switching (CuPy/NumPy)
- constants: Physical and lattice constants (Nc, Ns, Nd, fm2GeV)
- base_functions: Cached einsum, Levi-Civita, ArraySlicer, momentum list
- gamma_matrix: DeGrand-Rossi gamma matrices (18 types)
- sigma_matrix: Pauli matrices
- io_readers: Binary eigenvector and perambulator file readers
- vertex: Vertex functions (VdV, VVV, phase factors, omega weights)
- autowick: Automatic Wick contraction enumeration
- baroperator: Hadron operator Hermitian conjugation
- seqperam: Sequential perambulator (gamma_5 time-reversal)
- dynamic: Dynamic contraction with registries
- analyse: Statistical analysis (Jackknife, Bootstrap, meff, ratio_3pt)
"""

__version__ = "0.1.0"
