#!/usr/bin/env bash

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
resume_tool=$script_dir/agent-resume.sh
test_root=$(mktemp -d "${TMPDIR:-/tmp}/agent-resume-test.XXXXXX")
data_root=$test_root/data
workspace_root=$test_root/workspace

cleanup() {
    rm -rf -- "$test_root"
}
trap cleanup EXIT HUP INT TERM

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_contains() {
    case "$1" in
        *"$2"*) ;;
        *) fail "输出缺少: $2\n实际输出:\n$1";;
    esac
}

mkdir -p "$data_root/runs" "$workspace_root/tasks"

fake_launcher=$test_root/fake-launcher
cat >"$fake_launcher" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
{
    printf 'args=%s\n' "$*"
    printf 'pid=%s\n' "$$"
    printf 'cwd=%s\n' "$PWD"
    printf 'codex_provider=%s\n' "${CODEX_PROVIDER_ID:-}"
    printf 'opencode_provider=%s\n' "${OPENCODE_PROVIDER:-}"
    printf 'claude_provider=%s\n' "${CLAUDE_PROVIDER:-}"
    printf 'resume_active=%s\n' "${AGENT_RESUME_ACTIVE:-}"
    printf 'auto_resume=%s\n' "${AGENT_AUTO_RESUME:-}"
} >"${FAKE_CALL_LOG:?}"
[[ -z "${FAKE_SLEEP:-}" ]] || sleep "$FAKE_SLEEP"
printf '%s\n' '{"type":"item.completed","item":{"type":"agent_message","text":"resumed-ok"}}' \
    >>"${FAKE_RUN_LOG:?}"
awk '
    BEGIN { done = 0 }
    /^state=/ { print "state=finished"; done = 1; next }
    { print }
    END { if (!done) print "state=finished" }
' "${FAKE_MANIFEST:?}" >"${FAKE_MANIFEST}.tmp"
mv -f -- "${FAKE_MANIFEST}.tmp" "${FAKE_MANIFEST}"
exit "${FAKE_RC:-0}"
EOF
chmod 0755 "$fake_launcher"

create_run() {
    local run_id=$1 agent=$2 launcher=$3 cwd_rel=$4 role=${5:-solo-agent}
    run_dir=$data_root/runs/$run_id
    mkdir -p "$run_dir" "$workspace_root/$cwd_rel"
    manifest=$run_dir/manifest.env
    log_file=$run_dir/agent.log
    event_file=$run_dir/events.jsonl
    : >"$log_file"
    : >"$event_file"
    cat >"$manifest" <<EOF
schema_version=1
run_id=$run_id
created_at=2026-10-21T03:10:22+0800
updated_at=2026-10-21T03:10:32+0800
agent=$agent
launcher=$launcher
mode=drive
role=$role
tier=standard
posture=frontier-orchestrator
cwd=$workspace_root/$cwd_rel
workspace_root=$workspace_root
data_root=$data_root
run_dir=$run_dir
log_file=$log_file
list_file=$run_dir/inputs.txt
event_file=$event_file
context_file=$run_dir/context.txt
stop_file=$run_dir/stop
model=fake-$agent
reasoning_effort=max
variant=high
session_id=
thread_id=
turn=1
successful_turns=0
failed_turns=1
resume_count=0
max_turns=100
max_runtime=0
state=failed
last_exit=1
last_reason=进程退出码 1
EOF
    cat >"$run_dir/state.env" <<EOF
schema_version=1
run_id=$run_id
state=failed
updated_at=2026-10-21T03:10:32+0800
turn=1
session_id=
thread_id=
last_exit=1
last_reason=进程退出码 1
EOF
}

set_fake_env() {
    export FAKE_CALL_LOG=$test_root/calls.log
    export FAKE_RUN_LOG=$log_file
    export FAKE_MANIFEST=$manifest
    export FAKE_RC=0
    : >"$FAKE_CALL_LOG"
}

create_run 20261021T031022.dXBwYt codex co tasks
printf '%s\n' \
    '{"type":"thread.started","thread_id":"01a15ab8-d9ca-7a91-a09c-075ee48a9e37"}' \
    '{"type":"error","message":"exceeded retry limit, last status: 429 Too Many Requests"}' \
    '{"type":"turn.failed","error":{"message":"exceeded retry limit, last status: 429 Too Many Requests"}}' \
    >"$log_file"
set_fake_env

check_output=$("$resume_tool" --run-id 20261021T031022.dXBwYt --data-root "$data_root" --check)
assert_contains "$check_output" 'status=resumable'
assert_contains "$check_output" 'delay=10'
[[ ! -e "$run_dir/.auto-resume-attempted" ]] || fail '--check 不应写自动恢复标记'

set +e
resume_output=$(AGENT_RESUME_PROVIDER=opencode-go "$resume_tool" \
    --run-id 20261021T031022.dXBwYt --data-root "$data_root" \
    --delay 0 --timeout 10 --launcher "$fake_launcher" 2>&1)
resume_status=$?
set -e
(( resume_status == 0 )) || fail "Codex 恢复失败：$resume_output"
calls=$(<"$FAKE_CALL_LOG")
assert_contains "$calls" 'args=--resume 20261021T031022.dXBwYt --once --model fake-codex --reasoning-effort max'
assert_contains "$calls" "cwd=$workspace_root/tasks"
assert_contains "$calls" 'codex_provider=opencode-go'
assert_contains "$calls" 'resume_active=1'
assert_contains "$calls" 'auto_resume=0'
grep -Fq 'thread_id=01a15ab8-d9ca-7a91-a09c-075ee48a9e37' "$manifest" ||
    fail '未从 Codex 日志恢复 thread_id'
