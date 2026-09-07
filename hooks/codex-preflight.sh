#!/usr/bin/env bash
# Read-only context discovery for the beginning of an agent session.

set -Eeuo pipefail

command -v git >/dev/null 2>&1 || {
    printf 'codex-preflight: 未找到 git\n' >&2
    exit 2
}

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || {
    printf 'codex-preflight: 当前目录不在 Git 仓库中\n' >&2
    exit 1
}
repo_root=$(cd -- "$repo_root" && pwd -P)

branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || printf 'HEAD(detached)')

printf 'codex-preflight event=session-start\n'
printf 'repo_root=%s\n' "$repo_root"
printf 'branch=%s\n' "$branch"

instruction_count=0
declare -a seen_instructions=()
is_seen_instruction() {
    local candidate=$1
    local seen
    if ((${#seen_instructions[@]} > 0)); then
        for seen in "${seen_instructions[@]}"; do
            [[ "$seen" == "$candidate" ]] && return 0
        done
    fi
    return 1
}
for instruction in \
    "$repo_root/AGENTS.md" \
    "$repo_root/CODEX.md" \
    "$PWD/AGENTS.md"; do
    if is_seen_instruction "$instruction"; then
        continue
    fi
    seen_instructions+=("$instruction")
    if [[ -f "$instruction" ]]; then
        printf 'instruction=%s\n' "$instruction"
        instruction_count=$((instruction_count + 1))
    fi
done

if [[ -d "$repo_root/skills" ]]; then
    printf 'skills_dir=%s\n' "$repo_root/skills"
fi

printf 'instruction_count=%d\n' "$instruction_count"
printf 'codex-preflight: 只读预检完成\n'
