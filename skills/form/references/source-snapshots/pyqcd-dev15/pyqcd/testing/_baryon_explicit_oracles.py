"""Independent tiny-Nev numerical oracle for the baryon PJN 3pt wiring.

The expected value below is a literal transcription of the four explicit
``einsum`` contractions in
``refer/sush/lqcddb/examples/contraction.PJN.3pt.numpy.py``.  In particular,
it does not use ``dynamic_contraction`` (or a plan produced by it) to build the
expected value.  The production result is exercised only through
``pyqcd.pipeline._steps._run_3pt``.

PJNNJNP 4pt is deliberately not covered here.  Its available sush example
constructs the result with ``dynamic_contraction`` rather than an independent
finite list of contractions, and uses an axial ``gamma_5 @ gamma_mu`` current
where the current pipeline registers the vector ``gamma_mu`` current.  A
frozen value from that route would therefore not be an independent oracle for
the present observable.
"""

from __future__ import annotations

import numpy as np

from pyqcd.contraction import GammaRegistry, PeramRegistry, VRegistry
from pyqcd.lattice import gamma
from pyqcd.pipeline._config import PJN_CURR, PJN_SINK, PJN_SRC
from pyqcd.pipeline._steps import _run_3pt
from pyqcd.tools import set_backend


def _random_complex(rng: np.random.Generator, shape: tuple[int, ...]):
    """Return a deterministic non-symmetric complex test tensor."""
    return rng.normal(size=shape) + 1j * rng.normal(size=shape)


def _pjn_explicit_terms(
    sink_src,
    cur_src,
    sink_cur,
    gamma_7,
    current,
    sink_vvv,
    cur_vdv,
    src_vvv,
    projector,
    *,
    bilateral: bool = False,
):
    """Evaluate the four sush PJN Wick formulas without a generated plan."""
    if bilateral:
        suffix = ",aX,kY->XYGM"
        tail = (projector, projector)
    else:
        # The reference formula ends in ``ka``.  For the physical P+ used
        # here this equals the bilateral contraction because P+ is symmetric
        # and idempotent.
        suffix = ",ka->GM"
        tail = (projector,)

    common = (gamma_7, current, gamma_7, sink_vvv, cur_vdv, src_vvv)
    # Keep each reference sign adjacent to its literal contraction.  This is
    # intentionally repetitive: a generated table would weaken the oracle.
    return np.asarray([
        -np.einsum(
            "eifj,okpl,ambn,cgdh,ce,Gmo,gi,Mbdf,Mnp,Mhjl" + suffix,
            *(sink_src, cur_src, sink_cur, sink_src) + common + tail,
            optimize=True,
        ),
        +np.einsum(
            "eifj,okpl,agbh,cmdn,ce,Gmo,gi,Mbdf,Mnp,Mhjl" + suffix,
            *(sink_src, cur_src, sink_src, sink_cur) + common + tail,
            optimize=True,
        ),
        +np.einsum(
            "ekfl,oipj,ambn,cgdh,ce,Gmo,gi,Mbdf,Mnp,Mhjl" + suffix,
            *(sink_src, cur_src, sink_cur, sink_src) + common + tail,
            optimize=True,
        ),
        -np.einsum(
            "ekfl,oipj,agbh,cmdn,ce,Gmo,gi,Mbdf,Mnp,Mhjl" + suffix,
            *(sink_src, cur_src, sink_src, sink_cur) + common + tail,
            optimize=True,
        ),
    ])


