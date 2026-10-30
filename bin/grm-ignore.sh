#!/usr/bin/env bash
# grm-ignore — 依据当前仓库内所有 .gitignore 规则，从全部 Git 历史中永久删除匹配的文件，
#              强制推送覆盖远程所有分支/标签，并执行 GC 回收本地空间。
#
# ⚠️ 破坏性操作：
#   - 重写所有分支、标签、远程跟踪分支的提交历史（commit id 全部改变）
#   - 强制覆盖远程仓库（协作者必须重新 clone，不能 pull）
#
# 强烈建议：在全新 clone 的副本中执行，并先 -n 预览。
# 依赖：git-filter-repo（pip install git-filter-repo / brew install git-filter-repo）
#
# 用法: grm-ignore.sh [-n] [-y] [--keep-backup] [-r REMOTE] [--no-push] [--no-gc]
#   -n, --dry-run   仅列出将被删除的文件，不做任何修改
#   -y, --yes       跳过交互确认（不建议）
#   --keep-backup   重写前打包备份到 backup.<ts>.bundle
#   -r, --remote    指定远程名（默认 origin；不存在则跳过推送）
#   --no-push       完成本地重写与 GC 后停止，不推送远程
#   --no-gc         跳过本地 GC（调试用；不会释放磁盘空间）
set -euo pipefail

# ===== 脚本位置 =====
_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

# ===== 依赖检查 =====
command -v git >/dev/null || { echo "ERROR: git 未安装"; exit 1; }
command -v git-filter-repo >/dev/null || {
    echo "ERROR: 未找到 git-filter-repo。安装方式："
    echo "  pip install git-filter-repo"
    echo "  或 brew install git-filter-repo"
    exit 1
}

# ===== 仓库根 =====
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "ERROR: 不在 git 仓库内"; exit 1; }
cd "$REPO_ROOT"
echo "Repo: ${REPO_ROOT}"

# ===== 参数解析 =====
DRY=0; YES=0; KEEP_BACKUP=0; DO_PUSH=1; DO_GC=1; REMOTE_NAME="origin"
while [[ $# -gt 0 ]]; do
    case "$1" in
        -n|--dry-run)  DRY=1; shift ;;
        -y|--yes)      YES=1; shift ;;
        --keep-backup) KEEP_BACKUP=1; shift ;;
        --no-push)     DO_PUSH=0; shift ;;
        --no-gc)       DO_GC=0; shift ;;
        -r|--remote)
            # 不能用 ${2:?}：set -u 下无自定义消息，报错指向变量名 "2"
            if [[ -z "${2:-}" || "$2" == -* ]]; then
                echo "ERROR: -r/--remote 需要指定远程名，例如：-r origin" >&2
                exit 1
            fi
            REMOTE_NAME="$2"; shift 2 ;;
        -h|--help)     sed -n '2,25p' "$0"; exit 0 ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

# ===== 工作区状态提示 =====
if [[ -n "$(git status --porcelain)" ]]; then
    echo "⚠️  工作区有未提交改动，建议先 commit 或 stash。"
    if (( YES == 0 && DRY == 0 )); then
        read -r -p "继续？[y/N] " ans
        [[ "$ans" =~ ^[Yy]$ ]] || { echo "已取消。"; exit 1; }
    fi
fi

# ===== 临时文件 =====
PATHS_ALL=$(mktemp)
DELETE_PATHS_FILE=$(mktemp)
MATCHES_FILE=$(mktemp)
SYMLINKS_ALL=$(mktemp)
PROTECTED_PATHS=$(mktemp)
FILENAME_CALLBACK_FILE=$(mktemp)
SKIPPED_PATHS=$(mktemp)
CHECK_INPUT=$(mktemp)
CHECK_OUTPUT=$(mktemp)
CHECK_ERROR=$(mktemp)
IGNORE_SHADOW_DIR=""
_cleanup() {
    rm -f -- "$PATHS_ALL" "$DELETE_PATHS_FILE" "$MATCHES_FILE" "$SYMLINKS_ALL" \
        "$PROTECTED_PATHS" "$FILENAME_CALLBACK_FILE" "$SKIPPED_PATHS" \
        "$CHECK_INPUT" "$CHECK_OUTPUT" "$CHECK_ERROR"
    [[ -z "$IGNORE_SHADOW_DIR" ]] || rm -rf -- "$IGNORE_SHADOW_DIR"
}
trap _cleanup EXIT

