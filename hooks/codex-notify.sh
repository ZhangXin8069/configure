#!/usr/bin/env bash
# Best-effort completion notification.  Notification failure never blocks an agent.

set -Eeuo pipefail

title=${CODEX_HOOK_TITLE:-Codex}
message=${CODEX_HOOK_MESSAGE:-}

if (( $# > 0 )); then
    if [[ "$1" == '--title' ]]; then
        (( $# >= 2 )) || {
            printf 'codex-notify: --title 缺少值\n' >&2
            exit 2
        }
        title=$2
        shift 2
    fi
    if (( $# > 0 )); then
        message=$*
    fi
fi

if [[ -z "$message" && -n "${CODEX_HOOK_PAYLOAD:-}" ]]; then
    message=$CODEX_HOOK_PAYLOAD
elif [[ -z "$message" && ! -t 0 ]]; then
    message=$(< /dev/stdin)
fi

message=${message:-Codex agent 已完成当前任务}

# Accept a JSON event as a convenience, but never execute anything from it.
if [[ "$message" == \{* ]] && command -v python3 >/dev/null 2>&1; then
    if parsed=$(python3 - "$message" <<'PY'
import json
import sys

raw = sys.argv[1]
try:
    payload = json.loads(raw)
except (TypeError, ValueError):
    print(raw)
    raise SystemExit(0)

if isinstance(payload, dict):
    for key in ("message", "summary", "text", "last_message"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            print(value)
            break
    else:
        print("Codex agent event")
else:
    print(raw)
PY
    ); then
        [[ -n "$parsed" ]] && message=$parsed
    fi
fi

if command -v notify-send >/dev/null 2>&1; then
    if ! notify-send -- "$title" "$message" >/dev/null 2>&1; then
        printf 'codex-notify: notify-send 失败，已忽略\n' >&2
    fi
else
    printf 'codex-notify: %s：%s\n' "$title" "$message"
fi

exit 0
