"""
管线数据守卫：原始数据齐全度 / 输入数组校验 / ETA 进度日志
============================================================

整合 data/from-logs/logs/test7、data/from-logs/logs/test8 的工程化前置检查（照抄其逻辑，
泛化为路径与形状参数化版本；不 import logs/）：

    - check_raw_data：三类蒸馏原始数据（eigensystem / perambulators /
      configurations lime）逐组态齐全度，bad_list 明细（makedata 前置守卫）；
    - check_input_arrays：分析链输入数组（corr_pp / ops 等）存在性 +
      形状 + 有限性逐项校验（run 前置守卫）；
    - ProgressLog：时间戳 + flush + ETA 的轻量进度日志（服务器 nohup/tee
      下实时落盘可调控，tlog 语义）。

约定：返回 (n_ok, bad_list)，bad_list 为空才允许继续后续步骤。
"""
from __future__ import annotations

import os
import time
from datetime import datetime

import numpy as np


def progress_log(msg):
    """tlog 语义：[HH:MM:SS] + 立即 flush。"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


class ProgressLog:
    """分步进度日志器：每 k 步打印 时间戳/进度/已用/ETA。"""

    def __init__(self, total, label="", every=10, logger=progress_log):
        self.total = int(total)
        self.label = label
        self.every = max(int(every), 1)
        self.logger = logger
        self.t0 = time.perf_counter()
        self.done = 0

    def step(self, n_done=None, extra=""):
        """推进到第 n_done 步（缺省自增 1）；每逢 every 打印 ETA。"""
        if n_done is None:
            self.done += 1
        else:
            self.done = int(n_done)
        n = self.done
        if not (n % self.every == 0 or n == self.total or n == 1):
            return
        el = time.perf_counter() - self.t0
        eta = el / n * (self.total - n) if n else 0.0
        pct = f"{n / self.total * 100:.0f}%" if self.total else "?"
        msg = (f"{self.label} {n}/{self.total} ({pct}) "
               f"已用 {el:.0f}s ETA {eta:.0f}s")
        if extra:
            msg += f" | {extra}"
        self.logger(msg)


def check_raw_data(conf_ids, baseline, ens_name, nt=72, n_peram_src=4,
                   verbose=True, logger=progress_log):
    """三类原始数据组态齐全度检查（test7/test8 泛化版）：

      eigensystem/{ens}/{conf_id}/          eigvecs_t{t:03d}_… × Nt
      perambulators/{ens}/light/{conf_id}/  perams.{cid}.{d}.{t}（d=0..3 × Nt）
      configurations/CLOVER/{ens}/          {ens}_cfg_{cid}.lime

    Args:
        conf_ids: 组态号列表。
        baseline: 数据源根目录。
        ens_name: 系综目录名（如 beta6.20_mu-0.2770_ms-0.2400_L24x72）。
        nt: 时间格点数（eigvecs/perams 数量基准）。
        n_peram_src: 传播子源数（perams.{cid}.{d}.{t} 的 d 范围）。
    Returns:
        (n_ok, bad_list)——bad_list 空才允许继续 makedata。
    """
    bad = []
    prog = ProgressLog(len(conf_ids), label="原始数据检查", every=10,
                       logger=logger)
    for cid in conf_ids:
        ed = os.path.join(baseline, 'eigensystem', ens_name, str(cid))
        if not os.path.isdir(ed):
            bad.append(f'conf{cid}: eigensystem 目录缺失 {ed}')
        else:
            n_eig = sum(1 for f in os.listdir(ed)
                        if f.startswith('eigvecs_t'))
            if n_eig < nt:
                bad.append(f'conf{cid}: eigvecs 不全 {n_eig}/{nt}')

        pd_ = os.path.join(baseline, 'perambulators', ens_name,
                           'light', str(cid))
        if not os.path.isdir(pd_):
            bad.append(f'conf{cid}: perambulators 目录缺失 {pd_}')
        else:
            n_perm = sum(1 for f in os.listdir(pd_)
                         if f.startswith(f'perams.{cid}.'))
            if n_perm < n_peram_src * nt:
                bad.append(f'conf{cid}: perams 不全 {n_perm}/'
                           f'{n_peram_src * nt}（需 d=0..{n_peram_src - 1}'
                           f' × t=0..{nt - 1}）')

        cf = os.path.join(baseline, 'configurations', 'CLOVER', ens_name,
                          f'{ens_name}_cfg_{cid}.lime')
        if not os.path.isfile(cf):
            bad.append(f'conf{cid}: gauge 配置缺失 {cf}')
        prog.step()
    n_ok = len(conf_ids) - len(bad)
    if verbose:
        logger(f"原始数据检查完成: 通过 {n_ok}/{len(conf_ids)}，"
               f"异常 {len(bad)}"
               + ("（全部通过 ✓）" if not bad else "（详见 bad_list）"))
    return n_ok, bad


def check_input_arrays(data_root, spec, verbose=True,
                       logger=progress_log):
    """输入数组校验：存在性 + 形状 + 有限性（test7 check_input_data 泛化版）。

    Args:
        data_root: 数据根目录（每组态子目录 data/conf{cid} 风格由 spec 决定）。
        spec: 校验清单 dict：
            {
              'conf_ids': [...],
              'layout': callable(cid) -> 目录（默认 data_root/conf{cid}）,
              'items': [
                  {'name': 'corr_pp_P0_{cid}', 'ext': '.npy',
                   'shape': (72,), 'dataset': None},     # npy/h5 自动回退
                  {'name': 'ops_mu0_nu1_dz24_{cid}', 'ext': '.npz',
                   'shape': (24, 72), 'dataset': 'ops'},
                  {'name': 'corr_pp_P200_{cid}', 'ext': 'any',
                   'shape': (72,)},                      # any=.h5|.npy|.npz
              ],
            }
    Returns:
        (n_ok, bad_list)——按组态计（任一 item 异常即该组态记 bad）。
    """
    from ..tools._io import load_tensor_h5

    conf_ids = spec['conf_ids']
    layout = spec.get('layout', lambda cid: os.path.join(data_root,
                                                         f'conf{cid}'))
    items = spec['items']

    def _read(path_no_ext, dataset):
        h5p = path_no_ext + '.h5'
        if os.path.exists(h5p):
            arr = load_tensor_h5(h5p, dataset=dataset or 'data')
            return arr.get() if hasattr(arr, 'get') else np.asarray(arr)
        p = path_no_ext + '.npy'
        if os.path.exists(p):
            return np.load(p)
        p = path_no_ext + '.npz'
        if os.path.exists(p):
            z = np.load(p)
            return z[dataset] if dataset else z[z.files[0]]
        raise FileNotFoundError(path_no_ext)

    bad = []
    prog = ProgressLog(len(conf_ids), label="输入检查", every=10,
                       logger=logger)
    for cid in conf_ids:
        d = layout(cid)
        if not os.path.isdir(d):
            bad.append(f'conf{cid}: 目录缺失 {d}')
            prog.step()
            continue
        for it in items:
            fname = it['name'].format(cid=cid)
            base = os.path.join(d, fname)
            ext = it.get('ext', 'any')
            try:
                if ext == 'any':
                    for e in ('.h5', '.npy', '.npz'):
                        if os.path.exists(base + e):
                            break
                    else:
                        raise FileNotFoundError(base)
                elif not os.path.exists(base + ext):
                    raise FileNotFoundError(base + ext)
                ds = it.get('dataset')
                if ext == '.npy':
                    arr = np.load(base + '.npy')
                elif ext == '.npz':
                    z = np.load(base + '.npz')
                    arr = z[ds] if ds else z[z.files[0]]
                elif ext == '.h5':
                    a = load_tensor_h5(base + '.h5', dataset=ds or 'data')
                    arr = a.get() if hasattr(a, 'get') else np.asarray(a)
                else:
                    arr = _read(base, ds)
                want = it.get('shape')
                ok_shape = want is None or tuple(arr.shape) == tuple(want)
                ok_fin = (np.isfinite(np.asarray(arr)).all()
                          if getattr(arr.dtype, 'kind', '') in 'fc' else True)
                if not (ok_shape and ok_fin):
                    bad.append(f'conf{cid}: {fname} shape={arr.shape}'
                               f"（需 {want}）有限={ok_fin}")
            except Exception as e:      # noqa: BLE001——校验层收集一切异常
                bad.append(f'conf{cid}: {fname} 异常 {e}')
        prog.step()
    n_ok = len(conf_ids) - len(bad)
    if verbose:
        logger(f"输入检查完成: 通过 {n_ok}/{len(conf_ids)} 条目级异常 "
               f"{len(bad)}")
        for b in bad[:20]:
            print(f"  [BAD] {b}", flush=True)
        if len(bad) > 20:
            print(f"  ... 其余 {len(bad) - 20} 条异常略", flush=True)
    return n_ok, bad


# ═══════════════════════════════════════════════════════════════════
# 模板组合式存在性+大小一致性守卫（整合 lqcddb io/write_date.py）
# ═══════════════════════════════════════════════════════════════════

def check_files_existence(path_templates, **kwargs):
    """检查占位符替换后所有模板文件的存在性与大小一致性
    （照抄 lqcddb io/write_date.check_files_existence）。

    以第一个全存在组合的各文件大小为基准，后续同种文件大小不一致者
    记为 corrupted（存储错误），与 missing 一并归入缺失返回。

    Args:
        path_templates: 含 '<name>' 占位符的路径模板列表，
            如 ['<exp>/<run>/file']。
        **kwargs: 占位符名 → 取值列表（求笛卡尔积）。
    Returns:
        (existing, bad)：existing 为正常组合列表（单占位符时直接存取值，
        多占位符时存 dict）；bad = missing + corrupted。
    """
    import itertools

    if not kwargs:
        raise ValueError("至少需要提供一个占位符参数，例如 run_id=[...]")

    placeholders = list(kwargs.keys())
    value_lists = [kwargs[p] for p in placeholders]

    existing, missing, corrupted = [], [], []

    def _resolve_paths(combo):
        if len(placeholders) == 1:
            mapping = {f"<{p}>": str(combo) for p in placeholders}
        else:
            mapping = {f"<{p}>": str(combo[p]) for p in placeholders}
        paths = []
        for template in path_templates:
            fp = template
            for tag, val in mapping.items():
                fp = fp.replace(tag, val)
            paths.append(fp)
        return paths

    def _make_combo(values):
        if len(placeholders) == 1:
            return values[0]
        return dict(zip(placeholders, values))

    reference_sizes = []
    for values in itertools.product(*value_lists):
        combo = _make_combo(values)
        paths = _resolve_paths(combo)

        if not all(os.path.exists(fp) for fp in paths):
            missing.append(combo)
            continue

        if not reference_sizes:
            reference_sizes = [os.path.getsize(fp) for fp in paths]
            existing.append(combo)
        else:
            if all(os.path.getsize(fp) == reference_sizes[i]
                   for i, fp in enumerate(paths)):
                existing.append(combo)
            else:
                corrupted.append(combo)

    print(f"文件正常且存在 (len={len(existing)}): {existing}")
    print(f"文件异常但存在 (len={len(corrupted)}): {corrupted}")
    print(f"文件不存在 (len={len(missing)}): {missing}")
    return existing, missing + corrupted
