#!/usr/bin/env bash

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
test_root=$(mktemp -d "${TMPDIR:-/tmp}/agent-goal-test.XXXXXX")
cleanup() {
    rm -rf -- "$test_root"
}
trap cleanup EXIT HUP INT TERM

db="$test_root/goals_1.sqlite"
sqlite3 "$db" <<'SQL'
CREATE TABLE thread_goals (
    thread_id TEXT PRIMARY KEY NOT NULL,
    goal_id TEXT NOT NULL,
    objective TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN (
        'active', 'paused', 'blocked', 'usage_limited', 'budget_limited', 'complete'
    )),
    token_budget INTEGER,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    time_used_seconds INTEGER NOT NULL DEFAULT 0,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL
);
INSERT INTO thread_goals VALUES
  ('thread-limited', 'goal-1', '限流目标', 'budget_limited', 1, 120, 5, 1000, 3000),
  ('thread-active', 'goal-2', '活跃目标', 'active', 100, 40, 6, 1000, 2000),
  ('thread-done', 'goal-3', '完成目标', 'complete', 0, 10, 7, 1000, 1000);
SQL

goal() {
    "$script_dir/agent-goal.sh" --db "$db" "$@" 2>/dev/null
}

status_of() {
    sqlite3 "$db" "SELECT status || '|' || COALESCE(token_budget, 'NULL') || '|' || tokens_used FROM thread_goals WHERE thread_id = '$1';"
}

json_count=$(goal list --json | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')
[[ "$json_count" == 3 ]] || { printf 'FAIL: list --json 数量不正确：%s\n' "$json_count" >&2; exit 1; }

set +e
goal clear --thread thread-limited >/dev/null
rc=$?
set -e
[[ $rc == 2 ]] || { printf 'FAIL: 未加 --yes 应返回 2，实际 %s\n' "$rc" >&2; exit 1; }
[[ "$(status_of thread-limited)" == 'budget_limited|1|120' ]] || { printf 'FAIL: 未加 --yes 时不应修改\n' >&2; exit 1; }

goal clear --thread thread-limited --yes >/dev/null
[[ "$(status_of thread-limited)" == 'active|NULL|120' ]] || { printf 'FAIL: clear 未清除预算：%s\n' "$(status_of thread-limited)" >&2; exit 1; }

goal clear --thread thread-active --budget 1000 --yes >/dev/null
[[ "$(status_of thread-active)" == 'active|1000|40' ]] || { printf 'FAIL: --budget 增加预算失败：%s\n' "$(status_of thread-active)" >&2; exit 1; }

goal clear --thread thread-active --budget 5 --yes >/dev/null
[[ "$(status_of thread-active)" == 'budget_limited|5|40' ]] || { printf 'FAIL: --budget 低于已用量时应保持 budget_limited：%s\n' "$(status_of thread-active)" >&2; exit 1; }

goal clear --thread thread-active --budget 1000 --yes >/dev/null
goal clear --all-budget-limited --yes >/dev/null
[[ "$(status_of thread-active)" == 'active|1000|40' ]] || { printf 'FAIL: --all-budget-limited 误改非限流目标\n' >&2; exit 1; }
[[ "$(status_of thread-limited)" == 'active|NULL|120' ]] || { printf 'FAIL: --all-budget-limited 未处理目标\n' >&2; exit 1; }
[[ "$(status_of thread-done)" == 'complete|0|10' ]] || { printf 'FAIL: complete 目标被修改\n' >&2; exit 1; }

sqlite3 "$db" "UPDATE thread_goals SET status = 'budget_limited', token_budget = 1 WHERE thread_id = 'thread-limited';"
goal clear --latest --dry-run >/dev/null
[[ "$(status_of thread-limited)" == 'budget_limited|1|120' ]] || { printf 'FAIL: --dry-run 不应修改\n' >&2; exit 1; }

goal clear --latest --yes >/dev/null
[[ "$(status_of thread-limited)" == 'active|NULL|120' ]] || { printf 'FAIL: --latest 未选择最近更新的限流目标\n' >&2; exit 1; }

backup_count=$(find "$test_root" -maxdepth 1 -name 'goals_1.sqlite.bak.*' -type f | wc -l | tr -d ' ')
[[ "$backup_count" -ge 1 ]] || { printf 'FAIL: 未生成数据库备份\n' >&2; exit 1; }

set +e
goal clear --thread thread-done --yes >/dev/null
rc=$?
set -e
[[ $rc == 0 ]] || { printf 'FAIL: 对 complete 目标应为无操作成功，实际 %s\n' "$rc" >&2; exit 1; }
[[ "$(status_of thread-done)" == 'complete|0|10' ]] || { printf 'FAIL: complete 目标被修改\n' >&2; exit 1; }

printf 'PASS: agent-goal.sh list/clear/budget/latest/dry-run/complete 保护与备份\n'
