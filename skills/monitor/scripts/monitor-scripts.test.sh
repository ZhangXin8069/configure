#!/usr/bin/env bash
# monitor-scripts.test.sh — offline regression tests for the djob adapter scripts.
#
# The generic monitor model is documented in SKILL.md/references; these tests cover the
# djob adapter templates (poll_jobs.sh, wait_all_jobs.sh, watch_job.sh). The tests
# replace `ssh` with a deterministic fake, so they never touch a real scheduler.
# Run from anywhere:
#   bash skills/monitor/scripts/monitor-scripts.test.sh

set -u
LC_ALL=C

scripts_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
poll="$scripts_dir/poll_jobs.sh"
wait_all="$scripts_dir/wait_all_jobs.sh"
watch="$scripts_dir/watch_job.sh"

tmp=$(mktemp -d "${TMPDIR:-/tmp}/monitor-scripts.test.XXXXXX") || {
  printf 'monitor-scripts.test.sh: cannot create a temp directory\n' >&2
  exit 1
}
cleanup() { rm -rf "$tmp"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

fake_bin="$tmp/bin"
mkdir -p "$fake_bin"
cat >"$fake_bin/ssh" <<'FAKE_SSH'
#!/usr/bin/env bash
set -u
state_dir=${FAKE_SSH_DIR:?FAKE_SSH_DIR is required}
log=${FAKE_SSH_LOG:-/dev/null}
args=("$@")
n=${#args[@]}
[ "$n" -ge 2 ] || { printf 'fake ssh: too few arguments\n' >&2; exit 255; }
remote=${args[$((n - 1))]}
target=${args[$((n - 2))]}
printf 'target=%s remote=%s\n' "$target" "$remote" >>"$log"

counter_file="$state_dir/counter"
count=0
[ -f "$counter_file" ] && count=$(cat "$counter_file")
count=$((count + 1))
printf '%s\n' "$count" >"$counter_file"

specific="$state_dir/seq.$count"
scenario=$specific
[ -f "$scenario" ] || scenario="$state_dir/seq.default"
[ -f "$scenario" ] && cat "$scenario"

err_file="$specific.err"
[ -f "$err_file" ] || err_file="$state_dir/seq.default.err"
[ -f "$err_file" ] && cat "$err_file" >&2

rc_file="$specific.rc"
[ -f "$rc_file" ] || rc_file="$state_dir/seq.default.rc"
[ -f "$rc_file" ] && exit "$(cat "$rc_file")"
exit 0
FAKE_SSH
chmod +x "$fake_bin/ssh"
export PATH="$fake_bin:$PATH"

pass=0
fail=0
out=
rc=0
case_dir=
case_log=

ok() {
  pass=$((pass + 1))
  printf 'ok %d - %s\n' "$((pass + fail))" "$1"
}

not_ok() {
  fail=$((fail + 1))
  printf 'not ok %d - %s\n' "$((pass + fail))" "$1"
  printf '  rc=%s\n' "$rc"
  printf '%s\n' "$out" | sed 's/^/  /'
}

check_rc() {
  if [ "$rc" -eq "$1" ]; then ok "$2"; else not_ok "$2 (expected rc $1)"; fi
}

check_contains() {
  case "$out" in
    *"$1"*) ok "$2" ;;
    *) not_ok "$2 (missing: $1)" ;;
  esac
}

check_not_contains() {
  case "$out" in
    *"$1"*) not_ok "$2 (unexpected: $1)" ;;
    *) ok "$2" ;;
  esac
}

check_log_contains() {
  if grep -Fq -- "$1" "$case_log"; then
    ok "$2"
  else
    not_ok "$2 (log missing: $1)"
  fi
}

check_line() {
  if printf '%s\n' "$out" | grep -Fxq -- "$1"; then
    ok "$2"
  else
    not_ok "$2 (missing line: $1)"
  fi
}

check_no_line() {
  if printf '%s\n' "$out" | grep -Fxq -- "$1"; then
    not_ok "$2 (unexpected line: $1)"
  else
    ok "$2"
  fi
}

