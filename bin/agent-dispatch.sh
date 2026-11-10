#!/usr/bin/env bash
# 高层子 agent 派发接口：一次任务、最小上下文、机器可读结果。

_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
printf '###%s in %s is running...:%s###\n' "${_NAME}" "${_PATH}" "$(date '+%Y-%m-%d-%H-%M-%S')" >&2

_usage() {
    cat >&2 <<'EOF'
用法: agent-dispatch.sh [OPTIONS]
  --task TEXT             子任务正文（必填，除非使用 --task-file）
  --task-file PATH        从文件读取子任务正文
  --agent co|cl|op|cm     默认继承父 agent；无父上下文时默认 co
                          跨 agent 且未显式 --model/--strength 时回落目标默认
  --provider NAME         默认继承父 provider；可传 pay/go/cgo/gt/tgo/dgo 或完整名
  --model MODEL           默认继承父最终模型（跨 agent 时需显式指定）
  --strength LEVEL        默认继承父最终强度（跨 agent 时需显式指定）
  --cwd DIR               默认继承父工作目录
  --timeout DUR           超时（如 30s/5m/1h；默认 AGENT_DISPATCH_TIMEOUT=30m，0 关闭；
                          无 timeout 命令时不强制；超时/中断后不再拉起恢复链）
  --full                  使用完整 agent-prompt；默认使用最小子 agent prompt
                          瞬时 429/重试上限失败会自动恢复一次同一 run
  --text                  返回纯文本；默认返回 JSON
  --json                  返回 JSON（默认）
  --secure/--no-secure    覆盖 secure/HPC launcher 继承
  -h, --help              显示帮助
EOF
}

_fail() {
    printf '###%s: ERROR: %s###\n' "${_NAME}" "$*" >&2
    exit 64
}

_task=""
_task_file=""
_agent="${AGENT_PARENT_AGENT:-codex}"
_provider="${AGENT_PARENT_PROVIDER:-}"
_model="${AGENT_PARENT_MODEL:-}"
_strength="${AGENT_PARENT_STRENGTH:-}"
_cwd="${AGENT_PARENT_CWD:-$PWD}"
_timeout="${AGENT_DISPATCH_TIMEOUT:-30m}"
# --full 是单次派发选项；父 agent 的内部最小化状态不能污染后续默认派发。
_minimal=1
_format=json
_secure="${AGENT_PARENT_SECURE:-0}"
_agent_overridden=0
_secure_overridden=0
_model_overridden=0
_strength_overridden=0

while (( $# )); do
    case "$1" in
        --task)
            (( $# >= 2 )) || _fail '--task 缺少文本'
            _task="$2"; shift 2;;
        --task-file)
            (( $# >= 2 )) || _fail '--task-file 缺少路径'
            _task_file="$2"; shift 2;;
        --agent)
            (( $# >= 2 )) || _fail '--agent 缺少名称'
            _agent="$2"; _agent_overridden=1; shift 2;;
        --provider)
            (( $# >= 2 )) || _fail '--provider 缺少名称'
            _provider="$2"; shift 2;;
        --model)
            (( $# >= 2 )) || _fail '--model 缺少模型'
            _model="$2"; _model_overridden=1; shift 2;;
        --strength)
            (( $# >= 2 )) || _fail '--strength 缺少等级'
            _strength="$2"; _strength_overridden=1; shift 2;;
        --cwd)
            (( $# >= 2 )) || _fail '--cwd 缺少路径'
            _cwd="$2"; shift 2;;
        --timeout)
            (( $# >= 2 )) || _fail '--timeout 缺少时长'
            _timeout="$2"; shift 2;;
        --full)
            _minimal=0; shift;;
        --text)
            _format=text; shift;;
        --json)
            _format=json; shift;;
        --secure)
            _secure=1; _secure_overridden=1; shift;;
        --no-secure)
            _secure=0; _secure_overridden=1; shift;;
        -h|--help)
            _usage; exit 0;;
        *)
            _fail "未知参数 '$1'";;
    esac
done

[[ -n "${_task}" || -n "${_task_file}" ]] || _fail '必须提供 --task 或 --task-file'
[[ -z "${_task}" || -z "${_task_file}" ]] || _fail '--task 与 --task-file 不能同时使用'
if [[ -n "${_task_file}" ]]; then
    [[ -r "${_task_file}" ]] || _fail "--task-file 不可读：${_task_file}"
    _task="$(<"${_task_file}")"
fi
[[ -n "${_task}" ]] || _fail '派发任务为空'
[[ -d "${_cwd}" ]] || _fail "--cwd 不存在：${_cwd}"
[[ "${_timeout}" == 0 ]] && _timeout=""

case "${_agent}" in
    co|codex) _agent=co;;
    cl|claude) _agent=cl;;
    op|opencode) _agent=op;;
    cm|commandcode) _agent=cm;;
    *) _fail "--agent 仅支持 co/cl/op/cm";;
