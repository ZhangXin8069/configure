#!/usr/bin/env bash
# 统一 agent 启动器：cl/cls/op/co/ops/cos 软链接分发（cpupower.sh 模式，按 $_NAME 区分）
#   cl  → Claude Code（默认 deepseek-pay 途径的 Anthropic 兼容端点；TUI 权限模式见配置；驱动：claude -p → --resume 链）
#   cls → Claude Code HPC/secure 入口（agents.claude.secure_binary 部署路径，缺失时自动完整复制）
#   op  → OpenCode（默认 build agent：TUI；驱动：run -s 链）
#   co  → Codex（TUI；驱动：exec → exec resume 链）
#   ops → OpenCode HPC/secure 入口（agents.opencode.secure_binary 部署路径，缺失时自动完整复制）
#   cos → Codex HPC/secure 入口（agents.codex.secure_binary 部署路径，缺失时自动完整复制）
# prompt 单一来源：同目录 agent-prompt.txt（模板含 ${HOME}/${_PWD} 占位符；op 另支持 ${LIST_FILE}）
# 配置来源：同目录 agent-config.json（通用）+ agent-custom.json 或 agent-custom.json.refer（个性化，
#   存在 agent-custom.json 时替代后者）深度合并；模型途径、各途径/各 agent 默认模型与强度、共用参数均取自这两份配置
# 模型元数据：co 对内置目录之外的模型（deepseek 等）自动生成 model_catalog_json 注入（见 _codex_model_catalog），
#   消除 Codex ≥0.154 的「Model metadata ... not found」告警；缓存于 data/cache，可用 CODEX_MODEL_CATALOG 覆盖

# ---- 脚本定位：AGENT_SCRIPT_DIR 可在 /dev/fd/3 等场景注入真实目录；缺失时回退 BASH_SOURCE ----
# 软链接调用（把 cl/op/co 链到 PATH 中其他目录）时解析出脚本真实位置，否则同目录的
# agent-runtime.sh / agent-config.json / agent-prompt.txt 都找不到；_NAME 仍取调用名，
# 身份（cl/op/co）不受解析影响。readlink 不带 -f，兼容 macOS/HPC 老环境。
_SRC=${BASH_SOURCE[0]:-${0}}
_SRC_REAL="${_SRC}"
case "${_SRC}" in
    */*)
        _HOPS=0
        while [[ -L "${_SRC_REAL}" && ${_HOPS} -lt 40 ]]; do
            _LINK_DIR="${_SRC_REAL%/*}"
            [ -z "${_LINK_DIR}" ] && _LINK_DIR="/"
            _LINK_DIR="$(cd -- "${_LINK_DIR}" 2>/dev/null && pwd)" || break
            _LINK_TARGET="$(readlink "${_SRC_REAL}" 2>/dev/null)" || break
            [[ "${_LINK_TARGET}" == /* ]] || _LINK_TARGET="${_LINK_DIR}/${_LINK_TARGET}"
            _SRC_REAL="${_LINK_TARGET}"
            _HOPS=$((_HOPS + 1))
        done
        ;;
esac
case "${_SRC_REAL}" in */*) _DIR=${_SRC_REAL%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ -n "${AGENT_SCRIPT_DIR:-}" ]]; then
    _PATH="${AGENT_SCRIPT_DIR}"
else
    if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
fi
_NAME=${AGENT_LAUNCHER_NAME:-${_SRC##*/}}
case "${_NAME}" in
    cl)   _AGENT=claude;   _SECURE=0;;
    cls)  _AGENT=claude;   _SECURE=1;;
    op)   _AGENT=opencode; _SECURE=0;;
    co)   _AGENT=codex;    _SECURE=0;;
    ops)  _AGENT=opencode; _SECURE=1;;
    cos)  _AGENT=codex;    _SECURE=1;;
    *)
        echo "Usage: ln -s agent.sh {cl|cls|op|co|ops|cos}"
        exit 1;;
esac
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

# 增强鲁棒性：cwd 失效（如所在目录已被删除）时回退到脚本目录，
# 避免后续 pwd 与相对路径文件（日志/清单/重定向）创建失败
if ! _PWD="$(pwd 2>/dev/null)"; then
    echo "###${_NAME}: warning: 当前目录不可用（getcwd 失败），回退到 ${_PATH}###" >&2
    cd "${_PATH}" || exit 1
_PWD="$(pwd)"
fi

if [[ ! -r "${_PATH}/agent-runtime.sh" ]]; then
    echo "###${_NAME}: ERROR: ${_PATH}/agent-runtime.sh 不存在或不可读（共享 runtime 缺失）###" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "${_PATH}/agent-runtime.sh"
_agent_runtime_init "${_PWD}" "${_PATH}" || exit $?

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

_parse_nonnegative_integer() {
    local value="${1:-}"
    [[ "$value" =~ ^[0-9]+$ ]] || return 1
    printf '%s\n' "$value"
}

_parse_runtime_limit() {
    local value="${1:-}"
    [[ "$value" == 0 ]] && {
        printf '0\n'
        return 0
    }
    _parse_interval "$value"
}

# secure 变体（cls/ops/cos）二进制准备：入参为 agents.<agent>.secure_binary 配置值
# （支持 ${HOME} / ~ 占位符）。目标存在且可执行时直接使用；否则视为待部署路径，
# 从 PATH 中同名的可执行文件完整复制（非符号链接）过去，供 vscode-server 升级后自愈。
# stdout 输出最终可用路径；无法准备时明确报错并退出，不做静默回退。
_prepare_secure_binary() {
    local _agent_name="$1" _target="$2" _env_var="$3"
    _target="${_target//\$\{HOME\}/${HOME:-}}"
    _target="${_target/#\~/${HOME:-}}"
    if [[ -f "${_target}" && -x "${_target}" ]]; then
        printf '%s\n' "${_target}"
        return 0
    fi
    local _source=""
    _source="$(_agent_runtime_locate_binary "${_agent_name}")" || _source=""
    if [[ -z "${_source}" ]]; then
        # 源二进制尚未安装：先按 agent 系列约定自动安装，再重新探测（安装目录已前置到 PATH）
        _agent_runtime_ensure_agent "${_agent_name}" || true
        _source="$(_agent_runtime_locate_binary "${_agent_name}")" || _source=""
    fi
    if [[ -z "${_source}" ]]; then
        echo "###${_NAME}: ERROR: secure_binary 不存在且 PATH 中未找到 ${_agent_name}，请安装或设置 ${_env_var}###" >&2
        return 127
    fi
    local _target_dir
    _target_dir="$(dirname -- "${_target}")"
    if ! mkdir -p -- "${_target_dir}"; then
        echo "###${_NAME}: ERROR: 无法创建 secure_binary 目录：${_target_dir}###" >&2
        return 1
    fi
    if [[ -e "${_source}" && "${_source}" -ef "${_target}" ]]; then
        printf '%s\n' "${_target}"
        return 0
    fi
    if [[ -d "${_target}" && ! -L "${_target}" ]]; then
        echo "###${_NAME}: ERROR: secure_binary 路径被目录占用：${_target}###" >&2
        return 1
    fi
    local _tmp="${_target}.tmp.$$"
    rm -f -- "${_tmp}" 2>/dev/null || true
    # macOS/BSD 的 chmod 不支持 GNU 风格 -- 选项终止符（_tmp 恒为绝对路径，无需它）
    if ! cp -f -- "${_source}" "${_tmp}" || ! chmod +x "${_tmp}" \
        || ! rm -f -- "${_target}" || ! mv -f -- "${_tmp}" "${_target}"; then
        rm -f -- "${_tmp}" 2>/dev/null || true
        echo "###${_NAME}: ERROR: 无法将 ${_source} 复制到 secure_binary：${_target}###" >&2
        return 1
    fi
    echo "###${_NAME}: secure_binary 缺失，已从 ${_source} 完整复制到 ${_target}###" >&2
    printf '%s\n' "${_target}"
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
    # ${CONFIGURE_ROOT} = configure 部署根（非 ${HOME}/configure 的部署下同样正确）
    PROMPT="${PROMPT//\$\{CONFIGURE_ROOT\}/${AGENT_CONFIGURE_ROOT:-$(_agent_runtime_configure_root)}}"
    PROMPT="${PROMPT//\$\{HOME\}/${HOME:-}}"
    PROMPT="${PROMPT//\$\{_PWD\}/$_PWD}"
    PROMPT="${PROMPT//\$\{LIST_FILE\}/${LIST_FILE:-}}"
    if [[ -n "${AGENT_CONTEXT_PROMPT:-}" ]]; then
        PROMPT+="${AGENT_CONTEXT_PROMPT}"
    fi
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

# 数组元素包含判断（bash 3.2 无关联数组，用线性查找）
_contains() {
    local _target="$1"
    shift
    local _item
    for _item in "$@"; do
        [[ "${_item}" == "${_target}" ]] && return 0
    done
    return 1
}

# JSON 字符串值转义（反斜杠/双引号/换行；用于 cl 的 --settings 私有设置文件）
_json_escape() {
    local _s="$1"
    _s="${_s//\\/\\\\}"
    _s="${_s//\"/\\\"}"
    _s="${_s//$'\n'/}"
    _s="${_s//$'\r'/}"
    printf '%s' "${_s}"
}

# 旧 key 环境变量名过渡：新名缺失而旧名存在时导出新名（并告警提示迁移）
#   DEEPSEEK_API_KEY → DEEPSEEK_PAY_API_KEY；LQCD_API_KEY → CUSTOM_GPT_API_KEY
_migrate_legacy_keys() {
    local _pair _new_name _old_name
    for _pair in "DEEPSEEK_PAY_API_KEY:DEEPSEEK_API_KEY" "CUSTOM_GPT_API_KEY:LQCD_API_KEY"; do
        _new_name="${_pair%%:*}"
        _old_name="${_pair##*:}"
        if [[ -z "${!_new_name:-}" && -n "${!_old_name:-}" ]]; then
            export "${_new_name}=${!_old_name}"
            echo "###${_NAME}: warning: 未设置 ${_new_name}，回退使用旧变量 ${_old_name}（建议迁移到新名）###" >&2
        fi
    done
}

# 途径名规整化：custom-gpt → CUSTOM_GPT，与 _agent_config_load 展开出的 _CFG_* 变量名保持一致
_cfg_provider_key() {
    printf '%s' "$1" | tr '[:lower:]-' '[:upper:]_'
}

# 供应商快捷词：pay→deepseek-pay、go→opencode-go、gpt→custom-gpt；完整途径名原样返回
_provider_alias() {
    case "$1" in
        pay) printf 'deepseek-pay\n';;
        go)  printf 'opencode-go\n';;
        gpt) printf 'custom-gpt\n';;
        *)   printf '%s\n' "$1";;
    esac
}

# 途径在某 agent 下的默认模型（个性化配置 providers.<途径>.default_models.<agent>），未配置输出空
_cfg_provider_default_model() {
    local _pkey _akey _var
    _pkey="$(_cfg_provider_key "$1")"
    _akey="$(printf '%s' "$2" | tr '[:lower:]' '[:upper:]')"
    _var="_CFG_PROVIDERS_${_pkey}_DEFAULT_MODELS_${_akey}"
    printf '%s' "${!_var:-}"
}

# 途径在某 agent 下的默认强度（个性化配置 providers.<途径>.default_strengths.<agent>），未配置输出空
_cfg_provider_default_strength() {
    local _pkey _akey _var
    _pkey="$(_cfg_provider_key "$1")"
    _akey="$(printf '%s' "$2" | tr '[:lower:]' '[:upper:]')"
    _var="_CFG_PROVIDERS_${_pkey}_DEFAULT_STRENGTHS_${_akey}"
    printf '%s' "${!_var:-}"
}

# Codex 模型展示名（通用配置 agents.codex.model_catalog.display_names.<slug>），未配置输出空
_cfg_codex_model_display_name() {
    local _var
    _var="_CFG_AGENTS_CODEX_MODEL_CATALOG_DISPLAY_NAMES_$(printf '%s' "$1" | tr -c 'A-Za-z0-9' '_' | tr '[:lower:]' '[:upper:]')"
    while [[ "${_var}" == *__* ]]; do
        _var="${_var//__/_}"
    done
    printf '%s' "${!_var:-}"
}

