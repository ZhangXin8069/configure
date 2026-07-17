#!/usr/bin/env bash
# @INIT@
_PATH=$(
    cd "$(dirname "${BASH_SOURCE[0]:-$0}")"
    pwd
)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is sourcing...:$(date "+%Y-%m-%d-%H-%M-%S")###"
# @MKDIR@
mkdir -p ${_PATH}/bin
mkdir -p ${_PATH}/docs
mkdir -p ${_PATH}/lib
mkdir -p ${_PATH}/scripts
mkdir -p ${_PATH}/tmp
# @SOURCE@
echo "###configure/env.sh is sourced...:$(date "+%Y-%m-%d-%H-%M-%S")###" >>${_PATH}/tmp/scripts.sh
source ${_PATH}/tmp/scripts.sh
# @EXPORT@
# export TERM=xterm-256color
export PATH=${_PATH}/bin:$PATH
export PATH=${HOME}/.local/bin:$PATH
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
alias cl='claude'
alias clc='clear'
alias his='history | tail'
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"