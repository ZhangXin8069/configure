#!/usr/bin/env bash
# poll_jobs.sh — TEMPLATE (djob adapter): poll a djob queue until the active set is empty.
#
# This file is a djob adapter template shipped with the `monitor` skill; the generic
# observation model lives in SKILL.md and references/adapters.md. It is not executed by
# the skill itself: copy it into your task scratchpad, adjust the defaults for the job
# family you are watching, and run it there. Read-only: it never submits, cancels,
# kills, or writes into the data tree.
#
# Example (all jobs of one user, excluding a long-lived baseline job):
#   ./poll_jobs.sh --host <login-host> --user <remote-user> \
#     --exclude '<baseline-job-name>' \
#     --interval 300 --max-duration 14400
#
# Exit codes:
#   0    sentinel printed (active set empty)
#   2    usage or argument error
#   3    ssh/scheduler communication failed too many times in a row
#   124  poll/time budget exhausted
#   130  interrupted (SIGINT)
#   143  terminated (SIGTERM/HUP)
#
# Compile check: bash -n poll_jobs.sh

set -u
LC_ALL=C

usage() {
  cat <<'EOF'
Usage: poll_jobs.sh --host HOST [options]

Poll a remote scheduler queue and stop when the active set is empty.

Required:
  --host HOST             SSH host (alias or address)
Options:
  --user USER             Remote scheduler user (default: $USER)
  --interval SEC          Seconds between polls (default: 300)
  --sentinel TEXT         Line printed when the active set is empty (default: ALL_JOBS_DONE)
  --states "A B ..."      States treated as active
                          (default: "RUNNING PENDING WAITING STOPPED SSTOPPED")
  --include REGEX         Keep only rows matching this extended regex (whole djob line)
  --exclude REGEX         Drop rows matching this extended regex
                          (use it for long-lived baseline/pending jobs you do not own)
  --max-cycles N          Stop after N polls (0 = unlimited, default 0)
  --max-duration SEC      Stop after SEC seconds (default: 14400 = 4h);
                          the final sleep is capped to the remaining budget
  --max-ssh-failures N    Abort after N consecutive ssh failures (default: 3)
  --djob-extra "ARGS"     Extra djob arguments, e.g. "-w" (default: empty)
  --ssh-option OPT        Extra `ssh -o OPT` (repeatable)
  -h, --help              Show this help

The remote command is always:
  source /etc/profile; export PATH=/opt/batch/cli/bin:$PATH; djob -u USER [extra]

Notes:
  * An ssh failure is reported as ssh_error and never treated as "queue empty".
  * Job names in `djob -u` output are truncated (e.g. `kall_mgr10_*`); prefer
    --include on job ids, or use `djob -u USER -J` JSON for exact names.
EOF
}

die() {
  printf 'poll_jobs.sh: %s\n' "$*" >&2
  exit 2
}

is_uint() {
  case "$1" in
    '' | *[!0-9]*) return 1 ;;
    *) return 0 ;;
  esac
}

valid_ere() {
  awk -v re="$1" 'BEGIN { if ("" ~ re) print "" }' >/dev/null 2>&1
}

# --- defaults (edit these for a new job family, or pass flags) -------------
HOST=
REMOTE_USER=${USER:-}
INTERVAL=300
SENTINEL=ALL_JOBS_DONE
STATES="RUNNING PENDING WAITING STOPPED SSTOPPED"
INCLUDE=
EXCLUDE=
MAX_CYCLES=0
MAX_DURATION=14400
MAX_SSH_FAIL=3
DJOB_EXTRA=
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes)
# --------------------------------------------------------------------------

while [ $# -gt 0 ]; do
  case "$1" in
    --host)            [ $# -ge 2 ] || die "--host requires a value"; HOST=$2; shift 2 ;;
    --user)            [ $# -ge 2 ] || die "--user requires a value"; REMOTE_USER=$2; shift 2 ;;
    --interval)        [ $# -ge 2 ] || die "--interval requires a value"; INTERVAL=$2; shift 2 ;;
    --sentinel)        [ $# -ge 2 ] || die "--sentinel requires a value"; SENTINEL=$2; shift 2 ;;
    --states)          [ $# -ge 2 ] || die "--states requires a value"; STATES=$2; shift 2 ;;
    --include)         [ $# -ge 2 ] || die "--include requires a value"; INCLUDE=$2; shift 2 ;;
    --exclude)         [ $# -ge 2 ] || die "--exclude requires a value"; EXCLUDE=$2; shift 2 ;;
    --max-cycles)      [ $# -ge 2 ] || die "--max-cycles requires a value"; MAX_CYCLES=$2; shift 2 ;;
    --max-duration)    [ $# -ge 2 ] || die "--max-duration requires a value"; MAX_DURATION=$2; shift 2 ;;
    --max-ssh-failures) [ $# -ge 2 ] || die "--max-ssh-failures requires a value"; MAX_SSH_FAIL=$2; shift 2 ;;
    --djob-extra)      [ $# -ge 2 ] || die "--djob-extra requires a value"; DJOB_EXTRA=$2; shift 2 ;;
    --ssh-option)      [ $# -ge 2 ] || die "--ssh-option requires a value"; SSH_OPTS+=(-o "$2"); shift 2 ;;
    -h | --help)       usage; exit 0 ;;
    *)                 die "unknown argument: $1" ;;
  esac
done

[ -n "$HOST" ] || die "--host is required"
case "$HOST" in
  -*) die "--host must not start with '-'" ;;
  *[[:space:]]*) die "--host must not contain whitespace" ;;