# ===== [1/6] 遍历历史，提取所有文件路径 =====
echo "[1/6] 遍历历史，提取所有文件路径..."
# log --name-only：遍历所有引用可达提交中的每个路径。
# 不使用 rev-list --objects：相同 blob 被多个路径复用时，它只会输出其中一个路径。
# 已知限制：路径含换行符时会被错误拆分（Git 允许但极罕见）
git -C "$REPO_ROOT" log --all --pretty=format: --name-only --no-renames -z \
  | tr '\0' '\n' \
  | awk 'length($0) > 0' \
  | sort -u > "$PATHS_ALL"

TOTAL=$(wc -l < "$PATHS_ALL")
echo "  历史中唯一文件路径: ${TOTAL}"
if (( TOTAL == 0 )); then
    echo "仓库历史为空，无需处理。"
    echo "###${_NAME} done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
    exit 0
fi

# 历史 symlink 以 mode 120000 存储。只要路径在任一可达提交中曾是
# symlink，就整体保护该路径，避免 filter-repo 删除它或它后来变成的普通文件。
# -m 让仅由合并提交解决的路径类型变化也出现在 raw diff 中。
git -C "$REPO_ROOT" log --all --raw --no-renames -m -z --format= \
  | tr '\0' '\n' \
  | awk '
        /^:[0-7]+ [0-7]+ / {
            old_mode = substr($0, 2, 6)
            new_mode = substr($0, 9, 6)
            if (!getline path) next
            if (old_mode == "120000" || new_mode == "120000") print path
        }
    ' \
  | sort -u > "$SYMLINKS_ALL"
TOTAL_SYMLINKS=$(wc -l < "$SYMLINKS_ALL")
echo "  历史中曾为软链接的唯一路径: ${TOTAL_SYMLINKS}（始终保护）"

# filter-repo 的 --path 会同时匹配其子路径。若旧提交中某路径是普通文件，
# 后又变成目录，必须连同它的祖先前缀一起保护。
{
    cat "$SYMLINKS_ALL"
    awk '/(^|\/)data(\/|$)/' "$PATHS_ALL"
} | awk '
        NF {
            path = $0
            print path
            while (sub(/\/[^/]+$/, "", path)) print path
        }
    ' \
  | sort -u > "$PROTECTED_PATHS"
TOTAL_PROTECTED=$(wc -l < "$PROTECTED_PATHS")
echo "  受保护路径及祖先前缀: ${TOTAL_PROTECTED}"

# ===== [1/6] 用仓库内所有 .gitignore 规则匹配 =====
# 关键：在真实仓库中运行 check-ignore
#   - Git 会自动读取每一层的 .gitignore，规则相对其所在目录生效（data/.gitignore 的 * 只作用于 data/）
#   - -c core.excludesFile=/dev/null：排除 ~/.config/git/ignore 等全局规则干扰
#   - --no-index：即使文件已被跟踪也判定
echo "[1/6] 用仓库内所有 .gitignore 规则匹配历史路径..."
mapfile -t CHECK_PATHS < <(
    awk -v protected_file="$PROTECTED_PATHS" '
        BEGIN {
            while ((getline path < protected_file) > 0) protected[path] = 1
            close(protected_file)
        }
        !($0 in protected)
    ' "$PATHS_ALL"
)

