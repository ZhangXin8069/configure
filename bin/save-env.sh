#!/usr/bin/env bash
# ============================================================
# save-env.sh — 把当前环境导出为可 source 的 .env.sh
# 过滤掉 shell 内部 / 只读 / 每次变化无常的变量（如 _、SHLVL、UID）
# 以及 bash 导出的函数项（BASH_FUNC_module()=...）
#
# 用法：
#   bash save-env.sh                     # 输出到 ./.env.sh
#   bash save-env.sh myenv.sh TERM       # 输出 myenv.sh，并额外跳过 TERM
#
# 恢复：source .env.sh
# ============================================================

set -euo pipefail

OUT="${1:-.env.sh}"

# 默认跳过的变量：
#   _ UID EUID ...    只读特殊变量，source 会报错
#   SHLVL SECONDS ... source 会变 / 没有意义
#   PWD OLDPWD ...    目录状态，不该被快照覆盖
#   BASH_* SHELLOPTS  各 shell 内部变量，恢复无意义
#   HOSTNAME OSTYPE   系统信息
SKIP_PATTERN='_|SHLVL|PWD|OLDPWD|UID|EUID|GID|EGID|PPID|RANDOM|SECONDS|LINENO|BASHPID|BASHOPTS|SHELLOPTS|FUNCNAME|GROUPS|BASH_VERSION|BASH_VERSINFO|BASH_ARGV0|BASH_ARGV|BASH_ARGC|BASH_SOURCE|BASH_LINENO|BASH_COMMAND|BASH_SUBSHELL|BASH_EXECUTION_STRING|HOSTNAME|HOSTTYPE|MACHTYPE|OSTYPE|ZSH_VERSION|ZSH_ARGZERO'

# 命令行里额外指定的变量（如 TERM、DISPLAY）
EXTRA_PATTERN="$(IFS='|'; echo "${*:2}")"

# 变量名是否应被跳过
skip_var() {
  [[ "$1" =~ ^(${SKIP_PATTERN}|${EXTRA_PATTERN})$ ]]
}

# 把 "NAME=value" 包成单引号，内部 ' 转义为 '\''，bash/zsh 都能 source
shell_quote() {
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

# 主流程：读 env，跳过不想要的，重新加引号写出
while IFS= read -r -d '' entry; do
  name="${entry%%=*}"
  # 跳过非合法标识符的名字（如 bash 导出的函数 BASH_FUNC_module()=...），函数无法跨 shell 传递
  [[ "$name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
  skip_var "$name" && continue
  printf 'export %s\n' "$(shell_quote "$entry")"
done < <(env -0 | sort -z) > "$OUT"

echo "已写入 $OUT，共 $(grep -c '^export ' "$OUT") 个变量"
echo "恢复方法： source $OUT"
