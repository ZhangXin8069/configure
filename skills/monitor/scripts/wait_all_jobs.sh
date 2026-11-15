#!/usr/bin/env bash
# wait_all_jobs.sh — TEMPLATE (djob adapter): "wait until every djob job is gone".
#
# Thin djob-adapter wrapper around poll_jobs.sh with all-jobs defaults:
#   interval 300s, sentinel ALL_JOBS_DONE, max duration 4h, optional exclude.
# Copy both scripts into the task scratchpad and call this one for the common case.
#
# Example:
#   HOST=<login-host> REMOTE_USER=<remote-user> EXCLUDE='<baseline-job-name>' \
#     ./wait_all_jobs.sh
#   ./wait_all_jobs.sh --host <login-host> --user <remote-user> --exclude '<name>'
#   ./wait_all_jobs.sh --host <host> --include '^21[0-9]{6} ' --interval 120
#
# Compile check: bash -n wait_all_jobs.sh

set -u
LC_ALL=C

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
poll="$script_dir/poll_jobs.sh"
if [ ! -f "$poll" ]; then
  printf 'wait_all_jobs.sh: missing %s\n' "$poll" >&2
  exit 2
fi
if [ -x "$poll" ]; then
  poll_cmd=("$poll")
else
  poll_cmd=(bash "$poll")
fi

SCAN_INTERVAL=${SCAN_INTERVAL:-300}
SENTINEL=${SENTINEL:-ALL_JOBS_DONE}
MAX_DURATION=${MAX_DURATION:-14400}
EXCLUDE=${EXCLUDE:-}
MAX_CYCLES=${MAX_CYCLES:-0}
host=${HOST:-}
remote_user=${REMOTE_USER:-}

printf 'wait_all_jobs: host=%s user=%s interval=%ss sentinel=%s max_duration=%ss max_cycles=%s exclude=%s\n' \
  "${host:-<from flags>}" "${remote_user:-<from flags>}" \
  "$SCAN_INTERVAL" "$SENTINEL" "$MAX_DURATION" "$MAX_CYCLES" "${EXCLUDE:-<none>}"

args=(--interval "$SCAN_INTERVAL" --sentinel "$SENTINEL" --max-duration "$MAX_DURATION")
args+=(--max-cycles "$MAX_CYCLES")
if [ -n "$EXCLUDE" ]; then
  args+=(--exclude "$EXCLUDE")
fi
if [ -n "$host" ]; then
  args+=(--host "$host")
fi
if [ -n "$remote_user" ]; then
  args+=(--user "$remote_user")
fi

# User flags come last so they override the defaults above.
exec "${poll_cmd[@]}" "${args[@]}" "$@"
