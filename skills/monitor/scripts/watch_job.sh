#!/usr/bin/env bash
# watch_job.sh — TEMPLATE: follow one scheduler job and exit on a terminal state.
#
# Prints a line only when the state changes (timestamp + elapsed seconds), then exits
# as soon as the job reaches SUCCEEDED|FAILED|CANCELLED|KILLED. STOPPED/SSTOPPED mean
# the job is suspended and do NOT end the watch.
#
# This file is a template shipped with the `monitor` skill. It is read-only: it never
# submits, cancels, or kills anything. Copy it into the task scratchpad and edit the
# defaults if the scheduler flags differ on your cluster.
#
# Example:
#   ./watch_job.sh --host <login-host> --user <remote-user> --job <job-id>
#   ./watch_job.sh --host <host> --job <job-id> --interval 30 --max-duration 7200
#
# Exit codes:
#   0    terminal state observed (this does NOT mean the job succeeded)
#   2    usage or argument error
#   3    ssh/scheduler communication failed, or the job is no longer reported
#   9    wait timeout (job still PENDING/RUNNING)
#   130  interrupted (SIGINT)
#   143  terminated (SIGTERM/HUP)
#
# Compile check: bash -n watch_job.sh

set -u
LC_ALL=C

usage() {
  cat <<'EOF'
Usage: watch_job.sh --host HOST --job JOB [options]

Follow one scheduler job until it reaches a terminal state.

Required:
  --host HOST            SSH host (alias or address)
  --job JOB              Scheduler job id
Options:
  --user USER            Remote scheduler user (default: $USER)
  --interval SEC         Seconds between polls (default: 60)
  --max-duration SEC     Give up after SEC seconds (default: 3600);
                         the final sleep is capped to the remaining budget
  --mode MODE            auto | ll | table (default: auto)
                         ll    = `djob -ll JOB`, read the `state` field
                         table = `djob JOB`, read column 3 of the matching row
                         auto  = try ll, fall back to table when the state is empty
  --max-failures N       Abort after N consecutive ssh failures (default 3)
  --max-unknown N        Abort after N consecutive empty/unknown states (default 5)
  --ssh-option OPT       Extra `ssh -o OPT` (repeatable)
  -h, --help             Show this help

Terminal states: SUCCEEDED FAILED CANCELLED KILLED
(STOPPED/SSTOPPED are suspended states and keep the watch running.)
EOF
}

die() {
  printf 'watch_job.sh: %s\n' "$*" >&2
  exit 2
}

is_uint() {
  case "$1" in
    '' | *[!0-9]*) return 1 ;;
    *) return 0 ;;
  esac
}

HOST=
REMOTE_USER=${USER:-}
JOB=
INTERVAL=60
MAX_DURATION=3600
MODE=auto
MAX_FAIL=3
MAX_UNKNOWN=5
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes)

while [ $# -gt 0 ]; do
  case "$1" in
    --host)          [ $# -ge 2 ] || die "--host requires a value"; HOST=$2; shift 2 ;;
    --user)          [ $# -ge 2 ] || die "--user requires a value"; REMOTE_USER=$2; shift 2 ;;
    --job)           [ $# -ge 2 ] || die "--job requires a value"; JOB=$2; shift 2 ;;
    --interval)      [ $# -ge 2 ] || die "--interval requires a value"; INTERVAL=$2; shift 2 ;;
    --max-duration)  [ $# -ge 2 ] || die "--max-duration requires a value"; MAX_DURATION=$2; shift 2 ;;
    --mode)          [ $# -ge 2 ] || die "--mode requires a value"; MODE=$2; shift 2 ;;
    --max-failures)  [ $# -ge 2 ] || die "--max-failures requires a value"; MAX_FAIL=$2; shift 2 ;;
    --max-unknown)   [ $# -ge 2 ] || die "--max-unknown requires a value"; MAX_UNKNOWN=$2; shift 2 ;;
    --ssh-option)    [ $# -ge 2 ] || die "--ssh-option requires a value"; SSH_OPTS+=(-o "$2"); shift 2 ;;
    -h | --help)     usage; exit 0 ;;
    *)               die "unknown argument: $1" ;;
  esac
done

[ -n "$HOST" ] || die "--host is required"
case "$HOST" in
  -*) die "--host must not start with '-'" ;;
  *[[:space:]]*) die "--host must not contain whitespace" ;;
esac
[ -n "$JOB" ] || die "--job is required"
case "$JOB" in
  *[!A-Za-z0-9_.-]*) die "--job must look like a job id (letters/digits/._-)" ;;
esac
case "$REMOTE_USER" in
  '' | *[!A-Za-z0-9_.-]*) die "--user must be a plain user name" ;;
esac
case "$MODE" in
  auto | ll | table) ;;
  *) die "--mode must be auto, ll or table" ;;
