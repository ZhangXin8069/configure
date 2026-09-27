#!/usr/bin/env python3
"""
TMD-PDF 扩展图表生成
====================

输入：已有的 TMD-PDF 产物（artifacts/initial_run/data + analysis）
输出：本目录下的 plots/ + 1_result/L24x72/Pz* + analysis/disconnected

用法：
    python -m pyqcd.testing.tmd.extended_plots
    python -m pyqcd.testing.tmd.extended_plots \
        --tmd-root artifacts/initial_run --out-root artifacts/extended_run
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path

from pyqcd.analysis import generate_test0_style_plots, generate_test6_style_plots

DEFAULT_CONF_IDS = [6250, 6450, 6650, 6850, 7050, 7250, 7450, 7650, 7850, 8050]
# 尝试从 test9 的 tmd_summary.json 自动推断 momenta
def infer_momenta(tmd_root: Path):
    for cand in [tmd_root / "analysis" / "tmd_summary.json",
                 tmd_root / "analysis_b" / "tmd_summary.json"]:
        if cand.exists():
            import json
            j = json.loads(cand.read_text())
            moms = j.get("momenta", [])
            tags = [f"P{m[0]}{m[1]}{m[2]}" for m in moms]
            # 排除 P000 作分母但仍需画？保留全部用于 plots
            return tags
    # fallback: 探测 data 目录
    import glob
    cdir = tmd_root / "data" / "conf6250"
    if cdir.exists():
        tags = set()
        for p in cdir.glob("corr_pp_*.h5"):
            # corr_pp_P200_6250.h5 -> P200
            name = p.name
            parts = name.split("_")
            for part in parts:
                if part.startswith("P") and len(part) >= 4 and part[1:].isdigit():
                    tags.add(part)
        if tags:
            return sorted(tags)
    return ["P000", "P200", "P400"]

def main():
    ap = argparse.ArgumentParser(description="TMD-PDF 扩展图表")
    ap.add_argument(
        "--tmd-root",
        default=str(Path(__file__).parent / "artifacts" / "initial_run"))
    ap.add_argument(
        "--out-root",
        default=str(Path(__file__).parent / "artifacts" / "extended_run"))
    ap.add_argument("--conf-ids", default=",".join(map(str, DEFAULT_CONF_IDS)))
    args = ap.parse_args()
    tmd_root = Path(args.tmd_root).resolve()
    out_root = Path(args.out_root).resolve()
    conf_ids = [int(x) for x in args.conf_ids.split(",") if x.strip()]
    out_root.mkdir(parents=True, exist_ok=True)
    print(f"tmd_root={tmd_root}")
    print(f"out_root={out_root}")
    print(f"conf_ids={conf_ids}")

    # 推断 momenta：优先用 analysis_b（更全），fallback 用 analysis
    tags = infer_momenta(tmd_root)
    # 若 analysis_b 存在且比 analysis 更全，优先用 b 的标签但数据读取会同时尝试两个目录
    alt_tags = []
    for cand in [tmd_root / "analysis_b" / "tmd_summary.json"]:
        if cand.exists():
            import json
            j = json.loads(cand.read_text())
            moms = j.get("momenta", [])
            alt_tags = [f"P{m[0]}{m[1]}{m[2]}" for m in moms]
    # 合并去重，保证包含 P000,P200,P400 等
    all_tags = sorted(set(tags) | set(alt_tags))
    if not all_tags:
        all_tags = ["P000", "P200", "P400"]
    print(f"momentum_tags={all_tags}")

    # 额外：若 test9_root/analysis_b 存在，临时将 analysis_b 内容合并到 analysis 以便统一读取
    # generate functions 会自动尝试 analysis_b 备用路径，无需物理复制

    logger = lambda *a: print(*a)
    print("\n=== 生成 test0 风格 3 图 ===")
    generate_test0_style_plots(str(tmd_root), str(out_root), conf_ids,
                               all_tags, logger=logger)

    print("\n=== 生成 test6 风格 7 图 per Pz ===")
    generate_test6_style_plots(str(tmd_root), str(out_root), conf_ids,
                               all_tags, logger=logger)

    # 额外：复制 tmd_ratio 原有图表到本目录以便一站式查看（不重复计算）
    import shutil
    for sub in ["analysis/tmd_ratio", "analysis_b/tmd_ratio"]:
        src = tmd_root / sub
        if src.exists():
            dst = Path(out_root) / sub
            dst.parent.mkdir(parents=True, exist_ok=True)
            # 若 dst 不存在则复制，存在则跳过（避免覆盖新生成的）
            if not dst.exists():
                shutil.copytree(src, dst)
                print(f"copied {src} -> {dst}")
            else:
                print(f"already exists {dst}, skip copy")

    # 汇总
    print("\n=== 产物清单 ===")
    for d in ["plots", "analysis/disconnected", "1_result"]:
        p = Path(out_root) / d
        if p.exists():
            import subprocess
            subprocess.run(["ls", "-lh", str(p)], check=False)
            subprocess.run(["find", str(p), "-type", "f", "|", "head", "-20"], shell=True, check=False)
    print("generate_extended_plots done")

if __name__ == "__main__":
    main()
