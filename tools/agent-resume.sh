#!/usr/bin/env bash
# Resume one agent run after a transient infrastructure interruption.

set -Eeuo pipefail

tool_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd)
tool_name=$(basename -- "${BASH_SOURCE[0]:-$0}")
config_root=${AGENT_CONFIGURE_ROOT:-$(CDPATH= cd -- "${tool_dir}/.." && pwd)}

mode=resume
run_id=${AGENT_RUN_ID:-}
data_root_arg=""
delay=${AGENT_RESUME_DELAY:-10}
timeout_seconds=${AGENT_RESUME_TIMEOUT:-1800}
provider=${AGENT_RESUME_PROVIDER:-${AGENT_PARENT_PROVIDER:-}}
launcher_override=${AGENT_RESUME_LAUNCHER:-}
force=0

usage() {
    cat <<'USAGE'
用法：agent-resume.sh [选项]

检测一次因瞬时服务故障（例如 429、重试上限、连接中断）而退出的 agent run，
默认等待 10 秒后用原统一 launcher 执行 `--resume RUN_ID --once`。每个 run
只自动恢复一次，避免持续限流时形成无界重试。

选项：
  --run-id RUN_ID       指定 run；缺省依次读取 AGENT_RUN_ID 或最新可恢复 run
  --data-root DIR       覆盖 AGENT_DATA_DIR / configure 数据根
  --delay SECONDS       恢复前等待秒数，默认 10
  --timeout SECONDS     单次恢复的硬超时，默认 1800
  --provider NAME       恢复时使用的供应商；默认继承 AGENT_PARENT_PROVIDER
  --launcher PATH       覆盖 manifest 对应的统一 launcher（主要供包装器/测试）
  --check               只检查是否可恢复，不等待、不写文件
  --dry-run             输出将要执行的恢复计划，不等待、不写文件
  --force               忽略单次自动恢复标记
  -h, --help            显示帮助

退出码：0 恢复成功；1 已恢复但 agent 失败；2 参数错误；3 不可恢复；
4 正在运行、已停止或已尝试自动恢复；5 manifest/会话标识无效；6 找不到 run；
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
        --provider)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            provider=$2; shift 2;;
        --launcher)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            launcher_override=$2; shift 2;;
        --check|--dry-run)
            mode=check; shift;;
        --force)
            force=1; shift;;
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
            if [[ -z "$_session_id" && -n "$_thread_id" ]]; then
                _discovered_session=$_thread_id
                _session_id=$_thread_id
            fi
            [[ -n "$_thread_id" ]]
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
            [[ -n "$_session_id" ]]
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
            [[ -n "$_session_id" ]]
            ;;
        *)
            return 1
            ;;
    esac
}

log_has_transient_failure() {
    [[ -r "$_log_file" ]] || return 1
    tail -n 200 -- "$_log_file" 2>/dev/null | grep -Eiq \
        'exceeded retry limit|429[[:space:]]+too many requests|too many requests|rate limit|overloaded_error|service unavailable|bad gateway|gateway timeout|connection reset by peer|connection refused|stream disconnected|unexpected eof|timed out|temporarily unavailable|http[^0-9]*(500|502|503|504)'
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
    if (( lock_status == 2 )); then
        _reason=lock_unreadable
        return 1
    fi

    if [[ "$force" != 1 && -e "${_run_dir}/.auto-resume-attempted" ]]; then
        _state=$(manifest_value "$manifest" state)
        _reason=already_attempted
        return 1
    fi

    _state=$(manifest_value "$manifest" state)
    case "$_state" in
        failed|blocked) ;;
        running) _reason=stale_running;;
        finished|stopped|prepared|created)
            _reason=state_${_state:-missing}
            return 1;;
        *) _reason=state_unknown; return 1;;
    esac

    log_has_transient_failure || { _reason=non_transient_failure; return 1; }
    recover_session_ids || { _reason=session_missing; return 1; }
    _reason=transient_failure
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
        agent_alive|stop_requested|already_attempted|resume_already_scheduled) exit 4;;
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

run_launcher() {
    local launcher_path=$1 pid started now elapsed rc use_setsid=0
    shift
    started=$(date '+%s')
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

    while kill -0 "$pid" 2>/dev/null; do
        now=$(date '+%s')
        elapsed=$((now - started))
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
            printf '%s：run_id=%s 恢复超时（%ss），已终止 launcher pid=%s\n' \
                "$tool_name" "$_run_id" "$timeout_seconds" "$pid" >>"$resume_log"
            return 124
        fi
        sleep 1
    done
    if wait "$pid"; then
        return 0
    else
        rc=$?
        return "$rc"
    fi
}

acquire_schedule_lock || {
    printf '%s：status=skipped run_id=%s reason=%s\n' \
        "$tool_name" "$_run_id" "$_reason" >&2
    exit 4
}
trap release_schedule_lock EXIT
trap 'release_schedule_lock; exit 129' HUP
trap 'release_schedule_lock; exit 130' INT
trap 'release_schedule_lock; exit 143' TERM

printf '%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z') run_id=${_run_id} scheduled_delay=${delay}s provider=${provider:-<inherit>}" \
    >>"$resume_log"
printf '%s\n' "$$" >"$attempt_marker"
append_run_event resume-scheduled ok "检测到瞬时中断，${delay} 秒后自动恢复"
printf '%s：status=scheduled run_id=%s delay=%s resume_log=%s\n' \
    "$tool_name" "$_run_id" "$delay" "$resume_log"

sleep "$delay"

# The marker intentionally proves that this run already consumed its single
# automatic attempt; do not let it suppress the post-delay health check.
force=1
inspect_run "$manifest" || {
    append_run_event resume-skipped info "等待后不再满足恢复条件：${_reason}"
    printf '%s：status=skipped run_id=%s reason=%s\n' \
        "$tool_name" "$_run_id" "$_reason" >&2
    exit 4
}

update_manifest_identity "$manifest" || {
    append_run_event resume-failed failed "无法写回 session/thread 标识"
    printf '%s：status=failed run_id=%s reason=manifest_write_failed\n' \
        "$tool_name" "$_run_id" >&2
    exit 73
}
state_file=${_run_dir}/state.env
if [[ -f "$state_file" ]]; then
    update_manifest_identity "$state_file" || true
fi

launcher_path=$(resolve_launcher) || {
    append_run_event resume-failed failed "统一 launcher 不存在或不可执行"
    printf '%s：status=failed run_id=%s reason=launcher_unavailable\n' \
        "$tool_name" "$_run_id" >&2
    exit 7
}

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

append_run_event resume-start ok "等待结束，开始恢复"
printf '%s：status=starting run_id=%s launcher=%s provider=%s\n' \
    "$tool_name" "$_run_id" "$launcher_path" "${provider:-<inherit>}"
if run_launcher "$launcher_path" "${launcher_args[@]}"; then
    rc=0
    append_run_event resume-end ok "自动恢复成功"
    printf '%s：status=finished run_id=%s exit_code=0\n' "$tool_name" "$_run_id"
else
    rc=$?
    append_run_event resume-end failed "自动恢复失败，退出码 ${rc}"
    printf '%s：status=failed run_id=%s exit_code=%s resume_log=%s\n' \
        "$tool_name" "$_run_id" "$rc" "$resume_log" >&2
fi
exit "$rc"
