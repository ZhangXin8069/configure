"""运行 donghx/PyQCD 4150 费米子 2pt 对照链。

真实模式读取用户明确提供的 eigvec/perambulator，并只写本地 ``outdir`` 与
``data/comparison_4150`` 下的 VVV 缓存；不会修改 ``/public`` 参考数据。

示例：

    python -m pyqcd.testing.comparisons.donghx.run_4150_fermion --controlled
    python -m pyqcd.testing.comparisons.donghx.run_4150_fermion \
        --conf 4150 --outdir <path>
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]

from .cases_4150_fermion import (
    FermionConfig,
    array_meta,
    compare_selected,
    reference_output_paths,
    required_vvv_times,
    selected_pairs,
)


DEFAULT_EIG_ROOT = Path(
    "/public/group/lqcd/eigensystem/"
    "beta6.20_mu-0.2770_ms-0.2400_L24x72"
)
DEFAULT_PERAM_ROOT = Path(
    "/public/group/lqcd/perambulators/"
    "beta6.20_mu-0.2770_ms-0.2400_L24x72/light"
)
DEFAULT_REFERENCE_DIR = Path(
    "/public/group/lqcd/donghx/2pt_Result/"
    "beta6.20_mu-0.2770_ms-0.2400_L24x72/momsmear0_Cg5g4/4150"
)
REFERENCE_NEV = 100
COMPLEX128_TOLERANCE = 1e-10
COMPLEX64_TOLERANCE = 1e-5


def aggregate_comparison_status(comparisons):
    """按最严重比较结果聚合 runner 状态，避免掩盖未验证项。"""
    statuses = {item.get("status") for item in comparisons}
    if "diff" in statuses:
        return "diff"
    if "unverified" in statuses:
        return "unverified"
    return "pass"


def _numpy(value):
    getter = getattr(value, "get", None)
    return np.asarray(getter() if getter is not None else value)


def _set_numpy_backend():
    from pyqcd.tools import set_backend

    set_backend("numpy")


def _read_eigenvectors(eig_root: Path, config: FermionConfig, t: int):
    from pyqcd.tools import readin_eigvecs

    path = eig_root / config.conf_id / f"eigvecs_t{t:03d}_{config.conf_id}"
    eig = _numpy(readin_eigvecs(str(path), config.nx))
    if eig.shape[0] < config.nev:
        raise ValueError(
            f"eigenvector Nev={eig.shape[0]} 小于要求 Nev={config.nev}: {path}"
        )
    eig = eig[:config.nev].reshape(config.nev, config.nx, config.nx, config.nx, 3)
    return _apply_momentum_smear(eig, config)


def _apply_momentum_smear(eig, config: FermionConfig):
    """按 donghx 约定对每个 eigenvector 色分量施加空间相位。"""
    value = np.asarray(eig)
    expected = (config.nx, config.nx, config.nx, 3)
    if value.ndim != 5 or value.shape[1:] != expected:
        raise ValueError(
            f"eigenvector shape must be (Nev,{config.nx},{config.nx},"
            f"{config.nx},3), got {value.shape}"
        )
    if config.momentum_smear == 0:
        return np.ascontiguousarray(value)
    from pyqcd.vertex import momsmear_phase

    phase = momsmear_phase(config.nx, config.momentum_smear_vector)
    phase = phase.reshape(config.nx, config.nx, config.nx)
    return np.ascontiguousarray(value * phase[None, ..., None])


def _compute_vvv(eig_root: Path, config: FermionConfig, t: int):
    from pyqcd.vertex import Mom_VVV_sink_t, phase_exp_3pt

    eig = _read_eigenvectors(eig_root, config, t)
    phase = phase_exp_3pt(config.nx, list(config.momentum))
    return np.ascontiguousarray(_numpy(Mom_VVV_sink_t(phase, eig))[0])


def _vvv_cache_filename(config: FermionConfig, times: tuple[int, ...]) -> str:
    """构造不会混用普通/动量涂抹输入的 VVV 缓存文件名。"""
    name = (f"vvv_Px{config.momentum[2]}Py{config.momentum[1]}"
            f"Pz{config.momentum[0]}")
    if config.momentum_smear != 0:
        name += (f"_smear{config.momentum_smear_dir}{config.momentum_smear}"
                 f"_phase{config.momentum_smear_phase}")
    return f"{name}_Nev{config.nev}_t{times[0]}-{times[-1]}.npy"


def _load_vvv_cache(cache_path: Path, config: FermionConfig,
                    times: tuple[int, ...]):
    """复用形状和精度均匹配的本地 VVV 缓存。"""
    expected_shape = (len(times), config.nev, config.nev, config.nev)
    try:
        cache = np.load(cache_path, mmap_mode="r", allow_pickle=False)
    except (OSError, ValueError):
        return None
    if cache.shape != expected_shape or cache.dtype != np.dtype(np.complex128):
        return None
    record = {
        "times": list(times),
        "index": {str(t): i for i, t in enumerate(times)},
        "timings": [],
        "path": str(cache_path),
        "shape": list(cache.shape),
        "dtype": str(cache.dtype),
        "cache_reused": True,
    }
    return cache, record


def _write_vvv_cache(eig_root: Path, config: FermionConfig,
                     times: tuple[int, ...], cache_path: Path) -> tuple[np.ndarray, dict]:
    """按时间片写 VVV memmap，并返回 ``(cache, t->index)`` 元数据。"""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cached = _load_vvv_cache(cache_path, config, times)
    if cached is not None:
        print(f"reuse VVV cache: {cache_path}", flush=True)
        return cached
    cache = np.lib.format.open_memmap(
        cache_path,
        mode="w+",
        dtype=np.complex128,
        shape=(len(times), config.nev, config.nev, config.nev),
    )
    timings = []
    for index, t in enumerate(times):
        start = time.perf_counter()
        cache[index] = _compute_vvv(eig_root, config, t)
        cache.flush()
        elapsed = time.perf_counter() - start
        timings.append({"t": t, "seconds": round(elapsed, 4)})
        print(f"VVV t={t}: {elapsed:.3f} s", flush=True)
    return cache, {"times": list(times), "index": {str(t): i for i, t in enumerate(times)},
                   "timings": timings, "path": str(cache_path),
                   "shape": list(cache.shape), "dtype": str(cache.dtype),
                   "cache_reused": False}


def _read_peram(peram_root: Path, config: FermionConfig, t_source: int):
    from pyqcd.tools import readin_peram_time_slice

    path = peram_root / config.conf_id
    return _numpy(readin_peram_time_slice(
        str(path), config.conf_id, t_source, config.nt, config.nev
    ))


def _select_peram_root(config: FermionConfig, peram_root: Path,
                       momentum_peram_root: Path | None) -> Path:
    """选择 perambulator 输入；动量涂抹不得静默复用普通输入。"""
    ordinary = Path(peram_root).resolve()
    if config.momentum_smear == 0:
        return ordinary
    if momentum_peram_root is None:
        raise ValueError(
            "非零 momentum_smear 必须显式提供独立 momentum perambulator 根目录"
        )
    selected = Path(momentum_peram_root).resolve()
    if selected == ordinary:
        raise ValueError("momentum perambulator 根目录必须与普通 perambulator 独立")
    return selected


def _project_sparse(contract, config: FermionConfig):
    from pyqcd.contraction import parity_and_boundary

    return tuple(_numpy(x) for x in parity_and_boundary(contract, config.nt))


def _compare_reference(contract, nopol_pp, config: FermionConfig,
                       reference_dir: Path):
    comparisons = []
    paths = reference_output_paths(reference_dir, config)
    for object_name, actual, path in (
        ("contract", contract, paths["contract"]),
        ("nopol_pp", nopol_pp, paths["nopol_pp"]),
    ):
        record = {"object": object_name, "reference_path": str(path),
                  "actual_meta": array_meta(actual)}
        if config.nev != REFERENCE_NEV:
            record.update({
                "status": "unverified",
                "evidence": "unverified",
                "reason": "nev_mismatch",
                "reference_nev": REFERENCE_NEV,
                "actual_nev": config.nev,
            })
        elif not path.is_file():
            record.update({
                "status": "unverified",
                "evidence": "unverified",
                "reason": "reference_output_missing",
            })
        else:
            reference = np.load(path, allow_pickle=False)
            tolerance = (COMPLEX64_TOLERANCE
                         if reference.dtype == np.dtype(np.complex64)
                         else COMPLEX128_TOLERANCE)
            record.update(compare_selected(
                reference, actual, selected_pairs(config), tolerance=tolerance
            ))
            record["tolerance_basis"] = f"reference dtype {reference.dtype}"
            record["reference_meta"] = array_meta(reference)
            record["evidence"] = "confirmed"
        comparisons.append(record)

    comparisons.append({
        "object": "vvv",
        "status": "unverified",
        "evidence": "unverified",
        "reason": "reference_output_missing",
        "note": "已引入的参考结果目录没有可直接读取的逐时间 VVV 中间文件",
    })
    return comparisons


def _summary(outdir: Path, record: dict):
    counts = {}
    for item in record["comparisons"]:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    lines = [
        "# 4150 费米子 2pt 对照",
        "",
        f"输出目录: `{outdir}`",
        "",
        f"配置: `{json.dumps(record['config'], ensure_ascii=False)}`",
        f"整体状态: `{record['status']}`，证据状态: `{record['evidence']}`",
        "",
        "| 对象 | 状态 | 指标 | 值 | 最大绝对差 | 参考文件 |",
        "|---|---|---|---:|---:|---|",
    ]
    for item in record["comparisons"]:
        lines.append("| {object} | {status} | {metric} | {value} | {max_abs} | {path} |".format(
            object=item["object"], status=item["status"],
            metric=item.get("metric", "-"), value=item.get("value", "-"),
            max_abs=item.get("max_abs", "-"),
            path=item.get("reference_path", "-")))
    lines.extend(["", f"状态计数: `{json.dumps(counts, ensure_ascii=False)}`", ""])
    (outdir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def _save_json(path: Path, value: dict):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def run_real(config: FermionConfig, outdir: Path, *, eig_root=DEFAULT_EIG_ROOT,
             peram_root=DEFAULT_PERAM_ROOT, momentum_peram_root=None,
             reference_dir=DEFAULT_REFERENCE_DIR, vvv_cache=None) -> tuple[Path, dict]:
    """运行一条真实 peram+VVV+2pt 链并保存稀疏时间对。"""
    _set_numpy_backend()
    eig_root = Path(eig_root)
    peram_root = Path(peram_root)
    peram_root = _select_peram_root(config, peram_root, momentum_peram_root)
    if not peram_root.is_dir():
        raise FileNotFoundError(
            f"perambulator 根目录不存在或不可读: {peram_root}"
        )
    reference_dir = Path(reference_dir)
    pairs = selected_pairs(config)
    times = required_vvv_times(config)
    if vvv_cache is None:
        vvv_cache = (
            ROOT / "data" / "comparison_4150"
            / _vvv_cache_filename(config, times)
        )
    vvv, vvv_record = _write_vvv_cache(eig_root, config, times, Path(vvv_cache))
    vvv_index = {t: i for i, t in enumerate(times)}

    contract = np.zeros((config.nt, config.nt, 4, 4), dtype=np.complex128)
    peram_records = []
    total_start = time.perf_counter()
    from pyqcd.contraction import contract_donghx_2pt_pair

    for t_source in config.t_sources:
        start = time.perf_counter()
        peram = _read_peram(peram_root, config, t_source)
        if peram.shape != (config.nt, 4, 4, config.nev, config.nev):
            raise ValueError(f"unexpected peram shape {peram.shape} for t_source={t_source}")
        source_vvv = np.conj(vvv[vvv_index[t_source]])
        sink_times = {t_sink for t_sink, source, _ in pairs if source == t_source}
        for t_sink in sorted(sink_times):
            contract[t_sink, t_source] = _numpy(
                contract_donghx_2pt_pair(
                    peram[t_sink], vvv[vvv_index[t_sink]], source_vvv,
                    variant=config.variant,
                )
            )
            print(f"contract t_sink={t_sink}, t_source={t_source}", flush=True)
        elapsed = time.perf_counter() - start
        peram_records.append({"t_source": t_source, "seconds": round(elapsed, 4),
                              "shape": list(peram.shape), "dtype": str(peram.dtype)})
        print(f"peram t_source={t_source}: {elapsed:.3f} s", flush=True)

    nopol_pp, nopol_pm = _project_sparse(contract, config)
    outdir.mkdir(parents=True, exist_ok=False)
    np.save(outdir / "contract_sparse.npy", contract)
    np.save(outdir / "nopol_pp_sparse.npy", nopol_pp)
    np.save(outdir / "nopol_pm_sparse.npy", nopol_pm)
    comparisons = _compare_reference(contract, nopol_pp, config,
                                     reference_dir)
    status = aggregate_comparison_status(comparisons)
    record = {
        "schema": "pyqcd.donghx4150.fermion2pt.v1",
        "conf_id": config.conf_id,
        "config": {
            "nx": config.nx, "nt": config.nt, "nev": config.nev,
            "momentum_pzyx": list(config.momentum),
            "momentum_smear": config.momentum_smear,
            "momentum_smear_dir": config.momentum_smear_dir,
            "momentum_smear_phase": config.momentum_smear_phase,
            "momentum_smear_phase_pzyx": list(config.momentum_smear_vector),
            "variant": config.variant,
            "t_sources": list(config.t_sources),
            "delta_t": [config.delta_t_min, config.delta_t_max],
            "selected_pair_count": len(pairs),
        },
        "inputs": {
            "eigenvectors": str(eig_root / config.conf_id),
            "perambulators": str(peram_root / config.conf_id),
            "reference_output": str(reference_dir),
        },
        "outputs": {
            "contract": {"path": str(outdir / "contract_sparse.npy"),
                         **array_meta(contract)},
            "nopol_pp": {"path": str(outdir / "nopol_pp_sparse.npy"),
                         **array_meta(nopol_pp)},
            "nopol_pm": {"path": str(outdir / "nopol_pm_sparse.npy"),
                         **array_meta(nopol_pm)},
        },
        "vvv": vvv_record,
        "perambulator": peram_records,
        "timing_seconds": round(time.perf_counter() - total_start, 4),
        "comparisons": comparisons,
        "status": status,
        "evidence": "confirmed" if status == "pass" else status,
        "note": "contract/nopol 只在所选时间对非零；未计算的全时间源不参与比较",
    }
    _save_json(outdir / "results.json", record)
    _summary(outdir, record)
    return outdir, record


def run_controlled(outdir: Path | None = None) -> tuple[Path | None, dict]:
    """用小型随机张量检查 runner 的选对、投影和输出契约。"""
    _set_numpy_backend()
    config = FermionConfig(nx=2, nt=4, nev=3, t_sources=(0,),
                           delta_t_min=1, delta_t_max=2)
    rng = np.random.default_rng(4150)
    from pyqcd.contraction import contract_donghx_2pt_pair

    peram = rng.normal(size=(config.nt, 4, 4, config.nev, config.nev)) \
        + 1j * rng.normal(size=(config.nt, 4, 4, config.nev, config.nev))
    vvv = rng.normal(size=(config.nt, config.nev, config.nev, config.nev)) \
        + 1j * rng.normal(size=(config.nt, config.nev, config.nev, config.nev))
    contract = np.zeros((config.nt, config.nt, 4, 4), dtype=complex)
    source_vvv = np.conj(vvv[0])
    for t_sink, t_source, _ in selected_pairs(config):
        contract[t_sink, t_source] = _numpy(contract_donghx_2pt_pair(
            peram[t_sink], vvv[t_sink], source_vvv, variant=config.variant
        ))
    nopol_pp, nopol_pm = _project_sparse(contract, config)
    result = {
        "schema": "pyqcd.donghx4150.fermion2pt.v1",
        "mode": "controlled",
        "config": {"nx": config.nx, "nt": config.nt, "nev": config.nev,
                    "pairs": [list(p) for p in selected_pairs(config)]},
        "outputs": {"contract": array_meta(contract),
                    "nopol_pp": array_meta(nopol_pp),
                    "nopol_pm": array_meta(nopol_pm)},
        "status": "pass",
        "evidence": "confirmed",
    }
    if outdir is not None:
        outdir.mkdir(parents=True, exist_ok=False)
        np.save(outdir / "contract_sparse.npy", contract)
        np.save(outdir / "nopol_pp_sparse.npy", nopol_pp)
        np.save(outdir / "nopol_pm_sparse.npy", nopol_pm)
        _save_json(outdir / "results.json", result)
        _summary(outdir, {**result, "comparisons": []})
    return outdir, result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--conf", default="4150")
    parser.add_argument("--outdir", default="")
    parser.add_argument("--controlled", action="store_true")
    parser.add_argument("--eig-root", default=str(DEFAULT_EIG_ROOT))
    parser.add_argument("--peram-root", default=str(DEFAULT_PERAM_ROOT))
    parser.add_argument("--reference-dir", default=str(DEFAULT_REFERENCE_DIR))
    parser.add_argument("--vvv-cache", default="")
    parser.add_argument("--nev", type=int, default=100)
    parser.add_argument("--pz", type=int, default=0)
    parser.add_argument("--py", type=int, default=0)
    parser.add_argument("--px", type=int, default=0)
    parser.add_argument("--momentum-smear", type=int, default=0)
    parser.add_argument("--momentum-smear-dir", choices=("x", "y", "z"), default=None)
    parser.add_argument("--momentum-smear-phase", type=int, default=None)
    parser.add_argument("--momentum-peram-root", default="")
    parser.add_argument("--variant", default="Cg5g4")
    parser.add_argument("--t-source", type=int, action="append", default=None)
    parser.add_argument("--delta-t-min", type=int, default=2)
    parser.add_argument("--delta-t-max", type=int, default=36)
    args = parser.parse_args(argv)
    if args.controlled:
        path, result = run_controlled(Path(args.outdir) if args.outdir else None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if path is not None:
            print(f"== wrote {path}")
        return 0

    config = FermionConfig(
        conf_id=args.conf, nev=args.nev,
        momentum=(args.pz, args.py, args.px), variant=args.variant,
        momentum_smear=args.momentum_smear,
        momentum_smear_dir=args.momentum_smear_dir,
        momentum_smear_phase=args.momentum_smear_phase,
        t_sources=tuple(args.t_source or (0,)),
        delta_t_min=args.delta_t_min, delta_t_max=args.delta_t_max,
    )
    outdir = Path(args.outdir) if args.outdir else (
        HERE / "artifacts"
        / ("run_" + time.strftime("%Y%m%d%H%M%S") + "_fermion")
    )
    path, record = run_real(
        config, outdir, eig_root=args.eig_root, peram_root=args.peram_root,
        momentum_peram_root=args.momentum_peram_root or None,
        reference_dir=args.reference_dir,
        vvv_cache=args.vvv_cache or None,
    )
    print(json.dumps({"outdir": str(path), "status": record["status"],
                      "comparisons": record["comparisons"]},
                     ensure_ascii=False, indent=2))
    return 0 if all(item["status"] in {"pass", "unverified"}
                    for item in record["comparisons"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
