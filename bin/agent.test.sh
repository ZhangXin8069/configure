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

# 屏蔽宿主环境导出的真实 key/模型变量，保证断言确定性（测试内显式前缀赋值仍可覆盖）
unset DEEPSEEK_PAY_API_KEY OPENCODE_GO_API_KEY CUSTOM_GPT_API_KEY DEEPSEEK_API_KEY LQCD_API_KEY \
      ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL ANTHROPIC_MODEL \
      ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL ANTHROPIC_DEFAULT_HAIKU_MODEL \
      CLAUDE_CODE_SUBAGENT_MODEL CLAUDE_CODE_EFFORT_LEVEL CLAUDE_MODEL OPENCODE_MODEL OPENCODE_VARIANT \
      CODEX_MODEL CODEX_REASONING_EFFORT CODEX_SANDBOX CODEX_APPROVAL CLAUDE_PROVIDER OPENCODE_PROVIDER \
      CODEX_PROVIDER_ID CODEX_PROVIDER_BASE_URL CODEX_PROVIDER_ENV_KEY OPENCODE_AUTOUPDATE \
      CODEX_CHECK_FOR_UPDATE_ON_STARTUP AGENT_ONCE 2>/dev/null || true

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

assert_file_not_contains() {
    [[ -f "$1" ]] || fail "文件不存在：$1"
    if rg -Fq -- "$2" "$1"; then
        fail "$1 不应包含：$2"
    fi
}

make_fake() {
    local name="$1"
    local script="$test_root/${name}.sh"
    cat > "$script" <<'EOF'
#!/usr/bin/env bash
set -u
# 模型目录探测调用（codex --version / codex debug models）不计入 FAKE_CALL_LOG
if [[ "$(basename -- "$0")" == fake-codex.sh ]]; then
    case "$*" in
        '--version') printf 'codex-cli 9.9.9%s\n' "${FAKE_CODEX_VERSION_SUFFIX:-}"; exit 0;;
        'debug models'*)
            if [[ "${FAKE_MODELS_REJECT:-0}" == 1 && "$*" == *' -c '* ]]; then
                exit 3
            fi
            if [[ "${FAKE_MODELS_BAD:-0}" == 1 ]]; then
                printf 'not-json\n'
            else
                printf '%s\n' '{"models":[{"slug":"gpt-5.4-mini","display_name":"GPT-5.4-Mini","context_window":272000,"priority":23,"visibility":"hide","supported_reasoning_levels":[{"effort":"low","description":"Fast responses with lighter reasoning"},{"effort":"medium","description":"Balances speed and reasoning depth"},{"effort":"high","description":"Greater reasoning depth"},{"effort":"xhigh","description":"Extra high reasoning depth"}],"base_instructions":"fake template instructions"},{"slug":"gpt-6-astra","display_name":"GPT-6-Astra","context_window":272000,"supported_reasoning_levels":[{"effort":"low","description":"Fast responses with lighter reasoning"},{"effort":"medium","description":"Balances speed and reasoning depth"},{"effort":"high","description":"Greater reasoning depth"},{"effort":"xhigh","description":"Extra high reasoning depth"},{"effort":"max","description":"Maximum reasoning depth for the hardest problems"},{"effort":"ultra","description":"Maximum reasoning depth for the hardest problems"}],"base_instructions":"fake astra instructions"}]}'
            fi
            exit 0;;
    esac
fi
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
        printf 'opencode-config: %s\n' "${OPENCODE_CONFIG_CONTENT:-}" >> "$FAKE_CALL_LOG"
        ;;
    fake-claude.sh)
        printf 'session_id=session-fake\n' >&2
        _prev=''
        for _arg in "$@"; do
            if [[ "${_prev}" == '--settings' && -f "${_arg}" ]]; then
                printf 'claude-settings: %s\n' "$(cat -- "${_arg}")" >> "$FAKE_CALL_LOG"
                printf 'claude-settings-path: %s\n' "${_arg}" >> "$FAKE_CALL_LOG"
            fi
            _prev="${_arg}"
        done
        printf 'claude-env ANTHROPIC_BASE_URL=%s ANTHROPIC_MODEL=%s ANTHROPIC_DEFAULT_OPUS_MODEL=%s ANTHROPIC_DEFAULT_SONNET_MODEL=%s ANTHROPIC_DEFAULT_HAIKU_MODEL=%s ANTHROPIC_AUTH_TOKEN=%s ANTHROPIC_API_KEY=%s CLAUDE_CODE_SUBAGENT_MODEL=%s CLAUDE_CODE_EFFORT_LEVEL=%s CLAUDE_CODE_AUTO_COMPACT_WINDOW=%s\n' \
            "${ANTHROPIC_BASE_URL:-}" "${ANTHROPIC_MODEL:-}" "${ANTHROPIC_DEFAULT_OPUS_MODEL:-}" \
            "${ANTHROPIC_DEFAULT_SONNET_MODEL:-}" "${ANTHROPIC_DEFAULT_HAIKU_MODEL:-}" \
            "${ANTHROPIC_AUTH_TOKEN:-}" "${ANTHROPIC_API_KEY:-}" "${CLAUDE_CODE_SUBAGENT_MODEL:-}" \
            "${CLAUDE_CODE_EFFORT_LEVEL:-}" "${CLAUDE_CODE_AUTO_COMPACT_WINDOW:-}" >> "$FAKE_CALL_LOG"
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
    local script_root="${AGENT_TEST_SCRIPT_DIR:-$script_dir}"
    ln -sf "$launcher" "$test_root/$name"
    case "$name" in
        co) (cd "$repo/nested" && \
            AGENT_DATA_DIR="$data" AGENT_SCRIPT_DIR="$script_root" \
            FAKE_CALL_LOG="$call_log" \
            FAKE_FAIL_RESUMES="${FAKE_FAIL_RESUMES:-}" \
            FAKE_FAIL_COUNT_FILE="${FAKE_FAIL_COUNT_FILE:-}" \
            CODEX_BIN="$binary" \
            CODEX_PROVIDER_ID="${CODEX_PROVIDER_ID:-}" \
            CODEX_PROVIDER_BASE_URL="${CODEX_PROVIDER_BASE_URL:-}" \
            CODEX_PROVIDER_ENV_KEY="${CODEX_PROVIDER_ENV_KEY:-}" \
            DEEPSEEK_API_KEY= LQCD_API_KEY= \
            "$test_root/$name" "$@") ;;
        op) (cd "$repo/nested" && \
            AGENT_DATA_DIR="$data" AGENT_SCRIPT_DIR="$script_root" \
            FAKE_CALL_LOG="$call_log" \
            FAKE_FAIL_RESUMES="${FAKE_FAIL_RESUMES:-}" \
            FAKE_FAIL_COUNT_FILE="${FAKE_FAIL_COUNT_FILE:-}" \
            OPENCODE_BIN="$binary" \
            OPENCODE_GO_API_KEY="${OPENCODE_GO_API_KEY:-}" \
            DEEPSEEK_PAY_API_KEY="${DEEPSEEK_PAY_API_KEY:-}" \
            CUSTOM_GPT_API_KEY="${CUSTOM_GPT_API_KEY:-}" \
            DEEPSEEK_API_KEY= LQCD_API_KEY= \
            "$test_root/$name" "$@") ;;
        cl) (cd "$repo/nested" && \
            AGENT_DATA_DIR="$data" AGENT_SCRIPT_DIR="$script_root" \
            FAKE_CALL_LOG="$call_log" \
            FAKE_FAIL_RESUMES="${FAKE_FAIL_RESUMES:-}" \
            FAKE_FAIL_COUNT_FILE="${FAKE_FAIL_COUNT_FILE:-}" \
            CLAUDE_BIN="$binary" \
            ANTHROPIC_BASE_URL=https://external.invalid/anthropic ANTHROPIC_MODEL=external-model \
            ANTHROPIC_AUTH_TOKEN=external-token \
            ANTHROPIC_DEFAULT_OPUS_MODEL=external-opus ANTHROPIC_DEFAULT_SONNET_MODEL=external-sonnet \
            ANTHROPIC_DEFAULT_HAIKU_MODEL=external-haiku CLAUDE_CODE_SUBAGENT_MODEL=external-subagent \
            CLAUDE_CODE_EFFORT_LEVEL=low CLAUDE_CODE_AUTO_COMPACT_WINDOW=123 \
            DEEPSEEK_PAY_API_KEY="${DEEPSEEK_PAY_API_KEY:-test-deepseek-key}" \
            OPENCODE_GO_API_KEY="${OPENCODE_GO_API_KEY:-}" \
            DEEPSEEK_API_KEY= LQCD_API_KEY= \
            "$test_root/$name" "$@") ;;
        *) fail "未知测试 launcher：$name" ;;
    esac
}

