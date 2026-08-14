#!/usr/bin/env bash
# Shell 终端配置脚本
# 功能: 备份 ~/.bashrc ~/.zshrc ~/.oh-my-zsh, 从 lib/ 部署新版
# 用法: sh_init.sh [-b|-z|-a]
#   -b  仅部署 bashrc
#   -z  部署 zshrc 与 oh-my-zsh (默认)
#   -a  全部部署
# 启动链: ~/.zshrc → ~/configure/env.sh → bin/ 进 PATH → 命令直调
set -euo pipefail

_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

mode=z
while getopts "bza" opt; do
    case "$opt" in
    b) mode=b ;;
    z) mode=z ;;
    a) mode=a ;;
    *) echo "用法: ${_NAME} [-b|-z|-a]  (b=bashrc, z=zshrc+oh-my-zsh, a=全部; 默认 z)" >&2
       exit 1 ;;
    esac
done

# 备份旧目标(带时间戳)并部署新版本
deploy()
{
    local src=$1 dst=$2
    if [ -e "$dst" ]; then
        mv "$dst" "$dst.$(date "+%Y-%m-%d-%H-%M-%S").bak"
    fi
    cp -r "$src" "$dst"
}

if [[ $mode == b || $mode == a ]]; then
    deploy "${_PATH}/../lib/_bashrc" "${HOME}/.bashrc"
fi

if [[ $mode == z || $mode == a ]]; then
    if command -v zsh >/dev/null 2>&1; then
        deploy "${_PATH}/../lib/_zshrc" "${HOME}/.zshrc"
    else
        echo "警告: 未安装 zsh (apt install zsh wget), 跳过 .zshrc 部署" >&2
    fi
    if [ -d "${_PATH}/../lib/_oh-my-zsh" ]; then
        deploy "${_PATH}/../lib/_oh-my-zsh" "${HOME}/.oh-my-zsh"
    else
        echo "警告: lib/_oh-my-zsh 缺失, 跳过; 可手动官方安装:" >&2
        echo "  sh -c \"\$(wget https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh -O -)\"" >&2
    fi
fi

cat << 'USAGE'

  ┌──────────────────────────────────────────────────────────────┐
  │                  Shell 终端配置 — 使用说明                   │
  ├──────────────────────────────────────────────────────────────┤
  │                                                              │
  │  启动链                                                      │
  │    .zshrc / .bashrc  →  ~/configure/env.sh → bin/ 进 PATH    │
  │    bin/ 下命令直接按名调用, 加载 git 别名和 env 变量         │
  │                                                              │
  │  oh-my-zsh                                                   │
  │    主题: robbyrussell                                        │
  │    插件: git, zsh-syntax-highlighting,                       │
  │          zsh-autosuggestions, you-should-use                 │
  │                                                              │
  │  常用命令 (bin/ 直调)                                        │
  │    gpush.sh / gpull.sh   Git 推送/拉取                       │
  │    gback.sh              Git 分支备份                        │
  │    gls.sh                Git 仓库列表                        │
  │    gzALLpush.sh          推送所有 repo                       │
  │    ssub.sh / ssqueue.sh  Slurm 作业管理                      │
  │    zipython.sh           IPython 启动                        │
  │    zjulab.sh             Jupyter Lab 启动                    │
  │    vim_init.sh           Vim 配置部署                        │
  │    l / ll / la           ls 增强                             │
  │    md                    mkdir -p                            │
  │    py                    python3                             │
  │    cl                    claude                              │
  │    his                   history 最近记录                    │
  │                                                              │
  │  生效                                                        │
  │    新终端自动生效, 或执行: source ~/.zshrc                   │
  │                                                              │
  └──────────────────────────────────────────────────────────────┘
USAGE

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
