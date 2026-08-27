#!/usr/bin/env bash
# 统一 agent 启动器：cl/op/co/ops/cos 软链接分发（cpupower.sh 模式，按 $_NAME 区分）
#   cl  → Claude Code（TUI：--permission-mode auto；驱动：claude -p → --resume 链）
#   op  → OpenCode（build agent：TUI；驱动：run -s 链）
#   co  → Codex（TUI；驱动：exec → exec resume 链）
#   ops → OpenCode HPC/snsc 入口（默认 OPENCODE_BIN 指向 vscode-server 内部署路径）
#   cos → Codex HPC/snsc 入口
# prompt 单一来源：同目录 agent-prompt.txt（模板含 ${HOME}/${_PWD} 占位符；op 另支持 ${LIST_FILE}）

# ---- 脚本定位：AGENT_SCRIPT_DIR 可在 /dev/fd/3 等场景注入真实目录；缺失时回退 BASH_SOURCE ----
_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ -n "${AGENT_SCRIPT_DIR:-}" ]]; then
    _PATH="${AGENT_SCRIPT_DIR}"
else
    if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
fi
_NAME=${AGENT_LAUNCHER_NAME:-${_SRC##*/}}
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
unset _TS

# ---- 公共工具 ----
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

# prompt 基础读取：agent-prompt.txt 单一来源，替换 ${HOME}/${_PWD} 占位符；
# 文件缺失时给出明确报错并退出（防静默用空 prompt）。成功后 PROMPT 就绪。
_load_prompt() {
    local _pf="${_PATH}/agent-prompt.txt"
    if [[ ! -r "${_pf}" ]]; then
        echo "###${_NAME}: ERROR: ${_pf} 不存在或不可读（prompt 单一来源缺失）###" >&2
        exit 1
    fi
    PROMPT="$(<"${_pf}")"
    PROMPT="${PROMPT//\$\{HOME\}/${HOME:-}}"
    PROMPT="${PROMPT//\$\{_PWD\}/$_PWD}"
}

# 全局 agent 配置目录清单注入（co/cl 共用）：只列路径，不读取内容
_append_agent_config_dirs() {
    local _title="$1" _agent_dir
    shift
    PROMPT+=$'\n\n### '"${_title}"$' ###\n'
    for _agent_dir in "$@"; do
        if [[ -d "${_agent_dir}" ]]; then
            PROMPT+="${_agent_dir}"$'\n'
        else
            PROMPT+="（未找到 ${_agent_dir}）"$'\n'
        fi
    done
}

# 全局/工作区 SKILL.md 路径清单注入（co/cl 共用）：只列路径；去重
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

# 实时监视器清理（公共）：驱动模式下各分支启动 _live_log 并写入 _LIVE_PID；
# op 分支另有用户输入兜底补录（_recover_inputs，仅 op 分支定义）
_LIVE_PID=""
_cleanup() {
    if [[ "${_AGENT:-}" == opencode ]] && declare -F _recover_inputs >/dev/null 2>&1; then
        _recover_inputs
    fi
    [[ -n "${_LIVE_PID:-}" ]] && kill "${_LIVE_PID}" 2>/dev/null
}
trap '_cleanup' EXIT

# =====================================================================
# Claude Code 分支（cl）：TUI 或 -p/--resume 驱动链；模型旗标与 op/co 一致
# =====================================================================
run_claude() {
    local _CLAUDE_BIN="${CLAUDE_BIN:-}"
    if [[ -z "${_CLAUDE_BIN}" ]]; then
        _CLAUDE_BIN="$(command -v claude 2>/dev/null || true)"
    fi
    if [[ -z "${_CLAUDE_BIN}" ]]; then
        echo "###${_NAME}: ERROR: 未找到 claude，请安装 Claude Code 或设置 CLAUDE_BIN###" >&2
        exit 127
    fi

    _load_prompt
    # 与 co 相同的注入：全局 agent 配置目录 + skill 清单
    local _configure_agent_root="${HOME:-}/configure" _git_root _workspace_root
    local -a _agent_config_dirs _workspace_skill_roots
    local -A _SEEN_SKILL_PATHS=()
    _agent_config_dirs=(
        "${_configure_agent_root}/skills"
        "${_configure_agent_root}/tools"
        "${_configure_agent_root}/hooks"
        "${_configure_agent_root}/plugins"
    )
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
    _append_agent_config_dirs "全局 Agent 配置目录（按需读取）" "${_agent_config_dirs[@]}"
    _append_skill_list "全局技能（${_agent_config_dirs[0]}）" "${_agent_config_dirs[0]}"
    _append_skill_list "当前工作目录技能（${_PWD}）" "${_workspace_skill_roots[@]}"
    unset _git_root _workspace_root _workspace_skill_roots

    # ---- 参数解析：模型旗标 + 无人值守驱动选项 ----
    # 用法: ${_NAME} [-m|-o|-p|-q|-k|-g|-f|-h] [--model MODEL] [-file PATH] [-time DUR]
    #   --model MODEL     : 直接指定模型 ID，覆盖模型旗标；也可用 CLAUDE_MODEL 环境变量覆盖。
    #   -file/--file PATH : 驱动模式——prompt 回合完成后以文件内容为第一条指令，
    #                       之后每 --time 间隔向同一会话发送「继续」，直至 Ctrl+C 或连续 3 次失败
    #   -time/--time DUR  : 「继续」发送间隔，纯数字=秒；支持 s/m/h 后缀（如 30s/5m/2h），默认 30s
    # 仅给模型旗标时保持原有 TUI 交互模式不变
    local MODEL_FLAG="${CLAUDE_DEFAULT_MODEL_FLAG:--m}"
    local MODEL_OVERRIDE="${CLAUDE_MODEL:-}"
    local MODEL_ID MODEL_NAME DRIVE_FILE="" DRIVE_INTERVAL="" DRIVE_MODE=0
    while (( $# )); do
        case "$1" in
            -m|-o|-p|-q|-k|-g|-f|-h) MODEL_FLAG="$1"; shift;;
            --model)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少模型参数###" >&2; exit 64; fi
                MODEL_OVERRIDE="$2"; shift 2;;
            --help)
                echo "用法: ${_NAME} [-m|-o|-p|-q|-k|-g|-f|-h] [--model MODEL] [-file PATH] [-time DUR]"
                echo "默认模型: ${MODEL_FLAG}；只给模型旗标时进入 Claude TUI，给出 -file/-time 时进入驱动模式。"
                echo "模型默认 slug 可用 CLAUDE_MODEL_M/O/P/Q/K/G/F/H 环境变量覆盖。"
                exit 0;;
            -file|--file)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少路径参数###" >&2; exit 64; fi
                DRIVE_FILE="$2"; DRIVE_MODE=1; shift 2;;
            -time|--time)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少时长参数###" >&2; exit 64; fi
                _ti_raw="$2"; DRIVE_MODE=1; shift 2;;
            *) echo "###${_NAME}: ERROR: 未知参数 '$1'（用法: ${_NAME} [-m|-o|-p|-q|-k|-g|-f|-h] [--model MODEL] [-file PATH] [-time 30s]）###" >&2; exit 64;;
        esac
    done
    if [[ -n "${_ti_raw:-}" ]]; then
        if ! DRIVE_INTERVAL="$(_parse_interval "${_ti_raw}")"; then
            echo "###${_NAME}: ERROR: --time '${_ti_raw}' 格式无效（示例: 30 / 30s / 5m / 2h）###" >&2
            exit 64
        fi
    fi
    unset _ti_raw
    [[ -n "${DRIVE_INTERVAL}" ]] || DRIVE_INTERVAL=30

    # 模型选择：-m/-o/-p 侧重深度，-f/-k 侧重速度；默认 slug 可用 CLAUDE_MODEL_* 覆盖，CLAUDE_MODEL/--model 直接覆盖
    case "${MODEL_FLAG}" in
        -m) MODEL_ID="${CLAUDE_MODEL_M:-claude-sonnet-4-5}"; MODEL_NAME="Claude Sonnet 4.5";;
        -o) MODEL_ID="${CLAUDE_MODEL_O:-claude-opus-4-1}"; MODEL_NAME="Claude Opus 4.1";;
        -p) MODEL_ID="${CLAUDE_MODEL_P:-claude-opus-4-1}"; MODEL_NAME="Claude Opus 4.1";;
        -q) MODEL_ID="${CLAUDE_MODEL_Q:-claude-sonnet-4-5}"; MODEL_NAME="Claude Sonnet 4.5";;
        -k) MODEL_ID="${CLAUDE_MODEL_K:-claude-haiku-4-5}"; MODEL_NAME="Claude Haiku 4.5";;
        -g) MODEL_ID="${CLAUDE_MODEL_G:-claude-sonnet-4-5}"; MODEL_NAME="Claude Sonnet 4.5";;
        -f) MODEL_ID="${CLAUDE_MODEL_F:-claude-haiku-4-5}"; MODEL_NAME="Claude Haiku 4.5";;
        -h) MODEL_ID="${CLAUDE_MODEL_H:-claude-sonnet-4-5}"; MODEL_NAME="Claude Sonnet 4.5";;
        *) echo "###${_NAME}: ERROR: 不支持的默认模型旗标 '${MODEL_FLAG}'###" >&2; exit 64;;
    esac
    if [[ -n "${MODEL_OVERRIDE}" ]]; then
        MODEL_ID="${MODEL_OVERRIDE}"
        MODEL_NAME="${MODEL_OVERRIDE}（override）"
    fi

    echo "============================================================"
    echo "  Claude Code: ${MODEL_NAME} | permission-mode auto"
    echo "  log: ${LOG_FILE}"
    if (( _SNSC )); then
        echo "  launcher: snsc/HPC"
    fi
    if (( DRIVE_MODE )); then
        echo "  drive mode: ON | interval=${DRIVE_INTERVAL}s | first-instruction=${DRIVE_FILE:-<无，仅继续循环>}"
    else
        echo "  mode: TUI interactive"
    fi
    echo "============================================================"

    if (( ! DRIVE_MODE )); then
        # 原 TUI 交互模式（--permission-mode auto 原语义保留）
        "${_CLAUDE_BIN}" --permission-mode auto --model "${MODEL_ID}" 2> "${LOG_FILE}"
        return $?
    fi

    # ---- 驱动模式：headless claude -p → --resume 链式驱动 ----
    # 回合1 prompt → 从 stderr 日志提取 session id →（可选）回合2 文件首指令 → 每 N 秒「继续」
    # 实时活动监视器：claude stderr 无结构化事件行，仅筛出关键行（错误/警告/会话）实时输出
    _live_log()
    {
        local _iu
        if tail --version 2>/dev/null | head -1 | grep -q GNU; then
            _iu="-s 0.2 --pid=$$"
        else
            _iu="-s 0.2"
        fi
        ( tail ${_iu} -n 0 -F "${LOG_FILE}" 2>/dev/null | \
          while IFS= read -r _lt; do
              case "${_lt}" in
                  *ERROR*|*error*|*Error*|*WARN*|*warning*|*Warning*|*session*|*Session*) ;;
                  *) continue ;;
              esac
              printf '[%s] %s\n' "$(date +%H:%M:%S)" "$(printf '%s' "${_lt}" | cut -c1-140)"
          done ) &
        _LIVE_PID=$!
    }
    if [[ -n "${DRIVE_FILE}" && ! -r "${DRIVE_FILE}" ]]; then
        echo "###${_NAME}: ERROR: --file '${DRIVE_FILE}' 不存在或不可读###" >&2
        exit 66
    fi
    _live_log
    echo "---- drive: prompt round start $(date "+%F-%T") ----"
    "${_CLAUDE_BIN}" -p --permission-mode auto --model "${MODEL_ID}" "${PROMPT}" 2>> "${LOG_FILE}"
    _drv_rc=$?
    if (( _drv_rc != 0 )); then
        echo "###${_NAME}: ERROR: prompt 回合失败（退出码 ${_drv_rc}），驱动终止###" >&2
        exit "${_drv_rc}"
    fi
    _drv_sid="$(grep -oE 'session_(id|\.id)=[A-Za-z0-9_-]+' "${LOG_FILE}" 2>/dev/null | head -1 | cut -d= -f2)"
    if [[ -z "${_drv_sid}" ]]; then
        echo "###${_NAME}: ERROR: 无法从 ${LOG_FILE} 提取 session id，驱动终止###" >&2
        exit 1
    fi
    echo "---- drive: session=${_drv_sid} interval=${DRIVE_INTERVAL}s ----"
    if [[ -n "${DRIVE_FILE}" ]]; then
        _drv_instr="$(<"${DRIVE_FILE}")"
        echo "---- drive: first instruction <- ${DRIVE_FILE}（$(wc -c < "${DRIVE_FILE}") 字节）$(date "+%F-%T") ----"
        "${_CLAUDE_BIN}" -p --resume "${_drv_sid}" --permission-mode auto --model "${MODEL_ID}" "${_drv_instr}" \
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
        if "${_CLAUDE_BIN}" -p --resume "${_drv_sid}" --permission-mode auto --model "${MODEL_ID}" "继续" \
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
    unset _drv_sid _drv_rc _nudges _fails
    echo "logs -> ${LOG_FILE}"
    return 0
}

