#!/usr/bin/env bash
# Validate the files that a Git hook is about to accept.
#
# The checker reads blobs from the index instead of sourcing or executing them.
# This keeps validation independent from the working tree and avoids running
# untrusted repository code during a commit or push.

set -Eeuo pipefail

readonly script_name=${0##*/}

usage() {
    cat <<'USAGE'
用法：check.sh [--staged|--tracked]

  --staged   检查暂存区中新增或修改的 hooks/skills/tools/plugins 文件（默认）
  --tracked  检查 hooks/skills/tools/plugins 下索引中的全部受跟踪文件
  -h, --help 显示帮助
USAGE
}

die() {
    printf '%s: %s\n' "$script_name" "$*" >&2
    exit 2
}

mode=staged
case "${1:-}" in
    '') ;;
    --staged) mode=staged ;;
    --tracked) mode=tracked ;;
    -h|--help)
        usage
        exit 0
        ;;
    *)
        usage >&2
        die "未知选项：$1"
        ;;
esac

command -v git >/dev/null 2>&1 || die "未找到 git"
repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || die "当前目录不在 Git 仓库中"
cd -- "$repo_root"

declare -a paths=()

if [[ "$mode" == staged ]]; then
    # --diff-filter excludes deletions: there is no blob to syntax-check.
    while IFS= read -r -d '' path; do
        paths+=("$path")
    done < <(git diff --cached --name-only --diff-filter=ACMR -z -- hooks skills tools plugins)
else
    while IFS= read -r -d '' path; do
        paths+=("$path")
    done < <(git ls-files -z -- hooks skills tools plugins)
fi

failures=0
shell_count=0
python_count=0
json_count=0
skill_count=0
log_count=0

index_mode() {
    local path=$1
    local entry

    if ! IFS= read -r -d '' entry < <(git ls-files --stage -z -- "$path"); then
        return 1
    fi
    printf '%s\n' "${entry%% *}"
}

validate_shell_mode() {
    local path=$1
    local mode

    if ! mode=$(index_mode "$path"); then
        printf '✗ %s：无法读取索引权限\n' "$path" >&2
        failures=$((failures + 1))
        return
    fi
    if [[ "$mode" != 100755 ]]; then
        printf '✗ %s：Shell 入口索引权限应为 100755，实际为 %s\n' "$path" "$mode" >&2
        failures=$((failures + 1))
    fi
}

if [[ "$mode" == staged ]]; then
    if ! diff_output=$(git diff --cached --check -- hooks skills tools plugins 2>&1); then
        printf '✗ 暂存区存在空白或冲突标记问题：\n%s\n' "$diff_output" >&2
        failures=$((failures + 1))
    fi
fi

staged_blob_first_line() {
    local path=$1
    git show --no-ext-diff --format= ":$path" | sed -n '1p'
}

python_interpreter() {
    local path=$1
    local first_line

    case "$path" in
        *.py) printf 'python3\n'; return 0 ;;
    esac
    first_line=$(staged_blob_first_line "$path") || return 1
    if [[ "$first_line" =~ (^|[[:space:]/])python3?([[:space:]]|$) ]]; then
        printf 'python3\n'
    fi
    return 0
}

validate_python() {
    local path=$1
    local output
    if ! command -v python3 >/dev/null 2>&1; then
        printf '✗ %s：缺少 Python 语法检查器 python3\n' "$path" >&2
        failures=$((failures + 1))
        return
    fi
    if ! output=$(git show --no-ext-diff --format= ":$path" | python3 -c \
        'import ast, sys; ast.parse(sys.stdin.read())' 2>&1); then
        printf '✗ %s：Python AST 解析失败\n%s\n' "$path" "$output" >&2
        failures=$((failures + 1))
        return
    fi
    python_count=$((python_count + 1))
}

validate_json() {
    local path=$1
    local output
    if ! command -v python3 >/dev/null 2>&1; then
        printf '✗ %s：缺少 JSON 检查器 python3\n' "$path" >&2
        failures=$((failures + 1))
        return
    fi
    if ! output=$(git show --no-ext-diff --format= ":$path" | python3 -c \
        'import json, sys; json.load(sys.stdin)' 2>&1); then
        printf '✗ %s：JSON 解析失败\n%s\n' "$path" "$output" >&2
        failures=$((failures + 1))
        return
    fi
    json_count=$((json_count + 1))
}

shell_interpreter() {
    local path=$1
    local first_line

    case "$path" in
        *.zsh|.zshrc|.zprofile|.zlogin|.zlogout)
            printf 'zsh\n'
            return 0
            ;;
        *.sh|*.bash|.bashrc|.bash_profile|.profile)
            printf 'bash\n'
            return 0
            ;;
    esac

    first_line=$(staged_blob_first_line "$path") || return 1
    if [[ "$first_line" =~ (^|[[:space:]/])zsh([[:space:]]|$) ]]; then
        printf 'zsh\n'
    elif [[ "$first_line" =~ (^|[[:space:]/])bash([[:space:]]|$) ||
        "$first_line" =~ (^|[[:space:]/])sh([[:space:]]|$) ]]; then
        printf 'bash\n'
    fi
    return 0
}

