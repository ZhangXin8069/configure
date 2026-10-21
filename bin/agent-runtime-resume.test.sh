#!/usr/bin/env bash

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
runtime=$script_dir/agent-runtime.sh
test_root=$(mktemp -d "${TMPDIR:-/tmp}/agent-runtime-resume-test.XXXXXX")

cleanup() {
    rm -rf -- "$test_root"
}
trap cleanup EXIT HUP INT TERM

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

run_exit_case() {
    local case_name=$1 auto_resume=$2 resume_active=$3 expected=$4
    local case_root=$test_root/$case_name
    local fake_config=$case_root/config
    local data_root=$case_root/data
    local run_id=20261021T070000.$case_name
    local run_dir=$data_root/runs/$run_id
    local call_log=$case_root/calls.log
    mkdir -p "$fake_config/hooks" "$run_dir"
    cat > "$fake_config/hooks/agent-resume.sh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" > "${FAKE_RESUME_CALL_LOG:?}"
EOF
    chmod 0755 "$fake_config/hooks/agent-resume.sh"
    (
        export AGENT_CONFIGURE_ROOT=$fake_config
        export AGENT_DATA_ROOT=$data_root
        export AGENT_RUN_ID=$run_id
        export AGENT_RUN_DIR=$run_dir
        export AGENT_MANIFEST_FILE=$run_dir/manifest.env
        export AGENT_STATE_FILE=$run_dir/state.env
        export AGENT_EVENT_FILE=$run_dir/events.jsonl
        export AGENT_WORKSPACE_ROOT=$test_root
        export AGENT_WORKDIR=$test_root
        export AGENT_RUNTIME_AGENT=codex
        export AGENT_RUNTIME_STATE=running
        export AGENT_AUTO_RESUME=$auto_resume
        export AGENT_RESUME_ACTIVE=$resume_active
        export FAKE_RESUME_CALL_LOG=$call_log
        export _NAME=co
        : > "$AGENT_EVENT_FILE"
        # shellcheck disable=SC1090
        source "$runtime"
        _agent_runtime_on_exit 7
    )
    if (( expected )); then
        [[ -s "$call_log" ]] || fail "$case_name 未调用恢复 hook"
        grep -Fq -- "--run-id $run_id --data-root $data_root" "$call_log" ||
            fail "$case_name 恢复 hook 参数不正确"
    else
        [[ ! -e "$call_log" ]] || fail "$case_name 不应调用恢复 hook"
    fi
}

run_exit_case normal 1 0 1
run_exit_case disabled 0 0 0
run_exit_case resumed_child 1 1 0

printf 'PASS: agent-runtime.sh 只启动一个外层恢复监督进程，恢复中的子进程不会递归调度\n'
