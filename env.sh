#!/usr/bin/env bash
# 环境主入口: 被 ~/.zshrc / ~/.bashrc source (不可直接执行)
# 职责: PATH/LD_LIBRARY_PATH/locale/git 别名/通用别名
# @INIT@
_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in
    */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/" ;;
    *) _DIR=. ;;
esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
# @EXPORT@
# export TERM=xterm
# export TERM=xterm-256color
# @@LOCALE@@
# 选择系统可用的 UTF-8 locale（C.UTF-8 优先，缺失时回退 en_US.UTF-8），避免 setlocale 警告
# 已生效 UTF-8 LANG 时跳过检测（省 4 个子进程）; 检测仅一次 grep, 免 sort/head
case "${LANG:-}" in
*[Uu][Tt][Ff]8*|*[Uu][Tt][Ff]-8*)
    : ;;
*)
    _loc_utf8=$(locale -a 2>/dev/null | grep -im1 -E '^(C\.utf8|C\.UTF-8|en_US\.utf8|en_US\.UTF-8)$')
    [ -n "${_loc_utf8}" ] && export LANG="${_loc_utf8}" LC_ALL="${_loc_utf8}"
    unset _loc_utf8
    ;;
esac
# @@OPENMPI@@
# MPI_HOME=/usr/local/openmpi
# export PATH=${MPI_HOME}/bin:${PATH}
# export LD_LIBRARY_PATH=${MPI_HOME}/lib:${LD_LIBRARY_PATH}
# export MPI_INCLUDE_PATH=${MPI_HOME}/include:${MPI_INCLUDE_PATH}
# export MANPATH=${MPI_HOME}/share/man:${MANPATH}
# @@CUDA@@
# CUDA_HOME=/usr/local/cuda
# export PATH=${CUDA_HOME}/bin:${PATH}
# export LD_LIBRARY_PATH=${CUDA_HOME}/lib:${LD_LIBRARY_PATH}
# export CUDA_INCLUDE_PATH=${CUDA_HOME}/include:${CUDA_INCLUDE_PATH}
# export MANPATH=${CUDA_HOME}/share/man:${MANPATH}
# @@PATH@@
# 防重复: 已含仓库 bin 前缀则跳过（env.sh 可能被多次 source，避免 PATH 无限拼接）
case ":${PATH}:" in
*":${_PATH}/bin:"*) : ;;
*) export PATH=${_PATH}/bin:${HOME}/.local/bin:${HOME}/sbin:${HOME}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH} ;;
esac
# @@LD_LIBRARY_PATH@@
# 防重复: 已含仓库 lib 前缀则跳过
case ":${LD_LIBRARY_PATH}:" in
*":${_PATH}/lib:"*) : ;;
*) export LD_LIBRARY_PATH=${_PATH}/lib:${HOME}/.local/lib:${HOME}/slib:${HOME}/lib:/usr/local/lib:/usr/lib:/usr/lib64:/usr/libx32:/usr/lib32:/lib:/lib64:/libx32:/lib32:${LD_LIBRARY_PATH} ;;
esac
# @ALIAS@
alias ...=../..
alias ....=../../..
alias .....=../../../..
alias ......=../../../../..
alias 1='cd -1'
alias 2='cd -2'
alias 3='cd -3'
alias 4='cd -4'
alias 5='cd -5'
alias 6='cd -6'
alias 7='cd -7'
alias 8='cd -8'
alias 9='cd -9'
alias _='sudo '
alias egrep='grep -E --color=auto --exclude-dir={.bzr,CVS,.git,.hg,.svn,.idea,.tox}'
alias fgrep='grep -F --color=auto --exclude-dir={.bzr,CVS,.git,.hg,.svn,.idea,.tox}'
alias grep='grep --color=auto --exclude-dir={.bzr,CVS,.git,.hg,.svn,.idea,.tox}'
# @GIT_ALIASES@
source "${_PATH}/lib/_git_aliases.sh"
# ls 系（修正原 --color=tty 非法选项为 --color=auto; 两 shell 通用）
alias ls='ls --color=auto'
alias l='ls -lah'
alias ll='ls -lh'
alias la='ls -lAh'
alias lsa='ls -lah'
alias md='mkdir -p'
alias rd='rmdir'
# 通用增强
alias df='df -h'
alias du='du -h'
alias free='free -h'
alias path='echo -e ${PATH//:/\\n}'
# 常用工具
alias v='vim'
alias python='python3'
alias pip='pip3'
alias py='python'
alias clc='clear'
alias gsize='git count-objects -vH'
alias gcat-tag='git for-each-ref --sort=-creatordate --count=10 --format="tag: %(refname:short)%0aobject: %(objecttype) %(objectname)%0apeeled: %(*objecttype) %(*objectname)%0atagger: %(taggername) %(taggeremail)%0ataggerdate: %(taggerdate:iso-strict)%0acreatordate: %(creatordate:iso-strict)%0atag-subject: %(subject)%0aauthor: %(*authorname) %(*authoremail)%0aauthordate: %(*authordate:iso-strict)%0acommitter: %(*committername) %(*committeremail)%0acommitterdate: %(*committerdate:iso-strict)%0acommit-subject: %(*subject)%0amessage:%0a%(contents)%0a---%1f" refs/tags | awk '\''BEGIN { RS=sprintf("%c", 31) } $0 !~ /^\n?$/ { n++; record[n]=$0 } END { for (i=n; i>=1; i--) { sub(/^\n/, "", record[i]); print record[i] } }'\'''
alias gback-tag='git fetch origin --tags --force'
alias his='history | tail'
alias ohmyzsh='${EDITOR:-vim} ~/.oh-my-zsh'
alias zshconfig='${EDITOR:-vim} ~/.zshrc'
# zsh/oh-my-zsh 专有（bash 下不定义, 避免覆盖内置 history/whence 语义）
if [ -n "${ZSH_VERSION}" ]; then
    alias history='omz_history'
    alias which-command='whence'