esac
case "${AGENT_PARENT_AGENT:-}" in
    co|codex) _parent_agent=co;;
    cl|claude) _parent_agent=cl;;
    op|opencode) _parent_agent=op;;
    cm|commandcode) _parent_agent=cm;;
    *) _parent_agent="";;
esac
# 跨 agent 派发时，父模型/强度通常不属于目标 agent 的目录；未显式覆盖就回落到目标默认。
if (( _agent_overridden )) && [[ -n "${_parent_agent}" && "${_parent_agent}" != "${_agent}" ]]; then
    (( _model_overridden )) || _model=""
    (( _strength_overridden )) || _strength=""
fi

if (( _agent_overridden )) && (( ! _secure_overridden )); then
    [[ -n "${_parent_agent}" && "${_parent_agent}" == "${_agent}" ]] || _secure=0
fi

case "${_agent}:${_secure}" in
    co:1) _launcher=cos;;
    cl:1) _launcher=cls;;
    op:1) _launcher=ops;;
    cm:1) _launcher=cms;;
    co:0) _launcher=co;;
    cl:0) _launcher=cl;;
    op:0) _launcher=op;;
    cm:0) _launcher=cm;;
esac

[[ -x "${_PATH}/${_launcher}" ]] || _fail "launcher 不存在或不可执行：${_PATH}/${_launcher}"

_tmp="$(mktemp -d "${TMPDIR:-/tmp}/agent-dispatch.XXXXXX")" || exit 70
_cleanup() {
    local _rc=$?
    rm -rf -- "${_tmp}" 2>/dev/null || true
    return "${_rc}"
}
trap '_cleanup' EXIT HUP INT TERM

_combined="${_tmp}/combined.log"
_result_file="${_tmp}/result.txt"
local_args=(--once)
[[ -n "${_provider}" ]] && local_args+=("${_provider}")
case "${_agent}" in
    co)
        [[ -n "${_model}" ]] && local_args+=(--model "${_model}")
        [[ -n "${_strength}" ]] && local_args+=(--reasoning-effort "${_strength}")
        [[ -n "${AGENT_PARENT_SANDBOX:-}" ]] && local_args+=(--sandbox "${AGENT_PARENT_SANDBOX}")
        [[ -n "${AGENT_PARENT_APPROVAL:-}" ]] && local_args+=(--ask-for-approval "${AGENT_PARENT_APPROVAL}")
        ;;
    op)
        [[ -n "${_model}" ]] && local_args+=(--model "${_model}")
        [[ -n "${_strength}" ]] && local_args+=(--variant "${_strength}")
        ;;
    cl)
        if [[ -n "${_model}" ]]; then
            local_args+=("${_model}")
            [[ -n "${_strength}" ]] && local_args+=("${_strength}")
        fi
        ;;
    cm)
        [[ -n "${_model}" ]] && local_args+=(--model "${_model}")
        [[ -n "${_strength}" ]] && local_args+=(--effort "${_strength}")
        [[ -n "${AGENT_PARENT_PERMISSION_MODE:-}" ]] && local_args+=(--permission-mode "${AGENT_PARENT_PERMISSION_MODE}")
        ;;
esac

set +e
if [[ -n "${_timeout}" ]] && command -v timeout >/dev/null 2>&1; then
    (
        cd "${_cwd}" || exit 73
        AGENT_DISPATCH_TASK="${_task}" \
        AGENT_DISPATCH_MINIMAL="${_minimal}" \
        AGENT_DISPATCH_OUTPUT_FILE="${_result_file}" \
        AGENT_AUTO_RESUME=0 \
        timeout "${_timeout}" "${_PATH}/${_launcher}" "${local_args[@]}"
    ) >"${_combined}" 2>&1
    _rc=$?
else
    (
        cd "${_cwd}" || exit 73
        AGENT_DISPATCH_TASK="${_task}" \
        AGENT_DISPATCH_MINIMAL="${_minimal}" \
        AGENT_DISPATCH_OUTPUT_FILE="${_result_file}" \
        AGENT_AUTO_RESUME=0 \
        "${_PATH}/${_launcher}" "${local_args[@]}"
    ) >"${_combined}" 2>&1
    _rc=$?
fi
set -e

_run_id="$(sed -n 's/^[[:space:]]*run:[[:space:]]*//p' "${_combined}" | tail -1)"
_log_file="$(sed -n 's/^[[:space:]]*log:[[:space:]]*//p' "${_combined}" | head -1)"
[[ -n "${_log_file}" ]] || _log_file="$(sed -n 's/^logs -> //p' "${_combined}" | tail -1)"
_manifest=""
if [[ -n "${_run_id}" && -n "${AGENT_PARENT_DATA_ROOT:-}" && -f "${AGENT_PARENT_DATA_ROOT}/runs/${_run_id}/manifest.env" ]]; then
    _manifest="${AGENT_PARENT_DATA_ROOT}/runs/${_run_id}/manifest.env"