grep -Fq 'session_id=01a15ab8-d9ca-7a91-a09c-075ee48a9e37' "$manifest" ||
    fail '未从 Codex thread_id 补齐 session_id'
grep -Fq '"event":"resume-scheduled"' "$event_file" || fail '缺少 resume-scheduled 事件'
grep -Fq '"event":"resume-start"' "$event_file" || fail '缺少 resume-start 事件'
grep -Fq '"event":"resume-end"' "$event_file" || fail '缺少 resume-end 事件'
printf 'PASS: Codex 429 中断在默认策略下可检测并恢复原 thread\n'

before_calls=$(cksum "$FAKE_CALL_LOG")
set +e
duplicate_output=$("$resume_tool" --run-id 20261021T031022.dXBwYt --data-root "$data_root" \
    --delay 0 --launcher "$fake_launcher" 2>&1)
duplicate_status=$?
set -e
(( duplicate_status == 4 )) || fail "重复自动恢复应被单次标记阻止：$duplicate_output"
[[ "$(cksum "$FAKE_CALL_LOG")" == "$before_calls" ]] || fail '重复调度不应再次调用 launcher'
printf 'PASS: 同一 run 只自动恢复一次\n'

create_run 20261021T040000.authn codex co tasks
printf '%s\n' 'HTTP 401 Unauthorized' >"$log_file"
set_fake_env
set +e
auth_output=$("$resume_tool" --run-id 20261021T040000.authn --data-root "$data_root" --check --launcher "$fake_launcher" 2>&1)
auth_status=$?
set -e
(( auth_status == 3 )) || fail "认证失败不应被当作瞬时中断：$auth_output"
assert_contains "$auth_output" 'reason=non_transient_failure'
printf 'PASS: 认证错误等永久失败不会被误恢复\n'

create_run 20261021T040100.alive codex co tasks
printf '%s\n' '429 Too Many Requests' >"$log_file"
printf '%s\n' "$$" >"$run_dir/.lock"
set_fake_env
set +e
alive_output=$("$resume_tool" --run-id 20261021T040100.alive --data-root "$data_root" --check --launcher "$fake_launcher" 2>&1)
alive_status=$?
set -e
(( alive_status == 4 )) || fail "存活 run 不应被恢复：$alive_output"
assert_contains "$alive_output" 'reason=agent_alive'
rm -f -- "$run_dir/.lock"
printf 'PASS: 仍在运行的 agent 不会被重复启动\n'

create_run 20261021T040200.child opencode op tasks/subagent worker
printf '%s\n' \
    'session.id=ses_dispatch_child' \
    'exceeded retry limit, last status: 429 Too Many Requests' \
    >"$log_file"
set_fake_env
set +e
child_output=$(AGENT_RESUME_PROVIDER=opencode-go "$resume_tool" \
    --run-id 20261021T040200.child --data-root "$data_root" \
    --delay 0 --timeout 10 --launcher "$fake_launcher" 2>&1)
child_status=$?
set -e
(( child_status == 0 )) || fail "派发子 agent 恢复失败：$child_output"
calls=$(<"$FAKE_CALL_LOG")
assert_contains "$calls" 'args=--resume 20261021T040200.child --once --model fake-opencode --variant high'
assert_contains "$calls" "cwd=$workspace_root/tasks/subagent"
assert_contains "$calls" 'opencode_provider=opencode-go'
grep -Fq 'session_id=ses_dispatch_child' "$manifest" || fail '未恢复派发子 agent 的 session_id'
printf 'PASS: 派发子 agent 的 manifest/log 使用同一恢复路径\n'

create_run 20261021T040300.nosession codex co tasks
printf '%s\n' '429 Too Many Requests' >"$log_file"
set_fake_env
set +e
nosession_output=$("$resume_tool" --run-id 20261021T040300.nosession --data-root "$data_root" --check --launcher "$fake_launcher" 2>&1)
nosession_status=$?
set -e
(( nosession_status == 3 )) || fail "缺少会话标识时不应启动恢复：$nosession_output"
assert_contains "$nosession_output" 'reason=session_missing'
printf 'PASS: 无 session/thread 的中断会 fail-closed\n'

set +e
missing_output=$("$resume_tool" --run-id 20261021T049999.missing --data-root "$data_root" --check 2>&1)
missing_status=$?
set -e
(( missing_status == 6 )) || fail "不存在的 run 应返回 6：$missing_output"
assert_contains "$missing_output" 'reason=run_missing'
printf 'PASS: 显式指定的不存在 run 返回稳定退出码\n'

create_run 20261021T040400.timeout codex co tasks
printf '%s\n' \
    '{"type":"thread.started","thread_id":"01a15ab8-timeout-thread"}' \
    '{"type":"error","message":"exceeded retry limit, last status: 429 Too Many Requests"}' \
    >"$log_file"
set_fake_env
export FAKE_SLEEP=10
set +e
timeout_output=$("$resume_tool" --run-id 20261021T040400.timeout --data-root "$data_root" \
    --delay 0 --timeout 1 --launcher "$fake_launcher" 2>&1)
timeout_status=$?
set -e
unset FAKE_SLEEP
(( timeout_status == 124 )) || fail "恢复超时应返回 124：$timeout_output"
timed_pid=$(sed -n 's/^pid=//p' "$FAKE_CALL_LOG" | head -1)
[[ -n "$timed_pid" ]] || fail '超时测试未记录 launcher PID'
if kill -0 "$timed_pid" 2>/dev/null; then
    fail "恢复超时后 launcher 仍存活：pid=$timed_pid"
fi
printf 'PASS: 恢复 launcher 受硬超时约束且超时后进程已清理\n'

printf 'PASS: agent-resume.sh 检测、单次限制、身份恢复与子 agent 覆盖全部通过\n'