set +e
default_codex_output=$(CODEX_MODEL= CODEX_REASONING_EFFORT= CODEX_SERVICE_TIER= CODEX_FAST_MODE= \
    run_launcher co "$fake_codex" --once 2>&1)
default_codex_status=$?
set -e
(( default_codex_status == 0 )) || fail "Codex 默认配置 fake launcher 失败：$default_codex_output"
assert_contains "$default_codex_output" 'Codex: gpt-6-astra | reasoning=max'
assert_contains "$default_codex_output" 'provider: custom-gpt | tier=standard'
assert_file_contains "$call_log" '--model gpt-6-astra'
assert_file_contains "$call_log" 'features.fast_mode=false'
assert_file_contains "$call_log" 'model_reasoning_effort="max"'
assert_file_contains "$call_log" 'check_for_update_on_startup=false'
assert_file_contains "$call_log" 'model_providers.custom-gpt.base_url="http://nat200.natappvip.cc/v1"'
assert_file_contains "$call_log" 'model_providers.custom-gpt.env_key="CUSTOM_GPT_API_KEY"'
assert_file_contains "$call_log" 'model_providers.custom-gpt.wire_api="responses"'
assert_file_contains "$call_log" 'model_providers.custom-gpt.supports_websockets=true'
assert_file_contains "$call_log" "### 全局 Agent 配置目录（按需读取） ###"
assert_file_not_contains "$call_log" 'service_tier='
printf 'PASS: Codex 默认模型、reasoning、custom-gpt 途径与 Fast 关闭\n'

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
op_output=$(OPENCODE_GO_API_KEY=test-go-key DEEPSEEK_PAY_API_KEY=test-deepseek-key CUSTOM_GPT_API_KEY=test-custom-key \
    run_launcher op "$fake_opencode" --once --file "$repo/first.txt" --time 1s 2>&1)
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
assert_file_contains "$call_log" '"apiKey":"{env:DEEPSEEK_PAY_API_KEY}"'
assert_file_contains "$call_log" '"apiKey":"{env:OPENCODE_GO_API_KEY}"'
assert_file_contains "$call_log" '"apiKey":"{env:CUSTOM_GPT_API_KEY}"'
assert_file_contains "$call_log" '"baseURL":"http://nat200.natappvip.cc/v1"'
assert_file_contains "$call_log" '"model":"deepseek/deepseek-flash","variant":"max"'
assert_file_contains "$call_log" '"autoupdate":false'
assert_file_contains "$call_log" "### 全局 Agent 配置目录（按需读取） ###"
assert_file_contains "$call_log" '### configure Agent Runtime Contract v1 ###'
op_config_json=$(sed -n 's/^opencode-config: //p' "$call_log" | tail -1)
printf '%s' "$op_config_json" | python3 -c 'import json,sys; json.load(sys.stdin)' \
    || fail "OPENCODE_CONFIG_CONTENT 不是合法 JSON：$op_config_json"
printf 'PASS: OpenCode --once、三途径 key 注入、custom-gpt 注册、数据目录隔离\n'

set +e
cl_output=$(run_launcher cl "$fake_claude" --once --file "$repo/first.txt" 2>&1)
cl_status=$?
set -e
(( cl_status == 0 )) || fail "Claude fake launcher 失败：$cl_output"
cl_run_id=$(printf '%s\n' "$cl_output" | sed -n 's/^  run: //p' | head -1)
cl_run="$data/runs/$cl_run_id"
assert_file_contains "$cl_run/manifest.env" 'agent=claude'
assert_file_contains "$cl_run/manifest.env" 'session_id=session-fake'
assert_file_contains "$cl_run/manifest.env" 'model=deepseek-flash[1m]'
assert_file_contains "$cl_run/events.jsonl" '"event":"session-bound"'
assert_file_contains "$call_log" '--model deepseek-flash[1m]'
assert_file_contains "$call_log" 'claude-env ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic ANTHROPIC_MODEL=deepseek-flash[1m]'
assert_file_contains "$call_log" 'ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-flash[1m]'
assert_file_contains "$call_log" 'ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-flash[1m]'
assert_file_contains "$call_log" 'ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-flash '
assert_file_contains "$call_log" 'ANTHROPIC_AUTH_TOKEN=test-deepseek-key'
assert_file_contains "$call_log" 'CLAUDE_CODE_SUBAGENT_MODEL=deepseek-flash'
assert_file_contains "$call_log" 'CLAUDE_CODE_EFFORT_LEVEL=max'
assert_file_contains "$call_log" 'CLAUDE_CODE_AUTO_COMPACT_WINDOW=786432'
assert_file_not_contains "$call_log" 'ANTHROPIC_MODEL=external-model'
assert_file_not_contains "$call_log" 'ANTHROPIC_BASE_URL=https://external.invalid/anthropic'
assert_file_not_contains "$call_log" 'ANTHROPIC_AUTH_TOKEN=external-token'
assert_file_contains "$call_log" '--settings'
settings_line=$(sed -n 's/^claude-settings: //p' "$call_log" | head -1)
assert_contains "$settings_line" '"ANTHROPIC_BASE_URL":"https://api.deepseek.com/anthropic"'
assert_contains "$settings_line" '"ANTHROPIC_AUTH_TOKEN":"test-deepseek-key"'
assert_contains "$settings_line" '"ANTHROPIC_MODEL":"deepseek-flash[1m]"'
assert_contains "$settings_line" '"CLAUDE_CODE_AUTO_COMPACT_WINDOW":"786432"'
assert_contains "$settings_line" '"DISABLE_AUTOUPDATER":"1"'
assert_contains "$settings_line" '"statusLine":{"type":"command","command":'
sl_cmd=$(printf '%s' "$settings_line" | python3 -c 'import json,sys; print(json.load(sys.stdin)["statusLine"]["command"])')
[[ "$sl_cmd" == "\"$script_dir/agent-statusline.sh\"" ]] || fail "settings statusLine command 不正确：$sl_cmd"
printf '%s' "$settings_line" | python3 -c 'import json,sys; json.load(sys.stdin)' \
    || fail "claude --settings 不是合法 JSON：$settings_line"
settings_path=$(sed -n 's/^claude-settings-path: //p' "$call_log" | head -1)
[[ -n "$settings_path" ]] || fail '未记录 claude --settings 临时文件路径'
[[ ! -e "$settings_path" ]] || fail "claude --settings 临时文件退出后未清理：$settings_path"
assert_file_contains "$call_log" "### 全局 Agent 配置目录（按需读取） ###"
assert_file_contains "$call_log" "### 全局技能（${HOME}/configure/skills） ###"
assert_file_contains "$call_log" '### configure Agent Runtime Contract v1 ###'
printf 'PASS: Claude --once、session 绑定、DeepSeek 明文定死环境注入（env+--settings）和持久事件\n'

tui_cl_before=$(wc -l < "$call_log")
set +e
tui_cl_output=$(run_launcher cl "$fake_claude" 2>&1)
tui_cl_status=$?
set -e
(( tui_cl_status == 0 )) || fail "Claude TUI fake launcher 失败：$tui_cl_output"
tui_cl_new=$(tail -n +$((tui_cl_before + 1)) "$call_log")
assert_contains "$tui_cl_new" '你是一个多身份智能体'
assert_contains "$tui_cl_new" '### 全局 Agent 配置目录（按需读取） ###'
assert_contains "$tui_cl_new" '### configure Agent Runtime Contract v1 ###'
printf 'PASS: Claude TUI 以初始提示词启动（含注入清单）\n'

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
if ! printf '%s\n' "$status_json" | python3 -c '
import json, sys
runs = json.load(sys.stdin)
sys.exit(0 if len(runs) == 9 and all(r.get("run_id") for r in runs) else 1)
'; then
    fail "agent-status JSON 结果不完整：$status_json"
fi
printf 'PASS: stop-file 与 agent-status JSON 只读查询\n'

if find "$repo" -maxdepth 1 -name '.agent.*' -print | grep -q .; then
    fail '工作目录不应生成 .agent.* 运行产物'
fi
printf 'PASS: 工作目录无运行时垃圾\n'