# =====================================================================
# 配置文件加载：agent-config.json（通用配置）与 agent-custom.json（个性化配置，
# 缺失时回退 agent-custom.json.refer）深度合并后展开为一组 _CFG_* 变量。
# 解析器用 python3（可用 AGENT_CONFIG_PYTHON 指定其他解释器）。
# =====================================================================
_agent_config_load() {
    local _cfg="${_PATH}/agent-config.json"
    local _custom="${_PATH}/agent-custom.json"
    [[ -s "${_custom}" ]] || _custom="${_PATH}/agent-custom.json.refer"
    if [[ ! -s "${_cfg}" ]]; then
        echo "###${_NAME}: ERROR: 缺少通用配置 ${_cfg}###" >&2
        exit 1
    fi
    if [[ ! -s "${_custom}" ]]; then
        echo "###${_NAME}: ERROR: 缺少个性化配置（${_PATH}/agent-custom.json 与 agent-custom.json.refer 均不存在或为空）###" >&2
        exit 1
    fi
    local _py="${AGENT_CONFIG_PYTHON:-}"
    if [[ -z "${_py}" ]]; then
        if command -v python3 >/dev/null 2>&1; then
            _py=python3
        elif command -v python >/dev/null 2>&1; then
            _py=python
        else
            echo "###${_NAME}: ERROR: 解析配置文件需要 python3（或设置 AGENT_CONFIG_PYTHON）###" >&2
            exit 1
        fi
    fi
    _AGENT_PYTHON="${_py}" # 供后续 helper（如 Codex 模型目录）复用同一解释器
    local _dump
    if ! _dump="$("${_py}" - "${_cfg}" "${_custom}" <<'PYEOF'
import json
import os
import shlex
import sys


def deep_merge(base, override):
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = deep_merge(merged.get(key), value)
        return merged
    return override


def flatten(node, prefix, out):
    if isinstance(node, dict):
        for key, value in node.items():
            flatten(value, prefix + [str(key)], out)
    elif isinstance(node, list):
        out.append((prefix, json.dumps(node, ensure_ascii=False, separators=(",", ":"))))
    elif isinstance(node, bool):
        out.append((prefix, "true" if node else "false"))
    elif node is None:
        out.append((prefix, ""))
    else:
        out.append((prefix, str(node)))


def variable_name(parts):
    raw = "_".join(parts)
    name = "".join(ch if ch.isalnum() else "_" for ch in raw).upper()
    while "__" in name:
        name = name.replace("__", "_")
    return "_CFG_" + name.strip("_")


def opencode_providers(cfg):
    agents = cfg.get("agents") or {}
    providers = cfg.get("providers") or {}
    key_providers = (agents.get("opencode") or {}).get("key_providers") or []
    blocks = {}
    for name in key_providers:
        provider = providers.get(name)
        if not isinstance(provider, dict):
            continue
        env_key = str(provider.get("env_key") or "")
        if not env_key or not os.environ.get(env_key):
            continue
        provider_id = str(provider.get("opencode_provider_id") or name)
        if name == "custom-gpt":
            base_url = str(provider.get("base_url") or "")
            if not base_url:
                continue
            meta = provider.get("opencode") or {}
            models = {str(m): {} for m in (meta.get("models") or [])}
            blocks[provider_id] = {
                "npm": str(meta.get("npm") or "@ai-sdk/openai"),
                "name": str(provider.get("label") or name),
                "options": {"baseURL": base_url, "apiKey": "{env:%s}" % env_key},
                "models": models,
            }
        else:
            blocks[provider_id] = {"options": {"apiKey": "{env:%s}" % env_key}}
    return blocks


def main():
    with open(sys.argv[1], encoding="utf-8") as fh:
        base = json.load(fh)
    with open(sys.argv[2], encoding="utf-8") as fh:
        custom = json.load(fh)
    if not isinstance(base, dict) or not isinstance(custom, dict):
        raise SystemExit("config root must be a JSON object")
    cfg = deep_merge(base, custom)
    leaves = []
    flatten(cfg, [], leaves)
    lines = ["%s=%s" % (variable_name(parts), shlex.quote(value)) for parts, value in leaves]
    provider_json = json.dumps(opencode_providers(cfg), ensure_ascii=False, separators=(",", ":"))
    lines.append("_CFG_OPENCODE_PROVIDER_JSON=%s" % shlex.quote(provider_json))
    # 以 UTF-8 字节写出：不受调用方 locale（如 LANG=C）影响，避免中文值编码错误
    sys.stdout.buffer.write(("\n".join(lines) + "\n").encode("utf-8"))


main()
PYEOF
    )"; then
        echo "###${_NAME}: ERROR: 解析配置失败（${_cfg} / ${_custom}）###" >&2
        exit 1
    fi
    eval "${_dump}"
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
            if ! _contains "${_skill_path}" "${_SEEN_SKILL_PATHS[@]}"; then
                PROMPT+="${_skill_path}"$'\n'
                _SEEN_SKILL_PATHS+=("${_skill_path}")
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
_CLAUDE_SETTINGS_TMP=""
_cleanup() {
    local _exit_rc=$?
    if [[ "${_AGENT:-}" == opencode ]] && declare -F _recover_inputs >/dev/null 2>&1; then
        _recover_inputs
    fi
    [[ -n "${_LIVE_PID:-}" ]] && kill "${_LIVE_PID}" 2>/dev/null
    if [[ -n "${_CLAUDE_SETTINGS_TMP:-}" && -f "${_CLAUDE_SETTINGS_TMP}" ]]; then
        rm -f -- "${_CLAUDE_SETTINGS_TMP}"
    fi
    _agent_runtime_on_exit "${_exit_rc}"
    return "${_exit_rc}"
}
trap '_cleanup' EXIT
_interrupt() {
    _agent_runtime_mark stopped "收到中断信号" 130
    exit 130
}
_terminate() {
    _agent_runtime_mark stopped "收到终止信号" 143
    exit 143
}
trap '_interrupt' INT
trap '_terminate' TERM

