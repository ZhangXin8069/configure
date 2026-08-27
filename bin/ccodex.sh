#!/usr/bin/env bash
# Launch Codex: Full Access + 自动批准 + 可选模型/推理强度（默认 -m）
# 支持普通 TUI，以及保留的 -time 无人值守驱动模式。

# 脚本目录定位：CODEX_SCRIPT_DIR 可在 /dev/fd/3 等场景注入真实目录；
# 直接运行/符号链接运行时使用 BASH_SOURCE，环境变量缺失则回退。
_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ -n "${CODEX_SCRIPT_DIR:-}" ]]; then
    _PATH="${CODEX_SCRIPT_DIR}"
else
    if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
fi
_NAME=${CODEX_LAUNCHER_NAME:-${_SRC##*/}}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

# 增强鲁棒性：cwd 失效（如所在目录已被删除）时回退到脚本目录，
# 避免后续 pwd 与相对路径文件/重定向创建失败。
if ! _PWD="$(pwd 2>/dev/null)"; then
    echo "###${_NAME}: warning: 当前目录不可用（getcwd 失败），回退到 ${_PATH}###" >&2
    cd "${_PATH}" || exit 1
    _PWD="$(pwd)"
fi

_TS="$(date +%Y-%m-%d-%H-%M-%S)"
LOG_FILE=".agent.${_TS}.log"
unset _TS

# Codex 可执行文件：可用 CODEX_BIN 覆盖（例如 HPC 上的绝对路径）。
_CODEX_BIN="${CODEX_BIN:-}"
if [[ -z "${_CODEX_BIN}" ]]; then
    _CODEX_BIN="$(command -v codex 2>/dev/null || true)"
fi
if [[ -z "${_CODEX_BIN}" ]]; then
    echo "###${_NAME}: ERROR: 未找到 codex，请安装 Codex CLI 或设置 CODEX_BIN###" >&2
    exit 127
fi

# prompt 单一来源：Codex 专用模板，运行时替换 ${HOME}/${_PWD}。
PROMPT_FILE="${_PATH}/ccodex-prompt.txt"
if [[ ! -r "${PROMPT_FILE}" ]]; then
    echo "###${_NAME}: ERROR: ${PROMPT_FILE} 不存在或不可读（prompt 单一来源缺失）###" >&2
    exit 1
fi
PROMPT="$(<"${PROMPT_FILE}")"
PROMPT="${PROMPT//\$\{HOME\}/${HOME:-}}"
PROMPT="${PROMPT//\$\{_PWD\}/${_PWD}}"
unset PROMPT_FILE

# 初始注入严格限定为：固定 prompt、全局 skill 清单、当前工作区 skill 清单。
# 这里只列出 SKILL.md 路径，不读取 skill 内容；模型选中技能后再按需读取。
declare -A _SEEN_SKILL_PATHS=()
_append_skill_list() {
    local _title="$1" _root _skill_path _found=0 _discovered=0
    shift
    PROMPT+=$'\n\n### '"${_title}"$' ###\n'
    for _root in "$@"; do
        [[ -d "${_root}" ]] || continue
        while IFS= read -r _skill_path; do
            [[ -n "${_skill_path}" ]] || continue
            _discovered=1
            if [[ -z "${_SEEN_SKILL_PATHS[${_skill_path}]+x}" ]]; then
                PROMPT+="${_skill_path}"$'\n'
                _SEEN_SKILL_PATHS["${_skill_path}"]=1
                _found=1
            fi
        done < <(find "${_root}" -type f -name SKILL.md -print 2>/dev/null | sort)
    done
    if (( ! _found )); then
        if (( _discovered )); then
            PROMPT+=$'（与前序清单重复，未重复列出）\n'
        else
            PROMPT+=$'（未找到 SKILL.md）\n'
        fi
    fi
}

_configure_skills="${HOME:-}/configure/skills"
_workspace_root="${_PWD}"
if _git_root="$(git -C "${_PWD}" rev-parse --show-toplevel 2>/dev/null)"; then
    [[ -n "${_git_root}" ]] && _workspace_root="${_git_root}"
fi
_workspace_skill_roots=(
    "${_PWD}/skills"
    "${_PWD}/.codex/skills"
)
if [[ "${_workspace_root}" != "${_PWD}" ]]; then
    _workspace_skill_roots+=(
        "${_workspace_root}/skills"
        "${_workspace_root}/.codex/skills"
    )
fi
_append_skill_list "全局技能（${_configure_skills}）" "${_configure_skills}"
_append_skill_list "当前工作目录技能（${_PWD}）" "${_workspace_skill_roots[@]}"
unset -f _append_skill_list
unset _SEEN_SKILL_PATHS _configure_skills _git_root _workspace_root _workspace_skill_roots

# ---- 参数解析：模型旗标 + 无人值守驱动选项 ----
# 用法: ${_NAME} [-m|-o|-p|-q|-k|-g|-f|-h] [--model MODEL]
#                       [-time DUR]
#   -time/--time DUR  : 驱动模式中「继续」发送间隔，纯数字=秒；支持 s/m/h 后缀（默认 30s）。
#   --model MODEL     : 直接指定 Codex 模型，覆盖模型旗标；也可用 CODEX_MODEL 环境变量覆盖。
#   --reasoning-effort LEVEL : 直接指定 reasoning effort（low/medium/high/xhigh/max/ultra）。
MODEL_FLAG="${CODEX_DEFAULT_MODEL_FLAG:--m}"
MODEL_OVERRIDE="${CODEX_MODEL:-}"
REASONING_OVERRIDE="${CODEX_REASONING_EFFORT:-}"
CODEX_SANDBOX_MODE="${CODEX_SANDBOX:-danger-full-access}"
CODEX_APPROVAL_POLICY="${CODEX_APPROVAL:-never}"
DRIVE_INTERVAL=""
DRIVE_MODE=0
while (( $# )); do
    case "$1" in
        -m|-o|-p|-q|-k|-g|-f|-h) MODEL_FLAG="$1"; shift;;
        --model|-model)
            if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少模型参数###" >&2; exit 64; fi
            MODEL_OVERRIDE="$2"; shift 2;;
        --reasoning-effort)
            if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少等级参数###" >&2; exit 64; fi
            REASONING_OVERRIDE="$2"; shift 2;;
        --sandbox)
            if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少策略参数###" >&2; exit 64; fi
            CODEX_SANDBOX_MODE="$2"; shift 2;;
        --ask-for-approval)
            if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少策略参数###" >&2; exit 64; fi
            CODEX_APPROVAL_POLICY="$2"; shift 2;;
        -time|--time)
            if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少时长参数###" >&2; exit 64; fi
            _ti_raw="$2"; DRIVE_MODE=1; shift 2;;
        --help)
            echo "用法: ${_NAME} [-m|-o|-p|-q|-k|-g|-f|-h] [--model MODEL] [--reasoning-effort LEVEL] [-time DUR]"
            echo "默认模型: ${MODEL_FLAG}；只给模型旗标时进入 Codex TUI，给出 -time 时进入 exec 驱动模式。"
            exit 0;;
        *) echo "###${_NAME}: ERROR: 未知参数 '$1'（用法: ${_NAME} [-m|-o|-p|-q|-k|-g|-f|-h] [--model MODEL] [-time 30s]）###" >&2; exit 64;;
    esac