# =====================================================================
# OpenCode 分支（op/ops）：TUI 或 run -s 驱动链；自动收集项目上下文注入 prompt
# =====================================================================
run_opencode() {
    local _OPENCODE_BIN="${OPENCODE_BIN:-}"
    if (( _SNSC )) && [[ -z "${_OPENCODE_BIN}" ]]; then
        # snsc 上 opencode 通常手动部署在 vscode-server 目录内（升级后路径会变，请更新或设 OPENCODE_BIN）：
        #   mkdir -p /public/home/zhangxin/.vscode-server./cli/servers/Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/server/node/Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/server/out/debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/result_debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/output_result_debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/
        #   cp /public/home/zhangxin/.opencode/bin/opencode <上路径>/output_result_debug_Stable-.../
        _OPENCODE_BIN="/public/home/zhangxin/.vscode-server./cli/servers/Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/server/node/Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/server/out/debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/result_debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/output_result_debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713"
    fi
    if [[ -z "${_OPENCODE_BIN}" ]]; then
        _OPENCODE_BIN="$(command -v opencode 2>/dev/null || true)"
    fi
    if [[ -z "${_OPENCODE_BIN}" ]]; then
        echo "###${_NAME}: ERROR: 未找到 opencode，请安装 opencode 或设置 OPENCODE_BIN###" >&2
        exit 127
    fi

    _load_prompt
    PROMPT="${PROMPT//\$\{LIST_FILE\}/$LIST_FILE}"

    # 自动收集工作目录项目上下文：从 pwd 向上查找 AGENTS.md 与 .opencode，注入 prompt
    local PROJECT_CONTEXT="" project_root="" _ctx_dir="${_PWD}" _parent
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

    if [[ -n "${project_root}" ]]; then
        PROJECT_CONTEXT=$'\n\n\n### 工作目录项目上下文（由 agent.sh 自动注入） ###'
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
    unset PROJECT_CONTEXT _ctx_dir _parent project_root

    # ---- 参数解析：模型旗标 + 无人值守驱动选项 ----
    # 用法: ${_NAME} [-m|-o|-p|-q|-k|-g|-f|-h] [--model MODEL] [--variant LEVEL] [-file PATH] [-time DUR]
    #   --model MODEL     : 直接指定模型 ID，覆盖模型旗标；也可用 OPENCODE_MODEL 环境变量覆盖。
    #   --variant LEVEL   : 直接指定 build agent 的 variant（max/xhigh/high/low 等）。
    #   -file/--file PATH : 驱动模式——prompt 回合完成后以文件内容为第一条指令，
    #                       之后每 --time 间隔向同一会话发送「继续」，直至 Ctrl+C 或连续 3 次失败
    #   -time/--time DUR  : 「继续」发送间隔，纯数字=秒；支持 s/m/h 后缀（如 30s/5m/2h），默认 30s
    # 仅给模型旗标时保持原有 TUI 交互模式不变
    local MODEL_FLAG="${OPENCODE_DEFAULT_MODEL_FLAG:--f}"
    local MODEL_OVERRIDE="${OPENCODE_MODEL:-}"
    local VARIANT_OVERRIDE="${OPENCODE_VARIANT:-}"
    local MODEL_ID MODEL_NAME VARIANT="max" DRIVE_FILE="" DRIVE_INTERVAL="" DRIVE_MODE=0
    while (( $# )); do
        case "$1" in
            -m|-o|-p|-q|-k|-g|-f|-h) MODEL_FLAG="$1"; shift;;
            --model)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少模型参数###" >&2; exit 64; fi
                MODEL_OVERRIDE="$2"; shift 2;;
            --variant)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少等级参数###" >&2; exit 64; fi
                VARIANT_OVERRIDE="$2"; shift 2;;
            --help)
                echo "用法: ${_NAME} [-m|-o|-p|-q|-k|-g|-f|-h] [--model MODEL] [--variant LEVEL] [-file PATH] [-time DUR]"
                echo "默认模型: ${MODEL_FLAG}；只给模型旗标时进入 OpenCode TUI，给出 -file/-time 时进入驱动模式。"
                exit 0;;
            -file|--file)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少路径参数###" >&2; exit 64; fi
                DRIVE_FILE="$2"; DRIVE_MODE=1; shift 2;;
            -time|--time)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少时长参数###" >&2; exit 64; fi
                _ti_raw="$2"; DRIVE_MODE=1; shift 2;;
            *) echo "###${_NAME}: ERROR: 未知参数 '$1'（用法: ${_NAME} [-m|-o|-p|-q|-k|-g|-f|-h] [--model MODEL] [--variant LEVEL] [-file PATH] [-time 30s]）###" >&2; exit 64;;
        esac
    done
    if [[ -n "${_ti_raw:-}" ]]; then
        if ! DRIVE_INTERVAL="$(_parse_interval "${_ti_raw}")"; then
            echo "###${_NAME}: ERROR: --time '${_ti_raw}' 格式无效（示例: 30 / 30s / 5m / 2h）###" >&2
            exit 64
        fi
    fi
    unset _ti_raw
    [[ -n "${DRIVE_INTERVAL}" ]] || DRIVE_INTERVAL=30

    # 模型选择：默认 -f DeepSeek V4 Flash (2x usage)；-o Ox Alpha Free (Unlimited) / -h Hy3 (high) / -p Pro / -m Build auto·Muse Spark 1.2 Contributor OpenCode Go (xhigh) / -q Qwen3.8 Max / -k Kimi K3 / -g GPT-5.6 Luna
    # 各旗标默认模型可用 OPENCODE_MODEL_M/O/P/Q/K/G/F/H 环境变量覆盖；OPENCODE_MODEL/--model 直接覆盖。
    case "${MODEL_FLAG}" in
        -m) MODEL_ID="${OPENCODE_MODEL_M:-opencode-go/muse-spark-1.2-contributor}"; MODEL_NAME="Build auto·Muse Spark 1.2 Contributor OpenCode Go"; VARIANT="xhigh";;
        -o) MODEL_ID="${OPENCODE_MODEL_O:-opencode-go/ox-alpha-free}";    MODEL_NAME="Build auto · Ox Alpha Free (Unlimited) OpenCode Go";;
        -p) MODEL_ID="${OPENCODE_MODEL_P:-opencode-go/deepseek-v4-pro}";  MODEL_NAME="DeepSeek V4 Pro (New)";;
        -q) MODEL_ID="${OPENCODE_MODEL_Q:-opencode-go/qwen3.8-max}";      MODEL_NAME="Qwen3.8 Max";;
        -k) MODEL_ID="${OPENCODE_MODEL_K:-opencode-go/kimi-k3}";          MODEL_NAME="Kimi K3";;
        -g) MODEL_ID="${OPENCODE_MODEL_G:-opencode-go/gpt-5.6-luna}";     MODEL_NAME="GPT-5.6 Luna (2x usage)";;
        -f) MODEL_ID="${OPENCODE_MODEL_F:-opencode-go/deepseek-v4-flash}"; MODEL_NAME="DeepSeek V4 Flash (2x usage)";;
        -h) MODEL_ID="${OPENCODE_MODEL_H:-opencode-go/hy3}";              MODEL_NAME="Hy3"; VARIANT="high";;
        *) echo "###${_NAME}: ERROR: 不支持的默认模型旗标 '${MODEL_FLAG}'###" >&2; exit 64;;
    esac
    if [[ -n "${MODEL_OVERRIDE}" ]]; then
        MODEL_ID="${MODEL_OVERRIDE}"
        MODEL_NAME="${MODEL_OVERRIDE}（override）"
    fi
    [[ -n "${VARIANT_OVERRIDE}" ]] && VARIANT="${VARIANT_OVERRIDE}"

    export OPENCODE_CONFIG_CONTENT='{"lsp":true,"agent":{"build":{"model":"'"${MODEL_ID}"'","variant":"'"${VARIANT}"'"}}}'

    echo "============================================================"
    echo "  OpenCode: build | auto | ${MODEL_NAME} (${VARIANT})"
    echo "  log: ${LOG_FILE}"
    echo "  user-input list: ${LIST_FILE}"
    if (( _SNSC )); then
        echo "  launcher: snsc/HPC"
    fi
    if [[ -n "${project_root:-}" ]]; then
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
    _live_log()
    {
        local _iu
        if tail --version 2>/dev/null | head -1 | grep -q GNU; then
            _iu="-s 0.2 --pid=$$"
        else
            _iu="-s 0.2"
        fi
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
        [[ -x "${_OPENCODE_BIN}" ]] || return 0
        command -v python3  >/dev/null 2>&1 || return 0
        _rec_jf="/tmp/opencode/${LIST_FILE}.export.json"
        if "${_OPENCODE_BIN}" export "${_rec_sid}" 2>/dev/null > "${_rec_jf}"; then
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

    if (( ! DRIVE_MODE )); then
        # 原有 TUI 交互模式（无 -file/-time 时行为完全不变）
        "${_OPENCODE_BIN}" --agent build --auto --prompt "${PROMPT}" \
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
        "${_OPENCODE_BIN}" run --agent build --auto --print-logs --log-level DEBUG "${PROMPT}" \
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
            "${_OPENCODE_BIN}" run -s "${_drv_sid}" --agent build --auto --print-logs --log-level DEBUG "${_drv_instr}" \
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
            if "${_OPENCODE_BIN}" run -s "${_drv_sid}" --agent build --auto --print-logs --log-level DEBUG "继续" \
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
        unset _drv_sid _drv_rc _nudges _fails
    fi

    if [[ -s "${LIST_FILE}" ]]; then
        echo "user inputs -> ${LIST_FILE}（$(wc -l < "${LIST_FILE}") 行）"
    elif [[ -f "${LIST_FILE}" ]]; then
        echo "user inputs -> ${LIST_FILE}（空）"
    fi
    echo "logs -> ${LOG_FILE}"
    return 0
}

