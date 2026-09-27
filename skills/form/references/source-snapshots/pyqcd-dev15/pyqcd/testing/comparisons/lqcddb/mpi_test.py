"""MPI 搬运层对照单测：pyqcd.parallel._mpi_transport ↔ lqcddb.base.mpi_init。

运行：mpirun --allow-run-as-root -np 3 \
    python -m pyqcd.testing.comparisons.lqcddb.mpi_test
（np=3 质数以触发 TScatter 余量路径。）
"""
import sys

import numpy as np

from ..common.ref_bridge import load_lqcddb


def results():
    return []


def check(res, name, a, b, exact=True):
    if isinstance(a, tuple) or isinstance(b, tuple):
        ok = len(a) == len(b) and all(
            check_one(x, y) for x, y in zip(a, b))
    else:
        ok = check_one(a, b)
    res.append((name, ok))


def check_one(a, b):
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        a, b = np.asarray(a), np.asarray(b)
        return a.shape == b.shape and bool(np.array_equal(a, b))
    return a == b


def main():
    res = []
    rank = sys.modules.get("_RANK")

    # ---- 参照与被测模块 ----
    load_lqcddb()
    import lqcddb.base.mpi_init as R
    from pyqcd.parallel import _mpi_transport as P

    assert R.getMPISize() == P.getMPISize() == 3
    assert R.getMPIRank() == P.getMPIRank()

    # ---- 网格辅助 ----
    for gs in ([1, 1, 1, 3], [1, 1, 3, 1], [3, 1, 1, 1], [1, 3, 1, 1]):
        R.initGrid(list(gs)); P.initGrid(list(gs))
        check(res, f"coord{gs}", P.getGridCoord(), R.getGridCoord())
        rk = P.getRankFromCoord(P.getGridCoord(), list(gs))
        check(res, f"rankFromCoord{gs}", rk,
              R.getRankFromCoord(R.getGridCoord(), list(gs)))

    gd_r = R.getDefaultGrid(3, [24, 24, 24, 72])
    gd_p = P.getDefaultGrid(3, [24, 24, 24, 72])
    check(res, "defaultGrid", gd_p, gd_r)

    # ---- tlist ----
    for t in (7, [0, 5, 11, 30], np.arange(0, 9)):
        for gt in ("find", "TScatter"):
            r_ = R.get_mpi_tlist(72, t, gtype=gt)
            p_ = P.get_mpi_tlist(72, t, gtype=gt)
            check(res, f"tlist-{gt}-{str(t)[:12]}", p_, r_)

    # ---- get_mpi_data 八模式（数据按秩差异化，保证可分辨）----
    N = 12
    data = (np.arange(N * 4, dtype=np.float64)
            .reshape(N, 4) + 1j * np.arange(N * 4).reshape(N, 4) * 0.5)

    for mode, kw in [
        ("Gather", {}), ("Allgather", {}), ("Bcast", {}),
        ("TGather", {}), ("TScatter", {}), ("Transport", {}),
        ("Send", {"recv_rank": 2}),
    ]:
        rd = R.get_mpi_data(data.copy(), mdtype=mode, root=0, **kw)
        pd = P.get_mpi_data(data.copy(), mdtype=mode, root=0, **kw)
        check(res, f"mpi_data-{mode}", pd, rd)

    # Scatter：轴长需整除 3 → 用 axis=0、N=12 ✓
    rs = R.get_mpi_data(data.copy(), mdtype="Scatter", root=0, axis=0)
    ps_ = P.get_mpi_data(data.copy(), mdtype="Scatter", root=0, axis=0)
    check(res, "mpi_data-Scatter", ps_, rs)

    # TScatter 非整除余量路径：axis=0、N=8
    d8 = data[:8]
    rt = R.get_mpi_data(d8.copy(), mdtype="TScatter", root=0, axis=0)
    pt = P.get_mpi_data(d8.copy(), mdtype="TScatter", root=0, axis=0)
    check(res, "mpi_data-TScatter-rem", pt, rt)

    ok = all(v for _, v in res)
    print(f"[rank {rank}] PASS {sum(1 for _, v in res if v)}/{len(res)}")
    for n_, v_ in res:
        if not v_:
            print(f"  FAIL: {n_}")
    sys.stdout.flush()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    class _Mod:
        pass
    m = _Mod()
    m.RANK = __import__("mpi4py", fromlist=["MPI"]).MPI.COMM_WORLD.Get_rank()
    sys.modules["_RANK"] = m
    main()
