#!/usr/bin/env bash
# Shell 终端配置脚本
# 功能: 备份 ~/.bashrc ~/.zshrc ~/.oh-my-zsh, 部署新版 (从 lib/ 复制)
# 主题: robbyrussell + zsh-syntax-highlighting + zsh-autosuggestions
# 启动: .zshrc → ~/configure/env.sh → tmp/scripts.sh → 51 个 alias

_PATH=$(
    cd "$(dirname "$0")"
    pwd
)
_NAME=$(basename "$0")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
pushd ~
mkdir -p .oh-my-zsh
mv ./.bashrc .bashrc."$(date "+%Y-%m-%d-%H-%M-%S")".bak 2>/dev/null
mv ./.zshrc .zshrc."$(date "+%Y-%m-%d-%H-%M-%S")".bak 2>/dev/null
mv .oh-my-zsh .oh-my-zsh."$(date "+%Y-%m-%d-%H-%M-%S")".bak 2>/dev/null
# 首次安装 oh-my-zsh (取消注释以下两行):
# apt install zsh wget
# sh -c "$(wget https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh -O -)"
cp -r ${_PATH}/../lib/_bashrc .bashrc
cp -r ${_PATH}/../lib/_zshrc .zshrc
cp -r ${_PATH}/../lib/_oh-my-zsh .oh-my-zsh
popd

cat << 'USAGE'

  ┌──────────────────────────────────────────────────────────────┐
  │                  Shell 终端配置 — 使用说明                  │
  ├──────────────────────────────────────────────────────────────┤
  │                                                              │
  │  启动链                                                      │
  │    .zshrc  →  ~/configure/env.sh  →  tmp/scripts.sh        │
  │    自动生成 51 个 alias, 加载 git 别名和 env 变量            │
  │                                                              │
  │  oh-my-zsh                                                   │
  │    主题: robbyrussell                                        │
  │    插件: git, z, zsh-syntax-highlighting,                    │
  │          zsh-autosuggestions, you-should-use                 │
  │                                                              │
  │  常用 alias (自动生成)                                       │
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
