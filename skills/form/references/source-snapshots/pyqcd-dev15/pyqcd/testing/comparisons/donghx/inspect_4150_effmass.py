"""检查 donghx 4150 的跨组态 2pt 聚合数组。

参考 ``effmass`` 目录中的数组不是逐组态目录，而是沿
``4050, 4100, 4150, ..., 48000`` 顺序聚合的结果。本模块只读取这些数组和
仍可见的 4150 单组态输出，不复制外部数据；它验证 4150 行的位置、raw
``(t_sink, t_source)`` 矩阵以及按相对时间汇总后的 ``twoptall``。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np


CONF_ID = "4150"
DEFAULT_BASE = Path(
    "/public/group/lqcd/donghx/2pt_Result/"
    "beta6.20_mu-0.2770_ms-0.2400_L24x72"
)
EXPECTED_SAMPLE_INDEX = 2


def time_difference_sum(matrix: np.ndarray) -> np.ndarray:
    """按 ``(t_sink - t_source) mod Nt`` 汇总一个切片矩阵。

    参考脚本用 ``dtype=complex`` 创建输出；这里显式升宽到 complex128，避免
    complex64 输入在时间方向累加时产生仅由存储精度造成的假差异。
    """
    matrix = np.asarray(matrix, dtype=np.complex128)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError(f"matrix must be square 2-D, got {matrix.shape}")
    nt = matrix.shape[0]
    result = np.zeros(nt, dtype=np.complex128)
    for t_sink in range(nt):
        for t_source in range(nt):
            result[(t_sink - t_source) % nt] += matrix[t_sink, t_source]
    return result


def _relative_l2(actual: np.ndarray, expected: np.ndarray) -> float:
    actual = np.asarray(actual)
    expected = np.asarray(expected)
    return float(
        np.linalg.norm(actual - expected)
        / max(float(np.linalg.norm(expected)), 1e-300)
    )


def _default_tolerance(reference: np.ndarray, aggregate: np.ndarray) -> float:
    if np.asarray(reference).dtype == np.dtype("complex64") or np.asarray(aggregate).dtype == np.dtype("complex64"):
        return 5e-6
    return 1e-12


def compare_matrix_stack(
    stack: np.ndarray,
    reference: np.ndarray,
    *,
    tolerance: float | None = None,
) -> dict:
    """在 ``(Nsample, ...)`` 聚合中定位与 reference 相同的 raw 矩阵。"""
    stack = np.asarray(stack)
    reference = np.asarray(reference)
    if stack.ndim < 1 or stack.shape[1:] != reference.shape:
        raise ValueError(
            f"stack trailing shape {stack.shape[1:]} != reference {reference.shape}"
        )
    values = np.asarray(
        [_relative_l2(stack[index], reference) for index in range(stack.shape[0])],
        dtype=np.float64,
    )
    best_index = int(np.argmin(values))
    tol = _default_tolerance(reference, stack) if tolerance is None else float(tolerance)
    return {
        "status": "pass" if values[best_index] <= tol else "diff",
        "best_index": best_index,
        "rel_l2": float(values[best_index]),
        "tolerance": tol,
        "sample_count": int(stack.shape[0]),
        "aggregate_shape": list(stack.shape),
        "reference_shape": list(reference.shape),
        "aggregate_dtype": str(stack.dtype),
        "reference_dtype": str(reference.dtype),
    }


def compare_time_stack(
    stack: np.ndarray,
    reference_matrix: np.ndarray,
    *,
    tolerance: float | None = None,
) -> dict:
    """比较 ``twoptall`` 聚合与 reference raw 矩阵的相对时间汇总。"""
    reference = time_difference_sum(reference_matrix)
    result = compare_matrix_stack(stack, reference, tolerance=tolerance)
    result["reference_operation"] = "sum[(t_sink-t_source) mod Nt]"
    return result


def _specs(base: Path) -> list[dict]:
    """返回当前可见、能与 4150 单组态文件配对的聚合资产。"""
    effmass = base / "effmass"
    return [
        {
            "label": "raw +2z momentum-smear",
            "kind": "matrix",
            "aggregate": effmass / "momsmear2_Cg5g4" / "Res_2pt.npy",
            "reference_root": base / "momsmear2z" / CONF_ID,
            "momenta": [(0, 0, pz) for pz in (2, 3, 4, 5, 6)],
        },
        {
            "label": "raw -2z momentum-smear",
            "kind": "matrix",
            "aggregate": effmass / "momsmear2_Cg5g4" / "Res_2pt_mp.npy",
            "reference_root": base / "momsmear-2z" / CONF_ID,
            "momenta": [(0, 0, pz) for pz in (-2, -3, -4, -5, -6)],
        },
        {
            "label": "raw momentum-smear0 Cg5g4",
            "kind": "matrix",
            "aggregate": effmass / "momsmear0_Cg5g4" / "Res_2pt_momsmear0_Cg5g4.npy",
            "reference_root": base / "momsmear0_Cg5g4" / CONF_ID,
            "momenta": [(0, 0, pz) for pz in (2, 3, 4, 5)],
        },
        {
            "label": "twoptall +2z momentum-smear",
            "kind": "time",
            "aggregate": effmass / "momsmear2_Cg5g4_Disperion" / "twoptall.npy",
            "reference_root": base / "momsmear2z" / CONF_ID,
            "momenta": [(0, 0, pz) for pz in (2, 3, 4, 5, 6)],
        },
        {
            "label": "twoptall momentum-smear0 Cg5g4",
            "kind": "time",
            "aggregate": effmass / "momsmear0_Cg5g4_Disperion" / "twoptall_zdir.npy",
            "reference_root": base / "momsmear0_Cg5g4" / CONF_ID,
            "momenta": [(0, 0, pz) for pz in (2, 3, 4, 5)],
        },
        {
            "label": "twoptall Pz0 Cg5",
            "kind": "time",
            "aggregate": effmass / "Pz0_Cg5_Cg5g4" / "twoptall_Cg5.npy",
            "reference_root": base / "momsmear0_Cg5" / CONF_ID,
            "momenta": [(0, 0, 0)],
        },
        {
            "label": "twoptall Pz0 Cg5g4",
            "kind": "time",
            "aggregate": effmass / "Pz0_Cg5_Cg5g4" / "twoptall_Cg5g4.npy",
            "reference_root": base / "momsmear0_Cg5g4" / CONF_ID,
            "momenta": [(0, 0, 0)],
        },
    ]


def _reference_file(root: Path, momentum: tuple[int, int, int]) -> Path:
    px, py, pz = momentum
    matches = sorted(
        root.glob(
            f"twopt_slice_pp_Px{px}Py{py}Pz{pz}_*nopol_ss_conf{CONF_ID}.npy"
        )
    )
    if len(matches) != 1:
        raise FileNotFoundError(
            f"expected one nopol reference for {momentum}, found {len(matches)} in {root}"
        )
    return matches[0]


def _array_meta(path: Path, array: np.ndarray) -> dict:
    return {
        "path": str(path),
        "bytes": int(path.stat().st_size),
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "finite": bool(np.isfinite(array).all()),
    }


def inspect_aggregate(spec: dict) -> dict:
    """检查一个聚合资产及其 4150 对应样本。"""
    aggregate_path = Path(spec["aggregate"])
    result = {
        "label": spec["label"],
        "kind": spec["kind"],
        "aggregate": str(aggregate_path),
        "reference_root": str(spec["reference_root"]),
        "expected_sample_index": EXPECTED_SAMPLE_INDEX,
        "rows": [],
    }
    if not aggregate_path.is_file():
        result.update({"status": "unverified", "reason": "aggregate_missing"})
        return result

    stack = np.load(aggregate_path, mmap_mode="r", allow_pickle=False)
    result["aggregate_meta"] = _array_meta(aggregate_path, stack)
    try:
        for row, momentum in enumerate(spec["momenta"]):
            reference_path = _reference_file(Path(spec["reference_root"]), momentum)
            reference = np.load(reference_path, allow_pickle=False)
            aggregate_row = stack[row]
            if spec["kind"] == "matrix":
                comparison = compare_matrix_stack(aggregate_row, reference)
            elif spec["kind"] == "time":
                comparison = compare_time_stack(aggregate_row, reference)
            else:
                raise ValueError(f"unknown aggregate kind: {spec['kind']}")
            comparison.update(
                {
                    "row": row,
                    "momentum_pxpyzp": list(momentum),
                    "reference": _array_meta(reference_path, reference),
                    "expected_index_match": comparison["best_index"] == EXPECTED_SAMPLE_INDEX,
                }
            )
            if not comparison["expected_index_match"]:
                comparison["status"] = "diff"
            result["rows"].append(comparison)
    except (FileNotFoundError, ValueError, OSError) as exc:
        result.update({"status": "unverified", "reason": f"{type(exc).__name__}: {exc}"})
        return result

    result["status"] = (
        "pass"
        if result["rows"]
        and all(item["status"] == "pass" for item in result["rows"])
        else "diff"
    )
    return result


def inspect_all(base: str | Path = DEFAULT_BASE) -> dict:
    base = Path(base)
    assets = [inspect_aggregate(spec) for spec in _specs(base)]
    return {
        "schema": "pyqcd.donghx4150.effmass-aggregate.v1",
        "conf_id": CONF_ID,
        "expected_sample_index": EXPECTED_SAMPLE_INDEX,
        "conf_sequence_basis": "4050 + 50*k; 4150 => k=2",
        "assets": assets,
        "summary": {
            "assets": len(assets),
            "pass": sum(item["status"] == "pass" for item in assets),
            "diff": sum(item["status"] == "diff" for item in assets),
            "unverified": sum(item["status"] == "unverified" for item in assets),
            "rows": sum(len(item.get("rows", [])) for item in assets),
        },
    }


def _summary(report: dict) -> str:
    lines = [
        "# 4150 effmass 聚合 2pt 检查",
        "",
        "聚合脚本的组态序列为 `4050 + 50*k`，故 4150 对应样本索引 `k=2`。",
        "raw 项比较 `(t_sink,t_source)` 矩阵；`twoptall` 项先按",
        "`(t_sink-t_source) mod 72` 汇总，并对 complex64 输入升宽到 complex128。",
        "",
        "| 聚合资产 | 形状 | 行数 | 4150 索引（命中/行数） | 状态 |",
        "|---|---|---:|---:|---|",
    ]
    for asset in report["assets"]:
        rows = asset.get("rows", [])
        index_ok = sum(row.get("expected_index_match", False) for row in rows)
        shape = asset.get("aggregate_meta", {}).get("shape", "-")
        lines.append(
            f"| `{asset['label']}` | `{shape}` | {len(rows)} | "
            f"`{EXPECTED_SAMPLE_INDEX}`（{index_ok}/{len(rows)}） | "
            f"**{asset['status']}** |"
        )
    lines.extend(
        [
            "",
            f"汇总：{report['summary']['pass']}/{report['summary']['assets']} 个资产通过，",
            f"{report['summary']['rows']} 个动量行；所有通过行的最优匹配索引均为 2。",
            "这证明了可见 4150 单组态文件与聚合 raw/时间汇总的对应关系；",
            "不证明独立 momentum-smeared perambulator 或逐时间 VVV 文件已可见。",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=str(DEFAULT_BASE))
    parser.add_argument("--output", default="")
    parser.add_argument("--summary", default="")
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = inspect_all(args.base)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if args.summary:
        summary = Path(args.summary)
        summary.parent.mkdir(parents=True, exist_ok=True)
        summary.write_text(_summary(report))

    print(
        "inspect_4150_effmass: assets={assets} pass={pass_} diff={diff} "
        "unverified={unverified} rows={rows}".format(
            assets=report["summary"]["assets"],
            pass_=report["summary"]["pass"],
            diff=report["summary"]["diff"],
            unverified=report["summary"]["unverified"],
            rows=report["summary"]["rows"],
        )
    )
    return 0 if report["summary"]["diff"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
