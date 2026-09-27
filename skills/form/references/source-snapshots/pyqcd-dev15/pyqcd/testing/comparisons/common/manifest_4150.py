"""用户指定的 4150 数据/参考产物清单工具。

本模块只读取文件元数据，不复制、打开或修改外部数据数组；数组内容比较由各阶段
runner 负责。路径集中在此处，避免不同案例对同一资产使用不同拼写。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


CONF = "4150"
NX = 24
NT = 72

PUBLIC = Path("/public/group/lqcd")
INPUT_PATHS = {
    "gauge": PUBLIC / "configurations/CLOVER/beta6.20_mu-0.2770_ms-0.2400_L24x72"
    / "beta6.20_mu-0.2770_ms-0.2400_L24x72_cfg_4150.lime",
    "eigenvectors": PUBLIC / "eigensystem/beta6.20_mu-0.2770_ms-0.2400_L24x72/4150",
    "perambulators": PUBLIC / "perambulators/beta6.20_mu-0.2770_ms-0.2400_L24x72/light/4150",
    "hpy_3D_1": PUBLIC / "donghx/Hpysmear_beta6.20_mu-0.2770_ms-0.2400_L24x72/hpy_3D_1times"
    / "beta6.20_mu-0.2770_ms-0.2400_L24x72_cfg_4150.lime.contents",
    "hpy_3D_3": PUBLIC / "donghx/Hpysmear_beta6.20_mu-0.2770_ms-0.2400_L24x72/hpy_3D_3times"
    / "beta6.20_mu-0.2770_ms-0.2400_L24x72_cfg_4150.lime.contents",
    "hpy_3D_5": PUBLIC / "donghx/Hpysmear_beta6.20_mu-0.2770_ms-0.2400_L24x72/hpy_3D_5times"
    / "beta6.20_mu-0.2770_ms-0.2400_L24x72_cfg_4150.lime.contents",
    "hpy_4D_10": PUBLIC / "donghx/Hpysmear_beta6.20_mu-0.2770_ms-0.2400_L24x72/hpy_4D_10times_new"
    / "beta6.20_mu-0.2770_ms-0.2400_L24x72_cfg_4150.lime.contents",
}

REFERENCE_OUTPUT_PATHS = {
    "2pt_result": PUBLIC / "donghx/2pt_Result/beta6.20_mu-0.2770_ms-0.2400_L24x72",
    "2pt_cpu": PUBLIC / "donghx/2pt_cpu",
    "2pt_cpu_momsmear": PUBLIC / "donghx/2pt_cpu_momsmear",
    "2pt_dcu": PUBLIC / "donghx/2pt_dcu",
    "2pt_dcu_cupy": PUBLIC / "donghx/2pt_dcu_cupy",
    "2pt_diffpol": PUBLIC / "donghx/2pt_diffpol",
    "2pt_gpu_2026": PUBLIC / "donghx/2pt_gpu_2026",
    "2pt_gpu_new": PUBLIC / "donghx/2pt_gpu_new",
    "eigvec_result": PUBLIC / "donghx/Eigvec_result",
    "contraction": PUBLIC / "donghx/Contraction",
    "ope_tmd_result": PUBLIC / "donghx/Ope_Gluon/TMD_Ope_Gluon/Result"
    / "beta6.20_mu-0.2770_ms-0.2400_L24x72",
    "ope_hpy_result": PUBLIC / "donghx/Ope_Gluon/Result_hpy_4D_10times",
}

REFERENCE_CODE_PATHS = {
    "eigvec_driver": Path("refer/donghx/Eigvec_code/Calc_Eigvec_test.py"),
    "vvv": Path("refer/donghx/Calc_VVV.py"),
    "wick": Path("refer/donghx/Contraction/Wick_contraction.py"),
    "operator": Path("refer/donghx/Operator.py"),
    "ope_unpol": Path("refer/donghx/Calc_ope_unpol.py"),
    "ope_unpol_new": Path("refer/donghx/Calc_ope_unpol_new.py"),
    "gamma": Path("refer/donghx/gamma_matrix_cupy_DR.py"),
}


def _file_meta(path: Path) -> dict:
    """Return metadata without reading an array payload."""
    try:
        stat = path.stat()
    except OSError as exc:
        return {"path": str(path), "exists": False, "error": str(exc)}

    out = {
        "path": str(path),
        "exists": True,
        "kind": "directory" if path.is_dir() else "file",
        "bytes": int(stat.st_size),
        "mtime": float(stat.st_mtime),
    }
    if path.is_dir():
        files = []
        total = 0
        try:
            for child in path.rglob("*"):
                if child.is_file():
                    try:
                        total += child.stat().st_size
                        if len(files) < 20:
                            files.append(str(child))
                    except OSError:
                        continue
        except OSError as exc:
            out["scan_error"] = str(exc)
        out.update({"file_count": sum(1 for _ in path.rglob("*") if _.is_file()),
                    "total_bytes": int(total), "sample_files": files})
        return out

    suffix = path.suffix.lower()
    if suffix == ".npy":
        try:
            import numpy as np
            arr = np.load(path, mmap_mode="r", allow_pickle=False)
            out.update({"shape": list(arr.shape), "dtype": str(arr.dtype)})
        except Exception as exc:  # malformed data belongs in the manifest
            out["read_error"] = f"{type(exc).__name__}: {exc}"
    elif suffix == ".npz":
        try:
            import numpy as np
            with np.load(path, mmap_mode="r", allow_pickle=False) as archive:
                out["arrays"] = {
                    key: {"shape": list(archive[key].shape),
                          "dtype": str(archive[key].dtype)}
                    for key in archive.files
                }
        except Exception as exc:
            out["read_error"] = f"{type(exc).__name__}: {exc}"
    elif suffix in {".h5", ".hdf5"}:
        try:
            import h5py
            with h5py.File(path, "r") as handle:
                datasets = {}

                def visit(name, node):
                    if isinstance(node, h5py.Dataset):
                        datasets[name] = {"shape": list(node.shape),
                                          "dtype": str(node.dtype)}

                handle.visititems(visit)
                out["datasets"] = datasets
        except Exception as exc:
            out["read_error"] = f"{type(exc).__name__}: {exc}"
    return out


def array_meta(path: str | os.PathLike) -> dict:
    """Inspect one file/directory and never materialize its array payload."""
    return _file_meta(Path(path))


def _category(paths: dict[str, Path]) -> dict:
    return {name: _file_meta(path) for name, path in paths.items()}


def build_manifest(conf_id: str | int = CONF) -> dict:
    """Build a deterministic asset inventory for one configuration."""
    conf = str(conf_id)
    if conf != CONF:
        raise ValueError(f"本任务只允许显式组态 4150，收到 {conf!r}")
    return {
        "schema": "pyqcd.donghx4150.manifest.v1",
        "conf_id": conf,
        "lattice": {"Nx": NX, "Nt": NT, "layout": "tzyx,dir,color,color"},
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "input": _category(INPUT_PATHS),
        "reference_output": _category(REFERENCE_OUTPUT_PATHS),
        "reference_code": _category(REFERENCE_CODE_PATHS),
    }


def write_manifest(path: str | os.PathLike, conf_id: str | int = CONF) -> dict:
    manifest = build_manifest(conf_id)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--conf", default=CONF)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    result = build_manifest(args.conf)
    if args.output:
        write_manifest(args.output, args.conf)
    print(json.dumps(result, ensure_ascii=False, indent=2))