_check_ignore_range() {
    local start=$1 count=$2 rc midpoint
    (( count > 0 )) || return 0

    printf '%s\n' "${CHECK_PATHS[@]:start:count}" > "$CHECK_INPUT"
    set +e
    LC_ALL=C git -C "$REPO_ROOT" -c core.excludesFile=/dev/null -c core.quotePath=false \
        check-ignore --no-index --stdin -v < "$CHECK_INPUT" > "$CHECK_OUTPUT" 2> "$CHECK_ERROR"
    rc=$?
    set -e

    if (( rc <= 1 )); then
        cat "$CHECK_OUTPUT" >> "$MATCHES_FILE"
        return 0
    fi

    if (( count == 1 )) && (( rc == 128 )) \
        && grep -Fq 'is beyond a symbolic link' "$CHECK_ERROR"; then
        printf '%s\n' "${CHECK_PATHS[start]}" >> "$SKIPPED_PATHS"
        return 0
    fi

    if (( count == 1 )); then
        cat "$CHECK_ERROR" >&2
        return "$rc"
    fi

    midpoint=$(( count / 2 ))
    _check_ignore_range "$start" "$midpoint" 0 || return $?
    _check_ignore_range "$((start + midpoint))" "$((count - midpoint))" 0 || return $?
}

