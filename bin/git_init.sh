#!/usr/bin/env bash
# Git 初始化脚本
# 功能: 配置 git 用户名/邮箱, 生成 ed25519 SSH 密钥, 打印公钥
# 用法: 将打印的公钥添加到 Gitee / GitHub 后, 执行 ssh -T git@gitee.com 验证

_PATH=$(
    cd "$(dirname "$0")"
    pwd
)
_NAME=$(basename "$0")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
git config --global user.name "zhangxin"
git config --global user.email "zhangxin8069@qq.com"
ssh-keygen -t ed25519 -C "zhangxin8069@qq.com"
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519

cat << 'USAGE'

  ┌──────────────────────────────────────────────────────────────┐
  │                   Git 初始化 — 公钥                          │
  ├──────────────────────────────────────────────────────────────┤
  │                                                              │
  │  git user : zhangxin                                         │
  │  git email: zhangxin8069@qq.com                              │
  │  key type : ed25519                                          │
  │  key path : ~/.ssh/id_ed25519                                │
  │                                                              │
  └──────────────────────────────────────────────────────────────┘
USAGE

echo -e "id_ed25519.pub:\n"
cat ~/.ssh/id_ed25519.pub

cat << 'USAGE2'

  ┌──────────────────────────────────────────────────────────────┐
  │                                                              │
  │  将上方公钥添加到 Git 平台:                                  │
  │                                                              │
  │    Gitee:  https://gitee.com/profile/sshkeys                 │
  │    GitHub: https://github.com/settings/keys                  │
  │                                                              │
  │  验证连接:                                                   │
  │    ssh -T git@gitee.com                                      │
  │    ssh -T git@github.com                                     │
  │                                                              │
  │  常用 git alias (由 env.sh 提供):                            │
  │    gpush.sh   推送到 origin/main                             │
  │    gpull.sh   从 origin 拉取                                 │
  │    gback.sh   创建备份分支                                   │
  │    gls.sh     列出所有 git 仓库                              │
  │    gsize      查看仓库大小                                   │
  │                                                              │
  └──────────────────────────────────────────────────────────────┘
USAGE2

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
