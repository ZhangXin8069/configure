#!/usr/bin/env bash

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
launcher="$script_dir/agent.sh"
status_script="$script_dir/agent-status.sh"
test_root=$(mktemp -d "${TMPDIR:-/tmp}/agent-launcher-test.XXXXXX")

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
        *) fail "输出缺少：$2\n实际输出：\n$1" ;;
    esac
}

assert_file_contains() {
    [[ -f "$1" ]] || fail "文件不存在：$1"
    assert_contains "$(cat -- "$1")" "$2"
}

make_fake() {
    local name="$1"
    local script="$test_root/${name}.sh"
    cat > "$script" <<'EOF'
#!/usr/bin/env bash
set -u
printf '%s\t%s\n' "$0" "$*" >> "$FAKE_CALL_LOG"
if [[ "${FAKE_FAIL_RESUMES:-0}" == 1 &&
      "$(basename -- "$0")" == fake-codex.sh &&
      "$*" == *'exec resume'* ]]; then
    fail_count=0
    if [[ -r "${FAKE_FAIL_COUNT_FILE:-}" ]]; then
        fail_count="$(cat -- "$FAKE_FAIL_COUNT_FILE")"
    fi
    [[ "$fail_count" =~ ^[0-9]+$ ]] || fail_count=0
    fail_count=$((fail_count + 1))
    printf '%s\n' "$fail_count" > "${FAKE_FAIL_COUNT_FILE}"
    printf 'simulated resume failure %s\n' "$fail_count" >&2
    exit 7
fi
case "$(basename -- "$0")" in
    fake-codex.sh)
        printf '{"type":"thread.started","thread_id":"thread-fake"}\n'
        ;;
    fake-opencode.sh)
        printf 'timestamp=x level=INFO session.id=session-fake message=started\n' >&2
        ;;
    fake-claude.sh)
        printf 'session_id=session-fake\n' >&2
        ;;
esac
exit 0
EOF
    chmod 0755 "$script"
    printf '%s\n' "$script"
}

repo="$test_root/repo"
data="$test_root/data"
mkdir -p "$repo/nested" "$data"
git -C "$repo" init -q
printf '%s\n' '# root instructions' > "$repo/AGENTS.md"
printf '%s\n' '# nested instructions' > "$repo/nested/AGENTS.md"
printf '%s\n' 'first instruction' > "$repo/first.txt"
call_log="$test_root/calls.log"
: > "$call_log"

call_count() {
    awk -F '\t' '$1 ~ /fake-.*[.]sh$/ {n++} END {print n + 0}' "$call_log"
}

fake_codex=$(make_fake fake-codex)
fake_opencode=$(make_fake fake-opencode)
fake_claude=$(make_fake fake-claude)

run_launcher() {
    local name="$1"
    shift
    local binary="$1"
    shift
    ln -sf "$launcher" "$test_root/$name"
    case "$name" in
        co) (cd "$repo/nested" && \
            AGENT_DATA_DIR="$data" AGENT_SCRIPT_DIR="$script_dir" \
            FAKE_CALL_LOG="$call_log" \
            FAKE_FAIL_RESUMES="${FAKE_FAIL_RESUMES:-}" \
            FAKE_FAIL_COUNT_FILE="${FAKE_FAIL_COUNT_FILE:-}" \
            CODEX_BIN="$binary" \
            "$test_root/$name" "$@") ;;
        op) (cd "$repo/nested" && \
            AGENT_DATA_DIR="$data" AGENT_SCRIPT_DIR="$script_dir" \
            FAKE_CALL_LOG="$call_log" \
            FAKE_FAIL_RESUMES="${FAKE_FAIL_RESUMES:-}" \
            FAKE_FAIL_COUNT_FILE="${FAKE_FAIL_COUNT_FILE:-}" \
            OPENCODE_BIN="$binary" \
            "$test_root/$name" "$@") ;;
        cl) (cd "$repo/nested" && \
            AGENT_DATA_DIR="$data" AGENT_SCRIPT_DIR="$script_dir" \
            FAKE_CALL_LOG="$call_log" \
            FAKE_FAIL_RESUMES="${FAKE_FAIL_RESUMES:-}" \
            FAKE_FAIL_COUNT_FILE="${FAKE_FAIL_COUNT_FILE:-}" \
            CLAUDE_BIN="$binary" \
            "$test_root/$name" "$@") ;;
        *) fail "未知测试 launcher：$name" ;;
    esac
}

