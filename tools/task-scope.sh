#!/usr/bin/env bash

set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd -- "$(dirname -- "$SCRIPT_PATH")" && pwd -P)"

declare -a SKILL_CHAIN=()
declare -a REASON_BITS=()
TASK_TEXT=

usage() {
    cat <<'EOF'
用法：task-scope.sh [任务文本]
       task-scope.sh --task "任务文本"
       printf '%s\n' "任务文本" | task-scope.sh

把自然语言任务分类为合适的技能组合，并给出子任务拆分建议。
EOF
}

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 2
}

contains() {
    local haystack=$1
    local needle=$2
    case "$haystack" in
        *"$needle"*) return 0 ;;
        *) return 1 ;;
    esac
}

contains_any() {
    local haystack=$1
    shift
    local needle
    for needle in "$@"; do
        if contains "$haystack" "$needle"; then
            return 0
        fi
    done
    return 1
}

add_skill() {
    local skill=$1
    local existing
    for existing in "${SKILL_CHAIN[@]-}"; do
        [[ "$existing" == "$skill" ]] && return 0
    done
    SKILL_CHAIN+=("$skill")
}

add_reason() {
    local reason=$1
    local existing
    for existing in "${REASON_BITS[@]-}"; do
        [[ "$existing" == "$reason" ]] && return 0
    done
    REASON_BITS+=("$reason")
}

join_by_arrow() {
    local result=
    local item
    for item in "$@"; do
        if [[ -z "$result" ]]; then
            result="$item"
        else
            result="$result -> $item"
        fi
    done
    printf '%s' "$result"
}

join_by_comma() {
    local result=
    local item
    for item in "$@"; do
        if [[ -z "$result" ]]; then
            result="$item"
        else
            result="${result}、$item"
        fi
    done
    printf '%s' "$result"
}

