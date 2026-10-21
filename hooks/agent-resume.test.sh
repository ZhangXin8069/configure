#!/usr/bin/env bash

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
config_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
hook=$script_dir/agent-resume.sh
agent_hook=$script_dir/agent-hook.sh
resume_tool=$config_root/tools/agent-resume.sh
test_root=$(mktemp -d "${TMPDIR:-/tmp}/agent-resume-hook-test.XXXXXX")
data_root=$test_root/data
workspace=$test_root/workspace

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

mkdir -p "$data_root/runs" "$workspace"
run_id=20261021T050000.hook
run_dir=$data_root/runs/$run_id
mkdir -p "$run_dir"
manifest=$run_dir/manifest.env
log_file=$run_dir/agent.log
event_file=$run_dir/events.jsonl
cat >"$manifest" <<EOF
schema_version=1
run_id=$run_id
created_at=2026-10-21T05:00:00+0800
updated_at=2026-10-21T05:00:10+0800
agent=codex
launcher=co
mode=drive
role=solo-agent
tier=standard
posture=frontier-orchestrator
cwd=$workspace
workspace_root=$workspace
data_root=$data_root
run_dir=$run_dir
log_file=$log_file
list_file=$run_dir/inputs.txt
event_file=$event_file
context_file=$run_dir/context.txt
stop_file=$run_dir/stop
model=fake-hook
reasoning_effort=max
variant=
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
printf '%s\n' \
    '{"type":"thread.started","thread_id":"01a15ab8-hook-thread"}' \
    '{"type":"error","message":"exceeded retry limit, last status: 429 Too Many Requests"}' \
    >"$log_file"
: >"$event_file"

fake_launcher=$test_root/fake-launcher
call_log=$test_root/calls.log
cat >"$fake_launcher" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
printf '%s\n' "$*" >"${FAKE_CALL_LOG:?}"
awk '
    BEGIN { done = 0 }
    /^state=/ { print "state=finished"; done = 1; next }
    { print }
    END { if (!done) print "state=finished" }
' "${FAKE_MANIFEST:?}" >"${FAKE_MANIFEST}.tmp"
mv -f -- "${FAKE_MANIFEST}.tmp" "${FAKE_MANIFEST}"
printf '%s\n' '{"type":"item.completed","item":{"type":"agent_message","text":"hook-resumed"}}' \
    >>"${FAKE_LOG:?}"
EOF
chmod 0755 "$fake_launcher"
export FAKE_CALL_LOG=$call_log
export FAKE_MANIFEST=$manifest
export FAKE_LOG=$log_file

check_output=$(AGENT_RESUME_TOOL="$resume_tool" AGENT_RESUME_LAUNCHER="$fake_launcher" \
    "$agent_hook" agent-resume --check --run-id "$run_id" --data-root "$data_root")
assert_contains "$check_output" 'status=resumable'
[[ ! -e "$run_dir/.auto-resume-attempted" ]] || fail 'agent-resume 检查事件不应写恢复标记'

scheduled_output=$(AGENT_RESUME_TOOL="$resume_tool" AGENT_RESUME_LAUNCHER="$fake_launcher" \
    AGENT_RESUME_PROVIDER=opencode-go "$hook" --run-id "$run_id" --data-root "$data_root" --delay 0)
assert_contains "$scheduled_output" 'status=scheduled'

for _ in $(seq 1 50); do
    [[ -s "$call_log" ]] && break
    sleep 0.1
done
[[ -s "$call_log" ]] || fail "后台恢复没有调用 launcher；日志：$(cat "$run_dir/resume.log" 2>/dev/null || true)"
grep -Fq -- "--resume $run_id --once --model fake-hook --reasoning-effort max" "$call_log" ||
    fail 'hook 没有使用统一 launcher 的 resume 参数'
grep -Fq 'thread_id=01a15ab8-hook-thread' "$manifest" || fail 'hook 恢复链没有回写 thread_id'
printf 'PASS: agent-hook agent-resume 预检并异步调度统一恢复工具\n'

second_id=20261021T050100.permanent
second_dir=$data_root/runs/$second_id
mkdir -p "$second_dir"
cat >"$second_dir/manifest.env" <<EOF
schema_version=1
run_id=$second_id
agent=codex
launcher=co
workspace_root=$workspace
cwd=$workspace
data_root=$data_root
run_dir=$second_dir
log_file=$second_dir/agent.log
event_file=$second_dir/events.jsonl
stop_file=$second_dir/stop
model=fake-hook
reasoning_effort=max
session_id=
thread_id=
state=failed
last_exit=1
last_reason=进程退出码 1
EOF
printf '%s\n' \
    '{"type":"thread.started","thread_id":"01a15ab8-hook-permanent-thread"}' \
    'HTTP 401 Unauthorized' \
    >"$second_dir/agent.log"
: >"$second_dir/events.jsonl"
export FAKE_CALL_LOG=$call_log
export FAKE_MANIFEST=$second_dir/manifest.env
export FAKE_LOG=$second_dir/agent.log
: >"$call_log"
permanent_output=$(AGENT_RESUME_TOOL="$resume_tool" AGENT_RESUME_LAUNCHER="$fake_launcher" \
    "$hook" --run-id "$second_id" --data-root "$data_root" --delay 0 2>&1)
assert_contains "$permanent_output" 'status=scheduled'
for _ in $(seq 1 50); do
    [[ -s "$call_log" ]] && break
    sleep 0.1
done
[[ -s "$call_log" ]] || fail '普通失败没有启动后台恢复'
grep -Fq 'thread_id=01a15ab8-hook-permanent-thread' "$second_dir/manifest.env" ||
    fail '普通失败恢复后没有回写 thread_id'
printf 'PASS: hook 对普通意外失败同样启动后台恢复\n'

printf 'PASS: hooks/agent-resume.sh 异步调度、事件适配与普通失败恢复全部通过\n'