validate_shell() {
    local path=$1
    local interpreter=$2
    local output

    if ! command -v "$interpreter" >/dev/null 2>&1; then
        printf '✗ %s：缺少语法检查器 %s\n' "$path" "$interpreter" >&2
        failures=$((failures + 1))
        return
    fi

    if ! output=$(git show --no-ext-diff --format= ":$path" |
        "$interpreter" -n 2>&1); then
        printf '✗ %s：%s -n 失败\n%s\n' "$path" "$interpreter" "$output" >&2
        failures=$((failures + 1))
        return
    fi

    shell_count=$((shell_count + 1))
}

validate_skill_manifest() {
    local path=$1
    local expected=${path#skills/}
    expected=${expected%/SKILL.md}
    local output

    if ! output=$(git show --no-ext-diff --format= ":$path" |
        awk -v expected="$expected" '
            NR == 1 { first = $0; next }
            !closed && $0 == "---" { closed = 1; next }
            !closed && $0 ~ /^name:[[:space:]]*/ {
                name = $0
                sub(/^name:[[:space:]]*/, "", name)
                sub(/[[:space:]]+$/, "", name)
            }
            !closed && $0 ~ /^description:[[:space:]]*/ { description = 1 }
            !closed && $0 ~ /^metadata:[[:space:]]*$/ { metadata = 1 }
            !closed && $0 ~ /^  openclaw:[[:space:]]*$/ { openclaw = 1 }
            !closed && $0 ~ /^    emoji:[[:space:]]*/ { emoji = 1 }
            END {
                ok = 1
                if (first != "---") {
                    print "frontmatter 必须以 --- 开始"
                    ok = 0
                }
                if (!closed) {
                    print "frontmatter 缺少结束的 ---"
                    ok = 0
                }
                if (name != expected) {
                    print "name 与目录不一致：期望 " expected "，实际 " name
                    ok = 0
                }
                if (!description) {
                    print "frontmatter 缺少 description"
                    ok = 0
                }
                if (!metadata || !openclaw || !emoji) {
                    print "frontmatter 缺少 metadata.openclaw.emoji"
                    ok = 0
                }
                exit(ok ? 0 : 1)
            }
        ' 2>&1); then
        printf '✗ %s：SKILL.md frontmatter 无效\n%s\n' "$path" "$output" >&2
        failures=$((failures + 1))
        return
    fi

    skill_count=$((skill_count + 1))
}

for path in "${paths[@]}"; do
    base=${path##*/}

    # Skill sessions produce hidden timestamped logs; they are evidence for a
    # session, not repository source, and are explicitly excluded by AGENTS.md.
    case "$base" in
        .agent.*.log|.*.*.log)
            printf '✗ 禁止提交技能会话日志：%s\n' "$path" >&2
            log_count=$((log_count + 1))
            failures=$((failures + 1))
            ;;
    esac

    if [[ "$path" == skills/*/SKILL.md ]]; then
        validate_skill_manifest "$path"
    fi

    case "$path" in
        hooks/*.json|tools/*.json|plugins/*.json|plugins/*/*.json|plugins/*/*/*.json)
            validate_json "$path"
            ;;
    esac

    if ! interpreter=$(shell_interpreter "$path"); then
        printf '✗ %s：无法读取暂存内容\n' "$path" >&2
        failures=$((failures + 1))
        continue
    fi
    if [[ -n "$interpreter" ]]; then
        case "$path" in
            skills/form/references/source-snapshots/*) ;;
            *) validate_shell_mode "$path" ;;
        esac
        validate_shell "$path" "$interpreter"
    fi

    if interpreter=$(python_interpreter "$path"); then
        if [[ -n "$interpreter" ]]; then
            case "$path" in
                skills/form/references/source-snapshots/*) ;;
                *) validate_shell_mode "$path"; validate_python "$path" ;;
            esac
        fi
    fi
done

if (( failures > 0 )); then
    printf '✗ 检查失败：%d 项错误，%d 个 Shell 文件，%d 个 Python 文件，%d 个 JSON 文件，%d 个技能清单，%d 个日志文件。\n' \
        "$failures" "$shell_count" "$python_count" "$json_count" "$skill_count" "$log_count" >&2
    exit 1
fi

printf '✓ 检查通过：%d 个路径，%d 个 Shell 文件，%d 个 Python 文件，%d 个 JSON 文件，%d 个技能清单。\n' \
    "${#paths[@]}" "$shell_count" "$python_count" "$json_count" "$skill_count"