fi
# @@ZHANGXIN@@
# alias nvvp='nvvp -vm /usr/lib/jvm/java-8-openjdk-amd64/jre/bin/java'
alias nv-smi='nvidia-smi -l 1'
# nvtop 异常退出后 10 秒自动重启；正常退出或 Ctrl-C 时结束
_nnvtop_restart() {
    local _nnvtop_status
    while true; do
        command nvtop "$@"
        _nnvtop_status=$?
        case "${_nnvtop_status}" in
        0 | 130) return "${_nnvtop_status}" ;;
        esac
        printf 'nnvtop: nvtop 异常退出（状态码 %s），10 秒后重启；按 Ctrl-C 停止。\n' "${_nnvtop_status}" >&2
        sleep 10
        _nnvtop_status=$?
        [ "${_nnvtop_status}" -eq 0 ] || return "${_nnvtop_status}"
    done
}
alias nnvtop='_nnvtop_restart'
alias get_files_types="find . -type f -printf '%f\n' | sed -n 's/.*\.\([^.]*\)$/\1/p' | sort -u"
get_git_files_types() {
  while IFS= read -r -d '' f; do
    b=${f##*/}
    [[ $b == *.* && $b != .* ]] && printf '%s\n' "${b##*.}"
  done < <(git ls-files -co --exclude-standard -z) | sort -u
}
# ===== get_soft_links: 递归列出软链接（带指向与高亮） =====
# 用法: get_soft_links [路径]        # 默认 .
# 配色参考 fd -t l：链接青色加粗；目标黄色；断链红色
# 完全自包含；readlink 不可用或失败时逐级兜底到 ls / python3 / perl
# zsh 5+ / bash 4+ 通用；非 TTY 自动关闭颜色
get_soft_links() {
    local root_dir="${1:-.}"
    if [[ ! -d "$root_dir" ]]; then
        printf 'get_soft_links: not a directory: %s\n' "$root_dir" >&2
        return 1
    fi

    # ---- 颜色：仅 TTY 启用 ----
    local use_color=0
    [[ -t 1 ]] && use_color=1
    local C_LINK='' C_ARROW='' C_TARGET='' C_BROKEN='' C_RESET=''
    if (( use_color )); then
        C_LINK=$'\033[1;36m'    # 青加粗（fd symlink 默认）
        C_ARROW=$'\033[0;37m'   # 白
        C_TARGET=$'\033[0;33m'  # 黄
        C_BROKEN=$'\033[1;31m'  # 红加粗
        C_RESET=$'\033[0m'
    fi

    # ---- 收集软链接（不依赖 find，且不进入目录链接） ----
    local -a links=() pending=("$root_dir")
    local current_dir entry link
    local pending_index=0 pending_count=1 array_base=0
    [[ -z "${ZSH_VERSION:-}" ]] || setopt localoptions nullglob
    [[ -z "${ZSH_VERSION:-}" ]] || array_base=1
    while (( pending_index < pending_count )); do
        current_dir="${pending[pending_index + array_base]}"
        pending_index=$((pending_index + 1))
        for entry in "$current_dir"/* "$current_dir"/.[!.]* "$current_dir"/..?*; do
            [[ -e "$entry" || -L "$entry" ]] || continue
            if [[ -L "$entry" ]]; then
                links+=("$entry")
            elif [[ -d "$entry" ]]; then
                case "${entry##*/}" in
                    .git | node_modules) continue ;;
                esac
                pending+=("$entry")
                pending_count=$((pending_count + 1))
            fi
        done
    done

    # ---- 收集可用读取器（单个读取器失败时继续尝试下一个） ----
    # 优先级: readlink → ls -ld 解析 → python3 → perl
    local -a readers=()
    local reader reader_name reader_path
    for reader_name in readlink ls python3 perl; do
        if [[ -n "${ZSH_VERSION:-}" ]]; then
            reader_path=$(whence -p "$reader_name" 2>/dev/null) || reader_path=''
        else
            reader_path=$(type -P "$reader_name" 2>/dev/null) || reader_path=''
        fi
        if [[ -n "$reader_path" && -x "$reader_path" ]]; then
            readers+=("$reader_name")
        fi
    done

    # ---- 遍历 ----
    local count=0 broken=0 target out reader_input
    for link in "${links[@]}"; do
        case "$link" in
            /*) reader_input=$link ;;
            *)  reader_input="./$link" ;;
        esac

        target=''
        for reader in "${readers[@]}"; do
            case "$reader" in
                readlink)
                    target=$(command readlink "$reader_input" 2>/dev/null) || target='' ;;
                ls)
                    out=$(command ls -ld "$reader_input" 2>/dev/null) || out=''
                    case "$out" in
                        *" -> "*) target="${out#* -> }" ;;
                        *)        target='' ;;
                    esac ;;
                python3)
                    target=$(command python3 -c 'import os,sys;sys.stdout.write(os.readlink(sys.argv[1]))' "$reader_input" 2>/dev/null) || target='' ;;
                perl)
                    target=$(command perl -e 'print readlink($ARGV[0])' "$reader_input" 2>/dev/null) || target='' ;;
            esac
            [[ -n "$target" ]] && break
        done
        [[ -n "$target" ]] || target='?'

        if [[ -e "$link" ]]; then
            printf '%s%s%s %s->%s %s%s%s\n' \
                "$C_LINK" "$link" "$C_RESET" \
                "$C_ARROW" "$C_RESET" \
                "$C_TARGET" "$target" "$C_RESET"
        else
            printf '%s%s%s %s->%s %s%s%s %s[broken]%s\n' \
                "$C_LINK" "$link" "$C_RESET" \
                "$C_ARROW" "$C_RESET" \
                "$C_BROKEN" "$target" "$C_RESET" \
                "$C_BROKEN" "$C_RESET"
            broken=$((broken + 1))
        fi
        count=$((count + 1))
    done

    # ---- 汇总（走 stderr，不污染可解析 stdout） ----
    if (( use_color )); then
        printf '%s%d%s symlink(s)' "$C_LINK" "$count" "$C_RESET" >&2
        (( broken > 0 )) && printf ', %s%d broken%s' "$C_BROKEN" "$broken" "$C_RESET" >&2
        printf '\n' >&2
    else
        printf '%d symlink(s)' "$count" >&2
        (( broken > 0 )) && printf ', %d broken' "$broken" >&2
        printf '\n' >&2
    fi
}

# ===== get_git_large_files: 审计当前 Git 仓库历史中的大文件 =====
# 用法: get_git_large_files
# 范围: 当前仓库所有 ref 可达提交中的文件版本（含已删除文件）
# 着色: (1, 5] MiB 蓝色；(5, 10] MiB 黄色；> 10 MiB 红色
# GET_GIT_LARGE_FILES_COLOR=auto|always|never，默认 auto
get_git_large_files() (
    local temp_dir=''
    trap '[[ -z "${temp_dir:-}" ]] || rm -rf -- "$temp_dir"' EXIT
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM

    if ! git rev-parse --git-dir >/dev/null 2>&1; then
        printf 'get_git_large_files: 当前目录不在 Git 仓库中\n' >&2
        return 1
    fi

    local repo_root
    repo_root=$(git rev-parse --show-toplevel 2>/dev/null) ||
        repo_root=$(git rev-parse --git-dir 2>/dev/null)

    local use_color=0 color_mode=${GET_GIT_LARGE_FILES_COLOR:-auto}
    case "$color_mode" in
        always) use_color=1 ;;
        never)  use_color=0 ;;
        auto)   [[ -t 1 ]] && use_color=1 ;;
        *)
            printf 'get_git_large_files: 未知颜色模式 %s（应为 auto/always/never）\n' \
                "$color_mode" >&2
            return 1
            ;;
    esac
    [[ -z "${NO_COLOR:-}" || "$color_mode" == always ]] || use_color=0

    if [[ -z "$(git for-each-ref --format='%(objectname)' refs 2>/dev/null | head -n 1)" ]]; then
        printf 'Git 仓库: %s\n' "$repo_root"
        printf '未发现历史大文件：仓库中没有可用 ref 或提交。\n'
        return 0
    fi

    temp_dir=$(mktemp -d "${TMPDIR:-/tmp}/configure-git-large-files.XXXXXX") || {
        printf 'get_git_large_files: 无法创建临时目录\n' >&2
        return 1
    }
    local history_file=$temp_dir/history.bin
    local occurrences_file=$temp_dir/occurrences.tsv
    local unique_file=$temp_dir/occurrences-unique.tsv
    local objects_file=$temp_dir/objects.tsv
    local sized_file=$temp_dir/sized.tsv
    local sorted_file=$temp_dir/sorted.tsv

    if ! LC_ALL=C git log --all --raw --root -m --no-renames --no-abbrev -z \
        --format='C%H%x00' >"$history_file"; then
        printf 'get_git_large_files: 读取 Git 历史失败\n' >&2
        return 1
    fi

    local current_commit='' token file_path meta
    local old_mode new_mode old_oid new_oid change_status
    while IFS= read -r -d '' token; do
        token=${token#$'\n'}
        case "$token" in
            C*)
                current_commit=${token#C}
                ;;
            :*)
                IFS= read -r -d '' file_path || break
                meta=${token#:}
                read -r old_mode new_mode old_oid new_oid change_status <<<"$meta"
                [[ -n "$new_oid" && "$new_oid" == *[!0]* ]] || continue
                printf '%s\t%s\t%s\n' "$new_oid" "$current_commit" "$file_path"
                ;;
        esac
    done <"$history_file" >"$occurrences_file"

    if ! LC_ALL=C sort -u "$occurrences_file" >"$unique_file"; then
        printf 'get_git_large_files: 去重历史文件版本失败\n' >&2
        return 1
    fi

    local cat_format=$'%(objectname)\t%(objecttype)\t%(objectsize)\t%(rest)'
    if ! git cat-file --batch-check="$cat_format" <"$unique_file" >"$objects_file"; then
        printf 'get_git_large_files: 读取 Git 对象信息失败\n' >&2
        return 1
    fi

    local one_mib=1048576 five_mib=5242880 ten_mib=10485760
    local oid object_type object_size rest commit
    while IFS=$'\t' read -r oid object_type object_size rest; do
        [[ "$object_type" == blob ]] || continue
        (( object_size > one_mib )) || continue
        commit=${rest%%$'\t'*}
        file_path=${rest#*$'\t'}
        printf '%s\t%s\t%s\t%s\n' "$file_path" "$oid" "$object_size" "$commit"
    done <"$objects_file" >"$sized_file"

    if ! LC_ALL=C sort -u -t $'\t' -k1,1 -k3,3nr -k4,4 \
        "$sized_file" >"$sorted_file"; then
        printf 'get_git_large_files: 排序历史文件版本失败\n' >&2
        return 1
    fi

    local C_BLUE='' C_YELLOW='' C_RED='' C_RESET=''
    if (( use_color )); then
        C_BLUE=$'\033[34m'
        C_YELLOW=$'\033[33m'
        C_RED=$'\033[31m'
        C_RESET=$'\033[0m'
    fi

    printf 'Git 仓库: %s\n' "$repo_root"
    printf '历史大文件（1 MiB = 1048576 字节）\n'
    printf '大小标记: >1–5 MiB 蓝色 | >5–10 MiB 黄色 | >10 MiB 红色\n'

    local branch_names tag_names filename human_size
    local size_color='' count=0
    while IFS=$'\t' read -r file_path oid object_size commit; do
        branch_names=$(LC_ALL=C git for-each-ref --contains "$commit" \
            --format='%(refname:short)' refs/heads refs/remotes 2>/dev/null |
            awk '$0 !~ /\/HEAD$/ { printf "%s%s", separator, $0; separator="," }')
        tag_names=$(LC_ALL=C git tag --contains "$commit" 2>/dev/null |
            awk '{ printf "%s%s", separator, $0; separator="," }')
        [[ -n "$branch_names" ]] || branch_names='-'
        [[ -n "$tag_names" ]] || tag_names='-'

        filename=${file_path##*/}
        human_size=$(printf '%d.%02d MiB (%d bytes)' \
            "$((object_size / one_mib))" \
            "$(((object_size % one_mib) * 100 / one_mib))" \
            "$object_size")

        size_color=$C_RED
        (( object_size > ten_mib )) || {
            size_color=$C_YELLOW
            (( object_size > five_mib )) || size_color=$C_BLUE
        }

        printf '分支=[%s] 标签=[%s] 提交=[%s] 路径=[%s] 文件名=[%s] 大小=[%s%s%s] 哈希=[%s]\n' \
            "$branch_names" "$tag_names" "$commit" "$file_path" "$filename" \
            "$size_color" "$human_size" "$C_RESET" "$oid"
        count=$((count + 1))
    done <"$sorted_file"

    if (( count == 0 )); then
        printf '未发现大于 1 MiB 的历史文件版本。\n'
    else
        printf '共 %d 个历史大文件版本（> 1 MiB）。\n' "$count"
    fi
)
