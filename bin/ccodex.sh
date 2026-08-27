#!/usr/bin/env bash
# Launch Codex: Full Access + 自动批准 + 可选模型/推理强度（默认 -m）
# 支持普通 TUI，以及与 op 系列兼容的 -file/-time 无人值守驱动模式。

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
# 避免后续 pwd 与相对路径文件（日志/清单/重定向）创建失败。
if ! _PWD="$(pwd 2>/dev/null)"; then
    echo "###${_NAME}: warning: 当前目录不可用（getcwd 失败），回退到 ${_PATH}###" >&2
    cd "${_PATH}" || exit 1
    _PWD="$(pwd)"
fi

_TS="$(date +%Y-%m-%d-%H-%M-%S)"
LOG_FILE=".agent.${_TS}.log"
LIST_FILE=".agent.${_TS}.list"
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

# prompt 单一来源：Codex 专用模板，运行时替换 ${HOME}/${_PWD}/${LIST_FILE}。
PROMPT_FILE="${_PATH}/ccodex-prompt.txt"
if [[ ! -r "${PROMPT_FILE}" ]]; then
    echo "###${_NAME}: ERROR: ${PROMPT_FILE} 不存在或不可读（prompt 单一来源缺失）###" >&2
    exit 1
fi
PROMPT="$(<"${PROMPT_FILE}")"
PROMPT="${PROMPT//\$\{HOME\}/${HOME:-}}"
PROMPT="${PROMPT//\$\{_PWD\}/${_PWD}}"
PROMPT="${PROMPT//\$\{LIST_FILE\}/${LIST_FILE}}"
unset PROMPT_FILE

# 自动收集工作目录项目上下文：从 pwd 向上查找 AGENTS.md 与 .codex，注入 prompt。
PROJECT_CONTEXT=""
project_root=""
_ctx_dir="${_PWD}"
while :; do
    if [[ -f "${_ctx_dir}/AGENTS.md" || -d "${_ctx_dir}/.codex" ]]; then
        project_root="${_ctx_dir}"
        break
    fi
    _parent="${_ctx_dir%/*}"
    [ -z "${_parent}" ] && _parent="/"
    [[ "${_parent}" == "${_ctx_dir}" ]] && break
    _ctx_dir="${_parent}"
done
unset _ctx_dir _parent

if [[ -n "${project_root}" ]]; then
    PROJECT_CONTEXT=$'\n\n\n### 工作目录项目上下文（由 ccodex.sh 自动注入） ###'
    if [[ -f "${project_root}/AGENTS.md" ]]; then
        PROJECT_CONTEXT+=$'\n\n===== AGENTS.md ('"${project_root}"$'/AGENTS.md) =====\n'
        _n_lines="$(wc -l < "${project_root}/AGENTS.md")"
        if (( _n_lines > 400 )); then
            PROJECT_CONTEXT+="$(head -400 "${project_root}/AGENTS.md")"
            PROJECT_CONTEXT+=$'\n\n...（AGENTS.md 共 '"${_n_lines}"$' 行，已截断；完整内容请自行读取 '"${project_root}"$'/AGENTS.md）'
        else
            PROJECT_CONTEXT+="$(<"${project_root}/AGENTS.md")"
        fi
        unset _n_lines
    fi
    if [[ -d "${project_root}/.codex" ]]; then
        PROJECT_CONTEXT+=$'\n\n===== .codex 目录结构 ('"${project_root}"$'/.codex) =====\n'
        PROJECT_CONTEXT+="$(cd "${project_root}/.codex" && find . -maxdepth 2 -mindepth 1 ! -path './node_modules*' ! -path './.git*' | sort)"
    fi
    PROMPT="${PROMPT}${PROJECT_CONTEXT}"
fi
unset PROJECT_CONTEXT

