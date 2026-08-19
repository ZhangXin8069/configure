#!/usr/bin/env bash
# grm-cache — 依据 lib/_gitignore 规则，将已跟踪且匹配的文件移出 git 索引 (git rm --cached)，外来目录（子库、_ 前缀目录等）除外

set -euo pipefail
_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

GITIGNORE="${HOME}/configure/lib/_gitignore"
[ -f "$GITIGNORE" ] || { echo "ERROR: 忽略规则文件不存在: ${GITIGNORE}"; exit 1; }

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "ERROR: 不在 git 仓库内"; exit 1; }
echo "Repo: ${REPO_ROOT}"
echo "Rule: ${GITIGNORE}"

DRY=0
if [ "${1:-}" = "-n" ] || [ "${1:-}" = "--dry-run" ]; then
    DRY=1
fi

# 临时仓库隔离：避免仓库内其他 .gitignore（含损坏的 .gitignore 符号链接）干扰匹配
TMP_REPO=$(mktemp -d)
trap 'rm -rf "$TMP_REPO"' EXIT
git init -q "$TMP_REPO"

# 匹配：已跟踪文件 ∩ _gitignore 规则（仅取 _gitignore 来源的非否定模式）
mapfile -t FILES < <(
    git -C "$REPO_ROOT" ls-files |
        git -C "$TMP_REPO" -c core.excludesFile="$GITIGNORE" check-ignore --no-index --stdin -v 2>/dev/null |
        awk -v src="$GITIGNORE" -F'\t' '
            index($1, src ":") == 1 {
                pat = $1; sub(/^[^:]*:[0-9]+:/, "", pat)
                if (pat !~ /^!/) print $2
            }'
)

# 过滤外来目录：路径含 _ 前缀目录段 或 嵌套 .git 子库
KEEP=()
for f in "${FILES[@]:-}"; do
    case "$f" in
        */*) ;;
        *) KEEP+=("$f"); continue ;;
    esac
    dir="${f%/*}"
    p="$REPO_ROOT"
    foreign=0
    while :; do
        seg="${dir%%/*}"
        p="$p/$seg"
        case "$seg" in
            _*) foreign=1; break ;;
        esac
        if [ -e "$p/.git" ]; then
            foreign=1
            break
        fi
        if [ "$dir" = "${dir#*/}" ]; then
            break
        fi
        dir="${dir#*/}"
    done
    if [ "$foreign" -eq 0 ]; then
        KEEP+=("$f")
    else
        echo "skip(外来): ${f}"
    fi
done

if [ "${#KEEP[@]}" -eq 0 ]; then
    echo "无匹配文件（外来目录除外），索引无需变更。"
else
    echo "匹配 ${#KEEP[@]} 个文件:"
    printf '  %s\n' "${KEEP[@]}"
    if [ "$DRY" -eq 1 ]; then
        echo "dry-run: 未执行 git rm --cached"
    else
        git -C "$REPO_ROOT" rm --cached "${KEEP[@]}"
    fi
fi

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
