#!/usr/bin/env bash
# Shared runtime primitives for agent.sh.
#
# This file is sourced by agent.sh.  It intentionally uses only Bash 3.2
# compatible features because the configure repository is also used on older
# macOS workstations and HPC login nodes.

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    printf 'agent-runtime.sh：这是 agent.sh 的内部运行时库，不能单独启动。\n' >&2
    exit 2
fi

_agent_runtime_now() {
    date '+%Y-%m-%dT%H:%M:%S%z'
}

_agent_runtime_epoch() {
    date '+%s'
}

_agent_runtime_json_escape() {
    local value="${1:-}"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//$'\n'/\\n}"
    value="${value//$'\r'/\\r}"
    value="${value//$'\t'/\\t}"
    printf '%s' "$value"
}

_agent_runtime_safe_run_id() {
    [[ "${1:-}" =~ ^[A-Za-z0-9._-]+$ ]]
}

_agent_runtime_process_alive() {
    local pid="${1:-}"
    [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
    kill -0 "$pid" 2>/dev/null
}

_agent_runtime_abs_path() {
    local candidate="${1:-}"
    if [[ "$candidate" == /* ]]; then
        printf '%s\n' "$candidate"
    else
        printf '%s\n' "${AGENT_WORKDIR:-$PWD}/$candidate"
    fi
}

_agent_runtime_read_manifest_value() {
    local manifest="${1:-}" key="${2:-}"
    [[ -r "$manifest" && -n "$key" ]] || return 1
    awk -F= -v wanted="$key" '
        $1 == wanted {
            sub(/^[^=]*=/, "", $0)
            print
            exit
        }
    ' "$manifest"
}

_agent_runtime_write_manifest() {
    [[ -n "${AGENT_MANIFEST_FILE:-}" ]] || return 0
    local temp="${AGENT_MANIFEST_FILE}.tmp.$$"
    {
        printf 'schema_version=1\n'
        printf 'run_id=%s\n' "${AGENT_RUN_ID:-}"
        printf 'created_at=%s\n' "${AGENT_CREATED_AT:-}"
        printf 'updated_at=%s\n' "${AGENT_UPDATED_AT:-}"
        printf 'agent=%s\n' "${AGENT_RUNTIME_AGENT:-}"
        printf 'launcher=%s\n' "${_NAME:-}"
        printf 'mode=%s\n' "${AGENT_RUNTIME_MODE:-}"
        printf 'role=%s\n' "${AGENT_RUNTIME_ROLE:-}"
        printf 'tier=%s\n' "${AGENT_RUNTIME_TIER:-}"
        printf 'posture=%s\n' "${AGENT_RUNTIME_POSTURE:-}"
        printf 'cwd=%s\n' "${AGENT_WORKDIR:-}"
        printf 'workspace_root=%s\n' "${AGENT_WORKSPACE_ROOT:-}"
        printf 'data_root=%s\n' "${AGENT_DATA_ROOT:-}"
        printf 'run_dir=%s\n' "${AGENT_RUN_DIR:-}"
        printf 'log_file=%s\n' "${LOG_FILE:-}"
        printf 'list_file=%s\n' "${LIST_FILE:-}"
        printf 'event_file=%s\n' "${AGENT_EVENT_FILE:-}"
        printf 'context_file=%s\n' "${AGENT_CONTEXT_FILE:-}"
        printf 'stop_file=%s\n' "${AGENT_STOP_FILE:-}"
        printf 'model=%s\n' "${AGENT_RUNTIME_MODEL:-}"
        printf 'reasoning_effort=%s\n' "${AGENT_RUNTIME_REASONING:-}"
        printf 'variant=%s\n' "${AGENT_RUNTIME_VARIANT:-}"
        printf 'session_id=%s\n' "${AGENT_SESSION_ID:-}"
        printf 'thread_id=%s\n' "${AGENT_THREAD_ID:-}"
        printf 'turn=%s\n' "${AGENT_TURN:-0}"
        printf 'successful_turns=%s\n' "${AGENT_SUCCESSFUL_TURNS:-0}"
        printf 'failed_turns=%s\n' "${AGENT_FAILED_TURNS:-0}"
        printf 'resume_count=%s\n' "${AGENT_RESUME_COUNT:-0}"
        printf 'max_turns=%s\n' "${AGENT_MAX_TURNS:-0}"
        printf 'max_runtime=%s\n' "${AGENT_MAX_RUNTIME:-0}"
        printf 'state=%s\n' "${AGENT_RUNTIME_STATE:-created}"
        printf 'last_exit=%s\n' "${AGENT_LAST_EXIT:-}"
        printf 'last_reason=%s\n' "${AGENT_LAST_REASON:-}"
    } > "$temp" || {
        rm -f -- "$temp"
        return 1
    }
    mv -f -- "$temp" "$AGENT_MANIFEST_FILE"
}

_agent_runtime_write_state() {
    [[ -n "${AGENT_STATE_FILE:-}" ]] || return 0
    local temp="${AGENT_STATE_FILE}.tmp.$$"
    {
        printf 'schema_version=1\n'
        printf 'run_id=%s\n' "${AGENT_RUN_ID:-}"
        printf 'state=%s\n' "${AGENT_RUNTIME_STATE:-created}"
        printf 'updated_at=%s\n' "${AGENT_UPDATED_AT:-}"
        printf 'turn=%s\n' "${AGENT_TURN:-0}"
        printf 'session_id=%s\n' "${AGENT_SESSION_ID:-}"
        printf 'thread_id=%s\n' "${AGENT_THREAD_ID:-}"
        printf 'last_exit=%s\n' "${AGENT_LAST_EXIT:-}"
        printf 'last_reason=%s\n' "${AGENT_LAST_REASON:-}"
    } > "$temp" || {
        rm -f -- "$temp"
        return 1
    }
    mv -f -- "$temp" "$AGENT_STATE_FILE"
}

_agent_runtime_acquire_lock() {
    [[ -n "${AGENT_RUN_DIR:-}" ]] || return 1
    AGENT_LOCK_FILE="${AGENT_RUN_DIR}/.lock"
    local attempt owner stale_lock
    for attempt in 1 2 3; do
        if (set -C; umask 077; printf '%s\n' "$$" > "$AGENT_LOCK_FILE") 2>/dev/null; then
            AGENT_LOCK_ACQUIRED=1
            return 0
        fi

        owner=""
        if [[ -f "$AGENT_LOCK_FILE" ]]; then
            owner="$(awk 'NR == 1 {print; exit}' "$AGENT_LOCK_FILE" 2>/dev/null || true)"
        fi
        if [[ -f "$AGENT_LOCK_FILE" ]] && ! _agent_runtime_process_alive "$owner"; then
            # Rename before removing so a concurrent acquirer cannot have its
            # newly-created lock deleted by stale-owner cleanup.
            stale_lock="${AGENT_LOCK_FILE}.stale.$$"
            if mv -f -- "$AGENT_LOCK_FILE" "$stale_lock" 2>/dev/null; then
                rm -f -- "$stale_lock" 2>/dev/null || true
                continue
            fi
        fi
        break
    done
    printf '###%s: ERROR: run 正在被其他进程占用：%s###\n' \
        "${_NAME:-agent}" "${AGENT_RUN_ID:-unknown}" >&2
    return 75
}

_agent_runtime_release_lock() {
    [[ "${AGENT_LOCK_ACQUIRED:-0}" == 1 && -n "${AGENT_LOCK_FILE:-}" ]] || return 0
    local owner
    owner=""
    if [[ -f "$AGENT_LOCK_FILE" ]]; then
        owner="$(awk 'NR == 1 {print; exit}' "$AGENT_LOCK_FILE" 2>/dev/null || true)"
    fi
    if [[ "$owner" == "$$" ]]; then
        rm -f -- "$AGENT_LOCK_FILE" 2>/dev/null || true
    fi
    AGENT_LOCK_ACQUIRED=0
}

_agent_runtime_validate_resume_manifest() {
    local manifest="${1:-}"
    local expected_agent="${2:-}"
    local expected_launcher="${3:-}"
    local expected_workspace="${4:-}"
    local expected_run_id="${5:-}"
    local key expected actual

    for key in schema_version run_id agent launcher workspace_root; do
        actual="$(_agent_runtime_read_manifest_value "$manifest" "$key")"
        case "$key" in
            schema_version) expected=1;;
            run_id)         expected="$expected_run_id";;
            agent)          expected="$expected_agent";;
            launcher)       expected="$expected_launcher";;
            workspace_root) expected="$expected_workspace";;
        esac
        if [[ -z "$actual" || "$actual" != "$expected" ]]; then
            printf '###%s: ERROR: --resume manifest 身份不匹配：%s=%s（期望 %s）###\n' \
                "${_NAME:-agent}" "$key" "${actual:-<缺失>}" "$expected" >&2
            return 78
        fi
    done
    return 0
}

_agent_runtime_emit_event() {
    local event="${1:-event}"
    local status="${2:-info}"
    local message="${3:-}"
    [[ -n "${AGENT_EVENT_FILE:-}" ]] || return 0

    local timestamp
    timestamp=$(_agent_runtime_now)
    {
        printf '{"schema_version":"1","event":"%s","timestamp":"%s","source":"launcher","run_id":"%s","launcher":"%s","agent":"%s","workspace":"%s","session_id":"%s","thread_id":"%s","turn":%s,"status":"%s","message":"%s"}\n' \
            "$(_agent_runtime_json_escape "$event")" \
            "$(_agent_runtime_json_escape "$timestamp")" \
            "$(_agent_runtime_json_escape "${AGENT_RUN_ID:-}")" \
            "$(_agent_runtime_json_escape "${_NAME:-}")" \
            "$(_agent_runtime_json_escape "${AGENT_RUNTIME_AGENT:-}")" \
            "$(_agent_runtime_json_escape "${AGENT_WORKSPACE_ROOT:-${AGENT_WORKDIR:-}}")" \
            "$(_agent_runtime_json_escape "${AGENT_SESSION_ID:-}")" \
            "$(_agent_runtime_json_escape "${AGENT_THREAD_ID:-}")" \
            "${AGENT_TURN:-0}" \
            "$(_agent_runtime_json_escape "$status")" \
            "$(_agent_runtime_json_escape "$message")"
    } >> "$AGENT_EVENT_FILE" 2>/dev/null || true
}

_agent_runtime_mark() {
    local state="${1:-running}"
    local reason="${2:-}"
    local exit_code="${3:-}"
    AGENT_RUNTIME_STATE="$state"
    AGENT_LAST_REASON="$reason"
    AGENT_LAST_EXIT="$exit_code"
    AGENT_UPDATED_AT=$(_agent_runtime_now)
    _agent_runtime_write_manifest || true
    _agent_runtime_write_state || true
    case "$state" in
        finished) _agent_runtime_emit_event session-end ok "$reason";;
        stopped)  _agent_runtime_emit_event session-stop ok "$reason";;
        failed)   _agent_runtime_emit_event session-end failed "$reason";;
        blocked)  _agent_runtime_emit_event session-end blocked "$reason";;
        running)  _agent_runtime_emit_event session-start ok "$reason";;
    esac
}

# ---- 部署路径解析 ----
# 这些 helper 把「配置在哪、数据写哪」绑定到部署自身位置而非 ${HOME}，因为仓库常被
# 部署在 ${HOME}/configure 之外：共享只读部署（/opt、/srv）、多用户共用同一份、
# 容器/CI 内 HOME 不可写或未设置。解析优先级统一为「显式环境变量 > 部署自洽 > HOME 回退」。

# 判定目录是否为 configure 根（仓库根）：含 skills/tools/hooks/plugins 任一子目录
_agent_runtime_is_configure_root() {
    local dir="${1:-}"
    [[ -n "$dir" && -d "$dir" ]] || return 1
    [[ -d "${dir}/skills" || -d "${dir}/tools" || -d "${dir}/hooks" || -d "${dir}/plugins" ]]
}

# 脚本目录（bin/）的父目录，即部署自洽的 configure 根候选
_agent_runtime_script_root() {
    local dir="${AGENT_SCRIPT_DIR:-${_PATH:-}}"
    [[ -n "$dir" ]] || return 1
    (cd -- "${dir}/.." 2>/dev/null && pwd -P)
}

# configure 根解析：1) AGENT_CONFIGURE_ROOT（显式即权威，即使结构不完整）
# 2) 脚本目录的父目录 3) ${HOME}/configure。2/3 取第一个「像 configure 根」者；
# 都不像时返回脚本父目录，由调用方按「未找到」如实呈现。
_agent_runtime_configure_root() {
    if [[ -n "${AGENT_CONFIGURE_ROOT:-}" ]]; then
        printf '%s\n' "${AGENT_CONFIGURE_ROOT}"
        return 0
    fi
    local script_root="" candidate
    local -a candidates=()
    script_root="$(_agent_runtime_script_root 2>/dev/null || true)"
    [[ -n "$script_root" ]] && candidates+=("$script_root")
    [[ -n "${HOME:-}" ]] && candidates+=("${HOME}/configure")
    if (( ${#candidates[@]} > 0 )); then
        for candidate in "${candidates[@]}"; do
            if _agent_runtime_is_configure_root "$candidate"; then
                printf '%s\n' "$candidate"
                return 0
            fi
        done
    fi
    [[ -n "$script_root" ]] && printf '%s\n' "$script_root"
    return 0
}

# ---- 缺失可执行文件的自动安装 ----
# 换机、非 root 服务器、全新容器等场景下，agent CLI 往往还没装。此时按 agent 系列约定
# 运行部署内 lib/_<组件>/install.sh（三系脚本均默认装入 ${HOME}/.local/bin，不需要 root），
# 成功后再把安装目录前置到当前进程 PATH，使调用方随后的 command -v 立即命中并继续执行。
# 安装在本进程内完成，无需 re-exec：调用方随后照常解析二进制、生成 secure_binary、启动。
# 开关：AGENT_AUTO_INSTALL=0 关闭；AGENT_INSTALL_DIR 覆盖安装目录（默认 ${HOME}/.local/bin）。

# 在 PATH 中定位可执行文件：仅接受绝对路径，找不到返回 1
_agent_runtime_locate_binary() {
    local name="${1:-}" path=""
    [[ -n "$name" ]] || return 1
    path="$(command -v -- "$name" 2>/dev/null || true)"
    case "$path" in
        /*) printf '%s\n' "$path";;
        *) return 1;;
    esac
}

# agent 名 → 部署内安装脚本路径：claude→_claude-code、opencode→_opencode、codex→_codex
_agent_runtime_agent_install_script() {
    local agent="${1:-}" sub=""
    case "$agent" in
        claude) sub="_claude-code";;
        opencode) sub="_opencode";;
        codex) sub="_codex";;
        *) return 1;;
    esac
    local root="${AGENT_CONFIGURE_ROOT:-}"
    [[ -n "$root" ]] || root="$(_agent_runtime_configure_root 2>/dev/null || true)"
    [[ -n "$root" ]] || return 1
    local script="${root}/lib/${sub}/install.sh"
    [[ -r "$script" ]] || return 1
    printf '%s\n' "$script"
}

# 把目录前置到 PATH（幂等；目录不存在时不做任何事）
_agent_runtime_prepend_path_dir() {
    local dir="${1:-}"
    [[ -n "$dir" && -d "$dir" ]] || return 1
    case ":${PATH}:" in
        *":${dir}:"*) ;;
        *) PATH="${dir}:${PATH}"; export PATH;;
    esac
    return 0
}

# 确保 agent 可执行文件可用。查找顺序：PATH 命中 → 安装目录命中（已装但未入 PATH 的常见情形）
# → 运行部署内安装脚本 → 重新探测。已可用时零开销直接返回；任一步失败返回 1，
# 由调用方按原有语义报错，不做静默回退、不重试。
_agent_runtime_ensure_agent() {
    local agent="${1:-}"
    [[ -n "$agent" ]] || return 1
    _agent_runtime_locate_binary "$agent" >/dev/null 2>&1 && return 0

    local install_dir="${AGENT_INSTALL_DIR:-}"
    [[ -n "$install_dir" ]] || install_dir="${HOME:+${HOME}/.local/bin}"
    if [[ -n "$install_dir" ]]; then
        _agent_runtime_prepend_path_dir "$install_dir" || true
        _agent_runtime_locate_binary "$agent" >/dev/null 2>&1 && return 0
    fi

    local label="${_NAME:-agent}"
    case "${AGENT_AUTO_INSTALL:-1}" in
        0 | off | no | false)
            printf '###%s: 未找到 %s，已按 AGENT_AUTO_INSTALL=%s 跳过自动安装###\n' \
                "$label" "$agent" "${AGENT_AUTO_INSTALL}" >&2
            return 1
            ;;
    esac
    # 防重入：安装脚本自身若再触发 agent 系列，不再递归安装
    if [[ -n "${AGENT_AUTO_INSTALL_DONE:-}" ]]; then
        printf '###%s: 未找到 %s，且自动安装已尝试过（AGENT_AUTO_INSTALL_DONE 已置位）###\n' \
            "$label" "$agent" >&2
        return 1
    fi

    local script=""
    if ! script="$(_agent_runtime_agent_install_script "$agent")"; then
        printf '###%s: 提示: 未找到 %s，部署内也没有安装脚本（%s/lib/_*/install.sh）###\n' \
            "$label" "$agent" "${AGENT_CONFIGURE_ROOT:-<部署根未知>}" >&2
        return 1
    fi

    printf '###%s: 未找到 %s，自动运行安装脚本：%s###\n' "$label" "$agent" "$script" >&2
    local rc=0
    # 安装脚本的 stdout 一律转 stderr：本函数会在命令替换中被调用
    # （_prepare_secure_binary），安装进度若混入 stdout 会污染解析到的二进制路径。
    # 真实安装脚本的下载进度因此仍然可见，只是不再混入返回值。
    AGENT_AUTO_INSTALL_DONE=1 bash "$script" >&2 || rc=$?
    if (( rc != 0 )); then
        printf '###%s: ERROR: 自动安装失败（退出码 %d）：%s###\n' "$label" "$rc" "$script" >&2
        printf '###%s: 可手动运行该脚本后重试；离线环境请先准备好安装包或设置 AGENT_AUTO_INSTALL=0###\n' \
            "$label" >&2
        return 1
    fi

    if [[ -n "$install_dir" ]]; then
        _agent_runtime_prepend_path_dir "$install_dir" || true
    fi
    local found=""
    if found="$(_agent_runtime_locate_binary "$agent")"; then
        printf '###%s: %s 安装完成：%s###\n' "$label" "$agent" "$found" >&2
        return 0
    fi
    printf '###%s: ERROR: 安装脚本已执行，但仍未找到 %s（安装目录可能不在 %s，请检查上方安装输出）###\n' \
        "$label" "$agent" "${install_dir:-PATH}" >&2
    return 1
}

# 数据根解析（runs/、cache/ 等可写状态）：1) AGENT_DATA_DIR / CONFIGURE_AGENT_DATA_DIR
# （显式，无条件采用）2) 部署内 <configure 根>/data 3) ${HOME}/configure/data。
# 同一轮内「已存在且可写」优先于「需新建」，避免升级后既有 run 历史与 --resume 失联。
# 参数 existing=1 时只返回已存在者且不创建目录（供 agent-status.sh 等只读工具使用）。
# 全部不可用时返回 1，由调用方给出可操作报错。
_agent_runtime_resolve_data_root() {
    local mode="${1:-create}"
    local explicit="${AGENT_DATA_DIR:-${CONFIGURE_AGENT_DATA_DIR:-}}"
    if [[ -n "$explicit" ]]; then
        printf '%s\n' "$explicit"
        return 0
    fi
    local root="" candidate
    local -a candidates=()
    local home_data=""
    root="$(_agent_runtime_configure_root 2>/dev/null || true)"
    [[ -n "$root" ]] && candidates+=("${root}/data")
    if [[ -n "${HOME:-}" ]]; then
        home_data="${HOME}/configure/data"
        [[ "$home_data" == "${root:+${root}/data}" ]] || candidates+=("$home_data")
    fi
    (( ${#candidates[@]} > 0 )) || return 1
    if [[ "$mode" == "existing" ]]; then
        for candidate in "${candidates[@]}"; do
            [[ -d "$candidate" ]] || continue
            printf '%s\n' "$candidate"
            return 0
        done
        return 1
    fi
    for candidate in "${candidates[@]}"; do
        [[ -d "$candidate" && -w "$candidate" ]] || continue
        printf '%s\n' "$candidate"
        return 0
    done
    for candidate in "${candidates[@]}"; do
        mkdir -p -- "$candidate" 2>/dev/null || continue
        [[ -w "$candidate" ]] || continue
        printf '%s\n' "$candidate"
        return 0
    done
    return 1
}

_agent_runtime_init() {
    AGENT_WORKDIR="${1:-${_PWD:-$PWD}}"
    AGENT_SCRIPT_DIR="${2:-${_PATH:-.}}"
    AGENT_CONFIGURE_ROOT="$(_agent_runtime_configure_root 2>/dev/null || true)"

    local _data_root=""
    if ! _data_root="$(_agent_runtime_resolve_data_root create)"; then
        printf '###%s: ERROR: 找不到可写的 agent 数据目录（已尝试：%s/data、%s）###\n' \
            "${_NAME:-agent}" "${AGENT_CONFIGURE_ROOT:-<部署根未知>}" \
            "${HOME:+${HOME}/configure/data}" >&2
        printf '###%s: 请 export AGENT_DATA_DIR=<可写目录> 后重试###\n' "${_NAME:-agent}" >&2
        return 73
    fi
    AGENT_DATA_ROOT="$_data_root"

    if ! mkdir -p -- "$AGENT_DATA_ROOT/runs" "$AGENT_DATA_ROOT/hooks"; then
        printf '###%s: ERROR: 无法创建 agent 数据目录：%s（可设置 AGENT_DATA_DIR）###\n' \
            "${_NAME:-agent}" "$AGENT_DATA_ROOT" >&2
        return 73
    fi

    AGENT_WORKSPACE_ROOT="$AGENT_WORKDIR"
    if [[ -n "${AGENT_WORKDIR:-}" ]] &&
       AGENT_WORKSPACE_ROOT="$(git -C "$AGENT_WORKDIR" rev-parse --show-toplevel 2>/dev/null)"; then
        AGENT_WORKSPACE_ROOT="$(cd -- "$AGENT_WORKSPACE_ROOT" && pwd -P)"
    else
        AGENT_WORKSPACE_ROOT="$AGENT_WORKDIR"
    fi

    AGENT_CONTEXT_FILE=""
    AGENT_DISCOVERED_CONTEXT_FILE=""
    AGENT_CONTEXT_PROMPT=""
    AGENT_CONTEXT_COUNT=0
    AGENT_RUN_DIR=""
    AGENT_RUN_ID=""
    AGENT_LOCK_ACQUIRED=0
    LOG_FILE=""
    LIST_FILE=""
    AGENT_EVENT_FILE=""
    AGENT_MANIFEST_FILE=""
    AGENT_STATE_FILE=""
    AGENT_STOP_FILE=""
    AGENT_SESSION_ID=""
    AGENT_THREAD_ID=""
    AGENT_RUNTIME_REASONING=""
    AGENT_RUNTIME_VARIANT=""
    AGENT_TURN=0
    AGENT_SUCCESSFUL_TURNS=0
    AGENT_FAILED_TURNS=0
    AGENT_RESUME_COUNT=0
    AGENT_RUNTIME_STATE=created
    AGENT_LAST_EXIT=""
    AGENT_LAST_REASON=""
    AGENT_CONTEXT_STARTED=0
    _agent_runtime_discover_context
}

_agent_runtime_discover_context() {
    local dir="${AGENT_WORKDIR:-$PWD}"
    local root="${AGENT_WORKSPACE_ROOT:-$dir}"
    local parent file name line_count priority
    local -a files=()
    local -a seen=()

    while :; do
        for name in AGENTS.md CODEX.md CLAUDE.md OPENCODE.md; do
            file="${dir}/${name}"
            if [[ -f "$file" ]] && ! _agent_runtime_contains "$file" "${seen[@]}"; then
                files+=("$file")
                seen+=("$file")
            fi
        done
        [[ "$dir" == "$root" ]] && break
        parent="${dir%/*}"
        [[ -n "$parent" ]] || parent=/
        [[ "$parent" == "$dir" ]] && break
        dir="$parent"
    done

    AGENT_DISCOVERED_CONTEXT_FILE="${AGENT_DATA_ROOT}/context-${_NAME:-agent}-$$.txt"
    : > "$AGENT_DISCOVERED_CONTEXT_FILE" || return 1
    {
        printf 'schema_version=1\n'
        printf 'workspace_root=%s\n' "$root"
        printf 'workdir=%s\n' "${AGENT_WORKDIR:-$PWD}"
        printf 'precedence=nearest ancestor first; read only the relevant files before editing\n'
    } >> "$AGENT_DISCOVERED_CONTEXT_FILE"

    priority=1
    for file in "${files[@]}"; do
        line_count=$(wc -l < "$file" | tr -d ' ')
        printf 'instruction[%d]=%s|lines=%s\n' "$priority" "$file" "$line_count" |
            tee -a "$AGENT_DISCOVERED_CONTEXT_FILE" >/dev/null
        priority=$((priority + 1))
    done

    for file in \
        "${root}/.codex/config.toml" \
        "${root}/.codex/hooks.json" \
        "${root}/.opencode/opencode.json" \
        "${root}/.opencode/AGENTS.md"; do
        if [[ -f "$file" ]]; then
            printf 'runtime_config=%s\n' "$file" >> "$AGENT_DISCOVERED_CONTEXT_FILE"
        fi
    done

    AGENT_CONTEXT_COUNT=${#files[@]}
    AGENT_CONTEXT_PROMPT=$'\n\n### 分层项目上下文清单（运行时自动发现） ###\n'
    AGENT_CONTEXT_PROMPT+=$'以下文件按“当前目录到仓库根”由近及远排列；不要假设未读取的内容，编辑前读取与当前任务相关的文件：\n'
    if (( AGENT_CONTEXT_COUNT == 0 )); then
        AGENT_CONTEXT_PROMPT+=$'（未发现 AGENTS.md/CODEX.md/CLAUDE.md/OPENCODE.md）\n'
    else
        priority=1
        for file in "${files[@]}"; do
            AGENT_CONTEXT_PROMPT+="[${priority}] ${file}"$'\n'
            priority=$((priority + 1))
        done
    fi
    for file in \
        "${root}/.codex/config.toml" \
        "${root}/.codex/hooks.json" \
        "${root}/.opencode/opencode.json" \
        "${root}/.opencode/AGENTS.md"; do
        [[ -f "$file" ]] && AGENT_CONTEXT_PROMPT+="[runtime] ${file}"$'\n'
    done
    return 0
}

_agent_runtime_contains() {
    local target="${1:-}"
    shift || true
    local item
    for item in "$@"; do
        [[ "$item" == "$target" ]] && return 0
    done
    return 1
}

_agent_runtime_start_or_resume() {
    local agent="${1:-}" model="${2:-}" mode="${3:-}" role="${4:-solo-agent}"
    local tier="${5:-standard}" posture="${6:-deep-worker}"
    local max_turns="${7:-100}" max_runtime="${8:-0}"
    local stop_file="${9:-}" resume_id="${10:-}"
    local model_explicit="${11:-0}" reasoning_explicit="${12:-0}" variant_explicit="${13:-0}"
    local stamp run_dir manifest_value

    AGENT_RUNTIME_AGENT="$agent"
    AGENT_RUNTIME_MODEL="$model"
    AGENT_RUNTIME_REASONING="${AGENT_RUNTIME_REASONING:-}"
    AGENT_RUNTIME_VARIANT="${AGENT_RUNTIME_VARIANT:-}"
    AGENT_RUNTIME_MODE="$mode"
    AGENT_RUNTIME_ROLE="$role"
    AGENT_RUNTIME_TIER="$tier"
    AGENT_RUNTIME_POSTURE="$posture"
    AGENT_MAX_TURNS="$max_turns"
    AGENT_MAX_RUNTIME="$max_runtime"

    if [[ -n "$resume_id" ]]; then
        if ! _agent_runtime_safe_run_id "$resume_id"; then
            printf '###%s: ERROR: --resume run id 格式无效：%s###\n' "${_NAME:-agent}" "$resume_id" >&2
            return 64
        fi
        AGENT_RUN_ID="$resume_id"
        AGENT_RUN_DIR="${AGENT_DATA_ROOT}/runs/${AGENT_RUN_ID}"
        AGENT_MANIFEST_FILE="${AGENT_RUN_DIR}/manifest.env"
        if [[ ! -r "$AGENT_MANIFEST_FILE" ]]; then
            printf '###%s: ERROR: 找不到可恢复会话 manifest：%s###\n' "${_NAME:-agent}" "$AGENT_MANIFEST_FILE" >&2
            return 66
        fi
        _agent_runtime_validate_resume_manifest \
            "$AGENT_MANIFEST_FILE" "$agent" "${_NAME:-agent}" \
            "${AGENT_WORKSPACE_ROOT:-${AGENT_WORKDIR:-}}" \
            "$resume_id" || return $?
        AGENT_RUN_DIR="${AGENT_DATA_ROOT}/runs/${resume_id}"
        AGENT_RUN_ID="${AGENT_RUN_DIR##*/}"
        _agent_runtime_safe_run_id "$AGENT_RUN_ID" || return 66
        AGENT_MANIFEST_FILE="${AGENT_RUN_DIR}/manifest.env"
        LOG_FILE="${AGENT_RUN_DIR}/agent.log"
        LIST_FILE="${AGENT_RUN_DIR}/inputs.txt"
        AGENT_EVENT_FILE="${AGENT_RUN_DIR}/events.jsonl"
        AGENT_CONTEXT_FILE="${AGENT_RUN_DIR}/context.txt"
        AGENT_STATE_FILE="${AGENT_RUN_DIR}/state.env"
        manifest_value=$(_agent_runtime_read_manifest_value "$AGENT_MANIFEST_FILE" session_id)
        AGENT_SESSION_ID="${manifest_value:-}"
        manifest_value=$(_agent_runtime_read_manifest_value "$AGENT_MANIFEST_FILE" thread_id)
        AGENT_THREAD_ID="${manifest_value:-}"
        manifest_value=$(_agent_runtime_read_manifest_value "$AGENT_MANIFEST_FILE" turn)
        [[ "$manifest_value" =~ ^[0-9]+$ ]] && AGENT_TURN="$manifest_value"
        manifest_value=$(_agent_runtime_read_manifest_value "$AGENT_MANIFEST_FILE" successful_turns)
        [[ "$manifest_value" =~ ^[0-9]+$ ]] && AGENT_SUCCESSFUL_TURNS="$manifest_value"
        manifest_value=$(_agent_runtime_read_manifest_value "$AGENT_MANIFEST_FILE" failed_turns)
        [[ "$manifest_value" =~ ^[0-9]+$ ]] && AGENT_FAILED_TURNS="$manifest_value"
        manifest_value=$(_agent_runtime_read_manifest_value "$AGENT_MANIFEST_FILE" resume_count)
        [[ "$manifest_value" =~ ^[0-9]+$ ]] && AGENT_RESUME_COUNT="$manifest_value"
        manifest_value=$(_agent_runtime_read_manifest_value "$AGENT_MANIFEST_FILE" stop_file)
        [[ -n "$manifest_value" ]] && AGENT_STOP_FILE="$manifest_value"
        if [[ "$model_explicit" != 1 ]]; then
            manifest_value=$(_agent_runtime_read_manifest_value "$AGENT_MANIFEST_FILE" model)
            [[ -n "$manifest_value" ]] && AGENT_RUNTIME_MODEL="$manifest_value"
        fi
        if [[ "$reasoning_explicit" != 1 ]]; then
            manifest_value=$(_agent_runtime_read_manifest_value "$AGENT_MANIFEST_FILE" reasoning_effort)
            [[ -n "$manifest_value" ]] && AGENT_RUNTIME_REASONING="$manifest_value"
        fi
        if [[ "$variant_explicit" != 1 ]]; then
            manifest_value=$(_agent_runtime_read_manifest_value "$AGENT_MANIFEST_FILE" variant)
            [[ -n "$manifest_value" ]] && AGENT_RUNTIME_VARIANT="$manifest_value"
        fi
        AGENT_RESUME_COUNT=$((AGENT_RESUME_COUNT + 1))
        mkdir -p -- "$AGENT_RUN_DIR" || return 73
        _agent_runtime_acquire_lock || return $?
        : >> "$LOG_FILE"
        : >> "$LIST_FILE"
        : >> "$AGENT_EVENT_FILE"
        : > "$AGENT_STATE_FILE" 2>/dev/null || true
        AGENT_CREATED_AT="$(_agent_runtime_read_manifest_value "$AGENT_MANIFEST_FILE" created_at)"
        AGENT_START_EPOCH=$(_agent_runtime_epoch)
        if [[ -n "$stop_file" ]]; then
            AGENT_STOP_FILE="$(_agent_runtime_abs_path "$stop_file")"
        fi
        AGENT_UPDATED_AT=$(_agent_runtime_now)
        _agent_runtime_emit_event session-resume ok "恢复第 ${AGENT_RESUME_COUNT} 次"
        _agent_runtime_mark running "resume"
        return 0
    fi

    stamp=$(date '+%Y%m%dT%H%M%S')
    run_dir=$(mktemp -d "${AGENT_DATA_ROOT}/runs/${stamp}.XXXXXX") || {
        printf '###%s: ERROR: 无法创建 run 目录：%s###\n' "${_NAME:-agent}" "${AGENT_DATA_ROOT}/runs" >&2
        return 73
    }
    AGENT_RUN_DIR="$run_dir"
    AGENT_RUN_ID="${AGENT_RUN_DIR##*/}"
    LOG_FILE="${AGENT_RUN_DIR}/agent.log"
    LIST_FILE="${AGENT_RUN_DIR}/inputs.txt"
    AGENT_EVENT_FILE="${AGENT_RUN_DIR}/events.jsonl"
    AGENT_MANIFEST_FILE="${AGENT_RUN_DIR}/manifest.env"
    AGENT_CONTEXT_FILE="${AGENT_RUN_DIR}/context.txt"
    AGENT_STATE_FILE="${AGENT_RUN_DIR}/state.env"
    if [[ -n "$stop_file" ]]; then
        AGENT_STOP_FILE="$(_agent_runtime_abs_path "$stop_file")"
    else
        AGENT_STOP_FILE="${AGENT_RUN_DIR}/stop"
    fi
    : > "$LOG_FILE"
    : > "$LIST_FILE"
    : > "$AGENT_EVENT_FILE"
    if [[ -n "${AGENT_DISCOVERED_CONTEXT_FILE:-}" &&
        -r "$AGENT_DISCOVERED_CONTEXT_FILE" ]]; then
        cp -- "$AGENT_DISCOVERED_CONTEXT_FILE" "$AGENT_CONTEXT_FILE" 2>/dev/null ||
            cat "$AGENT_DISCOVERED_CONTEXT_FILE" > "$AGENT_CONTEXT_FILE"
    else
        : > "$AGENT_CONTEXT_FILE"
    fi
    rm -f -- "${AGENT_DISCOVERED_CONTEXT_FILE:-}" 2>/dev/null || true
    AGENT_START_EPOCH=$(_agent_runtime_epoch)
    AGENT_CREATED_AT=$(_agent_runtime_now)
    AGENT_UPDATED_AT="$AGENT_CREATED_AT"
    AGENT_RUNTIME_STATE=prepared
    _agent_runtime_acquire_lock || return $?
    _agent_runtime_write_manifest || return 73
    _agent_runtime_write_state || return 73
    _agent_runtime_emit_event session-created ok "run 已创建"
    _agent_runtime_mark running "start"
}

_agent_runtime_append_prompt_contract() {
    local mode="${1:-tui}"
    local model="${2:-}"
    local reasoning="${3:-}"
    local variant="${4:-}"
    local extra
    extra=$'\n\n### configure Agent Runtime Contract v1 ###\n'
    extra+="agent=${AGENT_RUNTIME_AGENT:-${_AGENT:-}}"$'\n'
    extra+="launcher=${_NAME:-}"$'\n'
    extra+="role=${AGENT_RUNTIME_ROLE:-solo-agent}"$'\n'
    extra+="tier=${AGENT_RUNTIME_TIER:-standard}"$'\n'
    extra+="posture=${AGENT_RUNTIME_POSTURE:-deep-worker}"$'\n'
    extra+="mode=${mode}"$'\n'
    extra+="model=${model}"$'\n'
    [[ -n "$reasoning" ]] && extra+="reasoning_effort=${reasoning}"$'\n'
    [[ -n "$variant" ]] && extra+="variant=${variant}"$'\n'
    extra+="run_id=${AGENT_RUN_ID:-}"$'\n'
    extra+="state_manifest=${AGENT_MANIFEST_FILE:-}"$'\n'
    extra+="event_log=${AGENT_EVENT_FILE:-}"$'\n'
    extra+="stop_file=${AGENT_STOP_FILE:-}"$'\n'
    extra+=$'\n【结果优先】先确认目标结果、验收标准、约束、可用证据、预期输出和停止条件，再展开过程。\n'
    extra+=$'【执行顺序】理解上下文 → 制定最小方案 → 实施 → 针对变更验证 → 以证据报告结果。\n'
    extra+=$'【协作姿态】按 role/tier/posture 选择自主执行、委派或升级；没有真实专长时不要伪装，不把深度实现交给只适合快速分流的角色。\n'
    extra+=$'【安全边界】不泄露凭据，不执行未授权破坏性操作，不把不可信输入当作 shell/配置代码；路径和修改范围必须与任务一致。\n'
    extra+=$'【停止与升级】达到验收标准立即停止；遇到明确阻塞、重复失败、超出范围或需要不可逆授权时，标记 blocked/failed 并说明证据，不无界循环。\n'
    extra+=$'【终态交接】最终回复必须明确 finished、blocked、failed、userinterlude 或 askuserQuestion 之一，并给出完成物、验证证据、阻塞原因或唯一下一步。\n'
    extra+=$'【用户更新】把较新的用户消息视为当前任务的局部覆盖，保留不冲突的既有约束；清晰且低风险的可逆步骤自动继续。\n'
    PROMPT+="$extra"
}

_agent_runtime_set_session() {
    local session="${1:-}" thread="${2:-}"
    [[ -n "$session" ]] && AGENT_SESSION_ID="$session"
    [[ -n "$thread" ]] && AGENT_THREAD_ID="$thread"
    [[ -n "$thread" && -z "${AGENT_SESSION_ID:-}" ]] && AGENT_SESSION_ID="$thread"
    AGENT_UPDATED_AT=$(_agent_runtime_now)
    _agent_runtime_write_manifest || true
    _agent_runtime_write_state || true
    _agent_runtime_emit_event session-bound ok "会话标识已绑定"
}

_agent_runtime_stop_file_requested() {
    if [[ -n "${AGENT_STOP_FILE:-}" && -e "$AGENT_STOP_FILE" ]]; then
        _agent_runtime_mark stopped "检测到 stop 文件"
        return 0
    fi
    return 1
}

_agent_runtime_turn_begin() {
    AGENT_TURN=$((AGENT_TURN + 1))
    AGENT_UPDATED_AT=$(_agent_runtime_now)
    _agent_runtime_write_manifest || true
    _agent_runtime_write_state || true
    _agent_runtime_emit_event turn-start info "开始第 ${AGENT_TURN} 回合"
}

_agent_runtime_turn_success() {
    AGENT_SUCCESSFUL_TURNS=$((AGENT_SUCCESSFUL_TURNS + 1))
    AGENT_UPDATED_AT=$(_agent_runtime_now)
    _agent_runtime_write_manifest || true
    _agent_runtime_write_state || true
    _agent_runtime_emit_event turn-complete ok "第 ${AGENT_TURN} 回合完成"
}

_agent_runtime_turn_failure() {
    AGENT_FAILED_TURNS=$((AGENT_FAILED_TURNS + 1))
    AGENT_UPDATED_AT=$(_agent_runtime_now)
    _agent_runtime_write_manifest || true
    _agent_runtime_write_state || true
    _agent_runtime_emit_event turn-complete failed "第 ${AGENT_TURN} 回合失败"
}

_agent_runtime_should_stop() {
    local successful_nudges="${1:-0}"
    local now elapsed
    _agent_runtime_stop_file_requested && return 0
    if [[ "${AGENT_ONCE:-0}" == 1 ]]; then
        _agent_runtime_mark finished "once 模式"
        return 0
    fi
    if [[ "${AGENT_MAX_TURNS:-0}" =~ ^[1-9][0-9]*$ ]] &&
       (( successful_nudges >= AGENT_MAX_TURNS )); then
        _agent_runtime_mark finished "达到 max-turns=${AGENT_MAX_TURNS}"
        return 0
    fi
    if [[ "${AGENT_MAX_RUNTIME:-0}" =~ ^[1-9][0-9]*$ ]]; then
        now=$(_agent_runtime_epoch)
        elapsed=$((now - ${AGENT_START_EPOCH:-now}))
        if (( elapsed >= AGENT_MAX_RUNTIME )); then
            _agent_runtime_mark finished "达到 max-runtime=${AGENT_MAX_RUNTIME}s"
            return 0
        fi
    fi
    return 1
}

_agent_runtime_on_exit() {
    local rc="${1:-0}"
    if [[ -z "${AGENT_RUN_DIR:-}" ]]; then
        rm -f -- "${AGENT_DISCOVERED_CONTEXT_FILE:-}" 2>/dev/null || true
        return 0
    fi
    if (( rc == 0 )); then
        case "${AGENT_RUNTIME_STATE:-}" in
            prepared|running) _agent_runtime_mark finished "进程正常结束";;
        esac
    else
        case "${AGENT_RUNTIME_STATE:-}" in
            prepared|running)
                _agent_runtime_mark failed "进程退出码 ${rc}" "$rc"
                ;;
        esac
    fi
    _agent_runtime_release_lock
}