esac
[ -n "$SENTINEL" ] || die "--sentinel must not be empty"
case "$STATES" in
  '' | *[!A-Za-z_[:space:]]*) die "--states must be space-separated state names" ;;
esac
# Normalize repeated whitespace so the regex has no empty alternative.
# shellcheck disable=SC2086
set -- $STATES
[ "$#" -gt 0 ] || die "--states must contain at least one state name"
STATES_RE=$(IFS='|'; printf '%s' "$*")
is_uint "$INTERVAL" || die "--interval must be a non-negative integer"
is_uint "$MAX_CYCLES" || die "--max-cycles must be a non-negative integer"
is_uint "$MAX_DURATION" || die "--max-duration must be a non-negative integer"
is_uint "$MAX_SSH_FAIL" || die "--max-ssh-failures must be a non-negative integer"
[ "$INTERVAL" -gt 0 ] || die "--interval must be greater than zero"
[ "$MAX_SSH_FAIL" -gt 0 ] || die "--max-ssh-failures must be greater than zero"
command -v ssh >/dev/null 2>&1 || die "ssh not found"
command -v awk >/dev/null 2>&1 || die "awk not found"
[ -z "$INCLUDE" ] || valid_ere "$INCLUDE" || die "--include must be a valid extended regex"
[ -z "$EXCLUDE" ] || valid_ere "$EXCLUDE" || die "--exclude must be a valid extended regex"

case "$REMOTE_USER" in
  '' | *[!A-Za-z0-9_.-]*) die "--user must be a plain user name" ;;
esac
case "$DJOB_EXTRA" in
  *[!A-Za-z0-9_.\ -]*) die "--djob-extra must be plain flags (letters/digits/space/._-)" ;;
esac

case "$HOST" in
  *@*) TARGET=$HOST ;;
  *)   TARGET="${REMOTE_USER}@${HOST}" ;;
esac

# The remote PATH assignment must reach the remote shell literally, so keep $PATH
# inside single quotes here and interpolate it as a plain string later.
PATH_SETUP='export PATH=/opt/batch/cli/bin:$PATH'
USER_FLAG="-u '$REMOTE_USER'"
REMOTE_CMD="source /etc/profile >/dev/null 2>&1 || true; ${PATH_SETUP}; djob ${USER_FLAG} ${DJOB_EXTRA} 2>/dev/null"

scratch_root=${AGENT_SCRATCH_ROOT:-${TMPDIR:-/tmp}}
mkdir -p -- "$scratch_root" 2>/dev/null || scratch_root=${TMPDIR:-/tmp}
ERR_FILE=$(mktemp "${scratch_root}/poll_jobs.err.XXXXXX") || die "cannot create a temp file"
cleanup() { rm -f "$ERR_FILE"; }
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM HUP

start_epoch=$(date +%s)
cycle=0
fail=0

printf 'poll_jobs: host=%s user=%s interval=%ss sentinel=%s max_duration=%ss\n' \
  "$HOST" "$REMOTE_USER" "$INTERVAL" "$SENTINEL" "$MAX_DURATION"

while :; do
  cycle=$((cycle + 1))

  out=$(ssh "${SSH_OPTS[@]}" "$TARGET" "$REMOTE_CMD" 2>"$ERR_FILE")
  rc=$?

  if [ "$rc" -ne 0 ]; then
    fail=$((fail + 1))
    printf '[%s] cycle=%d ssh_error rc=%d (%d/%d)\n' \
      "$(date +%H:%M:%S)" "$cycle" "$rc" "$fail" "$MAX_SSH_FAIL"
    sed -n '1,3p' "$ERR_FILE" >&2 || true
    if [ "$fail" -ge "$MAX_SSH_FAIL" ]; then
      printf 'POLL_ABORT ssh_failures=%d\n' "$fail"
      cleanup
      exit 3
    fi
  else
    fail=0
    active=$(printf '%s\n' "$out" | awk -v states="$STATES_RE" -v inc="$INCLUDE" -v exc="$EXCLUDE" '
      $1 == "ID" { next }
      NF < 3 { next }
      {
        if (states != "" && $3 !~ ("^(" states ")$")) next
        if (inc != "" && $0 !~ inc) next
        if (exc != "" && $0 ~ exc) next
        printf "%s %s %s\n", $1, $2, $3
      }')

    if [ -z "$active" ]; then
      printf '%s\n' "$SENTINEL"
      cleanup
      exit 0
    fi

    count=$(printf '%s\n' "$active" | awk 'END { print NR }')
    printf '[%s] cycle=%d active=%s\n' "$(date +%H:%M:%S)" "$cycle" "$count"
    printf '%s\n' "$active"
  fi

  now=$(date +%s)
  elapsed=$((now - start_epoch))
  if [ "$MAX_DURATION" -gt 0 ] && [ "$elapsed" -ge "$MAX_DURATION" ]; then
    printf 'POLL_TIMEOUT elapsed_s=%d cycles=%d\n' "$elapsed" "$cycle"
    cleanup
    exit 124
  fi
  if [ "$MAX_CYCLES" -gt 0 ] && [ "$cycle" -ge "$MAX_CYCLES" ]; then
    printf 'POLL_CYCLE_LIMIT cycles=%d\n' "$cycle"
    cleanup
    exit 124
  fi

  sleep_for=$INTERVAL
  if [ "$MAX_DURATION" -gt 0 ]; then
    remaining=$((MAX_DURATION - elapsed))
    [ "$remaining" -lt "$sleep_for" ] && sleep_for=$remaining
  fi
  sleep "$sleep_for"
done
