#!/usr/bin/env bash
# grm-ignore — 重写 Git 历史，永久删除当前 .gitignore 中匹配的所有文件，
#              并强制推送所有分支/标签到远程，最后执行 GC 释放空间。
#
# ⚠️ 破坏性操作：会重写全部历史，远程协作者必须重新克隆。
# 建议在全新克隆的仓库副本中执行。
#
# 用法: grm-ignore.sh [-n|--dry-run] [-y|--yes] [--keep-backup]
#   -n, --dry-run   仅显示将被删除的文件，不执行重写
#   -y, --yes       跳过交互确认（危险）
#   --keep-backup   重写前自动打包备份到 backup.bundle
set -euo pipefail

_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

# ---- 依赖检查 ----
command -v git >/dev/null || { echo "ERROR: git 未安装"; exit 1; }
command -v git-filter-repo >/dev/null || {
    echo "ERROR: 未找到 git-filter-repo。请先安装: pip install git-filter-repo"
    exit 1
}

# ---- 仓库根 ----
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "ERROR: 不在 git 仓库内"; exit 1; }
cd "$REPO_ROOT"
echo "Repo: ${REPO_ROOT}"

GITIGNORE="${REPO_ROOT}/.gitignore"
[ -f "$GITIGNORE" ] || { echo "ERROR: 当前目录没有 .gitignore"; exit 1; }

# ---- 参数解析 ----
DRY=0; YES=0; KEEP_BACKUP=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        -n|--dry-run)    DRY=1; shift ;;
        -y|--yes)        YES=1; shift ;;
        --keep-backup)   KEEP_BACKUP=1; shift ;;
        -h|--help)       sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

# ---- 提取历史中所有曾被 .gitignore 匹配的文件路径 ----
# 思路: 遍历所有提交过的文件，用临时隔离仓库的 check-ignore 判定。
TMP_REPO=$(mktemp -d)
trap 'rm -rf "$TMP_REPO"' EXIT
git init -q "$TMP_REPO"

echo "[1/6] 提取历史中所有文件并与 .gitignore 匹配..."
mapfile -t TO_DELETE < <(
    # 历史上出现过的所有唯一路径
    git log --all --pretty=format: --name-only --diff-filter=A -z |
    tr -d '\0' | sort -u |
    git -C "$TMP_REPO" -c core.excludesFile="$GITIGNORE" \
        check-ignore --no-index --stdin -v 2>/dev/null |
    awk -F'\t' '!seen[$2]++ {print $2}'
)

if (( ${#TO_DELETE[@]} == 0 )); then
    echo "无匹配 .gitignore 的历史文件，无需重写。"
    echo "###${_NAME} done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
    exit 0
fi

echo "匹配 ${#TO_DELETE[@]} 个历史文件将被永久移除:"
printf '  %s\n' "${TO_DELETE[@]}" | head -200
(( ${#TO_DELETE[@]} > 200 )) && echo "  ... (还有 $(( ${#TO_DELETE[@]} - 200 )) 个)"

if [ "$DRY" -eq 1 ]; then
    echo "dry-run: 未执行历史重写、推送或 GC。"
    echo "###${_NAME} done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
    exit 0
fi

# ---- 二次确认 ----
if [ "$YES" -ne 1 ]; then
    echo
    echo "⚠️  即将重写全部 Git 历史并强制覆盖远程仓库。"
    echo "    所有协作者必须重新克隆，本地未推送的工作将无法恢复。"
    read -r -p "确认继续? 输入 'rewrite' 继续，其他任意键取消: " ans
    [ "$ans" = "rewrite" ] || { echo "已取消。"; exit 1; }
fi

# ---- 可选备份 ----
if [ "$KEEP_BACKUP" -eq 1 ]; then
    bak="backup.$(date '+%Y%m%d-%H%M%S').bundle"
    echo "[2/6] 备份全部引用到 ${bak} ..."
    git bundle create "$bak" --all
    echo "备份完成: ${bak}"
else
    echo "[2/6] 跳过备份 (--keep-backup 可开启)"
fi

# ---- 写入待删除路径文件，供 filter-repo 使用 ----
PATHS_FILE=$(mktemp)
trap 'rm -rf "$TMP_REPO" "$PATHS_FILE"' EXIT
printf '%s\n' "${TO_DELETE[@]}" > "$PATHS_FILE"

# ---- 记录远程 URL (filter-repo 会自动移除 origin) ----
ORIGIN_URL=$(git remote get-url origin 2>/dev/null || true)

# ---- 执行历史重写 ----
echo "[3/6] 运行 git filter-repo 重写历史..."
# --force: 允许在非全新克隆中运行（谨慎）
# --invert-paths: 移除匹配路径，而非保留
git filter-repo --force \
    --invert-paths \
    --paths-from-file "$PATHS_FILE"

# ---- 恢复远程 ----
if [ -n "$ORIGIN_URL" ]; then
    echo "[4/6] 恢复远程 origin: ${ORIGIN_URL}"
    git remote add origin "$ORIGIN_URL" 2>/dev/null || git remote set-url origin "$ORIGIN_URL"
else
    echo "[4/6] 未检测到远程 origin，跳过推送。"
fi

# ---- 强制推送所有分支和标签 ----
if [ -n "$ORIGIN_URL" ]; then
    echo "[5/6] 强制推送所有分支和标签到远程..."
    # --force: 覆盖远程历史
    # --all:   所有分支
    # --tags:  所有标签
    # --prune: 删除远程已不存在的分支
    git push --force --all origin
    git push --force --tags origin
    git push --force --prune origin 2>/dev/null || true
fi

# ---- 本地 GC ----
echo "[6/6] 本地 GC 回收空间..."
git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo
echo "完成。本地仓库已瘦身。"
echo "注意: 远程仓库的 GC 通常由托管平台(如 GitHub/GitLab)在其后台自动触发，"
echo "      执行强制推送后，平台可能需要一段时间才会实际释放磁盘空间。"
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
