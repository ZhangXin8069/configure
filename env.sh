#!/usr/bin/env bash
# @INIT@
_SRC=${BASH_SOURCE[0]:-$0}
case "$_SRC" in
    */*) _DIR=${_SRC%/*} ;;
    *) _DIR=. ;;
esac
_PATH=$(cd "$_DIR" && pwd)
# @EXPORT@
# export TERM=xterm
# export TERM=xterm-256color
# @@LOCALE@@
# 选择系统可用的 UTF-8 locale（C.UTF-8 优先，缺失时回退 en_US.UTF-8），避免 setlocale 警告
_loc_utf8=$(locale -a 2>/dev/null | grep -iE '^(C\.utf-?8|en_US\.utf-?8)$' | sort | head -1)
[ -n "$_loc_utf8" ] && export LANG="$_loc_utf8" LC_ALL="$_loc_utf8"
unset _loc_utf8
# @@OPENMPI@@
# MPI_HOME=/usr/local/openmpi
# export PATH=${MPI_HOME}/bin:$PATH
# export LD_LIBRARY_PATH=${MPI_HOME}/lib:$LD_LIBRARY_PATH
# export MPI_INCLUDE_PATH=${MPI_HOME}/include:$MPI_INCLUDE_PATH
# export MANPATH=${MPI_HOME}/share/man:$MANPATH
# @@CUDA@@
# CUDA_HOME=/usr/local/cuda
# export PATH=${CUDA_HOME}/bin:$PATH
# export LD_LIBRARY_PATH=${CUDA_HOME}/lib:$LD_LIBRARY_PATH
# export CUDA_INCLUDE_PATH=${CUDA_HOME}/include:$CUDA_INCLUDE_PATH
# export MANPATH=${CUDA_HOME}/share/man:$MANPATH
# @@PATH@@
export PATH=${_PATH}/bin:${HOME}/.opencode/bin:${HOME}/.local/bin:${HOME}/sbin:${HOME}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH
# @@LD_LIBRARY_PATH@@
export LD_LIBRARY_PATH=${HOME}/.local/lib:${HOME}/slib:${HOME}/lib:/usr/local/lib:/usr/lib:/usr/lib64:/usr/libx32:/usr/lib32:/lib:/lib64:/libx32:/lib32:$LD_LIBRARY_PATH
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
alias history='omz_history'
alias l='ls -lah'
alias la='ls -lAh'
alias ll='ls -lh'
alias ls='ls --color=tty'
alias lsa='ls -lah'
alias md='mkdir -p'
alias ohmyzsh='mate ~/.oh-my-zsh'
alias rd='rmdir'
alias which-command='whence'
alias zshconfig='mate ~/.zshrc'
# @@ZHANGXIN@@
# alias nvvp='nvvp -vm /usr/lib/jvm/java-8-openjdk-amd64/jre/bin/java'
alias python='python3'
alias pip='pip3'
alias gsize='git count-objects -vH'
alias py='python'
alias clc='clear'
alias cls='clear'
alias his='history | tail'
