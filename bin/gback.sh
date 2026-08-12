#!/usr/bin/env bash
# gback — 以远程库为唯一基准，放弃本地全部差异，保持与远程完全一致
#   · 多余的就删：本地未跟踪/忽略文件、本地独有提交、远程已不存在的本地分支与标签
#   · 缺失的就补：远程有而本地缺失或被修改的跟踪文件，从远程恢复

_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel) || {
    echo "ERROR: 不在 git 仓库内。"
    exit 1
}
echo "Repo:    ${REPO_ROOT}"
cd "${REPO_ROOT}"

BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "${BRANCH}" == "HEAD" ]]; then
    echo "ERROR: HEAD 处于游离状态，请先检出分支。"
    exit 1
fi
echo "Branch:  ${BRANCH}"

git fetch --all --prune --prune-tags || {
    echo "ERROR: git fetch 失败。"
    exit 1
}

UPSTREAM=$(git rev-parse --abbrev-ref "${BRANCH}@{upstream}" 2>/dev/null) || {
    echo "ERROR: 分支 ${BRANCH} 无上游，无法以远程为基准。"
    exit 1
}
echo "Upstream: ${UPSTREAM}"

# 1. 本地独有提交 —— 放弃
UNPUSHED=$(git log --oneline --reverse "${UPSTREAM}..${BRANCH}" 2>/dev/null || true)
if [[ -n "${UNPUSHED}" ]]; then
    echo "放弃本地独有提交："
    echo "${UNPUSHED}"
else
    echo "无本地独有提交"
fi

# 2. 与远程不同的跟踪文件 —— 缺失就补、修改就还原（重置前预览）
CHANGED=$(git diff --name-status HEAD "${UPSTREAM}" 2>/dev/null || true)
if [[ -n "${CHANGED}" ]]; then
    echo "以下文件与远程不同，将从远程恢复（覆盖本地）："
    echo "${CHANGED}" | head -20 || true
else
    echo "无缺失/被修改的跟踪文件"
fi

# 3. 多余文件 —— 删除（未跟踪/忽略）
TO_CLEAN=$(git clean -ndx | wc -l)
if (( TO_CLEAN > 0 )); then
    echo "删除 ${TO_CLEAN} 个多余文件（未跟踪/忽略）："
    git clean -ndx | sed 's/^Would remove /  /' | head -20 || true
else
    echo "无多余文件"
fi

# 执行：重置为远程基准（补缺失、还原差异），再删除多余文件
git reset --hard "${UPSTREAM}"
git clean -fdx
git checkout -B "${BRANCH}" "${UPSTREAM}"

# 4. 本地多余分支（远程已不存在）—— 删除，保持引用一致
REMOTE_BRANCHES=$(git for-each-ref --format='%(refname:short)' refs/remotes | sed 's|^[^/]*/||' | sort -u)
EXTRA_LOCAL=""
while IFS= read -r b; do
    [[ "${b}" == "${BRANCH}" ]] && continue
    grep -qxF "${b}" <<<"${REMOTE_BRANCHES}" || EXTRA_LOCAL+="${b}"$'\n'
done < <(git for-each-ref --format='%(refname:short)' refs/heads)
if [[ -n "${EXTRA_LOCAL}" ]]; then
    echo "删除本地多余分支（远程已不存在）："
    echo "${EXTRA_LOCAL}" | sed 's/^/  /'
    while IFS= read -r b; do
        if [[ -n "${b}" ]]; then
            git branch -D "${b}" >/dev/null 2>&1 || echo "  [warn] 删除分支 ${b} 失败"
        fi
    done <<< "${EXTRA_LOCAL}"
else
    echo "无本地多余分支"
fi

# 校验：完全一致
STILL_DIRTY=$(git status --porcelain)
if [[ -z "${STILL_DIRTY}" ]]; then
    echo "OK: 工作区干净（无多余/缺失/被修改文件）"
else
    echo "WARNING: 工作区仍有差异："
    echo "${STILL_DIRTY}"
fi
if [[ "$(git rev-parse HEAD)" == "$(git rev-parse "${UPSTREAM}")" ]]; then
    echo "OK: 本地 HEAD 与 ${UPSTREAM} 一致"
else
    echo "WARNING: 本地 HEAD 与 ${UPSTREAM} 不一致"
fi
EXTRA_REMAIN=""
while IFS= read -r b; do
    [[ "${b}" == "${BRANCH}" ]] && continue
    grep -qxF "${b}" <<<"${REMOTE_BRANCHES}" || EXTRA_REMAIN+="${b}"$'\n'
done < <(git for-each-ref --format='%(refname:short)' refs/heads)
if [[ -z "${EXTRA_REMAIN}" ]]; then
    echo "OK: 无本地多余分支"
else
    echo "WARNING: 仍有本地多余分支："
    echo "${EXTRA_REMAIN}" | sed 's/^/  /'
fi
echo "HEAD:    $(git log --oneline -1)"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
