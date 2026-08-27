#!/usr/bin/env bash
# Generic event adapter for Codex-style agent runners.
#
# This is an explicit local protocol.  It does not assume that a particular
# Codex release discovers files in this directory automatically.

set -Eeuo pipefail

hook_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

usage() {
    cat <<'USAGE'
用法：codex-hook.sh <事件> [参数...]

事件：
  session-start       会话开始只读预检
  before-edit         校验待编辑路径位于仓库内且不触及 .git/日志
  after-edit          校验当前工作树改动
  stop                停止前执行当前工作树验证
  notify              发送非阻塞完成通知

事件别名：start、preflight、pre-edit、before-tool、post-edit、after-tool、
turn-end、post-turn、notification。
也可通过 CODEX_HOOK_EVENT 环境变量提供事件名。
USAGE
}

event=${CODEX_HOOK_EVENT:-}
if (( $# > 0 )); then
    event=$1
    shift
fi

case "$event" in
    -h|--help|help)
        usage
        exit 0
        ;;
    session-start|start|preflight)
        exec "$hook_dir/codex-preflight.sh" "$@"
        ;;
    before-edit|pre-edit|before-tool)
        exec "$hook_dir/codex-guard.sh" "$@"
        ;;
    after-edit|post-edit|after-tool|turn-end|post-turn|stop)
        exec "$hook_dir/codex-verify.sh" "$@"
        ;;
    notify|notification)
        exec "$hook_dir/codex-notify.sh" "$@"
        ;;
    '')
        usage >&2
        printf 'codex-hook.sh: 缺少事件名\n' >&2
        exit 2
        ;;
    *)
        usage >&2
        printf 'codex-hook.sh: 未知事件：%s\n' "$event" >&2
        exit 2
        ;;
esac
