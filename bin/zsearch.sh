#!/bin/bash
# Search for files with specific string in filename or content (skip binary files by default)
# Usage: ./search.sh [directory] [search_pattern]
# Note: Using tput or echo color codes for highlighting

search_dir="${1:-.}"
search_pattern="${2}"

# 方法一：使用tput设置颜色（参考tput.md）
RED=$(tput setaf 1; tput bold)      # 红色加粗
GREEN=$(tput setaf 2; tput bold)    # 绿色加粗
YELLOW=$(tput setaf 3; tput bold)   # 黄色加粗
BLUE=$(tput setaf 4; tput bold)     # 蓝色加粗
MAGENTA=$(tput setaf 5; tput bold)  # 洋红加粗
CYAN=$(tput setaf 6; tput bold)     # 青色加粗
WHITE=$(tput setaf 7; tput bold)    # 白色加粗
RESET=$(tput sgr0)                  # 重置颜色

# 方法二：使用echo颜色码（参考echo.md）
# RED='\e[1;31m'
# GREEN='\e[1;32m'
# YELLOW='\e[1;33m'
# BLUE='\e[1;34m'
# RESET='\e[0m'

# 检查输入参数
if [ -z "$search_pattern" ]; then
    echo -e "${RED}Usage: $0 [directory] [search_pattern]${RESET}"
    echo -e "${GREEN}Example: $0 . 'example'${RESET}"
    echo -e "${GREEN}Example: $0 /var/log '[Ee]rror.*'${RESET}"
    echo -e "${GREEN}Example: $0 . -i 'error'${RESET}"
    exit 1  # 参考exit.md的脚本退出示例
fi

echo -e "${CYAN}Searching in: ${YELLOW}$search_dir${RESET}"
echo -e "${CYAN}Pattern: ${YELLOW}$search_pattern${RESET}"
echo -e "${BLUE}--- Start search ---${RESET}"

# 1. 使用grep搜索文件内容（参考grep.md）
echo -e "${GREEN}Searching in file contents:${RESET}"
grep -rIH --color=always "$search_pattern" "$search_dir" 2>/dev/null 
# -I: 忽略二进制文件（参考grep.md）
# -H: 总是显示文件名（grep.md）
# --color=always: 总是显示颜色（grep.md）

# 2. 使用find搜索文件名（参考find和ls.md）
echo -e "${GREEN}\nSearching in file names:${RESET}"
find "$search_dir" -name "*${search_pattern}*" -type f 2>/dev/null | \
    while read file; do
        echo -e "${YELLOW}$file${RESET}"
    done

# 3. 错误处理（参考exit.md）
if [ $? -ne 0 ]; then
    echo -e "${RED}Some errors occurred during search.${RESET}"
fi

echo -e "${BLUE}--- End search ---${RESET}"

