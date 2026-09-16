#!/usr/bin/env bash
# Claude Code statusLine 渲染器：输出与 co（Codex tui.status_line）同款字段的一行状态栏。
# 由 Claude Code 高频调用（stdin 传入官方状态 JSON，stdout 首行为状态栏），只输出一行。
# 官方字段映射：model.display_name→model-with-reasoning、effort.level→推理强度、
#   workspace.current_dir→current-dir、context_window.*→context-used、
#   rate_limits.seven_day.used_percentage→weekly-limit、fast_mode→fast-mode、
#   cost.total_cost_usd→estimated-thread-cost、session_id→thread-id；
#   run-state/permissions/branch-changes 由本地环境与 git 提供。
# 配置（由 agent.sh 从 agent-config.json / agent-custom.json 注入）：
#   AGENT_STATUSLINE_SEGMENTS      JSON 数组字符串（如 ["model-with-reasoning","thread-id"]）
#   AGENT_STATUSLINE_USE_COLORS    true/false
#   AGENT_PERMISSION_MODE          权限模式（permissions/approval-mode 段）
#   AGENT_RUN_DIR                  data run 目录（run-state 段读 state.env）

set -u

payload="$(cat 2>/dev/null || true)"
segments_raw="${AGENT_STATUSLINE_SEGMENTS:-[]}"
use_colors="${AGENT_STATUSLINE_USE_COLORS:-true}"

# JSON 数组字符串 → 逗号分隔（去方括号与引号）
segments="${segments_raw#[}"
segments="${segments%]}"
segments="${segments//\"/}"

# 轻量 JSON 取值：payload 为单行小对象，grep/sed 足够且避免解释器启动开销
_field() { # 顶层字符串键
    printf '%s' "${payload}" | grep -o "\"$1\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" 2>/dev/null \
        | head -1 | sed 's/^[^:]*:[[:space:]]*"//; s/"$//'
}
_number() { # 顶层数字键
    printf '%s' "${payload}" | grep -o "\"$1\"[[:space:]]*:[[:space:]]*[0-9][0-9.eE+-]*" 2>/dev/null \
        | head -1 | sed 's/.*:[[:space:]]*//'
}
_value_in() { # 一个对象层内的字符串键（section, key）
    printf '%s' "${payload}" | grep -o "\"$1\"[[:space:]]*:[[:space:]]*{[^}]*\"$2\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" 2>/dev/null \
        | head -1 | sed 's/.*":[[:space:]]*"//; s/"$//'
}
_number_in() { # 一个对象层内的数字键（section, key）
    printf '%s' "${payload}" | grep -o "\"$1\"[[:space:]]*:[[:space:]]*{[^}]*\"$2\"[[:space:]]*:[[:space:]]*[0-9][0-9.eE+-]*" 2>/dev/null \
        | head -1 | sed 's/.*:[[:space:]]*//'
}
_bool_field() { # 顶层布尔键
    printf '%s' "${payload}" | grep -o "\"$1\"[[:space:]]*:[[:space:]]*\(true\|false\)" 2>/dev/null \
        | head -1 | sed 's/^[^:]*:[[:space:]]*//'
}

if [[ "${use_colors}" == "true" ]]; then
    _C_DIM=$'\033[2m'; _C_CYAN=$'\033[36m'; _C_GREEN=$'\033[32m'
    _C_YELLOW=$'\033[33m'; _C_MAGENTA=$'\033[35m'; _C_RESET=$'\033[0m'
else
    _C_DIM=""; _C_CYAN=""; _C_GREEN=""; _C_YELLOW=""; _C_MAGENTA=""; _C_RESET=""
fi

