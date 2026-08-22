#!/usr/bin/env bash
# Launch opencode: Build agent + auto + 可选模型 (-h/-p/-f/-q/-k/-g/-m, 默认 -f) + debug logs
# 自动收集工作目录（向上查找）的 AGENTS.md 与 .opencode，注入 prompt

# 脚本目录定位：unix-op.out 经 OPENCODE_SCRIPT_DIR 注入真实目录
# （/dev/fd/3 模式下 BASH_SOURCE 指向 /dev/fd/3，dirname 失效）；
# 直接运行/符号链接运行时 BASH_SOURCE 正常，环境变量缺失则回退。
_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ -n "${OPENCODE_SCRIPT_DIR:-}" ]]; then
    _PATH="${OPENCODE_SCRIPT_DIR}"
else
    if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

# 增强鲁棒性：cwd 失效（如所在目录已被删除）时回退到脚本目录，
# 避免后续 pwd 与相对路径文件（日志/清单/重定向）创建失败
if ! _PWD="$(pwd 2>/dev/null)"; then
    echo "###${_NAME}: warning: 当前目录不可用（getcwd 失败），回退到 ${_PATH}###" >&2
    cd "${_PATH}" || exit 1
    _PWD="$(pwd)"
fi

_TS="$(date +%Y-%m-%d-%H-%M-%S)"
LOG_FILE=".agent.${_TS}.log"
LIST_FILE=".agent.${_TS}.list"
unset _TS

# prompt 单一来源：同目录 oopencode-prompt.txt（模板含 ${HOME}/${_PWD}/${LIST_FILE} 占位符）
# 占位符按运行时值替换；文件缺失时给出明确报错并退出（防静默用空 prompt）
PROMPT_FILE="${_PATH}/oopencode-prompt.txt"
if [[ ! -r "${PROMPT_FILE}" ]]; then
    echo "###${_NAME}: ERROR: ${PROMPT_FILE} 不存在或不可读（prompt 单一来源缺失）###" >&2
    exit 1
fi
PROMPT="$(<"${PROMPT_FILE}")"
PROMPT="${PROMPT//\$\{HOME\}/$HOME}"
PROMPT="${PROMPT//\$\{_PWD\}/$_PWD}"
PROMPT="${PROMPT//\$\{LIST_FILE\}/$LIST_FILE}"
unset PROMPT_FILE

# 自动收集工作目录项目上下文：从 pwd 向上查找 AGENTS.md 与 .opencode，注入 prompt
PROJECT_CONTEXT=""
project_root=""
_ctx_dir="${_PWD}"
while :; do
    if [[ -f "${_ctx_dir}/AGENTS.md" || -d "${_ctx_dir}/.opencode" ]]; then
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
    PROJECT_CONTEXT=$'\n\n\n### 工作目录项目上下文（由 oopencode.sh 自动注入） ###'
    if [[ -f "${project_root}/AGENTS.md" ]]; then
        PROJECT_CONTEXT+=$'\n\n===== AGENTS.md ('"${project_root}"'/AGENTS.md) =====\n'
        _n_lines="$(wc -l < "${project_root}/AGENTS.md")"
        if (( _n_lines > 400 )); then
            PROJECT_CONTEXT+="$(head -400 "${project_root}/AGENTS.md")"
            PROJECT_CONTEXT+=$'\n\n...（AGENTS.md 共 '"${_n_lines}"$' 行，已截断；完整内容请自行读取 '"${project_root}"$'/AGENTS.md）'
        else
            PROJECT_CONTEXT+="$(<"${project_root}/AGENTS.md")"
        fi
        unset _n_lines
    fi
    if [[ -d "${project_root}/.opencode" ]]; then
        PROJECT_CONTEXT+=$'\n\n===== .opencode 目录结构 ('"${project_root}"'/.opencode) =====\n'
        PROJECT_CONTEXT+="$(cd "${project_root}/.opencode" && find . -maxdepth 2 -mindepth 1 ! -path './node_modules*' ! -path './.git*' | sort)"
    fi
    PROMPT="${PROMPT}${PROJECT_CONTEXT}"
fi
unset PROJECT_CONTEXT

# ---- 参数解析：模型旗标 + 无人值守驱动选项 ----
# 用法: ${_NAME} [-m|-o|-p|-q|-k|-g|-f|-h] [-file PATH] [-time DUR]
#   -file/--file PATH : 驱动模式——prompt 回合完成后以文件内容为第一条指令，
#                       之后每 --time 间隔向同一会话发送「继续」，直至 Ctrl+C 或连续 3 次失败
#   -time/--time DUR  : 「继续」发送间隔，纯数字=秒；支持 s/m/h 后缀（如 30s/5m/2h），默认 30s
# 仅给模型旗标时保持原有 TUI 交互模式不变
MODEL_FLAG="-f"
DRIVE_FILE=""
DRIVE_INTERVAL=""
DRIVE_MODE=0
while (( $# )); do
    case "$1" in
        -m|-o|-p|-q|-k|-g|-f|-h) MODEL_FLAG="$1"; shift;;
        -file|--file)
            if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少路径参数###" >&2; exit 64; fi
            DRIVE_FILE="$2"; DRIVE_MODE=1; shift 2;;
        -time|--time)
            if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少时长参数###" >&2; exit 64; fi
            _ti_raw="$2"; DRIVE_MODE=1; shift 2;;
        *) echo "###${_NAME}: ERROR: 未知参数 '$1'（用法: ${_NAME} [-m|-o|-p|-q|-k|-g|-f|-h] [-file PATH] [-time 30s]）###" >&2; exit 64;;
    esac