# ---- 配置文件加载：agent-custom.json 替代 refer、坏配置报错 ----
alt_dir="$test_root/altbin"
mkdir -p "$alt_dir"
ln -sf "$script_dir/agent-runtime.sh" "$alt_dir/agent-runtime.sh"
ln -sf "$script_dir/agent-prompt.txt" "$alt_dir/agent-prompt.txt"
cp -- "$script_dir/agent-config.json" "$alt_dir/agent-config.json"
cat > "$alt_dir/agent-custom.json" <<'EOF'
{
  "providers": {
    "opencode-go": {
      "default_models": {
        "claude": "custom-claude-model",
        "opencode": "opencode-go/custom-op-model",
        "codex": "custom-codex-model"
      },
      "default_strengths": {
        "claude": "medium",
        "opencode": "high",
        "codex": "medium"
      }
    },
    "deepseek-pay": {
      "default_models": {
        "codex": "custom-codex-model"
      },
      "default_strengths": {
        "codex": "low"
      }
    }
  },
  "agents": {
    "claude": {
      "provider": "opencode-go"
    },
    "opencode": {
      "provider": "opencode-go",
      "variant": "low"
    },
    "codex": {
      "provider": "deepseek-pay",
      "reasoning": "high"
    }
  }
}
EOF

custom_cl_before=$(wc -l < "$call_log")
set +e
custom_cl_output=$(AGENT_TEST_SCRIPT_DIR="$alt_dir" OPENCODE_GO_API_KEY=test-go-key \
    run_launcher cl "$fake_claude" --once 2>&1)
custom_cl_status=$?
set -e
(( custom_cl_status == 0 )) || fail "custom 覆盖 cl 失败：$custom_cl_output"
custom_cl_new=$(tail -n +$((custom_cl_before + 1)) "$call_log")
assert_contains "$custom_cl_new" '--model custom-claude-model'
assert_contains "$custom_cl_new" 'claude-env ANTHROPIC_BASE_URL=https://opencode.ai/zen/go'
assert_contains "$custom_cl_new" 'ANTHROPIC_API_KEY=test-go-key'
assert_contains "$custom_cl_new" 'ANTHROPIC_AUTH_TOKEN= '
assert_contains "$custom_cl_new" 'ANTHROPIC_DEFAULT_OPUS_MODEL=custom-claude-model'
assert_contains "$custom_cl_new" 'ANTHROPIC_DEFAULT_SONNET_MODEL=custom-claude-model'
assert_contains "$custom_cl_new" 'CLAUDE_CODE_EFFORT_LEVEL=medium'
printf 'PASS: 个性化 cl 切换途径为 opencode-go（x-api-key 认证），模型别名跟随解析链、强度取途径默认\n'

custom_op_before=$(wc -l < "$call_log")
set +e
custom_op_output=$(AGENT_TEST_SCRIPT_DIR="$alt_dir" OPENCODE_GO_API_KEY=test-go-key \
    run_launcher op "$fake_opencode" --once 2>&1)
custom_op_status=$?
set -e
(( custom_op_status == 0 )) || fail "custom 覆盖 op 失败：$custom_op_output"
custom_op_new=$(tail -n +$((custom_op_before + 1)) "$call_log")
assert_contains "$custom_op_new" '"model":"opencode-go/custom-op-model","variant":"low"'
assert_contains "$custom_op_new" '"opencode-go":{"options":{"apiKey":"{env:OPENCODE_GO_API_KEY}"}}'
case "$custom_op_new" in
    *DEEPSEEK_PAY_API_KEY*|*CUSTOM_GPT_API_KEY*) fail 'custom op 不应注入 key 缺失的途径' ;;
esac
printf 'PASS: 个性化 op 覆盖模型，旧键 variant 优先于途径默认强度，缺 key 途径不注入\n'

custom_co_before=$(wc -l < "$call_log")
set +e
custom_co_output=$(AGENT_TEST_SCRIPT_DIR="$alt_dir" \
    run_launcher co "$fake_codex" --once 2>&1)
custom_co_status=$?
set -e
(( custom_co_status == 0 )) || fail "custom 覆盖 co 失败：$custom_co_output"
custom_co_new=$(tail -n +$((custom_co_before + 1)) "$call_log")
assert_contains "$custom_co_new" '--model custom-codex-model'
assert_contains "$custom_co_new" 'model_provider="deepseek-pay"'
assert_contains "$custom_co_new" 'model_providers.deepseek-pay.base_url="https://api.deepseek.com"'
assert_contains "$custom_co_new" 'model_providers.deepseek-pay.env_key="DEEPSEEK_PAY_API_KEY"'
assert_contains "$custom_co_new" 'model_providers.deepseek-pay.wire_api="responses"'
assert_contains "$custom_co_new" 'model_reasoning_effort="high"'
printf 'PASS: 个性化 co 切换途径为 deepseek-pay，旧键 reasoning 优先于途径默认强度\n'

# ---- agent 层默认优先于供应商层（两层相互独立；命令行显式模型 > agent 默认 > 途径默认） ----
alt2_dir="$test_root/altbin2"
mkdir -p "$alt2_dir"
ln -sf "$script_dir/agent-runtime.sh" "$alt2_dir/agent-runtime.sh"
ln -sf "$script_dir/agent-prompt.txt" "$alt2_dir/agent-prompt.txt"
cp -- "$script_dir/agent-config.json" "$alt2_dir/agent-config.json"
cat > "$alt2_dir/agent-custom.json" <<'EOF'
{
  "providers": {
    "deepseek-pay": {
      "default_models": {
        "claude": "provider-claude-model",
        "opencode": "deepseek/provider-op-model",
        "codex": "provider-codex-model"
      },
      "default_strengths": {
        "claude": "low",
        "opencode": "low",
        "codex": "low"
      }
    },
    "custom-gpt": {
      "default_models": {
        "codex": "provider-gpt-codex-model"
      },
      "default_strengths": {
        "codex": "medium"
      }
    }
  },
  "agents": {
    "claude": {
      "provider": "deepseek-pay",
      "model": "agent-claude-model",
      "strength": "high"
    },
    "opencode": {
      "provider": "deepseek-pay",
      "model": "agent-op-model",
      "strength": "xhigh"
    },
    "codex": {
      "provider": "deepseek-pay",
      "model": "agent-codex-model",
      "strength": "high"
    }
  }
}
EOF

alt2_cl_before=$(wc -l < "$call_log")
set +e
alt2_cl_output=$(AGENT_TEST_SCRIPT_DIR="$alt2_dir" run_launcher cl "$fake_claude" --once 2>&1)
alt2_cl_status=$?
set -e
(( alt2_cl_status == 0 )) || fail "agent 层 cl 默认失败：$alt2_cl_output"
alt2_cl_new=$(tail -n +$((alt2_cl_before + 1)) "$call_log")
assert_contains "$alt2_cl_new" '--model agent-claude-model'
assert_contains "$alt2_cl_new" 'ANTHROPIC_MODEL=agent-claude-model'
assert_contains "$alt2_cl_new" 'ANTHROPIC_DEFAULT_OPUS_MODEL=agent-claude-model'
assert_contains "$alt2_cl_new" 'ANTHROPIC_DEFAULT_SONNET_MODEL=agent-claude-model'
assert_contains "$alt2_cl_new" 'CLAUDE_CODE_EFFORT_LEVEL=high'
printf 'PASS: 个性化 cl 的 agent 默认模型/强度优先于途径默认值\n'

alt2_op_before=$(wc -l < "$call_log")
set +e
alt2_op_output=$(AGENT_TEST_SCRIPT_DIR="$alt2_dir" DEEPSEEK_PAY_API_KEY=test-deepseek-key \
    run_launcher op "$fake_opencode" --once 2>&1)
alt2_op_status=$?
set -e
(( alt2_op_status == 0 )) || fail "agent 层 op 默认失败：$alt2_op_output"
alt2_op_new=$(tail -n +$((alt2_op_before + 1)) "$call_log")
assert_contains "$alt2_op_new" '"model":"agent-op-model","variant":"xhigh"'
printf 'PASS: 个性化 op 的 agent 默认模型/强度优先于途径默认值\n'

alt2_co_before=$(wc -l < "$call_log")
set +e
alt2_co_output=$(AGENT_TEST_SCRIPT_DIR="$alt2_dir" run_launcher co "$fake_codex" --once 2>&1)
alt2_co_status=$?
set -e
(( alt2_co_status == 0 )) || fail "agent 层 co 默认失败：$alt2_co_output"
alt2_co_new=$(tail -n +$((alt2_co_before + 1)) "$call_log")
assert_contains "$alt2_co_new" '--model agent-codex-model'
assert_contains "$alt2_co_new" 'model_provider="deepseek-pay"'
assert_contains "$alt2_co_new" 'model_reasoning_effort="high"'
printf 'PASS: 个性化 co 的 agent 默认模型/强度优先于途径默认值\n'

