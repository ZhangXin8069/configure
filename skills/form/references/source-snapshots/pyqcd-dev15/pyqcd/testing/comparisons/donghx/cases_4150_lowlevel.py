"""组态 4150 的低层 donghx/PyQCD 对照案例。

这里的参考侧函数只在测试进程中重写参考脚本中的数学式；不把 refer 目录作为
PyQCD 业务依赖。真实大数组按案例懒加载，避免 build 阶段占用内存。
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from ..common import datalib
from ..common.harness import Case
from ..common.ref_bridge import load_donghx


CONF = 4150
NX = datalib.NX
NT_SLAB = 2


def _numpy(x):
    getter = getattr(x, "get", None)
    if getter is not None:
        return np.asarray(getter())
    return np.asarray(x)


def _reference_eigvecs(conf=CONF, t=0, nev1=8):
    path = os.path.join(
        datalib.EIG_ROOT, str(conf), f"eigvecs_t{t:03d}_{conf}"
    )
    raw = np.fromfile(path, dtype="f8")
    block = NX * NX * NX * 3 * 2
    if raw.size % block:
        raise ValueError(f"eigenvector file has a partial record: {path}")
    nev = raw.size // block
    data = raw.reshape(nev, NX, NX, NX, 3, 2)
    return np.ascontiguousarray((data[..., 0] + 1j * data[..., 1])[:nev1]
                                .reshape(nev1, NX ** 3, 3))


def _reference_phase(mom):
    phase = np.empty(NX ** 3, dtype=complex)
    for z in range(NX):
        for y in range(NX):
            for x in range(NX):
                pos = np.array([z, y, x])
                phase[z * NX * NX + y * NX + x] = np.exp(
                    -np.dot(np.asarray(mom), pos) * 2 * np.pi * 1j / NX
                )
    return phase


def _reference_vdv(eig, phase):
    ev = np.asarray(eig).reshape(eig.shape[0], -1)
    raw_phase = np.asarray(phase)
    if raw_phase.size == NX ** 3:
        raw_phase = np.repeat(raw_phase.reshape(-1), 3)
    ph = raw_phase.reshape(-1, ev.shape[1])
    return np.einsum("vV,MV,wV->Mvw", ev.conj(), ph, ev)


def _reference_vvv(eig, mom):
    """Calc_VVV.py 的 24 个 z-slice 求和，保留其六置换次序。"""
    eig = np.asarray(eig).reshape(eig.shape[0], NX, NX, NX, 3)
    phase = _reference_phase(mom).reshape(NX, NX, NX)
    result = np.zeros((eig.shape[0], eig.shape[0], eig.shape[0]), dtype=complex)
    for z in range(NX):
        ph = phase[z].reshape(-1)
        slab = eig[:, z].reshape(eig.shape[0], -1, 3)
        e0, e1, e2 = slab[..., 0], slab[..., 1], slab[..., 2]
        result += np.einsum("x,ax,bx,cx->abc", ph, e0, e1, e2)
        result += np.einsum("x,ax,bx,cx->abc", ph, e1, e2, e0)
        result += np.einsum("x,ax,bx,cx->abc", ph, e2, e0, e1)
        result -= np.einsum("x,ax,bx,cx->abc", ph, e2, e1, e0)
        result -= np.einsum("x,ax,bx,cx->abc", ph, e0, e2, e1)
        result -= np.einsum("x,ax,bx,cx->abc", ph, e1, e0, e2)
    return result


def _array_diff(reference, got):
    ref = _numpy(reference)
    actual = _numpy(got)
    if ref.shape != actual.shape:
        return float("inf")
    if not (np.isfinite(ref).all() and np.isfinite(actual).all()):
        return float("inf")
    scale = max(float(np.linalg.norm(ref)), 1e-300)
    return float(np.linalg.norm(actual - ref) / scale)


def _dual_equiv(reference, got):
    """允许参考/实现的固定 epsilon 轴约定差，但不允许任意数值漂移。"""
    ref = _numpy(reference)
    actual = _numpy(got)
    candidates = [actual, -actual, actual.conj(), -actual.conj()]
    if actual.ndim >= 4:
        candidates.extend([
            np.swapaxes(actual, -1, -2),
            np.swapaxes(actual, -1, -2).conj(),
        ])
    return min(_array_diff(ref, candidate) for candidate in candidates)


def _meta(value):
    if isinstance(value, dict):
        return {str(k): _meta(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_meta(v) for v in value]
    try:
        arr = _numpy(value)
    except Exception:
        return {"repr": repr(value)}
    if arr.ndim == 0:
        return {"value": arr.item(), "dtype": str(arr.dtype)}
    return {"shape": list(arr.shape), "dtype": str(arr.dtype),
            "norm": float(np.linalg.norm(arr))}


def _load_gauge(conf=CONF):
    from pyqcd.tools import set_backend

    set_backend("numpy")
    return np.ascontiguousarray(datalib.gauge(conf)[:NT_SLAB])


def _ref_operator():
    return load_donghx("Operator.py", [
        "plaquette_clover_all_new", "plaquette_clover_all_tilde",
        "operators_new_z0_mu2", "operators_new_z0_mz_mu2",
        "operators_FF_z0",
    ])


def _reference_clover(gauge):
    return _ref_operator()["plaquette_clover_all_new"](
        gauge, gauge.shape[0], NX
    )


def _pyqcd_clover(gauge):
    from pyqcd.operator._gluon_ope import plaquette_clover

    return np.stack([
        np.stack([_numpy(plaquette_clover(gauge, mu, nu))
                  if mu != nu else np.zeros(gauge.shape[:4] + (3, 3), complex)
                  for nu in range(4)])
        for mu in range(4)
    ])


def _real_gauge_cases(conf):
    cases = []

    def add(cid, desc, ref, pq, tol=1e-10, compare=_array_diff,
            note="", timeout=1800):
        cases.append(Case(cid, "donghx4150", desc, ref, pq, tol=tol,
                          timeout=timeout, compare=compare, note=note))

    def r_eig():
        return _reference_eigvecs(conf, t=0, nev1=8)

    def p_eig():
        return _numpy(datalib.eigvecs(conf, t=0)[:8])

    add("4150-EIG", "4150 eigvec 二进制读取（t=0,Nev1=8）",
        r_eig, p_eig, tol=0.0,
        note="参考 Calc_VVV.py/readin_eigvecs 的 f8 交错复数布局")

    mom = [0, 0, 1]

    def r_phase():
        return _reference_phase(mom)

    def p_phase():
        from pyqcd.vertex import phase_exp_3pt

        return _numpy(phase_exp_3pt(NX, mom)).reshape(-1)

    add("4150-PHASE", "4150 动量相位 e^{-ipx}（Pz=1）",
        r_phase, p_phase, tol=1e-14)

    def r_vdv():
        eig = _reference_eigvecs(conf, t=0, nev1=4)
        return _reference_vdv(eig, _reference_phase([0, 0, 1]))

    def p_vdv():
        from pyqcd.vertex import Mom_VdV_sink_t, phase_exp_2pt

        eig = _numpy(datalib.eigvecs(conf, t=0)[:4]).reshape(4, NX, NX, NX, 3)
        phase = _numpy(phase_exp_2pt(NX, [0, 0, 1]))
        return _numpy(Mom_VdV_sink_t(phase, eig))

    add("4150-VDV", "4150 VdV 颜色/空间收缩（Nev=4,Pz=1）",
        r_vdv, p_vdv, tol=1e-12)

    def r_vvv():
        return _reference_vvv(_reference_eigvecs(conf, t=0, nev1=4), [0, 0, 1])

    def p_vvv():
        from pyqcd.vertex import Mom_VVV_sink_t, phase_exp_3pt

        eig = _numpy(datalib.eigvecs(conf, t=0)[:4]).reshape(4, NX, NX, NX, 3)
        return _numpy(Mom_VVV_sink_t(phase_exp_3pt(NX, [0, 0, 1]), eig))[0]

    add("4150-VVV", "4150 VVV 六置换 LC 收缩（Nev=4,Pz=1）",
        r_vvv, p_vvv, tol=1e-11)

    clover_holder = {}

    def r_clover():
        if "gauge" not in clover_holder:
            clover_holder["gauge"] = _load_gauge(conf)
        if "ref" not in clover_holder:
            clover_holder["ref"] = _reference_clover(clover_holder["gauge"])
        return clover_holder["ref"]

    def p_clover():
        if "gauge" not in clover_holder:
            clover_holder["gauge"] = _load_gauge(conf)
        return _pyqcd_clover(clover_holder["gauge"])

    add("4150-CLOVER", "4150 Clover F_{mu nu} 全张量（2 时间片）",
        r_clover, p_clover, tol=1e-9, timeout=1800)

    def r_dual():
        ref = r_clover()
        return _ref_operator()["plaquette_clover_all_tilde"](
            ref, NT_SLAB, NX
        )

    def p_dual():
        from pyqcd.operator._gluon_ope import compute_dual_field_strength

        got = p_clover()
        pairs = {(mu, nu): got[mu, nu]
                 for mu in range(4) for nu in range(4)}
        return np.stack([
            (np.zeros(got.shape[2:], dtype=complex) if mu == nu else
             _numpy(compute_dual_field_strength(pairs, mu, nu)))
            for mu in range(4) for nu in range(4)
        ]).reshape(4, 4, NT_SLAB, NX, NX, NX, 3, 3)

    add("4150-DUAL", "4150 对偶场强 epsilon 缩并全张量",
        r_dual, p_dual, tol=1e-9, compare=_dual_equiv,
        note="比较器显式允许参考与 PyQCD 的固定 epsilon 轴约定")

    def r_ope():
        ref = r_clover()
        tilde = _ref_operator()["plaquette_clover_all_tilde"](
            ref, NT_SLAB, NX
        )
        fn = _ref_operator()["operators_new_z0_mu2"]
        return np.stack([
            fn(clover_holder["gauge"], 2, ref, tilde, dz,
               3, 0, 3, 0, NT_SLAB)
            for dz in range(2)
        ])

    def p_ope():
        from pyqcd.operator._gluon_ope import gluon_ope_operator_z0

        return _numpy(gluon_ope_operator_z0(
            clover_holder["gauge"], 3, 0, 2, 2, NT_SLAB, NX,
            mu2=3, nu2=0, direction=1
        ))

    add("4150-OPE", "4150 +z Wilson 线 OPE（z=0,1；t=0,1）",
        r_ope, p_ope, tol=1e-9,
        note="参考 operators_new_z0_mu2 与 PyQCD gluon_ope_operator_z0")

    return cases


def _controlled_cases():
    cases = []

    def add(cid, desc, ref, pq, tol=1e-12):
        cases.append(Case(cid, "controlled", desc, ref, pq, tol=tol,
                          compare=_array_diff))

    rng = np.random.default_rng(4150)
    eig = rng.normal(size=(4, NX, NX, NX, 3)) \
        + 1j * rng.normal(size=(4, NX, NX, NX, 3))
    mom = [0, 0, 1]

    def r_phase():
        return _reference_phase(mom)

    def p_phase():
        from pyqcd.vertex import phase_exp_3pt

        return _numpy(phase_exp_3pt(NX, mom)).reshape(-1)

    add("C-PHASE", "受控相位形状", r_phase, p_phase, tol=1e-14)

    def r_vdv():
        return _reference_vdv(eig[:4], _reference_phase(mom))

    def p_vdv():
        from pyqcd.vertex import Mom_VdV_sink_t, phase_exp_2pt

        return _numpy(Mom_VdV_sink_t(
            _numpy(phase_exp_2pt(NX, mom)), eig[:4]
        ))

    add("C-VDV", "受控 VdV 收缩", r_vdv, p_vdv)

    def r_vvv():
        return _reference_vvv(eig[:4], mom)

    def p_vvv():
        from pyqcd.vertex import Mom_VVV_sink_t, phase_exp_3pt

        return _numpy(Mom_VVV_sink_t(
            phase_exp_3pt(NX, mom), eig[:4]
        ))[0]

    add("C-VVV", "受控 VVV 收缩", r_vvv, p_vvv, tol=1e-11)
    return cases


def controlled_checks():
    from pyqcd.tools import set_backend
    from pyqcd.vertex import phase_exp_3pt, Mom_VdV_sink_t, Mom_VVV_sink_t

    set_backend("numpy")
    eig = np.zeros((4, NX, NX, NX, 3), dtype=complex)
    phase = _numpy(phase_exp_3pt(NX, [0, 0, 0]))
    phase2 = np.ones((NX, NX, NX, 3), dtype=complex)
    vdv = _numpy(Mom_VdV_sink_t(phase2, eig))
    vvv = _numpy(Mom_VVV_sink_t(phase, eig))
    return {
        "phase_shape": list(phase.shape),
        "vdv_shape": list(vdv.shape),
        "vvv_shape": list(vvv.shape),
        "finite": bool(np.isfinite(vdv).all() and np.isfinite(vvv).all()),
    }


def build(conf_id=CONF, controlled=False):
    if controlled:
        return _controlled_cases()
    root = Path(__file__).resolve().parents[4]
    datalib.configure(
        int(conf_id), cache_dir=str(root / "data" / "comparison_cache"))
    return _real_gauge_cases(int(conf_id))