done

# 时长解析："30"→30 秒；支持 s/m/h 后缀（30s/5m/2h）
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

# 模型选择：默认 -f DeepSeek V4 Flash；-o Ox Alpha Free (Unlimited) / -h Hy3 (high) / -p Pro / -q Qwen3.8 Max / -k Kimi K3 / -g GPT-5.6 Luna / -m Build auto·Muse Spark 1.2 Contributor OpenCode Go (xhigh)
VARIANT="max"
case "${MODEL_FLAG}" in
    -m) MODEL_ID="opencode-go/muse-spark-1.2";   MODEL_NAME="Build auto·Muse Spark 1.2 Contributor OpenCode Go"; VARIANT="xhigh";;
    -o) MODEL_ID="opencode-go/ox-alpha-free";    MODEL_NAME="Build auto · Ox Alpha Free (Unlimited) OpenCode Go";;
    -p) MODEL_ID="opencode-go/deepseek-v4-pro";  MODEL_NAME="DeepSeek V4 Pro (New)";;
    -q) MODEL_ID="opencode-go/qwen3.8-max";      MODEL_NAME="Qwen3.8 Max";;
    -k) MODEL_ID="opencode-go/kimi-k3";          MODEL_NAME="Kimi K3";;
    -g) MODEL_ID="opencode-go/gpt-5.6-luna";     MODEL_NAME="GPT-5.6 Luna (2x usage)";;
    -f) MODEL_ID="opencode-go/deepseek-v4-flash"; MODEL_NAME="DeepSeek V4 Flash (2x usage)";;
    -h) MODEL_ID="opencode-go/hy3";              MODEL_NAME="Hy3"; VARIANT="high";;
esac

export OPENCODE_CONFIG_CONTENT='{"lsp":true,"agent":{"build":{"model":"'"${MODEL_ID}"'","variant":"'"${VARIANT}"'"}}}'

echo "============================================================"
echo "  OpenCode: build | auto | ${MODEL_NAME} (${VARIANT})"
echo "  log: ${LOG_FILE}"
echo "  user-input list: ${LIST_FILE}"
if [[ -n "${project_root}" ]]; then
    echo "  project context: ${project_root}（AGENTS.md 与 .opencode 已注入 prompt）"
else
    echo "  project context: 未发现 AGENTS.md / .opencode（仅使用固定 prompt）"
fi
if (( DRIVE_MODE )); then
    echo "  drive mode: ON | interval=${DRIVE_INTERVAL}s | first-instruction=${DRIVE_FILE:-<无，仅继续循环>}"
else
    echo "  mode: TUI interactive"
fi
echo "============================================================"

# 实时活动监视器：opencode run 的文本/事件在回合完成时批量到达，
# 唯一实时流是 DEBUG 日志——tail -F 跟踪其新写入的关键活动行（工具调用/权限/错误），
# 以 [HH:MM:SS] [LEVEL] 紧凑行实时输出到终端（GNU tail 用 -s 0.2 近实时；BSD 回退默认 -F）
_LIVE_PID=""
_tail_args()
{
    local _iu
    if tail --version 2>/dev/null | head -1 | grep -q GNU; then
        _iu="-s 0.2 --pid=$$"
    else
        _iu="-s 0.2"
    fi
    printf '%s\n' "${_iu}"
}
_live_log() {
    local _iu; _iu="$(_tail_args)"
    ( tail ${_iu} -n 0 -F "${LOG_FILE}" 2>/dev/null | \
      while IFS= read -r _lt; do
          case "${_lt}" in *level=ERROR*|*level=WARN*|*' tool '*|*permission=*) ;; *) continue ;; esac
          printf '[%s] %s\n' "$(date +%H:%M:%S)" \
                 "$(sed -E 's/timestamp=[^ ]+ level=([A-Z]+) run=[^ ]+ message=/[\1] /; s/"//g' <<<"${_lt}" | cut -c1-140)"
      done ) &
    _LIVE_PID=$!
}

