#!/usr/bin/env bash
# Codex 原生 goal 状态查看与预算修复。
# 默认只读；clear 会先备份 goals 数据库，且必须显式加 --yes 才会写入。

set -Eeuo pipefail

_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
printf '###%s in %s is running...:%s###\n' "${_NAME}" "${_PATH}" "$(date '+%Y-%m-%d-%H-%M-%S')" >&2

_usage() {
    cat >&2 <<'EOF'
用法:
  agent-goal.sh [--db PATH] list [--json]
  agent-goal.sh [--db PATH] clear [THREAD_ID ...] [--thread THREAD_ID]
                 [--latest|--all-budget-limited] [--budget N] [--yes] [--dry-run]

默认数据库: ${CODEX_GOALS_DB:-${CODEX_HOME:-$HOME/.codex}/goals_1.sqlite}

list:
  列出全部线程 goal 的状态、预算和用量。

clear:
  清除 token_budget 并把 goal 恢复为 active；或用 --budget N 改为新的正预算。
  无选择器时等同 --latest（最近更新的 budget_limited goal）。
  写入前用 SQLite .backup 生成带时间戳的备份；未加 --yes 时只显示目标，不修改。
  --dry-run 只显示将修改的行，不写入。complete 状态不会被修改。
EOF
}

_db="${CODEX_GOALS_DB:-${CODEX_HOME:-${HOME}/.codex}/goals_1.sqlite}"
_command="list"
_json=0
_yes=0
_dry_run=0
_all_budget_limited=0
_latest=0
_budget=""
_threads=()
_selector_given=0

