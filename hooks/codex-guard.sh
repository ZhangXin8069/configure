#!/usr/bin/env bash
# Guard paths supplied by a before-edit/before-tool adapter.

set -Eeuo pipefail

usage() {
    cat <<'USAGE'
用法：codex-guard.sh [--] <路径...>

路径可用相对当前目录的形式传入；不传参数时从 stdin 读取逐行路径，
也接受含 path/paths/file/files 字段的 JSON payload。
仅允许仓库内路径；拒绝仓库根目录、.git/、隐藏技能会话日志和仓库外路径。
USAGE
}

if [[ "${1:-}" == '-h' || "${1:-}" == '--help' ]]; then
    usage
    exit 0
fi
if [[ "${1:-}" == '--' ]]; then
    shift
fi

command -v git >/dev/null 2>&1 || {
    printf 'codex-guard: 未找到 git\n' >&2
    exit 2
}
command -v realpath >/dev/null 2>&1 || {
    printf 'codex-guard: 未找到 realpath\n' >&2
    exit 2
}

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || {
    printf 'codex-guard: 当前目录不在 Git 仓库中\n' >&2
    exit 1
}
repo_root=$(cd -- "$repo_root" && pwd -P)
caller_dir=$PWD

declare -a paths=()
if (( $# > 0 )); then
    paths+=("$@")
elif [[ ! -t 0 ]]; then
    input=$(< /dev/stdin)
    if [[ "$input" == \{* || "$input" == \[* ]]; then
        command -v python3 >/dev/null 2>&1 || {
            printf 'codex-guard: 解析 JSON payload 需要 python3\n' >&2
            exit 2
        }
        if ! json_paths=$(python3 - "$input" <<'PY'
import json
import sys

try:
    payload = json.loads(sys.argv[1])
except (TypeError, ValueError) as exc:
    print(f"JSON payload 无效：{exc}", file=sys.stderr)
    raise SystemExit(1)

paths = []

def collect(value):
    if isinstance(value, str) and value:
        paths.append(value)
    elif isinstance(value, list):
        for item in value:
            collect(item)
    elif isinstance(value, dict):
        for key in ("path", "paths", "file", "files"):
            if key in value:
                collect(value[key])
        for key in ("arguments", "input", "params"):
            if key in value:
                collect(value[key])

collect(payload)
if not paths:
    print("JSON payload 未包含可识别路径字段", file=sys.stderr)
    raise SystemExit(1)

for path in paths:
    print(path)
PY
        ); then
            printf 'codex-guard: JSON payload 未能提取路径\n' >&2
            exit 1
        fi
        while IFS= read -r path; do
            paths+=("$path")
        done <<< "$json_paths"
    else
        while IFS= read -r path; do
            paths+=("$path")
        done <<< "$input"
    fi
fi

if (( ${#paths[@]} == 0 )); then
    printf 'codex-guard: 未收到路径，跳过\n'
    exit 0
fi

failures=0
checked=0
for raw_path in "${paths[@]}"; do
    [[ -n "$raw_path" ]] || continue

    if [[ "$raw_path" == \{* || "$raw_path" == \[* ]]; then
        printf '✗ 不接受 JSON payload，请传入逐行路径：%s\n' "$raw_path" >&2
        failures=$((failures + 1))
        continue
    fi

    if [[ "$raw_path" == /* ]]; then
        candidate=$raw_path
    else
        candidate=$caller_dir/$raw_path
    fi
    if ! canonical=$(realpath -m -- "$candidate"); then
        printf '✗ 无法规范化路径：%s\n' "$raw_path" >&2
        failures=$((failures + 1))
        continue
    fi

    case "$canonical" in
        "$repo_root")
            printf '✗ 禁止直接操作仓库根目录：%s\n' "$raw_path" >&2
            failures=$((failures + 1))
            continue
            ;;
        "$repo_root"/*)
            relative=${canonical#"$repo_root"/}
            ;;
        *)
            printf '✗ 路径在仓库外：%s\n' "$raw_path" >&2
            failures=$((failures + 1))
            continue
            ;;
    esac

    base=${relative##*/}
    case "$relative" in
        .git|.git/*|*/.git|*/.git/*)
            printf '✗ 禁止触及 Git 元数据：%s\n' "$raw_path" >&2
            failures=$((failures + 1))
            continue
            ;;
    esac
    case "$base" in
        .agent.*.log|.*.*.log)
            printf '✗ 禁止写入技能会话日志：%s\n' "$raw_path" >&2
            failures=$((failures + 1))
            continue
            ;;
    esac

    printf '✓ before-edit allow: %s\n' "$relative"
    checked=$((checked + 1))
done

if (( failures > 0 )); then
    printf '✗ codex-guard: %d 个路径被拒绝，%d 个路径通过\n' "$failures" "$checked" >&2
    exit 1
fi

printf '✓ codex-guard: %d 个路径通过\n' "$checked"