done

# 时长解析："30"→30 秒；支持 s/m/h 后缀（30s/5m/2h）。
_parse_interval() {
    local v="$1" u n
    u="${v: -1}"
    case "$u" in
        [0-9]) n="$v"; u="s";;
        [smh]) n="${v%?}";;
        *) return 1;;
    esac
    [[ "$n" =~ ^[0-9]+$ ]] || return 1
    (( n > 0 )) || return 1
    case "$u" in
        s) printf '%s\n' "$n";;
        m) printf '%s\n' "$((n * 60))";;
        h) printf '%s\n' "$((n * 3600))";;
    esac
}
if [[ -n "${_ti_raw:-}" ]]; then
    if ! DRIVE_INTERVAL="$(_parse_interval "${_ti_raw}")"; then
        echo "###${_NAME}: ERROR: --time '${_ti_raw}' 格式无效（示例: 30 / 30s / 5m / 2h）###" >&2
        exit 64
    fi
fi
unset _ti_raw _parse_interval
[[ -n "${DRIVE_INTERVAL}" ]] || DRIVE_INTERVAL=30

# 模型选择：这些是当前 Codex CLI 模型目录中的稳定 slug；可用 --model/CODEX_MODEL 覆盖。
# -m/-o 侧重深度，-f 侧重速度；其余旗标保留 op 系列的快捷键习惯。
case "${MODEL_FLAG}" in
    -m) MODEL_ID="${CODEX_MODEL_M:-gpt-5.6-luna}";  MODEL_NAME="GPT-5.6-Luna";  REASONING_EFFORT="max";;
    -o) MODEL_ID="${CODEX_MODEL_O:-gpt-5.6-sol}";   MODEL_NAME="GPT-5.6-Sol";   REASONING_EFFORT="max";;
    -p) MODEL_ID="${CODEX_MODEL_P:-gpt-5.6-terra}"; MODEL_NAME="GPT-5.6-Terra"; REASONING_EFFORT="high";;
    -q) MODEL_ID="${CODEX_MODEL_Q:-gpt-5.5}";       MODEL_NAME="GPT-5.5";       REASONING_EFFORT="high";;
    -k) MODEL_ID="${CODEX_MODEL_K:-gpt-5.4-mini}";  MODEL_NAME="GPT-5.4-Mini";  REASONING_EFFORT="high";;
    -g) MODEL_ID="${CODEX_MODEL_G:-gpt-5.6-luna}";  MODEL_NAME="GPT-5.6-Luna";  REASONING_EFFORT="high";;
    -f) MODEL_ID="${CODEX_MODEL_F:-gpt-5.6-sol}";   MODEL_NAME="GPT-5.6-Sol";   REASONING_EFFORT="low";;
    -h) MODEL_ID="${CODEX_MODEL_H:-gpt-5.6-luna}";  MODEL_NAME="GPT-5.6-Luna";  REASONING_EFFORT="high";;
    *) echo "###${_NAME}: ERROR: 不支持的默认模型旗标 '${MODEL_FLAG}'###" >&2; exit 64;;
