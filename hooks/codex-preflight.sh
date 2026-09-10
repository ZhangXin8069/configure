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

# 从当前目录向仓库根收集全部说明文件，近处优先；这比只取一个根文件
# 更接近实际的层级覆盖语义，同时仍只输出路径和行数，不自动读取正文。
context_dir="$PWD"
priority=1
while :; do
    for instruction_name in AGENTS.md CODEX.md CLAUDE.md OPENCODE.md; do
        instruction="$context_dir/$instruction_name"
        if is_seen_instruction "$instruction"; then
            continue
        fi
        seen_instructions+=("$instruction")
        if [[ -f "$instruction" ]]; then
            instruction_lines=$(wc -l < "$instruction" | tr -d ' ')
            printf 'instruction[%d]=%s|lines=%s\n' "$priority" "$instruction" "$instruction_lines"
            instruction_count=$((instruction_count + 1))
            priority=$((priority + 1))
        fi
    done
    [[ "$context_dir" == "$repo_root" ]] && break
    parent="${context_dir%/*}"
    [[ -n "$parent" ]] || parent=/
    [[ "$parent" == "$context_dir" ]] && break
    context_dir="$parent"
done

if [[ -d "$repo_root/skills" ]]; then
    printf 'skills_dir=%s\n' "$repo_root/skills"
fi
for runtime_config in \
    "$repo_root/.codex/config.toml" \
    "$repo_root/.codex/hooks.json" \
    "$repo_root/.opencode/opencode.json"; do
    [[ -f "$runtime_config" ]] && printf 'runtime_config=%s\n' "$runtime_config"
done

printf 'instruction_count=%d\n' "$instruction_count"
printf 'codex-preflight: 只读预检完成\n'
