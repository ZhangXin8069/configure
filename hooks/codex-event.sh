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

json_escape() {
    local value="${1:-}"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//$'\n'/\\n}"
    value="${value//$'\r'/\\r}"
    value="${value//$'\t'/\\t}"
    printf '%s' "$value"
}

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

detail="$(printf '%s' "$detail" | tr '\n' ' ' | cut -c1-2000)"
timestamp="$(date '+%Y-%m-%dT%H:%M:%S%z')"
line=$(printf '{"schema_version":"1","event":"%s","timestamp":"%s","source":"%s","cwd":"%s","repo_root":"%s","run_id":"%s","session_id":"%s","thread_id":"%s","turn_id":"%s","status":"%s","detail":"%s"}' \
    "$(json_escape "$event")" \
    "$(json_escape "$timestamp")" \
    "$(json_escape "${CODEX_HOOK_SOURCE:-adapter}")" \
    "$(json_escape "$PWD")" \
    "$(json_escape "$repo_root")" \
    "$(json_escape "${CODEX_HOOK_RUN_ID:-${AGENT_RUN_ID:-}}")" \
    "$(json_escape "${CODEX_HOOK_SESSION_ID:-${AGENT_SESSION_ID:-}}")" \
    "$(json_escape "${CODEX_HOOK_THREAD_ID:-${AGENT_THREAD_ID:-}}")" \
    "$(json_escape "${CODEX_HOOK_TURN_ID:-${AGENT_TURN_ID:-}}")" \
    "$(json_escape "$status")" \
    "$(json_escape "$detail")")

printf '%s\n' "$line" >> "$event_file"
printf '%s\n' "$line"
