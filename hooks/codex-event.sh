#!/usr/bin/env bash
# Emit one durable Codex hook event using the configure JSONL envelope.

set -Eeuo pipefail

event="${1:-}"
status="${2:-info}"
detail="${3:-}"
if [[ -z "$event" ]]; then
    printf 'codex-event.sh：缺少事件名\n' >&2
    exit 2
fi

if command -v python3 >/dev/null 2>&1; then
    json_encoder=python3
elif command -v jq >/dev/null 2>&1; then
    json_encoder=jq
else
    printf 'codex-event.sh：JSON 编码需要 python3 或 jq\n' >&2
    exit 2
fi

repo_root=""
if command -v git >/dev/null 2>&1; then
    repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
    if [[ -n "$repo_root" ]]; then
        repo_root="$(cd -- "$repo_root" && pwd -P)"
    fi
fi

if [[ -n "${CODEX_HOOK_DATA_DIR:-}" ]]; then
    data_root="$CODEX_HOOK_DATA_DIR"
elif [[ -n "${AGENT_DATA_DIR:-}" ]]; then
    data_root="${AGENT_DATA_DIR}/hooks"
elif [[ -n "${HOME:-}" ]]; then
    data_root="${HOME}/configure/data/hooks"
else
    data_root="${TMPDIR:-/tmp}/configure-agent-hooks"
fi
mkdir -p -- "$data_root"

event_file="${CODEX_HOOK_EVENT_FILE:-${data_root}/events.jsonl}"
mkdir -p -- "$(dirname -- "$event_file")"

timestamp="$(date '+%Y-%m-%dT%H:%M:%S%z')"
if [[ "$json_encoder" == python3 ]]; then
    line=$(python3 - \
        "$event" \
        "$timestamp" \
        "${CODEX_HOOK_SOURCE:-adapter}" \
        "$PWD" \
        "$repo_root" \
        "${CODEX_HOOK_RUN_ID:-${AGENT_RUN_ID:-}}" \
        "${CODEX_HOOK_SESSION_ID:-${AGENT_SESSION_ID:-}}" \
        "${CODEX_HOOK_THREAD_ID:-${AGENT_THREAD_ID:-}}" \
        "${CODEX_HOOK_TURN_ID:-${AGENT_TURN_ID:-}}" \
        "$status" \
        "$detail" <<'PY'
import json
import sys

keys = (
    "event",
    "timestamp",
    "source",
    "cwd",
    "repo_root",
    "run_id",
    "session_id",
    "thread_id",
    "turn_id",
    "status",
    "detail",
)
values = sys.argv[1:]
if len(values) != len(keys):
    raise SystemExit("unexpected event field count")

record = {"schema_version": "1"}
record.update(zip(keys, values))
record["detail"] = record["detail"].replace("\n", " ")[:2000]
json.dump(record, sys.stdout, ensure_ascii=False, separators=(",", ":"))
sys.stdout.write("\n")
PY
)
else
    line=$(jq -cn \
        --arg schema_version 1 \
        --arg event "$event" \
        --arg timestamp "$timestamp" \
        --arg source "${CODEX_HOOK_SOURCE:-adapter}" \
        --arg cwd "$PWD" \
        --arg repo_root "$repo_root" \
        --arg run_id "${CODEX_HOOK_RUN_ID:-${AGENT_RUN_ID:-}}" \
        --arg session_id "${CODEX_HOOK_SESSION_ID:-${AGENT_SESSION_ID:-}}" \
        --arg thread_id "${CODEX_HOOK_THREAD_ID:-${AGENT_THREAD_ID:-}}" \
        --arg turn_id "${CODEX_HOOK_TURN_ID:-${AGENT_TURN_ID:-}}" \
        --arg status "$status" \
        --arg detail "$detail" \
        '{
            schema_version: $schema_version,
            event: $event,
            timestamp: $timestamp,
            source: $source,
            cwd: $cwd,
            repo_root: $repo_root,
            run_id: $run_id,
            session_id: $session_id,
            thread_id: $thread_id,
            turn_id: $turn_id,
            status: $status,
            detail: ($detail | gsub("\n"; " ") | .[0:2000])
        }')
fi

printf '%s\n' "$line" >> "$event_file"
printf '%s\n' "$line"
