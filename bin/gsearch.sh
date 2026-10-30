#!/usr/bin/env bash
_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

# Usage: gsearch.sh [-f] [directory] [search_pattern]
#   在 git 工作区中搜索：已跟踪 + 未跟踪但未被 .gitignore 排除的文件
#   被 .gitignore 排除的文件不进入搜索范围
#   -f  只按文件名匹配（跳过内容搜索）；位置随意，如 `gsearch.sh . -f so`
RED=$(tput setaf 1; tput bold)
GREEN=$(tput setaf 2; tput bold)
YELLOW=$(tput setaf 3; tput bold)
BLUE=$(tput setaf 4; tput bold)
CYAN=$(tput setaf 6; tput bold)
RESET=$(tput sgr0)

# --- 参数解析：遍历所有参数，-f 可在任意位置 ---
only_filename=false
positional=()
seen_ddash=false
for arg in "$@"; do
    if $seen_ddash; then
        positional+=("$arg"); continue
    fi
    case "$arg" in
        -f) only_filename=true ;;
        --) seen_ddash=true ;;
        -*) echo -e "${RED}Unknown option: $arg${RESET}"; exit 1 ;;
        *)  positional+=("$arg") ;;
    esac
done
search_dir="${positional[0]:-.}"
search_pattern="${positional[1]}"

if [ -z "$search_pattern" ]; then
    echo -e "${RED}Usage: $0 [-f] [directory] [search_pattern]${RESET}"
    echo -e "${GREEN}Example: $0 . 'example'${RESET}"
    echo -e "${GREEN}Example: $0 src '[Ee]rror.*'${RESET}"
    echo -e "${GREEN}Example: $0 . -f 'config'      # 只匹配文件名（-f 位置随意）${RESET}"
    echo -e "${GREEN}Example: $0 -- . '-pattern'    # pattern 以 - 开头时用 --${RESET}"
    exit 1
fi

# --- 必须在 git 工作树内 ---
if ! repo_root=$(git -C "$search_dir" rev-parse --show-toplevel 2>/dev/null); then
    echo -e "${RED}Not inside a git work tree: $search_dir${RESET}"
    exit 1
fi

if [ "$only_filename" = true ]; then
    echo -e "${CYAN}Mode: ${YELLOW}只匹配文件名${RESET}"
else
    echo -e "${CYAN}Mode: ${YELLOW}内容 + 文件名（全匹配）${RESET}"
fi
echo -e "${CYAN}Repo:    ${YELLOW}$repo_root${RESET}"
echo -e "${CYAN}Search in: ${YELLOW}$search_dir${RESET}"
echo -e "${CYAN}Pattern: ${YELLOW}$search_pattern${RESET}"
echo -e "${BLUE}--- Start search ---${RESET}"

status=0

# 1. 文件内容搜索（-f 时跳过）
#    - 用 git ls-files 取文件集，与 -f 文件名搜索保持完全一致
#    - 子 shell 内 cd 到 search_dir，保证 ls-files 输出与 grep 读文件的基准路径一致
#    - xargs -0 -r：NUL 安全；-r 表示列表为空时不执行（避免 grep 读 stdin 挂起）
if [ "$only_filename" != true ]; then
    echo -e "${GREEN}Searching in file contents (git worktree):${RESET}"
    (
        cd "$search_dir" || exit 1
        git ls-files -co --exclude-standard -z \
          | xargs -0 -r grep -nH -I --color=always -- "$search_pattern"
    ) 2>/dev/null
    rc=$?
    # xargs 在 grep 无匹配时返回 123；只有真正错误才置 status
    [ "$rc" -gt 1 ] && [ "$rc" -ne 123 ] && status=1
fi

# 2. 文件名搜索（只匹配 basename，glob 语义与 find -name 一致）
echo -e "${GREEN}\nSearching in file names (git worktree):${RESET}"
(
    cd "$search_dir" || exit 1
    git ls-files -co --exclude-standard -z \
      | while IFS= read -r -d '' f; do
            b=${f##*/}
            case "$b" in
                *$search_pattern*) printf '%s\n' "$f" ;;
            esac
        done
) 2>/dev/null | while IFS= read -r file; do
    echo -e "${YELLOW}${file}${RESET}"
done

# 3. 错误处理
if [ "$status" -ne 0 ]; then
    echo -e "${RED}Some errors occurred during search.${RESET}"
fi

echo -e "${BLUE}--- End search ---${RESET}"
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
