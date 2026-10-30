#!/usr/bin/env bash
# Generic event adapter for Codex-style agent runners.
#
# This is an explicit local protocol.  It does not assume that a particular
# Codex release discovers files in this directory automatically.

set -Eeuo pipefail

hook_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
format=${AGENT_HOOK_FORMAT:-human}
requested_timeout=${AGENT_HOOK_TIMEOUT:-}

usage() {
    cat <<'USAGE'
用法：agent-hook.sh <事件> [参数...]

事件：
  session-start       会话开始只读预检
  session-summary     会话结束/交接只读摘要（兼容 handoff）
  before-edit         校验待编辑路径位于仓库内且不触及 .git/日志
  after-edit          校验当前工作树改动
  stop                停止前执行当前工作树验证
  agent-resume        检测意外中断并在 10 秒后调度原任务持续恢复
  plugin-audit        静态审计 Codex plugin/hook/MCP manifest，不执行插件代码
  notify              发送非阻塞完成通知

选项：
  --json              输出统一 JSONL event envelope，并写入持久事件日志
                      （也可用 AGENT_HOOK_FORMAT=json）
  --timeout SECONDS   覆盖本次 hook 的硬超时；默认按事件选择
  --list              列出规范事件、默认超时和阻塞语义

事件别名：start、preflight、pre-edit、before-tool、post-edit、after-tool、
turn-end、post-turn、notification、resume。
也可通过 AGENT_HOOK_EVENT 环境变量提供事件名。
USAGE
}

event_timeout() {
    case "$1" in
        session-start) printf '30\n' ;;
        session-summary|session-end|session-idle) printf '20\n' ;;
        before-edit) printf '10\n' ;;
        after-edit|post-edit|after-tool|turn-end|post-turn|turn-complete|stop) printf '120\n' ;;
        agent-resume) printf '15\n' ;;
        plugin-audit) printf '90\n' ;;
        notify) printf '10\n' ;;
        *) printf '30\n' ;;
    esac
}

list_events() {
    cat <<'LIST'
session-start   30s   blocking    只读上下文预检
session-summary 20s   blocking    只读交接摘要
before-edit     10s   blocking    路径边界保护
after-edit      120s  blocking    工作树、Shell 与日志验证
stop            120s  blocking    停止前验证
agent-resume    15s   detached    预检后异步调度恢复
plugin-audit    90s   blocking    plugin/hook/MCP manifest 静态审计
notify          10s   best-effort 本地通知
LIST
}

event=${AGENT_HOOK_EVENT:-}
while (( $# > 0 )); do
    case "$1" in
        --json)
            format=json
            shift
            ;;
        --human)
            format=human
            shift
            ;;
        --timeout)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            requested_timeout=$2
            shift 2
            ;;
        --list)
            list_events
            exit 0
            ;;
        -h|--help|help)
            usage
            exit 0
            ;;
        *)
            event=$1
            shift
            break
            ;;
    esac
done

target=""
canonical_event=""

case "$event" in
    session-start|start|preflight)
        target="$hook_dir/agent-preflight.sh"
        canonical_event=session-start
        ;;
    session-summary|handoff)
        target="$hook_dir/agent-summary.sh"
        canonical_event=session-summary
        ;;
    before-edit|pre-edit|before-tool)
        target="$hook_dir/agent-guard.sh"
        canonical_event=before-edit
        ;;
    after-edit|post-edit|after-tool|turn-end|post-turn|turn-complete|stop)
        target="$hook_dir/agent-verify.sh"
        canonical_event="$event"
        ;;
    agent-resume|resume-agent|resume)
        target="$hook_dir/agent-resume.sh"
        canonical_event=agent-resume
        ;;
    plugin-audit|audit-plugin|audit-plugins)
        target="$hook_dir/../tools/plugin-audit.py"
        canonical_event=plugin-audit
        ;;
    notify|notification)
        target="$hook_dir/agent-notify.sh"
        canonical_event=notify
        ;;
    session-end|session-idle)
        target="$hook_dir/agent-summary.sh"
        canonical_event="$event"
        ;;
    '')
        usage >&2
        printf 'agent-hook.sh: 缺少事件名\n' >&2
        exit 2
        ;;
    *)
        usage >&2
        printf 'agent-hook.sh: 未知事件：%s\n' "$event" >&2
        exit 2
        ;;
esac

if [[ -z "$requested_timeout" ]]; then
    requested_timeout=$(event_timeout "$canonical_event")
fi
if [[ ! "$requested_timeout" =~ ^[1-9][0-9]*$ ]]; then
    printf 'agent-hook.sh: --timeout 必须是正整数秒：%s\n' "$requested_timeout" >&2
    exit 2
fi

