#!/usr/bin/env bash

set -Eeuo pipefail

# 屏蔽宿主 agent 的继承上下文，保证断言只反映本测试显式设置的父配置。
unset AGENT_PARENT_LAUNCHER AGENT_PARENT_AGENT AGENT_PARENT_PROVIDER AGENT_PARENT_MODEL \
      AGENT_PARENT_STRENGTH AGENT_PARENT_CWD AGENT_PARENT_WORKSPACE AGENT_PARENT_DATA_ROOT \
      AGENT_PARENT_RUN_ID AGENT_PARENT_MANIFEST AGENT_PARENT_SECURE AGENT_PARENT_SANDBOX \
      AGENT_PARENT_APPROVAL AGENT_PARENT_PERMISSION_MODE AGENT_DISPATCH_TIMEOUT \
      AGENT_DISPATCH_RESUME_ATTEMPTS 2>/dev/null || true

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
test_root=$(mktemp -d "${TMPDIR:-/tmp}/agent-dispatch-test.XXXXXX")
cleanup() {
    rm -rf -- "$test_root"
}
trap cleanup EXIT HUP INT TERM

mkdir -p "$test_root/work"
ln -sf "$script_dir/agent-dispatch.sh" "$test_root/agent-dispatch.sh"

make_fake() {
    local name="$1"
    local path="$test_root/$name"
    cat > "$path" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" > "${FAKE_ARGS:?}"
printf '%s' "${AGENT_DISPATCH_TASK:-}" > "${FAKE_TASK:?}"
printf '%s' "${AGENT_DISPATCH_MINIMAL:-}" > "${FAKE_MINIMAL:?}"
printf 'dispatch-result' > "${AGENT_DISPATCH_OUTPUT_FILE:?}"
printf 'fake launcher output\n'
exit "${FAKE_RC:-0}"
EOF
    chmod 0755 "$path"
}

make_fake op
make_fake co
make_fake cl
make_fake cm
make_fake cos
make_fake cms
mkdir -p "$test_root/data/runs/fake-run"
printf 'state=finished\n' > "$test_root/data/runs/fake-run/manifest.env"
export FAKE_ARGS="$test_root/args"
export FAKE_TASK="$test_root/task"
export FAKE_MINIMAL="$test_root/minimal"
export FAKE_LOG="$test_root/data/runs/fake-run/agent.log"
: > "$FAKE_LOG"

output=$(AGENT_DISPATCH_MINIMAL=0 AGENT_PARENT_AGENT=opencode AGENT_PARENT_PROVIDER=go \
    AGENT_PARENT_MODEL=glm-5.3-flash AGENT_PARENT_STRENGTH=high \
    AGENT_PARENT_CWD="$test_root/work" AGENT_PARENT_DATA_ROOT="$test_root/data" \
    "$test_root/agent-dispatch.sh" --task 'say hi' --json)
printf '%s' "$output" | python3 -c '
import json,sys
x=json.load(sys.stdin)
assert x["agent"]=="op"
assert x["provider"]=="go"
assert x["model"]=="glm-5.3-flash"
assert x["strength"]=="high"
assert x["result"]=="dispatch-result"
assert x["ok"] is True
' || { printf 'FAIL: 默认继承 JSON 不正确：%s\n' "$output" >&2; exit 1; }
grep -Fq -- "--once go --model glm-5.3-flash --variant high" "$FAKE_ARGS"
grep -Fxq -- 'say hi' "$FAKE_TASK"
grep -Fxq -- '1' "$FAKE_MINIMAL"

output=$(AGENT_PARENT_AGENT=opencode AGENT_PARENT_PROVIDER=go \
    AGENT_PARENT_MODEL=glm-5.3-flash AGENT_PARENT_STRENGTH=high \
    AGENT_PARENT_CWD="$test_root/work" AGENT_PARENT_DATA_ROOT="$test_root/data" \
    "$test_root/agent-dispatch.sh" --agent co --provider pay \
    --model deepseek-flash --strength max --no-secure --task 'override' --json)
printf '%s' "$output" | python3 -c '
import json,sys
x=json.load(sys.stdin)
assert x["agent"]=="co" and x["provider"]=="pay"
assert x["model"]=="deepseek-flash" and x["strength"]=="max"
' || { printf 'FAIL: 显式覆盖 JSON 不正确：%s\n' "$output" >&2; exit 1; }
grep -Fq -- '--once pay --model deepseek-flash --reasoning-effort max' "$FAKE_ARGS"

