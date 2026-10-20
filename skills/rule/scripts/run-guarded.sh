#!/usr/bin/env bash
set -u
LC_ALL=C

usage() {
  cat <<'EOF'
Usage: run-guarded.sh --label TEXT --timeout DURATION [options] -- command [args...]

Run one command with a hard timeout, periodic heartbeat, and optional progress
freshness detection.

Options:
  --label TEXT             Stable task label for event logs
  --timeout DURATION       Required hard timeout: integer with s/m/h/d suffix
  --heartbeat DURATION     Heartbeat interval (default: 60s)
  --kill-after DURATION    Grace period after TERM before KILL (default: 30s)
  --output-log PATH        Capture command stdout/stderr and append events here
  --event-log PATH         Append structured guard events to this file
  --watch-file PATH        File updated by real task progress or checkpoints
  --stale-after DURATION   Stop when watch file is stale (default: 3 heartbeats)
  -h, --help               Show this help

Tasks with --timeout greater than 600 seconds must provide --output-log or
--watch-file, so a listener can distinguish liveness from real progress.
EOF
}

die() {
  printf 'run-guarded: %s\n' "$*" >&2
  exit 2
}

duration_seconds() {
  local value=$1
  local number unit scale

  case "$value" in
    *[!0-9smhd]*|'') die "invalid duration: $value" ;;
  esac

  case "$value" in
    *s|*m|*h|*d)
      unit=${value: -1}
      number=${value%?}
      ;;
    *)
      unit=s
      number=$value
      ;;
  esac

  [[ $number =~ ^[0-9]+$ ]] || die "invalid duration: $value"
  case "$unit" in
    s) scale=1 ;;
    m) scale=60 ;;
    h) scale=3600 ;;
    d) scale=86400 ;;
  esac
  printf '%s\n' "$((10#$number * scale))"
}

single_line() {
  case "$1" in
    *$'\n'*|*$'\r'*) return 1 ;;
    *) return 0 ;;
  esac
}

regular_or_absent() {
  local path=$1
  [[ ! -L "$path" ]] || die "refusing symlink path: $path"
  [[ ! -e "$path" || -f "$path" ]] || die "path is not a regular file: $path"
}

file_mtime() {
  local path=$1
  stat -c '%Y' "$path" 2>/dev/null || stat -f '%m' "$path" 2>/dev/null
}

LABEL=
TIMEOUT_VALUE=
HEARTBEAT_VALUE=60s
KILL_AFTER_VALUE=30s
OUTPUT_LOG=
EVENT_LOG=
WATCH_FILE=
STALE_AFTER_VALUE=
COMMAND=()