terminate_hook_group() {
    local pid="$1"
    local target
    local _attempt

    if kill -0 -- "-$pid" 2>/dev/null; then
        target="-$pid"
    elif kill -0 "$pid" 2>/dev/null; then
        target="$pid"
    else
        return 0
    fi

    kill -TERM -- "$target" 2>/dev/null || true
    for _attempt in 1 2 3 4 5 6 7 8 9 10; do
        if [[ "$target" == -* ]]; then
            kill -0 -- "$target" 2>/dev/null || return 0
        else
            kill -0 "$target" 2>/dev/null || return 0
        fi
        sleep 0.05
    done
    kill -KILL -- "$target" 2>/dev/null || true
}

terminate_hook_process() {
    local pid="$1"
    terminate_hook_group "$pid"
    wait "$pid" 2>/dev/null || true
}

hook_started_at=$(date '+%s')
remaining_hook_timeout() {
    local now elapsed remaining
    now=$(date '+%s')
    elapsed=$((now - hook_started_at))
    remaining=$((requested_timeout - elapsed))
    (( remaining > 0 )) || return 1
    printf '%s\n' "$remaining"
}

active_hook_pid=""
launching_hook=0
pending_signal_code=""
forward_hook_signal() {
    local code="$1"
    if [[ -z "$active_hook_pid" ]] && (( launching_hook )); then
        pending_signal_code=$code
        return 0
    fi
    trap '' HUP INT TERM
    if [[ -n "$active_hook_pid" ]]; then
        terminate_hook_process "$active_hook_pid"
        active_hook_pid=""
    fi
    exit "$code"
}
trap 'forward_hook_signal 129' HUP
trap 'forward_hook_signal 130' INT
trap 'forward_hook_signal 143' TERM

run_hook_target() {
    local timeout=$1
    local cleanup_survivors=$2
    shift 2
    local pid started now elapsed rc monitor_was_on=0 signal_code
    started=$(date '+%s')
    case $- in *m*) monitor_was_on=1;; esac
    launching_hook=1
    pending_signal_code=""
    set -m
    "$@" &
    pid=$!
    active_hook_pid=$pid
    (( monitor_was_on )) || set +m
    launching_hook=0
    if [[ -n "$pending_signal_code" ]]; then
        signal_code=$pending_signal_code
        pending_signal_code=""
        forward_hook_signal "$signal_code"
    fi
    while kill -0 "$pid" 2>/dev/null; do
        now=$(date '+%s')
        elapsed=$((now - started))
        if (( elapsed >= timeout )); then
            terminate_hook_process "$pid"
            active_hook_pid=""
            printf 'agent-hook.sh: 事件 %s 超过 %ss 硬超时，已终止\n' \
                "$canonical_event" "$requested_timeout" >&2
            return 124
        fi
        sleep 0.2
    done
    if wait "$pid"; then
        rc=0
    else
        rc=$?
    fi
    if (( cleanup_survivors || rc != 0 )); then
        terminate_hook_group "$pid"
    fi
    active_hook_pid=""
    return "$rc"
}

if [[ "$format" != json ]]; then
    set +e
    if [[ "$canonical_event" == agent-resume ]]; then
        run_hook_target "$requested_timeout" 0 "$target" "$@"
    else
        run_hook_target "$requested_timeout" 1 "$target" "$@"
    fi
    hook_status=$?
    set -e
    exit "$hook_status"
fi

tmp_output=$(mktemp "${TMPDIR:-/tmp}/agent-hook.XXXXXX")
cleanup() {
    rm -f -- "$tmp_output"
}
trap cleanup EXIT

set +e
if [[ "$canonical_event" == agent-resume ]]; then
    run_hook_target "$requested_timeout" 0 "$target" "$@" >"$tmp_output" 2>&1
else
    run_hook_target "$requested_timeout" 1 "$target" "$@" >"$tmp_output" 2>&1
fi
hook_status=$?
set -e

detail=$(head -c 8192 "$tmp_output")
event_status=ok
if (( hook_status != 0 )); then
    event_status=failed
fi

if ! event_timeout=$(remaining_hook_timeout); then
    if [[ -s "$tmp_output" ]]; then
        cat -- "$tmp_output" >&2
    fi
    printf 'agent-hook.sh: 事件 %s 超过 %ss 硬超时，事件写入未启动\n' \
        "$canonical_event" "$requested_timeout" >&2
    exit 124
fi
set +e
AGENT_HOOK_SOURCE="${AGENT_HOOK_SOURCE:-native-adapter}" \
    run_hook_target "$event_timeout" 1 \
    "${hook_dir}/agent-event.sh" "$canonical_event" "$event_status" "$detail"
event_status_code=$?
set -e
if (( event_status_code != 0 )); then
    exit "$event_status_code"
fi
exit "$hook_status"
