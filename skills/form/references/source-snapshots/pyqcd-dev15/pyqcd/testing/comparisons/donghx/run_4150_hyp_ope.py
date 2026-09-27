"""4150 HYP 规范场与 donghx 非极化 OPE 的真实对照入口。

输入只读取用户明确提供的 HYP ILDG payload；输出仅包含轻量 JSON/Markdown
证据。直线截面取 TMD 成品的横向位移 ``delta_perp=0``，从而与
``gluon_ope_operator_z0(..., second_insert='F')`` 一一对应。
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np


CONF_ID = "4150"
NT = 72
NX = 24

HYP_RECORDS = {
    "3d1": Path(
        "/public/group/lqcd/donghx/Hpysmear_beta6.20_mu-0.2770_ms-0.2400_L24x72/"
        "hpy_3D_1times/beta6.20_mu-0.2770_ms-0.2400_L24x72_cfg_4150.lime.contents/"
        "msg02.rec04.ildg-binary-data"
    ),
    "3d3": Path(
        "/public/group/lqcd/donghx/Hpysmear_beta6.20_mu-0.2770_ms-0.2400_L24x72/"
        "hpy_3D_3times/beta6.20_mu-0.2770_ms-0.2400_L24x72_cfg_4150.lime.contents/"
        "msg02.rec04.ildg-binary-data"
    ),
    "3d5": Path(
        "/public/group/lqcd/donghx/Hpysmear_beta6.20_mu-0.2770_ms-0.2400_L24x72/"
        "hpy_3D_5times/beta6.20_mu-0.2770_ms-0.2400_L24x72_cfg_4150.lime.contents/"
        "msg02.rec04.ildg-binary-data"
    ),
    "4d10": Path(
        "/public/group/lqcd/donghx/Hpysmear_beta6.20_mu-0.2770_ms-0.2400_L24x72/"
        "hpy_4D_10times_new/beta6.20_mu-0.2770_ms-0.2400_L24x72_cfg_4150.lime.contents/"
        "msg02.rec04.ildg-binary-data"
    ),
}

REFERENCE_ROOT = Path(
    "/public/group/lqcd/donghx/Ope_Gluon/TMD_Ope_Gluon/Result/"
    "beta6.20_mu-0.2770_ms-0.2400_L24x72"
)

_REFERENCE_SPECS = {
    "x": {
        (1, 2): ("ops_mu1_nu2_zmax22_dx9_dy8_conf4150_new.npy", 9),
        (3, 1): ("ops_mu3_nu1_zmax22_dx9_dy8_conf4150_new.npy", 9),
        (3, 2): ("ops_mu3_nu2_zmax22_dx9_dy8_conf4150_new.npy", 9),
    },
    "y": {
        (2, 0): ("ops_mu2_nu0_zmax22_dy9_dx8_conf4150_new.npy", 9),
        (3, 0): ("ops_mu3_nu0_zmax22_dy9_dx8_conf4150_new.npy", 9),
        (3, 2): ("ops_mu3_nu2_zmax22_dy9_dx8_conf4150_new.npy", 9),
    },
    "z": {
        (0, 1): ("ops_mu0_nu1_dz12_dx5_conf4150.npy", 12),
        (3, 0): ("ops_mu3_nu0_dz12_dx5_conf4150.npy", 12),
        (3, 1): ("ops_mu3_nu1_dz12_dx5_conf4150.npy", 12),
    },
}

_DIR_INDEX = {"x": 0, "y": 1, "z": 2}


def reference_case(direction: str, mu: int, nu: int) -> dict:
    """Return the reference file and zero-transverse comparison slice."""
    try:
        filename, delta_z = _REFERENCE_SPECS[direction][(mu, nu)]
    except KeyError as exc:
        raise ValueError(f"no 4150 reference channel for {direction=} {(mu, nu)=}") from exc
    return {
        "direction": direction,
        "mu": mu,
        "nu": nu,
        "path": REFERENCE_ROOT / f"{direction}dir" / CONF_ID / filename,
        "axis": (slice(None), slice(None), 0),
        "delta_z": delta_z,
    }


def compare_line(reference, actual, *, tolerance: float = 1e-10) -> dict:
    """Compare a ``(Nt,delta_z)`` line without hiding shape mismatches."""
    ref = np.asarray(reference)
    got = np.asarray(actual)
    result = {"shape": list(got.shape), "tolerance": tolerance}
    if ref.shape != got.shape:
        result.update({"status": "diff", "reference_shape": list(ref.shape),
                       "max_abs": float("inf"), "rel_l2": float("inf")})
        return result
    delta = got - ref
    ref_norm = max(float(np.linalg.norm(ref)), 1e-300)
    result.update({
        "status": "pass" if float(np.linalg.norm(delta)) / ref_norm <= tolerance else "diff",
        "reference_shape": list(ref.shape),
        "reference_norm": float(np.linalg.norm(ref)),
        "actual_norm": float(np.linalg.norm(got)),
        "rel_l2": float(np.linalg.norm(delta) / ref_norm),
        "max_abs": float(np.max(np.abs(delta), initial=0.0)),
    })
    return result


def _gauge_meta(gauge) -> dict:
    links = np.asarray(gauge).reshape(-1, 3, 3)
    eye = np.eye(3, dtype=links.dtype)
    unitary = links @ links.conj().transpose(0, 2, 1)
    return {
        "shape": list(np.asarray(gauge).shape),
        "dtype": str(np.asarray(gauge).dtype),
        "finite": bool(np.isfinite(gauge).all()),
        "max_unitarity_deviation": float(np.max(np.abs(unitary - eye))),
    }


def run_real(smear: str = "4d10", directions=("x", "y", "z")) -> dict:
    """Compute and compare selected 4150 HYP OPE channels."""
    from pyqcd.operator import gluon_ope_operator_z0, read_gauge_lime
    from pyqcd.tools import set_backend

    if smear not in HYP_RECORDS:
        raise ValueError(f"unknown HYP smear {smear!r}; choose from {sorted(HYP_RECORDS)}")
    directions = tuple(directions)
    if any(direction not in _DIR_INDEX for direction in directions):
        raise ValueError(f"directions must be a subset of x/y/z, got {directions!r}")

    set_backend("numpy")
    start = time.perf_counter()
    gauge = read_gauge_lime(HYP_RECORDS[smear], NT, NX)
    result = {
        "schema": "pyqcd.donghx4150.hyp_ope.v1",
        "conf_id": CONF_ID,
        "smear": smear,
        "input": str(HYP_RECORDS[smear]),
        "gauge": _gauge_meta(gauge),
        "channels": [],
    }
    for direction in directions:
        z_dir = _DIR_INDEX[direction]
        for (mu, nu), _spec in _REFERENCE_SPECS[direction].items():
            case = reference_case(direction, mu, nu)
            delta_z = case["delta_z"]
            calc_start = time.perf_counter()
            actual = np.asarray(gluon_ope_operator_z0(
                gauge, mu, nu, z_dir, delta_z, NT, NX,
                second_insert="F",
            )).T
            item = {
                "direction": direction,
                "mu": mu,
                "nu": nu,
                "delta_z": delta_z,
                "seconds": round(time.perf_counter() - calc_start, 4),
                "actual_shape": list(actual.shape),
            }
            if smear != "4d10":
                item.update({
                    "status": "unverified",
                    "evidence": "unverified",
                    "reason": "reference_is_4d10_smear",
                })
            elif not case["path"].is_file():
                item.update({
                    "status": "unverified",
                    "evidence": "unverified",
                    "reason": "reference_output_missing",
                    "reference_path": str(case["path"]),
                })
            else:
                reference = np.load(case["path"], allow_pickle=False)[case["axis"]]
                item.update(compare_line(reference, actual))
                item.update({
                    "evidence": "confirmed",
                    "reference_path": str(case["path"]),
                })
            result["channels"].append(item)
    statuses = {item["status"] for item in result["channels"]}
    result["status"] = (
        "diff" if "diff" in statuses else
        "unverified" if "unverified" in statuses else "pass"
    )
    result["evidence"] = "confirmed" if result["status"] == "pass" else result["status"]
    result["seconds"] = round(time.perf_counter() - start, 4)
    return result


def _write_outputs(outdir: Path, result: dict):
    outdir.mkdir(parents=True, exist_ok=False)
    (outdir / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# 4150 HYP OPE 对照",
        "",
        f"状态：`{result['status']}`，证据：`{result['evidence']}`。",
        f"规范场：`{result['smear']}`，输入：`{result['input']}`。",
        "",
        "| 方向 | (mu,nu) | 状态 | 相对 L2 | 最大绝对差 |",
        "|---|---|---|---:|---:|",
    ]
    for item in result["channels"]:
        lines.append(
            f"| {item['direction']} | ({item['mu']},{item['nu']}) | "
            f"{item['status']} | {item.get('rel_l2', '-')} | "
            f"{item.get('max_abs', '-')} |"
        )
    (outdir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--smear", choices=sorted(HYP_RECORDS), default="4d10")
    parser.add_argument("--directions", default="x,y,z")
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args(argv)
    result = run_real(args.smear, tuple(x for x in args.directions.split(",") if x))
    _write_outputs(args.outdir, result)
    print(json.dumps({"status": result["status"], "outdir": str(args.outdir)},
                     ensure_ascii=False))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
