#!/usr/bin/env bash

set -Eeuo pipefail

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
printf 'dispatch-result' > "${AGENT_DISPATCH_OUTPUT_FILE:?}"
printf 'fake launcher output\n'
exit "${FAKE_RC:-0}"
EOF
    chmod 0755 "$path"
}

make_fake op
make_fake co
make_fake cl
make_fake cos
mkdir -p "$test_root/data/runs/fake-run"
printf 'state=finished\n' > "$test_root/data/runs/fake-run/manifest.env"
export FAKE_ARGS="$test_root/args"
export FAKE_TASK="$test_root/task"
export FAKE_LOG="$test_root/data/runs/fake-run/agent.log"
: > "$FAKE_LOG"

output=$(AGENT_PARENT_AGENT=opencode AGENT_PARENT_PROVIDER=go \
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

output=$(AGENT_PARENT_AGENT=opencode AGENT_PARENT_PROVIDER=go \
    AGENT_PARENT_MODEL=glm-5.3-flash AGENT_PARENT_STRENGTH=high \
    AGENT_PARENT_CWD="$test_root/work" AGENT_PARENT_DATA_ROOT="$test_root/data" \
    "$test_root/agent-dispatch.sh" --agent co --provider zen \
    --model gpt-5.6-luna --strength max --no-secure --task 'override' --json)
printf '%s' "$output" | python3 -c '
import json,sys
x=json.load(sys.stdin)
assert x["agent"]=="co" and x["provider"]=="zen"
assert x["model"]=="gpt-5.6-luna" and x["strength"]=="max"
' || { printf 'FAIL: 显式覆盖 JSON 不正确：%s\n' "$output" >&2; exit 1; }
grep -Fq -- '--once zen --model gpt-5.6-luna --reasoning-effort max' "$FAKE_ARGS"

output=$(AGENT_PARENT_AGENT=opencode AGENT_PARENT_PROVIDER=go \
    AGENT_PARENT_MODEL=glm-5.3-flash AGENT_PARENT_STRENGTH=high \
    AGENT_PARENT_CWD="$test_root/work" AGENT_PARENT_DATA_ROOT="$test_root/data" \
    "$test_root/agent-dispatch.sh" --agent cl --provider go \
    --model glm-5.3-flash --strength low --no-secure --task 'cl override' --json)
grep -Fq -- '--once go glm-5.3-flash low' "$FAKE_ARGS"

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

printf 'say via file' > "$test_root/task-file"
text=$(AGENT_PARENT_AGENT=opencode AGENT_PARENT_PROVIDER=go \
    AGENT_PARENT_MODEL=glm-5.3-flash AGENT_PARENT_STRENGTH=high \
    AGENT_PARENT_CWD="$test_root/work" AGENT_PARENT_DATA_ROOT="$test_root/data" \
    "$test_root/agent-dispatch.sh" --task-file "$test_root/task-file" --text)
[[ "$text" == dispatch-result ]] || { printf 'FAIL: --text 返回不正确：%s\n' "$text" >&2; exit 1; }

printf 'PASS: agent-dispatch.sh 默认继承、显式覆盖、task-file 与 JSON 结果\n'
