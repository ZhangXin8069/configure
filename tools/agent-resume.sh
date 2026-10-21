#!/usr/bin/env bash
# Resume one agent run after an unexpected process interruption.

set -Eeuo pipefail

tool_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd)
tool_name=$(basename -- "${BASH_SOURCE[0]:-$0}")
config_root=${AGENT_CONFIGURE_ROOT:-$(CDPATH= cd -- "${tool_dir}/.." && pwd)}

mode=resume
run_id=${AGENT_RUN_ID:-}
data_root_arg=""
delay=${AGENT_RESUME_DELAY:-10}
timeout_seconds=${AGENT_RESUME_TIMEOUT:-1800}
heartbeat_seconds=${AGENT_RESUME_HEARTBEAT:-60}
max_attempts=${AGENT_RESUME_MAX_ATTEMPTS:-0}
provider=${AGENT_RESUME_PROVIDER:-${AGENT_PARENT_PROVIDER:-}}
launcher_override=${AGENT_RESUME_LAUNCHER:-}
active_launcher_pid=""
active_launcher_group=0

usage() {
    cat <<'USAGE'
用法：agent-resume.sh [选项]

检测意外中断的 agent run，默认等待 10 秒后用原统一 launcher 执行
`--resume RUN_ID --once`。失败后会继续等待并重试，直到恢复成功、收到 stop 标记、
run 正常结束或达到可选的 AGENT_RESUME_MAX_ATTEMPTS 上限。

选项：
  --run-id RUN_ID       指定 run；缺省依次读取 AGENT_RUN_ID 或最新可恢复 run
  --data-root DIR       覆盖 AGENT_DATA_DIR / configure 数据根
  --delay SECONDS       恢复前等待秒数，默认 10
  --timeout SECONDS     单次恢复的硬超时，默认 1800
  --max-attempts N      最多恢复次数；0 表示无限，默认读取 AGENT_RESUME_MAX_ATTEMPTS=0
  --heartbeat SECONDS   单次恢复运行期间的心跳间隔，默认 60
  --provider NAME       恢复时使用的供应商；默认继承 AGENT_PARENT_PROVIDER
  --launcher PATH       覆盖 manifest 对应的统一 launcher（主要供包装器/测试）
  --check               只检查是否可恢复，不等待、不写文件
  --dry-run             输出将要执行的恢复计划，不等待、不写文件
  --force               兼容旧参数；当前恢复本身已支持无限重试
  -h, --help            显示帮助

退出码：0 恢复成功；1 达到可选重试上限后仍失败；2 参数错误；3 不可恢复；
4 正在运行、已停止、已正常结束或已有恢复调度；5 manifest/会话标识无效；6 找不到 run；
7 launcher 不可用；73 工作目录或写权限不可用；124 恢复超时。
USAGE
}

while (( $# > 0 )); do
    case "$1" in
        --run-id)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            run_id=$2; shift 2;;
        --data-root)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            data_root_arg=$2; shift 2;;
        --delay)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            delay=$2; shift 2;;
        --timeout)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            timeout_seconds=$2; shift 2;;
        --max-attempts)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            max_attempts=$2; shift 2;;
        --heartbeat)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            heartbeat_seconds=$2; shift 2;;
        --provider)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            provider=$2; shift 2;;
        --launcher)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            launcher_override=$2; shift 2;;
        --check|--dry-run)
            mode=check; shift;;
        --force)
            shift;;
        -h|--help)
            usage; exit 0;;
        *)
            printf '%s：未知参数：%s\n' "$tool_name" "$1" >&2
            usage >&2
            exit 2;;
    esac
done

