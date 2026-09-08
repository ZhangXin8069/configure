#!/usr/bin/env bash

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
scope_script=$script_dir/task-scope.sh

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_contains() {
    case "$1" in
        *"$2"*) ;;
        *) fail "输出缺少: $2\n实际输出:\n$1" ;;
    esac
}

assert_not_contains() {
    case "$1" in
        *"$2"*) fail "输出不应包含: $2\n实际输出:\n$1" ;;
        *) ;;
    esac
}

[[ -x "$scope_script" ]] || fail "脚本不可执行：$scope_script"

task_one='创建 coverage-report.sh、coverage-report.test.sh、task-scope.sh、task-scope.test.sh，并更新 README 和 AGENTS.md'
set +e
output_one=$(bash "$scope_script" "$task_one" 2>&1)
status_one=$?
set -e
(( status_one == 0 )) || fail "task-scope.sh 分类多目标实现失败\n输出：\n$output_one"
assert_contains "$output_one" '分类：多目标实现'
assert_contains "$output_one" '推荐技能组合：dispatch -> plan -> make -> test -> diff'
assert_contains "$output_one" '脚本/代码'
assert_contains "$output_one" '测试'
assert_contains "$output_one" 'README/AGENTS'
assert_contains "$output_one" '多目标/可并行'
assert_contains "$output_one" '需要计划'
printf 'PASS: 多目标实现请求得到分域建议\n'

task_two='排查 coverage-report 在缺少 AGENTS.md 时的报错，并修复后回归测试'
set +e
output_two=$(printf '%s\n' "$task_two" | bash "$scope_script" 2>&1)
status_two=$?
set -e
(( status_two == 0 )) || fail "task-scope.sh 分类修复排查失败\n输出：\n$output_two"
assert_contains "$output_two" '分类：修复排查'
assert_contains "$output_two" '推荐技能组合：debug -> test -> diff'
assert_contains "$output_two" '先复现，再定位'
assert_contains "$output_two" '最小修复'
assert_contains "$output_two" '回归'
assert_contains "$output_two" '修复/排查'
printf 'PASS: 修复请求得到调试链路建议\n'

task_three='先帮我评估这个分类器的可行性，再给出实现计划'
set +e
output_three=$(bash "$scope_script" --task "$task_three" 2>&1)
status_three=$?
set -e
(( status_three == 0 )) || fail "task-scope.sh 分类设计规划失败\n输出：\n$output_three"
assert_contains "$output_three" '分类：设计规划'
assert_contains "$output_three" '推荐技能组合：brainstorm -> plan'
assert_contains "$output_three" '需求澄清'
assert_contains "$output_three" '方案比较'
assert_contains "$output_three" '任务计划'
assert_contains "$output_three" '设计/方案'
printf 'PASS: 设计请求得到规划链路建议\n'