while (( $# > 0 )); do
    case "$1" in
        list|clear)
            _command="$1"
            shift
            ;;
        --db)
            (( $# >= 2 )) || { _usage; exit 2; }
            _db="$2"
            shift 2
            ;;
        --json)
            _json=1
            shift
            ;;
        --yes)
            _yes=1
            shift
            ;;
        --dry-run)
            _dry_run=1
            shift
            ;;
        --all-budget-limited)
            _all_budget_limited=1
            _selector_given=1
            shift
            ;;
        --latest)
            _latest=1
            _selector_given=1
            shift
            ;;
        --thread)
            (( $# >= 2 )) || { _usage; exit 2; }
            _threads+=("$2")
            _selector_given=1
            shift 2
            ;;
        --budget)
            (( $# >= 2 )) || { _usage; exit 2; }
            _budget="$2"
            shift 2
            ;;
        --)
            shift
            while (( $# > 0 )); do
                _threads+=("$1")
                shift
            done
            break
            ;;
        -h|--help)
            _usage
            exit 0
            ;;
        --*)
            printf '%s：未知选项：%s\n' "${_NAME}" "$1" >&2
            _usage
            exit 2
            ;;
        *)
            _threads+=("$1")
            shift
            ;;
    esac
done

if (( ${#_threads[@]} > 0 )); then
    _selector_given=1
fi
if [[ "${_command}" == "list" ]] && (( _selector_given || ${#_threads[@]} > 0 )); then
    printf '%s：list 不接受 goal 选择器\n' "${_NAME}" >&2
    exit 2
fi
if [[ "${_command}" == "clear" ]] && (( _all_budget_limited && _latest )); then
    printf '%s：--latest 与 --all-budget-limited 不能同时使用\n' "${_NAME}" >&2
    exit 2
fi
if [[ "${_command}" == "clear" ]] && (( ${#_threads[@]} > 0 )) && (( _all_budget_limited || _latest )); then
    printf '%s：显式 THREAD_ID 不能与 --latest/--all-budget-limited 同时使用\n' "${_NAME}" >&2
    exit 2
fi

if command -v sqlite3 >/dev/null 2>&1; then
    _sqlite_backend="cli"
elif command -v python3 >/dev/null 2>&1 && python3 -c 'import sqlite3' >/dev/null 2>&1; then
    _sqlite_backend="python"
else
    printf '%s：未找到 sqlite3 CLI，也未找到带 sqlite3 模块的 python3\n' "${_NAME}" >&2
    exit 69
fi
if [[ ! -f "${_db}" ]]; then
    printf '%s：goal 数据库不存在：%s\n' "${_NAME}" "${_db}" >&2
    exit 66
fi
if [[ ! -r "${_db}" ]]; then
    printf '%s：goal 数据库不可读：%s\n' "${_NAME}" "${_db}" >&2
    exit 77
fi

_sqlite() {
    if [[ "${_sqlite_backend}" == "cli" ]]; then
        sqlite3 -cmd '.timeout 5000' "$@"
        return
    fi

    python3 - "$@" <<'PY'
import json
import shlex
import sqlite3
import sys
import unicodedata


def cell_text(value):
    return "" if value is None else str(value)


def display_width(value):
    width = 0
    for character in value:
        width += 2 if unicodedata.east_asian_width(character) in ("F", "W") else 1
    return width


def pad(value, width):
    return value + " " * (width - display_width(value))


def print_table(columns, rows, show_header):
    if not rows:
        return

    cells = [[cell_text(value) for value in row] for row in rows]
    widths = [display_width(column) for column in columns]
    for row in cells:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], display_width(value))

    def print_row(row):
        print("  ".join(pad(value, widths[index]) for index, value in enumerate(row)).rstrip())

    if show_header:
        print_row(columns)
        print("  ".join("-" * width for width in widths))
    for row in cells:
        print_row(row)


def main():
    arguments = sys.argv[1:]
    json_mode = False
    show_header = False
    column_mode = False

    while arguments and arguments[0].startswith("-"):
        option = arguments.pop(0)
        if option == "-json":
            json_mode = True
        elif option == "-header":
            show_header = True
        elif option == "-column":
            column_mode = True
        else:
            print(f"sqlite3: unsupported option: {option}", file=sys.stderr)
            return 2

    if len(arguments) != 2:
        print("sqlite3: expected database path and SQL", file=sys.stderr)
        return 2

    database_path, sql = arguments
    connection = sqlite3.connect(database_path, timeout=5.0)
    try:
        statement = sql.lstrip()
        if statement.startswith(".backup"):
            backup_arguments = shlex.split(statement)
            if len(backup_arguments) != 2:
                print("sqlite3: invalid .backup command", file=sys.stderr)
                return 2
            destination = sqlite3.connect(backup_arguments[1], timeout=5.0)
            try:
                connection.backup(destination)
            finally:
                destination.close()
            return 0

        if json_mode or show_header or column_mode:
            cursor = connection.execute(sql)
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
            if json_mode:
                print(json.dumps(
                    [dict(zip(columns, row)) for row in rows],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ))
            else:
                print_table(columns, rows, show_header)
            return 0

        connection.executescript(sql)
        connection.commit()
        return 0
    finally:
        connection.close()


try:
    sys.exit(main())
except (OSError, sqlite3.Error, ValueError) as error:
    print(f"sqlite3: {error}", file=sys.stderr)
    sys.exit(1)
PY
}

_list_query='SELECT thread_id, goal_id, status, token_budget, tokens_used, time_used_seconds, created_at_ms, updated_at_ms, objective FROM thread_goals ORDER BY updated_at_ms DESC;'

if [[ "${_command}" == "list" ]]; then
    if (( _json )); then
        _sqlite -json "${_db}" "${_list_query}"
    else
        _sqlite -header -column "${_db}" \
            "SELECT thread_id, status, COALESCE(token_budget, '-') AS token_budget, tokens_used, time_used_seconds AS seconds, datetime(updated_at_ms / 1000, 'unixepoch', 'localtime') AS updated, substr(objective, 1, 80) AS objective FROM thread_goals ORDER BY updated_at_ms DESC;"
    fi
    printf '###%s in %s is done......:%s###\n' "${_NAME}" "${_PATH}" "$(date '+%Y-%m-%d-%H-%M-%S')" >&2
    exit 0
fi

if [[ -n "${_budget}" ]] && [[ ! "${_budget}" =~ ^[0-9]+$ ]]; then
    printf '%s：--budget 必须是正整数，实际为：%s\n' "${_NAME}" "${_budget}" >&2
    exit 2
fi
if [[ -n "${_budget}" ]] && (( _budget <= 0 )); then
    printf '%s：--budget 必须大于 0\n' "${_NAME}" >&2
    exit 2
fi

_where=""
if (( ${#_threads[@]} > 0 )); then
    _quoted=""
    for _thread in "${_threads[@]}"; do
        if [[ ! "${_thread}" =~ ^[A-Za-z0-9_-]+$ ]]; then
            printf '%s：THREAD_ID 格式无效：%s\n' "${_NAME}" "${_thread}" >&2
            exit 2
        fi
        [[ -n "${_quoted}" ]] && _quoted+=","
        _quoted+="'${_thread}'"
    done
    _where="thread_id IN (${_quoted})"
elif (( _all_budget_limited )); then
    _where="status = 'budget_limited'"
else
    _where="thread_id = (SELECT thread_id FROM thread_goals WHERE status = 'budget_limited' ORDER BY updated_at_ms DESC LIMIT 1)"
fi

_target_rows="$(_sqlite -header -column "${_db}" \
    "SELECT thread_id, status, COALESCE(token_budget, '-') AS token_budget, tokens_used, substr(objective, 1, 80) AS objective FROM thread_goals WHERE ${_where} AND status != 'complete' ORDER BY updated_at_ms DESC;")"

if [[ -z "${_target_rows}" ]]; then
    printf '%s：没有匹配且非 complete 的 goal\n' "${_NAME}" >&2
    printf '###%s in %s is done......:%s###\n' "${_NAME}" "${_PATH}" "$(date '+%Y-%m-%d-%H-%M-%S')" >&2
    exit 0
fi

if (( _dry_run )); then
    printf '%s\n' "${_target_rows}"
    printf '%s：dry-run，未修改数据库\n' "${_NAME}" >&2
    printf '###%s in %s is done......:%s###\n' "${_NAME}" "${_PATH}" "$(date '+%Y-%m-%d-%H-%M-%S')" >&2
    exit 0
fi

if (( ! _yes )); then
    printf '%s\n' "${_target_rows}"
    printf '%s：以上 goal 将被修改；确认后重新运行并加 --yes\n' "${_NAME}" >&2
    exit 2
fi

if [[ ! -w "${_db}" ]]; then
    printf '%s：goal 数据库不可写：%s\n' "${_NAME}" "${_db}" >&2
    exit 77
fi

_backup="${_db}.bak.$(date '+%Y%m%d%H%M%S').$$"
if ! _sqlite "${_db}" ".backup '${_backup}'"; then
    printf '%s：备份 goal 数据库失败，未做任何修改：%s\n' "${_NAME}" "${_backup}" >&2
    exit 74
fi

_now_ms=$(( $(date '+%s') * 1000 ))
if [[ -n "${_budget}" ]]; then
    _update_sql="UPDATE thread_goals SET token_budget = ${_budget}, status = CASE WHEN tokens_used >= ${_budget} THEN 'budget_limited' ELSE 'active' END, updated_at_ms = ${_now_ms} WHERE ${_where} AND status != 'complete';"
else
    _update_sql="UPDATE thread_goals SET token_budget = NULL, status = 'active', updated_at_ms = ${_now_ms} WHERE ${_where} AND status != 'complete';"
fi

if ! _sqlite "${_db}" "BEGIN IMMEDIATE; ${_update_sql} COMMIT;"; then
    printf '%s：更新 goal 失败；备份位于 %s\n' "${_NAME}" "${_backup}" >&2
    exit 75
fi

printf '%s：已更新 goal\n' "${_NAME}" >&2
_sqlite -header -column "${_db}" \
    "SELECT thread_id, status, COALESCE(token_budget, '-') AS token_budget, tokens_used, datetime(updated_at_ms / 1000, 'unixepoch', 'localtime') AS updated FROM thread_goals WHERE updated_at_ms = ${_now_ms} ORDER BY thread_id;"
printf '%s：备份：%s\n' "${_NAME}" "${_backup}" >&2
printf '###%s in %s is done......:%s###\n' "${_NAME}" "${_PATH}" "$(date '+%Y-%m-%d-%H-%M-%S')" >&2