# ---- 参数解析：模型旗标 + 无人值守驱动选项 ----
# 用法: ${_NAME} [-m|-o|-p|-q|-k|-g|-f|-h] [--model MODEL]
#                       [-file PATH] [-time DUR]
#   -file/--file PATH : 驱动模式——prompt 回合完成后以文件内容为第一条指令，
#                       之后每 --time 间隔向同一会话发送「继续」，直至 Ctrl+C 或连续 3 次失败。
#   -time/--time DUR  : 「继续」发送间隔，纯数字=秒；支持 s/m/h 后缀（默认 30s）。
#   --model MODEL     : 直接指定 Codex 模型，覆盖模型旗标；也可用 CODEX_MODEL 环境变量覆盖。
#   --reasoning-effort LEVEL : 直接指定 reasoning effort（low/medium/high/xhigh/max/ultra）。
MODEL_FLAG="${CODEX_DEFAULT_MODEL_FLAG:--m}"
MODEL_OVERRIDE="${CODEX_MODEL:-}"
REASONING_OVERRIDE="${CODEX_REASONING_EFFORT:-}"
CODEX_SANDBOX_MODE="${CODEX_SANDBOX:-danger-full-access}"
CODEX_APPROVAL_POLICY="${CODEX_APPROVAL:-never}"
DRIVE_FILE=""
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
        -file|--file)
            if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少路径参数###" >&2; exit 64; fi
            DRIVE_FILE="$2"; DRIVE_MODE=1; shift 2;;
        -time|--time)
            if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少时长参数###" >&2; exit 64; fi
            _ti_raw="$2"; DRIVE_MODE=1; shift 2;;
        --help)
            echo "用法: ${_NAME} [-m|-o|-p|-q|-k|-g|-f|-h] [--model MODEL] [--reasoning-effort LEVEL] [-file PATH] [-time DUR]"
            echo "默认模型: ${MODEL_FLAG}；只给模型旗标时进入 Codex TUI，给出 -file 或 -time 时进入 exec 驱动模式。"
            exit 0;;
        *) echo "###${_NAME}: ERROR: 未知参数 '$1'（用法: ${_NAME} [-m|-o|-p|-q|-k|-g|-f|-h] [--model MODEL] [-file PATH] [-time 30s]）###" >&2; exit 64;;
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
echo "  user-input list: ${LIST_FILE}"
if [[ "${CODEX_LAUNCHER_VARIANT:-main}" == snsc ]]; then
    echo "  launcher: snsc/HPC"
fi
if [[ -n "${project_root}" ]]; then
    echo "  project context: ${project_root}（AGENTS.md 与 .codex 已注入 prompt）"
else
    echo "  project context: 未发现 AGENTS.md / .codex（仅使用固定 prompt）"
fi
if (( DRIVE_MODE )); then
    echo "  drive mode: ON | interval=${DRIVE_INTERVAL}s | first-instruction=${DRIVE_FILE:-<无，仅继续循环>}"
else
    echo "  mode: TUI interactive"
fi
echo "  sandbox: ${CODEX_SANDBOX_MODE} | approval: ${CODEX_APPROVAL_POLICY}"
echo "============================================================"

# 记录驱动器注入的用户消息。Codex 没有可供脚本调用的会话导出接口，
# 因而文件指令/继续消息由包装器记录；TUI 中直接输入的消息仍由 prompt 中的约定记录。
_record_input() {
    local _content="${1-}" _n
    [[ -n "${_content}" ]] || return 0
    if [[ -f "${LIST_FILE}" ]] && grep -F -q -- "${_content}" "${LIST_FILE}" 2>/dev/null; then
        return 0
    fi
    _n=1
    if [[ -f "${LIST_FILE}" ]]; then
        _n=$(( $(grep -c '^---- \[' "${LIST_FILE}" 2>/dev/null || true) + 1 ))
    fi
    if ! printf '%s\n' "---- [$(date "+%Y-%m-%d %H:%M:%S")] 第 ${_n} 条用户输入 ----" >> "${LIST_FILE}" ||
       ! printf '%s\n' "${_content}" >> "${LIST_FILE}"; then
        echo "###${_NAME}: ERROR: 无法写入用户输入清单 ${LIST_FILE}###" >&2
        return 1
    fi
}

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
    # 回合1 prompt → thread.started →（可选）文件首指令 → 每 N 秒「继续」。
    if [[ -n "${DRIVE_FILE}" && ! -r "${DRIVE_FILE}" ]]; then
        echo "###${_NAME}: ERROR: --file '${DRIVE_FILE}' 不存在或不可读###" >&2
        exit 66
    fi
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
    if [[ -n "${DRIVE_FILE}" ]]; then
        _drv_instr="$(<"${DRIVE_FILE}")"
        if ! _record_input "${_drv_instr}"; then exit 1; fi
        echo "---- drive: first instruction <- ${DRIVE_FILE}（$(wc -c < "${DRIVE_FILE}") 字节）$(date "+%F-%T") ----"
        if "${_CODEX_BIN}" exec resume "${CODEX_COMMON_ARGS[@]}" --json "${_drv_sid}" -- "${_drv_instr}" >>"${LOG_FILE}" 2>&1; then
            _drv_rc=0
        else
            _drv_rc=$?
        fi
        if (( _drv_rc != 0 )); then
            echo "###${_NAME}: warning: 首条指令回合退出码 ${_drv_rc}，仍进入继续循环###" >&2
        fi
        unset _drv_instr
    else
        echo "---- drive: 未提供 -file，跳过首条指令直接进入继续循环 ----"
    fi
    _nudges=0
    _fails=0
    while :; do
        sleep "${DRIVE_INTERVAL}"
        if ! _record_input "继续"; then exit 1; fi
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

if [[ -s "${LIST_FILE}" ]]; then
    echo "user inputs -> ${LIST_FILE}（$(wc -l < "${LIST_FILE}") 行）"
elif [[ -f "${LIST_FILE}" ]]; then
    echo "user inputs -> ${LIST_FILE}（空）"
fi
echo "logs -> ${LOG_FILE}"
unset PROMPT _PWD
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
exit "${_run_rc:-0}"
