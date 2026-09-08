#!/usr/bin/env bash
# Read-only session summary for handoff and closeout.

set -Eeuo pipefail

command -v git >/dev/null 2>&1 || {
    printf 'codex-summary: 未找到 git\n' >&2
    exit 2
}

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || {
    printf 'codex-summary: 当前目录不在 Git 仓库中\n' >&2
    exit 1
}
repo_root=$(cd -- "$repo_root" && pwd -P)

branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || printf 'HEAD(detached)')
head=unborn
last_commit=unborn
if git rev-parse --verify HEAD >/dev/null 2>&1; then
    head=$(git rev-parse --short=12 HEAD 2>/dev/null || git rev-parse --short HEAD)
    last_commit=$(git log -1 --format='%h %s' --decorate=no 2>/dev/null || printf '%s' "$head")
fi

staged_count=0
unstaged_count=0
untracked_count=0
declare -a seen_paths=()
declare -a recent_paths=()

add_recent_path() {
    local candidate=$1
    local seen

    if ((${#seen_paths[@]} > 0)); then
        for seen in "${seen_paths[@]}"; do
            if [[ "$seen" == "$candidate" ]]; then
                return
            fi
        done
    fi

    seen_paths+=("$candidate")
    if ((${#recent_paths[@]} < 5)); then
        recent_paths+=("$candidate")
    fi
}

while IFS= read -r -d '' entry; do
    status=${entry:0:2}
    path=${entry:3}

    case "$status" in
        '??')
            untracked_count=$((untracked_count + 1))
            add_recent_path "$path"
            continue
            ;;
        '!!')
            continue
            ;;
    esac

    case ${status:0:1} in
        ' ') ;;
        *) staged_count=$((staged_count + 1)) ;;
    esac
    case ${status:1:1} in
        ' ') ;;
        *) unstaged_count=$((unstaged_count + 1)) ;;
    esac

    case ${status:0:1} in
        R|C)
            if IFS= read -r -d '' renamed_path; then
                path=$renamed_path
            fi
            ;;
    esac

    add_recent_path "$path"
done < <(git status --porcelain=v1 -z --untracked-files=normal --)

if (( staged_count == 0 && unstaged_count == 0 && untracked_count == 0 )); then
    worktree_status=clean
else
    worktree_status=dirty
fi

printf 'codex-summary event=session-summary\n'
printf 'repo_root=%s\n' "$repo_root"
printf 'branch=%s\n' "$branch"
printf 'head=%s\n' "$head"
printf 'last_commit=%s\n' "$last_commit"
printf 'worktree_status=%s\n' "$worktree_status"
printf 'staged_count=%d\n' "$staged_count"
printf 'unstaged_count=%d\n' "$unstaged_count"
printf 'untracked_count=%d\n' "$untracked_count"

if ((${#recent_paths[@]} > 0)); then
    for path in "${recent_paths[@]}"; do
        printf 'recent_path=%s\n' "$path"
    done
fi

printf 'codex-summary: 只读交接摘要完成\n'
