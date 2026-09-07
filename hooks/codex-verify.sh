#!/usr/bin/env bash
# Verify the current worktree without sourcing or executing repository code.

set -Eeuo pipefail

usage() {
    cat <<'USAGE'
用法：codex-verify.sh [--changed|--paths <路径...>]

  --changed       检查 Git 工作树中全部新增/修改文件（默认）
  --paths <...>   只检查指定路径，路径相对当前目录或使用绝对路径
USAGE
}

mode=changed
declare -a requested_paths=()
case "${1:-}" in
    '') ;;
    --changed|--worktree) mode=changed ;;
    --paths)
        mode=paths
        shift
        requested_paths+=("$@")
        ;;
    -h|--help)
        usage
        exit 0
        ;;
    *)
        usage >&2
        printf 'codex-verify: 未知选项：%s\n' "$1" >&2
        exit 2
        ;;
esac

command -v git >/dev/null 2>&1 || {
    printf 'codex-verify: 未找到 git\n' >&2
    exit 2
}

canonicalize_path() {
    local candidate=$1
    local existing=$candidate
    local component
    local canonical
    local -a missing=()
    local -a missing_tail=()

    if [[ -e "$existing" || -L "$existing" ]]; then
        realpath "$existing"
        return
    fi

    while [[ ! -e "$existing" && ! -L "$existing" ]]; do
        component=${existing##*/}
        [[ -n "$component" && "$component" != "." ]] || return 1
        if ((${#missing[@]} > 0)); then
            missing=("$component" "${missing[@]}")
        else
            missing=("$component")
        fi
        existing=${existing%/*}
        [[ -n "$existing" ]] || existing=/
    done

    canonical=$(realpath "$existing") || return 1
    for component in "${missing[@]}"; do
        case "$component" in
            ''|.)
                continue
                ;;
            ..)
                if ((${#missing_tail[@]} > 0)); then
                    missing_tail=("${missing_tail[@]:0:${#missing_tail[@]}-1}")
                else
                    canonical=$(realpath "$canonical/..") || return 1
                fi
                ;;
            *)
                if ((${#missing_tail[@]} == 0)) &&
                    [[ -e "$canonical/$component" || -L "$canonical/$component" ]]; then
                    canonical=$(realpath "$canonical/$component") || return 1
                else
                    missing_tail+=("$component")
                fi
                ;;
        esac
    done

    printf '%s' "$canonical"
    for component in "${missing_tail[@]}"; do
        printf '/%s' "$component"
    done
    printf '\n'
}

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || {
    printf 'codex-verify: 当前目录不在 Git 仓库中\n' >&2
    exit 1
}
repo_root=$(cd -- "$repo_root" && pwd -P)
caller_dir=$PWD
cd -- "$repo_root"

declare -a paths=()
if [[ "$mode" == changed ]]; then
    if git rev-parse --verify HEAD >/dev/null 2>&1; then
        while IFS= read -r -d '' path; do
            paths+=("$path")
        done < <(git diff HEAD --name-only --diff-filter=ACMR -z --)
    else
        while IFS= read -r -d '' path; do
            paths+=("$path")
        done < <(git diff --name-only --diff-filter=ACMR -z --)
        while IFS= read -r -d '' path; do
            paths+=("$path")
        done < <(git diff --cached --name-only --diff-filter=ACMR -z --)
    fi
    while IFS= read -r -d '' path; do
        paths+=("$path")
    done < <(git ls-files --others --exclude-standard -z --)
else
    if (( ${#requested_paths[@]} == 0 )); then
        printf 'codex-verify: --paths 至少需要一个路径\n' >&2
        exit 2
    fi
    command -v realpath >/dev/null 2>&1 || {
        printf 'codex-verify: 未找到 realpath\n' >&2
        exit 2
    }
    for raw_path in "${requested_paths[@]}"; do
        if [[ "$raw_path" == /* ]]; then
            candidate=$raw_path
        else
            candidate=$caller_dir/$raw_path
        fi
        canonical=$(canonicalize_path "$candidate") || {
            printf '✗ 无法规范化路径：%s\n' "$raw_path" >&2
            exit 1
        }
        case "$canonical" in
            "$repo_root")
                printf '✗ 不接受仓库根目录：%s\n' "$raw_path" >&2
                exit 1
                ;;
            "$repo_root"/*)
                paths+=("${canonical#"$repo_root"/}")
                ;;
            *)
                printf '✗ 路径在仓库外：%s\n' "$raw_path" >&2
                exit 1
                ;;
        esac
    done
fi

if (( ${#paths[@]} == 0 )); then
    printf '✓ codex-verify: 没有新增或修改文件\n'
    exit 0
fi

failures=0
shell_count=0
log_count=0

if ! diff_output=$(git diff --check -- "${paths[@]}" 2>&1); then
    printf '✗ git diff --check 失败：\n%s\n' "$diff_output" >&2
    failures=$((failures + 1))
fi

validate_untracked_whitespace() {
    local path=$1
    local index_status
    local diff_status=0
    local output

    [[ -f "$path" ]] || return

    if git ls-files --error-unmatch -- "$path" >/dev/null 2>&1; then
        return
    fi
    index_status=$?
    if (( index_status > 1 )); then
        printf '✗ %s：无法判断文件是否受 Git 跟踪\n' "$path" >&2
        failures=$((failures + 1))
        return
    fi

    output=$(git diff --no-index --check -- /dev/null "$path" 2>&1) || diff_status=$?
    if [[ -n "$output" ]]; then
        printf '✗ %s：未跟踪文件空白检查失败：\n%s\n' "$path" "$output" >&2
        failures=$((failures + 1))
    elif (( diff_status > 1 )); then
        printf '✗ %s：未跟踪文件空白检查无法完成\n' "$path" >&2
        failures=$((failures + 1))
    fi
}

shell_interpreter() {
    local path=$1
    local first_line=

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

    [[ -f "$path" && ! -L "$path" ]] || return 0
    IFS= read -r first_line < "$path" || true
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

    if [[ -L "$path" ]]; then
        printf '• 跳过符号链接 Shell 文件：%s\n' "$path"
        return
    fi
    if [[ ! -f "$path" ]]; then
        printf '• 跳过已删除文件：%s\n' "$path"
        return
    fi
    if ! command -v "$interpreter" >/dev/null 2>&1; then
        printf '✗ %s：缺少语法检查器 %s\n' "$path" "$interpreter" >&2
        failures=$((failures + 1))
        return
    fi
    if ! output=$("$interpreter" -n -- "$path" 2>&1); then
        printf '✗ %s：%s -n 失败\n%s\n' "$path" "$interpreter" "$output" >&2
        failures=$((failures + 1))
        return
    fi
    shell_count=$((shell_count + 1))
}

for path in "${paths[@]}"; do
    if [[ ! -f "$path" ]]; then
        printf '✗ 路径不存在或不是普通文件：%s\n' "$path" >&2
        failures=$((failures + 1))
        continue
    fi

    validate_untracked_whitespace "$path"

    base=${path##*/}
    case "$base" in
        .agent.*.log|.*.*.log)
            printf '✗ 禁止提交技能会话日志：%s\n' "$path" >&2
            log_count=$((log_count + 1))
            failures=$((failures + 1))
            ;;
    esac

    if interpreter=$(shell_interpreter "$path"); then
        if [[ -n "$interpreter" ]]; then
            validate_shell "$path" "$interpreter"
        fi
    fi
done

if (( failures > 0 )); then
    printf '✗ codex-verify: %d 项错误，%d 个 Shell 文件，%d 个日志文件\n' \
        "$failures" "$shell_count" "$log_count" >&2
    exit 1
fi

printf '✓ codex-verify: %d 个路径，%d 个 Shell 文件\n' \
    "${#paths[@]}" "$shell_count"
