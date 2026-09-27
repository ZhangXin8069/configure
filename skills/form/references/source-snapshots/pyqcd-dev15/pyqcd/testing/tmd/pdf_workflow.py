#!/usr/bin/env python3
"""
梯度流重整化核子胶子 TMD-PDF 全物理链（真实数据）
==================================================

调用 pyqcd 包（pyqcd.pipeline._tmd9 + renorm/analysis/operator）在真实
蒸馏数据（eigvec/peram/gauge，10 组态 beta6.20_mu-0.2770_ms-0.2400_L24x72）
上计算核子中胶子 TMD-PDF：

    1. 蒸馏 2pt（核子谱线，多动量：z 方向 [0,2,4] 或全方向 [0,2]）
    2. 梯度流：gauge → wilson_flow(τ=3a²) → flowed gauge
    3. 胶子 TMD 算符 O(z,b⊥)（flowed gauge 上，逐时间片空间求和）
    4. 不相连 3pt 因子化 + 真空扣除 + 比值 R
    5. 逐 (z,b) 拟合 → 裸矩阵元 c0(z,b,Pz)
    6. 自重整化（比值/混合方案）→ 准 TMD-PDF
    7. NLO 匹配 → 光锥 TMD-PDF x·g(x,b⊥) + CS 核
    8. 全图表输出 + JSON 汇总

产出：`pyqcd/testing/tmd/artifacts/work/`（数据 + 图表 + 报告）。

用法：
    python -m pyqcd.testing.tmd.pdf_workflow --smoke
    python -m pyqcd.testing.tmd.pdf_workflow --conf-ids 6250 --momenta A
    python -m pyqcd.testing.tmd.pdf_workflow
    mpirun -np N python -m pyqcd.testing.tmd.pdf_workflow --full
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                    '..', '..', '..'))

from pyqcd.pipeline._tmd9 import (
    MOMENTA_Z, MOMENTA_ALL, momentum_tag, parse_momentum_tag,
    compute_vertices_multi, compute_2pt_multi, compute_tmd_ope_time,
    load_multi_2pt, load_tmd_ope_all, self_renormalize,
)
from pyqcd.tools import set_backend, get_backend_name

DEFAULT_CONF_IDS = [6250, 6450, 6650, 6850, 7050,
                    7250, 7450, 7650, 7850, 8050]

OUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'artifacts', 'work')
LOG_ROOT = os.path.join(ROOT, 'logs', 'tmd_pdf')

# TMD 算符参数（格点单位）
Z_LIST = list(range(0, 13))          # z ∈ 0..12（Wilson 线纵向分离）
B_LIST = [0, 1, 2, 3, 4]             # b⊥ ∈ 0..4（横向位移）
STAPLE_LENGTH = max(abs(z) for z in Z_LIST)  # 全 z 扫描共享的固定臂长
TAU = 3.0                            # τ=3a² → 格点流时间 t=3
EPS = 0.05                           # RK3 步长（Luescher ≤0.05 保证 O(ε³)，60 步）


def parse_args():
    ap = argparse.ArgumentParser(description='梯度流胶子 TMD-PDF')
    ap.add_argument('--conf-ids', type=str, default=None,
                    help='逗号分隔组态（默认全 10 组态）')
    ap.add_argument('--momenta', choices=['A', 'B', 'Z'], default='A',
                    help='A=z 方向[0,2,4]; B=全方向{0,2}; Z=仅 z 方向（与A同）')
    ap.add_argument('--smoke', action='store_true',
                    help='冒烟：单组态(6250) 单动量(P200)')
    ap.add_argument('--smoke-mom', type=str, default='P200',
                    help='冒烟动量标签（默认 P200；多位/负分量如 P10_-2_0）')
    ap.add_argument('--skip-2pt', action='store_true', help='跳过蒸馏 2pt')
    ap.add_argument('--skip-ope', action='store_true', help='跳过梯度流 TMD 算符')
    ap.add_argument('--backend', default='torch', choices=['torch', 'numpy'])
    ap.add_argument('--precision', default='complex64',
                    choices=['complex64', 'complex128'])
    ap.add_argument('--staple-length', type=int, default=STAPLE_LENGTH,
                    help='所有 z 共享的 staple 臂长（格点单位，默认 12）')
    ap.add_argument('--out', default=None,
                    help='输出目录（默认 pyqcd/testing/tmd/artifacts/work）')
    ap.add_argument('--only-plot', action='store_true',
                    help='仅从已有数据重新出图+分析')
    ap.add_argument('--dry-run', action='store_true')
    return ap.parse_args()


def select_run_scope(args):
    """把 CLI 选择规范化为组态列表和唯一有序动量列表。"""
    if args.smoke:
        return [6250], [parse_momentum_tag(args.smoke_mom)]
    if args.conf_ids:
        conf_ids = [int(value) for value in args.conf_ids.split(',')]
    else:
        conf_ids = list(DEFAULT_CONF_IDS)
    momenta = MOMENTA_Z if args.momenta in ('A', 'Z') else MOMENTA_ALL
    return conf_ids, list(momenta)


def main():
    args = parse_args()
    out_dir = args.out or OUT_ROOT
    log_dir = LOG_ROOT

    logger = lambda *a: print(*a)

    conf_ids, momenta = select_run_scope(args)

    mom_tags = [momentum_tag(m) for m in momenta]
    logger(f"=== 梯度流核子胶子 TMD-PDF ===")
    logger(f"  组态: {conf_ids}")
    logger(f"  动量: {list(momenta)} ({mom_tags})")
    logger(f"  z_list={Z_LIST}, b_list={B_LIST}, "
           f"staple_length={args.staple_length}, tau={TAU}")
    logger(f"  输出: {out_dir}")
    logger(f"  backend={args.backend}, precision={args.precision}")

    if args.dry_run:
        return

    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    set_backend(args.backend, device='cuda:0' if args.backend == 'torch' else None)

    run_dir = out_dir
    data_dir = os.path.join(run_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)

    # ── 阶段 1：蒸馏顶点 + 2pt（多动量）─────────────────────────────
    if not args.only_plot and not args.skip_2pt:
        for cid in conf_ids:
            logger(f"\n─── 2pt: conf {cid} 动量 {mom_tags} ───")
            t0 = time.perf_counter()
            verts = compute_vertices_multi(cid, run_dir, logger, momenta,
                                           precision=args.precision)
            acc = compute_2pt_multi(cid, run_dir, logger, verts, momenta,
                                    precision=args.precision,
                                    channels=('pp',))
            logger(f"  2pt conf={cid} done in {time.perf_counter()-t0:.0f}s")
    else:
        logger("跳过蒸馏 2pt（--skip-2pt）")

    # ── 阶段 2：梯度流 + 胶子 TMD 算符矩阵元 ────────────────────────
    if not args.only_plot and not args.skip_ope:
        flow_dir = os.path.join(run_dir, 'flowed')
        for cid in conf_ids:
            logger(f"\n─── 梯度流 TMD 算符: conf {cid} ───")
            t0 = time.perf_counter()
            res = compute_tmd_ope_time(
                cid, run_dir, logger, Z_LIST, B_LIST,
                tau=TAU, eps=EPS, precision=args.precision,
                gauge_flow_dir=flow_dir,
                staple_length=args.staple_length)
            logger(f"  TMD OPE conf={cid} done in {time.perf_counter()-t0:.0f}s")
    else:
        logger("跳过梯度流 TMD 算符（--skip-ope）")

    # ── 阶段 3：分析 + 出图 ────────────────────────────────────────
    run_analysis(conf_ids, momenta, run_dir, logger, args)


def run_analysis(conf_ids, momenta, run_dir, logger, args):
    from pyqcd.analysis import (
        run_disconnected_tmd_ratio, plot_tmd_c0, plot_tmd_ratio,
    )
    from pyqcd.pipeline._tmd9 import load_tmd_ope_all

    mom_tags = [momentum_tag(m) for m in momenta]
    corr2 = load_multi_2pt(
        run_dir, conf_ids, mom_tags, channels=('pp',), logger=logger,
        momenta=momenta, precision=args.precision)
    ope = load_tmd_ope_all(
        run_dir, conf_ids, Z_LIST, B_LIST, logger=logger,
        staple_length=args.staple_length,
        tau=TAU, eps=EPS, precision=args.precision)

    results = {}
    for tag in mom_tags:
        if tag == 'P000':
            continue   # Pz=0 作分母，不单独分析比值
        # 跳过缺失 2pt 的动量（如冒烟只算了 P200）
        has = any(f'corr_pp_{tag}' in corr2[cid] for cid in corr2)
        if not has:
            logger(f"  跳过 {tag}：无 2pt 数据")
            continue
        logger(f"\n=== 动量 {tag}：不相连 TMD ratio + 拟合 ===")
        res = run_disconnected_tmd_ratio(
            corr2, ope, conf_ids, run_dir, logger=logger,
            NT=72, nz=len(Z_LIST), nb=len(B_LIST),
            dt_max=20, dt_start=7, dt_end=10, cut=6,
            momentum=tag)
        plot_tmd_c0(res, run_dir, tag, logger=logger,
                    nz=len(Z_LIST), nb=len(B_LIST))
        plot_tmd_ratio(res, run_dir, tag, logger=logger,
                       nz=len(Z_LIST), nb=len(B_LIST))
        results[tag] = {
            'c0_mean': np.asarray(res['proton']['c0']).mean(0).tolist(),
            'c0_err': None,
        }
        # 保存均值/误差（用 plateau 均值：10 组态统计下比 lsqfit 更稳健）
        c0 = np.asarray(res['proton']['c0'])
        from pyqcd.analysis import sem
        np.save(os.path.join(run_dir, 'analysis', 'tmd_ratio',
                             f'c0_mean_{tag}.npy'), c0.mean(0))
        np.save(os.path.join(run_dir, 'analysis', 'tmd_ratio',
                             f'c0_err_{tag}.npy'), sem(c0, True))
        # plateau-mean 版本已由 run_disconnected_tmd_ratio 直接产出
        # （pyqcd.analysis.plateau_c0，fit 窗口内 ratio 均值，抗奇异协方差）

    # ── 阶段 4：自重整化 + 匹配 → TMD-PDF ──────────────────────────
    run_tmd_pdf_chain(conf_ids, run_dir, logger, args, momenta=momenta)
    write_summary(run_dir, conf_ids, momenta, logger)


def load_verified_plateau_inputs(analysis_dir, momenta, logger=print):
    """读取有状态、逐样本、纯纵向正动量 plateau，拒绝伪 fallback。"""
    analysis_dir = os.fspath(analysis_dir)
    verified = {}

    def log(message):
        if logger is not None:
            logger(message)

    for momentum in momenta:
        tag = momentum_tag(momentum)
        pz, py, px = parse_momentum_tag(tag)
        if pz <= 0 or py != 0 or px != 0:
            log(f"  [warn] {tag} is not a positive longitudinal momentum; "
                "PDF input unavailable")
            continue
        data_path = os.path.join(analysis_dir, f'c0_plateau_{tag}.npy')
        status_path = os.path.join(
            analysis_dir, f'c0_plateau_status_{tag}.npz')
        if not os.path.isfile(data_path):
            log(f"  [warn] {tag} plateau data unavailable")
            continue
        if not os.path.isfile(status_path):
            log(f"  [warn] {tag} plateau status unavailable; "
                "numeric-only legacy data is not a verified PDF input")
            continue
        try:
            with np.load(status_path, allow_pickle=False) as metadata:
                if 'plateau_status' not in metadata.files:
                    raise ValueError('missing plateau_status')
                status = str(metadata['plateau_status'])
            c0 = np.load(data_path, allow_pickle=False)
        except (OSError, ValueError, KeyError) as exc:
            log(f"  [warn] {tag} plateau artifact unavailable: {exc}")
            continue
        if status != 'identifiable':
            log(f"  [warn] {tag} plateau status={status}; PDF input unavailable")
            continue
        c0 = np.asarray(c0)
        if (c0.ndim != 3 or c0.shape[0] < 2
                or c0.shape[1] < 1 or c0.shape[2] < 1):
            log(f"  [warn] {tag} plateau sample shape must be "
                f"(Nsample>=2,nz>=1,nb>=1), got {c0.shape}")
            continue
        if not np.isfinite(c0).all() or np.any(c0[:, 0, :] == 0):
            log(f"  [warn] {tag} plateau samples are nonfinite or have "
                "zero z=0 normalization")
            continue
        hR, _ = self_renormalize(c0)
        if not np.isfinite(hR).all():
            log(f"  [warn] {tag} renormalized plateau is nonfinite")
            continue
        verified[tag] = {
            'c0': c0,
            'hR': hR.mean(0),
            'pz_lattice': pz,
            'status': status,
        }
    return verified


def run_tmd_pdf_chain(conf_ids, run_dir, logger, args, *, momenta=None):
    """从 c0(z,b,Pz) 走自重整化/混合 → 准 TMD-PDF → NLO 匹配 → 光锥 TMD-PDF。"""
    from pyqcd.renorm import (
        quasi_tmd_pdf, cs_kernel_from_ratio, tmd_matching_hybrid,
        pz_to_gev, fm_to_GeV, a_len_set,
    )
    an_dir = os.path.join(run_dir, 'analysis', 'tmd_ratio')
    os.makedirs(an_dir, exist_ok=True)

    if momenta is None:
        momenta = MOMENTA_Z
    hR_store = load_verified_plateau_inputs(an_dir, momenta, logger=logger)

    # 保持请求顺序选择主 Pz；CS 核在前两个不同的正纵向动量间构造。
    if not hR_store:
        logger("  [warn] 无有状态的 Pz>0 逐样本矩阵元，跳过 PDF 链")
        return
    main_tag = next(iter(hR_store))

    conf = 'L24x72'
    pz_lattice = hR_store[main_tag]['pz_lattice']
    pz_gev = pz_to_gev(pz_lattice, conf)
    z_grid = np.array(Z_LIST) * (a_len_set[conf] * fm_to_GeV)   # fm
    b_grid = np.array(B_LIST) * (a_len_set[conf] * fm_to_GeV)   # fm

    hR = hR_store[main_tag]['hR']        # (nz, nb)
    # 准 TMD-PDF：x·g̃(x, b⊥, Pz)
    x_grid = np.linspace(0.02, 0.98, 128)
    x, xg = quasi_tmd_pdf(hR, z_grid, b_grid, pz_gev=pz_gev,
                          x_grid=x_grid, z_max=z_grid[-1])

    # CS 核（两动量比值，若有）：pyqcd.renorm.cs_kernel_two_momentum
    # （z_ref=1 起始 + clamp 数值保护，整合自本示例原内联实现）
    K = None
    if len(hR_store) >= 2:
        tags2 = list(hR_store)[:2]
        p1 = hR_store[tags2[0]]['pz_lattice']
        p2 = hR_store[tags2[1]]['pz_lattice']
        if p1 != p2:
            from pyqcd.renorm import cs_kernel_two_momentum
            c01 = hR_store[tags2[0]]['c0']
            c02 = hR_store[tags2[1]]['c0']
            K = cs_kernel_two_momentum(c01.mean(0), c02.mean(0),
                                       pz_to_gev(p1, conf), pz_to_gev(p2, conf),
                                       z_ref=1, k_clip=(-3.0, 3.0))

    # NLO 匹配 → 光锥 TMD-PDF x·g(x, b⊥)
    xm, xg_match = tmd_matching_hybrid(
        x_grid, b_perp=b_grid, mu=2.0, pz_gev=pz_gev,
        cs_kernel=(K if K is not None else 0.0),
        soft_factor=1.0, x_tmd=xg,
        lambda_s_fm=0.3)

    np.save(os.path.join(an_dir, 'quasi_tmd_pdf_x.npy'), x)
    np.save(os.path.join(an_dir, 'quasi_tmd_pdf_xg.npy'), xg)
    np.save(os.path.join(an_dir, 'matched_tmd_pdf_xg.npy'), xg_match)
    if K is not None:
        np.save(os.path.join(an_dir, 'cs_kernel_b.npy'), K)
        np.save(os.path.join(an_dir, 'cs_kernel_bgrid.npy'), b_grid)
    np.save(os.path.join(an_dir, 'b_grid_fm.npy'), b_grid)
    np.save(os.path.join(an_dir, 'z_grid_fm.npy'), z_grid)
    np.savez(
        os.path.join(an_dir, 'pdf_chain_input_status.npz'),
        momentum_tag=np.asarray(main_tag),
        pz_lattice=np.asarray(pz_lattice, dtype=np.int64),
        input_status=np.asarray(hR_store[main_tag]['status']),
        n_verified_momenta=np.asarray(len(hR_store), dtype=np.int64),
    )

    from pyqcd.analysis import plot_tmd_pdf
    plot_tmd_pdf(x, xg, xg_match, b_grid, K, main_tag, an_dir, logger)


def write_summary(run_dir, conf_ids, momenta, logger):
    summary = {
        'workflow': 'gradient-flow gluon TMD-PDF in nucleon',
        'conf_ids': conf_ids,
        'momenta': [list(m) for m in momenta],
        'z_list': Z_LIST, 'b_list': B_LIST,
        'tau': TAU, 'eps': EPS,
        'backend': get_backend_name(),
        'time': datetime.now().isoformat(),
    }
    an_dir = os.path.join(run_dir, 'analysis', 'tmd_ratio')
    for f in os.listdir(an_dir):
        if f.endswith('.npy'):
            try:
                arr = np.load(os.path.join(an_dir, f))
                summary[f'shape_{f[:-4]}'] = list(arr.shape)
            except Exception:
                pass
    with open(os.path.join(run_dir, 'analysis', 'tmd_summary.json'), 'w') as fp:
        json.dump(summary, fp, indent=2, default=str)
    logger(f"  Summary -> {os.path.join(run_dir, 'analysis', 'tmd_summary.json')}")


if __name__ == '__main__':
    main()
