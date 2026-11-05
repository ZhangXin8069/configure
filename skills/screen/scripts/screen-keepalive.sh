#!/bin/bash
# screen-keepalive.sh — 强制后台保活：每 interval 秒向指定 screen 会话注入一次 ls
# 仅在「会话 Attached + 画面静态 + 末行为提示符」时注入；锁被占用或闸门失败时跳过并记录。
set -u

SNAME=""
interval=20
lock=""
activity=""
logf=""
pidfile=""
stopfile=""

usage() {
  cat <<'EOF'
usage: screen-keepalive.sh --session NAME [options]
  --session NAME    目标 screen 会话名（必填）
  --interval SEC    保活间隔（默认 20，须 <30）
  --lock FILE       共享会话锁（可选；非阻塞获取，占用则跳过本轮）
  --activity FILE   活动心跳文件（可选；mtime 在 interval 内则跳过）
  --log FILE        日志文件（可选）
  --pidfile FILE    PID 文件（可选）
  --stopfile FILE   停止标志文件（可选；出现即退出）
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --session) SNAME="${2:-}"; shift 2 ;;
    --interval) interval="${2:-}"; shift 2 ;;
    --lock) lock="${2:-}"; shift 2 ;;
    --activity) activity="${2:-}"; shift 2 ;;
    --log) logf="${2:-}"; shift 2 ;;
    --pidfile) pidfile="${2:-}"; shift 2 ;;
    --stopfile) stopfile="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage >&2; exit 64 ;;
  esac
done

[ -n "$SNAME" ] || { usage >&2; exit 64; }
case "$interval" in ''|*[!0-9]*) echo "--interval 必须是整数" >&2; exit 64 ;; esac
[ "$interval" -lt 30 ] || { echo "--interval 必须 <30（保活硬性要求）" >&2; exit 64; }

TMP=$(mktemp -d "${TMPDIR:-/tmp}/screen-keepalive.XXXXXX") || exit 70
cleanup() { rc=$?; rm -rf -- "$TMP" 2>/dev/null; [ -n "$pidfile" ] && rm -f -- "$pidfile"; return "$rc"; }
trap 'cleanup' EXIT INT TERM HUP
[ -n "$pidfile" ] && printf '%s\n' "$$" > "$pidfile"

log() { [ -n "$logf" ] && printf '%s %s\n' "$(date '+%F %T')" "$*" >> "$logf"; return 0; }

nap() {
  local n=$1
  while [ "$n" -gt 0 ]; do
    if [ -n "$stopfile" ] && [ -f "$stopfile" ]; then return 1; fi
    sleep 1
    n=$((n - 1))
  done
  return 0
}

gate() {
  local a="$TMP/g1" b="$TMP/g2" last
  screen -S "$SNAME" -X hardcopy "$a" 2>/dev/null || return 2
  sleep 2
  screen -S "$SNAME" -X hardcopy "$b" 2>/dev/null || return 2
  cmp -s "$a" "$b" || return 3
  last=$(tr -d '\000' < "$b" | sed -e 's/[[:space:]]*$//' | grep -v '^$' | tail -1)
  case "$last" in *'$'|*'#'|*'%'|*'>') return 0;; *) return 4;; esac
}

log "start pid=$$ session=$SNAME interval=$interval"
while :; do
  if [ -n "$stopfile" ] && [ -f "$stopfile" ]; then log "stop requested"; break; fi

  if [ -n "$activity" ] && [ -f "$activity" ]; then
    now=$(date +%s); mt=$(stat -c %Y "$activity" 2>/dev/null || echo 0)
    if [ $((now - mt)) -lt "$interval" ]; then nap 5 || break; continue; fi
  fi

  if [ -n "$lock" ]; then
    exec 9>>"$lock" || { log "lock open failed"; nap 5 || break; continue; }
    if ! flock -n 9; then exec 9>&-; log "lock busy, skip"; nap 5 || break; continue; fi
  fi

  if gate; then
    screen -S "$SNAME" -X stuff "ls"
    screen -S "$SNAME" -X stuff "$(printf '\r')"
    log "inject ls"
  else
    log "gate failed rc=$?, skip (background 不自动清除阻塞)"
  fi

  [ -n "$lock" ] && exec 9>&-
  nap "$interval" || break
done
log "exit pid=$$"
exit 0