esac
is_uint "$INTERVAL" || die "--interval must be a non-negative integer"
is_uint "$MAX_DURATION" || die "--max-duration must be a non-negative integer"
is_uint "$MAX_FAIL" || die "--max-failures must be a non-negative integer"
is_uint "$MAX_UNKNOWN" || die "--max-unknown must be a non-negative integer"
[ "$INTERVAL" -gt 0 ] || die "--interval must be greater than zero"
[ "$MAX_FAIL" -gt 0 ] || die "--max-failures must be greater than zero"
[ "$MAX_UNKNOWN" -gt 0 ] || die "--max-unknown must be greater than zero"
command -v ssh >/dev/null 2>&1 || die "ssh not found"
command -v awk >/dev/null 2>&1 || die "awk not found"

case "$HOST" in
  *@*) TARGET=$HOST ;;
  *)   TARGET="${REMOTE_USER}@${HOST}" ;;
esac

# Keep $PATH literal for the remote shell.
PATH_SETUP='export PATH=/opt/batch/cli/bin:$PATH'
REMOTE_PREFIX="source /etc/profile >/dev/null 2>&1 || true; ${PATH_SETUP}; "

ERR_FILE=$(mktemp "${TMPDIR:-/tmp}/watch_job.err.XXXXXX") || die "cannot create a temp file"
cleanup() { rm -f "$ERR_FILE"; }
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM HUP

state_from_ll() {
  printf '%s\n' "$1" | awk '$1 == "state" { print $2; exit }'
}

state_from_table() {
  printf '%s\n' "$1" | awk -v j="$JOB" '$1 == j { print $3; exit }'
}

start_epoch=$(date +%s)
last=
fail=0
unknown=0

printf 'watch_job: host=%s user=%s job=%s interval=%ss max_duration=%ss mode=%s\n' \
  "$HOST" "$REMOTE_USER" "$JOB" "$INTERVAL" "$MAX_DURATION" "$MODE"
printf 'watch_job: terminal states = SUCCEEDED FAILED CANCELLED KILLED\n'

while :; do
  st=
  rc=1

  if [ "$MODE" != "table" ]; then
    out=$(ssh "${SSH_OPTS[@]}" "$TARGET" "${REMOTE_PREFIX}djob -ll $JOB 2>/dev/null" 2>"$ERR_FILE")
    rc=$?
    if [ "$rc" -eq 0 ]; then
      st=$(state_from_ll "$out")
    fi
  fi

  if [ -z "$st" ] && [ "$MODE" != "ll" ]; then
    out=$(ssh "${SSH_OPTS[@]}" "$TARGET" "${REMOTE_PREFIX}djob $JOB 2>/dev/null" 2>>"$ERR_FILE")
    rc=$?
    if [ "$rc" -eq 0 ]; then
      st=$(state_from_table "$out")
    fi
  fi

  elapsed=$(( $(date +%s) - start_epoch ))
  stamp=$(date +%H:%M:%S)

  if [ "$rc" -ne 0 ]; then
    fail=$((fail + 1))
    printf '[%s +%ss] job=%s ssh_error rc=%d (%d/%d)\n' \
      "$stamp" "$elapsed" "$JOB" "$rc" "$fail" "$MAX_FAIL"
    sed -n '1,3p' "$ERR_FILE" >&2 || true
    if [ "$fail" -ge "$MAX_FAIL" ]; then
      printf 'WATCH_ABORT job=%s reason=ssh_failures count=%d\n' "$JOB" "$fail"
      cleanup
      exit 3
    fi
  elif [ -z "$st" ]; then
    unknown=$((unknown + 1))
    printf '[%s +%ss] job=%s state=UNKNOWN (%d/%d) reason=no_state_field\n' \
      "$stamp" "$elapsed" "$JOB" "$unknown" "$MAX_UNKNOWN"
    if [ "$unknown" -ge "$MAX_UNKNOWN" ]; then
      printf 'WATCH_ABORT job=%s reason=not_reported count=%d\n' "$JOB" "$unknown"
      cleanup
      exit 3
    fi
  else
    fail=0
    unknown=0
    if [ "$st" != "$last" ]; then
      printf '[%s +%ss] job=%s state=%s\n' "$stamp" "$elapsed" "$JOB" "$st"
      last=$st
    fi
    case "$st" in
      SUCCEEDED | FAILED | CANCELLED | KILLED)
        printf 'WATCH_DONE job=%s state=%s after=%ss\n' "$JOB" "$st" "$elapsed"
        cleanup
        exit 0
        ;;
    esac
  fi

  if [ "$MAX_DURATION" -gt 0 ] && [ "$elapsed" -ge "$MAX_DURATION" ]; then
    printf 'WATCH_TIMEOUT job=%s state=%s after=%ss\n' "$JOB" "${st:-UNKNOWN}" "$elapsed"
    cleanup
    exit 9
  fi

  sleep_for=$INTERVAL
  if [ "$MAX_DURATION" -gt 0 ]; then
    remaining=$((MAX_DURATION - elapsed))
    [ "$remaining" -lt "$sleep_for" ] && sleep_for=$remaining
  fi
  sleep "$sleep_for"
done