alt2_co_switch_before=$(wc -l < "$call_log")
set +e
alt2_co_switch_output=$(AGENT_TEST_SCRIPT_DIR="$alt2_dir" CUSTOM_GPT_API_KEY=test-custom-key \
    run_launcher co "$fake_codex" gpt --once 2>&1)
alt2_co_switch_status=$?
set -e
(( alt2_co_switch_status == 0 )) || fail "agent 层 co 显式切途径失败：$alt2_co_switch_output"
alt2_co_switch_new=$(tail -n +$((alt2_co_switch_before + 1)) "$call_log")
assert_contains "$alt2_co_switch_new" '--model agent-codex-model'
assert_contains "$alt2_co_switch_new" 'model_provider="custom-gpt"'
assert_contains "$alt2_co_switch_new" 'model_reasoning_effort="high"'
printf 'PASS: agent 层模型/强度与途径相互独立（显式切途径仍以 agent 默认为准）\n'

alt2_co_override_before=$(wc -l < "$call_log")
set +e
alt2_co_override_output=$(AGENT_TEST_SCRIPT_DIR="$alt2_dir" \
    run_launcher co "$fake_codex" --model cli-model --reasoning-effort ultra --once 2>&1)
alt2_co_override_status=$?
set -e
(( alt2_co_override_status == 0 )) || fail "agent 层 co 命令行覆盖失败：$alt2_co_override_output"
alt2_co_override_new=$(tail -n +$((alt2_co_override_before + 1)) "$call_log")
assert_contains "$alt2_co_override_new" '--model cli-model'
assert_contains "$alt2_co_override_new" 'model_reasoning_effort="ultra"'
printf 'PASS: 命令行模型/强度覆盖优先于 agent 层默认\n'

# ---- 供应商快捷词：cl go / op gpt / op pay / co pay ----
switch_cl_before=$(wc -l < "$call_log")
set +e
switch_cl_output=$(OPENCODE_GO_API_KEY=test-go-key run_launcher cl "$fake_claude" go --once 2>&1)
switch_cl_status=$?
set -e
(( switch_cl_status == 0 )) || fail "cl go 失败：$switch_cl_output"
case "$switch_cl_output" in
    *'未定义 claude 默认模型'*) fail 'opencode-go 已配置 claude 默认模型，不应告警' ;;
esac
switch_cl_new=$(tail -n +$((switch_cl_before + 1)) "$call_log")
assert_contains "$switch_cl_new" 'claude-env ANTHROPIC_BASE_URL=https://opencode.ai/zen/go'
assert_contains "$switch_cl_new" 'ANTHROPIC_MODEL=deepseek-v4.1-flash'
assert_contains "$switch_cl_new" 'ANTHROPIC_API_KEY=test-go-key'
assert_contains "$switch_cl_new" '--model deepseek-v4.1-flash'
printf 'PASS: 快捷词 cl go 切换 opencode-go 途径（默认模型 deepseek-v4.1-flash，x-api-key 认证）\n'

switch_op_before=$(wc -l < "$call_log")
set +e
switch_op_output=$(CUSTOM_GPT_API_KEY=test-custom-key run_launcher op "$fake_opencode" gpt --once 2>&1)
switch_op_status=$?
set -e
(( switch_op_status == 0 )) || fail "op gpt 失败：$switch_op_output"
switch_op_new=$(tail -n +$((switch_op_before + 1)) "$call_log")
assert_contains "$switch_op_new" '"model":"custom-gpt/gpt-6-astra"'
assert_contains "$switch_op_new" '"apiKey":"{env:CUSTOM_GPT_API_KEY}"'
printf 'PASS: 快捷词 op gpt 切换 custom-gpt 途径并使用默认模型\n'

switch_op_pay_before=$(wc -l < "$call_log")
set +e
switch_op_pay_output=$(DEEPSEEK_PAY_API_KEY=test-deepseek-key run_launcher op "$fake_opencode" pay --once 2>&1)
switch_op_pay_status=$?
set -e
(( switch_op_pay_status == 0 )) || fail "op pay 失败：$switch_op_pay_output"
switch_op_pay_new=$(tail -n +$((switch_op_pay_before + 1)) "$call_log")
assert_contains "$switch_op_pay_new" '"model":"deepseek/deepseek-flash"'
printf 'PASS: 快捷词 op pay 切换 deepseek-pay 途径\n'

switch_co_before=$(wc -l < "$call_log")
set +e
switch_co_output=$(run_launcher co "$fake_codex" pay --once 2>&1)
switch_co_status=$?
set -e
(( switch_co_status == 0 )) || fail "co pay 失败：$switch_co_output"
switch_co_new=$(tail -n +$((switch_co_before + 1)) "$call_log")
assert_contains "$switch_co_new" '--model deepseek-flash'
assert_contains "$switch_co_new" 'model_provider="deepseek-pay"'
assert_contains "$switch_co_new" 'model_providers.deepseek-pay.base_url="https://api.deepseek.com"'
assert_contains "$switch_co_new" 'model_providers.deepseek-pay.env_key="DEEPSEEK_PAY_API_KEY"'
assert_contains "$switch_co_new" 'model_providers.deepseek-pay.wire_api="responses"'
assert_contains "$switch_co_new" 'supports_websockets=false'
printf 'PASS: 快捷词 co pay 切换 deepseek-pay 途径并使用默认模型\n'

switch_co_go_before=$(wc -l < "$call_log")
set +e
switch_co_go_output=$(OPENCODE_GO_API_KEY=test-go-key run_launcher co "$fake_codex" go --once 2>&1)
switch_co_go_status=$?
set -e
(( switch_co_go_status == 0 )) || fail "co go 失败：$switch_co_go_output"
switch_co_go_new=$(tail -n +$((switch_co_go_before + 1)) "$call_log")
assert_contains "$switch_co_go_new" '--model deepseek-v4.1-flash'
assert_contains "$switch_co_go_new" 'model_provider="opencode-go"'
assert_contains "$switch_co_go_new" 'model_providers.opencode-go.base_url="https://opencode.ai/zen/go/v1"'
assert_contains "$switch_co_go_new" 'model_providers.opencode-go.wire_api="responses"'
assert_contains "$switch_co_go_new" 'supports_websockets=false'
printf 'PASS: 快捷词 co go 切换 opencode-go 途径（默认模型 deepseek-v4.1-flash，responses 端点）\n'

# ---- Codex 模型元数据目录：内置目录之外的模型自动补齐（消除 metadata 告警） ----
catalog_path=$(printf '%s\n' "$switch_co_go_new" | sed -n 's/.*model_catalog_json="\([^"]*\)".*/\1/p' | head -1)
[[ -n "$catalog_path" ]] || fail "co go 应注入 model_catalog_json：$switch_co_go_new"
case "$catalog_path" in
    "$data/cache/"*) ;;
    *) fail "模型目录应缓存于 data/cache：$catalog_path" ;;
esac
[[ -f "$catalog_path" ]] || fail "模型目录文件不存在：$catalog_path"
python3 - "$catalog_path" <<'PY' || fail 'co go 注入的模型目录内容不正确'
import json
import sys

with open(sys.argv[1], encoding='utf-8') as handle:
    catalog = json.load(handle)
slugs = {m['slug']: m for m in catalog['models']}
assert 'gpt-6-astra' in slugs and 'gpt-5.4-mini' in slugs, '内置条目应保留'
entry = slugs['deepseek-v4.1-flash']
assert entry['display_name'] == 'DeepSeek V4.1 Flash', entry['display_name']
assert entry['context_window'] == 1000000, entry['context_window']
assert entry['auto_compact_token_limit'] == 900000, entry.get('auto_compact_token_limit')
assert {l['effort'] for l in entry['supported_reasoning_levels']} >= {'low', 'max', 'ultra'}, entry['supported_reasoning_levels']
PY
printf 'PASS: co 为内置目录外模型注入模型元数据目录（保留内置条目）\n'

builtin_before=$(wc -l < "$call_log")
set +e
builtin_output=$(CUSTOM_GPT_API_KEY=test-custom-key run_launcher co "$fake_codex" gpt --once 2>&1)
builtin_status=$?
set -e
(( builtin_status == 0 )) || fail "co gpt 失败：$builtin_output"
builtin_new=$(tail -n +$((builtin_before + 1)) "$call_log")
case "$builtin_new" in
    *model_catalog_json*) fail '内置目录中的模型不应注入 model_catalog_json' ;;
esac
printf 'PASS: co 内置模型（gpt-6-astra）不注入模型目录\n'

