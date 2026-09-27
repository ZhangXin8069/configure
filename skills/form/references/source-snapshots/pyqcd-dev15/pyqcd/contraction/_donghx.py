"""donghx 质子 2pt 显式缩并适配层。

donghx 的 2pt 实现先把一个 light perambulator 左右夹上插值矩阵，随后用
两项颜色 epsilon 收缩得到固定 ``(t_sink, t_source)`` 的 Dirac 矩阵。该
排列与通用 Wick 字符串的 gamma 插入位置并不相同，因此这里保留一个小而
明确的参考适配层；它不改变通用 ``dynamic_contraction`` 的费米子约定。

输入约定（固定一个时间对）：

* ``peram``: ``(4, 4, Nev, Nev)``，轴为
  ``(d_sink, d_source, ev_sink, ev_source)``；
* ``vvv_sink``/``vvv_source``: ``(Nev, Nev, Nev)``，后者应由调用方按
  参考实现预先取共轭，例如 ``VVV[t_source].conj()``；
* 返回 ``(4, 4)``，轴为 ``(i, l)``。

支持的 ``variant`` 与 refer/donghx 的插值矩阵选择一致：
``Cg5``、``Cg5g3``、``Cg5g4``、``offdiag01``、``offdiag02``、
``offdiag12``。
"""

from __future__ import annotations

from ..lattice._gamma import gamma
from ..tools._backend import get_backend
from ..tools._base import cached_contract


_VARIANT_NAMES = {
    "Cg5",
    "Cg5g3",
    "Cg5g4",
    "offdiag01",
    "offdiag02",
    "offdiag12",
}


def _interpolator_pair(variant):
    """返回 refer/donghx 的 ``(interProject1, interProject2)``。"""
    if variant not in _VARIANT_NAMES:
        choices = ", ".join(sorted(_VARIANT_NAMES))
        raise ValueError(f"unknown donghx 2pt variant {variant!r}; choose {choices}")

    g7 = gamma(7)
    g3 = gamma(3)
    g4 = gamma(4)
    if variant == "Cg5":
        return g7, g7
    if variant == "Cg5g3":
        projector = g7 @ g3
        return projector, projector
    if variant == "Cg5g4":
        projector = g7 @ g4
        return projector, projector
    if variant == "offdiag01":
        return g7 @ g3, g7
    if variant == "offdiag02":
        return g7 @ g4, g7
    return g7 @ g3, g7 @ g4


def _validate_shapes(peram, vvv_sink, vvv_source):
    """校验固定时间对的轴序，避免把完整时间轴误当作 Dirac 轴。"""
    if len(peram.shape) != 4 or peram.shape[:2] != (4, 4):
        raise ValueError(
            "peram must have shape (4, 4, Nev, Nev), "
            f"got {peram.shape}"
        )
    if len(vvv_sink.shape) != 3 or len(vvv_source.shape) != 3:
        raise ValueError(
            "vvv_sink and vvv_source must have shape (Nev, Nev, Nev), "
            f"got {vvv_sink.shape} and {vvv_source.shape}"
        )
    nev = peram.shape[2:]
    expected = (nev[0], nev[0], nev[0])
    if nev[0] != nev[1] or vvv_sink.shape != expected \
            or vvv_source.shape != expected:
        raise ValueError(
            "peram and VVV eigenvector axes are incompatible: "
            f"peram={peram.shape}, vvv_sink={vvv_sink.shape}, "
            f"vvv_source={vvv_source.shape}"
        )


def contract_donghx_2pt_pair(peram, vvv_sink, vvv_source,
                             variant="Cg5g4", optimize="auto"):
    """复现 donghx 固定时间对的两项质子 2pt 缩并。

    Parameters
    ----------
    peram : ndarray-like, shape (4, 4, Nev, Nev)
        一个 ``(t_sink, t_source)`` 时间对的 light perambulator。
    vvv_sink, vvv_source : ndarray-like, shape (Nev, Nev, Nev)
        汇、源重子顶点。源顶点是否共轭由调用方决定，以显式保留参考
        实现的 ``np.conj(VVV_sink[t_source])`` 语义。
    variant : str
        插值矩阵变体，见模块说明。
    optimize : str or bool
        传给 ``cached_contract`` 的 einsum 路径选项。

    Returns
    -------
    ndarray-like, shape (4, 4)
        ``term1 - term2`` 的未投影 Dirac 矩阵。

    Notes
    -----
    公式直接对应 refer/donghx 2pt 脚本：

    ``CG5peram_uCG5 = contract("gh,hkbe,jk->gjbe", ...)``（固定一个
    ``t_sink`` 时间对后去掉脚本中的首个 ``t`` 轴）；

    ``term1 = contract("abc,gjad,gjbe,ilcf,def->il", ...)``；

    ``term2 = contract("abc,glaf,gjbe,ijcd,def->il", ...)``。
    """
    backend = get_backend()
    peram = backend.asarray(peram)
    vvv_sink = backend.asarray(vvv_sink)
    vvv_source = backend.asarray(vvv_source)
    _validate_shapes(peram, vvv_sink, vvv_source)

    inter_projector1, inter_projector2 = _interpolator_pair(variant)
    transformed = cached_contract(
        "gh,hkbe,jk->gjbe",
        inter_projector1,
        peram,
        inter_projector2,
        optimize=optimize,
    )
    term1 = cached_contract(
        "abc,gjad,gjbe,ilcf,def->il",
        vvv_sink,
        peram,
        transformed,
        peram,
        vvv_source,
        optimize=optimize,
    )
    term2 = cached_contract(
        "abc,glaf,gjbe,ijcd,def->il",
        vvv_sink,
        peram,
        transformed,
        peram,
        vvv_source,
        optimize=optimize,
    )
    return term1 - term2


__all__ = ["contract_donghx_2pt_pair"]
