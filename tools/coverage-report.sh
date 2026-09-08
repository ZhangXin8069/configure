#!/usr/bin/env bash

set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd -- "$(dirname -- "$SCRIPT_PATH")" && pwd -P)"
DEFAULT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
ROOT="$DEFAULT_ROOT"

declare -a TEMP_FILES=()
declare -a GAP_LINES=()

cleanup_temp_files() {
    if ((${#TEMP_FILES[@]} > 0)); then
        rm -f -- "${TEMP_FILES[@]}"
    fi
}
trap cleanup_temp_files EXIT

usage() {
    cat <<'EOF'
用法：coverage-report.sh [--root PATH] [--help]

只读汇总 skills/tools/hooks/plugins 四树覆盖状况、skills/.opencode/skills 镜像线索和缺口提示。
EOF
}

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 2
}

add_gap() {
    GAP_LINES+=("$*")
}

new_temp_file() {
    local temp_file
    temp_file=$(mktemp "${TMPDIR:-/tmp}/coverage-report.XXXXXX")
    TEMP_FILES+=("$temp_file")
    printf '%s' "$temp_file"
}

collect_find_output() {
    local output=$1
    shift
    find "$@" -print0 | sort -z > "$output"
}

collect_find_lines() {
    local output=$1
    shift
    find "$@" -print | sort > "$output"
}

count_lines() {
    local input=$1
    if [[ ! -s "$input" ]]; then
        printf '0'
        return
    fi
    wc -l < "$input" | tr -d ' '
}

strip_prefix_lines() {
    local input=$1
    local prefix=$2
    local output=$3
    local line
    : > "$output"
    while IFS= read -r line; do
        printf '%s\n' "${line#"$prefix"}"
    done < "$input" > "$output"
}

join_count() {
    local value=$1
    local total=$2
    if [[ "$total" -eq 0 ]]; then
        printf '0'
        return
    fi
    printf '%s/%s' "$value" "$total"
}

report_skills_tree() {
    local tree_dir="$ROOT/skills"
    local registry="$tree_dir/AGENTS.md"
    local dir_list
    local skill_dir
    local skill_name
    local skill_file
    local skill_agents
    local skill_total=0
    local skill_md_ok=0
    local skill_agents_ok=0
    local skill_name_ok=0
    local skill_registered_ok=0
    local skill_frontmatter_ok=0
    local skill_sections_ok=0
    local registry_entries=0
    local first_line
    local frontmatter_end
    local frontmatter
    local -a missing_sections=()

    if [[ ! -d "$tree_dir" ]]; then
        printf 'skills: 缺失\n'
        add_gap 'skills/ 缺失'
        return
    fi

    if [[ -f "$registry" ]]; then
        registry_entries=$(awk -F'`' '/^\| `[^`]+` \|/ { print $2 }' "$registry" | sort -u | wc -l | tr -d ' ')
    else
        add_gap 'skills/AGENTS.md 缺失'
    fi

    dir_list=$(new_temp_file)
    collect_find_output "$dir_list" "$tree_dir" -mindepth 1 -maxdepth 1 -type d
    while IFS= read -r -d '' skill_dir; do
        skill_total=$((skill_total + 1))
        skill_name="${skill_dir##*/}"
        skill_file="$skill_dir/SKILL.md"
        skill_agents="$skill_dir/AGENTS.md"
        missing_sections=

        if [[ -f "$skill_file" ]]; then
            skill_md_ok=$((skill_md_ok + 1))
        else
            add_gap "skills/$skill_name 缺少 SKILL.md"
            continue
        fi

        if [[ -f "$skill_agents" ]]; then
            skill_agents_ok=$((skill_agents_ok + 1))
        else
            add_gap "skills/$skill_name 缺少 AGENTS.md"
        fi

        if [[ "$skill_name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
            skill_name_ok=$((skill_name_ok + 1))
        else
            add_gap "skills/$skill_name 目录名不符合小写连字符约定"
        fi

        if [[ -f "$registry" ]] && grep -Fq "| \`$skill_name\` |" "$registry"; then
            skill_registered_ok=$((skill_registered_ok + 1))
        else
            [[ -f "$registry" ]] && add_gap "skills/$skill_name 未登记到 skills/AGENTS.md"
        fi

        first_line="$(sed -n '1p' "$skill_file")"
        frontmatter_end="$(awk 'NR > 1 && $0 == "---" { print NR; exit }' "$skill_file")"
        if [[ "$first_line" == '---' && -n "$frontmatter_end" ]]; then
            frontmatter="$(sed -n "1,${frontmatter_end}p" "$skill_file")"
            if grep -Fqx "name: $skill_name" <<< "$frontmatter" &&
                grep -Eq '^description:[[:space:]]*' <<< "$frontmatter" &&
                grep -Eq '当用户|Use when' <<< "$frontmatter" &&
                grep -Eq '^metadata:[[:space:]]*$' <<< "$frontmatter" &&
                grep -Eq '^  openclaw:[[:space:]]*$' <<< "$frontmatter"; then
                skill_frontmatter_ok=$((skill_frontmatter_ok + 1))
            else
                add_gap "skills/$skill_name 的 frontmatter 不完整或与目录不一致"
            fi
        else
            add_gap "skills/$skill_name 的 frontmatter 不完整"
        fi

        missing_sections=()
        for heading in '执行前置' '核心原则' 'Git 检查' '触发时机' '工作流程' '错误处理' '注意事项'; do
            if ! grep -Fq "## $heading" "$skill_file"; then
                missing_sections+=("$heading")
            fi
        done
        if ((${#missing_sections[@]} == 0)); then
            skill_sections_ok=$((skill_sections_ok + 1))
        else
            add_gap "skills/$skill_name 缺少章节：${missing_sections[*]}"
        fi
    done < "$dir_list"

    printf 'skills: 目录=%d，name=%s，SKILL.md=%s，AGENTS.md=%s，登记=%s，frontmatter=%s，章节=%s\n' \
        "$skill_total" \
        "$(join_count "$skill_name_ok" "$skill_total")" \
        "$(join_count "$skill_md_ok" "$skill_total")" \
        "$(join_count "$skill_agents_ok" "$skill_total")" \
        "$(join_count "$skill_registered_ok" "$skill_total")" \
        "$(join_count "$skill_frontmatter_ok" "$skill_total")" \
        "$(join_count "$skill_sections_ok" "$skill_total")"
    if [[ -f "$registry" ]]; then
        printf 'skills/AGENTS.md 条目=%s\n' "$registry_entries"
    fi
}

report_shell_tree() {
    local tree_name=$1
    local tree_dir="$ROOT/$tree_name"
    local list_file
    local script_path
    local rel_path
    local script_total=0
    local executable_ok=0
    local shebang_ok=0
    local syntax_ok=0
    local first_line

    if [[ ! -d "$tree_dir" ]]; then
        printf '%s: 缺失\n' "$tree_name"
        add_gap "$tree_name/ 缺失"
        return
    fi

    list_file=$(new_temp_file)
    collect_find_output "$list_file" "$tree_dir" -type f \( -name '*.sh' -o -name 'pre-commit' -o -name 'pre-push' \)
    while IFS= read -r -d '' script_path; do
        script_total=$((script_total + 1))
        rel_path="${script_path#"$ROOT/"}"
        if [[ -x "$script_path" ]]; then
            executable_ok=$((executable_ok + 1))
        else
            add_gap "$rel_path 不可执行"
        fi

        if IFS= read -r first_line < "$script_path" && [[ "$first_line" == '#!'* ]]; then
            shebang_ok=$((shebang_ok + 1))
        else
            add_gap "$rel_path 缺少 shebang"
        fi

        if bash -n "$script_path"; then
            syntax_ok=$((syntax_ok + 1))
        else
            add_gap "$rel_path 语法错误"
        fi
    done < "$list_file"

    printf '%s: 脚本=%d，可执行=%s，shebang=%s，bash-n=%s\n' \
        "$tree_name" \
        "$script_total" \
        "$(join_count "$executable_ok" "$script_total")" \
        "$(join_count "$shebang_ok" "$script_total")" \
        "$(join_count "$syntax_ok" "$script_total")"
}

report_plugins_tree() {
    local tree_dir="$ROOT/plugins"
    local manifest_list
    local manifest_errors
    local manifest_path
    local plugin_root
    local plugin_name
    local manifest_total=0
    local manifest_ok=0

    if [[ ! -d "$tree_dir" ]]; then
        printf 'plugins: 缺失\n'
        add_gap 'plugins/ 缺失'
        return
    fi

    manifest_list=$(new_temp_file)
    collect_find_output "$manifest_list" "$tree_dir" -type f -path '*/.codex-plugin/plugin.json'
    while IFS= read -r -d '' manifest_path; do
        manifest_total=$((manifest_total + 1))
        plugin_root="$(dirname -- "$(dirname -- "$manifest_path")")"
        plugin_name="$(basename -- "$plugin_root")"
        manifest_errors=$(new_temp_file)
        if python3 - "$manifest_path" "$plugin_name" "$plugin_root" <<'PY' 2> "$manifest_errors"
import json
import pathlib
import sys

manifest_path = pathlib.Path(sys.argv[1])
expected_name = sys.argv[2]
plugin_root = pathlib.Path(sys.argv[3])

try:
    plugin_root = plugin_root.resolve(strict=True)
except (OSError, RuntimeError) as exc:
    print(f"插件根目录无法解析: {plugin_root}: {exc}")
    raise SystemExit(1)

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
                continue
            resolved = plugin_root / pathlib.Path(relative)
            try:
                resolved = resolved.resolve(strict=True)
            except (OSError, RuntimeError):
                errors.append(f"{key} 引用不存在或无法解析: {relative!r}")
                continue
            if resolved != plugin_root and plugin_root not in resolved.parents:
                errors.append(f"{key} 含越界路径: {relative!r}")

if errors:
    for error in errors:
        print(f"manifest {manifest_path}: {error}")
    raise SystemExit(1)
PY
        then
            manifest_ok=$((manifest_ok + 1))
        else
            add_gap "plugins/${manifest_path#"$ROOT/"} 检查失败"
            while IFS= read -r line; do
                [[ -n "$line" ]] && add_gap "  $line"
            done < "$manifest_errors"
        fi
    done < "$manifest_list"

    printf 'plugins: manifest=%s，valid=%s\n' \
        "$(join_count "$manifest_total" "$manifest_total")" \
        "$(join_count "$manifest_ok" "$manifest_total")"
    if ((manifest_total == 0)); then
        add_gap 'plugins/ 当前没有可直接加载的 .codex-plugin/plugin.json'
    fi
}

report_skill_mirror() {
    local source_dir="$ROOT/skills"
    local mirror_dir="$ROOT/.opencode/skills"
    local source_abs
    local mirror_abs
    local source_rel
    local mirror_rel
    local common_rel
    local missing_rel
    local extra_rel
    local diff_count=0
    local rel

    if [[ ! -d "$source_dir" || ! -d "$mirror_dir" ]]; then
        printf '镜像一致性线索：skills=%s，.opencode/skills=%s\n' \
            "$([[ -d "$source_dir" ]] && printf 存在 || printf 缺失)" \
            "$([[ -d "$mirror_dir" ]] && printf 存在 || printf 缺失)"
        [[ ! -d "$source_dir" ]] && add_gap 'skills/ 缺失，无法检查镜像'
        [[ ! -d "$mirror_dir" ]] && add_gap '.opencode/skills 缺失，无法检查镜像'
        return
    fi

    source_abs=$(new_temp_file)
    mirror_abs=$(new_temp_file)
    source_rel=$(new_temp_file)
    mirror_rel=$(new_temp_file)
    common_rel=$(new_temp_file)
    missing_rel=$(new_temp_file)
    extra_rel=$(new_temp_file)
    collect_find_lines "$source_abs" "$source_dir" -type f
    collect_find_lines "$mirror_abs" "$mirror_dir" -type f
    strip_prefix_lines "$source_abs" "$source_dir/" "$source_rel"
    strip_prefix_lines "$mirror_abs" "$mirror_dir/" "$mirror_rel"
    comm -12 "$source_rel" "$mirror_rel" > "$common_rel"
    comm -23 "$source_rel" "$mirror_rel" > "$missing_rel"
    comm -13 "$source_rel" "$mirror_rel" > "$extra_rel"

    while IFS= read -r rel; do
        [[ -n "$rel" ]] || continue
        if ! cmp -s -- "$source_dir/$rel" "$mirror_dir/$rel"; then
            diff_count=$((diff_count + 1))
            add_gap "skills 镜像内容不一致：$rel"
        fi
    done < "$common_rel"

    while IFS= read -r rel; do
        [[ -n "$rel" ]] || continue
        add_gap "skills 镜像缺少文件：$rel"
    done < "$missing_rel"

    while IFS= read -r rel; do
        [[ -n "$rel" ]] || continue
        add_gap "skills 镜像多余文件：$rel"
    done < "$extra_rel"

    printf '镜像一致性线索：source=%s，mirror=%s，missing=%s，extra=%s，diff=%s\n' \
        "$(count_lines "$source_rel")" \
        "$(count_lines "$mirror_rel")" \
        "$(count_lines "$missing_rel")" \
        "$(count_lines "$extra_rel")" \
        "$diff_count"
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

printf '覆盖报告：%s\n' "$ROOT"
printf '边界：configure-check.sh 负责门禁；coverage-report.sh 只给线索，不改仓库。\n\n'
printf '四树覆盖摘要\n'
report_skills_tree
report_shell_tree tools
report_shell_tree hooks
report_plugins_tree
printf '\n镜像一致性线索\n'
report_skill_mirror

printf '\n缺口提示\n'
if ((${#GAP_LINES[@]} == 0)); then
    printf '  - 未发现明显缺口。\n'
else
    for gap in "${GAP_LINES[@]}"; do
        printf '  - %s\n' "$gap"
    done
fi