while (($# > 0)); do
  case "$1" in
    --label)
      (($# >= 2)) || die "--label requires a value"
      LABEL=$2
      shift 2
      ;;
    --timeout)
      (($# >= 2)) || die "--timeout requires a value"
      TIMEOUT_VALUE=$2
      shift 2
      ;;
    --heartbeat)
      (($# >= 2)) || die "--heartbeat requires a value"
      HEARTBEAT_VALUE=$2
      shift 2
      ;;
    --kill-after)
      (($# >= 2)) || die "--kill-after requires a value"
      KILL_AFTER_VALUE=$2
      shift 2
      ;;
    --output-log)
      (($# >= 2)) || die "--output-log requires a value"
      OUTPUT_LOG=$2
      shift 2
      ;;
    --event-log)
      (($# >= 2)) || die "--event-log requires a value"
      EVENT_LOG=$2
      shift 2
      ;;
    --watch-file)
      (($# >= 2)) || die "--watch-file requires a value"
      WATCH_FILE=$2
      shift 2
      ;;
    --stale-after)
      (($# >= 2)) || die "--stale-after requires a value"
      STALE_AFTER_VALUE=$2
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      COMMAND=("$@")
      break
      ;;
    *)
      die "unknown argument before --: $1"
      ;;
  esac
done

[[ -n "$LABEL" ]] || die "--label is required"
single_line "$LABEL" || die "--label must be a single line"
[[ -n "$TIMEOUT_VALUE" ]] || die "--timeout is required"
((${#COMMAND[@]} > 0)) || die "command is required after --"

TIMEOUT_SECONDS=$(duration_seconds "$TIMEOUT_VALUE")
HEARTBEAT_SECONDS=$(duration_seconds "$HEARTBEAT_VALUE")
KILL_AFTER_SECONDS=$(duration_seconds "$KILL_AFTER_VALUE")
((TIMEOUT_SECONDS > 0)) || die "--timeout must be greater than zero"
((HEARTBEAT_SECONDS > 0)) || die "--heartbeat must be greater than zero"
((KILL_AFTER_SECONDS > 0)) || die "--kill-after must be greater than zero"

if [[ -n "$WATCH_FILE" ]]; then
  regular_or_absent "$WATCH_FILE"
elif [[ -n "$OUTPUT_LOG" ]]; then
  WATCH_FILE=$OUTPUT_LOG
fi

if [[ -n "$STALE_AFTER_VALUE" ]]; then
  [[ -n "$WATCH_FILE" ]] || die "--stale-after requires --watch-file or --output-log"
  STALE_AFTER_SECONDS=$(duration_seconds "$STALE_AFTER_VALUE")
  ((STALE_AFTER_SECONDS > 0)) || die "--stale-after must be greater than zero"
else
  STALE_AFTER_SECONDS=$((HEARTBEAT_SECONDS * 3))
fi

if ((TIMEOUT_SECONDS > 600)) && [[ -z "$WATCH_FILE" ]]; then
  die "timeouts above 600 seconds require --output-log or --watch-file"
fi

[[ -z "$OUTPUT_LOG" ]] || regular_or_absent "$OUTPUT_LOG"
[[ -z "$EVENT_LOG" ]] || regular_or_absent "$EVENT_LOG"
if [[ -n "$OUTPUT_LOG" && -n "$EVENT_LOG" && "$OUTPUT_LOG" == "$EVENT_LOG" ]]; then
  die "--output-log and --event-log must be different files"
fi

TIMEOUT_CMD=
if command -v timeout >/dev/null 2>&1; then
  TIMEOUT_CMD=$(command -v timeout)
elif command -v gtimeout >/dev/null 2>&1; then
  TIMEOUT_CMD=$(command -v gtimeout)
else
  die "timeout/gtimeout is required; refusing to start an unbounded process"
fi

if [[ -n "$OUTPUT_LOG" ]]; then
  : >>"$OUTPUT_LOG" || die "cannot write --output-log: $OUTPUT_LOG"
fi
if [[ -n "$EVENT_LOG" ]]; then
  : >>"$EVENT_LOG" || die "cannot write --event-log: $EVENT_LOG"
fi

START_EPOCH=$(date +%s)
START_ISO=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
STOPPED_BY=
MONITOR_PID=
STOP_MARKER=$(mktemp "${TMPDIR:-/tmp}/run-guarded-stop.XXXXXX") ||
  die "cannot create stop marker"

cleanup() {
  rm -f "$STOP_MARKER"
}
trap cleanup EXIT

emit_event() {
  local payload=$1
  local line="[rule] ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ') label='$LABEL' $payload"
  printf '%s\n' "$line" >&2
  if [[ -n "$EVENT_LOG" ]]; then
    printf '%s\n' "$line" >>"$EVENT_LOG" || true
  fi
}

resource_snapshot() {
  local values
  values=$(ps -o pcpu=,rss=,stat= -p "$CHILD_PID" 2>/dev/null | awk 'NR==1 {printf "%s,%s,%s", $1, $2, $3}')
  if [[ -z "$values" ]]; then
    printf 'na,na,na\n'
  else
    printf '%s\n' "$values"
  fi
}

progress_age() {
  local now mtime
  now=$(date +%s)
  if [[ -n "$WATCH_FILE" && -e "$WATCH_FILE" ]]; then
    mtime=$(file_mtime "$WATCH_FILE" 2>/dev/null || true)
    if [[ -n "$mtime" ]]; then
      printf '%s\n' "$((now - mtime))"
      return
    fi
  fi
  printf '%s\n' "$((now - START_EPOCH))"
}

signal_child() {
  local signal=$1
  if [[ "$USE_SETSID" -eq 1 ]]; then
    kill -s "$signal" -- "-$CHILD_PID" 2>/dev/null ||
      kill -s "$signal" "$CHILD_PID" 2>/dev/null || true
  else
    kill -s "$signal" "$CHILD_PID" 2>/dev/null || true
  fi
}

stop_child() {
  local reason=$1
  STOPPED_BY=$reason
  printf '%s\n' "$reason" >"$STOP_MARKER"
  emit_event "event=stopping reason=$reason pid=$CHILD_PID"
  signal_child TERM

  local deadline=$(( $(date +%s) + KILL_AFTER_SECONDS ))
  while kill -0 "$CHILD_PID" 2>/dev/null; do
    if (( $(date +%s) >= deadline )); then
      emit_event "event=kill reason=$reason pid=$CHILD_PID"
      signal_child KILL
      break
    fi
    sleep 1
  done
}

monitor_child() {
  local age resources cpu rss state elapsed sleeper=
  monitor_interrupted() {
    if [[ -n "$sleeper" ]]; then
      kill "$sleeper" 2>/dev/null || true
    fi
    exit 0
  }
  trap monitor_interrupted TERM INT

  while kill -0 "$CHILD_PID" 2>/dev/null; do
    sleep "$HEARTBEAT_SECONDS" &
    sleeper=$!
    wait "$sleeper" 2>/dev/null || true
    sleeper=
    kill -0 "$CHILD_PID" 2>/dev/null || break

    age=$(progress_age)
    resources=$(resource_snapshot)
    IFS=, read -r cpu rss state <<<"$resources"
    elapsed=$(( $(date +%s) - START_EPOCH ))
    emit_event "event=heartbeat pid=$CHILD_PID elapsed_s=$elapsed progress_age_s=$age cpu_pct=$cpu rss_kb=$rss state=$state watch_file='${WATCH_FILE:-none}'"

    if ((age >= STALE_AFTER_SECONDS)); then
      emit_event "event=stalled pid=$CHILD_PID progress_age_s=$age stale_after_s=$STALE_AFTER_SECONDS"
      stop_child stale
      break
    fi
  done
}

on_signal() {
  local signal=$1
  emit_event "event=interrupted signal=$signal pid=$CHILD_PID"
  stop_child signal
  wait "$CHILD_PID" 2>/dev/null || true
  if [[ -n "$MONITOR_PID" ]]; then
    kill "$MONITOR_PID" 2>/dev/null || true
    wait "$MONITOR_PID" 2>/dev/null || true
  fi
  exit 130
}

USE_SETSID=0
if command -v setsid >/dev/null 2>&1; then
  USE_SETSID=1
fi

emit_event "event=start pid_pending=1 timeout_s=$TIMEOUT_SECONDS heartbeat_s=$HEARTBEAT_SECONDS stale_after_s=$STALE_AFTER_SECONDS output_log='${OUTPUT_LOG:-none}' watch_file='${WATCH_FILE:-none}' command=$(basename "${COMMAND[0]}") argc=${#COMMAND[@]}"

if [[ "$USE_SETSID" -eq 1 ]]; then
  if [[ -n "$OUTPUT_LOG" ]]; then
    setsid "$TIMEOUT_CMD" --signal=TERM --kill-after="${KILL_AFTER_SECONDS}s" "${TIMEOUT_SECONDS}s" "${COMMAND[@]}" >>"$OUTPUT_LOG" 2>&1 &
  else
    setsid "$TIMEOUT_CMD" --signal=TERM --kill-after="${KILL_AFTER_SECONDS}s" "${TIMEOUT_SECONDS}s" "${COMMAND[@]}" &
  fi
else
  if [[ -n "$OUTPUT_LOG" ]]; then
    "$TIMEOUT_CMD" --signal=TERM --kill-after="${KILL_AFTER_SECONDS}s" "${TIMEOUT_SECONDS}s" "${COMMAND[@]}" >>"$OUTPUT_LOG" 2>&1 &
  else
    "$TIMEOUT_CMD" --signal=TERM --kill-after="${KILL_AFTER_SECONDS}s" "${TIMEOUT_SECONDS}s" "${COMMAND[@]}" &
  fi
fi
CHILD_PID=$!
emit_event "event=started pid=$CHILD_PID start_utc=$START_ISO"

trap 'on_signal INT' INT
trap 'on_signal TERM' TERM
trap 'on_signal HUP' HUP

monitor_child &
MONITOR_PID=$!

wait "$CHILD_PID"
STATUS=$?
if [[ -s "$STOP_MARKER" ]]; then
  STOPPED_BY=$(head -n 1 "$STOP_MARKER")
  wait "$MONITOR_PID" 2>/dev/null || true
else
  kill "$MONITOR_PID" 2>/dev/null || true
  wait "$MONITOR_PID" 2>/dev/null || true
fi

if [[ "$STOPPED_BY" == "stale" ]]; then
  STATUS=124
fi

ELAPSED=$(( $(date +%s) - START_EPOCH ))
emit_event "event=exit pid=$CHILD_PID status=$STATUS elapsed_s=$ELAPSED stopped_by='${STOPPED_BY:-natural}'"
exit "$STATUS"