def _make_pjn_fixture(seed: int = 20260830, nev: int = 2):
    """Build tiny registries whose unequal random entries expose axis swaps."""
    rng = np.random.default_rng(seed)
    peram_shape = (4, 4, nev, nev)
    sink_src = _random_complex(rng, peram_shape)
    cur_src = _random_complex(rng, peram_shape)
    sink_cur = _random_complex(rng, peram_shape)
    sink_vvv = _random_complex(rng, (1, nev, nev, nev))
    cur_vdv = _random_complex(rng, (1, nev, nev))
    src_vvv = _random_complex(rng, (1, nev, nev, nev))

    gamma_7 = np.asarray(gamma(7), dtype=np.complex128)
    current = np.asarray(
        [gamma(mu) for mu in (1, 2, 3, 4)], dtype=np.complex128)
    projector = np.asarray((gamma(0) + gamma(4)) / 2.0,
                           dtype=np.complex128)

    np.testing.assert_allclose(projector.T, projector, rtol=0.0, atol=0.0)
    np.testing.assert_allclose(projector @ projector, projector,
                               rtol=0.0, atol=0.0)

    perams = PeramRegistry()
    perams.register("light", ("tsink", "tsrc"), sink_src)
    perams.register("light", ("tcur0", "tsrc"), cur_src)
    perams.register("light", ("tsink", "tcur0"), sink_cur)

    vertices = VRegistry()
    vertices.register("VVV_0", "tsink", sink_vvv)
    vertices.register("VDV_0", "tcur0", cur_vdv)
    vertices.register("VVV_0", "tsrc", src_vvv)

    gammas = GammaRegistry()
    gammas.register("gamma_7", gamma_7)
    gammas.register("gamma_mu", current)
    gammas.register("Projector", (projector, projector))

    tensors = (sink_src, cur_src, sink_cur, gamma_7, current,
               sink_vvv, cur_vdv, src_vvv, projector)
    return perams, vertices, gammas, tensors


def test_pjn_3pt_matches_four_explicit_wick_contractions():
    """Catch Wick sign/route errors and the former projected-axis ravel bug."""
    set_backend("numpy")
    perams, vertices, gammas, tensors = _make_pjn_fixture()

    terms = _pjn_explicit_terms(*tensors)
    expected = np.sum(terms, axis=0)
    actual = _run_3pt(
        np,
        PJN_SINK,
        PJN_SRC,
        PJN_CURR,
        perams,
        vertices,
        gammas,
        ["M", "M", "M"],
        ["", "G", ""],
    )

    np.testing.assert_allclose(actual, expected[:, 0],
                               rtol=2.0e-12, atol=2.0e-10)

    # Mutation check 1: each independently sourced Wick sign must matter.
    sign_mutation_errors = []
    for diagram in range(4):
        mutated = expected - 2.0 * terms[diagram]
        error = float(np.max(np.abs(mutated[:, 0] - actual)))
        sign_mutation_errors.append(error)
        assert error > 1.0e-6, (
            f"Wick sign mutation {diagram} was not detected: error={error}")

    # Mutation check 2: model the former Projection=True result (XYGM), then
    # the old pipeline's ravel()[:4].  The correct aggregation is the X=Y
    # trace; taking the first four flattened entries selects only X=Y=0.
    bilateral_terms = _pjn_explicit_terms(*tensors, bilateral=True)
    old_xygm = np.sum(bilateral_terms, axis=0)
    traced = np.einsum("XXGM->GM", old_xygm)
    old_ravel = old_xygm.ravel()[:4]
    np.testing.assert_allclose(traced, expected, rtol=2.0e-12, atol=2.0e-10)
    old_ravel_error = float(np.max(np.abs(old_ravel - expected[:, 0])))
    assert old_ravel_error > 1.0e-6, (
        f"old ravel aggregation unexpectedly matched: error={old_ravel_error}")

    scale = max(float(np.max(np.abs(expected[:, 0]))), 1.0)
    return {
        "max_abs_error": float(np.max(np.abs(actual - expected[:, 0]))),
        "max_rel_error": float(np.max(np.abs(actual - expected[:, 0]))) / scale,
        "old_ravel_error": old_ravel_error,
        "min_sign_mutation_error": min(sign_mutation_errors),
    }


def main():
    metrics = test_pjn_3pt_matches_four_explicit_wick_contractions()
    print(
        "PJN explicit oracle PASS: diagrams=4, Nev=2, G=4, M=1, "
        f"max_abs_error={metrics['max_abs_error']:.3e}, "
        f"max_rel_error={metrics['max_rel_error']:.3e}"
    )
    print(
        "mutation check PASS: "
        f"old_ravel_error={metrics['old_ravel_error']:.3e}, "
        f"min_sign_flip_error={metrics['min_sign_mutation_error']:.3e}"
    )
    print(
        "PJNNJNP 4pt explicit oracle: NOT COVERED "
        "(reference expected is dynamic-plan-derived and uses gamma5*gamma_mu, "
        "not the pipeline's vector gamma_mu current)"
    )


if __name__ == "__main__":
    main()