# =====================================================================
# Codex 分支（co/cos）：TUI 或 exec → exec resume 驱动链；注入 skill 清单
# =====================================================================
run_codex() {
    local _CODEX_BIN="${CODEX_BIN:-}"
    if [[ -z "${_CODEX_BIN}" ]]; then
        _CODEX_BIN="$(command -v codex 2>/dev/null || true)"
    fi
    if [[ -z "${_CODEX_BIN}" ]]; then
        echo "###${_NAME}: ERROR: 未找到 codex，请安装 Codex CLI 或设置 CODEX_BIN###" >&2
        exit 127
    fi

    _load_prompt
    # 初始注入包含固定 prompt、全局 agent 配置目录清单以及全局/工作区 skill 清单。
    # 这里只列出路径，不读取配置内容；模型需要时再按需读取。
    local _configure_agent_root="${HOME:-}/configure" _git_root _workspace_root
    local -a _agent_config_dirs _workspace_skill_roots
    local -A _SEEN_SKILL_PATHS=()
    _agent_config_dirs=(
        "${_configure_agent_root}/skills"
        "${_configure_agent_root}/tools"
        "${_configure_agent_root}/hooks"
        "${_configure_agent_root}/plugins"
    )
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
    _append_agent_config_dirs "全局 Agent 配置目录（按需读取）" "${_agent_config_dirs[@]}"
    _append_skill_list "全局技能（${_agent_config_dirs[0]}）" "${_agent_config_dirs[0]}"
    _append_skill_list "当前工作目录技能（${_PWD}）" "${_workspace_skill_roots[@]}"
    unset _git_root _workspace_root _workspace_skill_roots

    # ---- 参数解析：模型旗标 + 无人值守驱动选项 ----
    # 用法: ${_NAME} [-m|-o|-p|-q|-k|-g|-f|-h] [--model MODEL]
    #                       [-time DUR]
    #   -time/--time DUR  : 驱动模式中「继续」发送间隔，纯数字=秒；支持 s/m/h 后缀（默认 30s）。
    #   --model MODEL     : 直接指定 Codex 模型，覆盖模型旗标；也可用 CODEX_MODEL 环境变量覆盖。
    #   --reasoning-effort LEVEL : 直接指定 reasoning effort（low/medium/high/xhigh/max/ultra）。
    local MODEL_FLAG="${CODEX_DEFAULT_MODEL_FLAG:--m}"
    local MODEL_OVERRIDE="${CODEX_MODEL:-}"
    local REASONING_OVERRIDE="${CODEX_REASONING_EFFORT:-}"
    local CODEX_SANDBOX_MODE="${CODEX_SANDBOX:-danger-full-access}"
    local CODEX_APPROVAL_POLICY="${CODEX_APPROVAL:-never}"
    local MODEL_ID MODEL_NAME REASONING_EFFORT DRIVE_INTERVAL="" DRIVE_MODE=0
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
    if [[ -n "${_ti_raw:-}" ]]; then
        if ! DRIVE_INTERVAL="$(_parse_interval "${_ti_raw}")"; then
            echo "###${_NAME}: ERROR: --time '${_ti_raw}' 格式无效（示例: 30 / 30s / 5m / 2h）###" >&2
            exit 64
        fi
    fi
    unset _ti_raw
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
    local -a CODEX_COMMON_ARGS CODEX_AGENT_DIR_ARGS CODEX_INITIAL_ARGS
    CODEX_COMMON_ARGS=(
        --model "${MODEL_ID}"
        --config "model_reasoning_effort=\"${REASONING_EFFORT}\""
        --config "approval_policy=\"${CODEX_APPROVAL_POLICY}\""
        --config "sandbox_mode=\"${CODEX_SANDBOX_MODE}\""
    )
    for _agent_dir in "${_agent_config_dirs[@]}"; do
        [[ -d "${_agent_dir}" ]] || continue
        CODEX_AGENT_DIR_ARGS+=(--add-dir "${_agent_dir}")
    done
    CODEX_INITIAL_ARGS=(
        "${CODEX_COMMON_ARGS[@]}"
        "${CODEX_AGENT_DIR_ARGS[@]}"
    )
    unset _agent_dir

    echo "============================================================"
    echo "  Codex: ${MODEL_NAME} | reasoning=${REASONING_EFFORT}"
    echo "  log: ${LOG_FILE}"
    echo "  agent config: ${_configure_agent_root}/{skills,tools,hooks,plugins}"
    if (( _SNSC )); then
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

    if (( ! DRIVE_MODE )); then
        # 普通模式：保持 Codex TUI；只给模型旗标时不进入 exec 链。
        "${_CODEX_BIN}" "${CODEX_INITIAL_ARGS[@]}" -- "${PROMPT}" 2>"${LOG_FILE}"
        _run_rc=$?
    else
        # ---- 驱动模式：headless codex exec → exec resume 链式驱动 ----
        # 回合1 prompt → thread.started → 每 N 秒发送固定的「继续」。
        _live_log
        echo "---- drive: prompt round start $(date "+%F-%T") ----"
        if "${_CODEX_BIN}" exec "${CODEX_INITIAL_ARGS[@]}" --json -- "${PROMPT}" >>"${LOG_FILE}" 2>&1; then
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
    return "${_run_rc:-0}"
}

# ---- 分发（cpupower.sh 模式：按 $_NAME 分发）----
case "${_NAME}" in
    cl)   _AGENT=claude;   _SNSC=0;;
    op)   _AGENT=opencode; _SNSC=0;;
    co)   _AGENT=codex;    _SNSC=0;;
    ops)  _AGENT=opencode; _SNSC=1;;
    cos)  _AGENT=codex;    _SNSC=1;;
    *)
        echo "Usage: ln -s agent.sh {cl|op|co|ops|cos}"
        exit 1;;
esac

case "${_AGENT}" in
    claude)   run_claude "$@";;
    opencode) run_opencode "$@";;
    codex)    run_codex "$@";;
esac
_rc=$?
unset PROMPT _PWD
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
exit "${_rc}"