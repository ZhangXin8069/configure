#!/usr/bin/env bash
# Generic event adapter for Codex-style agent runners.
#
# This is an explicit local protocol.  It does not assume that a particular
# Codex release discovers files in this directory automatically.

set -Eeuo pipefail

hook_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
format=${AGENT_HOOK_FORMAT:-human}

usage() {
    cat <<'USAGE'
用法：agent-hook.sh <事件> [参数...]

事件：
  session-start       会话开始只读预检
  session-summary     会话结束/交接只读摘要（兼容 handoff）
  before-edit         校验待编辑路径位于仓库内且不触及 .git/日志
  after-edit          校验当前工作树改动
  stop                停止前执行当前工作树验证
  agent-resume        检测瞬时中断并在 10 秒后调度原任务恢复
  notify              发送非阻塞完成通知

选项：
  --json              输出统一 JSONL event envelope，并写入持久事件日志
                      （也可用 AGENT_HOOK_FORMAT=json）

事件别名：start、preflight、pre-edit、before-tool、post-edit、after-tool、
turn-end、post-turn、notification、resume。
也可通过 AGENT_HOOK_EVENT 环境变量提供事件名。
USAGE
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

if [[ "$format" != json ]]; then
    exec "$target" "$@"
fi

tmp_output=$(mktemp "${TMPDIR:-/tmp}/agent-hook.XXXXXX")
cleanup() {
    rm -f -- "$tmp_output"
}
trap cleanup EXIT HUP INT TERM

set +e
"$target" "$@" >"$tmp_output" 2>&1
hook_status=$?
set -e

detail=$(<"$tmp_output")
event_status=ok
if (( hook_status != 0 )); then
    event_status=failed
fi

AGENT_HOOK_SOURCE="${AGENT_HOOK_SOURCE:-native-adapter}" \
    "${hook_dir}/agent-event.sh" "$canonical_event" "$event_status" "$detail"
exit "$hook_status"
