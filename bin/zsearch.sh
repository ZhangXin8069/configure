#!/usr/bin/env bash
_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

# Usage: ./search.sh [-f] [directory] [search_pattern]
#   -f  只按文件名匹配（跳过内容搜索）；位置随意，如 `./search.sh . -f so`
RED=$(tput setaf 1; tput bold)
GREEN=$(tput setaf 2; tput bold)
YELLOW=$(tput setaf 3; tput bold)
BLUE=$(tput setaf 4; tput bold)
MAGENTA=$(tput setaf 5; tput bold)
CYAN=$(tput setaf 6; tput bold)
WHITE=$(tput setaf 7; tput bold)
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
    echo -e "${GREEN}Example: $0 /var/log '[Ee]rror.*'${RESET}"
    echo -e "${GREEN}Example: $0 . -f 'config'      # 只匹配文件名（-f 位置随意）${RESET}"
    echo -e "${GREEN}Example: $0 -- . '-pattern'    # pattern 以 - 开头时用 --${RESET}"
    exit 1
fi

if [ "$only_filename" = true ]; then
    echo -e "${CYAN}Mode: ${YELLOW}只匹配文件名${RESET}"
else
    echo -e "${CYAN}Mode: ${YELLOW}内容 + 文件名（全匹配）${RESET}"
fi
echo -e "${CYAN}Searching in: ${YELLOW}$search_dir${RESET}"
echo -e "${CYAN}Pattern: ${YELLOW}$search_pattern${RESET}"
echo -e "${BLUE}--- Start search ---${RESET}"

status=0

# 1. 文件内容搜索（-f 时跳过）；-- 防止 pattern 以 - 开头被 grep 当选项
if [ "$only_filename" != true ]; then
    echo -e "${GREEN}Searching in file contents:${RESET}"
    grep -rIH --color=always -- "$search_pattern" "$search_dir" 2>/dev/null
    rc=$?
    [ "$rc" -gt 1 ] && status=1
fi

# 2. 文件名搜索（-name 只匹配 basename）
echo -e "${GREEN}\nSearching in file names:${RESET}"
find "$search_dir" -name "*${search_pattern}*" -type f 2>/dev/null | \
    while read -r file; do
        echo -e "${YELLOW}${file}${RESET}"
    done

# 3. 错误处理
if [ "$status" -ne 0 ]; then
    echo -e "${RED}Some errors occurred during search.${RESET}"
fi

echo -e "${BLUE}--- End search ---${RESET}"
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
