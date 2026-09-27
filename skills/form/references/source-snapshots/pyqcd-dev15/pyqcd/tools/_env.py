"""运行环境快照（整合蒸馏回归入口的 dump_env 约定）。

记录时间/主机/Python/关键包版本/xelatex/git 状态/GPU 信息/命令行，
供长跑产物自证可复现环境。纯标准库 + 可选探测，任何缺失项记 None/'n/a'。
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime


def dump_env(path, root=None, extra_packages=('numpy', 'scipy',
                                               'matplotlib', 'cupy',
                                               'lsqfit', 'gvar')):
    """写环境快照 JSON 并返回 info dict（照抄 test0/main.py dump_env）。

    Args:
        path: 输出 JSON 路径（目录不存在则创建）。
        root: git 仓库根（None 时用当前工作目录）。
        extra_packages: 额外探测版本的包名列表。
    Returns:
        info dict。
    """
    root = root or os.getcwd()
    git_branch = git_head = 'n/a'
    try:
        git_branch = subprocess.run(
            ['git', '-C', root, 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True, text=True).stdout.strip() or 'n/a'
        git_head = subprocess.run(
            ['git', '-C', root, 'log', '-1', '--oneline'],
            capture_output=True, text=True).stdout.strip() or 'n/a'
    except Exception:
        pass

    import importlib

    def _ver(m):
        try:
            return importlib.import_module(m).__version__
        except Exception:
            return None

    info = {
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'hostname': platform.node(),
        'python': platform.python_version(),
        **{m: _ver(m) for m in extra_packages},
        'xelatex': shutil.which('xelatex'),
        'git_branch': git_branch,
        'git_head': git_head,
        'cmdline': ' '.join(sys.argv),
    }
    try:
        out = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.total',
             '--format=csv,noheader'], capture_output=True, text=True)
        info['gpu'] = out.stdout.strip() if out.returncode == 0 else 'n/a'
    except Exception:
        info['gpu'] = 'n/a'

    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(info, f, indent=2)
    return info