# =====================================================================
# Claude Code 分支（cl/cls）：TUI 或 -p/--resume 驱动链；模型旗标与 op/co 一致
# =====================================================================
run_claude() {
    local _CLAUDE_BIN="${CLAUDE_BIN:-}"
    if (( _SECURE )) && [[ -z "${_CLAUDE_BIN}" && -n "${_CFG_AGENTS_CLAUDE_SECURE_BINARY:-}" ]]; then
        # HPC/secure 变体：优先使用 agent-custom.json 的 agents.claude.secure_binary 部署路径，
        # 缺失时由 _prepare_secure_binary 从 PATH 中的 claude 完整复制（非符号链接）
        _CLAUDE_BIN="$(_prepare_secure_binary claude "${_CFG_AGENTS_CLAUDE_SECURE_BINARY}" CLAUDE_BIN)" || exit $?
    fi
    if [[ -z "${_CLAUDE_BIN}" ]]; then
        _CLAUDE_BIN="$(command -v claude 2>/dev/null || true)"
    fi
    if [[ -z "${_CLAUDE_BIN}" ]]; then
        # 环境里还没装：按 agent 系列约定运行部署内安装脚本，再重新探测一次
        _agent_runtime_ensure_agent claude || true
        _CLAUDE_BIN="$(_agent_runtime_locate_binary claude)" || _CLAUDE_BIN=""
    fi
    if [[ -z "${_CLAUDE_BIN}" ]]; then
        echo "###${_NAME}: ERROR: 未找到 claude，请安装 Claude Code 或设置 CLAUDE_BIN###" >&2
        exit 127
    fi

    # ---- 途径设置与 --settings 生成在模型选择之后执行（供应商快捷词需要先解析） ----

    # 与 co 相同的注入：全局 agent 配置目录 + skill 清单
    local _configure_agent_root="${AGENT_CONFIGURE_ROOT:-$(_agent_runtime_configure_root)}" _git_root _workspace_root
    local -a _agent_config_dirs _workspace_skill_roots _SEEN_SKILL_PATHS=()
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
    # dirs/skills 注入在 _load_prompt 之后执行（_load_prompt 会重置 PROMPT）

    # ---- 参数解析：模型/途径覆盖 + 无人值守驱动选项 ----
    # 用法: ${_NAME} [pay|go|gpt] [--model MODEL] [-file PATH] [-time DUR]
    #   --model MODEL     : 直接指定模型 ID；也可用 CLAUDE_MODEL 环境变量覆盖。
    #                       未指定时按两层默认取（显式选途径时途径默认优先，否则 agent 自身默认优先）：
    #                       providers.<途径>.default_models.claude 与 agents.claude.model 互为一层，高优先层缺值回退另一层。
    #   -file/--file PATH : 驱动模式——prompt 回合完成后以文件内容为第一条指令，
    #                       之后每 --time 间隔向同一会话发送「继续」，直至 Ctrl+C 或连续 3 次失败
    #   -time/--time DUR  : 「继续」发送间隔，纯数字=秒；支持 s/m/h 后缀（如 30s/5m/2h），默认 30s
    # 不给驱动选项时保持原有 TUI 交互模式不变
    local MODEL_OVERRIDE="${CLAUDE_MODEL:-}"
    local PROVIDER_OVERRIDE="${CLAUDE_PROVIDER:-}"
    local MODEL_ID MODEL_NAME DRIVE_FILE="" DRIVE_INTERVAL="" DRIVE_MODE=0
    local MODEL_EXPLICIT=0
    local MAX_TURNS_RAW="${AGENT_MAX_TURNS:-100}"
    local MAX_RUNTIME_RAW="${AGENT_MAX_RUNTIME:-0}"
    local STOP_FILE_ARG="${AGENT_STOP_PATH:-}"
    local RESUME_RUN_ID="${AGENT_RESUME_RUN_ID:-}"
    local ONCE_MODE="${AGENT_ONCE:-0}"
    [[ -n "${MODEL_OVERRIDE}" ]] && MODEL_EXPLICIT=1
    while (( $# )); do
        case "$1" in
            pay|go|gpt|deepseek-pay|opencode-go|custom-gpt)
                PROVIDER_OVERRIDE="$(_provider_alias "$1")"; shift;;
            --model)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少模型参数###" >&2; exit 64; fi
                MODEL_OVERRIDE="$2"; MODEL_EXPLICIT=1; shift 2;;
            --help)
                echo "用法: ${_NAME} [pay|go|gpt] [--model MODEL] [-file PATH] [-time DUR]"
                echo "供应商快捷词: pay=deepseek-pay / go=opencode-go / gpt=custom-gpt（如 ${_NAME} go）。"
                echo "模型: 两层默认——显式选途径（快捷词或 CLAUDE_PROVIDER 环境变量）时优先取 providers.<途径>.default_models.claude，否则优先取 agents.claude.model，缺值回退另一层；--model/CLAUDE_MODEL 直接覆盖。"
                echo "不给驱动选项时进入 Claude TUI，给出 -file/-time 时进入驱动模式。"
                exit 0;;
            -file|--file)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少路径参数###" >&2; exit 64; fi
                DRIVE_FILE="$2"; DRIVE_MODE=1; shift 2;;
            -time|--time)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少时长参数###" >&2; exit 64; fi
                _ti_raw="$2"; DRIVE_MODE=1; shift 2;;
            --once)
                ONCE_MODE=1; DRIVE_MODE=1; shift;;
            --max-turns)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少回合数###" >&2; exit 64; fi
                MAX_TURNS_RAW="$2"; DRIVE_MODE=1; shift 2;;
            --max-runtime)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少时长参数###" >&2; exit 64; fi
                MAX_RUNTIME_RAW="$2"; DRIVE_MODE=1; shift 2;;
            --stop-file)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少路径参数###" >&2; exit 64; fi
                STOP_FILE_ARG="$2"; DRIVE_MODE=1; shift 2;;
            --resume)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少 run id###" >&2; exit 64; fi
                RESUME_RUN_ID="$2"; DRIVE_MODE=1; shift 2;;
            *) echo "###${_NAME}: ERROR: 未知参数 '$1'（用法: ${_NAME} [pay|go|gpt] [--model MODEL] [-file PATH] [-time 30s]）###" >&2; exit 64;;
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
    if ! MAX_TURNS_RAW="$(_parse_nonnegative_integer "${MAX_TURNS_RAW}")"; then
        echo "###${_NAME}: ERROR: --max-turns '${MAX_TURNS_RAW}' 必须是非负整数###" >&2
        exit 64
    fi
    if ! MAX_RUNTIME_RAW="$(_parse_runtime_limit "${MAX_RUNTIME_RAW}")"; then
        echo "###${_NAME}: ERROR: --max-runtime '${MAX_RUNTIME_RAW}' 格式无效（示例: 0 / 30 / 5m / 2h）###" >&2
        exit 64
    fi

    # ---- 途径设置：Anthropic 兼容端点与 key 均取自 agent-config.json/agent-custom.json ----
    # 端点与 baseline 环境变量无条件覆盖外部同名变量；ANTHROPIC_AUTH_TOKEN 取自途径 env_key 环境变量。
    # 途径来自命令行快捷词（pay/go/gpt）、CLAUDE_PROVIDER 环境变量或个性化配置 agents.claude.provider。
    # 环境变量值同样过别名规整，使 CLAUDE_PROVIDER=go 等价于命令行快捷词 go。
    local _cl_provider="$(_provider_alias "${PROVIDER_OVERRIDE:-${_CFG_AGENTS_CLAUDE_PROVIDER}}")"
    if [[ -z "${_cl_provider}" ]]; then
        echo "###${_NAME}: ERROR: 未指定途径（命令行快捷词 pay|go|gpt、CLAUDE_PROVIDER 环境变量或 agent-custom.json agents.claude.provider）###" >&2
        exit 64
    fi
    # 是否由用户显式指定途径（命令行快捷词或 CLAUDE_PROVIDER 环境变量，两者一视同仁）：
    # 决定两层默认谁优先——显式时 providers 层优先，否则 agent 层优先。
    local PROVIDER_EXPLICIT=0
    if [[ -n "${PROVIDER_OVERRIDE}" ]]; then PROVIDER_EXPLICIT=1; fi
    local _CL_PERMISSION_MODE="${_CFG_AGENTS_CLAUDE_PERMISSION_MODE:-auto}"
    local _cl_pkey _cl_var _cl_key_name _cl_key=""
    _cl_pkey="$(_cfg_provider_key "${_cl_provider}")"
    _cl_var="_CFG_PROVIDERS_${_cl_pkey}_ANTHROPIC_BASE_URL"
    ANTHROPIC_BASE_URL="${!_cl_var:-}"
    if [[ -z "${ANTHROPIC_BASE_URL}" ]]; then
        echo "###${_NAME}: ERROR: 途径 '${_cl_provider}' 未定义 anthropic_base_url，cl 无法使用该途径（见 agent-config.json / agent-custom.json）###" >&2
        exit 64
    fi
    _cl_var="_CFG_PROVIDERS_${_cl_pkey}_ENV_KEY"
    _cl_key_name="${!_cl_var:-}"
    export ANTHROPIC_BASE_URL

    # 模型选择（两层默认：显式选途径时 providers 层优先，否则 agent 层优先；高优先层缺值回退另一层）：
    #   1) --model/CLAUDE_MODEL 显式覆盖；
    #   2) 显式途径时取 providers.<途径>.default_models.claude，缺省回退 agents.claude.model；
    #   3) 途径来自 agents.claude.provider 时取 agents.claude.model，缺省回退途径默认模型。
    # 两层皆空时启动报错，避免模型与端点脱钩。
    local _cl_agent_model="${_CFG_AGENTS_CLAUDE_MODEL:-}"
    local _cl_provider_model
    _cl_provider_model="$(_cfg_provider_default_model "${_cl_provider}" claude)"
    local _cl_model_label="（途径默认）"
    if [[ -n "${MODEL_OVERRIDE}" ]]; then
        MODEL_ID="${MODEL_OVERRIDE}"
        _cl_model_label="（override）"
    elif (( PROVIDER_EXPLICIT )) && [[ -n "${_cl_provider_model}" ]]; then
        MODEL_ID="${_cl_provider_model}"
    elif [[ -n "${_cl_agent_model}" ]]; then
        MODEL_ID="${_cl_agent_model}"
        _cl_model_label="（agent 默认）"
    else
        MODEL_ID="${_cl_provider_model}"
    fi
    if [[ -z "${MODEL_ID}" ]]; then
        echo "###${_NAME}: ERROR: 途径 '${_cl_provider}' 未定义 claude 默认模型（见 agent-custom.json agents.claude.model 或 providers.${_cl_provider}.default_models.claude）###" >&2
        exit 64
    fi
    MODEL_NAME="${MODEL_ID}${_cl_model_label}"
    # 强度选择（与模型同两层优先级；cl 无强度覆盖入口，故无 override 槽）：
    #   显式途径时 providers.<途径>.default_strengths.claude 优先，否则 agent 层优先；
    #   agent 层内部顺序不变：agents.claude.strength > 旧键 agents.claude.env.CLAUDE_CODE_EFFORT_LEVEL；
    #   高优先层缺值回退另一层，皆空则 max（内置兜底）。
    local CLAUDE_STRENGTH=""
    local _cl_agent_strength="${_CFG_AGENTS_CLAUDE_STRENGTH:-}"
    [[ -n "${_cl_agent_strength}" ]] || _cl_agent_strength="${_CFG_AGENTS_CLAUDE_ENV_CLAUDE_CODE_EFFORT_LEVEL:-}"
    local _cl_provider_strength
    _cl_provider_strength="$(_cfg_provider_default_strength "${_cl_provider}" claude)"
    if (( PROVIDER_EXPLICIT )) && [[ -n "${_cl_provider_strength}" ]]; then
        CLAUDE_STRENGTH="${_cl_provider_strength}"
    elif [[ -n "${_cl_agent_strength}" ]]; then
        CLAUDE_STRENGTH="${_cl_agent_strength}"
    else
        CLAUDE_STRENGTH="${_cl_provider_strength}"
    fi
    [[ -n "${CLAUDE_STRENGTH}" ]] || CLAUDE_STRENGTH="max"
    # 状态栏（与 co 同款的通用 statusline 配置，经 agent-statusline.sh 渲染）
    export AGENT_STATUSLINE_SEGMENTS="${_CFG_STATUSLINE_SEGMENTS:-[]}"
    export AGENT_STATUSLINE_USE_COLORS="${_CFG_STATUSLINE_USE_COLORS:-true}"
    export AGENT_PERMISSION_MODE="${_CL_PERMISSION_MODE}"
    local -a _cl_env_keys=(
        ANTHROPIC_MODEL ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL
        ANTHROPIC_DEFAULT_HAIKU_MODEL CLAUDE_CODE_SUBAGENT_MODEL
        CLAUDE_CODE_EFFORT_LEVEL CLAUDE_CODE_AUTO_COMPACT_WINDOW DISABLE_AUTOUPDATER
    )
    local _cl_env_key _cl_env_value
    for _cl_env_key in "${_cl_env_keys[@]}"; do
        _cl_var="_CFG_AGENTS_CLAUDE_ENV_${_cl_env_key}"
        _cl_env_value="${!_cl_var:-}"
        if [[ -n "${_cl_env_value}" ]]; then
            printf -v "${_cl_env_key}" '%s' "${_cl_env_value}"
            export "${_cl_env_key}"
        else
            unset "${_cl_env_key}"
        fi
    done
    unset _cl_env_key _cl_env_value
    # ANTHROPIC_MODEL 与最终模型保持一致（快捷词/两层默认切换模型时同步 env 与 --settings）；
    # OPUS/SONNET 别名未在 agents.claude.env 显式配置时同样跟随最终模型，避免切换途径后残留旧模型
    ANTHROPIC_MODEL="${MODEL_ID}"
    export ANTHROPIC_MODEL
    if [[ -z "${_CFG_AGENTS_CLAUDE_ENV_ANTHROPIC_DEFAULT_OPUS_MODEL:-}" ]]; then
        ANTHROPIC_DEFAULT_OPUS_MODEL="${MODEL_ID}"
        export ANTHROPIC_DEFAULT_OPUS_MODEL
    fi
    if [[ -z "${_CFG_AGENTS_CLAUDE_ENV_ANTHROPIC_DEFAULT_SONNET_MODEL:-}" ]]; then
        ANTHROPIC_DEFAULT_SONNET_MODEL="${MODEL_ID}"
        export ANTHROPIC_DEFAULT_SONNET_MODEL
    fi
    # 强度落地：CLAUDE_CODE_EFFORT_LEVEL 取解析结果（覆盖外部/旧配置同名变量）
    printf -v CLAUDE_CODE_EFFORT_LEVEL '%s' "${CLAUDE_STRENGTH}"
    export CLAUDE_CODE_EFFORT_LEVEL
    # 认证头：多数 Anthropic 兼容端点接受 Authorization: Bearer（ANTHROPIC_AUTH_TOKEN），
    # 少数（如 opencode-go）只认 x-api-key（ANTHROPIC_API_KEY）；由途径的 anthropic_auth 选择
    # （取值 api_key / auth_token，缺省 auth_token）。另一认证变量显式清除，避免残留旧值抢占。
    _cl_var="_CFG_PROVIDERS_${_cl_pkey}_ANTHROPIC_AUTH"
    if [[ "${!_cl_var:-auth_token}" == "api_key" ]]; then
        _cl_auth_var="ANTHROPIC_API_KEY"
        _cl_auth_other="ANTHROPIC_AUTH_TOKEN"
    else
        _cl_auth_var="ANTHROPIC_AUTH_TOKEN"
        _cl_auth_other="ANTHROPIC_API_KEY"
    fi
    [[ -n "${_cl_key_name}" ]] && _cl_key="${!_cl_key_name:-}"
    if [[ -n "${_cl_key}" ]]; then
        printf -v "${_cl_auth_var}" '%s' "${_cl_key}"
        export "${_cl_auth_var}"
        unset "${_cl_auth_other}"
    else
        unset "${_cl_auth_var}" "${_cl_auth_other}"
        echo "###${_NAME}: warning: 未设置 ${_cl_key_name:-途径 key 环境变量}，${_cl_auth_var} 已清除，Claude Code 可能无法认证###" >&2
    fi

    # 用户级 settings.json 的 env 块（如 cc-switch 遗留的 ANTHROPIC_BASE_URL）优先级高于进程环境变量，
    # 因此再生成只读私有临时设置文件并经 CLI --settings 注入（优先级高于用户/项目设置）；退出时清理。
    _CLAUDE_SETTINGS_TMP="$(mktemp "${TMPDIR:-/tmp}/claude-settings.XXXXXX")" || {
        echo "###${_NAME}: ERROR: 无法创建 claude --settings 临时文件###" >&2
        exit 1
    }
    chmod 600 "${_CLAUDE_SETTINGS_TMP}"
    # 两个认证键都显式写入（生效的带值、另一个为空串），以覆盖用户级 settings.json 里可能遗留的旧 token
    # （如 PROXY_MANAGED）或另一种认证头的残留值，避免误导性 401
    if [[ "${_cl_auth_var}" == "ANTHROPIC_API_KEY" ]]; then
        _claude_token_fragment=",\"ANTHROPIC_API_KEY\":\"$(_json_escape "${ANTHROPIC_API_KEY:-}")\",\"ANTHROPIC_AUTH_TOKEN\":\"\""
    else
        _claude_token_fragment=",\"ANTHROPIC_AUTH_TOKEN\":\"$(_json_escape "${ANTHROPIC_AUTH_TOKEN:-}")\",\"ANTHROPIC_API_KEY\":\"\""
    fi
    # env 块由 _cl_env_keys 动态生成（未配置的键省略，含 DISABLE_AUTOUPDATER 等）
    local _claude_env_fragment="" _cl_frag_key _cl_frag_value
    for _cl_frag_key in "${_cl_env_keys[@]}"; do
        _cl_frag_value="${!_cl_frag_key:-}"
        [[ -n "${_cl_frag_value}" ]] || continue
        _claude_env_fragment+=",\"$(_json_escape "${_cl_frag_key}")\":\"$(_json_escape "${_cl_frag_value}")\""
    done
    unset _cl_frag_key _cl_frag_value
    # statusLine 命令路径加引号（路径含空格可用；Windows 经 Git Bash 执行时须用正斜杠）
    _claude_statusline_cmd="\"$(_json_escape "${_PATH}/agent-statusline.sh")\""
    {
        printf '{"env":{"ANTHROPIC_BASE_URL":"%s"%s%s},"statusLine":{"type":"command","command":"%s"}}\n' \
            "$(_json_escape "${ANTHROPIC_BASE_URL}")" \
            "${_claude_env_fragment}" "${_claude_token_fragment}" \
            "$(_json_escape "${_claude_statusline_cmd}")"
    } > "${_CLAUDE_SETTINGS_TMP}"
    unset _claude_token_fragment _claude_env_fragment _claude_statusline_cmd _cl_auth_var _cl_auth_other

    local _runtime_mode=tui
    (( DRIVE_MODE )) && _runtime_mode=drive
    [[ -n "${RESUME_RUN_ID}" ]] && _runtime_mode=resume
    AGENT_ONCE="${ONCE_MODE}"
    AGENT_RUNTIME_REASONING=""
    AGENT_RUNTIME_VARIANT=""
    _agent_runtime_start_or_resume \
        claude "$MODEL_ID" "$_runtime_mode" \
        "${AGENT_ROLE:-solo-agent}" "${AGENT_TIER:-standard}" \
        "${AGENT_POSTURE:-deep-worker}" "$MAX_TURNS_RAW" "$MAX_RUNTIME_RAW" \
        "$STOP_FILE_ARG" "$RESUME_RUN_ID" "$MODEL_EXPLICIT" 0 0 || exit $?
    MODEL_ID="${AGENT_RUNTIME_MODEL:-$MODEL_ID}"
    _load_prompt
    _append_agent_config_dirs "全局 Agent 配置目录（按需读取）" "${_agent_config_dirs[@]}"
    _append_skill_list "全局技能（${_agent_config_dirs[0]}）" "${_agent_config_dirs[0]}"
    _append_skill_list "当前工作目录技能（${_PWD}）" "${_workspace_skill_roots[@]}"
    unset _git_root _workspace_root _workspace_skill_roots
    _agent_runtime_append_prompt_contract "$_runtime_mode" "$MODEL_ID" "" ""

    echo "============================================================"
    echo "  Claude Code: ${MODEL_NAME} | provider=${_cl_provider} | permission-mode ${_CL_PERMISSION_MODE}"
    if [[ -n "${_cl_key}" ]]; then
        echo "  auth: ${_cl_key_name} 已设置"
    else
        echo "  auth: ${_cl_key_name:-<途径未定义 key 变量>} 未设置 —— 请先 export 该变量（缺失时请求会 401）"
    fi
    echo "  run: ${AGENT_RUN_ID}"
    echo "  log: ${LOG_FILE}"
    echo "  state: ${AGENT_MANIFEST_FILE}"
    echo "  context: ${AGENT_CONTEXT_COUNT} 层说明文件（清单：${AGENT_CONTEXT_FILE}）"
    if (( _SECURE )); then
        echo "  launcher: secure/HPC"
    fi
    if (( DRIVE_MODE )); then
        echo "  drive mode: ON | interval=${DRIVE_INTERVAL}s | max-turns=${AGENT_MAX_TURNS} | max-runtime=${AGENT_MAX_RUNTIME}s | first-instruction=${DRIVE_FILE:-<无，仅继续循环>}"
    else
        echo "  mode: TUI interactive"
    fi
    echo "============================================================"

    if (( ! DRIVE_MODE )); then
        # TUI 交互模式：与 op/co 一致，把初始提示词作为首条消息传入（--permission-mode 原语义保留）
        _agent_runtime_turn_begin
        "${_CLAUDE_BIN}" --settings "${_CLAUDE_SETTINGS_TMP}" --permission-mode "${_CL_PERMISSION_MODE}" --model "${MODEL_ID}" "${PROMPT}" 2> "${LOG_FILE}"
        _run_rc=$?
        if (( _run_rc == 0 )); then
            _agent_runtime_turn_success
        else
            _agent_runtime_turn_failure
        fi
        return "${_run_rc}"
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
    if _agent_runtime_stop_file_requested; then
        echo "logs -> ${LOG_FILE}"
        return 0
    fi
    _live_log
    _drv_sid="${AGENT_SESSION_ID:-}"
    if [[ -n "${RESUME_RUN_ID}" ]]; then
        if [[ -z "${_drv_sid}" ]]; then
            echo "###${_NAME}: ERROR: 可恢复会话没有 session_id，驱动终止###" >&2
            exit 1
        fi
        echo "---- drive: resume session=${_drv_sid} interval=${DRIVE_INTERVAL}s ----"
    else
        echo "---- drive: prompt round start $(date "+%F-%T") ----"
        _agent_runtime_turn_begin
        "${_CLAUDE_BIN}" -p --settings "${_CLAUDE_SETTINGS_TMP}" --permission-mode "${_CL_PERMISSION_MODE}" --model "${MODEL_ID}" "${PROMPT}" 2>> "${LOG_FILE}"
        _drv_rc=$?
        if (( _drv_rc != 0 )); then
            _agent_runtime_turn_failure
            echo "###${_NAME}: ERROR: prompt 回合失败（退出码 ${_drv_rc}），驱动终止###" >&2
            exit "${_drv_rc}"
        fi
        _agent_runtime_turn_success
        _drv_sid="$(grep -oE 'session_(id|\.id)=[A-Za-z0-9_-]+' "${LOG_FILE}" 2>/dev/null | head -1 | cut -d= -f2)"
        if [[ -z "${_drv_sid}" ]]; then
            echo "###${_NAME}: ERROR: 无法从 ${LOG_FILE} 提取 session id，驱动终止###" >&2
            exit 1
        fi
        _agent_runtime_set_session "${_drv_sid}" ""
    fi
    echo "---- drive: session=${_drv_sid} interval=${DRIVE_INTERVAL}s ----"
    if [[ -n "${DRIVE_FILE}" ]]; then
        _drv_instr="$(<"${DRIVE_FILE}")"
        echo "---- drive: first instruction <- ${DRIVE_FILE}（$(wc -c < "${DRIVE_FILE}") 字节）$(date "+%F-%T") ----"
        _agent_runtime_turn_begin
        "${_CLAUDE_BIN}" -p --resume "${_drv_sid}" --settings "${_CLAUDE_SETTINGS_TMP}" --permission-mode "${_CL_PERMISSION_MODE}" --model "${MODEL_ID}" "${_drv_instr}" \
                2>> "${LOG_FILE}"
        _drv_rc=$?
        if (( _drv_rc == 0 )); then
            _agent_runtime_turn_success
        else
            _agent_runtime_turn_failure
        fi
        if (( _drv_rc != 0 )); then
            echo "###${_NAME}: warning: 首条指令回合退出码 ${_drv_rc}，仍进入继续循环###" >&2
        fi
        unset _drv_instr
    else
        echo "---- drive: 未提供 -file，跳过首条指令直接进入继续循环 ----"
    fi
    if (( ONCE_MODE )); then
        if [[ -n "${RESUME_RUN_ID}" && -z "${DRIVE_FILE}" ]]; then
            _agent_runtime_turn_begin
            "${_CLAUDE_BIN}" -p --resume "${_drv_sid}" --settings "${_CLAUDE_SETTINGS_TMP}" --permission-mode "${_CL_PERMISSION_MODE}" --model "${MODEL_ID}" "继续" \
                    2>> "${LOG_FILE}"
            _drv_rc=$?
            if (( _drv_rc == 0 )); then
                _agent_runtime_turn_success
                _agent_runtime_mark finished "resume once"
                echo "logs -> ${LOG_FILE}"
                return 0
            fi
            _agent_runtime_turn_failure
            _agent_runtime_mark failed "resume once 失败" "${_drv_rc}"
            return "${_drv_rc}"
        fi
        _agent_runtime_should_stop 0 || true
        echo "logs -> ${LOG_FILE}"
        return 0
    fi
    _nudges=0
    _fails=0
    _loop_rc=0
    while :; do
        if _agent_runtime_should_stop "${_nudges}"; then
            break
        fi
        sleep "${DRIVE_INTERVAL}"
        if _agent_runtime_should_stop "${_nudges}"; then
            break
        fi
        _agent_runtime_turn_begin
        if "${_CLAUDE_BIN}" -p --resume "${_drv_sid}" --settings "${_CLAUDE_SETTINGS_TMP}" --permission-mode "${_CL_PERMISSION_MODE}" --model "${MODEL_ID}" "继续" \
                2>> "${LOG_FILE}"; then
            _agent_runtime_turn_success
            _nudges=$((_nudges + 1))
            _fails=0
            echo "---- drive: 继续 #${_nudges} ok $(date "+%F-%T") ----"
        else
            _drv_rc=$?
            _agent_runtime_turn_failure
            _fails=$((_fails + 1))
            echo "###${_NAME}: warning: 继续发送失败 ${_fails}/3（退出码 ${_drv_rc}）###" >&2
            if (( _fails >= 3 )); then
                echo "###${_NAME}: ERROR: 连续 3 次「继续」失败，驱动循环终止（累计成功 ${_nudges} 次）###" >&2
                _agent_runtime_mark blocked "连续 3 次继续失败" "${_drv_rc}"
                _loop_rc=1
                break
            fi
        fi
    done
    _drive_result="${_loop_rc:-0}"
    unset _drv_sid _drv_rc _nudges _fails _loop_rc
    echo "logs -> ${LOG_FILE}"
    return "${_drive_result}"
}

