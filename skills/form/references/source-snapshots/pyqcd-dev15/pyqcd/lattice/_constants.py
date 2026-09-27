"""
Physical and Lattice QCD Constants
==================================

Fundamental constants used across all modules. Adapted from lqcddb constant/constant.py.

Constants
---------
Nc : int = 3
    Number of colors (SU(3) gauge group).
Ns : int = 4
    Number of spin (Dirac) components.
Nd : int = 4
    Number of spacetime dimensions.
fm2GeV : float
    Conversion factor from fm⁻¹ to GeV: 0.1973269804 GeV·fm.
"""

# ── Group theory constants ─────────────────────────────────────────
Nc = 3    # Number of colors (SU(3) QCD)
Ns = 4    # Number of spin (Dirac) components
Nd = 4    # Number of spacetime dimensions (t, z, y, x)

# ── Unit conversion ────────────────────────────────────────────────
# ℏc = 0.1973269804 GeV·fm  →  1 fm⁻¹ = 0.1973269804 GeV
fm2GeV = 0.1973269804

# ── Lattice ensemble parameters (L24x72, β=6.20) ──────────────────
# Lattice spacing a ≈ 0.105 fm at β=6.20 for the CLQCD ensemble
# a⁻¹ ≈ 1.88 GeV
LATTICE_SPACING = 0.1053   # fm
INV_LATTICE_SPACING = fm2GeV / LATTICE_SPACING  # ≈ 1.874 GeV
