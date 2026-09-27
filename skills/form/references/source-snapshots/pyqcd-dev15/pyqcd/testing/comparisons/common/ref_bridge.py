"""参考库加载桥：lqcddb 直接导入；donghx 脚本 AST 提取函数（剔除顶层驱动 IO）。"""
import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LQCDBB_SRC = ROOT / 'refer' / 'sush' / 'lqcddb' / 'src'
DONGHX_DIR = ROOT / 'refer' / 'donghx'

os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')


def load_lqcddb():
    source = os.fspath(LQCDBB_SRC)
    if source not in sys.path:
        sys.path.insert(0, source)
    import lqcddb
    return lqcddb


def load_donghx(filename, func_names=None):
    path = DONGHX_DIR / filename
    tree = ast.parse(open(path).read())
    def has_io(node):
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                f = n.func
                name = getattr(f, 'id', None) or getattr(f, 'attr', '') or ''
                if name in {'open', 'fromfile', 'savez', 'savetxt', 'print',
                            'input', 'exists', 'system', 'makedirs',
                            'getsize'}:
                    return True
            if isinstance(n, ast.Attribute) and n.attr == 'argv':
                return True
        return False

    SAFE = {'range', 'len', 'set', 'list', 'enumerate', 'zip', 'float',
            'int', 'abs', 'sorted', 'min', 'max', 'sum', 'dict', 'tuple',
            'print'}

    def is_pure(node):
        # 允许安全内建调用（表构建循环）；排除 IO/argv/未知函数调用
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                f = n.func
                name = getattr(f, 'id', None) or getattr(f, 'attr', '') or ''
                if name not in SAFE:
                    return False
            elif isinstance(n, ast.Attribute) and n.attr == 'argv':
                return False
        return True

    body = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef,
                             ast.ClassDef)):
            body.append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            if not has_io(node):
                body.append(node)
        elif isinstance(node, ast.For) and is_pure(node):
            body.append(node)
    mod = ast.Module(body=body, type_ignores=[])
    ns = {'__name__': 'donghx_' + filename.replace('.py', '').replace('.', '_')}
    source = os.fspath(DONGHX_DIR)
    if source not in sys.path:
        sys.path.insert(0, source)
    exec(compile(mod, os.fspath(path), 'exec'), ns)
    if func_names is not None:
        missing = [k for k in func_names if k not in ns]
        if missing:
            raise KeyError(f'{filename} 缺函数: {missing}')
        return {k: ns[k] for k in func_names}
    return ns