# =====================================================================
# OpenCode 分支（op/ops）：TUI 或 run -s 驱动链；自动收集项目上下文注入 prompt
# =====================================================================
run_opencode() {
    local _OPENCODE_BIN="${OPENCODE_BIN:-}"
    if (( _SECURE )) && [[ -z "${_OPENCODE_BIN}" ]]; then
        # HPC/secure 变体：opencode 部署在 vscode-server 目录内（升级后路径会变，请更新或设 OPENCODE_BIN）；
        # 机器相关路径取自 agent-custom.json 的 agents.opencode.secure_binary，
        # 缺失时由 _prepare_secure_binary 从 PATH 中的 opencode 完整复制（非符号链接）
        if [[ -n "${_CFG_AGENTS_OPENCODE_SECURE_BINARY:-}" ]]; then
            _OPENCODE_BIN="$(_prepare_secure_binary opencode "${_CFG_AGENTS_OPENCODE_SECURE_BINARY}" OPENCODE_BIN)" || exit $?
        fi
    fi
    if [[ -z "${_OPENCODE_BIN}" ]]; then
        _OPENCODE_BIN="$(command -v opencode 2>/dev/null || true)"
    fi
    if [[ -z "${_OPENCODE_BIN}" ]]; then
        # 环境里还没装：按 agent 系列约定运行部署内安装脚本，再重新探测一次
        _agent_runtime_ensure_agent opencode || true
        _OPENCODE_BIN="$(_agent_runtime_locate_binary opencode)" || _OPENCODE_BIN=""
    fi
    if [[ -z "${_OPENCODE_BIN}" ]]; then
        echo "###${_NAME}: ERROR: 未找到 opencode，请安装 opencode 或设置 OPENCODE_BIN###" >&2
        exit 127
    fi

    # ---- 参数解析：模型/途径覆盖 + 无人值守驱动选项 ----
    # 用法: ${_NAME} [pay|go|gpt] [--model MODEL] [--variant LEVEL] [-file PATH] [-time DUR]
    #   --model MODEL     : 直接指定模型 ID；也可用 OPENCODE_MODEL 环境变量覆盖。
    #                       未指定时按两层默认取（显式选途径时途径默认优先，否则 agent 自身默认优先）：
    #                       providers.<途径>.default_models.opencode 与 agents.opencode.model 互为一层，高优先层缺值回退另一层。
    #   --variant LEVEL   : 直接指定 build agent 的 variant（max/xhigh/high/low 等）。
    #   -file/--file PATH : 驱动模式——prompt 回合完成后以文件内容为第一条指令，
    #                       之后每 --time 间隔向同一会话发送「继续」，直至 Ctrl+C 或连续 3 次失败
    #   -time/--time DUR  : 「继续」发送间隔，纯数字=秒；支持 s/m/h 后缀（如 30s/5m/2h），默认 30s
    # 不给驱动选项时保持原有 TUI 交互模式不变
    local MODEL_OVERRIDE="${OPENCODE_MODEL:-}"
    local VARIANT_OVERRIDE="${OPENCODE_VARIANT:-}"
    local PROVIDER_OVERRIDE="${OPENCODE_PROVIDER:-}"
    local MODEL_ID MODEL_NAME VARIANT="" DRIVE_FILE="" DRIVE_INTERVAL="" DRIVE_MODE=0
    local MODEL_EXPLICIT=0 VARIANT_EXPLICIT=0
    local MAX_TURNS_RAW="${AGENT_MAX_TURNS:-100}"
    local MAX_RUNTIME_RAW="${AGENT_MAX_RUNTIME:-0}"
    local STOP_FILE_ARG="${AGENT_STOP_PATH:-}"
    local RESUME_RUN_ID="${AGENT_RESUME_RUN_ID:-}"
    local ONCE_MODE="${AGENT_ONCE:-0}"
    [[ -n "${MODEL_OVERRIDE}" ]] && MODEL_EXPLICIT=1
    [[ -n "${VARIANT_OVERRIDE}" ]] && VARIANT_EXPLICIT=1
    while (( $# )); do
        case "$1" in
            pay|go|gpt|deepseek-pay|opencode-go|custom-gpt)
                PROVIDER_OVERRIDE="$(_provider_alias "$1")"; shift;;
            --model)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少模型参数###" >&2; exit 64; fi
                MODEL_OVERRIDE="$2"; MODEL_EXPLICIT=1; shift 2;;
            --variant)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少等级参数###" >&2; exit 64; fi
                VARIANT_OVERRIDE="$2"; VARIANT_EXPLICIT=1; shift 2;;
            --help)
                echo "用法: ${_NAME} [pay|go|gpt] [--model MODEL] [--variant LEVEL] [-file PATH] [-time DUR]"
                echo "供应商快捷词: pay=deepseek-pay / go=opencode-go / gpt=custom-gpt（如 ${_NAME} gpt）。"
                echo "模型: 两层默认——显式选途径（快捷词或 OPENCODE_PROVIDER 环境变量）时优先取 providers.<途径>.default_models.opencode，否则优先取 agents.opencode.model，缺值回退另一层；--model/OPENCODE_MODEL 直接覆盖。"
                echo "不给驱动选项时进入 OpenCode TUI，给出 -file/-time 时进入驱动模式。"
                exit 0;;
            -file|--file)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少路径参数###" >&2; exit 64; fi
                DRIVE_FILE="$2"; DRIVE_MODE=1; shift 2;;
            -time|--time)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少时长参数###" >&2; exit 64; fi
                _ti_raw="$2"; DRIVE_MODE=1; shift 2;;
            --once)
                ONCE_MODE=1; DRIVE_MODE=1; shift;;
            --max-turns)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少回合数###" >&2; exit 64; fi
                MAX_TURNS_RAW="$2"; DRIVE_MODE=1; shift 2;;
            --max-runtime)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少时长参数###" >&2; exit 64; fi
                MAX_RUNTIME_RAW="$2"; DRIVE_MODE=1; shift 2;;
            --stop-file)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少路径参数###" >&2; exit 64; fi
                STOP_FILE_ARG="$2"; DRIVE_MODE=1; shift 2;;
            --resume)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少 run id###" >&2; exit 64; fi
                RESUME_RUN_ID="$2"; DRIVE_MODE=1; shift 2;;
            *) echo "###${_NAME}: ERROR: 未知参数 '$1'（用法: ${_NAME} [pay|go|gpt] [--model MODEL] [--variant LEVEL] [-file PATH] [-time 30s]）###" >&2; exit 64;;
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
    _max_turns_input="$MAX_TURNS_RAW"
    if ! MAX_TURNS_RAW="$(_parse_nonnegative_integer "${_max_turns_input}")"; then
        echo "###${_NAME}: ERROR: --max-turns '${_max_turns_input}' 必须是非负整数###" >&2
        exit 64
    fi
    _max_runtime_input="$MAX_RUNTIME_RAW"
    if ! MAX_RUNTIME_RAW="$(_parse_runtime_limit "${_max_runtime_input}")"; then
        echo "###${_NAME}: ERROR: --max-runtime '${_max_runtime_input}' 格式无效（示例: 0 / 30 / 5m / 2h）###" >&2
        exit 64
    fi
    unset _max_turns_input _max_runtime_input

    # 模型选择（两层默认：显式选途径时 providers 层优先，否则 agent 层优先；高优先层缺值回退另一层）：
    #   1) --model/OPENCODE_MODEL 显式覆盖；
    #   2) 显式途径时取 providers.<途径>.default_models.opencode，缺省回退 agents.opencode.model；
    #   3) 途径来自 agents.opencode.provider 时取 agents.opencode.model，缺省回退途径默认模型。
    # 两层皆空时启动报错。
    local _op_provider="$(_provider_alias "${PROVIDER_OVERRIDE:-${_CFG_AGENTS_OPENCODE_PROVIDER}}")"
    if [[ -z "${_op_provider}" ]]; then
        echo "###${_NAME}: ERROR: 未指定途径（命令行快捷词 pay|go|gpt、OPENCODE_PROVIDER 环境变量或 agent-custom.json agents.opencode.provider）###" >&2
        exit 64
    fi
    # 是否由用户显式指定途径（命令行快捷词或 OPENCODE_PROVIDER 环境变量，两者一视同仁）
    local PROVIDER_EXPLICIT=0
    if [[ -n "${PROVIDER_OVERRIDE}" ]]; then PROVIDER_EXPLICIT=1; fi
    local _op_agent_model="${_CFG_AGENTS_OPENCODE_MODEL:-}"
    local _op_provider_model
    _op_provider_model="$(_cfg_provider_default_model "${_op_provider}" opencode)"
    local _op_model_label="（途径默认）"
    if [[ -n "${MODEL_OVERRIDE}" ]]; then
        MODEL_ID="${MODEL_OVERRIDE}"
        _op_model_label="（override）"
    elif (( PROVIDER_EXPLICIT )) && [[ -n "${_op_provider_model}" ]]; then
        MODEL_ID="${_op_provider_model}"
    elif [[ -n "${_op_agent_model}" ]]; then
        MODEL_ID="${_op_agent_model}"
        _op_model_label="（agent 默认）"
    else
        MODEL_ID="${_op_provider_model}"
    fi
    if [[ -z "${MODEL_ID}" ]]; then
        echo "###${_NAME}: ERROR: 途径 '${_op_provider}' 未定义 opencode 默认模型（见 agent-custom.json agents.opencode.model 或 providers.${_op_provider}.default_models.opencode）###" >&2
        exit 64
    fi
    MODEL_NAME="${MODEL_ID}${_op_model_label}"
    # 强度（variant，与模型同两层优先级）：override 仍在链尾最后赋值取胜
    #   agent 层内部顺序不变：agents.opencode.strength > 旧键 agents.opencode.variant
    local _op_agent_variant="${_CFG_AGENTS_OPENCODE_STRENGTH:-}"
    [[ -n "${_op_agent_variant}" ]] || _op_agent_variant="${_CFG_AGENTS_OPENCODE_VARIANT:-}"
    local _op_provider_variant
    _op_provider_variant="$(_cfg_provider_default_strength "${_op_provider}" opencode)"
    if (( PROVIDER_EXPLICIT )) && [[ -n "${_op_provider_variant}" ]]; then
        VARIANT="${_op_provider_variant}"
    elif [[ -n "${_op_agent_variant}" ]]; then
        VARIANT="${_op_agent_variant}"
    else
        VARIANT="${_op_provider_variant}"
    fi
    [[ -n "${VARIANT}" ]] || VARIANT="max"
    [[ -n "${VARIANT_OVERRIDE}" ]] && VARIANT="${VARIANT_OVERRIDE}"

    # 显式指定途径时提示该途径 key 未设置（op 仅注册 key 已设置的途径；显式途径下模型取自 providers 层，
    # 该途径若因缺 key 未注册，模型就落空了）——命令行快捷词与环境变量一视同仁
    if (( PROVIDER_EXPLICIT )); then
        local _op_pkey _op_key_var _op_key_name
        _op_pkey="$(_cfg_provider_key "${_op_provider}")"
        _op_key_var="_CFG_PROVIDERS_${_op_pkey}_ENV_KEY"
        _op_key_name="${!_op_key_var:-}"
        if [[ -n "${_op_key_name}" && -z "${!_op_key_name:-}" ]]; then
            echo "###${_NAME}: warning: 途径 '${_op_provider}' 的 key 环境变量 ${_op_key_name} 未设置，opencode 将无法请求该途径###" >&2
        fi
    fi

    local _runtime_mode=tui
    (( DRIVE_MODE )) && _runtime_mode=drive
    [[ -n "${RESUME_RUN_ID}" ]] && _runtime_mode=resume
    AGENT_ONCE="${ONCE_MODE}"
    AGENT_RUNTIME_REASONING=""
    AGENT_RUNTIME_VARIANT="$VARIANT"
    _agent_runtime_start_or_resume \
        opencode "$MODEL_ID" "$_runtime_mode" \
        "${AGENT_ROLE:-solo-agent}" "${AGENT_TIER:-standard}" \
        "${AGENT_POSTURE:-deep-worker}" "$MAX_TURNS_RAW" "$MAX_RUNTIME_RAW" \
        "$STOP_FILE_ARG" "$RESUME_RUN_ID" "$MODEL_EXPLICIT" 0 "$VARIANT_EXPLICIT" || exit $?
    MODEL_ID="${AGENT_RUNTIME_MODEL:-$MODEL_ID}"
    VARIANT="${AGENT_RUNTIME_VARIANT:-$VARIANT}"
    _load_prompt
    local _configure_agent_root="${AGENT_CONFIGURE_ROOT:-$(_agent_runtime_configure_root)}" _git_root _workspace_root
    local -a _agent_config_dirs _workspace_skill_roots _SEEN_SKILL_PATHS=()
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
    _agent_runtime_append_prompt_contract "$_runtime_mode" "$MODEL_ID" "" "$VARIANT"

    local _OP_AGENT="${_CFG_AGENTS_OPENCODE_AGENT:-build}"
    local _OP_AUTOUPDATE="${OPENCODE_AUTOUPDATE:-${_CFG_AGENTS_OPENCODE_AUTOUPDATE:-false}}"
    local _op_provider_json="${_CFG_OPENCODE_PROVIDER_JSON:-}"
    if [[ -z "${_op_provider_json}" ]]; then
        _op_provider_json='{}'
    fi
    export OPENCODE_CONFIG_CONTENT
    OPENCODE_CONFIG_CONTENT="$(printf '{"lsp":%s,"autoupdate":%s,"agent":{"%s":{"model":"%s","variant":"%s"}},"provider":%s}' \
        "${_CFG_AGENTS_OPENCODE_LSP:-true}" "${_OP_AUTOUPDATE}" "${_OP_AGENT}" "${MODEL_ID}" "${VARIANT}" \
        "${_op_provider_json}")"

    echo "============================================================"
    echo "  OpenCode: ${_OP_AGENT} | auto | ${MODEL_NAME} (${VARIANT})"
    echo "  run: ${AGENT_RUN_ID}"
    echo "  log: ${LOG_FILE}"
    echo "  state: ${AGENT_MANIFEST_FILE}"
    echo "  context: ${AGENT_CONTEXT_COUNT} 层说明文件（清单：${AGENT_CONTEXT_FILE}）"
    echo "  user-input list: ${LIST_FILE}"
    if (( _SECURE )); then
        echo "  launcher: secure/HPC"
    fi
    if (( AGENT_CONTEXT_COUNT > 0 )); then
        echo "  project context: ${AGENT_WORKSPACE_ROOT}（分层说明文件清单已注入 prompt）"
    else
        echo "  project context: 未发现分层说明文件（仅使用固定 prompt）"
    fi
    if (( DRIVE_MODE )); then
        echo "  drive mode: ON | interval=${DRIVE_INTERVAL}s | max-turns=${AGENT_MAX_TURNS} | max-runtime=${AGENT_MAX_RUNTIME}s | first-instruction=${DRIVE_FILE:-<无，仅继续循环>}"
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
        _rec_jf="${AGENT_RUN_DIR}/export.json"
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
        # 原有 TUI 交互模式（无驱动选项时保持原生交互）
        _agent_runtime_turn_begin
        "${_OPENCODE_BIN}" --agent "${_OP_AGENT}" --auto --prompt "${PROMPT}" \
                --print-logs --log-level DEBUG \
                2> "${LOG_FILE}"
        _run_rc=$?
        if (( _run_rc == 0 )); then
            _agent_runtime_turn_success
        else
            _agent_runtime_turn_failure
        fi
        return "${_run_rc}"
    else
        # ---- 驱动模式：headless opencode run 链式驱动 ----
        # 回合1 prompt → 从日志提取 session.id →（可选）回合2 文件首指令 → 每 N 秒「继续」
        if [[ -n "${DRIVE_FILE}" && ! -r "${DRIVE_FILE}" ]]; then
            echo "###${_NAME}: ERROR: --file '${DRIVE_FILE}' 不存在或不可读###" >&2
            exit 66
        fi
        if _agent_runtime_stop_file_requested; then
            echo "logs -> ${LOG_FILE}"
            return 0
        fi
        _live_log
        _drv_sid="${AGENT_SESSION_ID:-}"
        if [[ -n "${RESUME_RUN_ID}" ]]; then
            if [[ -z "${_drv_sid}" ]]; then
                echo "###${_NAME}: ERROR: 可恢复会话没有 session_id，驱动终止###" >&2
                exit 1
            fi
            echo "---- drive: resume session=${_drv_sid} interval=${DRIVE_INTERVAL}s ----"
        else
            echo "---- drive: prompt round start $(date "+%F-%T") ----"
            _agent_runtime_turn_begin
            "${_OPENCODE_BIN}" run --agent "${_OP_AGENT}" --auto --print-logs --log-level DEBUG "${PROMPT}" \
                    2> "${LOG_FILE}"
            _drv_rc=$?
            if (( _drv_rc != 0 )); then
                _agent_runtime_turn_failure
                echo "###${_NAME}: ERROR: prompt 回合失败（退出码 ${_drv_rc}），驱动终止###" >&2
                exit "${_drv_rc}"
            fi
            _agent_runtime_turn_success
            _drv_sid="$(grep -o 'session.id=[A-Za-z0-9_-]*' "${LOG_FILE}" 2>/dev/null | head -1 | cut -d= -f2)"
            if [[ -z "${_drv_sid}" ]]; then
                echo "###${_NAME}: ERROR: 无法从 ${LOG_FILE} 提取 session.id，驱动终止###" >&2
                exit 1
            fi
            _agent_runtime_set_session "${_drv_sid}" ""
        fi
        echo "---- drive: session=${_drv_sid} interval=${DRIVE_INTERVAL}s ----"
        if [[ -n "${DRIVE_FILE}" ]]; then
            _drv_instr="$(<"${DRIVE_FILE}")"
            echo "---- drive: first instruction <- ${DRIVE_FILE}（$(wc -c < "${DRIVE_FILE}") 字节）$(date "+%F-%T") ----"
            _agent_runtime_turn_begin
            "${_OPENCODE_BIN}" run -s "${_drv_sid}" --agent "${_OP_AGENT}" --auto --print-logs --log-level DEBUG "${_drv_instr}" \
                    2>> "${LOG_FILE}"
            _drv_rc=$?
            if (( _drv_rc == 0 )); then
                _agent_runtime_turn_success
            else
                _agent_runtime_turn_failure
            fi
            if (( _drv_rc != 0 )); then
                echo "###${_NAME}: warning: 首条指令回合退出码 ${_drv_rc}，仍进入继续循环###" >&2
            fi
            unset _drv_instr
        else
            echo "---- drive: 未提供 -file，跳过首条指令直接进入继续循环 ----"
        fi
        if (( ONCE_MODE )); then
            if [[ -n "${RESUME_RUN_ID}" && -z "${DRIVE_FILE}" ]]; then
                _agent_runtime_turn_begin
                "${_OPENCODE_BIN}" run -s "${_drv_sid}" --agent "${_OP_AGENT}" --auto --print-logs --log-level DEBUG "继续" \
                        2>> "${LOG_FILE}"
                _drv_rc=$?
                if (( _drv_rc == 0 )); then
                    _agent_runtime_turn_success
                    _agent_runtime_mark finished "resume once"
                    echo "logs -> ${LOG_FILE}"
                    return 0
                fi
                _agent_runtime_turn_failure
                _agent_runtime_mark failed "resume once 失败" "${_drv_rc}"
                return "${_drv_rc}"
            fi
            _agent_runtime_should_stop 0 || true
            echo "logs -> ${LOG_FILE}"
            return 0
        fi
        _nudges=0
        _fails=0
        _loop_rc=0
        while :; do
            if _agent_runtime_should_stop "${_nudges}"; then
                break
            fi
            sleep "${DRIVE_INTERVAL}"
            if _agent_runtime_should_stop "${_nudges}"; then
                break
            fi
            _agent_runtime_turn_begin
            if "${_OPENCODE_BIN}" run -s "${_drv_sid}" --agent "${_OP_AGENT}" --auto --print-logs --log-level DEBUG "继续" \
                    2>> "${LOG_FILE}"; then
                _agent_runtime_turn_success
                _nudges=$((_nudges + 1))
                _fails=0
                echo "---- drive: 继续 #${_nudges} ok $(date "+%F-%T") ----"
            else
                _drv_rc=$?
                _agent_runtime_turn_failure
                _fails=$((_fails + 1))
                echo "###${_NAME}: warning: 继续发送失败 ${_fails}/3（退出码 ${_drv_rc}）###" >&2
                if (( _fails >= 3 )); then
                    echo "###${_NAME}: ERROR: 连续 3 次「继续」失败，驱动循环终止（累计成功 ${_nudges} 次）###" >&2
                    _agent_runtime_mark blocked "连续 3 次继续失败" "${_drv_rc}"
                    _loop_rc=1
                    break
                fi
            fi
        done
        _drive_result="${_loop_rc:-0}"
        unset _drv_sid _drv_rc _nudges _fails _loop_rc
        echo "logs -> ${LOG_FILE}"
        return "${_drive_result}"
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

