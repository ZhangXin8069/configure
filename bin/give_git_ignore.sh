#!/usr/bin/env bash
# 依据 git 工作区现有文件的后缀生成 .gitignore：
# 仅保留这些后缀 + keep 清单，其余全部忽略。
# 若已存在 .gitignore，会先重命名为 .gitignore.<YYYY-MM-DD-HH-MM-SS>.bak
# 同时为 data/、logs/ 和 docs/ 子目录按固定内容生成 .gitignore（目录不存在则跳过）
#
# 用法: give_git_ignore.sh [-f] [-n] [-o OUT] [-k PATTERN]... [--no-default-keep] [-sub]
#   -f               跳过备份，直接覆盖已存在的 .gitignore
#   -n, --dry-run    只打印，不写入、不备份
#   -o OUT           输出路径（默认 <repo>/.gitignore）
#   -k PATTERN       追加保留项（可多次）
#   --no-default-keep 丢弃内建默认 keep 清单
#   -sub             只写 data/、logs/、docs/ 子目录的 .gitignore
set -euo pipefail

# ---- 默认保留: 无后缀 / 特殊情况但值得纳入版本控制的文件 ----
DEFAULT_KEEP=(
  'Makefile' 'makefile' 'GNUmakefile'
  'Dockerfile' 'dockerfile' 'Containerfile'
  'LICENSE' 'LICENSE.*' 'COPYING' 'COPYING.*' 'NOTICE' 'NOTICE.*'
  'README' 'README.*' 'AUTHORS' 'CONTRIBUTORS'
  'CHANGELOG' 'CHANGELOG.*'
  '.gitignore' '.gitattributes' '.gitmodules' '.gitkeep'
  '.editorconfig' '.clang-format' '.clang-tidy'
  '.env.example' '.env.sample' '.keep'
)

# form 的固定快照完整保留 15 个软链接；其中 6 个无后缀入口必须精确放行，
# 既包括权威目录，也包括 OpenCode 加载镜像。不要放宽为整个快照目录通配。
FORM_SNAPSHOT_KEEP=(
  'skills/form/references/source-snapshots/configure-main/bin/cl'
  'skills/form/references/source-snapshots/configure-main/bin/cls'
  'skills/form/references/source-snapshots/configure-main/bin/co'
  'skills/form/references/source-snapshots/configure-main/bin/cos'
  'skills/form/references/source-snapshots/configure-main/bin/op'
  'skills/form/references/source-snapshots/configure-main/bin/ops'
  '.opencode/skills/form/references/source-snapshots/configure-main/bin/cl'
  '.opencode/skills/form/references/source-snapshots/configure-main/bin/cls'
  '.opencode/skills/form/references/source-snapshots/configure-main/bin/co'
  '.opencode/skills/form/references/source-snapshots/configure-main/bin/cos'
  '.opencode/skills/form/references/source-snapshots/configure-main/bin/op'
  '.opencode/skills/form/references/source-snapshots/configure-main/bin/ops'
)

FORCE=0; DRY=0; OUT=""; NO_DEFAULT=0; SUB_ONLY=0
EXTRA_KEEP=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--force)           FORCE=1; shift ;;
        -n|--dry-run)         DRY=1; shift ;;
        -o|--output)          OUT="${2:?}"; shift 2 ;;
        -k|--keep)            EXTRA_KEEP+=("${2:?}"); shift 2 ;;
        --no-default-keep)    NO_DEFAULT=1; shift ;;
        -sub|--sub-only)      SUB_ONLY=1; shift ;;
        -h|--help)
            sed -n '2,13p' "$0"; exit 0 ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

root=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "Not inside a git repository." >&2; exit 1; }
cd "$root"
OUT=${OUT:-$root/.gitignore}

# ---- 备份已存在的文件 ----
# 命名: <file>.<YYYY-MM-DD-HH-MM-SS>.bak；同秒冲突追加 -N
backup_existing() {
    local f="$1" ts bak i
    ts=$(date '+%Y-%m-%d-%H-%M-%S')
    bak="${f}.${ts}.bak"
    i=1
    while [[ -e "$bak" ]]; do
        bak="${f}.${ts}-${i}.bak"
        ((i++))
    done
    mv -- "$f" "$bak"
    printf '%s\n' "$bak"
}

# ---- 通用: 写子目录 .gitignore（备份逻辑同主 .gitignore） ----
# 参数: <target_path> <content_line1> <content_line2> ...
write_sub_ignore() {
    local target="$1"; shift
    local content=("$@")

    if [[ -e "$target" ]]; then
        if (( FORCE == 1 )); then
            :  # 直接覆盖，不备份
        elif (( DRY == 1 )); then
            echo "[dry-run] would back up: $target -> ${target}.<ts>.bak" >&2
        else
            local bak
            bak=$(backup_existing "$target")
            echo "backed up: $target -> $bak"
        fi
    fi

    if (( DRY == 1 )); then
        echo "--- $target (dry-run) ---" >&2
        printf '%s\n' "${content[@]}" >&2
        echo "--- end ---" >&2
    else
        printf '%s\n' "${content[@]}" > "$target"
        echo "written: $target"
    fi
}