esac
if [[ -n "${MODEL_OVERRIDE}" ]]; then
    MODEL_ID="${MODEL_OVERRIDE}"
    MODEL_NAME="${MODEL_OVERRIDE}（override）"
fi
[[ -n "${REASONING_OVERRIDE}" ]] && REASONING_EFFORT="${REASONING_OVERRIDE}"

# 构造数组，避免工作目录、模型名和 prompt 中的空格/特殊字符被重新分词。
CODEX_COMMON_ARGS=(
    --model "${MODEL_ID}"
    --config "model_reasoning_effort=\"${REASONING_EFFORT}\""
    --config "approval_policy=\"${CODEX_APPROVAL_POLICY}\""
    --config "sandbox_mode=\"${CODEX_SANDBOX_MODE}\""
)

echo "============================================================"
echo "  Codex: ${MODEL_NAME} | reasoning=${REASONING_EFFORT}"
echo "  log: ${LOG_FILE}"
if [[ "${CODEX_LAUNCHER_VARIANT:-main}" == snsc ]]; then
    echo "  launcher: snsc/HPC"
fi
if (( DRIVE_MODE )); then
    echo "  drive mode: ON | interval=${DRIVE_INTERVAL}s | prompt + 继续"
else
    echo "  mode: TUI interactive"
fi
echo "  sandbox: ${CODEX_SANDBOX_MODE} | approval: ${CODEX_APPROVAL_POLICY}"
echo "============================================================"

# JSONL 活动监视器：Codex exec 的事件写入 LOG_FILE，筛出工具、权限、错误和最终消息。
_LIVE_PID=""
_codex_event_text() {
    command -v python3 >/dev/null 2>&1 || return 0
    python3 -c 'import json,sys; x=json.loads(sys.stdin.read()); i=x.get("item",{}); t=i.get("text",""); print(t if isinstance(t,str) else "")' <<<"${1}" 2>/dev/null
}
_live_log() {
    local -a _tail_args
    if tail --version 2>/dev/null | head -1 | grep -q GNU; then
        _tail_args=(-s 0.2 "--pid=$$")
    else
        _tail_args=(-s 0.2)
    fi
    (
        tail "${_tail_args[@]}" -n 0 -F "${LOG_FILE}" 2>/dev/null |
        while IFS= read -r _lt; do
            _now="$(date +%H:%M:%S)"
            if [[ "${_lt}" == *'"type":"item.completed"'* || "${_lt}" == *'"type": "item.completed"'* ]] &&
               [[ "${_lt}" == *'agent_message'* ]]; then
                _msg="$(_codex_event_text "${_lt}" | tr '\n' ' ' | cut -c1-180)"
                [[ -n "${_msg}" ]] && printf '[%s] [AGENT] %s\n' "${_now}" "${_msg}"
                continue
            fi
            if [[ "${_lt}" == *'item.started'* || "${_lt}" == *'item.completed'* ]] &&
               [[ "${_lt}" == *'command_execution'* || "${_lt}" == *'mcp_tool_call'* || "${_lt}" == *'file_change'* ]]; then
                printf '[%s] [INFO] codex tool event\n' "${_now}"
                continue
            fi
            if [[ "${_lt}" == *'approval'* || "${_lt}" == *'permission'* || "${_lt}" == *'exec_approval'* ]]; then
                printf '[%s] [WARN] %s\n' "${_now}" "$(printf '%s' "${_lt}" | cut -c1-180)"
                continue
            fi
            if [[ "${_lt}" == *'turn.failed'* || "${_lt}" == *'"type":"error"'* || "${_lt}" == *'"type": "error"'* || "${_lt}" == *' ERROR '* ]]; then
                printf '[%s] [ERROR] %s\n' "${_now}" "$(printf '%s' "${_lt}" | cut -c1-180)"
            fi
        done
    ) &
    _LIVE_PID=$!
}

