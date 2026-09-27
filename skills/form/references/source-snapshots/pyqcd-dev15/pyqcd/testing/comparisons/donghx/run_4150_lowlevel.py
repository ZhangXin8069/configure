"""运行 4150 低层对象对照并保存结构化证据。"""

from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent

from .cases_4150_lowlevel import build


class ReferenceUnavailable(RuntimeError):
    """Reference output/code cannot be used for this case."""


def _numpy(value):
    getter = getattr(value, "get", None)
    if getter is not None:
        return np.asarray(getter())
    return np.asarray(value)


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


def _save_array(value, path):
    """Save only ndarray leaves; keep output filenames deterministic."""
    if isinstance(value, dict):
        for key, child in value.items():
            _save_array(child, path / str(key))
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _save_array(child, path / str(index))
        return
    try:
        arr = _numpy(value)
    except Exception:
        return
    if arr.ndim == 0 or arr.size > 4_000_000:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path.with_suffix(".npy"), arr)


def _default_compare(reference, actual):
    ref = _numpy(reference)
    got = _numpy(actual)
    if ref.shape != got.shape:
        return float("inf")
    if not (np.isfinite(ref).all() and np.isfinite(got).all()):
        return float("inf")
    return float(np.linalg.norm(got - ref) /
                 max(float(np.linalg.norm(ref)), 1e-300))


def _execute(case, array_root=None):
    record = {
        "id": case.cid,
        "group": case.group,
        "desc": case.desc,
        "tol": case.tol,
        "note": case.note,
        "evidence": "confirmed",
        "status": "running",
    }
    ref = actual = None
    try:
        start = time.perf_counter()
        ref = case.run_ref()
        record["t_ref"] = round(time.perf_counter() - start, 4)
        record["ref_meta"] = _meta(ref)
    except Exception as exc:
        record["status"] = "unverified" if isinstance(
            exc, ReferenceUnavailable) else "ref_error"
        record["evidence"] = "unverified" if record["status"] == "unverified" else "confirmed"
        record["err_ref"] = traceback.format_exc()[-1600:]

    try:
        start = time.perf_counter()
        actual = case.run_pq()
        record["t_pq"] = round(time.perf_counter() - start, 4)
        record["pq_meta"] = _meta(actual)
    except Exception:
        record["status"] = "pq_error"
        record["err_pq"] = traceback.format_exc()[-1600:]
        return record

    if record["status"] == "unverified":
        return record
    if record.get("status") == "ref_error":
        return record

    if array_root is not None:
        _save_array(ref, array_root / case.cid / "reference")
        _save_array(actual, array_root / case.cid / "pyqcd")

    compare = case.compare
    if compare == "none":
        diff = 0.0
    elif callable(compare):
        diff = float(compare(ref, actual))
    else:
        diff = _default_compare(ref, actual)
    record["diff"] = diff
    record["status"] = "pass" if diff <= case.tol else "diff"
    if record.get("t_ref") and record.get("t_pq"):
        record["speedup"] = round(record["t_ref"] / record["t_pq"], 3)
    return record


def run(conf_id=4150, outdir=None, controlled=False, save_arrays=True):
    if outdir is None:
        outdir = HERE / "artifacts" / (
            "run_" + time.strftime("%Y%m%d%H%M%S"))
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=False)
    cases = build(conf_id, controlled=controlled)
    array_root = outdir / "arrays" if save_arrays else None
    results = []
    for case in cases:
        print(f"[{case.group}] {case.cid}: {case.desc}", flush=True)
        record = _execute(case, array_root=array_root)
        results.append(record)
        print("  -> {status} diff={diff} t_ref={tr} t_pq={tp}".format(
            status=record["status"], diff=record.get("diff", "-"),
            tr=record.get("t_ref", "-"), tp=record.get("t_pq", "-")), flush=True)

    (outdir / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str) + "\n"
    )
    counts = {}
    for record in results:
        counts[record["status"]] = counts.get(record["status"], 0) + 1
    summary = ["# 4150 低层对象对照", "", f"输出目录: `{outdir}`", "",
               "| 状态 | id | diff | tol | t_ref(s) | t_pyqcd(s) |", "|---|---|---:|---:|---:|---:|"]
    for record in results:
        summary.append("| {status} | {id} | {diff} | {tol} | {tr} | {tp} |".format(
            status=record["status"], id=record["id"],
            diff=record.get("diff", "-"), tol=record.get("tol", "-"),
            tr=record.get("t_ref", "-"), tp=record.get("t_pq", "-")))
    summary.extend(["", "状态计数: " + json.dumps(counts, ensure_ascii=False), ""])
    (outdir / "summary.md").write_text("\n".join(summary))
    return outdir, results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--conf", type=int, default=4150)
    parser.add_argument("--outdir", default="")
    parser.add_argument("--controlled", action="store_true")
    parser.add_argument("--no-arrays", action="store_true")
    args = parser.parse_args()
    outdir = args.outdir or None
    path, results = run(args.conf, outdir, args.controlled,
                        save_arrays=not args.no_arrays)
    print(f"== wrote {path} ({len(results)} cases)")


if __name__ == "__main__":
    main()