# Codex 模型元数据目录：Codex 内置目录只含 OpenAI 系模型，三方模型（deepseek 等）启动时
# 会告警「Model metadata for `X` not found. Defaulting to fallback metadata…」。这里以
# `codex debug models` 导出的内置目录为底，克隆模板条目补一条自定义元数据，缓存于
# data/cache/ 并输出文件路径（经 --config model_catalog_json 注入）。模型已在内置目录中、
# 或条件不具备（无 python3 等）时输出空：不注入、保持 Codex 原生行为。
_codex_model_catalog() {
    local _bin="$1" _model="$2" _display="$3" _template="$4" _ctx="$5" _compact="$6"
    local _py="${_AGENT_PYTHON:-python3}"
    command -v "${_py}" >/dev/null 2>&1 || return 0
    [[ -n "${_bin}" && -x "${_bin}" && -n "${_model}" ]] || return 0
    # 数据根由 _agent_runtime_init 解析（部署自洽 + HOME 回退）；拿不到时不注入模型目录
    local _data_root="${AGENT_DATA_ROOT:-}"
    [[ -n "$_data_root" ]] || _data_root="$(_agent_runtime_resolve_data_root 2>/dev/null || true)"
    [[ -n "$_data_root" ]] || return 0
    local _cache_dir="${_data_root}/cache"
    local _ver
    _ver="$("${_bin}" --version 2>/dev/null | head -n 1)" || return 0
    [[ -n "${_ver}" ]] || return 0
    _ver="$(printf '%s' "${_ver}" | tr -c 'A-Za-z0-9._-' '-')"
    [[ -n "${_ver}" ]] || return 0
    local _base="${_cache_dir}/codex-models-${_ver}.json"
    if [[ ! -s "${_base}" ]]; then
        mkdir -p -- "${_cache_dir}" 2>/dev/null || return 0
        local _tmp
        _tmp="$(mktemp "${_cache_dir}/.codex-models.XXXXXX")" || return 0
        if "${_bin}" debug models >"${_tmp}" 2>/dev/null && [[ -s "${_tmp}" ]]; then
            mv -f -- "${_tmp}" "${_base}" 2>/dev/null || true
        else
            rm -f -- "${_tmp}" 2>/dev/null || true
            return 0
        fi
        [[ -s "${_base}" ]] || return 0
    fi
    local _out
    if ! _out="$("${_py}" - "${_base}" "${_cache_dir}" "${_ver}" "${_model}" "${_display}" "${_template}" "${_ctx}" "${_compact}" <<'PYEOF' 2>/dev/null
import hashlib
import json
import os
import re
import sys

base_path, cache_dir, version, model, display, template, ctx, compact = sys.argv[1:9]

def sanitize(text):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
    return cleaned or "model"

def as_int(value, fallback):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback

try:
    with open(base_path, encoding="utf-8") as handle:
        catalog = json.load(handle)
except Exception as exc:
    raise SystemExit("无法读取内置模型目录 %s：%s" % (base_path, exc))

models = catalog.get("models") if isinstance(catalog, dict) else None
if not isinstance(models, list) or not models:
    sys.exit(0)

if any(entry.get("slug") == model for entry in models):
    sys.exit(0)  # 内置目录已含该模型：不注入，保持原生行为

tmpl = next((entry for entry in models if entry.get("slug") == template), None)
if tmpl is None:  # 模板缺失时回退到任一含指令文本的条目
    tmpl = next((entry for entry in models if entry.get("base_instructions") or entry.get("model_messages")), None)
if tmpl is None:
    sys.exit(0)

levels = {}
for entry in models:
    for level in entry.get("supported_reasoning_levels") or []:
        if isinstance(level, dict) and level.get("effort"):
            levels.setdefault(level["effort"], level)
order = ["minimal", "low", "medium", "high", "xhigh", "max", "ultra"]
ordered = sorted(levels, key=lambda name: (order.index(name) if name in order else len(order), name))

entry = json.loads(json.dumps(tmpl))
entry.update({
    "slug": model,
    "display_name": display or model,
    "description": "%s（自定义模型目录条目）" % (display or model),
    "priority": 50,
    "upgrade": None,
    "context_window": as_int(ctx, entry.get("context_window")),
    "max_context_window": as_int(ctx, entry.get("max_context_window") or entry.get("context_window")),
    "auto_compact_token_limit": as_int(compact, entry.get("auto_compact_token_limit")),
    "supported_reasoning_levels": [levels[name] for name in ordered] or entry.get("supported_reasoning_levels"),
})

key = hashlib.sha1("|".join([version, model, display or "", template or "", str(ctx), str(compact)]).encode("utf-8")).hexdigest()[:12]
out_path = os.path.join(cache_dir, "codex-models-%s-%s-%s.json" % (sanitize(version), sanitize(model), key))
if not os.path.exists(out_path):
    catalog["models"] = list(models) + [entry]
    tmp_path = "%s.tmp.%d" % (out_path, os.getpid())
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(catalog, handle, ensure_ascii=False)
    os.replace(tmp_path, out_path)
print(out_path)
PYEOF
    )"; then
        echo "###${_NAME}: warning: Codex 模型目录生成失败，保留内置 fallback 元数据###" >&2
        return 0
    fi
    [[ -n "${_out}" && -f "${_out}" ]] || return 0
    # 最小自检：本次 Codex 必须能加载该目录，否则不注入（避免版本差异下未知配置项拖垮启动）
    if ! "${_bin}" debug models -c "model_catalog_json=\"${_out}\"" >/dev/null 2>&1; then
        echo "###${_NAME}: warning: Codex 无法加载模型目录 ${_out}，本次不注入###" >&2
        return 0
    fi
    printf '%s\n' "${_out}"
}

