#!/usr/bin/env python3
"""
有效质量谱产物断言
==================

用法：python -m pyqcd.testing.spectrum.verify_effective_mass <run_dir>

断言：
  A. 图表齐全性——对照两参考目录的类型清单（A3 ratio_3pt 因输入无 3pt 数据
     跳过，断言其"缺席有据"而非存在）；
  B. 数据形状——corr2_{P0,P2}.npy = (Nconf, DT_MAX)，拟合 npz 键与有限性；
  C. 物理自洽——A 型 P0 E0 ≈ 质子质量 ~1.1 GeV（stab1 已验证结论量级）、
     P2 > P0、色散 |E2−√(m0²+p²)|/√(m0²+p²) < 10%、A/B 两独立方法 E0 互差
     < 0.15 GeV。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

NT = 72
NX = 24
DT_MAX = 20
ALTTc = 0.1053
UNIT = 0.197 / ALTTc
CHANNELS = ("P0", "P2")

B_PLOTS = ["eff_mass.png", "sem_comparison.png", "eff_mass_GeV.png",
           "eff_mass_fit_dirs.png", "corr2_raw.png", "meff_corr.png",
           "meff_hist.png"]
A_PLOTS = ["correlators_all_channels.png", "meff_all_channels.png"]
SKIP_PLOTS = {"ratio_3pt_all_channels.png":
              "需连通 3pt/perambulators 数据，输入数据集中不存在"}

FAILS = []


def check(name, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def main(run_dir):
    summary_path = os.path.join(run_dir, "analysis_summary.json")
    with open(summary_path) as f:
        s = json.load(f)
    nconf = s["Nconf"]

    # A. 图表齐全性
    for p in B_PLOTS + A_PLOTS:
        fp = os.path.join(run_dir, p)
        check(f"plot:{p}", os.path.isfile(fp) and os.path.getsize(fp) > 1000,
              f"{os.path.getsize(fp)} bytes" if os.path.isfile(fp) else "missing")
    for p, why in SKIP_PLOTS.items():
        notes = " ".join(s.get("plots_expected_missing", []))
        check(f"skip-justified:{p}",
              (not os.path.exists(os.path.join(run_dir, p))) and p in notes,
              f"缺席且已注明根因：{why}")

    # B. 数据形状与有限性
    for ch in CHANNELS:
        fp = os.path.join(run_dir, f"corr2_{ch}.npy")
        a = np.load(fp)
        check(f"shape:corr2_{ch}", a.shape == (nconf, DT_MAX), str(a.shape))
    z = np.load(os.path.join(run_dir, "1_fit_data.npz"))
    for ch in CHANNELS:
        e0 = z[f"E0_{ch}"]
        chi2 = z[f"chi2_{ch}"]
        frac_bad = float(np.mean(~np.isfinite(e0)))
        check(f"fit:E0_{ch}", frac_bad < 0.05 and np.nanmean(e0) > 0.1,
              f"E0={np.nanmean(e0):.4f}(lat) bad={frac_bad:.1%}")
        check(f"fit:chi2_{ch}", 0 < np.nanmean(chi2) < 20,
              f"chi2/dof={np.nanmean(chi2):.2f}")
    check("report_txt",
          os.path.getsize(os.path.join(run_dir, "2_fit_report.txt")) > 200)

    # C. 物理自洽
    pa = s["part_a"]
    pb = s["part_b"]
    m0_a = pa.get("proton_P0", {}).get("E0_GeV", np.nan)
    m2_a = pa.get("proton_P2", {}).get("E0_GeV", np.nan)
    check("phys:P0_mass_scale", 0.9 < m0_a < 1.4,
          f"A-type E0(P0)={m0_a:.3f} GeV（stab1 验证量级 ≈1.12）")
    check("phys:P2>P0", m2_a > m0_a, f"{m2_a:.3f} > {m0_a:.3f}")
    p_phys = (2 * np.pi * 2 / NX) * UNIT
    edisp = np.sqrt(m0_a ** 2 + p_phys ** 2)
    rel = abs(m2_a - edisp) / edisp
    check("phys:dispersion", rel < 0.10,
          f"|E2−√(m0²+p²)|/E = {rel:.1%} (p={p_phys:.3f} GeV)")
    for ch in CHANNELS:
        d = abs(pb[ch]["E0_GeV"] - pa[f"proton_{ch}"]["E0_GeV"])
        check(f"cross:A-B_E0_{ch}", d < 0.15,
              f"B={pb[ch]['E0_GeV']:.3f} vs A={pa[f'proton_{ch}']['E0_GeV']:.3f}"
              f" GeV, |d|={d * 1e3:.0f} MeV")

    print("=" * 60)
    if FAILS:
        print(f"verify: {len(FAILS)} FAIL → {FAILS}")
        return 1
    print("verify: ALL PASS")
    return 0


def cli():
    parser = argparse.ArgumentParser(description='验证有效质量谱产物')
    parser.add_argument('run_dir', nargs='?', default='.')
    args = parser.parse_args()
    return main(args.run_dir)


if __name__ == "__main__":
    sys.exit(cli())