# ---- 各子目录 .gitignore 内容 ----
# data/: 只保留 .gitignore、AGENTS.md、README.md
apply_data_ignore() {
    if [[ ! -d data ]]; then
        echo "skip: data 目录不存在"
        return 0
    fi
    write_sub_ignore "data/.gitignore" \
        '*' \
        '!.gitignore' \
        '!AGENTS.md' \
        '!README.md'
}

# logs/: 保留 .gitignore、AGENTS.md、README.md、所有 .txt
# 注: 按用户要求字面保留开头的两个 `*`（重复的 * 无副作用）
apply_logs_ignore() {
    if [[ ! -d logs ]]; then
        echo "skip: logs 目录不存在"
        return 0
    fi
    write_sub_ignore "logs/.gitignore" \
        '*' \
        '*' \
        '!.gitignore' \
        '!AGENTS.md' \
        '!README.md' \
        '!*.txt'
}

# docs/: 忽略 docs 下所有目录
apply_docs_ignore() {
    if [[ ! -d docs ]]; then
        echo "skip: docs 目录不存在"
        return 0
    fi
    write_sub_ignore "docs/.gitignore" \
        '**/'
}

# ---- 备份主 .gitignore ----
if (( SUB_ONLY == 0 )); then
    if [[ -e "$OUT" ]]; then
        if (( FORCE == 1 )); then
            :
        elif (( DRY == 1 )); then
            echo "[dry-run] would back up: $OUT -> ${OUT}.<ts>.bak" >&2
        else
            bak=$(backup_existing "$OUT")
            echo "backed up: $OUT -> $bak"
        fi
    fi
fi

# ---- 合并 keep 清单并去重 ----
keep=()
(( NO_DEFAULT == 0 )) && keep+=("${DEFAULT_KEEP[@]}" "${FORM_SNAPSHOT_KEEP[@]}")
(( ${#EXTRA_KEEP[@]} )) && keep+=("${EXTRA_KEEP[@]}")

declare -A _seen=()
uniq_keep=()
for p in "${keep[@]}"; do
    [[ -n "${_seen[$p]:-}" ]] && continue
    _seen[$p]=1
    uniq_keep+=("$p")
done

# ---- 收集工作区现有后缀 ----
mapfile -t exts < <(
    git ls-files -co --exclude-standard -z |
    while IFS= read -r -d '' f; do
        b=${f##*/}
        [[ $b == *.* && $b != .* ]] && printf '%s\n' "${b##*.}"
    done | sort -u
)

# ---- 生成内容 ----
gen() {
    echo "# Auto-generated by $(basename "$0") at $(date '+%F %T')"
    echo "# 策略: 仅保留工作区现有后缀 + keep 清单, 其余全部忽略"
    echo
    echo "# 1) 先忽略一切"
    echo "*"
    echo "# 2) 重新包含目录, 保证 git 能递归遍历(否则 !*.ext 不生效)"
    echo "!*/"
    echo
    echo "# 3) 保留工作区现有后缀"
    if (( ${#exts[@]} == 0 )); then
        echo "# (无)"
    else
        for e in "${exts[@]}"; do
            e=${e//\\/\\\\}; e=${e//\!/\\!}; e=${e//\#/\\#}
            e=${e//\[/\\[};  e=${e//\]/\\]}
            printf '!*.%s\n' "$e"
        done
    fi
    echo
    echo "# 4) 保留无后缀 / 特殊文件 (默认清单 + 用户 -k)"
    if (( ${#uniq_keep[@]} == 0 )); then
        echo "# (无)"
    else
        for p in "${uniq_keep[@]}"; do printf '!%s\n' "$p"; done
    fi
}

# ---- 主 .gitignore ----
if (( SUB_ONLY == 0 )); then
    if (( DRY == 1 )); then
        gen
    else
        gen > "$OUT"
        echo "written: $OUT"
        echo "kept extensions (${#exts[@]}):"
        if (( ${#exts[@]} )); then printf '  .%s\n' "${exts[@]}"; fi
        echo "kept special files (${#uniq_keep[@]}):"
        if (( ${#uniq_keep[@]} )); then printf '  %s\n' "${uniq_keep[@]}"; fi
    fi
fi

# ---- 子目录 .gitignore ----
echo
echo "# === 子目录 .gitignore ==="
apply_data_ignore
apply_logs_ignore
apply_docs_ignore

# ---- 汇总 ----
echo
echo "done."
