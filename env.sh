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
*) export PATH=${_PATH}/bin:${HOME}/.opencode/bin:${HOME}/.local/bin:${HOME}/sbin:${HOME}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH} ;;
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
source ${_PATH}/lib/_git_aliases.sh
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