elif [[ -n "${_run_id}" && -n "${AGENT_DATA_DIR:-}" && -f "${AGENT_DATA_DIR}/runs/${_run_id}/manifest.env" ]]; then
    _manifest="${AGENT_DATA_DIR}/runs/${_run_id}/manifest.env"
fi

_resume_status=not_needed
_resume_rc=""
# 超时/中断是调用方的最终边界，不能再拉起无限恢复链。
if (( _rc != 0 && _rc != 124 && _rc != 130 && _rc != 143 )) && [[ -n "${_run_id}" && -n "${_manifest}" ]]; then
    _resume_tool="${AGENT_RESUME_TOOL:-${AGENT_CONFIGURE_ROOT:-$(CDPATH= cd -- "${_PATH}/.." && pwd)}/tools/agent-resume.sh}"
    if [[ -x "${_resume_tool}" ]]; then
        _resume_data_root="${AGENT_PARENT_DATA_ROOT:-${AGENT_DATA_DIR:-}}"
        _resume_args=(--run-id "${_run_id}" --delay "${AGENT_RESUME_DELAY:-10}")
        [[ -z "${_resume_data_root}" ]] || _resume_args+=(--data-root "${_resume_data_root}")
        [[ -z "${_provider}" ]] || _resume_args+=(--provider "${_provider}")
        _resume_args+=(--max-attempts "${AGENT_DISPATCH_RESUME_ATTEMPTS:-1}")
        set +e
        _resume_output=$(AGENT_RESUME_PROVIDER="${_provider}" \
            "${_resume_tool}" "${_resume_args[@]}" 2>&1)
        _resume_rc=$?
        set -e
        printf '%s\n' "${_resume_output}" >>"${_combined}"
        case "${_resume_rc}" in
            0)
                _resume_status=finished
                _rc=0
                ;;
            3)
                _resume_status=not_recoverable
                ;;
            4)
                _resume_status=skipped
                ;;
            *)
                _resume_status=failed
                _rc=${_resume_rc}
                ;;
        esac
    else
        _resume_status=unavailable
    fi
fi

if [[ "${_format}" == text ]]; then
    if [[ -s "${_result_file}" ]]; then
        cat -- "${_result_file}"
    elif [[ -n "${_log_file}" && -f "${_log_file}" ]]; then
        tail -n 80 "${_log_file}"
    else
        tail -n 80 "${_combined}"
    fi
else
    python3 - "${_rc}" "${_agent}" "${_launcher}" "${_provider}" "${_model}" \
        "${_strength}" "${_run_id}" "${_manifest}" "${_log_file}" \
        "${_result_file}" "${_combined}" "${_resume_status}" "${_resume_rc}" <<'PY'
import json
import os
import sys

(rc, agent, launcher, provider, model, strength, run_id, manifest,
 log_file, result_file, combined_file, resume_status, resume_rc) = sys.argv[1:14]
rc = int(rc)
result = ""
if os.path.isfile(result_file):
    with open(result_file, encoding="utf-8", errors="replace") as handle:
        result = handle.read()
if not result and log_file and os.path.isfile(log_file):
    messages = []
    with open(log_file, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except Exception:
                continue
            item = event.get("item") if isinstance(event, dict) else None
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = item.get("text")
                if isinstance(text, str) and text:
                    messages.append(text)
    if messages:
        result = messages[-1]

combined_tail = ""
if os.path.isfile(combined_file):
    with open(combined_file, encoding="utf-8", errors="replace") as handle:
        combined_tail = "".join(handle.readlines()[-80:])
state = ""
resolved_model = model
if manifest and os.path.isfile(manifest):
    with open(manifest, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("state="):
                state = line.split("=", 1)[1].strip()
            elif line.startswith("model="):
                candidate = line.split("=", 1)[1].strip()
                if candidate:
                    resolved_model = candidate
payload = {
    "schema_version": "agent-dispatch/v1",
    "ok": rc == 0,
    "agent": agent,
    "launcher": launcher,
    "provider": provider,
    "model": resolved_model,
    "strength": strength,
    "run_id": run_id,
    "state": state,
    "exit_code": rc,
    "timed_out": rc == 124,
    "manifest": manifest,
    "log_file": log_file,
    "result": result,
    "output_tail": "" if result else combined_tail[-4000:],
    "auto_resume": {
        "status": resume_status,
        "exit_code": int(resume_rc) if resume_rc else None,
    },
}
print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
PY
fi

exit "${_rc}"