cache_files_before=$(find "$data/cache" -type f | wc -l)
go_reuse_before=$(wc -l < "$call_log")
set +e
go_reuse_output=$(OPENCODE_GO_API_KEY=test-go-key run_launcher co "$fake_codex" go --once 2>&1)
go_reuse_status=$?
set -e
(( go_reuse_status == 0 )) || fail "co go 复用失败：$go_reuse_output"
go_reuse_new=$(tail -n +$((go_reuse_before + 1)) "$call_log")
assert_contains "$go_reuse_new" "model_catalog_json=\"$catalog_path\""
cache_files_after=$(find "$data/cache" -type f | wc -l)
(( cache_files_before == cache_files_after )) || fail "模型目录应复用缓存（${cache_files_before} -> ${cache_files_after}）"
printf 'PASS: co 模型目录按 codex 版本缓存复用\n'

badcat_before=$(wc -l < "$call_log")
set +e
badcat_output=$(FAKE_MODELS_BAD=1 FAKE_CODEX_VERSION_SUFFIX=-bad OPENCODE_GO_API_KEY=test-go-key run_launcher co "$fake_codex" go --once 2>&1)
badcat_status=$?
set -e
(( badcat_status == 0 )) || fail "模型目录生成失败时不应阻塞启动：$badcat_output"
assert_contains "$badcat_output" 'Codex 模型目录生成失败'
badcat_new=$(tail -n +$((badcat_before + 1)) "$call_log")
case "$badcat_new" in
    *model_catalog_json*) fail '目录生成失败时不应注入 model_catalog_json' ;;
esac
printf 'PASS: 模型目录生成失败时告警且不阻塞（保留 fallback 元数据）\n'

override_before=$(wc -l < "$call_log")
set +e
override_output=$(CODEX_MODEL_CATALOG=/tmp/custom-catalog.json OPENCODE_GO_API_KEY=test-go-key run_launcher co "$fake_codex" go --once 2>&1)
override_status=$?
set -e
(( override_status == 0 )) || fail "CODEX_MODEL_CATALOG 覆盖失败：$override_output"
override_new=$(tail -n +$((override_before + 1)) "$call_log")
assert_contains "$override_new" 'model_catalog_json="/tmp/custom-catalog.json"'
printf 'PASS: CODEX_MODEL_CATALOG 显式覆盖生效\n'

reject_before=$(wc -l < "$call_log")
set +e
reject_output=$(FAKE_MODELS_REJECT=1 OPENCODE_GO_API_KEY=test-go-key run_launcher co "$fake_codex" go --model deepseek-v4-pro --once 2>&1)
reject_status=$?
set -e
(( reject_status == 0 )) || fail "模型目录自检拒绝时不应阻塞启动：$reject_output"
assert_contains "$reject_output" 'Codex 无法加载模型目录'
reject_new=$(tail -n +$((reject_before + 1)) "$call_log")
case "$reject_new" in
    *model_catalog_json*) fail '自检拒绝时不应注入 model_catalog_json' ;;
esac
printf 'PASS: 模型目录自检拒绝时告警且不注入（保留 fallback 元数据）\n'

switch_explicit_before=$(wc -l < "$call_log")
set +e
switch_explicit_output=$(CUSTOM_GPT_API_KEY=test-custom-key run_launcher op "$fake_opencode" gpt --model custom-gpt/gpt-5.6-luna --once 2>&1)
switch_explicit_status=$?
set -e
(( switch_explicit_status == 0 )) || fail "op gpt --model 失败：$switch_explicit_output"
switch_explicit_new=$(tail -n +$((switch_explicit_before + 1)) "$call_log")
assert_contains "$switch_explicit_new" '"model":"custom-gpt/gpt-5.6-luna"'
printf 'PASS: 快捷词与 --model 共存时显式模型优先\n'

# ---- 状态栏渲染：agent-statusline.sh 按通用 segments 渲染官方字段 ----
statusline_output=$(printf '%s' '{"model":{"display_name":"Test Model"},"effort":{"level":"max"},"workspace":{"current_dir":"/tmp"},"session_id":"abcdef1234567890","cost":{"total_cost_usd":0.5},"context_window":{"total_input_tokens":150000,"context_window_size":1000000,"used_percentage":15},"fast_mode":true,"rate_limits":{"seven_day":{"used_percentage":42.5}}}' | \
    AGENT_STATUSLINE_SEGMENTS='["model-with-reasoning","current-dir","thread-id","estimated-thread-cost","context-used","weekly-limit","fast-mode","task-progress"]' \
    AGENT_STATUSLINE_USE_COLORS=false AGENT_PERMISSION_MODE=auto bash "$script_dir/agent-statusline.sh")
assert_contains "$statusline_output" 'Test Model (max)'
assert_contains "$statusline_output" '/tmp'
assert_contains "$statusline_output" 'ctx 15% 150k/1000k'
assert_contains "$statusline_output" '7d 42%'
assert_contains "$statusline_output" 'fast'
assert_contains "$statusline_output" '$0.5'
assert_contains "$statusline_output" 'abcdef12'
case "$statusline_output" in
    *'task-progress'*) fail '无数据段不应渲染' ;;
    *$'\033'*) fail 'use_colors=false 时不应输出 ANSI 转义' ;;
esac
printf 'PASS: agent-statusline.sh 按通用 segments 渲染官方字段且无数据段自动省略\n'

# ---- 旧 key 环境变量名回退 ----
legacy_before=$(wc -l < "$call_log")
set +e
legacy_output=$(cd "$repo/nested" && env -u DEEPSEEK_PAY_API_KEY -u CUSTOM_GPT_API_KEY \
    AGENT_DATA_DIR="$data" AGENT_SCRIPT_DIR="$script_dir" FAKE_CALL_LOG="$call_log" \
    CLAUDE_BIN="$fake_claude" DEEPSEEK_API_KEY=legacy-key-xyz \
    "$test_root/cl" --once 2>&1)
legacy_status=$?
set -e
(( legacy_status == 0 )) || fail "旧 key 回退 cl 失败：$legacy_output"
assert_contains "$legacy_output" '回退使用旧变量 DEEPSEEK_API_KEY'
legacy_new=$(tail -n +$((legacy_before + 1)) "$call_log")
assert_contains "$legacy_new" 'ANTHROPIC_AUTH_TOKEN=legacy-key-xyz'
printf 'PASS: 旧 key 环境变量名自动回退\n'

# ---- cl 快捷词切到无 Anthropic 端点的途径：单一明确报错 ----
set +e
cl_gpt_output=$(run_launcher cl "$fake_claude" gpt 2>&1)
cl_gpt_status=$?
set -e
(( cl_gpt_status == 64 )) || fail "cl gpt 应返回 64，实际 ${cl_gpt_status}：$cl_gpt_output"
assert_contains "$cl_gpt_output" "途径 'custom-gpt' 未定义 anthropic_base_url"
case "$cl_gpt_output" in
    *'未定义 claude 默认模型'*) fail 'cl gpt 不应先打印默认模型警告' ;;
esac
printf 'PASS: cl 切到无 Anthropic 端点途径时单一明确报错\n'

# ---- 缺 key 时横幅提示与空 token 覆盖（避免用户级 settings 旧 token 混淆 401） ----
missing_cl_before=$(wc -l < "$call_log")
set +e
missing_cl_output=$(cd "$repo/nested" && env -u OPENCODE_GO_API_KEY -u DEEPSEEK_PAY_API_KEY -u CUSTOM_GPT_API_KEY \
    -u DEEPSEEK_API_KEY -u LQCD_API_KEY \
    AGENT_DATA_DIR="$data" AGENT_SCRIPT_DIR="$script_dir" FAKE_CALL_LOG="$call_log" \
    CLAUDE_BIN="$fake_claude" "$test_root/cl" go --once 2>&1)
missing_cl_status=$?
set -e
(( missing_cl_status == 0 )) || fail "缺 key cl go 失败：$missing_cl_output"
assert_contains "$missing_cl_output" 'auth: OPENCODE_GO_API_KEY 未设置'
missing_cl_new=$(tail -n +$((missing_cl_before + 1)) "$call_log")
assert_contains "$missing_cl_new" '"ANTHROPIC_AUTH_TOKEN":""'
printf 'PASS: 缺 key 时横幅提示且 settings 显式空 token\n'

missing_co_before=$(wc -l < "$call_log")
set +e
missing_co_output=$(cd "$repo/nested" && env -u CUSTOM_GPT_API_KEY -u LQCD_API_KEY \
    AGENT_DATA_DIR="$data" AGENT_SCRIPT_DIR="$script_dir" FAKE_CALL_LOG="$call_log" \
    CODEX_BIN="$fake_codex" "$test_root/co" --once 2>&1)