trim_text() {
    printf '%s' "$1" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

while (($# > 0)); do
    case "$1" in
        --help|-h)
            usage
            exit 0
            ;;
        --task)
            if (($# < 2)); then
                printf '缺少 --task 的文本参数。\n' >&2
                usage >&2
                exit 2
            fi
            TASK_TEXT="$2"
            shift 2
            ;;
        --)
            shift
            if (($# > 0)); then
                TASK_TEXT="${TASK_TEXT:+$TASK_TEXT }$*"
            fi
            break
            ;;
        *)
            TASK_TEXT="${TASK_TEXT:+$TASK_TEXT }$1"
            shift
            ;;
    esac
done

if [[ -z "${TASK_TEXT:-}" && ! -t 0 ]]; then
    TASK_TEXT="$(cat)"
fi
TASK_TEXT="$(trim_text "${TASK_TEXT:-}")"

if [[ -z "$TASK_TEXT" ]]; then
    printf '缺少任务文本。\n' >&2
    usage >&2
    exit 2
fi

need_go_on=false
need_fast=false
need_auto=false
need_all=false
need_dispatch=false
need_brainstorm=false
need_plan=false
need_analy=false
need_report=false
need_review=false
need_debug=false
need_optim=false
need_skill_creator=false
need_up=false
need_init=false
need_tag=false
need_tdd=false
need_make=false
need_test=false
need_diff=false

if contains_any "$TASK_TEXT" '继续上次' '继续' '接着' '恢复会话' '续接' 'go-on'; then
    need_go_on=true
    add_reason '继续上下文'
fi

if contains_any "$TASK_TEXT" '快速' '尽快' '少轮' '省 token' '省上下文' '轻量' 'fast'; then
    need_fast=true
    add_reason '快速/省上下文'
fi

if contains_any "$TASK_TEXT" '无人值守' '0交互' '零交互' '自动执行' '自动化'; then
    need_auto=true
    add_reason '自动执行'
fi

if contains_any "$TASK_TEXT" '收敛' '不断优化' '循环直到' '直到满意' '做到最好' '反复迭代' '不停优化' '持续改进'; then
    need_all=true
    add_reason '收敛迭代'
fi

if contains_any "$TASK_TEXT" '同时' '并行' '分头' '拆分' '分别' '各自' '多个' '两个' '三' '四' '多目标' '多文件' '多用例' '、' '；' ';'; then
    need_dispatch=true
    add_reason '多目标/可并行'
fi

if contains_any "$TASK_TEXT" '先理清' '设计一下' '方案探讨' '可行性' '给几个方案' '需求不清楚' '怎么实现' 'brainstorm' '头脑风暴' '设计' '方案'; then
    need_brainstorm=true
    add_reason '设计/方案'
fi

if contains_any "$TASK_TEXT" '计划' '规划' '拆解' '任务分解' '实施计划' '先规划' '先别写代码' 'plan'; then
    need_plan=true
    add_reason '计划/拆解'
fi

if contains_any "$TASK_TEXT" '分析' '调查' '诊断' '统计' '汇总' '审视' '诊断报告'; then
    need_analy=true
    add_reason '分析/诊断'
fi

if contains_any "$TASK_TEXT" '汇报' '报告' '展示' '演示' 'PPT' 'PDF' 'beamer' 'pdf'; then
    need_report=true
    add_reason '汇报/报告'
fi

if contains_any "$TASK_TEXT" '审查' '复查' 'review' '代码审查' '检查改动' '审查改动'; then
    need_review=true
    add_reason '审查/复查'
fi

if contains_any "$TASK_TEXT" '报错' 'bug' '失败' '崩溃' '异常' '定位' '排查' '修复' 'debug' '为什么' '哪一行'; then
    need_debug=true
    add_reason '修复/排查'
fi

if contains_any "$TASK_TEXT" '优化' '性能' '加速' '速度' '省资源' 'optim'; then
    need_optim=true
    add_reason '优化/性能'
fi

if contains_any "$TASK_TEXT" '技能' 'skill' 'SKILL.md' '触发描述' 'reference' && contains_any "$TASK_TEXT" 'AGENTS.md' 'AGENTS'; then
    need_skill_creator=true
    add_reason '技能维护'
fi

if contains_any "$TASK_TEXT" '升级' '四树' '插件推荐' '热榜' '生态' 'up '; then
    need_up=true
    add_reason '仓库升级'
fi

if contains_any "$TASK_TEXT" '初始化' '归档' '部署' 'init'; then
    need_init=true
    add_reason '初始化/归档'
fi

if contains_any "$TASK_TEXT" '打标' '标签' 'tag' '版本标记'; then
    need_tag=true
    add_reason '标签/发布'
fi

if contains_any "$TASK_TEXT" 'TDD' '测试驱动' '先写测试' '红绿' 'red-green'; then
    need_tdd=true
    add_reason '测试驱动'
fi

if contains_any "$TASK_TEXT" '创建' '生成' '实现' '搭建' '构建' '做一个' '新增' '写一个' '修改' '更新' 'make' 'build'; then
    need_make=true
    add_reason '实现/生成'
fi

if contains_any "$TASK_TEXT" '测试' '验证' '回归' '跑测试' '测试一下' 'test'; then
    need_test=true
    add_reason '测试/验证'
fi

if contains_any "$TASK_TEXT" 'diff' '改动' '对比' '变更' '查看改动' '审查改动'; then
    need_diff=true
    add_reason '差异/复查'
fi

if "$need_tdd"; then
    need_make=true
    need_test=true
    need_diff=true
fi

if "$need_debug"; then
    need_test=true
    need_diff=true
fi

if "$need_optim"; then
    need_test=true
    need_diff=true
fi

if "$need_skill_creator"; then
    need_test=true
    need_diff=true
fi

if "$need_up"; then
    need_test=true
    need_diff=true
fi

if "$need_review"; then
    need_diff=true
fi

if "$need_make"; then
    need_diff=true
fi

if "$need_init"; then
    need_diff=true
fi

if "$need_tag"; then
    need_diff=true
fi

if "$need_dispatch"; then
    need_plan=true
fi

if "$need_brainstorm" && ! "$need_plan"; then
    need_plan=true
fi

if "$need_plan"; then
    add_reason '需要计划'
fi

if "$need_dispatch" && "$need_make"; then
    add_reason '适合拆域并行'
fi

if "$need_dispatch" && "$need_debug"; then
    add_reason '独立失败可分开查'
fi

if "$need_dispatch" && "$need_review"; then
    add_reason '独立审查可并行'
fi

if "$need_dispatch" && "$need_test"; then
    add_reason '独立用例可并行'
fi

if "$need_go_on" && "$need_debug"; then
    add_reason '接着处理现有修复'
fi

if "$need_go_on" && "$need_make"; then
    add_reason '接着处理现有实现'
fi

if "$need_go_on" && "$need_plan"; then
    add_reason '接着当前计划'
fi

if "$need_go_on"; then
    add_skill 'go-on'
fi
if "$need_fast"; then
    add_skill 'fast'
fi
if "$need_auto"; then
    add_skill 'auto'
fi
if "$need_all"; then
    add_skill 'all'
fi
if "$need_dispatch"; then
    add_skill 'dispatch'
fi

if "$need_brainstorm"; then
    add_skill 'brainstorm'
fi
if "$need_plan"; then
    add_skill 'plan'
fi
if "$need_analy"; then
    add_skill 'analy'
fi
if "$need_report"; then
    add_skill 'report'
fi
if "$need_review"; then
    add_skill 'review'
fi
if "$need_debug"; then
    add_skill 'debug'
fi
if "$need_optim"; then
    add_skill 'optim'
fi
if "$need_skill_creator"; then
    add_skill 'skill-creator'
fi
if "$need_up"; then
    add_skill 'up'
fi
if "$need_init"; then
    add_skill 'init'
fi
if "$need_tag"; then
    add_skill 'tag'
fi
if "$need_tdd"; then
    add_skill 'tdd'
fi
if "$need_make"; then
    add_skill 'make'
fi
if "$need_test"; then
    add_skill 'test'
fi
if "$need_diff"; then
    add_skill 'diff'
fi

classification='通用任务'
split_lines=()
if "$need_dispatch" && "$need_make"; then
    classification='多目标实现'
    split_lines+=('1. 脚本/代码：实现各个交付物')
    split_lines+=('2. 测试：为每个交付物补回归')
    split_lines+=('3. 文档：README/AGENTS 同步')
elif "$need_dispatch" && "$need_debug"; then
    classification='多目标修复'
    split_lines+=('1. 复现与定位：每个失败域单独收证据')
    split_lines+=('2. 最小修复：每个域单独改根因')
    split_lines+=('3. 回归验证：原路径逐个复测')
elif "$need_dispatch" && "$need_review"; then
    classification='多目标审查'
    split_lines+=('1. 改动收集：按目标域分开')
    split_lines+=('2. 问题分级：每个域独立给结论')
    split_lines+=('3. 复查结论：整合后统一回顾')
elif "$need_dispatch" && "$need_test" && ! "$need_make" && ! "$need_debug"; then
    classification='多用例验证'
    split_lines+=('1. 按用例或文件边界拆分')
    split_lines+=('2. 每个子任务单独验证')
    split_lines+=('3. 最后统一回归')
elif "$need_debug"; then
    classification='修复排查'
    split_lines+=('1. 先复现，再定位')
    split_lines+=('2. 最小修复')
    split_lines+=('3. 原路径回归')
elif "$need_optim"; then
    classification='优化性能'
    split_lines+=('1. 基线测量')
    split_lines+=('2. 主导项优化')
    split_lines+=('3. 复测对比')
elif "$need_review"; then
    classification='审查复查'
    split_lines+=('1. 改动收集')
    split_lines+=('2. 问题分级')
    split_lines+=('3. 复查结论')
elif "$need_report"; then
    classification='分析报告'
    split_lines+=('1. 证据整理')
    split_lines+=('2. 结论成文')
    split_lines+=('3. 版式/产物检查')
elif "$need_analy"; then
    classification='分析诊断'
    split_lines+=('1. 范围扫描')
    split_lines+=('2. 证据整理')
    split_lines+=('3. 结论输出')
elif "$need_brainstorm" || "$need_plan"; then
    classification='设计规划'
    split_lines+=('1. 需求澄清')
    split_lines+=('2. 方案比较')
    split_lines+=('3. 任务计划')
elif "$need_skill_creator"; then
    classification='技能维护'
    split_lines+=('1. 触发词与边界')
    split_lines+=('2. SKILL.md 与 AGENTS.md')
    split_lines+=('3. 测试与 README')
elif "$need_up"; then
    classification='仓库升级'
    split_lines+=('1. 四树基线')
    split_lines+=('2. 差距分析')
    split_lines+=('3. 同步验证')
elif "$need_init"; then
    classification='初始化归档'
    split_lines+=('1. 目录扫描')
    split_lines+=('2. AGENTS 归档')
    split_lines+=('3. 权限与语法复查')
elif "$need_tag"; then
    classification='标签发布'
    split_lines+=('1. 变更盘点')
    split_lines+=('2. 标签操作')
    split_lines+=('3. 推送前校验')
elif "$need_tdd"; then
    classification='测试驱动'
    split_lines+=('1. 失败测试')
    split_lines+=('2. 最小实现')
    split_lines+=('3. 回归验证')
elif "$need_make"; then
    classification='实现生成'
    split_lines+=('1. 文件结构')
    split_lines+=('2. 实现')
    split_lines+=('3. 测试/文档')
elif "$need_test"; then
    classification='测试验证'
    split_lines+=('1. 测试对象')
    split_lines+=('2. 通过标准')
    split_lines+=('3. 回归证据')
fi

if ((${#SKILL_CHAIN[@]} == 0)); then
    add_skill 'brainstorm'
    add_skill 'plan'
    classification='设计规划'
    split_lines=(
        '1. 需求澄清'
        '2. 方案比较'
        '3. 任务计划'
    )
fi

printf '任务：%s\n' "$TASK_TEXT"
printf '分类：%s\n' "$classification"
printf '推荐技能组合：%s\n' "$(join_by_arrow "${SKILL_CHAIN[@]}")"
printf '拆分建议：\n'
for line in "${split_lines[@]}"; do
    printf '%s\n' "- $line"
done
if ((${#REASON_BITS[@]} > 0)); then
    printf '依据：%s\n' "$(join_by_comma "${REASON_BITS[@]}")"
fi
