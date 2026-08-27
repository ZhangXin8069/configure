#!/usr/bin/env bash

set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd -- "$(dirname -- "$SCRIPT_PATH")" && pwd -P)"
DEFAULT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
ROOT="$DEFAULT_ROOT"
ERRORS=0
WARNINGS=0
SKILL_COUNT=0
TOOL_SCRIPT_COUNT=0
HOOK_SCRIPT_COUNT=0
PLUGIN_MANIFEST_COUNT=0

usage() {
    cat <<'EOF'
用法：configure-check.sh [--root PATH] [--help]

只读检查 configure 仓库的 skills/tools/hooks/plugins 四棵目录树。
退出码：0=通过，1=发现问题，2=参数错误。
EOF
}

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    ERRORS=$((ERRORS + 1))
}

warn() {
    printf 'WARN: %s\n' "$*" >&2
    WARNINGS=$((WARNINGS + 1))
}

pass() {
    printf 'PASS: %s\n' "$*"
}

while (($# > 0)); do
    case "$1" in
        --help|-h)
            usage
            exit 0
            ;;
        --root)
            if (($# < 2)); then
                printf '缺少 --root 的路径参数。\n' >&2
                usage >&2
                exit 2
            fi
            ROOT="$2"
            shift 2
            ;;
        --root=*)
            ROOT="${1#*=}"
            if [[ -z "$ROOT" ]]; then
                printf -- '--root 不能是空路径。\n' >&2
                usage >&2
                exit 2
            fi
            shift
            ;;
        *)
            printf '未知参数：%s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ ! -d "$ROOT" ]]; then
    printf '根目录不存在或不是目录：%s\n' "$ROOT" >&2
    exit 2
fi
ROOT="$(cd -- "$ROOT" && pwd -P)"

printf '检查根目录：%s\n' "$ROOT"

for rel in skills tools hooks plugins; do
    if [[ -d "$ROOT/$rel" ]]; then
        pass "$rel/ 存在"
    else
        fail "$rel/ 缺失"
    fi
done

if [[ -d "$ROOT/skills" ]]; then
    while IFS= read -r -d '' skill_dir; do
        SKILL_COUNT=$((SKILL_COUNT + 1))
        skill_name="${skill_dir##*/}"
        skill_file="$skill_dir/SKILL.md"
        skill_agents="$skill_dir/AGENTS.md"

        if [[ ! -f "$skill_file" ]]; then
            fail "技能 $skill_name 缺少 SKILL.md"
            continue
        fi
        if [[ ! -f "$skill_agents" ]]; then
            fail "技能 $skill_name 缺少 AGENTS.md"
        fi

        first_line="$(sed -n '1p' "$skill_file")"
        frontmatter_end="$(awk 'NR > 1 && $0 == "---" { print NR; exit }' "$skill_file")"
        if [[ "$first_line" != "---" || -z "$frontmatter_end" ]]; then
            fail "技能 $skill_name 的 frontmatter 不完整"
        else
            frontmatter="$(sed -n "1,${frontmatter_end}p" "$skill_file")"
            if ! grep -Fqx "name: $skill_name" <<< "$frontmatter"; then
                fail "技能 $skill_name 的 frontmatter name 与目录不一致"
            fi
            if ! grep -Eq '^description:[[:space:]]*' <<< "$frontmatter"; then
                fail "技能 $skill_name 缺少 description"
            fi
            if ! grep -Eq '^metadata:[[:space:]]*$' <<< "$frontmatter" ||
                ! grep -Eq '^  openclaw:[[:space:]]*$' <<< "$frontmatter"; then
                fail "技能 $skill_name 缺少 metadata.openclaw"
            fi
        fi

        for heading in '执行前置' '核心原则' '触发时机' '工作流程' '错误处理' '注意事项'; do
            if ! grep -Fq "## $heading" "$skill_file"; then
                fail "技能 $skill_name 缺少章节：$heading"
            fi
        done
    done < <(find "$ROOT/skills" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)
    pass "技能目录检查完成：$SKILL_COUNT 个"
fi

