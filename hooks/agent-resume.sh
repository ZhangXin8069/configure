#!/usr/bin/env bash
# Schedule the agent-resume supervisor after an unexpected agent failure.

set -Eeuo pipefail

hook_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd)
config_root=${AGENT_CONFIGURE_ROOT:-$(CDPATH= cd -- "${hook_dir}/.." && pwd)}
tool=${AGENT_RESUME_TOOL:-${config_root}/tools/agent-resume.sh}

run_id=${AGENT_RUN_ID:-}
data_root=${AGENT_DATA_DIR:-${config_root}/data}
delay=${AGENT_RESUME_DELAY:-10}
provider=${AGENT_RESUME_PROVIDER:-${AGENT_PARENT_PROVIDER:-}}
launcher_override=${AGENT_RESUME_LAUNCHER:-}
mode=schedule

usage() {
    cat <<'USAGE'
用法：agent-resume.sh [--run-id RUN_ID] [--data-root DIR] [--delay SECONDS]
                     [--provider NAME] [--launcher PATH] [--check|--foreground]

默认只做快速预检，随后脱离当前 agent 进程启动 tools/agent-resume.sh；
预检失败时不调度。--check 只报告可恢复性，--foreground 用于调试或测试。
USAGE
}

while (( $# > 0 )); do
    case "$1" in
        --run-id)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            run_id=$2; shift 2;;
        --data-root)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            data_root=$2; shift 2;;
        --delay)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            delay=$2; shift 2;;
        --provider)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            provider=$2; shift 2;;
        --launcher)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            launcher_override=$2; shift 2;;
        --check)
            mode=check; shift;;
        --foreground)
            mode=foreground; shift;;
        -h|--help)
            usage; exit 0;;
        *)
            printf 'agent-resume.sh：未知参数：%s\n' "$1" >&2
            usage >&2
            exit 2;;
    esac
done

[[ "$delay" =~ ^[0-9]+$ ]] || {
    printf 'agent-resume.sh：--delay 必须是非负整数：%s\n' "$delay" >&2
    exit 2
}
[[ -x "$tool" ]] || {
    printf 'agent-resume.sh：恢复工具不存在或不可执行：%s\n' "$tool" >&2
    exit 7
}

tool_args=()
[[ -z "$run_id" ]] || tool_args+=(--run-id "$run_id")
[[ -z "$data_root" ]] || tool_args+=(--data-root "$data_root")
tool_args+=(--delay "$delay" --timeout "${AGENT_RESUME_TIMEOUT:-1800}")
[[ -z "$provider" ]] || tool_args+=(--provider "$provider")
[[ -z "$launcher_override" ]] || tool_args+=(--launcher "$launcher_override")

set +e
check_output=$("$tool" "${tool_args[@]}" --check 2>&1)
check_status=$?
set -e

if (( check_status != 0 )); then
    printf '%s\n' "$check_output"
    if (( check_status == 3 )); then
        exit 0
    fi
    exit "$check_status"
fi

if [[ "$mode" == check ]]; then
    printf '%s\n' "$check_output"
    exit 0
fi
if [[ "$mode" == foreground ]]; then
    exec "$tool" "${tool_args[@]}"
fi

run_dir=""
if [[ -n "$run_id" ]]; then
    run_dir=${data_root}/runs/${run_id}
fi
if [[ -n "$run_dir" && -d "$run_dir" ]]; then
    dispatch_log=${run_dir}/resume-hook.log
else
    mkdir -p -- "${data_root}/hooks"
    dispatch_log=${data_root}/hooks/agent-resume-dispatch.log
fi

(
    trap '' HUP
    export AGENT_DATA_DIR="$data_root"
    export AGENT_RESUME_PROVIDER="$provider"
    [[ -z "$launcher_override" ]] || export AGENT_RESUME_LAUNCHER="$launcher_override"
    exec "$tool" "${tool_args[@]}"
) >>"$dispatch_log" 2>&1 </dev/null &
resume_pid=$!

printf 'agent-resume：status=scheduled run_id=%s delay=%s pid=%s log=%s\n' \
    "${run_id:-auto}" "$delay" "$resume_pid" "$dispatch_log"
printf '%s\n' "$check_output"