new_case() {
  case_dir="$tmp/case-$1"
  mkdir -p "$case_dir"
  printf '0\n' >"$case_dir/counter"
  export FAKE_SSH_DIR="$case_dir"
  export FAKE_SSH_LOG="$tmp/case-$1.log"
  : >"$FAKE_SSH_LOG"
  case_log=$FAKE_SSH_LOG
}

run_cmd() {
  if command -v timeout >/dev/null 2>&1; then
    out=$(timeout 20 "$@" 2>&1)
  else
    out=$("$@" 2>&1)
  fi
  rc=$?
}

run_env() {
  if command -v timeout >/dev/null 2>&1; then
    out=$(timeout 20 env "$@" 2>&1)
  else
    out=$(env "$@" 2>&1)
  fi
  rc=$?
}

# --- argument validation ---------------------------------------------------
new_case poll-help
run_cmd bash "$poll" --help
check_rc 0 "poll_jobs --help exits 0"
check_contains "--host HOST" "poll_jobs --help shows the required host flag"

new_case poll-no-host
run_cmd bash "$poll"
check_rc 2 "poll_jobs rejects a missing --host"
check_contains "--host is required" "poll_jobs explains the missing host"

new_case poll-bad-interval
run_cmd bash "$poll" --host fake --interval 0
check_rc 2 "poll_jobs rejects a zero interval"
check_contains "--interval must be greater than zero" "poll_jobs explains the interval error"

new_case poll-bad-regex
run_cmd bash "$poll" --host fake --include '['
check_rc 2 "poll_jobs rejects an invalid --include ERE"
check_contains "--include must be a valid extended regex" "poll_jobs explains the ERE error"

new_case poll-bad-states
run_cmd bash "$poll" --host fake --states 'RUNNING,PENDING'
check_rc 2 "poll_jobs rejects comma-separated --states"
check_contains "--states must be space-separated state names" "poll_jobs explains the states error"

new_case poll-empty-sentinel
run_cmd bash "$poll" --host fake --sentinel ''
check_rc 2 "poll_jobs rejects an empty sentinel"
check_contains "--sentinel must not be empty" "poll_jobs explains the sentinel error"

new_case poll-blank-states
run_cmd bash "$poll" --host fake --states '   '
check_rc 2 "poll_jobs rejects whitespace-only --states"
check_contains "--states must contain at least one state name" "poll_jobs explains the blank states error"

# --- all-jobs polling ------------------------------------------------------
new_case poll-active-then-empty
cat >"$case_dir/seq.1" <<'EOF'
ID NAME STATE USER ACCOUNT QUEUE START_TIME END_TIME EXEC_NODES
2133322 kall_mgr10_* RUNNING u a q - - cn1
2133326 kall_mg1_r5* PENDING u a q - - -
2108699 qcu_opt_base PENDING u a q - - -
2133333 done_job SUCCEEDED u a q t t cn2
EOF
cat >"$case_dir/seq.2" <<'EOF'
ID NAME STATE USER ACCOUNT QUEUE START_TIME END_TIME EXEC_NODES
EOF
printf '** WARNING: fake transport noise\n' >"$case_dir/seq.1.err"
run_cmd bash "$poll" --host fakehost --user fakeuser --interval 1 \
  --max-cycles 3 --exclude 'qcu_opt_base'
check_rc 0 "poll_jobs prints the sentinel when the active set empties"
check_contains "active=2" "poll_jobs counts only active rows"
check_line "ALL_JOBS_DONE" "poll_jobs prints the default sentinel"
check_not_contains "qcu_opt_base" "poll_jobs applies --exclude"
check_not_contains "done_job" "poll_jobs ignores terminal rows"
check_not_contains "WARNING" "poll_jobs keeps successful ssh stderr out of stdout"
check_log_contains "target=fakeuser@fakehost" "poll_jobs builds user@host from --user/--host"

new_case poll-ssh-abort
printf '255\n' >"$case_dir/seq.1.rc"
printf '255\n' >"$case_dir/seq.2.rc"
printf '255\n' >"$case_dir/seq.3.rc"
run_cmd bash "$poll" --host fake --interval 1 --max-ssh-failures 3
check_rc 3 "poll_jobs aborts after consecutive ssh failures"
check_contains "POLL_ABORT ssh_failures=3" "poll_jobs reports the ssh failure count"
check_no_line "ALL_JOBS_DONE" "poll_jobs never turns an ssh failure into a sentinel"

