"""
SU(2) Clebsch–Gordan 系数（自旋/同位旋角动量代数）
====================================================

整合 refer/sush/lqcddb/src/lqcddb/base/cg_coeff.py 的逻辑
（SU2combine / SU2decompose），改用 Racah 闭式公式的纯 Python 实现——
不依赖 sympy（阶乘比经 Fraction 精确有理运算，最终一次开方取 double，
精度 ~1e-15；不 import refer/）。

半整数角动量内部以倍数整数 (2j, 2m) 表示，避免浮点比较问题。

    - cg_coefficient(j1, m1, j2, m2, J, M)：单个 CG 系数；
    - SU2combine(states)：多粒子级联耦合（记录中间 J 以区分简并态）；
    - SU2decompose(j_list, target, intermediate_Js)：耦合态分解为直积基。

用途：多重态/isospin 组合插符对（如 I=0/1/5 重子道）收缩的前置权重表。
"""
from __future__ import annotations

from fractions import Fraction
from functools import lru_cache
from math import factorial, sqrt

__all__ = ["cg_coefficient", "SU2combine", "SU2decompose"]


def _two(x):
    """半整数 → 倍数整数。"""
    t = int(round(2 * float(x)))
    if abs(2 * float(x) - t) > 1e-9:
        raise ValueError(f"非半整数角动量: {x}")
    return t


@lru_cache(maxsize=None)
def _cg_two(j1, m1, j2, m2, J, M):
    """倍数整数参数的 Racah 公式（Fraction 精确求和，带符号）。

    输入为 2j/2m 倍数域；Racah 公式的全部阶乘宗量
    （j1+j2−J、j1±m1、J±M 等）在物理域恒为非负整数，
    即倍数域偶数——以 F(n2)=((n2/2)!) 求值；k 以物理步长（倍数域 2）循环。

    CG = √pref · Σ_k (−1)^k / [k!(j1+j2−J−k)!(j1−m1−k)!(j2+m2−k)!
                                (J−j2+m1+k)!(J−j1−m2+k)!]
    pref = (2J+1)·Δ(j1,j2,J)·Π(m 相关阶乘)，恒正 ⇒ 符号由级数给出。
    """
    if not (abs(m1) <= j1 and abs(m2) <= j2 and abs(M) <= J):
        return 0.0
    if m1 + m2 != M:
        return 0.0
    if not (abs(j1 - j2) <= J <= j1 + j2):
        return 0.0
    if (j1 + j2 + J) % 2:
        return 0.0          # 物理域 j1+j2+J 非整数（倍数域为奇）→ 禁戒耦合

    def F(n2):
        """倍数域表达式 n2 → 物理整数阶乘（n2//2!）。"""
        return Fraction(factorial(n2 // 2), 1)

    tri = F(j1 + j2 - J) * F(j1 - j2 + J) * F(-j1 + j2 + J) \
        / F(j1 + j2 + J + 2)
    pref = Fraction(J + 1, 1) * tri \
        * F(j1 + m1) * F(j1 - m1) \
        * F(j2 + m2) * F(j2 - m2) \
        * F(J + M) * F(J - M)
    total = Fraction(0)
    k_lo = max(0, j2 - j1 - M, j1 + m2 - J)
    k_hi = min(j1 + j2 - J, j1 - m1, j2 + m2)
    for k2 in range(k_lo, k_hi + 1, 2):          # 倍数域步长 2 = 物理步长 1
        total += Fraction((-1) ** (k2 // 2), 1) / (
            F(k2) * F(j1 + j2 - J - k2)
            * F(j1 - m1 - k2) * F(j2 + m2 - k2)
            * F(J - j2 + m1 + k2) * F(J - j1 - m2 + k2))
    if total == 0:
        return 0.0
    val_sq = float(pref * total * total)
    sgn = 1.0 if total > 0 else -1.0
    return sgn * val_sq ** 0.5


def cg_coefficient(j1, m1, j2, m2, J, M):
    """单个 SU(2) CG 系数 ⟨j1 m1; j2 m2 | J M⟩（float，精确到 ~1e-15）。

    符号约定为 Condon–Shortley（Edmonds）。
    """
    return _cg_two(_two(j1), _two(m1), _two(j2), _two(m2),
                   _two(J), _two(M))


def SU2combine(states):
    """多粒子级联耦合：输入 [(j1,m1),(j2,m2),...]，输出 {(J,M,中间J): 系数}。

    与 lqcddb 一致：N>2 时键中记录除最后一步外的全部中间 J 元组，
    用于唯一标识简并的正交态；系数为路径累乘（多条路径叠加）。
    """
    if not states:
        return {}
    parsed = [(_two(j), _two(m)) for j, m in states]
    j1, m1 = parsed[0]
    current = {(j1, m1, ()): 1.0}

    for step_i in range(1, len(parsed)):
        j2, m2 = parsed[step_i]
        nxt = {}
        for (jp, mp, int_js), coeff_prev in current.items():
            for J in range(abs(jp - j2), jp + j2 + 1, 2):
                c = cg_coefficient(jp / 2, mp / 2, j2 / 2, m2 / 2,
                                   J / 2, (mp + m2) / 2)
                if c != 0.0:
                    new_int = int_js + (J,) if step_i < len(parsed) - 1 \
                        else int_js
                    key = (J, mp + m2, new_int)
                    nxt[key] = nxt.get(key, 0.0) + coeff_prev * c
        current = nxt
    return {(J / 2, M / 2, tuple(x / 2 for x in int_js)): c
            for (J, M, int_js), c in current.items() if c != 0.0}


def SU2decompose(j_list, target, intermediate_Js=None):
    """耦合态分解：输入各粒子总角动量与目标 (J,M)，输出 {(m_1..m_N): 系数}。

    N>2 时必须提供 intermediate_Js 序列以唯一确定耦合路径。
    """
    j_two = [_two(j) for j in j_list]
    J_t, M_t = _two(target[0]), _two(target[1])
    int_two = None if intermediate_Js is None \
        else [_two(j) for j in intermediate_Js]

    if len(j_two) == 1:
        if J_t == j_two[0] and abs(M_t) <= J_t:
            return {(M_t / 2,): 1.0}
        return {}
    if len(j_two) > 2 and int_two is None:
        raise ValueError("N>2 时必须提供 intermediate_Js")
    if len(j_two) == 2:
        int_two = []

    j_last = j_two[-1]
    j_prev = int_two[-1] if int_two else j_two[0]
    results = {}

    for two_m_last in range(-j_last, j_last + 1, 2):
        m_prev = M_t - two_m_last
        if abs(m_prev) <= j_prev:
            cg = cg_coefficient(j_prev / 2, m_prev / 2, j_last / 2,
                                two_m_last / 2, J_t / 2, M_t / 2)
            if cg != 0.0:
                prev = SU2decompose(
                    [x / 2 for x in j_two[:-1]], (j_prev / 2, m_prev / 2),
                    [x / 2 for x in int_two[:-1]] if int_two else None)
                for m_tuple, coeff_prev in prev.items():
                    key = m_tuple + (two_m_last / 2,)
                    results[key] = results.get(key, 0.0) + coeff_prev * cg
    return {k: v for k, v in results.items() if v != 0.0}