[[ "$delay" =~ ^[0-9]+$ ]] || {
    printf '%s：--delay 必须是非负整数：%s\n' "$tool_name" "$delay" >&2
    exit 2
}
[[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]] || {
    printf '%s：--timeout 必须是正整数：%s\n' "$tool_name" "$timeout_seconds" >&2
    exit 2
}
[[ "$heartbeat_seconds" =~ ^[1-9][0-9]*$ ]] || {
    printf '%s：--heartbeat 必须是正整数：%s\n' "$tool_name" "$heartbeat_seconds" >&2
    exit 2
}
[[ "$max_attempts" =~ ^[0-9]+$ ]] || {
    printf '%s：--max-attempts 必须是非负整数：%s\n' "$tool_name" "$max_attempts" >&2
    exit 2
}
if [[ -n "$run_id" && ! "$run_id" =~ ^[A-Za-z0-9._-]+$ ]]; then
    printf '%s：RUN_ID 格式无效：%s\n' "$tool_name" "$run_id" >&2
    exit 2
fi
if [[ -n "$provider" && ! "$provider" =~ ^[A-Za-z0-9._-]+$ ]]; then
    printf '%s：provider 格式无效：%s\n' "$tool_name" "$provider" >&2
    exit 2
fi

json_escape() {
    local value=${1:-}
    value=${value//\\/\\\\}
    value=${value//\"/\\\"}
    value=${value//$'\n'/\\n}
    value=${value//$'\r'/\\r}
    value=${value//$'\t'/\\t}
    printf '%s' "$value"
}

manifest_value() {
    local manifest=$1 key=$2
    [[ -r "$manifest" && -n "$key" ]] || return 1
    awk -F= -v wanted="$key" '
        $1 == wanted {
            sub(/^[^=]*=/, "", $0)
            print
            exit
        }
    ' "$manifest"
}

resolve_data_root() {
    local candidate
    if [[ -n "$data_root_arg" ]]; then
        candidate=$data_root_arg
    elif [[ -n "${AGENT_DATA_DIR:-}" ]]; then
        candidate=${AGENT_DATA_DIR}
    elif [[ -n "${CONFIGURE_AGENT_DATA_DIR:-}" ]]; then
        candidate=${CONFIGURE_AGENT_DATA_DIR}
    elif [[ -d "${config_root}/data" ]]; then
        candidate=${config_root}/data
    elif [[ -n "${HOME:-}" && -d "${HOME}/configure/data" ]]; then
        candidate=${HOME}/configure/data
    else
        printf '%s：无法定位 agent 数据根\n' "$tool_name" >&2
        return 73
    fi
    [[ -d "$candidate" ]] || {
        printf '%s：数据根不存在：%s\n' "$tool_name" "$candidate" >&2
        return 73
    }
    (CDPATH= cd -- "$candidate" && pwd -P)
}

data_root=$(resolve_data_root) || exit $?

reset_run_state() {
    _run_id=""
    _manifest=""
    _run_dir=""
    _agent=""
    _launcher=""
    _state=""
    _log_file=""
    _event_file=""
    _stop_file=""
    _workspace_root=""
    _run_cwd=""
    _model=""
    _reasoning=""
    _variant=""
    _thread_id=""
    _session_id=""
    _discovered_thread=""
    _discovered_session=""
    _created_at=""
    _agent_state_loaded=0
    _agent_state_session=""
    _agent_state_thread=""
    _agent_state_transient=""
    _turn=0
    _reason=""
}

normalize_existing_dir() {
    local path=$1
    [[ -d "$path" ]] || return 1
    (CDPATH= cd -P -- "$path" 2>/dev/null && pwd -P)
}

normalize_existing_file() {
    local path=$1 parent base
    [[ -f "$path" ]] || return 1
    parent=$(normalize_existing_dir "$(dirname -- "$path")") || return 1
    base=$(basename -- "$path")
    [[ -n "$base" ]] || return 1
    printf '%s/%s\n' "$parent" "$base"
}

path_under() {
    local path=$1 root=$2
    [[ "$path" == "$root" || "$path" == "$root"/* ]]
}

lock_owner() {
    local lock_file=$1
    awk 'NR == 1 { print; exit }' "$lock_file" 2>/dev/null || true
}

lock_is_alive() {
    local lock_file=$1 owner
    [[ -e "$lock_file" ]] || return 1
    owner=$(lock_owner "$lock_file")
    [[ "$owner" =~ ^[1-9][0-9]*$ ]] || return 2
    kill -0 "$owner" 2>/dev/null
}

report_value() {
    local report=$1 key=$2
    awk -F= -v wanted="$key" '
        $1 == wanted {
            sub(/^[^=]*=/, "", $0)
            print
            exit
        }
    ' <<<"$report"
}

load_agent_state_report() {
    if [[ "$_agent_state_loaded" == 1 ]]; then
        [[ -n "$_agent_state_session$_agent_state_thread" ]]
        return
    fi
    _agent_state_loaded=1
    local helper=${config_root}/tools/agent-session-state.py
    local python_bin=${AGENT_STATE_PYTHON:-${AGENT_CODEX_STATE_PYTHON:-python3}}
    [[ -r "$helper" ]] && command -v "$python_bin" >/dev/null 2>&1 || return 1

    local -a state_args=(--agent "$_agent" --run-id "$_run_id" --cwd "$_run_cwd")
    [[ -z "$_created_at" ]] || state_args+=(--created-at "$_created_at")
    local report=""
    if command -v timeout >/dev/null 2>&1; then
        report=$(timeout "${AGENT_STATE_TIMEOUT:-${AGENT_CODEX_STATE_TIMEOUT:-5}}" \
            "$python_bin" "$helper" "${state_args[@]}" 2>/dev/null) || return 1
    else
        report=$("$python_bin" "$helper" "${state_args[@]}" 2>/dev/null) || return 1
    fi
    local session_id thread_id
    session_id=$(report_value "$report" session_id)
    thread_id=$(report_value "$report" thread_id)
    [[ -z "$session_id" || "$session_id" =~ ^[A-Za-z0-9._-]+$ ]] || return 1
    [[ -z "$thread_id" || "$thread_id" =~ ^[A-Za-z0-9._-]+$ ]] || return 1
    [[ -n "$session_id$thread_id" ]] || return 1
    _agent_state_session=$session_id
    _agent_state_thread=$thread_id
    _agent_state_transient=$(report_value "$report" transient_failure)
    return 0
}

agent_state_has_transient_failure() {
    load_agent_state_report || return 1
    [[ "$_agent_state_transient" == 1 ]]
}

recover_session_ids() {
    local id=""
    case "$_agent" in
        codex)
            if [[ -z "$_thread_id" && -r "$_log_file" ]]; then
                id=$(grep -oE '"thread_id"[[:space:]]*:[[:space:]]*"[A-Za-z0-9._-]+"' "$_log_file" 2>/dev/null |
                    head -1 | sed -E 's/.*"thread_id"[[:space:]]*:[[:space:]]*"//; s/"$//')
                if [[ "$id" =~ ^[A-Za-z0-9._-]+$ ]]; then
                    _discovered_thread=$id
                    _thread_id=$id
                fi
            fi
            ;;
        claude)
            if [[ -z "$_session_id" && -r "$_log_file" ]]; then
                id=$(grep -oE 'session_(id|\.id)=[A-Za-z0-9._-]+' "$_log_file" 2>/dev/null |
                    head -1 | cut -d= -f2)
                if [[ "$id" =~ ^[A-Za-z0-9._-]+$ ]]; then
                    _discovered_session=$id
                    _session_id=$id
                fi
            fi
            ;;
        opencode)
            if [[ -z "$_session_id" && -r "$_log_file" ]]; then
                id=$(grep -oE '"sessionID"[[:space:]]*:[[:space:]]*"[A-Za-z0-9._-]+"' "$_log_file" 2>/dev/null |
                    head -1 | sed -E 's/.*"sessionID"[[:space:]]*:[[:space:]]*"//; s/"$//')
                if [[ -z "$id" ]]; then
                    id=$(grep -oE 'session\.id=[A-Za-z0-9._-]+' "$_log_file" 2>/dev/null |
                        head -1 | cut -d= -f2)
                fi
                if [[ -z "$id" ]]; then
                    id=$(grep -oE '/session/ses_[A-Za-z0-9._-]+' "$_log_file" 2>/dev/null |
                        head -1 | sed 's#.*/##')
                fi
                if [[ "$id" =~ ^[A-Za-z0-9._-]+$ ]]; then
                    _discovered_session=$id
                    _session_id=$id
                fi
            fi
            ;;
        *)
            return 1
            ;;
    esac
    if load_agent_state_report; then
        if [[ -z "$_session_id" && -n "$_agent_state_session" ]]; then
            _discovered_session=$_agent_state_session
            _session_id=$_agent_state_session
        fi
        if [[ -z "$_thread_id" && -n "$_agent_state_thread" ]]; then
            _discovered_thread=$_agent_state_thread
            _thread_id=$_agent_state_thread
        fi
    fi
    if [[ "$_agent" == codex ]]; then
        if [[ -z "$_session_id" && -n "$_thread_id" ]]; then
            _discovered_session=$_thread_id
            _session_id=$_thread_id
        fi
        [[ -n "$_thread_id" ]]
        return
    fi
    [[ -n "$_session_id" ]]
}

classify_transient_failure() {
    if [[ -r "$_log_file" ]] && tail -n 200 -- "$_log_file" 2>/dev/null | grep -Eiq \
        'exceeded retry limit|429[[:space:]]+too many requests|too many requests|rate limit|concurr(ency|ent)([[:space:]_\.-]*(request|session|job|task|run|connection)s?)?[[:space:]_\.-]*(limit|cap|quota|exceeded|reached)|too many concurrent([[:space:]_\.-]+(request|session|job|task|run|connection)s?)?|maximum concurrent([[:space:]_\.-]+(request|session|job|task|run|connection)s?)?|parallel(ism)?[[:space:]_\.-]*(request|session|job|task|run|connection)?s?[[:space:]_\.-]*(limit|cap|quota|exceeded|reached)|并发[^[:cntrl:]]{0,20}(上限|限制|超限|已满|过多)|overloaded_error|service unavailable|bad gateway|gateway timeout|connection reset by peer|connection refused|stream disconnected|unexpected eof|timed out|temporarily unavailable|upstream_error|reasoning_content.*passed back|(http|status([[:space:]_\.-]*code)?)[^0-9]*(429|500|502|503|504)'; then
        return 0
    fi
    agent_state_has_transient_failure
}

inspect_run() {
    local manifest=$1 lock_file lock_status event_parent
    reset_run_state
    _manifest=$manifest

    [[ -r "$manifest" ]] || { _reason=manifest_unreadable; return 1; }
    _run_id=$(manifest_value "$manifest" run_id)
    [[ "$_run_id" =~ ^[A-Za-z0-9._-]+$ ]] || { _reason=invalid_run_id; return 1; }
    [[ "$(manifest_value "$manifest" schema_version)" == 1 ]] || { _reason=unsupported_schema; return 1; }

    _agent=$(manifest_value "$manifest" agent)
    _launcher=$(manifest_value "$manifest" launcher)
    case "${_agent}:${_launcher}" in
        codex:co|codex:cos|opencode:op|opencode:ops|claude:cl|claude:cls) ;;
        *) _reason=invalid_identity; return 1;;
    esac

    _run_dir=$(manifest_value "$manifest" run_dir)
    [[ -n "$_run_dir" ]] || _run_dir=$(dirname -- "$manifest")
    _run_dir=$(normalize_existing_dir "$_run_dir") || { _reason=run_dir_missing; return 1; }
    [[ "$_run_dir" == "$data_root/runs/$_run_id" ]] || { _reason=run_dir_mismatch; return 1; }

    _workspace_root=$(manifest_value "$manifest" workspace_root)
    _workspace_root=$(normalize_existing_dir "$_workspace_root") || { _reason=workspace_missing; return 1; }
    _run_cwd=$(manifest_value "$manifest" cwd)
    _run_cwd=$(normalize_existing_dir "$_run_cwd") || _run_cwd=$_workspace_root
    path_under "$_run_cwd" "$_workspace_root" || { _reason=cwd_outside_workspace; return 1; }

    _log_file=$(manifest_value "$manifest" log_file)
    [[ -n "$_log_file" ]] || _log_file=${_run_dir}/agent.log
    _log_file=$(normalize_existing_file "$_log_file") || { _reason=log_missing; return 1; }
    path_under "$_log_file" "$_run_dir" || { _reason=log_outside_run; return 1; }

    _event_file=$(manifest_value "$manifest" event_file)
    [[ -n "$_event_file" ]] || _event_file=${_run_dir}/events.jsonl
    if [[ -e "$_event_file" ]]; then
        _event_file=$(normalize_existing_file "$_event_file") || { _reason=event_file_invalid; return 1; }
        path_under "$_event_file" "$_run_dir" || { _reason=event_file_outside_run; return 1; }
    else
        event_parent=$(normalize_existing_dir "$(dirname -- "$_event_file")" 2>/dev/null || true)
        if [[ -n "$event_parent" ]] && path_under "$event_parent" "$_run_dir"; then
            _event_file=${event_parent}/$(basename -- "$_event_file")
        else
            _event_file=${_run_dir}/events.jsonl
        fi
    fi
    _stop_file=$(manifest_value "$manifest" stop_file)
    _created_at=$(manifest_value "$manifest" created_at)
    _model=$(manifest_value "$manifest" model)
    _reasoning=$(manifest_value "$manifest" reasoning_effort)
    _variant=$(manifest_value "$manifest" variant)
    _thread_id=$(manifest_value "$manifest" thread_id)
    _session_id=$(manifest_value "$manifest" session_id)
    if [[ -n "$_model" ]]; then
        case "$_model" in
            -*) _reason=invalid_model; return 1;;
            *[[:space:]]*) _reason=invalid_model; return 1;;
        esac
    fi
    if [[ -n "$_reasoning" && ! "$_reasoning" =~ ^[A-Za-z0-9._-]+$ ]]; then
        _reason=invalid_reasoning
        return 1
    fi
    if [[ -n "$_variant" && ! "$_variant" =~ ^[A-Za-z0-9._-]+$ ]]; then
        _reason=invalid_variant
        return 1
    fi
    _turn=$(manifest_value "$manifest" turn)
    [[ "$_turn" =~ ^[0-9]+$ ]] || _turn=0

    [[ ! -e "$_stop_file" ]] || { _reason=stop_requested; return 1; }
    lock_file=${_run_dir}/.lock
    lock_status=0
    lock_is_alive "$lock_file" || lock_status=$?
    if (( lock_status == 0 )); then
        _reason=agent_alive
        return 1
    fi
    # A malformed lock cannot identify a live owner. Treat it as stale; the
    # launcher performs its own atomic stale-lock recovery before writing state.
    (( lock_status == 2 )) && _reason=stale_lock

    _state=$(manifest_value "$manifest" state)
    case "$_state" in
        finished|stopped)
            _reason=state_${_state}
            return 1;;
        *);;
    esac

    if classify_transient_failure; then
        _reason=transient_failure
    else
        _reason=unexpected_interruption
    fi
    recover_session_ids || { _reason=session_missing; return 1; }
    return 0
}

