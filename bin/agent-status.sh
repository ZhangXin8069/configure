#!/usr/bin/env bash
# Read-only inspection of agent.sh durable run manifests.

set -Eeuo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd -- "$(dirname -- "$SCRIPT_PATH")" && pwd -P)"

usage() {
    cat <<'USAGE'
用法：agent-status.sh [--all] [--json] [RUN_ID]

默认显示最新一次运行；RUN_ID 显示指定运行；--all 显示全部运行。
数据目录优先级：AGENT_DATA_DIR、CONFIGURE_AGENT_DATA_DIR、
${HOME}/configure/data（HOME 未设置时回退到仓库 data/）。
本命令只读，不恢复、不删除、不修改任何运行状态。
USAGE
}

if [[ -r "${SCRIPT_DIR}/agent-runtime.sh" ]]; then
    # shellcheck source=/dev/null
    source "${SCRIPT_DIR}/agent-runtime.sh"
fi

if [[ -n "${AGENT_DATA_DIR:-}" ]]; then
    DATA_ROOT="$AGENT_DATA_DIR"
elif [[ -n "${CONFIGURE_AGENT_DATA_DIR:-}" ]]; then
    DATA_ROOT="$CONFIGURE_AGENT_DATA_DIR"
elif [[ -n "${HOME:-}" ]]; then
    DATA_ROOT="${HOME}/configure/data"
else
    DATA_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)/data"
fi

all_runs=0
json_mode=0
requested_id=""
while (($# > 0)); do
    case "$1" in
        --all)
            all_runs=1
            shift
            ;;
        --json)
            json_mode=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --*)
            printf 'agent-status.sh：未知选项：%s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
        *)
            if [[ -n "$requested_id" ]]; then
                printf 'agent-status.sh：只能指定一个 RUN_ID\n' >&2
                exit 2
            fi
            requested_id="$1"
            shift
            ;;
    esac
done

read_value() {
    local manifest="$1"
    local key="$2"
    awk -F= -v wanted="$key" '
        $1 == wanted {
            sub(/^[^=]*=/, "", $0)
            print
            exit
        }
    ' "$manifest"
}

json_escape() {
    if declare -F _agent_runtime_json_escape >/dev/null 2>&1; then
        _agent_runtime_json_escape "$1"
        return
    fi
    local value="${1:-}"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//$'\n'/\\n}"
    value="${value//$'\r'/\\r}"
    value="${value//$'\t'/\\t}"
    printf '%s' "$value"
}

if [[ -n "$requested_id" ]] && ! _agent_runtime_safe_run_id "$requested_id" 2>/dev/null; then
    printf 'agent-status.sh：RUN_ID 格式无效：%s\n' "$requested_id" >&2
    exit 2
fi

if [[ -n "$requested_id" ]]; then
    manifests=("${DATA_ROOT}/runs/${requested_id}/manifest.env")
elif (( all_runs )); then
    manifests=()
    if [[ -d "${DATA_ROOT}/runs" ]]; then
        while IFS= read -r manifest; do
            manifests+=("$manifest")
        done < <(find "${DATA_ROOT}/runs" -mindepth 2 -maxdepth 2 -type f -name manifest.env -print | sort -r)
    fi
else
    latest=""
    if [[ -d "${DATA_ROOT}/runs" ]]; then
        latest="$(find "${DATA_ROOT}/runs" -mindepth 2 -maxdepth 2 -type f -name manifest.env -print | sort -r | head -1)"
    fi
    manifests=()
    [[ -n "$latest" ]] && manifests+=("$latest")
fi

if (( ${#manifests[@]} == 0 )); then
    if (( json_mode )); then
        printf '[]\n'
    else
        printf 'agent-status：未找到运行记录：%s\n' "$DATA_ROOT"
    fi
    exit 0
fi

records=0
if (( json_mode )); then
    printf '['
fi
for manifest in "${manifests[@]}"; do
    if [[ ! -r "$manifest" ]]; then
        printf 'agent-status：manifest 不可读：%s\n' "$manifest" >&2
        continue
    fi
    run_id="$(read_value "$manifest" run_id)"
    [[ -n "$run_id" ]] || run_id="$(basename -- "$(dirname -- "$manifest")")"
    state="$(read_value "$manifest" state)"
    agent="$(read_value "$manifest" agent)"
    mode="$(read_value "$manifest" mode)"
    updated_at="$(read_value "$manifest" updated_at)"
    session_id="$(read_value "$manifest" session_id)"
    thread_id="$(read_value "$manifest" thread_id)"
    turn="$(read_value "$manifest" turn)"
    reason="$(read_value "$manifest" last_reason)"
    if [[ ! "$turn" =~ ^[0-9]+$ ]]; then
        turn=0
    fi

    if (( json_mode )); then
        (( records > 0 )) && printf ','
        printf '{"run_id":"%s","state":"%s","agent":"%s","mode":"%s","updated_at":"%s","session_id":"%s","thread_id":"%s","turn":%s,"last_reason":"%s","manifest":"%s"}' \
            "$(json_escape "$run_id")" \
            "$(json_escape "$state")" \
            "$(json_escape "$agent")" \
            "$(json_escape "$mode")" \
            "$(json_escape "$updated_at")" \
            "$(json_escape "$session_id")" \
            "$(json_escape "$thread_id")" \
            "${turn:-0}" \
            "$(json_escape "$reason")" \
            "$(json_escape "$manifest")"
    else
        printf 'run=%s state=%s agent=%s mode=%s turn=%s updated=%s\n' \
            "$run_id" "$state" "$agent" "$mode" "${turn:-0}" "$updated_at"
        [[ -n "$session_id" ]] && printf 'session_id=%s\n' "$session_id"
        [[ -n "$thread_id" ]] && printf 'thread_id=%s\n' "$thread_id"
        [[ -n "$reason" ]] && printf 'last_reason=%s\n' "$reason"
        printf 'manifest=%s\n' "$manifest"
    fi
    records=$((records + 1))
done
if (( json_mode )); then
    printf ']\n'
fi

(( records > 0 ))
