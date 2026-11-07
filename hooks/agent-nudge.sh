#!/usr/bin/env bash
# Arm or disarm the auto-skill idle nudge for the current agent run.

set -Eeuo pipefail

hook_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd)
config_root=${AGENT_CONFIGURE_ROOT:-$(CDPATH= cd -- "${hook_dir}/.." && pwd)}
tool=${AGENT_IDLE_NUDGE_TOOL:-${config_root}/tools/agent-idle-nudge.sh}

usage() {
    cat <<'USAGE'
用法：agent-nudge.sh <enable|disable|complete|status> [选项]

auto 技能在无人值守循环中启用空闲看门狗：当 agent 已停止工作（回合完成）
且连续 AGENT_IDLE_NUDGE_SECONDS（默认 300 秒）没有真实用户输入时，
TUI 看门狗以用户身份注入一条“汇报阶段进度并继续下一轮”的指令。

选项：
  --goal TEXT       任务定义（enable 时记录，供审计）
  --manifest PATH   运行 manifest
  --run-dir DIR     运行目录
  --run-id ID       运行 id
  --data-root DIR   数据根
  --check           只报告标记状态（等价 status）
  -h, --help        显示帮助

退出码：0 成功；2 参数或运行上下文错误；7 缺少 python3。
USAGE
}

command_name=${1:-status}
if (( $# > 0 )); then
    shift
fi
args=()
goal=""

while (( $# > 0 )); do
    case "$1" in
        --goal)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            goal=$2; shift 2;;
        --manifest|--run-dir|--run-id|--data-root)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            args+=("$1" "$2"); shift 2;;
        --check)
            command_name=status; shift;;
        -h|--help)
            usage; exit 0;;
        *)
            printf 'agent-nudge.sh：未知参数：%s\n' "$1" >&2
            usage >&2
            exit 2;;
    esac
done

case "${command_name}" in
    enable|disable|complete|status) ;;
    *)
        printf 'agent-nudge.sh：未知命令：%s\n' "$command_name" >&2
        usage >&2
        exit 2;;
esac

[[ -x "${tool}" ]] || {
    printf 'agent-nudge.sh：空闲注入工具不存在或不可执行：%s\n' "${tool}" >&2
    exit 7
}

tool_args=("${command_name}" "${args[@]}")
[[ -z "${goal}" ]] || tool_args+=(--goal "${goal}")
exec "${tool}" "${tool_args[@]}"
