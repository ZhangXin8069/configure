#!/usr/bin/env bash
# Arm/disarm the auto-skill idle nudge markers for one agent run.

set -Eeuo pipefail

_PATH=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename -- "${BASH_SOURCE[0]:-$0}")
config_root=${AGENT_CONFIGURE_ROOT:-$(CDPATH= cd -- "${_PATH}/.." && pwd)}
data_root=${AGENT_DATA_ROOT:-${config_root}/data}

usage() {
    cat <<'USAGE'
用法：agent-idle-nudge.sh <enable|disable|complete|status> [选项]

作用：auto 技能用运行目录标记控制 TUI 空闲看门狗。
  enable    允许看门狗在空闲阈值后注入用户指令，并清除旧完成标记
  disable   停止看门狗（保留 run 状态）
  complete  标记最终目标已完成，看门狗不再注入
  status    只读查看标记状态

选项：
  --manifest PATH   运行 manifest（默认 AGENT_MANIFEST_FILE）
  --run-dir DIR     运行目录（默认 AGENT_RUN_DIR，或由 manifest 推导）
  --run-id ID       运行 id（默认 AGENT_RUN_ID，或由 manifest 推导）
  --data-root DIR   数据根（默认 AGENT_DATA_ROOT，或 configure/data）
  --goal TEXT       任务定义（enable 时写入，供审计）
  -h, --help        显示帮助
USAGE
}

command_name=${1:-status}
if (( $# > 0 )); then
    shift
fi
manifest=${AGENT_MANIFEST_FILE:-}
run_dir=${AGENT_RUN_DIR:-}
run_id=${AGENT_RUN_ID:-}
run_id_explicit=0
goal=""

while (( $# > 0 )); do
    case "$1" in
        --manifest)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            manifest=$2; shift 2;;
        --run-dir)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            run_dir=$2; shift 2;;
        --run-id)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            run_id=$2; run_id_explicit=1; shift 2;;
        --data-root)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            data_root=$2; shift 2;;
        --goal)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            goal=$2; shift 2;;
        -h|--help)
            usage; exit 0;;
        *)
            printf '%s：未知参数：%s\n' "$_NAME" "$1" >&2
            usage >&2
            exit 2;;
    esac
done

case "${command_name}" in
    enable|disable|complete|status) ;;
    *)
        printf '%s：未知命令：%s\n' "$_NAME" "$command_name" >&2
        usage >&2
        exit 2;;
esac

if [[ -z "${run_dir}" && -n "${manifest}" ]]; then
    [[ -r "${manifest}" ]] || {
        printf '%s：manifest 不可读：%s\n' "$_NAME" "$manifest" >&2
        exit 2
    }
    run_dir=$(CDPATH= cd -- "$(dirname -- "${manifest}")" && pwd)
fi
if [[ -z "${run_dir}" && -n "${run_id}" ]]; then
    run_dir="${data_root}/runs/${run_id}"
fi
if [[ -z "${run_dir}" ]]; then
    printf '%s：缺少运行上下文；请传 --manifest/--run-dir，或导出 AGENT_MANIFEST_FILE/AGENT_RUN_DIR\n' "$_NAME" >&2
    exit 2
fi
[[ -d "${run_dir}" ]] || {
    printf '%s：运行目录不存在：%s\n' "$_NAME" "$run_dir" >&2
    exit 2
}
run_dir=$(CDPATH= cd -- "${run_dir}" && pwd)

if (( ! run_id_explicit )) && [[ -r "${run_dir}/manifest.env" ]]; then
    run_id=$(awk -F= '$1 == "run_id" { sub(/^[^=]*=/, "", $0); print; exit }' "${run_dir}/manifest.env" 2>/dev/null || true)
fi
[[ -n "${run_id}" ]] || run_id=$(basename -- "${run_dir}")
[[ "${run_id}" =~ ^[A-Za-z0-9._-]+$ ]] || {
    printf '%s：非法 run id：%s\n' "$_NAME" "$run_id" >&2
    exit 2
}

enabled_file=${run_dir}/.idle-nudge-enabled
complete_file=${run_dir}/.goal-complete
attempt_file=${run_dir}/.idle-nudge-attempted
watch_pid_file=${run_dir}/.tui-watch.pid

python_bin=${AGENT_STATE_PYTHON:-python3}
command -v "${python_bin}" >/dev/null 2>&1 || {
    printf '%s：缺少 python3，无法写入 JSON 标记\n' "$_NAME" >&2
    exit 7
}

write_json() {
    local target=$1 payload=$2
    "${python_bin}" - "${target}" "${payload}" <<'PY'
import json, os, sys, tempfile
target, raw = sys.argv[1], sys.argv[2]
value = json.loads(raw)
directory = os.path.dirname(target) or "."
descriptor, temp = tempfile.mkstemp(prefix=".nudge.", dir=directory)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True)
        stream.write("\n")
    os.chmod(temp, 0o600)
    os.replace(temp, target)
finally:
    if os.path.exists(temp):
        os.unlink(temp)
PY
}

watcher_running() {
    [[ -r "${watch_pid_file}" ]] || return 1
    local pid
    pid=$(<"${watch_pid_file}")
    [[ "${pid}" =~ ^[1-9][0-9]*$ ]] || return 1
    kill -0 "${pid}" 2>/dev/null
}

case "${command_name}" in
    enable)
        rm -f -- "${complete_file}" "${attempt_file}"
        payload=$("${python_bin}" - "${run_id}" "${goal}" "$$" <<'PY'
import json, sys
run_id, goal, pid = sys.argv[1:4]
print(json.dumps({
    "schema_version": 1,
    "run_id": run_id,
    "goal": goal,
    "pid": int(pid),
}, ensure_ascii=False, separators=(",", ":")))
PY
)
        write_json "${enabled_file}" "${payload}"
        printf 'status=enabled run_id=%s goal=%s marker=%s\n' "${run_id}" "${goal:-<empty>}" "${enabled_file}"
        if watcher_running; then
            printf 'watch=active pid=%s\n' "$(<"${watch_pid_file}")"
        else
            printf 'watch=inactive warning=no-live-tui-watcher marker=%s\n' "${watch_pid_file}" >&2
        fi
        ;;
    disable)
        rm -f -- "${enabled_file}"
        printf 'status=disabled run_id=%s marker=%s\n' "${run_id}" "${enabled_file}"
        ;;
    complete)
        payload=$("${python_bin}" - "${run_id}" "$$" <<'PY'
import json, sys
run_id, pid = sys.argv[1:3]
print(json.dumps({
    "schema_version": 1,
    "run_id": run_id,
    "pid": int(pid),
}, ensure_ascii=False, separators=(",", ":")))
PY
)
        write_json "${complete_file}" "${payload}"
        rm -f -- "${enabled_file}"
        printf 'status=complete run_id=%s marker=%s\n' "${run_id}" "${complete_file}"
        ;;
    status)
        enabled=0
        complete=0
        enabled_goal=""
        [[ -f "${enabled_file}" ]] && enabled=1
        [[ -f "${complete_file}" ]] && complete=1
        if (( enabled )); then
            enabled_goal=$("${python_bin}" - "${enabled_file}" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as stream:
        value = json.load(stream)
    print(value.get("goal", "") if isinstance(value, dict) else "")
except (OSError, ValueError):
    print("")
PY
)
        fi
        printf 'run_id=%s enabled=%s complete=%s goal=%s marker=%s complete_marker=%s\n' \
            "${run_id}" "${enabled}" "${complete}" "${enabled_goal:-<empty>}" "${enabled_file}" "${complete_file}"
        ;;
esac