find_resumable_manifest() {
    local manifest
    while IFS= read -r manifest; do
        if inspect_run "$manifest"; then
            printf '%s\n' "$manifest"
            return 0
        fi
    done < <(find "${data_root}/runs" -mindepth 2 -maxdepth 2 -type f -name manifest.env -print 2>/dev/null | sort -r)
    return 1
}

if [[ -n "$run_id" ]]; then
    manifest=${data_root}/runs/${run_id}/manifest.env
    if [[ ! -r "$manifest" ]]; then
        printf '%s：status=skipped run_id=%s reason=run_missing\n' "$tool_name" "$run_id" >&2
        exit 6
    fi
else
    manifest=$(find_resumable_manifest || true)
    if [[ -z "$manifest" ]]; then
        printf '%s：status=none reason=%s data_root=%s\n' "$tool_name" "${_reason:-no_resumable_run}" "$data_root" >&2
        exit 3
    fi
fi

inspect_run "$manifest" || {
    printf '%s：status=skipped run_id=%s reason=%s\n' \
        "$tool_name" "${_run_id:-unknown}" "${_reason:-not_resumable}" >&2
    case "${_reason:-}" in
        agent_alive|stop_requested|state_finished|state_stopped|resume_already_scheduled) exit 4;;
        invalid_run_id|unsupported_schema|invalid_identity|run_dir_mismatch|workspace_missing|cwd_outside_workspace|log_outside_run|event_file_invalid|event_file_outside_run|invalid_model|invalid_reasoning|invalid_variant) exit 5;;
        *) exit 3;;
    esac
}

