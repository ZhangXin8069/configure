#!/usr/bin/env python3
"""
有效质量谱与 ratio 链产物断言
=============================

用法：python -m pyqcd.testing.spectrum.verify_effective_mass_ratio <run_dir>

断言：
  A. 图表齐全性——10 类目标图全部存在（基础谱链 9 类 + ratio 链新增
     ratio_3pt_all_channels.png；后者为 disconnected OPE 比值型，
     非 perambulator 连通 3pt，物理语义已在图题注明）；
  B. 数据形状——corr2_{P0,P2}.npy=(Nconf,20)、拟合 npz 键/有限性、
     02 链产物（ratio npy 形状 (Nconf,20,20,24)、3 窗口拟合目录、
     主窗口 |c0(z<=4)|<2 与 chi2 合理）；
  C. 物理自洽——P0 E0 ~ 质子质量量级、P2>P0、色散 <10%、A/B 双方法
     E0 互差 <0.15 GeV、与基础谱运行跨一致性 <0.10 GeV
     （组态集外部删减后的漂移检查）。
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
RATIO_PZ = 2

B_PLOTS = ["eff_mass.png", "sem_comparison.png", "eff_mass_GeV.png",
           "eff_mass_fit_dirs.png", "corr2_raw.png", "meff_corr.png",
           "meff_hist.png"]
A_PLOTS = ["correlators_all_channels.png", "meff_all_channels.png"]
C_PLOT = "ratio_3pt_all_channels.png"

FAILS = []


def check(name, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def main(run_dir):
    here = os.path.dirname(os.path.abspath(__file__))
    summary_path = os.path.join(run_dir, "analysis_summary.json")
    with open(summary_path) as f:
        s = json.load(f)
    nconf = s["Nconf"]

    # A. 图表齐全性（10 型全查，无跳过项）
    for p in B_PLOTS + A_PLOTS + [C_PLOT]:
        fp = os.path.join(run_dir, p)
        check(f"plot:{p}", os.path.isfile(fp) and os.path.getsize(fp) > 1000,
              f"{os.path.getsize(fp)} bytes" if os.path.isfile(fp) else "missing")
    check("summary:no_missing_plots",
          s.get("plots_expected_missing") == [],
          str(s.get("plots_expected_missing")))
    check("summary:nconf_note", "实际存在" in s.get("nconf_note", ""))

    # B1. 数据形状与有限性（Part A/B，同 dev6）
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

    # B2. 02 链产物（Part C）
    pc = s.get("part_c") or {}
    if not pc:
        check("part_c:present", False, "summary 缺 part_c（--skip-ratio?）")
        print("=" * 60)
        print(f"verify: {len(FAILS)} FAIL -> {FAILS}")
        return 1
    rshape = tuple(pc["ratio_shape"])
    check("part_c:ratio_shape", rshape == (nconf, DT_MAX, DT_MAX, NX),
          str(rshape))
    ratio_path = os.path.join(
        run_dir, "L24x72",
        f"ratio_Pz{RATIO_PZ}_Nsam{nconf}_dtmax{DT_MAX}.npy")
    ok_r = os.path.isfile(ratio_path)
    check("part_c:ratio_npy", ok_r, ratio_path if not ok_r else "")
    if ok_r:
        rr = np.load(ratio_path)
        cen = rr[:, 4:14, 4:14, :8]
        frac_fin = float(np.mean(np.isfinite(cen)))
        check("part_c:ratio_finite", frac_fin > 0.95,
              f"finite={frac_fin:.1%}（中心区 [4:14,4:14,z<8]）")
    wins = {tuple(w) for w in pc["windows"]}
    check("part_c:windows", wins == {(6, 11, 2), (7, 11, 3), (9, 11, 4)},
          str(sorted(wins)))
    prim = os.path.join(run_dir, "L24x72", pc["primary_fit_dir"])
    fz = np.load(os.path.join(prim, "0_fit_data.npz"))
    c0 = fz["c0"]                       # (Nsample, Nz)
    chi2z = fz["chi2"].mean(0)
    check("part_c:c0_finite_small_z",
          float(np.mean(np.isfinite(c0[:, :5]))) > 0.99,
          f"finite={np.mean(np.isfinite(c0[:, :5])):.1%} (z<=4)")
    c0m = np.nanmean(c0, axis=0)
    mag_ok = bool(np.all(np.abs(c0m[:5]) < 2.0))
    check("part_c:|c0|<2_small_z", mag_ok,
          f"c0(z=0..4)={np.round(c0m[:5], 3).tolist()}")
    check("part_c:chi2_reasonable",
          bool(np.all((chi2z[:8] > 0) & (chi2z[:8] < 20))),
          f"chi2(z=0..7) mean={chi2z[:8].mean():.2f}")
    for aux in ["1_fit_report.txt", "ratio.png", "c0.png", "chi2.png"]:
        fp = os.path.join(prim, aux)
        check(f"part_c:{aux}", os.path.isfile(fp) and os.path.getsize(fp) > 200)

    # C. 物理自洽
    pa = s["part_a"]
    pb = s["part_b"]
    m0_a = pa.get("proton_P0", {}).get("E0_GeV", np.nan)
    m2_a = pa.get("proton_P2", {}).get("E0_GeV", np.nan)
    check("phys:P0_mass_scale", 0.9 < m0_a < 1.4,
          f"A-type E0(P0)={m0_a:.3f} GeV（stab1 验证量级 ~1.12）")
    check("phys:P2>P0", m2_a > m0_a, f"{m2_a:.3f} > {m0_a:.3f}")
    p_phys = (2 * np.pi * RATIO_PZ / NX) * UNIT
    edisp = np.sqrt(m0_a ** 2 + p_phys ** 2)
    rel = abs(m2_a - edisp) / edisp
    check("phys:dispersion", rel < 0.10,
          f"|E2-sqrt(m0^2+p^2)|/E = {rel:.1%} (p={p_phys:.3f} GeV)")
    for ch in CHANNELS:
        d = abs(pb[ch]["E0_GeV"] - pa[f"proton_{ch}"]["E0_GeV"])
        check(f"cross:A-B_E0_{ch}", d < 0.15,
              f"B={pb[ch]['E0_GeV']:.3f} vs A={pa[f'proton_{ch}']['E0_GeV']:.3f}"
              f" GeV, |d|={d * 1e3:.0f} MeV")

    # D. 与基础谱运行的跨一致性
    # summary json 可能未被跟踪，数值固化于此作为回退；
    # 本地文件存在时以文件为准。
    ref_e0 = {"proton_P0": 1.1473901702295601,
              "proton_P2": 1.5477404566750945}   # A 型 E0 [GeV]
    ref_path = os.path.normpath(os.path.join(
        here, "artifacts", "effective_mass", "analysis_summary.json"))
    if os.path.isfile(ref_path):
        with open(ref_path) as f:
            ref = json.load(f)
        for ch in CHANNELS:
            ref_e0[f"proton_{ch}"] = ref["part_a"][f"proton_{ch}"]["E0_GeV"]
    for ch in CHANNELS:
        e_now = pa[f"proton_{ch}"]["E0_GeV"]
        e_ref = ref_e0[f"proton_{ch}"]
        d = abs(e_now - e_ref)
        check(f"xrun:E0_{ch}_vs_effective_mass", d < 0.10,
              f"ratio={e_now:.3f} vs base={e_ref:.3f} GeV, "
              f"|d|={d * 1e3:.0f} MeV (<100 MeV)"
              + ("" if os.path.isfile(ref_path) else " [内置参考值]"))

    print("=" * 60)
    if FAILS:
        print(f"verify: {len(FAILS)} FAIL -> {FAILS}")
        return 1
    print("verify: ALL PASS")
    return 0


def cli():
    parser = argparse.ArgumentParser(description='验证有效质量谱与 ratio 链产物')
    parser.add_argument('run_dir', nargs='?', default='.')
    args = parser.parse_args()
    return main(args.run_dir)


if __name__ == "__main__":
    sys.exit(cli())
