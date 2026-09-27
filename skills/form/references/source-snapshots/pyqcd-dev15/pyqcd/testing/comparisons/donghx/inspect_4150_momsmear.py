"""检查 donghx 4150 2pt 成品的结构和投影关系。

本模块只消费参考目录中的 ``.npy`` 成品，不生成或替代任何 perambulator。它的
数值检查范围是输出级：验证 ``contract`` 经 DR 基正宇称/极化投影及反周期边界
符号后得到 ``nopol_ss`` 或 ``pol*_ss``，并记录所有文件的 shape/dtype/有限性。
既覆盖非零动量涂抹，也覆盖 ``momsmear0`` 的隐式算符文件名。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

import numpy as np

from pyqcd.lattice import gamma


CONF_ID = "4150"
POLARIZATION_DIRECTIONS = {
    "pol15_ss": 1,
    "pol25_ss": 2,
    "pol35_ss": 3,
}
DEFAULT_ROOTS = {
    "momsmear-2x": Path(
        "/public/group/lqcd/donghx/2pt_Result/"
        "beta6.20_mu-0.2770_ms-0.2400_L24x72/momsmear-2x/4150"
    ),
    "momsmear-2y": Path(
        "/public/group/lqcd/donghx/2pt_Result/"
        "beta6.20_mu-0.2770_ms-0.2400_L24x72/momsmear-2y/4150"
    ),
    "momsmear-2z": Path(
        "/public/group/lqcd/donghx/2pt_Result/"
        "beta6.20_mu-0.2770_ms-0.2400_L24x72/momsmear-2z/4150"
    ),
    "momsmear2x": Path(
        "/public/group/lqcd/donghx/2pt_Result/"
        "beta6.20_mu-0.2770_ms-0.2400_L24x72/momsmear2x/4150"
    ),
    "momsmear2z": Path(
        "/public/group/lqcd/donghx/2pt_Result/"
        "beta6.20_mu-0.2770_ms-0.2400_L24x72/momsmear2z/4150"
    ),
    "momsmear0_Cg5": Path(
        "/public/group/lqcd/donghx/2pt_Result/"
        "beta6.20_mu-0.2770_ms-0.2400_L24x72/momsmear0_Cg5/4150"
    ),
    "momsmear0_Cg5g4": Path(
        "/public/group/lqcd/donghx/2pt_Result/"
        "beta6.20_mu-0.2770_ms-0.2400_L24x72/momsmear0_Cg5g4/4150"
    ),
}

# 这些是用户本轮明确给出的独立 momentum-smeared perambulator 候选根目录。
# 普通 light perambulator 即使存在，也不能替代它们。
INDEPENDENT_PERAM_ROOTS = (
    Path("/public/group/lqcd/donghx/Peram_code_2505"),
    Path("/public/group/lqcd/donghx/Peram_mpi"),
    Path("/public/group/lqcd/donghx/Peram_result"),
)

_OUTPUT_RE = re.compile(
    r"^twopt_slice_pp_"
    r"Px(?P<px>-?\d+)Py(?P<py>-?\d+)Pz(?P<pz>-?\d+)"
    r"_eginphase(?P<phase>-?\d+)"
    r"(?:_(?P<variant>[A-Za-z0-9]+))?"
    r"_"
    r"(?P<kind>contract|nopol_ss|pol\d+_ss)"
    rf"_conf{CONF_ID}\.npy$"
)


def parse_output_filename(name: str) -> dict | None:
    """解析 4150 参考输出名，返回 ``(Pz,Py,Px)`` 顺序的动量。

    ``variant='implicit'`` 表示参考文件名没有显式算符后缀；调用方保留这一
    信息而不从目录名猜测其物理含义。``None`` 表示不支持的文件。
    """
    match = _OUTPUT_RE.fullmatch(str(name))
    if match is None:
        return None
    return {
        "momentum": [
            int(match.group("pz")),
            int(match.group("py")),
            int(match.group("px")),
        ],
        "phase": int(match.group("phase")),
        "variant": match.group("variant") or "implicit",
        "kind": match.group("kind"),
    }


def _pplus() -> np.ndarray:
    """返回与 donghx 脚本相同的 ``1/2*(gamma(0)+gamma(4))``。"""
    return 0.5 * (np.asarray(gamma(0)) + np.asarray(gamma(4)))


def _polarization_projector(kind: str) -> np.ndarray:
    """返回 donghx 的 ``P+ (i gamma_d gamma5)`` 极化矩阵。"""
    if kind not in POLARIZATION_DIRECTIONS:
        choices = ", ".join(sorted(POLARIZATION_DIRECTIONS))
        raise ValueError(f"unknown polarization {kind!r}; choose {choices}")
    direction = POLARIZATION_DIRECTIONS[kind]
    return _pplus() @ (
        1j * np.asarray(gamma(direction)) @ np.asarray(gamma(5))
    )


def _compare_projected(
    contract: np.ndarray,
    projected: np.ndarray,
    projector: np.ndarray,
    *,
    einsum_indices: str,
) -> dict:
    """按指定自旋指标顺序比较一个投影数组。"""
    raw_contract = np.asarray(contract)
    raw_projected = np.asarray(projected)
    if raw_contract.ndim != 4 or raw_contract.shape[-2:] != (4, 4):
        return {
            "status": "diff",
            "reason": "contract_shape",
            "contract_shape": list(raw_contract.shape),
            "projected_shape": list(raw_projected.shape),
            "einsum_indices": einsum_indices,
        }
    if raw_projected.shape != raw_contract.shape[:2]:
        return {
            "status": "diff",
            "reason": "projected_shape",
            "contract_shape": list(raw_contract.shape),
            "projected_shape": list(raw_projected.shape),
            "einsum_indices": einsum_indices,
        }

    expected = np.einsum(
        f"{einsum_indices},yxil->yx",
        projector,
        raw_contract,
    )
    sink, source = np.indices(expected.shape)
    expected = expected.copy()
    expected[sink < source] *= -1.0
    delta = expected - raw_projected
    reference_norm = float(np.linalg.norm(raw_projected))
    rel_l2 = float(np.linalg.norm(delta) / max(reference_norm, 1e-300))
    max_abs = float(np.max(np.abs(delta), initial=0.0))
    is_complex64 = (
        raw_contract.dtype == np.dtype("complex64")
        or raw_projected.dtype == np.dtype("complex64")
    )
    tolerance = 5e-6 if is_complex64 else 1e-12
    return {
        "status": "pass" if rel_l2 <= tolerance else "diff",
        "metric": "rel_l2",
        "value": rel_l2,
        "max_abs": max_abs,
        "tolerance": tolerance,
        "einsum_indices": einsum_indices,
        "contract_dtype": str(raw_contract.dtype),
        "projected_dtype": str(raw_projected.dtype),
    }


def compare_contract_polarization(contract, polarized, kind: str) -> dict:
    """验证 ``contract`` 到一个 ``pol*_ss`` 的极化/边界投影。

    标准路径使用 ``einsum('li,yxil->yx', ...)``，与 donghx 2pt CPU/DCU
    实现及 PyQCD 的 ``(i,l)`` 收缩轴约定一致。旧的 ``L24x72_diffpol``
    变体使用 ``il``；若输入恰好符合该变体，只记录为旁证，不把它算作
    标准 ``li`` 通过。
    """
    projector = _polarization_projector(kind)
    result = _compare_projected(
        contract,
        polarized,
        projector,
        einsum_indices="li",
    )
    legacy = _compare_projected(
        contract,
        polarized,
        projector,
        einsum_indices="il",
    )
    result.update(
        {
            "kind": kind,
            "direction": POLARIZATION_DIRECTIONS[kind],
            "projector": "Pplus @ (1j * gamma(direction) @ gamma(5))",
            "legacy_transposed": legacy,
        }
    )
    if result["status"] == "diff" and legacy["status"] == "pass":
        result["reason"] = "matches_legacy_transposed_einsum"
    return result


def compare_contract_nopol(contract, nopol) -> dict:
    """验证 ``contract`` 到 ``nopol_ss`` 的正宇称/边界投影。

    参考脚本先计算 ``einsum('li,yxil->yx', Pplus, contract)``，再对
    ``t_sink < t_source`` 的反周期项乘 ``-1``。complex64 成品使用显式较宽
    容差；这不是把存储舍入误报成算法差异。
    """
    raw_contract = np.asarray(contract)
    raw_nopol = np.asarray(nopol)
    if raw_contract.ndim != 4 or raw_contract.shape[-2:] != (4, 4):
        return {
            "status": "diff",
            "reason": "contract_shape",
            "contract_shape": list(raw_contract.shape),
            "nopol_shape": list(raw_nopol.shape),
        }
    if raw_nopol.shape != raw_contract.shape[:2]:
        return {
            "status": "diff",
            "reason": "nopol_shape",
            "contract_shape": list(raw_contract.shape),
            "nopol_shape": list(raw_nopol.shape),
        }

    expected = np.einsum("li,yxil->yx", _pplus(), raw_contract)
    sink, source = np.indices(expected.shape)
    expected = expected.copy()
    expected[sink < source] *= -1.0
    delta = expected - raw_nopol
    reference_norm = float(np.linalg.norm(raw_nopol))
    rel_l2 = float(np.linalg.norm(delta) / max(reference_norm, 1e-300))
    max_abs = float(np.max(np.abs(delta), initial=0.0))
    is_complex64 = raw_contract.dtype == np.dtype("complex64") or raw_nopol.dtype == np.dtype("complex64")
    tolerance = 5e-6 if is_complex64 else 1e-12
    return {
        "status": "pass" if rel_l2 <= tolerance else "diff",
        "metric": "rel_l2",
        "value": rel_l2,
        "max_abs": max_abs,
        "tolerance": tolerance,
        "contract_dtype": str(raw_contract.dtype),
        "nopol_dtype": str(raw_nopol.dtype),
    }


def _array_meta(path: Path) -> dict:
    """读取 npy header 并扫描有限性；不把数据另存到工作区。"""
    result = {
        "path": str(path),
        "bytes": int(path.stat().st_size),
    }
    try:
        array = np.load(path, mmap_mode="r", allow_pickle=False)
        result.update(
            {
                "shape": list(array.shape),
                "dtype": str(array.dtype),
                "finite": bool(np.isfinite(array).all()),
            }
        )
    except Exception as exc:
        result.update(
            {
                "status": "unreadable",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    return result


def _load_array(meta: dict) -> np.ndarray:
    return np.asarray(np.load(meta["path"], allow_pickle=False))


def _peram_status() -> dict:
    states = []
    for path in INDEPENDENT_PERAM_ROOTS:
        states.append(
            {
                "path": str(path),
                "exists": path.exists(),
                "kind": "directory" if path.is_dir() else ("file" if path.is_file() else None),
            }
        )
    exists = any(item["exists"] for item in states)
    return {
        "status": "candidate_exists_unverified" if exists else "unverified",
        "paths": states,
        "reason": "independent_momentum_smeared_perambulator_not_verified",
    }


def inspect_directory(root: str | Path) -> dict:
    """检查一个 4150 momentum-smear 成品目录。"""
    root = Path(root)
    if not root.is_dir():
        return {
            "root": str(root),
            "exists": False,
            "file_count": 0,
            "group_count": 0,
            "groups": [],
            "unparsed_files": [],
        }

    files = sorted(path for path in root.iterdir() if path.is_file())
    groups: dict[tuple[tuple[int, int, int], int, str], dict] = {}
    unparsed = []
    for path in files:
        parsed = parse_output_filename(path.name)
        if parsed is None:
            if path.suffix == ".npy":
                unparsed.append(path.name)
            continue
        key = (tuple(parsed["momentum"]), parsed["phase"], parsed["variant"])
        group = groups.setdefault(
            key,
            {
                "momentum": parsed["momentum"],
                "phase": parsed["phase"],
                "variant": parsed["variant"],
                "files": {},
            },
        )
        group["files"][parsed["kind"]] = _array_meta(path)

    ordered = []
    for key in sorted(groups):
        group = groups[key]
        contract_meta = group["files"].get("contract")
        nopol_meta = group["files"].get("nopol_ss")
        if contract_meta is None or nopol_meta is None:
            group["projection"] = {
                "status": "unverified",
                "reason": "contract_or_nopol_missing",
            }
        elif "shape" not in contract_meta or "shape" not in nopol_meta:
            group["projection"] = {
                "status": "diff",
                "reason": "unreadable_input",
            }
        else:
            group["projection"] = compare_contract_nopol(
                _load_array(contract_meta), _load_array(nopol_meta)
            )
        polarizations = {}
        for kind in POLARIZATION_DIRECTIONS:
            polarized_meta = group["files"].get(kind)
            if polarized_meta is None:
                polarizations[kind] = {
                    "status": "unverified",
                    "reason": "polarization_output_missing",
                }
            elif contract_meta is None:
                polarizations[kind] = {
                    "status": "unverified",
                    "reason": "contract_missing",
                }
            elif "shape" not in contract_meta or "shape" not in polarized_meta:
                polarizations[kind] = {
                    "status": "diff",
                    "reason": "unreadable_input",
                }
            else:
                polarizations[kind] = compare_contract_polarization(
                    _load_array(contract_meta),
                    _load_array(polarized_meta),
                    kind,
                )
        group["polarizations"] = polarizations
        ordered.append(group)

    return {
        "root": str(root),
        "exists": True,
        "file_count": len(files),
        "group_count": len(ordered),
        "groups": ordered,
        "unparsed_files": unparsed,
    }


def inspect_roots(roots: dict[str, str | Path] | None = None) -> dict:
    """检查多个根目录并附上独立 smeared perambulator 的状态。"""
    selected = DEFAULT_ROOTS if roots is None else roots
    reports = {
        "schema": "pyqcd.donghx4150.2pt-output.v2",
        "conf_id": CONF_ID,
        "independent_smeared_perambulator": _peram_status(),
        "roots": {
            label: inspect_directory(root) for label, root in selected.items()
        },
    }
    return reports


def _summary(report: dict) -> str:
    lines = [
        "# 4150 2pt 最终输出级检查",
        "",
        "本检查验证参考成品的结构及 `contract → P+ / P+Σd → 反周期边界`；",
        "其中标准极化收缩为 `einsum('li,yxil->yx', ...)`；旧 `il` 变体只作诊断。",
        "不把普通 light perambulator 当作独立 momentum-smeared perambulator；"
        "`momsmear0` 仅表示参考输出配置，不据此推断存在独立涂抹 perambulator。",
        "",
        "| 根目录 | 文件数 | 动量组数 | nopol pass | 极化 pass/diff/unverified | 未解析 `.npy` |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, item in report["roots"].items():
        statuses = [group["projection"]["status"] for group in item["groups"]]
        polar_statuses = [
            status
            for group in item["groups"]
            for status in (
                item["status"] for item in group["polarizations"].values()
            )
        ]
        lines.append(
            "| {} | {} | {} | {} | {}/{}/{} | {} |".format(
                label,
                item["file_count"],
                item["group_count"],
                statuses.count("pass"),
                polar_statuses.count("pass"),
                polar_statuses.count("diff"),
                polar_statuses.count("unverified"),
                len(item["unparsed_files"]),
            )
        )
    peram = report["independent_smeared_perambulator"]
    lines.extend(
        [
            "",
            f"独立 momentum-smeared perambulator：**{peram['status']}**。",
            "候选根目录状态：",
            "",
            "| 路径 | exists | 类型 |",
            "|---|---:|---|",
        ]
    )
    for state in peram["paths"]:
        lines.append(f"| `{state['path']}` | {state['exists']} | {state['kind'] or '-'} |")
    return "\n".join(lines) + "\n"


def _parse_root_specs(specs: Iterable[str]) -> dict[str, Path]:
    roots = {}
    for spec in specs:
        if "=" not in spec:
            raise ValueError(f"--root 需要 LABEL=PATH，收到 {spec!r}")
        label, path = spec.split("=", 1)
        if not label or not path:
            raise ValueError(f"--root 需要非空 LABEL 和 PATH，收到 {spec!r}")
        roots[label] = Path(path)
    return roots


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        metavar="LABEL=PATH",
        help="覆盖默认根目录；可重复传入",
    )
    parser.add_argument("--output", default="", help="写 JSON 证据路径")
    parser.add_argument("--summary", default="", help="写 Markdown 摘要路径")
    args = parser.parse_args(argv)
    report = inspect_roots(_parse_root_specs(args.root) if args.root else None)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if args.summary:
        summary = Path(args.summary)
        summary.parent.mkdir(parents=True, exist_ok=True)
        summary.write_text(_summary(report))
    statuses = [
        group["projection"]["status"]
        for root in report["roots"].values()
        for group in root["groups"]
    ]
    polar_statuses = [
        status
        for root in report["roots"].values()
        for group in root["groups"]
        for status in (
            item["status"] for item in group["polarizations"].values()
        )
    ]
    diff_count = statuses.count("diff") + polar_statuses.count("diff")
    print(
        "inspect_4150_momsmear: roots={} groups={} pass={} diff={} "
        "unverified={} polar_pass={} polar_diff={} polar_unverified={} peram={}".format(
            len(report["roots"]),
            len(statuses),
            statuses.count("pass"),
            statuses.count("diff"),
            statuses.count("unverified"),
            polar_statuses.count("pass"),
            polar_statuses.count("diff"),
            polar_statuses.count("unverified"),
            report["independent_smeared_perambulator"]["status"],
        )
    )
    return 0 if diff_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