if [[ "$mode" == check ]]; then
    printf '%s：status=resumable run_id=%s agent=%s launcher=%s state=%s delay=%s timeout=%s reason=%s\n' \
        "$tool_name" "$_run_id" "$_agent" "$_launcher" "$_state" \
        "$delay" "$timeout_seconds" "$_reason"
    exit 0
fi

resume_log=${_run_dir}/resume.log
schedule_lock=${_run_dir}/.auto-resume-schedule
attempt_marker=${_run_dir}/.auto-resume-attempted

acquire_schedule_lock() {
    local owner stale
    if mkdir -- "$schedule_lock" 2>/dev/null; then
        printf '%s\n' "$$" >"${schedule_lock}/pid"
        return 0
    fi
    owner=$(awk 'NR == 1 { print; exit }' "${schedule_lock}/pid" 2>/dev/null || true)
    if [[ "$owner" =~ ^[1-9][0-9]*$ ]] && kill -0 "$owner" 2>/dev/null; then
        _reason=resume_already_scheduled
        return 1
    fi
    stale=${schedule_lock}.stale.$$
    if mv -- "$schedule_lock" "$stale" 2>/dev/null; then
        rm -f -- "${stale}/pid" 2>/dev/null || true
        rmdir -- "$stale" 2>/dev/null || true
    fi
    if mkdir -- "$schedule_lock" 2>/dev/null; then
        printf '%s\n' "$$" >"${schedule_lock}/pid"
        return 0
    fi
    _reason=resume_already_scheduled
    return 1
}