check_shell_tree() {
    local tree="$1"
    local script_count=0
    local script_path
    local first_line

    [[ -d "$ROOT/$tree" ]] || return 0
    while IFS= read -r -d '' script_path; do
        script_count=$((script_count + 1))
        if [[ ! -x "$script_path" ]]; then
            fail "$tree 脚本不可执行：${script_path#"$ROOT/"}"
        fi
        if ! IFS= read -r first_line < "$script_path" || [[ "$first_line" != '#!'* ]]; then
            fail "$tree 脚本缺少 shebang：${script_path#"$ROOT/"}"
        fi
        if ! bash -n "$script_path"; then
            fail "$tree 脚本语法错误：${script_path#"$ROOT/"}"
        fi
    done < <(
        find "$ROOT/$tree" -type f \( -name '*.sh' -o -name 'pre-commit' -o -name 'pre-push' \) -print0 |
            sort -z
    )

    if [[ "$tree" == tools ]]; then
        TOOL_SCRIPT_COUNT=$script_count
    else
        HOOK_SCRIPT_COUNT=$script_count
    fi
    pass "$tree 脚本检查完成：$script_count 个"
}

check_shell_tree tools
check_shell_tree hooks

if [[ -d "$ROOT/plugins" ]]; then
    while IFS= read -r -d '' manifest; do
        PLUGIN_MANIFEST_COUNT=$((PLUGIN_MANIFEST_COUNT + 1))
        plugin_root="$(dirname -- "$(dirname -- "$manifest")")"
        plugin_name="$(basename -- "$plugin_root")"
        if ! python3 - "$manifest" "$plugin_name" "$plugin_root" <<'PY'
import json
import pathlib
import sys

manifest_path = pathlib.Path(sys.argv[1])
expected_name = sys.argv[2]
plugin_root = pathlib.Path(sys.argv[3])

try:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    print(f"manifest JSON 无法解析: {manifest_path}: {exc}")
    raise SystemExit(1)

errors = []
if not isinstance(data, dict):
    errors.append("顶层必须是 JSON 对象")
if isinstance(data, dict):
    if data.get("name") != expected_name:
        errors.append(f"name 应为 {expected_name!r}，实际为 {data.get('name')!r}")
    if not isinstance(data.get("version"), str) or not data["version"]:
        errors.append("version 必须是非空字符串")

    for key in ("skills", "agents", "commands", "scripts", "assets"):
        value = data.get(key)
        if value is None:
            continue
        paths = [value] if isinstance(value, str) else value
        if not isinstance(paths, list) or not all(isinstance(item, str) for item in paths):
            errors.append(f"{key} 必须是字符串或字符串数组")
            continue
        for relative in paths:
            candidate = pathlib.PurePosixPath(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                errors.append(f"{key} 含越界路径: {relative!r}")
            elif not (plugin_root / pathlib.Path(relative)).exists():
                errors.append(f"{key} 引用不存在: {relative!r}")

if errors:
    for error in errors:
        print(f"manifest {manifest_path}: {error}")
    raise SystemExit(1)
PY
        then
            fail "插件 manifest 检查失败：${manifest#"$ROOT/"}"
        fi
    done < <(find "$ROOT/plugins" -type f -path '*/.codex-plugin/plugin.json' -print0 | sort -z)
    if ((PLUGIN_MANIFEST_COUNT == 0)); then
        warn 'plugins/ 当前没有可直接加载的 .codex-plugin/plugin.json；推荐索引不会被当作插件加载'
    else
        pass "插件 manifest 检查完成：$PLUGIN_MANIFEST_COUNT 个"
    fi
fi

printf '摘要：skills=%d，tools-shell=%d，hooks-shell=%d，plugin-manifests=%d，warnings=%d，errors=%d\n' \
    "$SKILL_COUNT" "$TOOL_SCRIPT_COUNT" "$HOOK_SCRIPT_COUNT" "$PLUGIN_MANIFEST_COUNT" "$WARNINGS" "$ERRORS"

if ((ERRORS > 0)); then
    exit 1
fi
exit 0