# 渲染单个 segment；无数据时返回 1（调用方跳过）
_render() {
    local seg="$1" value="" model level dir cwd branch changes pct total window sid cost fast
    case "${seg}" in
        model-with-reasoning)
            model="$(_field display_name)"
            [[ -n "${model}" ]] || model="${ANTHROPIC_MODEL:-}"
            [[ -n "${model}" ]] || return 1
            level="$(_value_in effort level)"
            [[ -n "${level}" ]] || level="${CLAUDE_CODE_EFFORT_LEVEL:-}"
            value="${_C_CYAN}${model}${_C_RESET}"
            [[ -n "${level}" ]] && value+=" ${_C_DIM}(${level})${_C_RESET}"
            ;;
        current-dir)
            dir="$(_field current_dir)"
            [[ -n "${dir}" ]] || return 1
            value="${_C_DIM}${dir/#${HOME}/~}${_C_RESET}"
            ;;
        hostname)
            value="${_C_DIM}$(hostname 2>/dev/null)${_C_RESET}"
            [[ -n "${value}" ]] || return 1
            ;;
        branch-changes)
            cwd="$(_field current_dir)"; [[ -n "${cwd}" ]] || cwd="${PWD}"
            branch="$(git -C "${cwd}" rev-parse --abbrev-ref HEAD 2>/dev/null)" || return 1
            [[ -n "${branch}" ]] || return 1
            changes="$(git -C "${cwd}" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
            value="${_C_GREEN}${branch}${_C_RESET}"
            [[ "${changes}" != "0" ]] && value+="${_C_YELLOW}*${changes}${_C_RESET}"
            ;;
        run-state)
            [[ -n "${AGENT_RUN_DIR:-}" && -r "${AGENT_RUN_DIR}/state.env" ]] || return 1
            value="$(sed -n 's/^state=//p' "${AGENT_RUN_DIR}/state.env" 2>/dev/null | head -1)"
            [[ -n "${value}" ]] || return 1
            value="${_C_MAGENTA}${value}${_C_RESET}"
            ;;
        permissions)
            [[ -n "${AGENT_PERMISSION_MODE:-}" ]] || return 1
            value="${_C_YELLOW}${AGENT_PERMISSION_MODE}${_C_RESET}"
            ;;
        approval-mode)
            [[ -n "${AGENT_PERMISSION_MODE:-}" ]] || return 1
            value="${_C_YELLOW}approval:${AGENT_PERMISSION_MODE}${_C_RESET}"
            ;;
        context-used)
            pct="$(_number_in context_window used_percentage)"
            [[ -n "${pct}" ]] || return 1
            pct="${pct%%.*}"
            total="$(_number_in context_window total_input_tokens)"
            window="$(_number_in context_window context_window_size)"
            if [[ -n "${window}" && -n "${total}" && "${window}" -gt 0 ]]; then
                value="${_C_DIM}ctx ${pct}% $((total / 1000))k/$((window / 1000))k${_C_RESET}"
            else
                value="${_C_DIM}ctx ${pct}%${_C_RESET}"
            fi
            ;;
        weekly-limit)
            pct="$(_number_in seven_day used_percentage)"
            [[ -n "${pct}" ]] || return 1
            pct="${pct%%.*}"
            value="${_C_DIM}7d ${pct}%${_C_RESET}"
            ;;
        fast-mode)
            fast="$(_bool_field fast_mode)"
            [[ "${fast}" == "true" ]] || return 1
            value="${_C_MAGENTA}fast${_C_RESET}"
            ;;
        estimated-thread-cost)
            cost="$(_number total_cost_usd)"
            [[ -n "${cost}" ]] || return 1
            value="${_C_DIM}\$$(printf '%.4f' "${cost}" 2>/dev/null || printf '%s' "${cost}")${_C_RESET}"
            ;;
        thread-id)
            sid="$(_field session_id)"
            [[ -n "${sid}" ]] || return 1
            value="${_C_DIM}${sid:0:8}${_C_RESET}"
            ;;
        *)
            # cl 无对应数据源的段（如 task-progress）静默跳过
            return 1
            ;;
    esac
    printf '%s' "${value}"
}

output=""
IFS=',' read -r -a _seg_list <<< "${segments}" 2>/dev/null || _seg_list=()
for seg in "${_seg_list[@]}"; do
    seg="${seg//[[:space:]]/}"
    [[ -n "${seg}" ]] || continue
    part="$(_render "${seg}")" || continue
    [[ -n "${part}" ]] || continue
    if [[ -n "${output}" ]]; then
        output+=" ${_C_DIM}|${_C_RESET} "
    fi
    output+="${part}"
done
printf '%s\n' "${output}"
