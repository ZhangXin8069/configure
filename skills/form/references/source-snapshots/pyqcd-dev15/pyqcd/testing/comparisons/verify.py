"""对照套件断言门：校验最近一次 results.json 的通过率与关键项。

用法：python -m pyqcd.testing.comparisons.verify [results.json]
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# 允许非 pass 的白名单（结构性/统计性/登记差异项）
WHITELIST_STRUCTURAL = {'L17', 'L20', 'L22b', 'L28', 'L30', 'D08',
                        'S10'}
# 数值分歧已登记 MAPPING.md optim/backlog 的项（不要求 note 字段）
WHITELIST_REGISTERED = {'D04'}
# 数值分歧已登记 optim/backlog 的项：要求 status=diff 且已附 note
WHITELIST_DIFF_NOTE = {'L25'}


def _is_comparison_results(value):
    """识别主对照套件结果，排除单项 runner 的 JSON。"""
    return (isinstance(value, list) and
            all(isinstance(item, dict) and 'id' in item and 'status' in item
                for item in value))


def _default_results_path():
    """选择最近完整的主套件结果，避免被单项证据目录遮蔽。"""
    paths = sorted(glob.glob(os.path.join(
        HERE, 'artifacts', 'run_*', 'results.json')))
    valid = []
    for path in paths:
        try:
            with open(path) as stream:
                value = json.load(stream)
        except (OSError, ValueError, TypeError):
            continue
        if _is_comparison_results(value):
            valid.append((path, len(value)))
    if not valid:
        raise FileNotFoundError(
            f'未找到主套件结果: {HERE}/artifacts/run_*/results.json')
    complete = [item for item in valid if item[1] >= 40]
    return (complete or valid)[-1][0]


def main():
    parser = argparse.ArgumentParser(description='对照套件断言门')
    parser.add_argument('results', nargs='?', help='results.json 路径')
    args = parser.parse_args()
    path = args.results or _default_results_path()
    with open(path) as stream:
        results = json.load(stream)
    if not _is_comparison_results(results):
        raise SystemExit(f'结果文件不是主套件列表: {path}')
    fails = []
    for r in results:
        st, cid = r['status'], r['id']
        if st == 'pass':
            continue
        if st == 'diff' and cid in WHITELIST_STRUCTURAL:
            continue
        if st == 'diff' and cid in WHITELIST_DIFF_NOTE and r.get('note'):
            continue
        if st == 'diff' and cid in WHITELIST_REGISTERED:
            continue
        fails.append(f"{cid} {st} {r.get('diff', '')}")
    n_pass = sum(1 for r in results if r['status'] == 'pass')
    print(f"results: {path}")
    print(f"pass={n_pass}/{len(results)} whitelist_ok="
          f"{len(results) - n_pass - len(fails)} hard_fails={len(fails)}")
    for f_ in fails:
        print('  HARD-FAIL:', f_)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