release_schedule_lock() {
    local owner
    owner=$(awk 'NR == 1 { print; exit }' "${schedule_lock}/pid" 2>/dev/null || true)
    if [[ "$owner" == "$$" ]]; then
        rm -f -- "${schedule_lock}/pid" 2>/dev/null || true
        rmdir -- "$schedule_lock" 2>/dev/null || true
    fi
}

append_run_event() {
    local event=$1 status=$2 message=$3 timestamp
    timestamp=$(date '+%Y-%m-%dT%H:%M:%S%z')
    mkdir -p -- "$(dirname -- "$_event_file")" 2>/dev/null || true
    printf '{"schema_version":"1","event":"%s","timestamp":"%s","source":"agent-resume","run_id":"%s","launcher":"%s","agent":"%s","workspace":"%s","session_id":"%s","thread_id":"%s","turn":%s,"status":"%s","message":"%s"}\n' \
        "$(json_escape "$event")" \
        "$(json_escape "$timestamp")" \
        "$(json_escape "$_run_id")" \
        "$(json_escape "$_launcher")" \
        "$(json_escape "$_agent")" \
        "$(json_escape "$_workspace_root")" \
        "$(json_escape "$_session_id")" \
        "$(json_escape "$_thread_id")" \
        "$_turn" \
        "$(json_escape "$status")" \
        "$(json_escape "$message")" >>"$_event_file" 2>/dev/null || true
}

