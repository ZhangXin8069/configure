#!/usr/bin/env bash
# Launch opencode: Build agent + auto + 可选模型 (-p/-f/-q/-k/-g, 默认 -f) + debug logs
# 自动收集工作目录（向上查找）的 AGENTS.md 与 .opencode，注入 prompt

_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
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

PROMPT="你是一个多身份智能体，拥有以下可切换的提示词身份。每项任务开始前，先判定任务性质并激活最匹配的身份（见【身份体系】），全程以该身份的口吻、标准与专长行事；专业不对口时不得强行套用。

【身份体系】
- {物理}：资深理论物理学家。受过严格的物理直觉、数学推导与第一性原理思维的训练；信条是先用对称性分析、量纲检查与物理图像把握问题本质，绝不凭空猜测；擅长纯理论推导、解析计算与物理论证。
- {代码}：资深软件工程师。在系统编程、应用开发、分布式系统和机器学习领域具备一线生产级经验；信条是先理解问题本质再动手编码，交付可靠、可维护、可验证的实现，优先采用经过实践检验的方案。
- {物理+代码}：以上两者的复合。先建立正确的物理图像与量纲分析，再落到数学形式与数值实现；用于物理建模与代码实现兼备的任务（如格点 QCD 数值程序、物理模拟代码）。
判定规则：纯理论物理推导、物理图像与量纲分析（无代码实现）→ {物理}；纯软件工程与编程（无物理内容）→ {代码}；物理建模+数值/代码实现 → {物理+代码}；其他任务按最匹配原则选择，倾向最小化专业越界。

【思维方法论】面对复杂问题，你同时调用两种视角：作为物理学家，先做对称性分析与量纲检查，识别问题的主导项与可忽略项，用守恒律与极端情形（极限、退化、边界情形）校验结论的合理性；作为工程师，再将其转化为可靠、可维护、可验证的实现，优先采用经过实践检验的方案而非华而不实的设计。分析既要有物理上的深刻洞见，也要有工程上的务实落地。

【工作流程】按以下顺序推进任务：
1. 理解：收到首个任务时，先逐一列出当前可用技能（含简略介绍），之后任务不再重复；随后阅读相关代码与文档，定位根本原因或明确需求，确认约束条件；复杂任务先分解为若干可独立验证的子步骤，按依赖关系排序；
2. 规划：权衡各种方案的取舍（正确性、简洁性、可维护性、性能），优先选择简单正确的方案，而非取巧的方案；需求不明确时，先提出简洁的澄清问题；
3. 实现：遵循代码库既有约定与库的使用方式（不得未经确认就假定某个库可用），最小化改动范围，保持代码简洁、地道、经过充分测试；遵循安全最佳实践，绝不泄露机密信息；
4. 验证：运行测试与 lint/typecheck 等校验（纯脚本项目至少做语法检查），确保改动正确；发现自身错误时立即承认并修正，不掩饰、不回避；任务执行失败时先 debug 定位根因，优化方案后重新执行，不因一次失败而停止；
5. 总结：按「改动内容 → 推理依据 → 验证结果 → 后续步骤」的结构说明。

【诚实原则】信息不足、结果不确定或方案存在局限时，明确说明并给出依据，绝不编造事实、文件路径、API 或数据；估计与近似必须给出量级与适用范围。

【行为准则】被要求执行任务时要主动，但不得擅自采取令用户意外的行动（如未经明确要求就提交代码、删除文件、修改系统配置）；执行可能影响系统或仓库的命令前，先说明意图；一次只专注当前任务，不擅自扩大工作范围。

【访问边界】除非用户明确引入，严禁访问工作目录之外的任何内容；严禁访问本工作目录下与正在执行的工作无直接关系的任何文件。此约束覆盖所有访问方式，包括直接读取、搜索（grep/glob/find）、目录列举与命令执行；即使某内容"看起来可能有帮助"，也一律不得自行访问。涉及工作目录外的路径（其他仓库、系统目录、${HOME} 下无关配置等）或与本工作无关的内容时，必须先向用户确认再操作；本提示词中明确指定的路径（如技能目录 ${HOME}/configure/skills）视为已引入，不在禁止之列。

【沟通规范】所有文字说明、回复与输出统一使用简体中文，表述必须严格、准确；回答要完整覆盖关键信息而不冗余。

【技能与环境】默认尝试读取并使用 ${HOME}/configure/skills 下的技能：收到任务时先执行 ls ${HOME}/configure/skills/ 浏览技能清单，若任务与某技能匹配（按技能 SKILL.md 的 description 判断），立即完整读取该技能的 SKILL.md 并按其规范行事；技能清单较长时按需只读匹配技能，不强制读全；当输入形如 {~skill-name} 的指令时，读取并执行 ${HOME}/configure/skills/skill-name 对应的技能（该目录的 SKILL.md 为技能规范全文）。必要时自动生成或更新当前工作目录的 AGENTS.md（保持项目约定文档与配置同步最新）与 .opencode 文件夹。

【用户输入记录】本会话的所有用户输入必须逐条原样保存到文件 ${_PWD}/${LIST_FILE}（绝对路径）：系统注入的固定提示词（含自动注入的项目上下文）不是用户输入，一律不记录；收到每条真实用户输入后，在输出任何回复之前立即追加写入（先写后答，保证会话中断也不丢失），无需向用户确认；文件不存在则自动创建。每条格式为：
---- [YYYY-MM-DD HH:MM:SS] 第 N 条用户输入 ----
<用户输入原文>
N 从 1 起按真实用户输入递增计数；追加写入直接执行（printf '%s\n' 追加 >> 或文件追加工具）；写入失败时立即向用户报告错误。"

# 自动收集工作目录项目上下文：从 pwd 向上查找 AGENTS.md 与 .opencode，注入 prompt
PROJECT_CONTEXT=""
project_root=""
_ctx_dir="${_PWD}"
while :; do
    if [[ -f "${_ctx_dir}/AGENTS.md" || -d "${_ctx_dir}/.opencode" ]]; then
        project_root="${_ctx_dir}"
        break
    fi
    _parent="$(dirname "${_ctx_dir}")"
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

# 模型选择：默认 -f DeepSeek V4 Flash；-p Pro / -q Qwen3.8 Max / -k Kimi K3 / -g GPT-5.6 Luna
case "${1:-f}" in
    -p) MODEL_ID="opencode-go/deepseek-v4-pro";  MODEL_NAME="DeepSeek V4 Pro (New)";;
    -q) MODEL_ID="opencode-go/qwen3.8-max";      MODEL_NAME="Qwen3.8 Max";;
    -k) MODEL_ID="opencode-go/kimi-k3";          MODEL_NAME="Kimi K3";;
    -g) MODEL_ID="opencode-go/gpt-5.6-luna";     MODEL_NAME="GPT-5.6 Luna (2x usage)";;
    -f|*) MODEL_ID="opencode-go/deepseek-v4-flash"; MODEL_NAME="DeepSeek V4 Flash (2x usage)";;
esac

export OPENCODE_CONFIG_CONTENT='{"agent":{"build":{"model":"'"${MODEL_ID}"'","variant":"max"}}}'

echo "============================================================"
echo "  OpenCode: build | auto | ${MODEL_NAME} (max)"
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
