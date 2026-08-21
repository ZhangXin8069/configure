#!/usr/bin/env bash
# Launch opencode: Build agent + auto + 可选模型 (-h/-o/-p/-f/-q/-k/-g/-m, 默认 -m) + debug logs
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

# 模型选择：默认 -m Build auto·Muse Spark 1.2 Contributor OpenCode Go (xhigh)；-o Ox Alpha Free (Unlimited) / -h Hy3 (high) / -p Pro / -f Flash / -q Qwen3.8 Max / -k Kimi K3 / -g GPT-5.6 Luna
# -m: Build auto·Muse Spark 1.2 Contributor OpenCode Go·xhigh
# -o: Build auto · Ox Alpha Free (Unlimited) OpenCode Go·max
VARIANT="max"
case "${1:--m}" in
    -m) MODEL_ID="opencode-go/muse-spark-1.2";   MODEL_NAME="Build auto·Muse Spark 1.2 Contributor OpenCode Go"; VARIANT="xhigh";;
    -o) MODEL_ID="opencode-go/ox-alpha-free";    MODEL_NAME="Build auto · Ox Alpha Free (Unlimited) OpenCode Go";;
    -p) MODEL_ID="opencode-go/deepseek-v4-pro";  MODEL_NAME="DeepSeek V4 Pro (New)";;
    -q) MODEL_ID="opencode-go/qwen3.8-max";      MODEL_NAME="Qwen3.8 Max";;
    -k) MODEL_ID="opencode-go/kimi-k3";          MODEL_NAME="Kimi K3";;
    -g) MODEL_ID="opencode-go/gpt-5.6-luna";     MODEL_NAME="GPT-5.6 Luna (2x usage)";;
    -f) MODEL_ID="opencode-go/deepseek-v4-flash"; MODEL_NAME="DeepSeek V4 Flash (2x usage)";;
    -h|*) MODEL_ID="opencode-go/hy3";            MODEL_NAME="Hy3"; VARIANT="high";;
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
echo "============================================================"

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
trap '_recover_inputs' EXIT
unset _rec_sid _rec_jf

opencode --agent build --auto --prompt "${PROMPT}" \
        --print-logs --log-level DEBUG \
        2> "${LOG_FILE}"

if [[ -s "${LIST_FILE}" ]]; then
    echo "user inputs -> ${LIST_FILE}（$(wc -l < "${LIST_FILE}") 行）"
elif [[ -f "${LIST_FILE}" ]]; then
    echo "user inputs -> ${LIST_FILE}（空）"
fi
echo "logs -> ${LOG_FILE}"
unset _PWD
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
