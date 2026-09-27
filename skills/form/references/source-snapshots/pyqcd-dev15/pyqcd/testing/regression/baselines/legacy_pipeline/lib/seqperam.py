"""
Sequential Perambulator (γ₅ Time-Reversal)
==========================================

Computes the sequential perambulator from the original perambulator
using γ₅-Hermiticity:

    τ_{seq}(t, t_src) = γ₅ τ(t_src, t)† γ₅

This provides the time-reversed propagator needed when the source
and sink time orderings are swapped in Wick contractions.

Adapted from lqcddb contraction/seqperam.py.
"""

from .base_functions import cached_contract
from .gamma_matrix import gamma


def seq_peram(peram):
    """Compute the sequential (time-reversed) perambulator.

    Applies γ₅-Hermiticity to reverse the source→sink direction:

        peram_seq(t_sink, t_source) = γ₅ · peram(t_source, t_sink)† · γ₅

    The perambulator convention is:
        peram[t_sink, d_sink, d_source, ev_sink, ev_source]
    where the first axis (t_sink) varies with sink time for fixed source.

    Parameters
    ----------
    peram : ndarray, shape (T, 4, 4, Nev, Nev) or (..., T, 4, 4, Nev, Nev)
        Original perambulator. The time axis is the first (or second-to-last
        of the leading batch dimensions) axis.
        Dirac indices: (d_sink=4, d_source=4).

    Returns
    -------
    ndarray, same shape as input
        Sequential perambulator: γ₅ · peram† · γ₅.
        Hermitian conjugation swaps ev_sink↔ev_source and Dirac indices,
        while γ₅ multiplication handles the spin structure.

    Notes
    -----
    The einsum pattern 'ab,...bcef,cd->...dafe' performs:
        Σ_{b,c} (γ₅)_{a,b} · peram*_{...,c,b,e,f} · (γ₅)_{c,d}
    where:
        a,d: Dirac indices (output)
        b,c: contracted Dirac indices
        e,f: eigenvector indices

    Complex conjugation of peram handles the Hermitian conjugate.
    """
    return cached_contract(
        'ab,...bcef,cd->...dafe',
        gamma(5), peram.conj(), gamma(5)
    )