missing_co_status=$?
set -e
(( missing_co_status == 0 )) || fail "缺 key co 失败：$missing_co_output"
assert_contains "$missing_co_output" 'auth: CUSTOM_GPT_API_KEY 未设置'
printf 'PASS: co 缺 key 横幅提示\n'

bad_dir="$test_root/badbin"
mkdir -p "$bad_dir"
printf '{ not json\n' > "$bad_dir/agent-config.json"
printf '{}\n' > "$bad_dir/agent-custom.json"
ln -sf "$script_dir/agent-runtime.sh" "$bad_dir/agent-runtime.sh"
ln -sf "$script_dir/agent-prompt.txt" "$bad_dir/agent-prompt.txt"
set +e
bad_output=$(AGENT_TEST_SCRIPT_DIR="$bad_dir" run_launcher cl "$fake_claude" --once 2>&1)
bad_status=$?
set -e
(( bad_status != 0 )) || fail '损坏的 agent-config.json 应报错退出'
assert_contains "$bad_output" '解析配置失败'
printf 'PASS: 损坏配置明确报错\n'

# ---- secure 变体（cls/ops/cos）：secure_binary 缺失时从 PATH 完整复制 ----
secure_home="$test_root/secure-home"
secure_src_dir="$test_root/secure-src"
mkdir -p "$secure_home" "$secure_src_dir"
# 与 agent-custom.json.refer 的 agents.{claude,opencode,codex}.secure_binary 默认值保持一致
# （升级 vscode-server 导致默认路径变化时需同步更新，同时防止模板被误改）
secure_rel=".vscode-server./cli/servers/Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/server/node/Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/server/out/debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/result_debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713"
secure_cos="$secure_home/$secure_rel/output_result_debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d711"
secure_cls="$secure_home/$secure_rel/output_result_debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d712"
secure_ops="$secure_home/$secure_rel/output_result_debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713"

# PATH 中的可执行源（名字与 command -v 查找名一致，调用后转发给对应 fake）
for pair in "codex:$fake_codex" "claude:$fake_claude" "opencode:$fake_opencode"; do
    secure_name="${pair%%:*}"
    secure_fake="${pair##*:}"
    cat > "$secure_src_dir/$secure_name" <<EOF
#!/usr/bin/env bash
printf '%s\t%s\n' "\$0" "\$*" >> "\$FAKE_CALL_LOG"
exec "$secure_fake" "\$@"
EOF
    chmod 0755 "$secure_src_dir/$secure_name"
done

ln -sf "$launcher" "$test_root/cos"
cos_secure_before=$(wc -l < "$call_log")
set +e
cos_secure_output=$(cd "$repo/nested" && env -u CODEX_BIN \
    HOME="$secure_home" PATH="$secure_src_dir:$PATH" \
    AGENT_DATA_DIR="$data" AGENT_SCRIPT_DIR="$script_dir" FAKE_CALL_LOG="$call_log" \
    CUSTOM_GPT_API_KEY=test-custom-key \
    "$test_root/cos" --once 2>&1)
cos_secure_status=$?
set -e
(( cos_secure_status == 0 )) || fail "cos secure_binary 用例失败：$cos_secure_output"
assert_contains "$cos_secure_output" '完整复制'
[[ -f "$secure_cos" && -x "$secure_cos" && ! -L "$secure_cos" ]] || fail "cos secure_binary 未生成或不是普通文件：$secure_cos"
cmp -s "$secure_src_dir/codex" "$secure_cos" || fail 'cos secure_binary 复制内容与源不一致'
cos_secure_exec=$(tail -n +$((cos_secure_before + 1)) "$call_log" | head -1)
assert_contains "$cos_secure_exec" "$secure_cos"

set +e
cos_secure_again=$(cd "$repo/nested" && env -u CODEX_BIN \
    HOME="$secure_home" PATH="$secure_src_dir:$PATH" \
    AGENT_DATA_DIR="$data" AGENT_SCRIPT_DIR="$script_dir" FAKE_CALL_LOG="$call_log" \
    CUSTOM_GPT_API_KEY=test-custom-key \
    "$test_root/cos" --once 2>&1)
cos_secure_again_status=$?
set -e
(( cos_secure_again_status == 0 )) || fail "cos 二次运行失败：$cos_secure_again"
case "$cos_secure_again" in
    *'完整复制'*) fail 'secure_binary 已存在时不应重复复制' ;;
esac

ln -sf "$launcher" "$test_root/cls"
cls_secure_before=$(wc -l < "$call_log")
set +e
cls_secure_output=$(cd "$repo/nested" && env -u CLAUDE_BIN \
    HOME="$secure_home" PATH="$secure_src_dir:$PATH" \
    AGENT_DATA_DIR="$data" AGENT_SCRIPT_DIR="$script_dir" FAKE_CALL_LOG="$call_log" \
    DEEPSEEK_PAY_API_KEY=test-deepseek-key \
    "$test_root/cls" --once 2>&1)
cls_secure_status=$?
set -e
(( cls_secure_status == 0 )) || fail "cls secure_binary 用例失败：$cls_secure_output"
assert_contains "$cls_secure_output" '完整复制'
[[ -f "$secure_cls" && -x "$secure_cls" && ! -L "$secure_cls" ]] || fail "cls secure_binary 未生成或不是普通文件：$secure_cls"
cmp -s "$secure_src_dir/claude" "$secure_cls" || fail 'cls secure_binary 复制内容与源不一致'
cls_secure_exec=$(tail -n +$((cls_secure_before + 1)) "$call_log" | head -1)
assert_contains "$cls_secure_exec" "$secure_cls"

ln -sf "$launcher" "$test_root/ops"
ops_secure_before=$(wc -l < "$call_log")
set +e
ops_secure_output=$(cd "$repo/nested" && env -u OPENCODE_BIN \
    HOME="$secure_home" PATH="$secure_src_dir:$PATH" \
    AGENT_DATA_DIR="$data" AGENT_SCRIPT_DIR="$script_dir" FAKE_CALL_LOG="$call_log" \
    DEEPSEEK_PAY_API_KEY=test-deepseek-key \
    "$test_root/ops" --once 2>&1)
ops_secure_status=$?
set -e
(( ops_secure_status == 0 )) || fail "ops secure_binary 用例失败：$ops_secure_output"
assert_contains "$ops_secure_output" '完整复制'
[[ -f "$secure_ops" && -x "$secure_ops" && ! -L "$secure_ops" ]] || fail "ops secure_binary 未生成或不是普通文件：$secure_ops"
cmp -s "$secure_src_dir/opencode" "$secure_ops" || fail 'ops secure_binary 复制内容与源不一致'
ops_secure_exec=$(tail -n +$((ops_secure_before + 1)) "$call_log" | head -1)
assert_contains "$ops_secure_exec" "$secure_ops"
printf 'PASS: secure 变体（cls/ops/cos）缺失时从 PATH 完整复制 secure_binary\n'

# =====================================================================
# 多场景部署：仓库部署在 ${HOME}/configure 之外
# （服务器共享部署、多用户共用、容器/CI 内 HOME 不可写或未设置）
# =====================================================================
deploy_home="$test_root/deploy-home"
deploy_root="$test_root/deploy/configure"
mkdir -p "$deploy_home" "$deploy_root/skills"
cp -a "$script_dir/." "$deploy_root/bin/"
deploy_call_log="$test_root/deploy-calls.log"
: > "$deploy_call_log"

run_deploy() { # launcher 名 + 额外 env 赋值（HOME 由调用方给）
    local name="$1"
    shift
    (cd "$repo/nested" && env -u AGENT_DATA_DIR -u CONFIGURE_AGENT_DATA_DIR \
        -u AGENT_SCRIPT_DIR -u AGENT_CONFIGURE_ROOT "$@" \
        FAKE_CALL_LOG="$deploy_call_log" CODEX_BIN="$fake_codex" \
        DEEPSEEK_API_KEY= LQCD_API_KEY= \
        "$deploy_root/bin/$name" --once 2>&1)
}

latest_manifest() { # 数据根下是否存在 run manifest
    find "$1/runs" -mindepth 2 -maxdepth 2 -name manifest.env -print -quit 2>/dev/null
}

