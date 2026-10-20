#!/usr/bin/env bash
set -euo pipefail
LC_ALL=C

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
GUARD="$SCRIPT_DIR/run-guarded.sh"
TMP_ROOT=$(mktemp -d "$SCRIPT_DIR/.run-guarded-test.XXXXXX")
trap 'rm -rf "$TMP_ROOT"' EXIT

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_contains() {
  local file=$1
  local text=$2
  grep -Fq -- "$text" "$file" || fail "missing '$text' in $file"
}

"$GUARD" --help >/dev/null

SUCCESS_EVENTS="$TMP_ROOT/success.events"
"$GUARD" \
  --label success \
  --timeout 5s \
  --heartbeat 1s \
  --event-log "$SUCCESS_EVENTS" \
  -- bash -c 'printf "success-output\\n"' \
  >"$TMP_ROOT/success.stdout" 2>"$TMP_ROOT/success.stderr"
grep -Fqx 'success-output' "$TMP_ROOT/success.stdout" || fail "command stdout was not preserved"
assert_contains "$SUCCESS_EVENTS" 'event=start'
assert_contains "$SUCCESS_EVENTS" 'event=exit'
assert_contains "$SUCCESS_EVENTS" 'status=0'

TIMEOUT_EVENTS="$TMP_ROOT/timeout.events"
set +e
"$GUARD" \
  --label timeout \
  --timeout 1s \
  --heartbeat 1s \
  --kill-after 1s \
  --event-log "$TIMEOUT_EVENTS" \
  -- sleep 5 \
  >/dev/null 2>"$TMP_ROOT/timeout.stderr"
timeout_status=$?
set -e
[[ "$timeout_status" -eq 124 ]] || fail "hard timeout returned $timeout_status, expected 124"
assert_contains "$TIMEOUT_EVENTS" 'event=exit'
assert_contains "$TIMEOUT_EVENTS" 'status=124'

if "$GUARD" \
  --label missing-progress \
  --timeout 601s \
  -- true \
  >/dev/null 2>&1; then
  fail "long command without progress log should be rejected"
fi

OUTPUT_LOG="$TMP_ROOT/output.log"
CAPTURE_EVENTS="$TMP_ROOT/capture.events"
"$GUARD" \
  --label capture \
  --timeout 5s \
  --output-log "$OUTPUT_LOG" \
  --event-log "$CAPTURE_EVENTS" \
  -- bash -c 'printf "captured\\n"' \
  >/dev/null 2>"$TMP_ROOT/capture.stderr"
assert_contains "$OUTPUT_LOG" 'captured'
assert_contains "$CAPTURE_EVENTS" 'status=0'

STALL_OUTPUT="$TMP_ROOT/stall-output.log"
STALL_EVENTS="$TMP_ROOT/stall.events"
set +e
"$GUARD" \
  --label stall \
  --timeout 10s \
  --heartbeat 1s \
  --stale-after 1s \
  --kill-after 1s \
  --output-log "$STALL_OUTPUT" \
  --event-log "$STALL_EVENTS" \
  -- sleep 5 \
  >/dev/null 2>"$TMP_ROOT/stall.stderr"
stall_status=$?
set -e
[[ "$stall_status" -eq 124 ]] || fail "stalled process returned $stall_status, expected 124"
assert_contains "$STALL_EVENTS" 'event=stalled'
assert_contains "$STALL_EVENTS" "stopped_by='stale'"

printf 'run-guarded tests: PASS\n'