_check_skipped_in_shadow() {
    local git_dir ignore_path source dest

    IGNORE_SHADOW_DIR=$(mktemp -d)
    while IFS= read -r -d '' ignore_path; do
        [[ "${ignore_path##*/}" == ".gitignore" ]] || continue
        case "$ignore_path" in
            data|data/*|*/data|*/data/*) continue ;;
        esac
        source=${REPO_ROOT}/${ignore_path}
        [[ -f "$source" && ! -L "$source" ]] || continue
        dest=${IGNORE_SHADOW_DIR}/${ignore_path}
        mkdir -p -- "$(dirname -- "$dest")"
        cp -- "$source" "$dest"
    done < <(git -C "$REPO_ROOT" ls-files -z --cached --others --exclude-standard)

    while IFS= read -r ignore_path; do
        [[ -n "$ignore_path" ]] || continue
        mkdir -p -- "$IGNORE_SHADOW_DIR/$(dirname -- "$ignore_path")"
    done < "$SKIPPED_PATHS"

    git_dir=$(git -C "$REPO_ROOT" rev-parse --absolute-git-dir)
    set +e
    LC_ALL=C git --git-dir="$git_dir" --work-tree="$IGNORE_SHADOW_DIR" \
        -c core.excludesFile=/dev/null -c core.quotePath=false \
        check-ignore --no-index --stdin -v < "$SKIPPED_PATHS" > "$CHECK_OUTPUT" 2> "$CHECK_ERROR"
    local rc=$?
    set -e
    (( rc <= 1 )) || return "$rc"

    cat "$CHECK_OUTPUT" >> "$MATCHES_FILE"
    : > "$SKIPPED_PATHS"
}

: > "$MATCHES_FILE"
set +e
_check_ignore_range 0 "${#CHECK_PATHS[@]}" 0
CHECK_IGNORE_STATUS=$?
set -e
if (( CHECK_IGNORE_STATUS > 1 )); then
    echo "ERROR: git check-ignore 失败（退出码 ${CHECK_IGNORE_STATUS}）" >&2
    exit "$CHECK_IGNORE_STATUS"
fi

if [[ -s "$SKIPPED_PATHS" ]]; then
    set +e
    _check_skipped_in_shadow
    SHADOW_CHECK_STATUS=$?
    set -e
    if (( SHADOW_CHECK_STATUS > 1 )); then
        echo "  ⚠️ 影子工作树仍无法分类 symlink 后路径，将保守跳过。" >&2
    fi
fi

TOTAL_SKIPPED=$(wc -l < "$SKIPPED_PATHS")
if (( TOTAL_SKIPPED > 0 )); then
    mapfile -t SKIPPED_PATHS_LINES < "$SKIPPED_PATHS"
    echo "  ⚠️ 跳过 ${TOTAL_SKIPPED} 个穿过当前软链接的历史路径（无法安全分类）:"
    printf '    %s\n' "${SKIPPED_PATHS_LINES[@]:0:20}"
    if (( TOTAL_SKIPPED > 20 )); then
        echo "    ... (还有 $(( TOTAL_SKIPPED - 20 )) 个)"
    fi
fi

# 解析 -v 输出：<source>:<lineno>:<pattern>\t<pathname>
# 否定规则（!pattern）表示路径最终未被忽略，不能传给 filter-repo。
# 安全阀：永不删除历史 symlink、任意层级 data 目录及其祖先前缀，以及 .gitignore 自身。
mapfile -t TO_DELETE < <(
    awk -F'\t' -v protected_file="$PROTECTED_PATHS" '
        BEGIN {
            while ((getline path < protected_file) > 0) protected[path] = 1
            close(protected_file)
        }
        NF >= 2 && !seen[$2]++ {
            path = $2
            if (path in protected) next
            pattern = $1
            sub(/^.*:[0-9]+:/, "", pattern)
            if (pattern ~ /^!/) next
            n = split(path, a, "/")
            if (a[n] != ".gitignore") print path
        }
    ' "$MATCHES_FILE"
)

if (( ${#TO_DELETE[@]} == 0 )); then
    echo "无匹配 .gitignore 的历史文件，无需重写。"
    echo "###${_NAME} done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
    exit 0
fi

echo "匹配 ${#TO_DELETE[@]} 个历史文件将被永久移除："
printf '  %s\n' "${TO_DELETE[@]:0:300}"
if (( ${#TO_DELETE[@]} > 300 )); then
    echo "  ... (还有 $(( ${#TO_DELETE[@]} - 300 )) 个)"
fi

# ===== dry-run 出口 =====
if (( DRY == 1 )); then
    echo "dry-run: 未执行历史重写、推送或 GC。"
    echo "###${_NAME} done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
    exit 0
fi

# ===== 二次确认 =====
if (( YES == 0 )); then
    echo
    echo "⚠️  即将："
    echo "    1) 重写所有分支、标签、远程跟踪分支的提交历史"
    if (( DO_PUSH == 1 )); then
        echo "    2) 强制推送覆盖远程 '${REMOTE_NAME}'（含标签）"
    else
        echo "    2) 不推送（--no-push）"
    fi
    if (( DO_GC == 1 )); then
        echo "    3) 执行 reflog expire + gc"
    fi
    echo "    完成后协作者必须重新 clone，不能 pull。"
    read -r -p "确认继续？输入 'rewrite' 继续，其他键取消: " ans
    [ "$ans" = "rewrite" ] || { echo "已取消。"; exit 1; }
fi

# ===== .git 体积（用于最后对比） =====
SIZE_BEFORE=$(du -sh "$REPO_ROOT/.git" 2>/dev/null | awk '{print $1}')
echo "  .git 当前体积: ${SIZE_BEFORE:-unknown}"

# ===== [2/6] 可选备份 =====
if (( KEEP_BACKUP == 1 )); then
    bak="backup.$(date '+%Y%m%d-%H%M%S').bundle"
    echo "[2/6] 备份全部引用到 ${bak} ..."
    git bundle create "$bak" --all
    echo "  备份完成: ${bak} ($(du -h "$bak" 2>/dev/null | cut -f1))"
else
    echo "[2/6] 跳过备份（--keep-backup 可开启）"
fi

# ===== 记录远程信息（filter-repo 会自动移除 remote） =====
REMOTE_URL=""
if (( DO_PUSH == 1 )); then
    REMOTE_URL=$(git remote get-url "$REMOTE_NAME" 2>/dev/null || true)
    if [[ -n "$REMOTE_URL" ]]; then
        echo "  记录远程 ${REMOTE_NAME}: ${REMOTE_URL}"
    else
        echo "  ⚠️ 未找到远程 '${REMOTE_NAME}'，将跳过推送"
    fi
fi

# ===== 写入待删除路径与字面量过滤器 =====
# --paths-from-file 会解释 literal:/glob:/regex:/==>/#，不能承载任意文件名。
# 通过 NUL 列表和 filename callback 逐项匹配，避免文件名变成 filter-repo 指令。
printf '%s\0' "${TO_DELETE[@]}" > "$DELETE_PATHS_FILE"
cat > "$FILENAME_CALLBACK_FILE" <<'PY'
global _grm_ignore_delete_paths
if "_grm_ignore_delete_paths" not in globals():
    with open(os.environ["GRM_IGNORE_DELETE_PATHS_FILE"], "rb") as handle:
        _grm_ignore_delete_paths = {
            path for path in handle.read().split(b"\0") if path
        }

path = filename
while True:
    if path in _grm_ignore_delete_paths:
        return None
    slash = path.rfind(b"/")
    if slash < 0:
        break
    path = path[:slash]
return filename
PY

# ===== [3/6] 历史重写 =====
echo "[3/6] git filter-repo 重写历史（filename callback 移除匹配项）..."
# filter-repo 默认处理 refs/heads/、refs/tags/、refs/remotes/ 下的所有 refs
# 因此无需额外 --refs；如遇旧版本 bug 或需扩展范围，可追加：
#   --refs 'refs/heads/*' 'refs/tags/*' 'refs/remotes/*'
GRM_IGNORE_DELETE_PATHS_FILE="$DELETE_PATHS_FILE" \
    git filter-repo --force --filename-callback "$FILENAME_CALLBACK_FILE"

# ===== [4/6] 恢复远程 =====
if [[ -n "$REMOTE_URL" ]]; then
    echo "[4/6] 恢复远程 ${REMOTE_NAME}: ${REMOTE_URL}"
    if git remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
        git remote set-url "$REMOTE_NAME" "$REMOTE_URL"
    else
        git remote add "$REMOTE_NAME" "$REMOTE_URL"
    fi
else
    echo "[4/6] 无远程可恢复，跳过"
fi

# ===== [5/6] 强制推送 =====
if (( DO_PUSH == 1 )) && [[ -n "$REMOTE_URL" ]]; then
    echo "[5/6] 强制推送所有分支与标签到 ${REMOTE_NAME} ..."
    git push --force "$REMOTE_NAME" --all
    git push --force "$REMOTE_NAME" --tags
    echo "  提示：远端仍存在的旧分支/标签（本地已无同名者）不会被自动删除。"
    echo "        如需清理: git push --force --prune ${REMOTE_NAME}"
elif (( DO_PUSH == 1 )); then
    echo "[5/6] 无远程可推送，跳过"
else
    echo "[5/6] --no-push：跳过推送"
    echo "  本地已重写完成。之后手动推送时请用 --force："
    echo "    git push --force <remote> --all && git push --force <remote> --tags"
fi

# ===== [6/6] 本地 GC =====
if (( DO_GC == 1 )); then
    echo "[6/6] 本地 GC 回收空间..."
    git reflog expire --expire=now --all
    git gc --prune=now --aggressive
    SIZE_AFTER=$(du -sh "$REPO_ROOT/.git" 2>/dev/null | awk '{print $1}')
    echo "  .git 体积: ${SIZE_BEFORE:-?} -> ${SIZE_AFTER:-?}"
else
    echo "[6/6] --no-gc：跳过 GC"
fi

# ===== 完成 =====
echo
echo "完成。"
echo "注意:"
echo "  - 本地仓库已瘦身。"
echo "  - 远程仓库的 GC 由托管平台后台调度，磁盘空间可能几分钟~几小时后才真正释放。"
echo "  - 所有协作者必须重新 clone，不能 pull。"
echo "  - 子模块历史未被处理；如需清理子模块，cd 进子模块后单独执行本脚本。"
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