output=$(AGENT_PARENT_AGENT=opencode AGENT_PARENT_PROVIDER=go \
    AGENT_PARENT_MODEL=glm-5.3-flash AGENT_PARENT_STRENGTH=high \
    AGENT_PARENT_CWD="$test_root/work" AGENT_PARENT_DATA_ROOT="$test_root/data" \
    "$test_root/agent-dispatch.sh" --agent cl --provider go \
    --model glm-5.3-flash --strength low --no-secure --task 'cl override' --json)
grep -Fq -- '--once go glm-5.3-flash low' "$FAKE_ARGS"

output=$(AGENT_PARENT_AGENT=codex AGENT_PARENT_PROVIDER=go \
    AGENT_PARENT_MODEL=glm-5.3-flash AGENT_PARENT_STRENGTH=high \
    AGENT_PARENT_CWD="$test_root/work" AGENT_PARENT_DATA_ROOT="$test_root/data" \
    "$test_root/agent-dispatch.sh" --agent cm --provider gt \
    --model deepseek/deepseek-v4.1-flash --strength max --no-secure --task 'cm override' --json)
printf '%s' "$output" | python3 -c '
import json,sys
x=json.load(sys.stdin)
assert x["launcher"]=="cm" and x["agent"]=="cm" and x["provider"]=="gt"
assert x["model"]=="deepseek/deepseek-v4.1-flash" and x["strength"]=="max"
' || { printf 'FAIL: cm 派发 JSON 不正确：%s\n' "$output" >&2; exit 1; }
grep -Fq -- '--once gt --model deepseek/deepseek-v4.1-flash --effort max' "$FAKE_ARGS"

# 新别名 cgo/tgo/dgo 由启动器统一解析，派发接口应原样透传
output=$(AGENT_PARENT_AGENT=opencode AGENT_PARENT_PROVIDER=go \
    AGENT_PARENT_CWD="$test_root/work" AGENT_PARENT_DATA_ROOT="$test_root/data" \
    "$test_root/agent-dispatch.sh" --agent op --provider cgo \
    --model glm-5.3-flash --strength high --no-secure --task 'cgo alias' --json)
printf '%s' "$output" | python3 -c '
import json,sys
x=json.load(sys.stdin)
assert x["provider"]=="cgo" and x["agent"]=="op"
' || { printf 'FAIL: cgo 派发 JSON 不正确：%s\n' "$output" >&2; exit 1; }
grep -Fq -- '--once cgo --model glm-5.3-flash --variant high' "$FAKE_ARGS"

output=$(AGENT_PARENT_AGENT=codex AGENT_PARENT_PROVIDER=go \
    AGENT_PARENT_CWD="$test_root/work" AGENT_PARENT_DATA_ROOT="$test_root/data" \
    "$test_root/agent-dispatch.sh" --agent co --provider tgo \
    --model deepseek/deepseek-v4.1-flash --strength max --no-secure --task 'tgo alias' --json)
printf '%s' "$output" | python3 -c '
import json,sys
x=json.load(sys.stdin)
assert x["provider"]=="tgo" and x["agent"]=="co"
' || { printf 'FAIL: tgo 派发 JSON 不正确：%s\n' "$output" >&2; exit 1; }
grep -Fq -- '--once tgo --model deepseek/deepseek-v4.1-flash --reasoning-effort max' "$FAKE_ARGS"

output=$(AGENT_PARENT_AGENT=opencode AGENT_PARENT_PROVIDER=go \
    AGENT_PARENT_CWD="$test_root/work" AGENT_PARENT_DATA_ROOT="$test_root/data" \
    "$test_root/agent-dispatch.sh" --agent cm --provider dgo \
    --model dgo-test-model --strength max --no-secure --task 'dgo alias' --json)
printf '%s' "$output" | python3 -c '
import json,sys
x=json.load(sys.stdin)
assert x["provider"]=="dgo" and x["agent"]=="cm"
' || { printf 'FAIL: dgo 派发 JSON 不正确：%s\n' "$output" >&2; exit 1; }
grep -Fq -- '--once dgo --model dgo-test-model --effort max' "$FAKE_ARGS"

output=$(AGENT_PARENT_AGENT=commandcode AGENT_PARENT_PROVIDER=gt \
    AGENT_PARENT_PERMISSION_MODE=accept-edits \
    AGENT_PARENT_CWD="$test_root/work" AGENT_PARENT_DATA_ROOT="$test_root/data" \
    "$test_root/agent-dispatch.sh" --agent cm --task 'cm permission' --json)