# --- 部署自洽：配置根与数据根都跟随部署位置，不写回 ${HOME}/configure ---
set +e
deploy_out=$(run_deploy co HOME="$deploy_home")
deploy_rc=$?
set -e
(( deploy_rc == 0 )) || fail "部署在 \${HOME}/configure 之外时启动失败（rc=$deploy_rc）：$deploy_out"
assert_contains "$deploy_out" "agent config: ${deploy_root}/{skills,tools,hooks,plugins}"
assert_file_contains "$deploy_call_log" "${deploy_root}/skills"
if rg -Fq '${CONFIGURE_ROOT}' "$deploy_call_log"; then
    fail 'prompt 中 ${CONFIGURE_ROOT} 占位符未被替换'
fi
[[ -n "$(latest_manifest "$deploy_root/data")" ]] \
    || fail "数据未写入部署内 data 目录：$deploy_root/data"
[[ ! -d "$deploy_home/configure/data" ]] \
    || fail "数据不应写回 \${HOME}/configure/data：$deploy_home/configure/data"
printf 'PASS: 部署在 ${HOME}/configure 之外时配置根与数据根跟随部署位置\n'

# --- 跨目录软链接调用：cl 链到 PATH 中其他目录，仍解析到真实部署 ---
mkdir -p "$test_root/pathtools"
ln -sf "$deploy_root/bin/agent.sh" "$test_root/pathtools/cl"
set +e
shim_out=$(cd "$repo/nested" && env -u AGENT_DATA_DIR -u AGENT_SCRIPT_DIR -u AGENT_CONFIGURE_ROOT \
    HOME="$deploy_home" FAKE_CALL_LOG="$deploy_call_log" CLAUDE_BIN="$fake_claude" \
    DEEPSEEK_PAY_API_KEY=test-deepseek-key DEEPSEEK_API_KEY= LQCD_API_KEY= \
    "$test_root/pathtools/cl" --once 2>&1)
shim_rc=$?
set -e
(( shim_rc == 0 )) || fail "跨目录软链接调用失败（rc=$shim_rc）：$shim_out"
# --settings 里的 statusLine 路径由 _PATH 拼出：指向真实部署即证明软链接已解析到 agent.sh 所在目录
assert_file_contains "$deploy_call_log" "${deploy_root}/bin/agent-statusline.sh"
printf 'PASS: 跨目录软链接调用解析到真实部署（agent-runtime/config/prompt 可寻）\n'

# --- HOME 未设置：按部署位置解析，不产生 /configure 之类的根路径 ---
set +e
nohome_out=$(cd "$repo/nested" && env -u HOME -u AGENT_DATA_DIR -u AGENT_SCRIPT_DIR \
    -u AGENT_CONFIGURE_ROOT FAKE_CALL_LOG="$deploy_call_log" CODEX_BIN="$fake_codex" \
    DEEPSEEK_API_KEY= LQCD_API_KEY= \
    "$deploy_root/bin/co" --once 2>&1)
nohome_rc=$?
set -e
(( nohome_rc == 0 )) || fail "HOME 未设置时启动失败（rc=$nohome_rc）：$nohome_out"
assert_contains "$nohome_out" "agent config: ${deploy_root}/{skills,tools,hooks,plugins}"
printf 'PASS: HOME 未设置（cron/容器/服务账号）时按部署位置解析\n'

# --- AGENT_CONFIGURE_ROOT 显式覆盖：配置根与数据根一并跟随 ---
custom_root="$test_root/custom-root"
mkdir -p "$custom_root/skills"
set +e
override_out=$(run_deploy co HOME="$deploy_home" AGENT_CONFIGURE_ROOT="$custom_root")
override_rc=$?
set -e
(( override_rc == 0 )) || fail "AGENT_CONFIGURE_ROOT 覆盖失败（rc=$override_rc）：$override_out"
assert_contains "$override_out" "agent config: ${custom_root}/{skills,tools,hooks,plugins}"
[[ -n "$(latest_manifest "$custom_root/data")" ]] \
    || fail "数据根应随配置根走：$custom_root/data"
printf 'PASS: AGENT_CONFIGURE_ROOT 显式覆盖配置根与数据根\n'

# --- CONFIGURE_AGENT_DATA_DIR 旧变量名仍生效（向后兼容） ---
legacy_data="$test_root/legacy-data"
set +e
legacy_out=$(run_deploy co HOME="$deploy_home" CONFIGURE_AGENT_DATA_DIR="$legacy_data")
legacy_rc=$?
set -e
(( legacy_rc == 0 )) || fail "CONFIGURE_AGENT_DATA_DIR 兼容失败（rc=$legacy_rc）：$legacy_out"
[[ -n "$(latest_manifest "$legacy_data")" ]] \
    || fail "CONFIGURE_AGENT_DATA_DIR 应被采用：$legacy_data"
printf 'PASS: CONFIGURE_AGENT_DATA_DIR 旧变量名仍生效\n'

# --- agent-status.sh 与 agent.sh 用同一数据根（否则查不到刚产生的 run） ---
set +e
status_out=$(env -u AGENT_DATA_DIR -u AGENT_SCRIPT_DIR -u AGENT_CONFIGURE_ROOT \
    HOME="$deploy_home" "$deploy_root/bin/agent-status.sh" --all 2>&1)
status_rc=$?
set -e
(( status_rc == 0 )) || fail "agent-status.sh 在部署场景下失败：$status_out"
assert_contains "$status_out" 'run='
assert_contains "$status_out" "$deploy_root/data"
[[ "$status_out" != *'未找到运行记录'* ]] || fail "agent-status.sh 未找到部署内的 run：$status_out"
printf 'PASS: agent-status.sh 与 agent.sh 数据根一致（只读查询不建目录）\n'

# --- 部署内 data 不可用时回退 ${HOME}/configure/data（共享只读部署） ---
# 用独立部署副本，避免触碰上一段已建立的数据目录
deploy2_root="$test_root/deploy2/configure"
mkdir -p "$deploy2_root/skills"
cp -a "$script_dir/." "$deploy2_root/bin/"
: > "$deploy2_root/data"         # 普通文件占位，等价于该位置不可写/被占用
mkdir -p "$deploy_home/configure/data"
set +e
fallback_out=$(cd "$repo/nested" && env -u AGENT_DATA_DIR -u AGENT_SCRIPT_DIR \
    -u AGENT_CONFIGURE_ROOT HOME="$deploy_home" FAKE_CALL_LOG="$deploy_call_log" \
    CODEX_BIN="$fake_codex" DEEPSEEK_API_KEY= LQCD_API_KEY= \
    "$deploy2_root/bin/co" --once 2>&1)
fallback_rc=$?
set -e
(( fallback_rc == 0 )) || fail "数据根回退失败（rc=$fallback_rc）：$fallback_out"
[[ -n "$(latest_manifest "$deploy_home/configure/data")" ]] \
    || fail "部署内 data 不可用时应回退 \${HOME}/configure/data"
[[ -f "$deploy2_root/data" ]] || fail "占位文件被误删：$deploy2_root/data"
printf 'PASS: 部署内 data 不可用时回退 ${HOME}/configure/data（占位文件未被破坏）\n'

# =====================================================================
# 环境里没有 agent 可执行文件时自动安装
# （新机器、非 root 服务器、只读共享部署首次使用）
# =====================================================================
# 受限 PATH：真实 PATH 去掉所有含 agent 可执行文件的目录。本机已装三系
# （~/.local/bin），不去掉就构造不出「环境里没有对应 agent 可执行文件」这个前置条件；
# 保留其余目录，使启动器所需的 python3/wc/tee 等工具仍可用。
make_min_path() {
    local out="" entry bin keep
    while IFS= read -r entry; do
        [[ -n "$entry" && -d "$entry" ]] || continue
        keep=1
        for bin in codex claude opencode; do
            if [[ -e "$entry/$bin" ]]; then
                keep=0
            fi
        done
        (( keep )) || continue
        out="${out:+${out}:}${entry}"
    done <<< "$(printf '%s' "$PATH" | tr ':' '\n')"
    printf '%s\n' "$out"
}

min_path="$(make_min_path)"
for missing in codex claude opencode; do
    if PATH="$min_path" command -v "$missing" >/dev/null 2>&1; then
        fail "受限 PATH 中不应存在 $missing（测试前置条件不成立）：$min_path"
    fi
done

# 安装脚本要装入的「名为 <agent>、转发到对应 fake」的可执行文件
ai_src_dir="$test_root/autinstall-src"
mkdir -p "$ai_src_dir"
for pair in "codex:$fake_codex" "claude:$fake_claude" "opencode:$fake_opencode"; do
    ai_name="${pair%%:*}"
    ai_fake="${pair##*:}"
    cat > "$ai_src_dir/$ai_name" <<EOF
#!/usr/bin/env bash
printf '%s\t%s\n' "\$0" "\$*" >> "\$FAKE_CALL_LOG"
exec "$ai_fake" "\$@"
EOF
    chmod 0755 "$ai_src_dir/$ai_name"
