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
# 别名捕获（alias 不跨进程传递，子进程拿不到父 shell 的别名）：
#   方式一（推荐）：父 shell 先导出别名文件，再传路径
#     bash:  alias -p > /tmp/aliases.txt && SAVE_ENV_ALIASES_FILE=/tmp/aliases.txt bash save-env.sh
#     zsh:   alias -L > /tmp/aliases.txt && SAVE_ENV_ALIASES_FILE=/tmp/aliases.txt bash save-env.sh
#   方式二：source 运行脚本（source save-env.sh 时能取到当前 shell 别名）
#   方式三：直接 bash 运行——自动从父 shell（zsh/bash）交互模式捕获别名
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

# 输出别名段：优先取 SAVE_ENV_ALIASES_FILE（父 shell 预导出）；否则从父 shell 交互模式
# 捕获（zsh -i 'alias -L' / bash -ic 'alias -p'，alias 不跨进程传递，只能另起交互 shell 取）；
# 父 shell 未知时回退脚本自身 alias -p。只收普通别名（^alias name=...），
# 跳过 zsh 全局别名（alias -g）、特殊名字（alias -- -、alias ...）与启动噪音
emit_aliases() {
  local -a lines
  local line
  if [[ -n "${SAVE_ENV_ALIASES_FILE:-}" && -f "${SAVE_ENV_ALIASES_FILE}" ]]; then
    mapfile -t lines < "${SAVE_ENV_ALIASES_FILE}"
  else
    case "$(ps -o comm= -p "$PPID" 2>/dev/null || true)" in
      *zsh)  mapfile -t lines < <(zsh -i -c 'alias -L' 2>/dev/null) ;;
      *bash) mapfile -t lines < <(bash -ic 'alias -p' 2>/dev/null) ;;
      *)     mapfile -t lines < <(alias -p) ;;
    esac
  fi
  for line in "${lines[@]}"; do
    [[ "$line" =~ ^alias[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)= ]] && printf '%s\n' "$line"
  done
}

# 主流程：读 env，跳过不想要的，转义单引号后重新写出（纯内置，无子进程）
while IFS= read -r -d '' entry; do
  name="${entry%%=*}"
  # 跳过非合法标识符的名字（如 bash 导出的函数 BASH_FUNC_module()=...），函数无法跨 shell 传递
  [[ "$name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
  skip_var "$name" && continue
  printf "export '%s'\n" "${entry//\'/\'\\\'\'}"
done < <(env -0 | sort -z) > "$OUT"

# 别名段（空则整体省略）
ALIASES_OUT="$(emit_aliases)"
if [[ -n "$ALIASES_OUT" ]]; then
  echo "" >> "$OUT"
  echo "# --- aliases ---" >> "$OUT"
  printf '%s\n' "$ALIASES_OUT" >> "$OUT"
fi

VAR_COUNT=$(grep -c '^export ' "$OUT" || true)
ALIAS_COUNT=$(grep -c '^alias [A-Za-z_][A-Za-z0-9_]*=' "$OUT" || true)
echo "已写入 $OUT，共 $VAR_COUNT 个变量、$ALIAS_COUNT 个别名"
echo "恢复方法： source $OUT"