run_codex() {
    local _CODEX_BIN="${CODEX_BIN:-}"
    if (( _SECURE )) && [[ -z "${_CODEX_BIN}" && -n "${_CFG_AGENTS_CODEX_SECURE_BINARY:-}" ]]; then
        # HPC/secure 变体：优先使用 agent-custom.json 的 agents.codex.secure_binary 部署路径，
        # 缺失时由 _prepare_secure_binary 从 PATH 中的 codex 完整复制（非符号链接）
        _CODEX_BIN="$(_prepare_secure_binary codex "${_CFG_AGENTS_CODEX_SECURE_BINARY}" CODEX_BIN)" || exit $?
    fi
    if [[ -z "${_CODEX_BIN}" ]]; then
        _CODEX_BIN="$(command -v codex 2>/dev/null || true)"
    fi
    if [[ -z "${_CODEX_BIN}" ]]; then
        # 环境里还没装：按 agent 系列约定运行部署内安装脚本，再重新探测一次
        _agent_runtime_ensure_agent codex || true
        _CODEX_BIN="$(_agent_runtime_locate_binary codex)" || _CODEX_BIN=""
    fi
    if [[ -z "${_CODEX_BIN}" ]]; then
        echo "###${_NAME}: ERROR: 未找到 codex，请安装 Codex CLI 或设置 CODEX_BIN###" >&2
        exit 127
    fi

    # 初始注入包含固定 prompt、全局 agent 配置目录清单以及全局/工作区 skill 清单。
    # 这里只列出路径，不读取配置内容；模型需要时再按需读取。
    local _configure_agent_root="${AGENT_CONFIGURE_ROOT:-$(_agent_runtime_configure_root)}" _git_root _workspace_root
    local -a _agent_config_dirs _workspace_skill_roots _SEEN_SKILL_PATHS=()
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
    # dirs/skills 注入在 _load_prompt 之后执行（_load_prompt 会重置 PROMPT）

    # ---- 参数解析：模型/途径覆盖 + 无人值守驱动选项 ----
    # 用法: ${_NAME} [pay|go|gpt] [--model MODEL]
    #                       [-time DUR]
    #   -time/--time DUR  : 驱动模式中「继续」发送间隔，纯数字=秒；支持 s/m/h 后缀（默认 30s）。
    #   --model MODEL     : 直接指定 Codex 模型；也可用 CODEX_MODEL 环境变量覆盖。
    #                       未指定时按两层默认取（显式选途径时途径默认优先，否则 agent 自身默认优先）：
    #                       providers.<途径>.default_models.codex 与 agents.codex.model 互为一层，高优先层缺值回退另一层。
    #   --reasoning-effort LEVEL : 直接指定 reasoning effort（low/medium/high/xhigh/max/ultra），
    #                              同两层优先级：途径默认强度与 agents.codex.strength 互为一层，缺值回退另一层。
    local MODEL_OVERRIDE="${CODEX_MODEL:-}"
    local REASONING_OVERRIDE="${CODEX_REASONING_EFFORT:-}"
    local PROVIDER_OVERRIDE="${CODEX_PROVIDER_ID:-}"
    local CODEX_SANDBOX_MODE="${CODEX_SANDBOX:-${_CFG_AGENTS_CODEX_SANDBOX:-danger-full-access}}"
    local CODEX_APPROVAL_POLICY="${CODEX_APPROVAL:-${_CFG_AGENTS_CODEX_APPROVAL:-never}}"
    local MODEL_ID MODEL_NAME REASONING_EFFORT DRIVE_INTERVAL="" DRIVE_MODE=0
    local MODEL_EXPLICIT=0 REASONING_EXPLICIT=0
    local MAX_TURNS_RAW="${AGENT_MAX_TURNS:-100}"
    local MAX_RUNTIME_RAW="${AGENT_MAX_RUNTIME:-0}"
    local STOP_FILE_ARG="${AGENT_STOP_PATH:-}"
    local RESUME_RUN_ID="${AGENT_RESUME_RUN_ID:-}"
    local ONCE_MODE="${AGENT_ONCE:-0}"
    [[ -n "${MODEL_OVERRIDE}" ]] && MODEL_EXPLICIT=1
    [[ -n "${REASONING_OVERRIDE}" ]] && REASONING_EXPLICIT=1
    while (( $# )); do
        case "$1" in
            pay|go|gpt|deepseek-pay|opencode-go|custom-gpt)
                PROVIDER_OVERRIDE="$(_provider_alias "$1")"; shift;;
            --model|-model)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少模型参数###" >&2; exit 64; fi
                MODEL_OVERRIDE="$2"; MODEL_EXPLICIT=1; shift 2;;
            --reasoning-effort)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少等级参数###" >&2; exit 64; fi
                REASONING_OVERRIDE="$2"; REASONING_EXPLICIT=1; shift 2;;
            --sandbox)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少策略参数###" >&2; exit 64; fi
                CODEX_SANDBOX_MODE="$2"; shift 2;;
            --ask-for-approval)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少策略参数###" >&2; exit 64; fi
                CODEX_APPROVAL_POLICY="$2"; shift 2;;
            -time|--time)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少时长参数###" >&2; exit 64; fi
                _ti_raw="$2"; DRIVE_MODE=1; shift 2;;
            --once)
                ONCE_MODE=1; DRIVE_MODE=1; shift;;
            --max-turns)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少回合数###" >&2; exit 64; fi
                MAX_TURNS_RAW="$2"; DRIVE_MODE=1; shift 2;;
            --max-runtime)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少时长参数###" >&2; exit 64; fi
                MAX_RUNTIME_RAW="$2"; DRIVE_MODE=1; shift 2;;
            --stop-file)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少路径参数###" >&2; exit 64; fi
                STOP_FILE_ARG="$2"; DRIVE_MODE=1; shift 2;;
            --resume)
                if [[ $# -lt 2 ]]; then echo "###${_NAME}: ERROR: $1 缺少 run id###" >&2; exit 64; fi
                RESUME_RUN_ID="$2"; DRIVE_MODE=1; shift 2;;
            --help)
                echo "用法: ${_NAME} [pay|go|gpt] [--model MODEL] [--reasoning-effort LEVEL] [-time DUR]"
                echo "驱动控制: [--once] [--max-turns N] [--max-runtime DUR] [--stop-file PATH] [--resume RUN_ID]"
                echo "供应商快捷词: pay=deepseek-pay / go=opencode-go / gpt=custom-gpt（如 ${_NAME} pay）。"
                echo "模型: 两层默认——显式选途径（快捷词或 CODEX_PROVIDER_ID 环境变量）时优先取 providers.<途径>.default_models.codex，否则优先取 agents.codex.model，缺值回退另一层；--model/CODEX_MODEL 直接覆盖。"
                echo "不给驱动选项时进入 Codex TUI，给出驱动选项时进入 exec 模式。"
                exit 0;;
            *) echo "###${_NAME}: ERROR: 未知参数 '$1'（用法: ${_NAME} [pay|go|gpt] [--model MODEL] [-time 30s]）###" >&2; exit 64;;
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
    _max_turns_input="$MAX_TURNS_RAW"
    if ! MAX_TURNS_RAW="$(_parse_nonnegative_integer "${_max_turns_input}")"; then
        echo "###${_NAME}: ERROR: --max-turns '${_max_turns_input}' 必须是非负整数###" >&2
        exit 64
    fi
    _max_runtime_input="$MAX_RUNTIME_RAW"
    if ! MAX_RUNTIME_RAW="$(_parse_runtime_limit "${_max_runtime_input}")"; then
        echo "###${_NAME}: ERROR: --max-runtime '${_max_runtime_input}' 格式无效（示例: 0 / 30 / 5m / 2h）###" >&2
        exit 64
    fi
    unset _max_turns_input _max_runtime_input

    # 模型选择（两层默认：显式选途径时 providers 层优先，否则 agent 层优先；高优先层缺值回退另一层）：
    #   1) --model/CODEX_MODEL 显式覆盖；
    #   2) 显式途径时取 providers.<途径>.default_models.codex，缺省回退 agents.codex.model；
    #   3) 途径来自 agents.codex.provider 时取 agents.codex.model，缺省回退途径默认模型。
    # 两层皆空时启动报错。
    local _cx_provider="$(_provider_alias "${PROVIDER_OVERRIDE:-${_CFG_AGENTS_CODEX_PROVIDER}}")"
    if [[ -z "${_cx_provider}" ]]; then
        echo "###${_NAME}: ERROR: 未指定途径（命令行快捷词 pay|go|gpt、CODEX_PROVIDER_ID 环境变量或 agent-custom.json agents.codex.provider）###" >&2
        exit 64
    fi
    # 是否由用户显式指定途径（命令行快捷词或 CODEX_PROVIDER_ID 环境变量，两者一视同仁）
    local PROVIDER_EXPLICIT=0
    if [[ -n "${PROVIDER_OVERRIDE}" ]]; then PROVIDER_EXPLICIT=1; fi
    local _cx_agent_model="${_CFG_AGENTS_CODEX_MODEL:-}"
    local _cx_provider_model
    _cx_provider_model="$(_cfg_provider_default_model "${_cx_provider}" codex)"
    local _cx_model_label="（途径默认）"
    if [[ -n "${MODEL_OVERRIDE}" ]]; then
        MODEL_ID="${MODEL_OVERRIDE}"
        _cx_model_label="（override）"
    elif (( PROVIDER_EXPLICIT )) && [[ -n "${_cx_provider_model}" ]]; then
        MODEL_ID="${_cx_provider_model}"
    elif [[ -n "${_cx_agent_model}" ]]; then
        MODEL_ID="${_cx_agent_model}"
        _cx_model_label="（agent 默认）"
    else
        MODEL_ID="${_cx_provider_model}"
    fi
    if [[ -z "${MODEL_ID}" ]]; then
        echo "###${_NAME}: ERROR: 途径 '${_cx_provider}' 未定义 codex 默认模型（见 agent-custom.json agents.codex.model 或 providers.${_cx_provider}.default_models.codex）###" >&2
        exit 64
    fi
    MODEL_NAME="${MODEL_ID}${_cx_model_label}"
    # 强度（reasoning，与模型同两层优先级）：override 仍在链尾最后赋值取胜
    #   agent 层内部顺序不变：agents.codex.strength > 旧键 agents.codex.reasoning
    local _cx_agent_reasoning="${_CFG_AGENTS_CODEX_STRENGTH:-}"
    [[ -n "${_cx_agent_reasoning}" ]] || _cx_agent_reasoning="${_CFG_AGENTS_CODEX_REASONING:-}"
    local _cx_provider_reasoning
    _cx_provider_reasoning="$(_cfg_provider_default_strength "${_cx_provider}" codex)"
    if (( PROVIDER_EXPLICIT )) && [[ -n "${_cx_provider_reasoning}" ]]; then
        REASONING_EFFORT="${_cx_provider_reasoning}"
    elif [[ -n "${_cx_agent_reasoning}" ]]; then
        REASONING_EFFORT="${_cx_agent_reasoning}"
    else
        REASONING_EFFORT="${_cx_provider_reasoning}"
    fi
    [[ -n "${REASONING_EFFORT}" ]] || REASONING_EFFORT="max"
    [[ -n "${REASONING_OVERRIDE}" ]] && REASONING_EFFORT="${REASONING_OVERRIDE}"

    local _runtime_mode=tui
    (( DRIVE_MODE )) && _runtime_mode=drive
    [[ -n "${RESUME_RUN_ID}" ]] && _runtime_mode=resume
    AGENT_ONCE="${ONCE_MODE}"
    AGENT_RUNTIME_REASONING="$REASONING_EFFORT"
    AGENT_RUNTIME_VARIANT=""
    _agent_runtime_start_or_resume \
        codex "$MODEL_ID" "$_runtime_mode" \
        "${AGENT_ROLE:-solo-agent}" "${AGENT_TIER:-standard}" \
        "${AGENT_POSTURE:-frontier-orchestrator}" "$MAX_TURNS_RAW" "$MAX_RUNTIME_RAW" \
        "$STOP_FILE_ARG" "$RESUME_RUN_ID" "$MODEL_EXPLICIT" "$REASONING_EXPLICIT" 0 || exit $?
    MODEL_ID="${AGENT_RUNTIME_MODEL:-$MODEL_ID}"
    REASONING_EFFORT="${AGENT_RUNTIME_REASONING:-$REASONING_EFFORT}"
    _load_prompt
    _append_agent_config_dirs "全局 Agent 配置目录（按需读取）" "${_agent_config_dirs[@]}"
    _append_skill_list "全局技能（${_agent_config_dirs[0]}）" "${_agent_config_dirs[0]}"
    _append_skill_list "当前工作目录技能（${_PWD}）" "${_workspace_skill_roots[@]}"
    unset _git_root _workspace_root _workspace_skill_roots
    _agent_runtime_append_prompt_contract "$_runtime_mode" "$MODEL_ID" "$REASONING_EFFORT" ""
    local CODEX_PROVIDER_ID="${_cx_provider}"
    local _cx_pkey _cx_pvar
    _cx_pkey="$(_cfg_provider_key "${CODEX_PROVIDER_ID}")"
    _cx_pvar="_CFG_PROVIDERS_${_cx_pkey}_ENV_KEY"
    local CODEX_PROVIDER_ENV_KEY="${CODEX_PROVIDER_ENV_KEY:-${!_cx_pvar:-}}"
    _cx_pvar="_CFG_PROVIDERS_${_cx_pkey}_BASE_URL"
    local CODEX_PROVIDER_BASE_URL="${CODEX_PROVIDER_BASE_URL:-${!_cx_pvar:-}}"
    _cx_pvar="_CFG_PROVIDERS_${_cx_pkey}_WIRE_API"
    local CODEX_PROVIDER_WIRE_API="${CODEX_PROVIDER_WIRE_API:-${!_cx_pvar:-responses}}"
    _cx_pvar="_CFG_PROVIDERS_${_cx_pkey}_SUPPORTS_WEBSOCKETS"
    local CODEX_PROVIDER_SUPPORTS_WEBSOCKETS="${CODEX_PROVIDER_SUPPORTS_WEBSOCKETS:-${!_cx_pvar:-false}}"
    local CODEX_PROVIDER_NAME="${CODEX_PROVIDER_NAME:-${CODEX_PROVIDER_ID}}"
    if [[ -z "${CODEX_PROVIDER_BASE_URL}" ]]; then
        echo "###${_NAME}: warning: 途径 '${CODEX_PROVIDER_ID}' 未配置 base_url（见 agent-config.json / agent-custom.json）###" >&2
    fi
    local CODEX_MODEL_CONTEXT_WINDOW="${CODEX_MODEL_CONTEXT_WINDOW:-${_CFG_AGENTS_CODEX_CONFIG_MODEL_CONTEXT_WINDOW:-1000000}}"
    local CODEX_CHECK_FOR_UPDATE_ON_STARTUP="${CODEX_CHECK_FOR_UPDATE_ON_STARTUP:-${_CFG_AGENTS_CODEX_CONFIG_CHECK_FOR_UPDATE_ON_STARTUP:-false}}"
    local CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT="${CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT:-${_CFG_AGENTS_CODEX_CONFIG_MODEL_AUTO_COMPACT_TOKEN_LIMIT:-900000}}"
    # 模型元数据目录：为内置目录之外的模型（deepseek 等）补齐元数据，消除启动告警
    local CODEX_MODEL_CATALOG="${CODEX_MODEL_CATALOG:-}"
    if [[ -z "${CODEX_MODEL_CATALOG}" && "${_CFG_AGENTS_CODEX_MODEL_CATALOG_ENABLED:-true}" != "false" ]]; then
        CODEX_MODEL_CATALOG="$(_codex_model_catalog \
            "${_CODEX_BIN}" "${MODEL_ID}" \
            "$(_cfg_codex_model_display_name "${MODEL_ID}")" \
            "${_CFG_AGENTS_CODEX_MODEL_CATALOG_CLONE_TEMPLATE:-gpt-5.4-mini}" \
            "${CODEX_MODEL_CONTEXT_WINDOW}" "${CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT}")"
    fi
    local CODEX_SERVICE_TIER="${CODEX_SERVICE_TIER:-${_CFG_AGENTS_CODEX_CONFIG_SERVICE_TIER:-}}"
    local CODEX_FAST_MODE="${CODEX_FAST_MODE:-${_CFG_AGENTS_CODEX_CONFIG_FEATURES_FAST_MODE:-false}}"
    local CODEX_PERSONALITY="${CODEX_PERSONALITY:-${_CFG_AGENTS_CODEX_CONFIG_PERSONALITY:-pragmatic}}"
    local CODEX_APPROVALS_REVIEWER="${CODEX_APPROVALS_REVIEWER:-${_CFG_AGENTS_CODEX_CONFIG_APPROVALS_REVIEWER:-auto_review}}"
    local CODEX_FORCED_LOGIN_METHOD="${CODEX_FORCED_LOGIN_METHOD:-${_CFG_AGENTS_CODEX_CONFIG_FORCED_LOGIN_METHOD:-api}}"
    local CODEX_TUI_STATUS_LINE="${CODEX_TUI_STATUS_LINE:-${_CFG_AGENTS_CODEX_CONFIG_TUI_STATUS_LINE:-${_CFG_STATUSLINE_SEGMENTS:-[\"model-with-reasoning\",\"current-dir\",\"hostname\",\"branch-changes\",\"run-state\",\"permissions\",\"approval-mode\",\"context-used\",\"weekly-limit\",\"estimated-thread-cost\",\"thread-id\",\"fast-mode\",\"task-progress\"]}}}"
    local CODEX_TUI_STATUS_LINE_USE_COLORS="${CODEX_TUI_STATUS_LINE_USE_COLORS:-${_CFG_AGENTS_CODEX_CONFIG_TUI_STATUS_LINE_USE_COLORS:-${_CFG_STATUSLINE_USE_COLORS:-true}}}"

    # 构造数组，避免工作目录、模型名和 prompt 中的空格/特殊字符被重新分词。
    local -a CODEX_COMMON_ARGS CODEX_AGENT_DIR_ARGS CODEX_INITIAL_ARGS
    CODEX_COMMON_ARGS=(
        --model "${MODEL_ID}"
        --config "forced_login_method=\"${CODEX_FORCED_LOGIN_METHOD}\""
        --config "model_provider=\"${CODEX_PROVIDER_ID}\""
        --config "model_context_window=${CODEX_MODEL_CONTEXT_WINDOW}"
        --config "check_for_update_on_startup=${CODEX_CHECK_FOR_UPDATE_ON_STARTUP}"
        --config "model_auto_compact_token_limit=${CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT}"
        --config "personality=\"${CODEX_PERSONALITY}\""
        --config "approvals_reviewer=\"${CODEX_APPROVALS_REVIEWER}\""
        --config "model_providers.${CODEX_PROVIDER_ID}.name=\"${CODEX_PROVIDER_NAME}\""
        --config "model_providers.${CODEX_PROVIDER_ID}.base_url=\"${CODEX_PROVIDER_BASE_URL}\""
        --config "model_providers.${CODEX_PROVIDER_ID}.env_key=\"${CODEX_PROVIDER_ENV_KEY}\""
        --config "model_providers.${CODEX_PROVIDER_ID}.wire_api=\"${CODEX_PROVIDER_WIRE_API}\""
        --config "model_providers.${CODEX_PROVIDER_ID}.supports_websockets=${CODEX_PROVIDER_SUPPORTS_WEBSOCKETS}"
        --config "tui.status_line=${CODEX_TUI_STATUS_LINE}"
        --config "tui.status_line_use_colors=${CODEX_TUI_STATUS_LINE_USE_COLORS}"
        --config "features.fast_mode=${CODEX_FAST_MODE}"
        --config "model_reasoning_effort=\"${REASONING_EFFORT}\""
        --config "approval_policy=\"${CODEX_APPROVAL_POLICY}\""
        --config "sandbox_mode=\"${CODEX_SANDBOX_MODE}\""
    )
    if [[ -n "${CODEX_SERVICE_TIER}" ]]; then
        CODEX_COMMON_ARGS+=(--config "service_tier=\"${CODEX_SERVICE_TIER}\"")
    fi
    if [[ -n "${CODEX_MODEL_CATALOG}" ]]; then
        CODEX_COMMON_ARGS+=(--config "model_catalog_json=\"${CODEX_MODEL_CATALOG}\"")
    fi
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
    echo "  provider: ${CODEX_PROVIDER_ID} | tier=${CODEX_SERVICE_TIER:-standard} | personality=${CODEX_PERSONALITY}"
    if [[ -n "${CODEX_MODEL_CATALOG}" ]]; then
        echo "  catalog: 注入自定义模型元数据（${MODEL_ID}）"
    fi
    if [[ -n "${CODEX_PROVIDER_ENV_KEY}" && -z "${!CODEX_PROVIDER_ENV_KEY:-}" ]]; then
        echo "  auth: ${CODEX_PROVIDER_ENV_KEY} 未设置 —— 请先 export 该变量（缺失时请求会 401）"
    fi
    echo "  tui: status_line preset | colors=${CODEX_TUI_STATUS_LINE_USE_COLORS}"
    echo "  run: ${AGENT_RUN_ID}"
    echo "  log: ${LOG_FILE}"
    echo "  state: ${AGENT_MANIFEST_FILE}"
    echo "  context: ${AGENT_CONTEXT_COUNT} 层说明文件（清单：${AGENT_CONTEXT_FILE}）"
    echo "  agent config: ${_configure_agent_root}/{skills,tools,hooks,plugins}"
    if (( _SECURE )); then
        echo "  launcher: secure/HPC"
    fi
    if (( DRIVE_MODE )); then
        echo "  drive mode: ON | interval=${DRIVE_INTERVAL}s | max-turns=${AGENT_MAX_TURNS} | max-runtime=${AGENT_MAX_RUNTIME}s | prompt + 继续"
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
        _agent_runtime_turn_begin
        "${_CODEX_BIN}" "${CODEX_INITIAL_ARGS[@]}" -- "${PROMPT}" 2>"${LOG_FILE}"
        _run_rc=$?
        if (( _run_rc == 0 )); then
            _agent_runtime_turn_success
        else
            _agent_runtime_turn_failure
        fi
    else
        # ---- 驱动模式：headless codex exec → exec resume 链式驱动 ----
        # 回合1 prompt → thread.started → 每 N 秒发送固定的「继续」。
        if _agent_runtime_stop_file_requested; then
            echo "logs -> ${LOG_FILE}"
            return 0
        fi
        _live_log
        _drv_sid="${AGENT_THREAD_ID:-}"
        if [[ -n "${RESUME_RUN_ID}" ]]; then
            if [[ -z "${_drv_sid}" ]]; then
                echo "###${_NAME}: ERROR: 可恢复会话没有 thread_id，驱动终止###" >&2
                exit 1
            fi
            echo "---- drive: resume thread=${_drv_sid} interval=${DRIVE_INTERVAL}s ----"
        else
            echo "---- drive: prompt round start $(date "+%F-%T") ----"
            _agent_runtime_turn_begin
            if "${_CODEX_BIN}" exec "${CODEX_INITIAL_ARGS[@]}" --json -- "${PROMPT}" >>"${LOG_FILE}" 2>&1; then
                _drv_rc=0
            else
                _drv_rc=$?
            fi
            if (( _drv_rc != 0 )); then
                _agent_runtime_turn_failure
                echo "###${_NAME}: ERROR: prompt 回合失败（退出码 ${_drv_rc}），驱动终止###" >&2
                exit "${_drv_rc}"
            fi
            _agent_runtime_turn_success
            _drv_sid="$(_extract_thread_id "${LOG_FILE}")"
            if [[ -z "${_drv_sid}" ]]; then
                echo "###${_NAME}: ERROR: 无法从 ${LOG_FILE} 提取 thread_id，驱动终止###" >&2
                exit 1
            fi
            _agent_runtime_set_session "${_drv_sid}" "${_drv_sid}"
        fi
        echo "---- drive: thread=${_drv_sid} interval=${DRIVE_INTERVAL}s ----"
        echo "---- drive: prompt 已完成，进入继续循环 ----"
        if (( ONCE_MODE )); then
            if [[ -n "${RESUME_RUN_ID}" ]]; then
                _agent_runtime_turn_begin
                if "${_CODEX_BIN}" exec resume "${CODEX_COMMON_ARGS[@]}" --json "${_drv_sid}" -- "继续" >>"${LOG_FILE}" 2>&1; then
                    _agent_runtime_turn_success
                    _agent_runtime_mark finished "resume once"
                    _run_rc=0
                else
                    _run_rc=$?
                    _agent_runtime_turn_failure
                    _agent_runtime_mark failed "resume once 失败" "${_run_rc}"
                fi
            else
                _agent_runtime_mark finished "once 模式"
                _run_rc=0
            fi
            echo "logs -> ${LOG_FILE}"
            return "${_run_rc}"
        fi
        _nudges=0
        _fails=0
        _loop_rc=0
        while :; do
            if _agent_runtime_should_stop "${_nudges}"; then
                break
            fi
            sleep "${DRIVE_INTERVAL}"
            if _agent_runtime_should_stop "${_nudges}"; then
                break
            fi
            _agent_runtime_turn_begin
            if "${_CODEX_BIN}" exec resume "${CODEX_COMMON_ARGS[@]}" --json "${_drv_sid}" -- "继续" >>"${LOG_FILE}" 2>&1; then
                _agent_runtime_turn_success
                _nudges=$((_nudges + 1))
                _fails=0
                echo "---- drive: 继续 #${_nudges} ok $(date "+%F-%T") ----"
            else
                _drv_rc=$?
                _agent_runtime_turn_failure
                _fails=$((_fails + 1))
                echo "###${_NAME}: warning: 继续发送失败 ${_fails}/3（退出码 ${_drv_rc}）###" >&2
                if (( _fails >= 3 )); then
                    echo "###${_NAME}: ERROR: 连续 3 次「继续」失败，驱动循环终止（累计成功 ${_nudges} 次）###" >&2
                    _agent_runtime_mark blocked "连续 3 次继续失败" "${_drv_rc}"
                    _loop_rc=1
                    break
                fi
            fi
        done
        _drive_result="${_loop_rc:-0}"
        unset _drv_sid _drv_rc _nudges _fails _loop_rc
        echo "logs -> ${LOG_FILE}"
        return "${_drive_result}"
    fi

    echo "logs -> ${LOG_FILE}"
    return "${_run_rc:-0}"
}

_migrate_legacy_keys
_agent_config_load

case "${_AGENT}" in
    claude)   run_claude "$@";;
    opencode) run_opencode "$@";;
    codex)    run_codex "$@";;
esac
_rc=$?
unset PROMPT _PWD
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
exit "${_rc}"