set +e
codex_output=$(run_launcher co "$fake_codex" --once --model fake-model --reasoning-effort low 2>&1)
codex_status=$?
set -e
(( codex_status == 0 )) || fail "Codex fake launcher 失败：$codex_output"
assert_contains "$codex_output" 'run:'
assert_contains "$codex_output" 'state:'
assert_contains "$codex_output" 'context: 2 层说明文件'
assert_contains "$codex_output" 'max-turns=100'

codex_run_id=$(printf '%s\n' "$codex_output" | sed -n 's/^  run: //p' | head -1)
codex_run="$data/runs/$codex_run_id"
[[ -n "$codex_run" ]] || fail 'Codex run 目录未创建'
assert_file_contains "$codex_run/manifest.env" 'state=finished'
assert_file_contains "$codex_run/manifest.env" 'model=fake-model'
assert_file_contains "$codex_run/context.txt" 'nested/AGENTS.md'
assert_file_contains "$codex_run/context.txt" 'repo/AGENTS.md'
assert_file_contains "$codex_run/events.jsonl" '"event":"session-end"'
assert_file_contains "$call_log" '--model fake-model'
printf 'PASS: Codex --once、模型覆盖、分层上下文和持久状态\n'

set +e
resume_output=$(run_launcher co "$fake_codex" --resume "$codex_run_id" --once 2>&1)
resume_status=$?
set -e
(( resume_status == 0 )) || fail "Codex resume fake launcher 失败：$resume_output"
assert_file_contains "$codex_run/manifest.env" 'resume_count=1'
assert_file_contains "$codex_run/events.jsonl" '"event":"session-resume"'
assert_file_contains "$call_log" 'exec resume'
assert_contains "$(tail -1 "$call_log")" 'exec resume --model fake-model'
printf 'PASS: Codex --resume 复用 session 并追加生命周期事件\n'

manifest_backup="$test_root/manifest.env.bak"
cp -- "$codex_run/manifest.env" "$manifest_backup"
awk 'BEGIN {done=0} /^run_id=/ {print "run_id=other-run"; done=1; next} {print} END {if (!done) print "run_id=other-run"}' \
    "$manifest_backup" > "$codex_run/manifest.env"
set +e
run_id_mismatch_output=$(run_launcher co "$fake_codex" --resume "$codex_run_id" --once 2>&1)
run_id_mismatch_status=$?
set -e
cp -- "$manifest_backup" "$codex_run/manifest.env"
(( run_id_mismatch_status != 0 )) || fail 'manifest run_id 与目录名不一致时不应恢复'
assert_contains "$run_id_mismatch_output" 'run_id='
printf 'PASS: manifest run_id 错配会拒绝恢复\n'

stale_pid=999999
while kill -0 "$stale_pid" 2>/dev/null; do
    stale_pid=$((stale_pid + 1))
done
printf '%s\n' "$stale_pid" > "$codex_run/.lock"
set +e
stale_output=$(run_launcher co "$fake_codex" --resume "$codex_run_id" --once 2>&1)
stale_status=$?
set -e
(( stale_status == 0 )) || fail "stale lock 恢复失败：$stale_output"
assert_file_contains "$codex_run/manifest.env" 'resume_count=2'
[[ ! -e "$codex_run/.lock" ]] || fail 'stale lock 恢复后不应残留锁文件'
printf 'PASS: Unix stale lock 可回收且不阻塞恢复\n'

printf '%s\n' "$$" > "$codex_run/.lock"
set +e
busy_output=$(run_launcher co "$fake_codex" --resume "$codex_run_id" --once 2>&1)
busy_status=$?
set -e
(( busy_status == 75 )) || fail "并发锁冲突应返回 75，实际为 ${busy_status}：${busy_output}"
[[ -f "$codex_run/.lock" ]] || fail '锁获取失败时不应删除其他进程的锁'
assert_contains "$(cat "$codex_run/.lock")" "$$"
rm -f -- "$codex_run/.lock"
printf 'PASS: 锁获取失败时不会误删 owner 的锁\n'

