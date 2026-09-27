"""
Hadron Operator Hermitian Conjugation
=====================================

Functions to compute the Hermitian conjugate of hadron operators,
including baryon and meson operators with gamma matrix insertions.

Computes GAMMA_PROPERTIES (H, T, C signs) and DIQUARK_TRANSPOSE_SIGN
directly from the gamma matrices, rather than hardcoding them.

Adapted from lqcddb contraction/baroperator.py.
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Tuple
from ..lattice._gamma import gamma


# ── Charge conjugation matrix in DR basis: C = γ₄ γ₂ ──────────────

# Get the underlying numpy arrays for computation
_g0 = gamma(0)  # identity
_g1 = gamma(1)  # γ₁
_g2 = gamma(2)  # γ₂
_g3 = gamma(3)  # γ₃
_g4 = gamma(4)  # γ₄
_g5 = gamma(5)  # γ₅

# Move to numpy for offline computation of properties
_g0_np = _g0.get() if hasattr(_g0, 'get') else _g0
_g1_np = _g1.get() if hasattr(_g1, 'get') else _g1
_g2_np = _g2.get() if hasattr(_g2, 'get') else _g2
_g3_np = _g3.get() if hasattr(_g3, 'get') else _g3
_g4_np = _g4.get() if hasattr(_g4, 'get') else _g4
_g5_np = _g5.get() if hasattr(_g5, 'get') else _g5

C_mat = _g4_np @ _g2_np           # Charge conjugation matrix C = γ₄ γ₂
C_inv = C_mat.conj().T             # C^{-1} = C† (C is unitary)


def _H(M):
    """Hermitian conjugate: Γ^H = γ₄ Γ† γ₄"""
    return _g4_np @ M.conj().T @ _g4_np


def _T(M):
    """Transpose: Γ^T"""
    return M.T


def _C(M):
    """Charge conjugation: C^{-1} Γ C"""
    return C_inv @ M @ C_mat


def _sign(M_ref, M_result):
    """Identify sign: if M_result = s * M_ref (s = ±1), return s.

    For non-proportional cases (e.g. parity projectors γ16/γ17 under charge
    conjugation, where C maps P₊→P₋ and the overlap vanishes), returns 0.
    Such matrices never appear as operator gamma insertions in the Wick
    contractions used here (they are only registered as spin projectors), so
    the 0 sentinel is never consulted for actual diagram equivalence.
    """
    num = np.trace(M_ref.conj().T @ M_result)
    den = np.trace(M_ref.conj().T @ M_ref)
    if abs(den) < 1e-12:
        return 0
    ratio = num / den
    if np.abs(ratio.real - 1.0) < 1e-12:
        return +1
    if np.abs(ratio.real + 1.0) < 1e-12:
        return -1
    return 0


# Gamma vector for index-parametrised structures
_gamma_vec = [_g4_np, _g1_np, _g2_np, _g3_np]


def _sigma(mu, nu):
    """σ_{μν} = ½ [γ_μ, γ_ν] (Euclidean convention)"""
    return 0.5 * (_gamma_vec[mu] @ _gamma_vec[nu]
                  - _gamma_vec[nu] @ _gamma_vec[mu])


# Mapping: name → representative 4×4 complex matrix
_MAT = {
    "1":                      _g0_np,
    "gamma_5":                _g5_np,
    "gamma_0":                _g4_np,
    "gamma_1":                _g1_np,
    "gamma_2":                _g2_np,
    "gamma_3":                _g3_np,
    "gamma_4":                _g4_np,
    "gamma_6":                _g2_np @ _g3_np,
    "gamma_7":                _g3_np @ _g1_np,
    "gamma_8":                _g1_np @ _g2_np,
    "gamma_mu":               _g4_np,                    # μ = 0 (time)
    "gamma_5 * gamma_mu":     _g5_np @ _g4_np,           # μ = 0
    "sigma_mu_nu":            _sigma(0, 1),              # (μ,ν) = (0,1)
    "C":                      C_mat,
    "C * gamma_5":            C_mat @ _g5_np,
    "C * gamma_mu":           C_mat @ _g4_np,            # μ = 0
    "C * gamma_5 * gamma_mu": C_mat @ _g5_np @ _g4_np,   # μ = 0
    "C * sigma_mu_nu":        C_mat @ _sigma(0, 1),      # (μ,ν) = (0,1)
}

# Also add gamma_X names that wick_contraction might generate
for i in range(18):
    gname = f"gamma_{i}"
    if gname not in _MAT:
        _MAT[gname] = gamma(i).get() if hasattr(gamma(i), 'get') else gamma(i)

# Compute GAMMA_PROPERTIES: H/T/C transformation signs
GAMMA_PROPERTIES = {}
for name, M in _MAT.items():
    GAMMA_PROPERTIES[name] = {
        "H": (_sign(M, _H(M)), name),
        "T": (_sign(M, _T(M)), name),
        "C": (_sign(M, _C(M)), name),
    }

# Compute DIQUARK_TRANSPOSE_SIGN: (C*Γ)^T = η * (C*Γ)
DIQUARK_TRANSPOSE_SIGN = {}
_diquark_names = [
    "C", "C * gamma_5", "C * gamma_mu",
    "C * gamma_5 * gamma_mu", "C * sigma_mu_nu",
]
for name in _diquark_names:
    D = _MAT[name]
    DIQUARK_TRANSPOSE_SIGN[name] = _sign(D, D.T)


@dataclass
class Gamma:
    """Wrapper providing H/T/C queries for a named gamma structure."""
    expr: str

    def H(self):
        if self.expr not in GAMMA_PROPERTIES:
            raise ValueError(f"Unknown gamma structure: {self.expr}")
        return GAMMA_PROPERTIES[self.expr]["H"]

    def T(self):
        if self.expr not in GAMMA_PROPERTIES:
            raise ValueError(f"Unknown gamma structure: {self.expr}")
        return GAMMA_PROPERTIES[self.expr]["T"]

    def C(self):
        if self.expr not in GAMMA_PROPERTIES:
            raise ValueError(f"Unknown gamma structure: {self.expr}")
        return GAMMA_PROPERTIES[self.expr]["C"]


# ═══════════════════════════════════════════════════════════════════
# Operator parsing utilities
# ═══════════════════════════════════════════════════════════════════

def is_separator(x: str) -> bool:
    """Check if token is a hadron delimiter '|'."""
    return x == "|"


def is_gamma(x: str) -> bool:
    """Check if token is a known gamma structure name."""
    return x in GAMMA_PROPERTIES


def is_quark(x: str) -> bool:
    """Check if token is a quark field (not separator, not gamma)."""
    if is_separator(x):
        return False
    if is_gamma(x):
        return False
    return True


def dagger_quark(q: str) -> str:
    """Toggle dagger flag: 'q' ↔ 'q^d'."""
    if "^d" in q:
        return q.replace("^d", "")
    return q + "^d"


def split_hadrons(tokens: List[str]) -> List[List[str]]:
    """Split flat token list into individual hadrons delimited by '|'."""
    hadrons = []
    current = []
    inside = False
    for x in tokens:
        if x == "|" and not inside:
            current = ["|"]
            inside = True
        elif x == "|" and inside:
            current.append("|")
            hadrons.append(current)
            inside = False
        else:
            current.append(x)
    return hadrons


def classify_structure(body: List[str]) -> str:
    """Classify hadron body: 'meson' (2q), 'baryon' (3q), or 'generic'."""
    n_quark = sum(is_quark(x) for x in body)
    if n_quark == 2:
        return "meson"
    if n_quark == 3:
        return "baryon"
    return "generic"


def hermitian_gamma_chain(gammas: List[str]) -> Tuple[int, List[str]]:
    """Hermitian conjugate of gamma chain: (G₁G₂)^H = G₂^H G₁^H."""
    sign = 1
    new_chain = []
    for g in gammas[::-1]:
        GG = Gamma(g)
        s, gg = GG.H()
        sign *= s
        new_chain.append(gg)
    return sign, new_chain


# ═══════════════════════════════════════════════════════════════════
# Hadron operator conjugation
# ═══════════════════════════════════════════════════════════════════

def conjugate_meson(quarks, gammas):
    """Conjugate meson: q̄Γq → q̄Γ^H q."""
    sign = 1
    gamma_sign, new_gammas = hermitian_gamma_chain(gammas)
    sign *= gamma_sign
    qbar = dagger_quark(quarks[1])
    q = dagger_quark(quarks[0])
    return [sign] + ["|", qbar] + new_gammas + [q, "|"]


def conjugate_baryon(quarks, gammas):
    """Conjugate baryon: (q₁^T C Γ q₂) q₃ → (q̄₁ C Γ q̄₂) q̄₃."""
    sign = -1
    gamma_sign, new_gammas = hermitian_gamma_chain(gammas)
    sign *= gamma_sign
    for g in gammas:
        if g in DIQUARK_TRANSPOSE_SIGN:
            sign *= DIQUARK_TRANSPOSE_SIGN[g]
    q1 = dagger_quark(quarks[1])
    q2 = dagger_quark(quarks[2])
    q3 = dagger_quark(quarks[0])
    return [sign] + ["|", q1] + new_gammas + [q2, q3, "|"]


def conjugate_generic(quarks, gammas):
    """Conjugate generic multi-quark operator."""
    sign = 1
    gamma_sign, new_gammas = hermitian_gamma_chain(gammas)
    sign *= gamma_sign
    new_quarks = [dagger_quark(q) for q in quarks[::-1]]
    return [sign] + ["|"] + new_quarks + new_gammas + ["|"]


def conjugate_single_hadron(tokens: List[str]):
    """Conjugate a single hadron token list."""
    if tokens[0] != "|" or tokens[-1] != "|":
        raise ValueError("Hadron must start/end with '|'")
    body = tokens[1:-1]
    quarks = []
    gammas = []
    for x in body:
        if is_quark(x):
            quarks.append(x)
        elif is_gamma(x):
            gammas.append(x)
        else:
            raise ValueError(f"Unknown token: {x}")
    structure = classify_structure(body)
    if structure == "meson":
        return conjugate_meson(quarks, gammas)
    elif structure == "baryon":
        return conjugate_baryon(quarks, gammas)
    else:
        return conjugate_generic(quarks, gammas)


def conjugate_operator(tokens: List[str]):
    """Conjugate a full operator expression with one or more hadrons.

    Example: ``conjugate_operator(['|', 'u^d', 'gamma_5', 'd', '|'])``
    returns ``[1.0, '|', 'd^d', 'gamma_5', 'u', '|']``

    Parameters
    ----------
    tokens : list of str
        Operator token list with '|' delimiters.

    Returns
    -------
    list
        ``[sign, token1, token2, ...]`` — conjugate operator with overall sign.
    """
    hadrons = split_hadrons(tokens)
    total_sign = 1
    final_tokens = []
    for hadron in hadrons:
        result = conjugate_single_hadron(hadron)
        total_sign *= result[0]
        final_tokens.extend(result[1:])
    return [float(total_sign)] + final_tokens


def transpose_gamma(gamma_expr: str):
    """Return the transpose sign of a gamma structure: (sign, name)."""
    G = Gamma(gamma_expr)
    return G.T()


def charge_conjugation_gamma(gamma_expr: str):
    """Return the charge conjugation sign of a gamma structure: (sign, name)."""
    G = Gamma(gamma_expr)
    return G.C()


def diquark_symmetry(gamma_expr: str):
    """Return diquark transpose symmetry sign η: (C*Γ)^T = η·(C*Γ)."""
    if gamma_expr not in DIQUARK_TRANSPOSE_SIGN:
        raise ValueError(f"{gamma_expr} is not a diquark structure")
    return DIQUARK_TRANSPOSE_SIGN[gamma_expr]


def parity_and_boundary(contrac_nucl_matrix, Nt: int):
    """双宇称投影 + 反周期边界符号翻转（照抄 zhangxin workflow
    ``apply_parity_and_boundary``，源出 donghx 2pt 代码）。

    P± = ½(γ₀ ± γ₄)（DR 基 gamma(0)=identity、gamma(4)=temporal）；
    收缩矩阵按 "li,...il->..." 收缩后得 pp/pm 两组投影关联。
    反周期时间边界约定：t_sink < t_source 时 pp 翻号，
    t_sink > t_source 时 pm 翻号。

    Args:
        contrac_nucl_matrix: (..., t_sink, t_source, i, l) 收缩矩阵
            （末两轴为自旋指标 i,l；支持批量前置维）。
        Nt: 时间格点数。
    Returns:
        (pp, pm)，形状 (..., Nt, Nt)。
    """
    from ..tools._backend import get_backend

    cp = get_backend()
    matrix_pplus = 0.5 * (gamma(0) + gamma(4))
    matrix_pminus = 0.5 * (gamma(0) - gamma(4))

    pp = cp.einsum("li,...il->...", matrix_pplus, contrac_nucl_matrix)
    pm = cp.einsum("li,...il->...", matrix_pminus, contrac_nucl_matrix)

    t_sink = np.arange(Nt).reshape(Nt, 1)
    t_source = np.arange(Nt).reshape(1, Nt)
    sign_pp = np.where(t_sink < t_source, -1.0, 1.0)
    sign_pm = np.where(t_sink > t_source, -1.0, 1.0)
    pp = pp * sign_pp
    pm = pm * sign_pm
    return pp, pm