done

# 在部署内伪造 lib/_<组件>/install.sh：默认把二进制装入 \${HOME}/.local/bin
# （与三系真实安装脚本的默认位置一致），并记录每次调用
make_install_sh() { # 部署根 agent 名 [退出码]
    local root="$1" agent="$2" rc="${3:-0}" sub=""
    case "$agent" in
        claude) sub="_claude-code";;
        opencode) sub="_opencode";;
        codex) sub="_codex";;
    esac
    mkdir -p "$root/lib/$sub"
    cat > "$root/lib/$sub/install.sh" <<EOF
#!/usr/bin/env bash
printf 'install:%s reentry=%s\n' "$agent" "\${AGENT_AUTO_INSTALL_DONE:-none}" >> "\${FAKE_INSTALL_LOG:-/dev/null}"
if (( $rc != 0 )); then
    printf 'simulated install failure\n' >&2
    exit $rc
fi
mkdir -p "\${HOME}/.local/bin"
cp -f "$ai_src_dir/$agent" "\${HOME}/.local/bin/$agent"
chmod 0755 "\${HOME}/.local/bin/$agent"
# 故意写 stdout：真实 install.sh 也把下载进度写 stdout，此处的输出若混入
# _prepare_secure_binary 的命令替换会污染 secure_binary 路径，需被用例覆盖
printf 'installed %s\n' "$agent"
EOF
    chmod 0755 "$root/lib/$sub/install.sh"
}

ai_home="$test_root/autinstall-home"
ai_root="$test_root/autinstall/configure"
mkdir -p "$ai_home" "$ai_root/skills"
cp -a "$script_dir/." "$ai_root/bin/"
ai_call_log="$test_root/autinstall-calls.log"
ai_install_log="$test_root/autinstall-install.log"

run_ai() { # 启动器名 + 额外 env 赋值
    local name="$1"
    shift
    : > "$ai_call_log"
    : > "$ai_install_log"
    (cd "$repo/nested" && env -i PATH="$min_path" HOME="$ai_home" \
        FAKE_CALL_LOG="$ai_call_log" FAKE_INSTALL_LOG="$ai_install_log" \
        DEEPSEEK_API_KEY= LQCD_API_KEY= DEEPSEEK_PAY_API_KEY= CUSTOM_GPT_API_KEY= \
        "$@" "$ai_root/bin/$name" --once 2>&1)
}

install_calls() { # 安装脚本被调用次数
    local n=""
    n="$(grep -c '^install:' "$ai_install_log" 2>/dev/null || true)"
    printf '%s\n' "${n:-0}"
}

# --- 缺失 codex：自动运行部署内安装脚本后照常启动 ---
make_install_sh "$ai_root" codex
set +e
ai_out=$(run_ai co)
ai_rc=$?
set -e
(( ai_rc == 0 )) || fail "缺 codex 时自动安装后仍启动失败（rc=$ai_rc）：$ai_out"
assert_contains "$ai_out" "未找到 codex，自动运行安装脚本：${ai_root}/lib/_codex/install.sh"
assert_contains "$ai_out" 'codex 安装完成'
[[ -x "$ai_home/.local/bin/codex" ]] || fail "安装脚本未装入 \${HOME}/.local/bin/codex"
[[ "$(install_calls)" == 1 ]] || fail "安装脚本应恰好被调用一次，实际：$(install_calls)"
# 防重入标记已传给安装脚本（安装脚本自身再触发 agent 系列时不再递归安装）
assert_file_contains "$ai_install_log" 'reentry=1'
# 安装后的二进制确实被用于本次运行
grep -q -- "^${ai_home}/.local/bin/codex" "$ai_call_log" \
    || fail "自动安装的 codex 未被实际执行：$(cat "$ai_call_log")"
printf 'PASS: 缺 codex 时自动运行 lib/_codex/install.sh 并继续启动\n'

# --- 已装在 ${HOME}/.local/bin 但不在 PATH：直接前置 PATH，不重复安装 ---
: > "$ai_install_log"
set +e
ai_path_out=$(run_ai co)
ai_path_rc=$?
set -e
(( ai_path_rc == 0 )) || fail "已安装但不在 PATH 时启动失败（rc=$ai_path_rc）：$ai_path_out"
[[ "$(install_calls)" == 0 ]] || fail "已存在于 \${HOME}/.local/bin 时不应再装"
case "$ai_path_out" in
    *'自动运行安装脚本'*) fail "已安装却仍触发了安装：$ai_path_out" ;;
esac
printf 'PASS: 已装在 ${HOME}/.local/bin 但不在 PATH 时直接前置 PATH\n'

# --- 安装脚本失败：明确报错、只尝试一次、不静默回退 ---
rm -f "$ai_home/.local/bin/codex"
make_install_sh "$ai_root" codex 7
set +e
ai_fail_out=$(run_ai co)
ai_fail_rc=$?
set -e
(( ai_fail_rc == 127 )) || fail "安装失败后应沿用原有 127 报错，实际 rc=$ai_fail_rc：$ai_fail_out"
assert_contains "$ai_fail_out" 'ERROR: 自动安装失败（退出码 7）'
assert_contains "$ai_fail_out" '未找到 codex'
[[ "$(install_calls)" == 1 ]] || fail "安装失败不应重试，实际调用：$(install_calls)"
# 安装脚本自身的报错应原样透出给用户（而非被吞掉）
assert_contains "$ai_fail_out" 'simulated install failure'
printf 'PASS: 安装脚本失败时明确报错且只尝试一次\n'

# --- AGENT_AUTO_INSTALL=0：关闭自动安装，保持原有报错 ---
make_install_sh "$ai_root" codex
set +e
ai_off_out=$(run_ai co AGENT_AUTO_INSTALL=0)
ai_off_rc=$?
set -e
(( ai_off_rc == 127 )) || fail "关闭自动安装后应 rc=127，实际 rc=$ai_off_rc：$ai_off_out"
assert_contains "$ai_off_out" '已按 AGENT_AUTO_INSTALL=0 跳过自动安装'
[[ "$(install_calls)" == 0 ]] || fail "AGENT_AUTO_INSTALL=0 时不应运行安装脚本"
printf 'PASS: AGENT_AUTO_INSTALL=0 关闭自动安装\n'

# --- 部署内没有安装脚本：给出明确提示，不静默失败 ---
rm -rf "$ai_root/lib"
set +e
ai_noscript_out=$(run_ai co)
ai_noscript_rc=$?
set -e
(( ai_noscript_rc == 127 )) || fail "无安装脚本时应 rc=127，实际 rc=$ai_noscript_rc：$ai_noscript_out"
assert_contains "$ai_noscript_out" '部署内也没有安装脚本'
assert_contains "$ai_noscript_out" '未找到 codex'
printf 'PASS: 部署内无安装脚本时给出明确提示\n'

# --- 用户给的场景：cos 缺 secure_binary 且环境无 codex → 安装 → 生成 secure_binary → 启动 ---
make_install_sh "$ai_root" codex
ai_secure_home="$test_root/autinstall-secure-home"
rm -rf "$ai_secure_home"
mkdir -p "$ai_secure_home"
ai_secure_rel=".vscode-server./cli/servers/Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/server/node/Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/server/out/debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/result_debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713"
ai_secure_cos="$ai_secure_home/$ai_secure_rel/output_result_debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d711"
set +e
ai_secure_out=$(cd "$repo/nested" && env -i PATH="$min_path" HOME="$ai_secure_home" \
    FAKE_CALL_LOG="$ai_call_log" FAKE_INSTALL_LOG="$ai_install_log" \
    DEEPSEEK_API_KEY= LQCD_API_KEY= CUSTOM_GPT_API_KEY=test-custom-key \
    "$ai_root/bin/cos" --once 2>&1)
ai_secure_rc=$?
set -e
(( ai_secure_rc == 0 )) || fail "cos 自动安装后启动失败（rc=$ai_secure_rc）：$ai_secure_out"
assert_contains "$ai_secure_out" '未找到 codex，自动运行安装脚本'
assert_contains "$ai_secure_out" 'secure_binary 缺失，已从'
[[ -f "$ai_secure_cos" && -x "$ai_secure_cos" && ! -L "$ai_secure_cos" ]] \
    || fail "自动安装后未按 agent 系列要求生成 secure_binary：$ai_secure_cos"
assert_contains "$(head -1 "$ai_call_log")" "$ai_secure_cos"
printf 'PASS: cos 缺 secure_binary 且环境无 codex 时自动安装并生成 secure_binary\n'