grep -Fq -- '--once gt --permission-mode accept-edits' "$FAKE_ARGS"

output=$(AGENT_PARENT_AGENT=commandcode AGENT_PARENT_PROVIDER=gt \
    AGENT_PARENT_MODEL=deepseek/deepseek-v4.1-flash AGENT_PARENT_STRENGTH=high \
    AGENT_PARENT_CWD="$test_root/work" AGENT_PARENT_DATA_ROOT="$test_root/data" \
    "$test_root/agent-dispatch.sh" --agent co --no-secure --task 'cross agent' --json)
grep -Fxq -- '--once gt' "$FAKE_ARGS" || {
    printf 'FAIL: 跨 agent 未回落目标默认模型/强度：%s\n' "$(cat "$FAKE_ARGS")" >&2
    exit 1
}

output=$(AGENT_PARENT_AGENT=codex AGENT_PARENT_LAUNCHER=cos \
    AGENT_PARENT_PROVIDER=go AGENT_PARENT_MODEL=glm-5.3-flash \
    AGENT_PARENT_STRENGTH=high AGENT_PARENT_SECURE=1 \
    AGENT_PARENT_SANDBOX=danger-full-access AGENT_PARENT_APPROVAL=never \
    AGENT_PARENT_CWD="$test_root/work" AGENT_PARENT_DATA_ROOT="$test_root/data" \
    "$test_root/agent-dispatch.sh" --task 'secure inherit' --json)
printf '%s' "$output" | python3 -c '
import json,sys
x=json.load(sys.stdin)
assert x["launcher"]=="cos" and x["agent"]=="co"
' || { printf 'FAIL: secure launcher 继承失败：%s\n' "$output" >&2; exit 1; }
grep -Fq -- '--sandbox danger-full-access' "$FAKE_ARGS"
grep -Fq -- '--ask-for-approval never' "$FAKE_ARGS"

output=$(AGENT_PARENT_AGENT=commandcode AGENT_PARENT_LAUNCHER=cms \
    AGENT_PARENT_PROVIDER=gt AGENT_PARENT_MODEL=deepseek/deepseek-v4.1-flash \
    AGENT_PARENT_STRENGTH=max AGENT_PARENT_SECURE=1 \
    AGENT_PARENT_CWD="$test_root/work" AGENT_PARENT_DATA_ROOT="$test_root/data" \
    "$test_root/agent-dispatch.sh" --agent cm --task 'cm secure inherit' --json)
printf '%s' "$output" | python3 -c '
import json,sys
x=json.load(sys.stdin)
assert x["launcher"]=="cms" and x["agent"]=="cm"
' || { printf 'FAIL: cm secure launcher 继承失败：%s\n' "$output" >&2; exit 1; }

output=$(AGENT_PARENT_AGENT=commandcode AGENT_PARENT_LAUNCHER=cms \
    AGENT_PARENT_PROVIDER=gt AGENT_PARENT_SECURE=1 \
    AGENT_PARENT_CWD="$test_root/work" AGENT_PARENT_DATA_ROOT="$test_root/data" \
    "$test_root/agent-dispatch.sh" --agent co --task 'cross secure' --json)
printf '%s' "$output" | python3 -c '
import json,sys
x=json.load(sys.stdin)
assert x["launcher"]=="co" and x["agent"]=="co"
' || { printf 'FAIL: 跨 agent 未回落非 secure launcher：%s\n' "$output" >&2; exit 1; }

printf 'say via file' > "$test_root/task-file"
text=$(AGENT_PARENT_AGENT=opencode AGENT_PARENT_PROVIDER=go \
    AGENT_PARENT_MODEL=glm-5.3-flash AGENT_PARENT_STRENGTH=high \
    AGENT_PARENT_CWD="$test_root/work" AGENT_PARENT_DATA_ROOT="$test_root/data" \
    "$test_root/agent-dispatch.sh" --task-file "$test_root/task-file" --text)
[[ "$text" == dispatch-result ]] || { printf 'FAIL: --text 返回不正确：%s\n' "$text" >&2; exit 1; }

