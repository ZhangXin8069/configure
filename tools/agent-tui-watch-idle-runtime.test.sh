#!/usr/bin/env bash
# Verify bin/agent-runtime.sh forwards idle-nudge settings to the TUI watcher.

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
test_root=$(mktemp -d "${TMPDIR:-/tmp}/agent-idle-runtime.XXXXXX")
cleanup() {
    rm -rf -- "$test_root"
}
trap cleanup EXIT HUP INT TERM

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

unset AGENT_AUTO_RESUME AGENT_RESUME_ACTIVE AGENT_TUI_IDLE_COMMAND_JSON \
    AGENT_EVENT_FILE AGENT_STOP_FILE AGENT_MANIFEST_FILE AGENT_STATE_FILE 2>/dev/null || true

run_dir=$test_root/run
mkdir -p "$run_dir"
run_id=20260101T000000.idle
printf 'run_id=%s\n' "$run_id" >"$run_dir/manifest.env"
printf '{}\n' >"$run_dir/.idle-nudge-enabled"

log=$run_dir/tui-watch.log
runtime=$script_dir/../bin/agent-runtime.sh

AGENT_CONFIGURE_ROOT=$(CDPATH= cd -- "$script_dir/.." && pwd) \
AGENT_RUN_ID=$run_id \
AGENT_RUN_DIR=$run_dir \
AGENT_WORKDIR=$test_root \
AGENT_STATE_PYTHON=python3 \
AGENT_TUI_WATCH_INTERVAL=0.05 \
AGENT_TUI_WATCH_MAX_RUNTIME=1.5 \
AGENT_TUI_WATCH_HEARTBEAT=10 \
AGENT_TUI_WATCH_STATE_TIMEOUT=2 \
AGENT_TUI_WATCH_RECOVER_TIMEOUT=2 \
AGENT_IDLE_NUDGE_SECONDS=1 \
AGENT_IDLE_NUDGE_POLL=0.05 \
AGENT_IDLE_NUDGE_MAX=3 \
AGENT_TUI_IDLE_COMMAND_JSON='["/bin/true","{message}"]' \
    bash -c '
        source "$1"; shift
        AGENT_TUI_IDLE_COMMAND_JSON=$AGENT_TUI_IDLE_COMMAND_JSON \
            _agent_runtime_run_tui_watched commandcode "[]" \
            python3 -c "import time; time.sleep(1.2)"
    ' _ "$runtime" >/dev/null 2>&1

[[ -f "$log" ]] || fail "watcher 未生成日志：$log"
grep -Fq 'idle_nudge=1' "$log" || fail 'watcher 未收到空闲注入开关'
grep -Fq 'idle_seconds=1.0' "$log" || fail 'watcher 未收到空闲阈值'
[[ -f "$run_dir/.tui-watch.pid" ]] || fail 'watcher pid 文件未写入'

# 未武装（无启用标记）时 watcher 应跳过注入。
run_dir2=$test_root/run2
mkdir -p "$run_dir2"
printf 'run_id=%s\n' "$run_id" >"$run_dir2/manifest.env"
AGENT_CONFIGURE_ROOT=$(CDPATH= cd -- "$script_dir/.." && pwd) \
AGENT_RUN_ID=$run_id \
AGENT_RUN_DIR=$run_dir2 \
AGENT_WORKDIR=$test_root \
AGENT_STATE_PYTHON=python3 \
AGENT_TUI_WATCH_INTERVAL=0.05 \
AGENT_TUI_WATCH_MAX_RUNTIME=1 \
AGENT_TUI_WATCH_HEARTBEAT=10 \
AGENT_TUI_WATCH_STATE_TIMEOUT=2 \
AGENT_TUI_WATCH_RECOVER_TIMEOUT=2 \
AGENT_IDLE_NUDGE_SECONDS=1 \
AGENT_IDLE_NUDGE_POLL=0.05 \
AGENT_TUI_IDLE_COMMAND_JSON='["/bin/true","{message}"]' \
    bash -c '
        source "$1"; shift
        AGENT_TUI_IDLE_COMMAND_JSON=$AGENT_TUI_IDLE_COMMAND_JSON \
            _agent_runtime_run_tui_watched commandcode "[]" \
            python3 -c "import time; time.sleep(0.8)"
    ' _ "$runtime" >/dev/null 2>&1

if grep -Fq 'action=idle-nudge ' "$run_dir2/tui-watch.log" 2>/dev/null; then
    fail '未武装时 watcher 不应注入'
fi

printf 'PASS: agent-runtime 转发空闲注入参数并写入 watcher pid\n'