update_manifest_identity() {
    local source=$1 temp=${1}.resume.$$ thread=${_thread_id:-} session=${_session_id:-}
    [[ -n "$thread" || -n "$session" ]] || return 0
    umask 077
    awk -v thread="$thread" -v session="$session" '
        BEGIN { seen_thread = 0; seen_session = 0 }
        /^thread_id=/ && thread != "" { print "thread_id=" thread; seen_thread = 1; next }
        /^session_id=/ && session != "" { print "session_id=" session; seen_session = 1; next }
        { print }
        END {
            if (thread != "" && !seen_thread) print "thread_id=" thread
            if (session != "" && !seen_session) print "session_id=" session
        }
    ' "$source" >"$temp" || {
        rm -f -- "$temp"
        return 1
    }
    mv -f -- "$temp" "$source"
}

resolve_launcher() {
    local candidate
    if [[ -n "$launcher_override" ]]; then
        candidate=$launcher_override
        [[ "$candidate" == */* ]] || candidate=${config_root}/bin/$candidate
    else
        candidate=${config_root}/bin/${_launcher}
    fi
    [[ -x "$candidate" ]] || return 1
    printf '%s\n' "$candidate"
}

terminate_active_launcher() {
    local pid=$active_launcher_pid group=$active_launcher_group
    [[ -n "$pid" ]] || return 0
    if kill -0 "$pid" 2>/dev/null; then
        if (( group )); then
            kill -TERM -- "-$pid" 2>/dev/null || true
        else
            kill -TERM "$pid" 2>/dev/null || true
        fi
        sleep 2
        if kill -0 "$pid" 2>/dev/null; then
            if (( group )); then
                kill -KILL -- "-$pid" 2>/dev/null || true
            else
                kill -KILL "$pid" 2>/dev/null || true
            fi
        fi
    fi
    wait "$pid" 2>/dev/null || true
    active_launcher_pid=""
    active_launcher_group=0
}

run_launcher() {
    local launcher_path=$1 pid started now elapsed rc use_setsid=0 next_heartbeat
    shift
    started=$(date '+%s')
    next_heartbeat=$((started + heartbeat_seconds))
    if command -v setsid >/dev/null 2>&1; then
        use_setsid=1
    fi

    (
        cd -- "$_run_cwd" || exit 73
        export AGENT_DATA_DIR="$data_root"
        export AGENT_RESUME_ACTIVE=1
        export AGENT_AUTO_RESUME=0
        case "$_agent" in
            codex) [[ -z "$provider" ]] || export CODEX_PROVIDER_ID="$provider";;
            opencode) [[ -z "$provider" ]] || export OPENCODE_PROVIDER="$provider";;
            claude) [[ -z "$provider" ]] || export CLAUDE_PROVIDER="$provider";;
        esac
        if (( use_setsid )); then
            exec setsid "$launcher_path" "$@"
        fi
        exec "$launcher_path" "$@"
    ) >>"$resume_log" 2>&1 &
    pid=$!
    active_launcher_pid=$pid
    active_launcher_group=$use_setsid

    while kill -0 "$pid" 2>/dev/null; do
        now=$(date '+%s')
        elapsed=$((now - started))
        if (( now >= next_heartbeat )); then
            printf '%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z') run_id=${_run_id} heartbeat elapsed=${elapsed}s pid=${pid}" \
                >>"$resume_log"
            next_heartbeat=$((now + heartbeat_seconds))
        fi
        if (( elapsed >= timeout_seconds )); then
            if (( use_setsid )); then
                kill -TERM -- "-$pid" 2>/dev/null || true
            else
                kill -TERM "$pid" 2>/dev/null || true
            fi
            sleep 2
            if (( use_setsid )); then
                kill -KILL -- "-$pid" 2>/dev/null || true
            else
                kill -KILL "$pid" 2>/dev/null || true
            fi
            wait "$pid" 2>/dev/null || true
            active_launcher_pid=""
            active_launcher_group=0
            printf '%s：run_id=%s 恢复超时（%ss），已终止 launcher pid=%s\n' \
                "$tool_name" "$_run_id" "$timeout_seconds" "$pid" >>"$resume_log"
            return 124
        fi
        sleep 1
    done
    if wait "$pid"; then
        rc=0
    else
        rc=$?
    fi
    active_launcher_pid=""
    active_launcher_group=0
    return "$rc"
}

acquire_schedule_lock || {
    printf '%s：status=skipped run_id=%s reason=%s\n' \
        "$tool_name" "$_run_id" "$_reason" >&2
    exit 4
}
cleanup_resume() {
    terminate_active_launcher
    release_schedule_lock
}
trap cleanup_resume EXIT
trap 'cleanup_resume; exit 129' HUP
trap 'cleanup_resume; exit 130' INT
trap 'cleanup_resume; exit 143' TERM

printf '%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z') run_id=${_run_id} scheduled_delay=${delay}s provider=${provider:-<inherit>}" \
    >>"$resume_log"
append_run_event resume-scheduled ok "检测到 agent 意外中断，${delay} 秒后自动恢复"
printf '%s：status=scheduled run_id=%s delay=%s resume_log=%s\n' \
    "$tool_name" "$_run_id" "$delay" "$resume_log"

launcher_args=(--resume "$_run_id" --once)
case "$_agent" in
    codex)
        [[ -z "$_model" ]] || launcher_args+=(--model "$_model")
        [[ -z "$_reasoning" ]] || launcher_args+=(--reasoning-effort "$_reasoning")
        [[ -z "${AGENT_PARENT_SANDBOX:-}" ]] || launcher_args+=(--sandbox "$AGENT_PARENT_SANDBOX")
        [[ -z "${AGENT_PARENT_APPROVAL:-}" ]] || launcher_args+=(--ask-for-approval "$AGENT_PARENT_APPROVAL")
        ;;
    opencode)
        [[ -z "$_model" ]] || launcher_args+=(--model "$_model")
        [[ -z "$_variant" ]] || launcher_args+=(--variant "$_variant")
        ;;
    claude)
        if [[ -n "$_model" ]]; then
            launcher_args+=("$_model")
            [[ -z "$_reasoning" ]] || launcher_args+=("$_reasoning")
        fi
        ;;
esac

attempt=0
while true; do
    sleep "$delay"
    attempt=$((attempt + 1))
    inspect_run "$manifest" || {
        append_run_event resume-skipped info "重试前不再满足恢复条件：${_reason}"
        printf '%s：status=skipped run_id=%s reason=%s attempts=%s\n' \
            "$tool_name" "$_run_id" "$_reason" "$attempt" >&2
        exit 4
    }

    update_manifest_identity "$manifest" || {
        append_run_event resume-failed failed "无法写回 session/thread 标识"
        printf '%s：status=failed run_id=%s reason=manifest_write_failed\n' "$tool_name" >&2
        exit 73
    }
    state_file=${_run_dir}/state.env
    if [[ -f "$state_file" ]]; then
        update_manifest_identity "$state_file" || true
    fi

    launcher_path=$(resolve_launcher) || {
        append_run_event resume-failed failed "统一 launcher 不存在或不可执行"
        printf '%s：status=failed run_id=%s reason=launcher_unavailable\n' "$tool_name" >&2
        exit 7
    }

    printf 'attempt=%s\nupdated_at=%s\n' "$attempt" "$(date '+%Y-%m-%dT%H:%M:%S%z')" \
        >"$attempt_marker"
    append_run_event resume-start ok "第 ${attempt} 次恢复开始"
    printf '%s：status=starting run_id=%s attempt=%s launcher=%s provider=%s\n' \
        "$tool_name" "$_run_id" "$attempt" "$launcher_path" "${provider:-<inherit>}"
    if run_launcher "$launcher_path" "${launcher_args[@]}"; then
        rc=0
        append_run_event resume-end ok "第 ${attempt} 次自动恢复成功"
        printf '%s：status=finished run_id=%s attempts=%s exit_code=0\n' \
            "$tool_name" "$_run_id" "$attempt"
        exit 0
    else
        rc=$?
    fi

    append_run_event resume-end failed "第 ${attempt} 次自动恢复失败，退出码 ${rc}"
    printf '%s：status=retrying run_id=%s attempt=%s exit_code=%s resume_log=%s\n' \
        "$tool_name" "$_run_id" "$attempt" "$rc" "$resume_log" >&2
    if (( max_attempts > 0 && attempt >= max_attempts )); then
        printf '%s：status=failed run_id=%s attempts=%s exit_code=%s resume_log=%s\n' \
            "$tool_name" "$_run_id" "$attempt" "$rc" "$resume_log" >&2
        exit "$rc"
    fi
done