release_lock_dir="$test_root/release-lock"
mkdir -p "$release_lock_dir"
set +e
release_lock_output=$(bash -c '
    set -Eeuo pipefail
    runtime="$1"
    run_dir="$2"
    source "$runtime"
    _NAME=co
    AGENT_RUN_ID=release-test
    AGENT_RUN_DIR="$run_dir"
    AGENT_RUNTIME_STATE=finished
    _agent_runtime_acquire_lock
    printf "%s\n" "other-owner" > "$AGENT_LOCK_FILE"
    _agent_runtime_on_exit 0
' bash "$script_dir/agent-runtime.sh" "$release_lock_dir" 2>&1)
release_lock_status=$?
set -e
(( release_lock_status == 0 )) || fail "非 owner 锁释放测试失败：$release_lock_output"
assert_contains "$(cat -- "$release_lock_dir/.lock")" 'other-owner'
printf 'PASS: 退出清理不会释放非本进程 owner 的锁\n'

set +e
agent_mismatch_output=$(run_launcher op "$fake_opencode" --resume "$codex_run_id" --once 2>&1)
agent_mismatch_status=$?
set -e
(( agent_mismatch_status != 0 )) || fail '不同 agent 不应恢复同一 run'
assert_contains "$agent_mismatch_output" 'agent='
printf 'PASS: 不同 agent 的恢复请求被拒绝\n'

other_repo="$test_root/other-repo"
mkdir -p "$other_repo"
git -C "$other_repo" init -q
set +e
workspace_mismatch_output=$(cd "$other_repo" && \
    AGENT_DATA_DIR="$data" AGENT_SCRIPT_DIR="$script_dir" \
    FAKE_CALL_LOG="$call_log" CODEX_BIN="$fake_codex" \
    "$test_root/co" --resume "$codex_run_id" --once 2>&1)
workspace_mismatch_status=$?
set -e
(( workspace_mismatch_status != 0 )) || fail '不同 workspace 不应恢复同一 run'
assert_contains "$workspace_mismatch_output" 'workspace_root='
printf 'PASS: 不同 workspace 的恢复请求被拒绝\n'

set +e
op_output=$(run_launcher op "$fake_opencode" --once --file "$repo/first.txt" --time 1s 2>&1)
op_status=$?
set -e
(( op_status == 0 )) || fail "OpenCode fake launcher 失败：$op_output"
assert_contains "$op_output" 'user-input list:'
op_run_id=$(printf '%s\n' "$op_output" | sed -n 's/^  run: //p' | head -1)
op_run="$data/runs/$op_run_id"
assert_file_contains "$op_run/manifest.env" 'agent=opencode'
assert_file_contains "$op_run/manifest.env" 'state=finished'
assert_file_contains "$op_run/inputs.txt" ''
assert_file_contains "$call_log" 'first instruction'
printf 'PASS: OpenCode --once、文件指令和数据目录隔离\n'

set +e
cl_output=$(run_launcher cl "$fake_claude" --once --file "$repo/first.txt" 2>&1)
cl_status=$?
set -e
(( cl_status == 0 )) || fail "Claude fake launcher 失败：$cl_output"
cl_run_id=$(printf '%s\n' "$cl_output" | sed -n 's/^  run: //p' | head -1)
cl_run="$data/runs/$cl_run_id"
assert_file_contains "$cl_run/manifest.env" 'agent=claude'
assert_file_contains "$cl_run/manifest.env" 'session_id=session-fake'
assert_file_contains "$cl_run/events.jsonl" '"event":"session-bound"'
printf 'PASS: Claude --once、session 绑定和持久事件\n'

max_turns_before=$(call_count)
set +e
max_turns_output=$(run_launcher co "$fake_codex" --time 1s --max-turns 1 2>&1)
max_turns_status=$?
set -e
(( max_turns_status == 0 )) || fail "max-turns fake launcher 失败：$max_turns_output"
max_turns_run_id=$(printf '%s\n' "$max_turns_output" | sed -n 's/^  run: //p' | head -1)
max_turns_run="$data/runs/$max_turns_run_id"
assert_file_contains "$max_turns_run/manifest.env" 'state=finished'
assert_file_contains "$max_turns_run/manifest.env" 'last_reason=达到 max-turns=1'
max_turns_delta=$(( $(call_count) - max_turns_before ))
(( max_turns_delta == 2 )) || fail "max-turns 应执行初始回合+1 次继续，实际调用数：$max_turns_delta"
printf 'PASS: max-turns 限制继续回合数\n'

max_runtime_before=$(call_count)
set +e
max_runtime_output=$(run_launcher co "$fake_codex" --time 2s --max-runtime 1 2>&1)
max_runtime_status=$?
set -e
(( max_runtime_status == 0 )) || fail "max-runtime fake launcher 失败：$max_runtime_output"
max_runtime_run_id=$(printf '%s\n' "$max_runtime_output" | sed -n 's/^  run: //p' | head -1)
max_runtime_run="$data/runs/$max_runtime_run_id"
assert_file_contains "$max_runtime_run/manifest.env" 'state=finished'
assert_file_contains "$max_runtime_run/manifest.env" 'last_reason=达到 max-runtime=1s'
max_runtime_delta=$(( $(call_count) - max_runtime_before ))
(( max_runtime_delta == 1 )) || fail "max-runtime 到期后不应多发继续回合，实际调用数：$max_runtime_delta"
printf 'PASS: max-runtime 在等待后阻止额外回合\n'

fail_count_file="$test_root/fail-count"
: > "$fail_count_file"
set +e
blocked_output=$(FAKE_FAIL_RESUMES=1 FAKE_FAIL_COUNT_FILE="$fail_count_file" \
    run_launcher co "$fake_codex" --time 1s 2>&1)
blocked_status=$?
set -e
(( blocked_status != 0 )) || fail '连续 resume 失败应返回非零状态'
blocked_run_id=$(printf '%s\n' "$blocked_output" | sed -n 's/^  run: //p' | head -1)
blocked_run="$data/runs/$blocked_run_id"
assert_file_contains "$blocked_run/manifest.env" 'state=blocked'
assert_file_contains "$blocked_run/manifest.env" 'failed_turns=3'
assert_file_contains "$blocked_run/manifest.env" 'last_exit=7'
assert_file_contains "$blocked_run/events.jsonl" '"status":"blocked"'
printf 'PASS: 连续三次继续失败进入 blocked 终态\n'

stop_file="$test_root/stop"
touch "$stop_file"
set +e
stop_output=$(AGENT_DATA_DIR="$data" AGENT_SCRIPT_DIR="$script_dir" \
    FAKE_CALL_LOG="$call_log" CODEX_BIN="$fake_codex" AGENT_STOP_PATH="$stop_file" \
    "$test_root/co" --time 1s --max-turns 2 --stop-file "$stop_file" 2>&1)
stop_status=$?
set -e
(( stop_status == 0 )) || fail "stop-file fake launcher 失败：$stop_output"
assert_contains "$stop_output" 'run:'
stop_run_id=$(printf '%s\n' "$stop_output" | sed -n 's/^  run: //p' | head -1)
stop_run="$data/runs/$stop_run_id"
assert_file_contains "$stop_run/manifest.env" 'state=stopped'
assert_file_contains "$stop_run/events.jsonl" '"event":"session-stop"'

status_json=$(AGENT_DATA_DIR="$data" "$status_script" --all --json)
if ! printf '%s\n' "$status_json" | jq -e 'length == 7 and all(.[]; .run_id != "")' >/dev/null; then
    fail "agent-status JSON 结果不完整：$status_json"
fi
printf 'PASS: stop-file 与 agent-status JSON 只读查询\n'

if find "$repo" -maxdepth 1 -name '.agent.*' -print | grep -q .; then
    fail '工作目录不应生成 .agent.* 运行产物'
fi
printf 'PASS: 工作目录无运行时垃圾\n'
