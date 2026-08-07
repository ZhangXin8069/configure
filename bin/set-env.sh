#!/usr/bin/env bash
# ============================================================
# set-env.sh — 一键初始化 / 恢复 shell 环境
#
# 注意：本脚本必须 source 执行，因为它要为「当前 shell」设置环境变量；
#       直接运行（子进程）会丢掉所有环境变量，毫无意义。
#   用法： source ~/configure/bin/set-env.sh
#       或  . ~/configure/bin/set-env.sh
#
# 顺序：
#   0. source ~/.bashrc
#   1. source ~/.env.sh（不存在则在 $HOME 下调用 save-env.sh 生成）
#   2. source ~/configure/env.sh
#   3. source ~/env.sh
# ============================================================

_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

# ---------- 0. source ~/.bashrc ----------
if [[ -f "${HOME}/.bashrc" ]]; then
  source "${HOME}/.bashrc"
else
  echo ">>> 未找到 ${HOME}/.bashrc，跳过"
fi

# ---------- 1. source ~/.env.sh；不存在则用 save-env.sh 生成 ----------
if [[ -f "${HOME}/.env.sh" ]]; then
  source "${HOME}/.env.sh"
else
  echo ">>> 未找到 ${HOME}/.env.sh，在 \$HOME 下调用 save-env.sh 生成..."
  # save-env.sh 默认把 .env.sh 写到「当前目录」，故 pushd 到 $HOME，运行后 popd 还原
  pushd "${HOME}" >/dev/null
  bash "${HOME}/configure/bin/save-env.sh"
  popd >/dev/null
  if [[ -f "${HOME}/.env.sh" ]]; then
    source "${HOME}/.env.sh"
  else
    echo ">>> save-env.sh 生成失败，跳过 ~/.env.sh"
  fi
fi

# ---------- 2. source ~/configure/env.sh ----------
if [[ -f "${HOME}/configure/env.sh" ]]; then
  source "${HOME}/configure/env.sh"
else
  echo ">>> 未找到 ${HOME}/configure/env.sh，跳过"
fi

# ---------- 3. source ~/env.sh ----------
if [[ -f "${HOME}/env.sh" ]]; then
  source "${HOME}/env.sh"
else
  echo ">>> 未找到 ${HOME}/env.sh，跳过"
fi

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