# 从 Codex JSONL 的 thread.started 事件提取会话 ID。
_extract_thread_id() {
    local _log="$1"
    if command -v python3 >/dev/null 2>&1; then
        python3 - "${_log}" <<'PY'
import json, re, sys
path = sys.argv[1]
try:
    with open(path, encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                event = json.loads(line)
            except Exception:
                event = None
            if isinstance(event, dict) and event.get("type") == "thread.started":
                thread_id = event.get("thread_id")
                if thread_id:
                    print(thread_id)
                    break
            match = re.search(r'"thread_id"\s*:\s*"([^"]+)"', line)
            if match:
                print(match.group(1))
                break
except OSError:
    pass
PY
        return 0
    fi
    grep -m1 -o '"thread_id"[[:space:]]*:[[:space:]]*"[^"]*"' "${_log}" 2>/dev/null |
        sed 's/.*"thread_id"[[:space:]]*:[[:space:]]*"//; s/"$//'
}

_cleanup() {
    [[ -n "${_LIVE_PID:-}" ]] && kill "${_LIVE_PID}" 2>/dev/null
}
trap '_cleanup' EXIT

if (( ! DRIVE_MODE )); then
    # 普通模式：保持 Codex TUI；只给模型旗标时不进入 exec 链。
    "${_CODEX_BIN}" "${CODEX_COMMON_ARGS[@]}" -- "${PROMPT}" 2>"${LOG_FILE}"
    _run_rc=$?
else
    # ---- 驱动模式：headless codex exec → exec resume 链式驱动 ----
    # 回合1 prompt → thread.started → 每 N 秒发送固定的「继续」。
    _live_log
    echo "---- drive: prompt round start $(date "+%F-%T") ----"
    if "${_CODEX_BIN}" exec "${CODEX_COMMON_ARGS[@]}" --json -- "${PROMPT}" >>"${LOG_FILE}" 2>&1; then
        _drv_rc=0
    else
        _drv_rc=$?
    fi
    if (( _drv_rc != 0 )); then
        echo "###${_NAME}: ERROR: prompt 回合失败（退出码 ${_drv_rc}），驱动终止###" >&2
        exit "${_drv_rc}"
    fi
    _drv_sid="$(_extract_thread_id "${LOG_FILE}")"
    if [[ -z "${_drv_sid}" ]]; then
        echo "###${_NAME}: ERROR: 无法从 ${LOG_FILE} 提取 thread_id，驱动终止###" >&2
        exit 1
    fi
    echo "---- drive: thread=${_drv_sid} interval=${DRIVE_INTERVAL}s ----"
    echo "---- drive: prompt 已完成，进入继续循环 ----"
    _nudges=0
    _fails=0
    while :; do
        sleep "${DRIVE_INTERVAL}"
        if "${_CODEX_BIN}" exec resume "${CODEX_COMMON_ARGS[@]}" --json "${_drv_sid}" -- "继续" >>"${LOG_FILE}" 2>&1; then
            _nudges=$((_nudges + 1))
            _fails=0
            echo "---- drive: 继续 #${_nudges} ok $(date "+%F-%T") ----"
        else
            _drv_rc=$?
            _fails=$((_fails + 1))
            echo "###${_NAME}: warning: 继续发送失败 ${_fails}/3（退出码 ${_drv_rc}）###" >&2
            if (( _fails >= 3 )); then
                echo "###${_NAME}: ERROR: 连续 3 次「继续」失败，驱动循环终止（累计成功 ${_nudges} 次）###" >&2
                break
            fi
        fi
    done
    unset _drv_sid _drv_rc _nudges _fails
fi

echo "logs -> ${LOG_FILE}"
unset PROMPT _PWD
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
exit "${_run_rc:-0}"