new_case poll-timeout
cat >"$case_dir/seq.default" <<'EOF'
ID NAME STATE USER ACCOUNT QUEUE START_TIME END_TIME EXEC_NODES
2133322 held_job RUNNING u a q - - cn1
EOF
run_cmd bash "$poll" --host fake --interval 30 --max-duration 1
check_rc 124 "poll_jobs exits 124 at the time budget"
check_contains "POLL_TIMEOUT" "poll_jobs prints POLL_TIMEOUT instead of a sentinel"
check_no_line "ALL_JOBS_DONE" "poll_jobs does not report completion on timeout"

# --- wait_all_jobs wrapper -------------------------------------------------
new_case wait-env
cat >"$case_dir/seq.default" <<'EOF'
ID NAME STATE USER ACCOUNT QUEUE START_TIME END_TIME EXEC_NODES
EOF
run_env HOST=envhost REMOTE_USER=envuser bash "$wait_all" --interval 1 --max-cycles 1
check_rc 0 "wait_all_jobs exits 0 when the queue is empty"
check_line "ALL_JOBS_DONE" "wait_all_jobs forwards the all-jobs sentinel"
check_contains "host=envhost user=envuser" "wait_all_jobs reads HOST/REMOTE_USER"
check_log_contains "target=envuser@envhost" "wait_all_jobs forwards HOST/REMOTE_USER to poll_jobs"

# --- single-job watch ------------------------------------------------------
new_case watch-no-job
run_cmd bash "$watch" --host fake
check_rc 2 "watch_job rejects a missing --job"
check_contains "--job is required" "watch_job explains the missing job"

new_case watch-transitions
i=0
for state in PENDING RUNNING STOPPED SUCCEEDED; do
  i=$((i + 1))
  printf '    state                               %s\n' "$state" >"$case_dir/seq.$i"
done
run_cmd bash "$watch" --host fake --user fakeuser --job 2133322 --mode ll \
  --interval 1 --max-duration 10
check_rc 0 "watch_job exits 0 on a terminal state"
check_contains "state=PENDING" "watch_job reports PENDING"
check_contains "state=RUNNING" "watch_job reports RUNNING"
check_contains "state=STOPPED" "watch_job reports STOPPED"
check_contains "state=SUCCEEDED" "watch_job reports SUCCEEDED"
check_contains "WATCH_DONE job=2133322 state=SUCCEEDED" "watch_job finishes on SUCCEEDED"
check_not_contains "WATCH_DONE job=2133322 state=STOPPED" "watch_job does not treat STOPPED as terminal"

new_case watch-auto-fallback
: >"$case_dir/seq.1"
cat >"$case_dir/seq.2" <<'EOF'
ID NAME STATE USER ACCOUNT QUEUE START_TIME END_TIME EXEC_NODES
1 job RUNNING u a q - - cn1
EOF
printf '    state                               SUCCEEDED\n' >"$case_dir/seq.3"
run_cmd bash "$watch" --host fake --job 1 --mode auto --interval 1 --max-duration 10
check_rc 0 "watch_job auto mode exits 0"
check_contains "state=RUNNING" "watch_job auto mode falls back to the table"
check_contains "WATCH_DONE job=1 state=SUCCEEDED" "watch_job auto mode reads the final ll state"

new_case watch-timeout
printf '    state                               RUNNING\n' >"$case_dir/seq.default"
run_cmd bash "$watch" --host fake --job 1 --mode ll --interval 30 --max-duration 1
check_rc 9 "watch_job exits 9 at the time budget"
check_contains "WATCH_TIMEOUT job=1 state=RUNNING" "watch_job prints WATCH_TIMEOUT"

new_case watch-ssh-abort
printf '255\n' >"$case_dir/seq.1.rc"
printf '255\n' >"$case_dir/seq.2.rc"
printf '255\n' >"$case_dir/seq.3.rc"
run_cmd bash "$watch" --host fake --job 1 --mode ll --interval 1 --max-failures 3
check_rc 3 "watch_job aborts after consecutive ssh failures"
check_contains "WATCH_ABORT job=1 reason=ssh_failures count=3" "watch_job reports the ssh failure count"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