# 兜底防丢失：trap EXIT（任何退出路径均触发）——从 LOG_FILE 提取 session.id，export 会话 JSON，
# python3 提取 user 消息文本（跳过系统注入提示词），与 LIST_FILE 比对后追加补录缺失的用户输入
_recover_inputs() {
    local _rec_sid _rec_jf
    _rec_sid="$(grep -o 'session.id=[A-Za-z0-9_-]*' "${LOG_FILE}" 2>/dev/null | head -1 | cut -d= -f2)"
    [[ -n "${_rec_sid}" ]] || return 0
    command -v opencode >/dev/null 2>&1 || return 0
    command -v python3  >/dev/null 2>&1 || return 0
    _rec_jf="/tmp/opencode/${LIST_FILE}.export.json"
    if opencode export "${_rec_sid}" 2>/dev/null > "${_rec_jf}"; then
        python3 - "${_rec_jf}" "${LIST_FILE}" <<'PYEOF'
import json, sys, datetime
exp, lst = sys.argv[1], sys.argv[2]
try:
    with open(exp) as f:
        d = json.load(f)
except Exception:
    sys.exit(0)
users = []
for m in d.get('messages', []):
    if m.get('info', {}).get('role') != 'user':
        continue
    for p in m.get('parts', []):
        if p.get('type') == 'text':
            t = p.get('text', '')
            if t and '【用户输入记录】' not in t:
                users.append(t)
try:
    with open(lst) as f:
        content = f.read()
except FileNotFoundError:
    content = ''
recs = [t for t in users if t not in content]
if recs:
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(lst, 'a') as f:
        for t in recs:
            f.write(f'---- [{ts}] 兜底补录 ----\n{t}\n')
    print(f"  recover: 兜底补录 {len(recs)} 条缺失用户输入 -> {lst}")
PYEOF
    fi
    rm -f "${_rec_jf}"
}
_cleanup() {
    _recover_inputs
    [[ -n "${_LIVE_PID:-}" ]] && kill "${_LIVE_PID}" 2>/dev/null
}
trap '_cleanup' EXIT
unset _rec_sid _rec_jf

# mkdir -p /public/home/zhangxin/.vscode-server./cli/servers/Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/server/node/Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/server/out/debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/result_debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/
# cp /public/home/zhangxin/.opencode/bin/opencode /public/home/zhangxin/.vscode-server./cli/servers/Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/server/node/Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/server/out/debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/result_debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/output_result_debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713
_BIN=/public/home/zhangxin/.vscode-server./cli/servers/Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/server/node/Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/server/out/debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/result_debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/output_result_debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713

if (( ! DRIVE_MODE )); then
    # 原有 TUI 交互模式（无 -file/-time 时行为完全不变）
    "${_BIN}" --agent build --auto --prompt "${PROMPT}" \
            --print-logs --log-level DEBUG \
            2> "${LOG_FILE}"
else
    # ---- 驱动模式：headless opencode run 链式驱动 ----
    # 回合1 prompt → 从日志提取 session.id →（可选）回合2 文件首指令 → 每 N 秒「继续」
    if [[ -n "${DRIVE_FILE}" && ! -r "${DRIVE_FILE}" ]]; then
        echo "###${_NAME}: ERROR: --file '${DRIVE_FILE}' 不存在或不可读###" >&2
        exit 66
    fi
    _live_log
    echo "---- drive: prompt round start $(date "+%F-%T") ----"
    "${_BIN}" run --agent build --auto --print-logs --log-level DEBUG "${PROMPT}" \
            2> "${LOG_FILE}"
    _drv_rc=$?
    if (( _drv_rc != 0 )); then
        echo "###${_NAME}: ERROR: prompt 回合失败（退出码 ${_drv_rc}），驱动终止###" >&2
        exit "${_drv_rc}"
    fi
    _drv_sid="$(grep -o 'session.id=[A-Za-z0-9_-]*' "${LOG_FILE}" 2>/dev/null | head -1 | cut -d= -f2)"
    if [[ -z "${_drv_sid}" ]]; then
        echo "###${_NAME}: ERROR: 无法从 ${LOG_FILE} 提取 session.id，驱动终止###" >&2
        exit 1
    fi
    echo "---- drive: session=${_drv_sid} interval=${DRIVE_INTERVAL}s ----"
    if [[ -n "${DRIVE_FILE}" ]]; then
        _drv_instr="$(<"${DRIVE_FILE}")"
        echo "---- drive: first instruction <- ${DRIVE_FILE}（$(wc -c < "${DRIVE_FILE}") 字节）$(date "+%F-%T") ----"
        "${_BIN}" run -s "${_drv_sid}" --agent build --auto --print-logs --log-level DEBUG "${_drv_instr}" \
                2>> "${LOG_FILE}"
        _drv_rc=$?
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
        if "${_BIN}" run -s "${_drv_sid}" --agent build --auto --print-logs --log-level DEBUG "继续" \
                2>> "${LOG_FILE}"; then
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
    unset _BIN _drv_sid _drv_rc _nudges _fails
fi

if [[ -s "${LIST_FILE}" ]]; then
    echo "user inputs -> ${LIST_FILE}（$(wc -l < "${LIST_FILE}") 行）"
elif [[ -f "${LIST_FILE}" ]]; then
    echo "user inputs -> ${LIST_FILE}（空）"
fi
echo "logs -> ${LOG_FILE}"
unset _PWD
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