resume_run=20261021T060000.dispatch
resume_run_dir=$test_root/data/runs/$resume_run
mkdir -p "$resume_run_dir"
cat > "$test_root/co" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
run_id=20261021T060000.dispatch
run_dir=${AGENT_PARENT_DATA_ROOT:?}/runs/${run_id}
mkdir -p "$run_dir"
cat > "$run_dir/agent.log" <<'LOG'
{"type":"thread.started","thread_id":"01a15ab8-dispatch-thread"}
{"type":"error","message":"exceeded retry limit, last status: 429 Too Many Requests"}
LOG
cat > "$run_dir/manifest.env" <<MANIFEST
schema_version=1
run_id=$run_id
agent=codex
launcher=co
mode=drive
role=worker
workspace_root=$PWD
cwd=$PWD
data_root=${AGENT_PARENT_DATA_ROOT:?}
run_dir=$run_dir
log_file=$run_dir/agent.log
event_file=$run_dir/events.jsonl
stop_file=$run_dir/stop
model=glm-5.3-flash
reasoning_effort=high
variant=
session_id=
thread_id=
turn=1
state=failed
last_exit=7
last_reason=进程退出码 7
MANIFEST
: > "$run_dir/events.jsonl"
printf 'run: %s\nlog: %s\n' "$run_id" "$run_dir/agent.log"
exit 7
EOF
chmod 0755 "$test_root/co"

resume_fake=$test_root/resume-co
cat > "$resume_fake" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
printf 'args=%s\n' "$*" > "${RESUME_FAKE_ARGS:?}"
printf 'cwd=%s\n' "$PWD" >> "$RESUME_FAKE_ARGS"
printf 'provider=%s\n' "${CODEX_PROVIDER_ID:-}" >> "$RESUME_FAKE_ARGS"
printf '%s\n' '{"type":"item.completed","item":{"type":"agent_message","text":"dispatch-resume-ok"}}' \
    >> "$RESUME_FAKE_LOG"
awk '
    BEGIN { done = 0 }
    /^state=/ { print "state=finished"; done = 1; next }
    { print }
    END { if (!done) print "state=finished" }
' "${RESUME_FAKE_MANIFEST:?}" > "${RESUME_FAKE_MANIFEST}.tmp"
mv -f -- "${RESUME_FAKE_MANIFEST}.tmp" "${RESUME_FAKE_MANIFEST}"
EOF
chmod 0755 "$resume_fake"

export RESUME_FAKE_ARGS=$test_root/resume-args
export RESUME_FAKE_LOG=$resume_run_dir/agent.log
export RESUME_FAKE_MANIFEST=$resume_run_dir/manifest.env
set +e
resumed_output=$(AGENT_PARENT_AGENT=codex AGENT_PARENT_PROVIDER=go \
    AGENT_PARENT_MODEL=glm-5.3-flash AGENT_PARENT_STRENGTH=high \
    AGENT_PARENT_CWD="$test_root/work" AGENT_PARENT_DATA_ROOT="$test_root/data" \
    AGENT_RESUME_TOOL="$script_dir/../tools/agent-resume.sh" \
    AGENT_RESUME_LAUNCHER="$resume_fake" AGENT_RESUME_DELAY=0 \
    "$test_root/agent-dispatch.sh" --task 'resume child' --json 2>"$test_root/resume-stderr")
resumed_status=$?
set -e
(( resumed_status == 0 )) || {
    printf 'FAIL: 子 agent 瞬时失败未恢复：%s\nSTDERR:\n%s\n' "$resumed_output" "$(cat "$test_root/resume-stderr")" >&2
    exit 1
}
printf '%s' "$resumed_output" | python3 -c '
import json,sys
x=json.load(sys.stdin)
assert x["ok"] is True
assert x["run_id"]=="20261021T060000.dispatch"
assert x["state"]=="finished"
assert x["result"]=="dispatch-resume-ok"
assert x["auto_resume"]["status"]=="finished"
assert x["auto_resume"]["exit_code"]==0
' || { printf 'FAIL: 子 agent 恢复 JSON 不正确：%s\n' "$resumed_output" >&2; exit 1; }
grep -Fq -- '--resume 20261021T060000.dispatch --once --model glm-5.3-flash --reasoning-effort high' \
    "$RESUME_FAKE_ARGS"
grep -Fq 'provider=go' "$RESUME_FAKE_ARGS"
grep -Fq "cwd=$test_root/work" "$RESUME_FAKE_ARGS"

printf 'PASS: agent-dispatch.sh 默认继承、显式覆盖、task-file、JSON 结果与子 agent 自动恢复\n'
