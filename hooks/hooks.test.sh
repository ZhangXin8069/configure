#!/usr/bin/env bash

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
hook_script=$script_dir/codex-hook.sh
verify_script=$script_dir/codex-verify.sh
guard_script=$script_dir/codex-guard.sh
preflight_script=$script_dir/codex-preflight.sh
event_script=$script_dir/codex-event.sh
test_root=$(mktemp -d "${TMPDIR:-/tmp}/codex-verify-test.XXXXXX")

cleanup() {
    rm -rf -- "$test_root"
}
trap cleanup EXIT HUP INT TERM

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
    esac
}

if ! command -v jq >/dev/null 2>&1 && ! command -v python3 >/dev/null 2>&1; then
    fail 'JSON hook 测试需要 jq 或 python3 解析 JSON'
fi

json_envelope_valid() {
    local json=$1
    if command -v jq >/dev/null 2>&1; then
        printf '%s\n' "$json" | jq -e '
            .schema_version == "1" and
            .event == "session-start" and
            .run_id == "hook-run" and
            .session_id == "session-hook" and
            .turn_id == "3" and
            .status == "ok"
        ' >/dev/null
    else
        printf '%s\n' "$json" | python3 -c '
import json
import sys

data = json.load(sys.stdin)
ok = (
    data.get("schema_version") == "1"
    and data.get("event") == "session-start"
    and data.get("run_id") == "hook-run"
    and data.get("session_id") == "session-hook"
    and data.get("turn_id") == "3"
    and data.get("status") == "ok"
)
raise SystemExit(0 if ok else 1)
'
    fi
}

jsonl_event_valid() {
    local file=$1
    if [[ "${HOOK_TEST_JSON_PARSER:-auto}" != python ]] &&
        command -v jq >/dev/null 2>&1; then
        jq -e '.event == "session-start"' "$file" >/dev/null
    else
        python3 -c '
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    events = [json.loads(line) for line in handle if line.strip()]
valid = events and all(item.get("event") == "session-start" for item in events)
raise SystemExit(0 if valid else 1)
' "$file"
    fi
}

jsonl_control_detail_valid() {
    local file=$1
    if [[ "${HOOK_TEST_JSON_PARSER:-auto}" != python ]] &&
        command -v jq >/dev/null 2>&1; then
        jq -e '.detail == "control:\u0001detail"' "$file" >/dev/null
    else
        python3 -c '
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    events = [json.loads(line) for line in handle if line.strip()]
valid = len(events) == 1 and events[0].get("detail") == "control:\x01detail"
raise SystemExit(0 if valid else 1)
' "$file"
    fi
}

repo=$test_root/repo
mkdir -p "$repo"
repo_realpath=$(cd -- "$repo" && pwd -P)
git -C "$repo" init -q

set +e
output=$(cd -- "$repo" && "$preflight_script" 2>&1)
preflight_status=$?
set -e

(( preflight_status == 0 )) || fail "session-start 预检失败\n输出：\n$output"
assert_contains "$output" 'codex-preflight event=session-start'
assert_contains "$output" 'instruction_count=0'
printf 'PASS: session-start 预检兼容 Bash 3.2\n'

mkdir -p "$repo/nested"
printf '%s\n' '# root instructions' > "$repo/AGENTS.md"
printf '%s\n' '# nested instructions' > "$repo/nested/AGENTS.md"
printf '%s\n' '# codex instructions' > "$repo/CODEX.md"
instruction_outside_dir=$test_root/outside-instructions
mkdir -p "$instruction_outside_dir"
instruction_outside_realpath=$(cd -- "$instruction_outside_dir" && pwd -P)
printf '%s\n' '# outside instructions' > "$instruction_outside_dir/AGENTS.md"
ln -s "$repo/nested" "$instruction_outside_dir/linked-nested"
set +e
output=$(cd -- "$instruction_outside_dir/linked-nested" && "$preflight_script" 2>&1)
hierarchical_status=$?
set -e

(( hierarchical_status == 0 )) || fail "层级说明文件预检失败\n输出：\n$output"
assert_contains "$output" 'instruction[1]='
assert_contains "$output" "$repo_realpath/nested/AGENTS.md"
assert_contains "$output" 'instruction[2]='
assert_contains "$output" "$repo_realpath/AGENTS.md"
assert_contains "$output" 'instruction[3]='
assert_contains "$output" "$repo_realpath/CODEX.md"
assert_contains "$output" 'instruction_count=3'
assert_not_contains "$output" "$instruction_outside_realpath/AGENTS.md"
assert_not_contains "$output" "$instruction_outside_realpath/linked-nested"
printf 'PASS: session-start 使用物理路径并限制层级说明文件在仓库内\n'

instruction_symlink_repo=$test_root/instruction-symlink-repo
instruction_symlink_outside=$test_root/instruction-symlink-outside
mkdir -p "$instruction_symlink_repo" "$instruction_symlink_outside"
git -C "$instruction_symlink_repo" init -q
printf '%s\n' 'outside one' 'outside two' > "$instruction_symlink_outside/AGENTS.md"
ln -s "$instruction_symlink_outside/AGENTS.md" "$instruction_symlink_repo/AGENTS.md"
set +e
output=$(cd -- "$instruction_symlink_repo" && "$preflight_script" 2>&1)
instruction_symlink_status=$?
set -e
(( instruction_symlink_status == 0 )) || fail "说明文件越界符号链接不应使预检崩溃\n输出：\n$output"
assert_not_contains "$output" "$instruction_symlink_outside/AGENTS.md"
assert_not_contains "$output" 'instruction[1]='
assert_contains "$output" 'instruction_count=0'
printf 'PASS: 仓库内说明文件符号链接不能越界读取仓库外文件\n'

hook_data="$test_root/hook-data"
set +e
json_output=$(cd -- "$repo" && CODEX_HOOK_DATA_DIR="$hook_data" \
    CODEX_HOOK_RUN_ID=hook-run CODEX_HOOK_SESSION_ID=session-hook \
    CODEX_HOOK_TURN_ID=3 "$hook_script" --json session-start 2>&1)
json_status=$?
set -e

(( json_status == 0 )) || fail "JSON hook 失败\n输出：\n$json_output"
if ! json_envelope_valid "$json_output"; then
    fail "JSON hook envelope 无效：$json_output"
fi
event_file="$hook_data/events.jsonl"
[[ -s "$event_file" ]] || fail 'JSON hook 没有写入持久事件文件'
if ! jsonl_event_valid "$event_file"; then
    fail '持久事件文件不是合法 JSONL'
fi
multi_event_file="$hook_data/events-multiple.jsonl"
printf '%s\n' '{"event":"session-start"}' '{"event":"session-start"}' > "$multi_event_file"
if command -v python3 >/dev/null 2>&1 &&
    ! HOOK_TEST_JSON_PARSER=python jsonl_event_valid "$multi_event_file"; then
    fail 'Python JSONL 回退不能解析多条事件'
fi
printf 'PASS: JSON hook envelope 与持久事件日志\n'

control_event_dir="$hook_data/control"
control_detail=$(printf 'control:\001detail')
set +e
control_output=$(cd -- "$repo" && CODEX_HOOK_DATA_DIR="$control_event_dir" \
    "$event_script" session-start ok "$control_detail" 2>&1)
control_status=$?
set -e

(( control_status == 0 )) || fail "控制字符事件编码失败\n输出：\n$control_output"
control_event_file=$control_event_dir/events.jsonl
[[ -s "$control_event_file" ]] || fail '控制字符事件没有写入持久 JSONL'
if ! jsonl_control_detail_valid "$control_event_file"; then
    fail '控制字符事件不是合法 JSONL'
fi

bash_path=$(command -v bash)
if command -v jq >/dev/null 2>&1; then
    fallback_bin=$test_root/jq-only-bin
    fallback_event_dir=$test_root/jq-fallback-data
    mkdir -p "$fallback_bin"
    for tool in date dirname jq mkdir; do
        tool_path=$(command -v "$tool") || fail "缺少 jq 回退测试工具：$tool"
        ln -s "$tool_path" "$fallback_bin/$tool"
    done
    set +e
    fallback_output=$(cd -- "$repo" && PATH="$fallback_bin" \
        CODEX_HOOK_DATA_DIR="$fallback_event_dir" "$bash_path" "$event_script" \
        session-start ok "$control_detail" 2>&1)
    fallback_status=$?
    set -e
    (( fallback_status == 0 )) || fail "jq JSON 编码回退失败\n输出：\n$fallback_output"
    if ! jsonl_control_detail_valid "$fallback_event_dir/events.jsonl"; then
        fail 'jq 回退生成的事件不是合法 JSONL'
    fi
fi

missing_parser_bin=$test_root/no-json-parser-bin
mkdir -p "$missing_parser_bin"
set +e
missing_parser_output=$(cd -- "$repo" && PATH="$missing_parser_bin" \
    "$bash_path" "$event_script" session-start 2>&1)
missing_parser_status=$?
set -e
(( missing_parser_status != 0 )) || fail '缺少 JSON 编码器时 codex-event 不应成功'
assert_contains "$missing_parser_output" 'JSON 编码需要 python3 或 jq'
printf 'PASS: 事件 JSON 对控制字符可靠编码并在 jq 回退/缺失时明确处理\n'

printf 'trailing whitespace  \n' > "$repo/untracked.txt"
set +e
output=$(cd -- "$repo" && "$verify_script" --paths untracked.txt 2>&1)
status=$?
set -e

(( status != 0 )) || fail '未跟踪文件的尾随空白不应通过 codex-verify'
assert_contains "$output" 'trailing whitespace'

printf 'PASS: 未跟踪文件的尾随空白被拒绝\n'

set +e
output=$(cd -- "$repo" && "$guard_script" -- new/created.sh ../outside.txt 2>&1)
guard_status=$?
set -e

(( guard_status != 0 )) || fail '仓库外路径与仓库内新路径的组合不应通过 codex-guard'
assert_contains "$output" 'before-edit allow: new/created.sh'
assert_contains "$output" '路径在仓库外'
printf 'PASS: 不存在的仓库内路径可规范化，仓库外路径被拒绝\n'

outside_dir=$test_root/outside
mkdir -p "$outside_dir"
ln -s "$outside_dir" "$repo/escape"
set +e
output=$(cd -- "$repo" && "$guard_script" -- escape/created.sh 2>&1)
symlink_status=$?
set -e

(( symlink_status != 0 )) || fail '经过仓库内符号链接逃逸的路径不应通过 codex-guard'
assert_contains "$output" '路径在仓库外'
printf 'PASS: 符号链接逃逸路径被拒绝\n'

set +e
output=$(cd -- "$repo" && "$guard_script" </dev/null 2>&1)
empty_guard_status=$?
set -e
(( empty_guard_status != 0 )) || fail '无路径且 stdin 为空时 codex-guard 不应成功'
assert_contains "$output" '未收到路径'

set +e
output=$(cd -- "$repo" && "$guard_script" <<< '' 2>&1)
blank_guard_status=$?
set -e
(( blank_guard_status != 0 )) || fail '空 stdin 时 codex-guard 不应成功'
assert_contains "$output" '未收到路径'

set +e
output=$(cd -- "$repo" && "$guard_script" <<< '{}' 2>&1)
json_guard_status=$?
set -e
(( json_guard_status != 0 )) || fail 'JSON payload 无路径时 codex-guard 不应成功'
assert_contains "$output" 'JSON payload 未能提取路径'
printf 'PASS: codex-guard 对空路径输入 fail-closed\n'

set +e
output=$(cd -- "$repo" && "$verify_script" --paths missing.sh 2>&1)
missing_status=$?
set -e

(( missing_status != 0 )) || fail '显式指定的不存在路径不应通过 codex-verify'
assert_contains "$output" '路径不存在或不是普通文件'

printf 'PASS: 不存在的显式路径被拒绝\n'

committed_repo=$test_root/committed-repo
mkdir -p "$committed_repo"
git -C "$committed_repo" init -q
git -C "$committed_repo" config user.name 'Hook Test'
git -C "$committed_repo" config user.email 'hook-test@example.invalid'
printf '#!/usr/bin/env bash\nprintf "ok\\n"\n' > "$committed_repo/tracked.sh"
git -C "$committed_repo" add -- tracked.sh
git -C "$committed_repo" commit -qm initial
mkdir -p "$committed_repo/data/runs"
set +e
runtime_guard_output=$(cd -- "$committed_repo" && "$guard_script" -- data/runs/session 2>&1)
runtime_guard_status=$?
set -e
(( runtime_guard_status != 0 )) || fail 'agent runtime 数据路径不应通过 codex-guard'
assert_contains "$runtime_guard_output" 'agent 运行时数据'
printf 'PASS: agent runtime 数据路径被保护\n'

printf '#!/usr/bin/env bash\nif [\n' > "$committed_repo/staged.sh"
git -C "$committed_repo" add -- staged.sh

set +e
output=$(cd -- "$committed_repo" && "$verify_script" --changed 2>&1)
changed_status=$?
set -e

(( changed_status != 0 )) || fail '仅暂存的 Shell 文件应被 --changed 检查'
assert_contains "$output" 'staged.sh'
assert_contains "$output" 'bash -n 失败'
printf 'PASS: --changed 包含仅暂存的文件\n'

staged_whitespace_repo=$test_root/staged-whitespace-repo
mkdir -p "$staged_whitespace_repo"
git -C "$staged_whitespace_repo" init -q
git -C "$staged_whitespace_repo" config user.name 'Hook Test'
git -C "$staged_whitespace_repo" config user.email 'hook-test@example.invalid'
printf 'clean\n' > "$staged_whitespace_repo/staged.txt"
git -C "$staged_whitespace_repo" add -- staged.txt
git -C "$staged_whitespace_repo" commit -qm initial
printf 'trailing whitespace  \n' > "$staged_whitespace_repo/staged.txt"
git -C "$staged_whitespace_repo" add -- staged.txt

set +e
output=$(cd -- "$staged_whitespace_repo" && "$verify_script" --changed 2>&1)
staged_whitespace_status=$?
set -e

(( staged_whitespace_status != 0 )) || fail '仅暂存的尾随空白不应通过 codex-verify --changed'
assert_contains "$output" 'git diff --cached --check 失败'
assert_contains "$output" 'staged.txt'
printf 'PASS: --changed 检查仅暂存的尾随空白\n'

set +e
output=$(cd -- "$staged_whitespace_repo" && "$verify_script" --paths staged.txt 2>&1)
staged_paths_status=$?
set -e

(( staged_paths_status != 0 )) || fail '仅暂存的尾随空白不应通过 codex-verify --paths'
assert_contains "$output" 'git diff --cached --check 失败'
assert_contains "$output" 'staged.txt'
printf 'PASS: --paths 检查仅暂存的尾随空白\n'

printf '#!/usr/bin/env bash\necho tracked\n' > "$committed_repo/tracked.sh"
printf 'summary scratch\n' > "$committed_repo/untracked.txt"

baseline_status=$(cd -- "$committed_repo" && git status --short --untracked-files=normal)
committed_repo_realpath=$(cd -- "$committed_repo" && pwd -P)

set +e
output=$(cd -- "$committed_repo" && "$hook_script" session-summary 2>&1)
summary_status=$?
set -e

(( summary_status == 0 )) || fail "session-summary 不应失败\n输出：\n$output"
assert_contains "$output" 'codex-summary event=session-summary'
assert_contains "$output" "repo_root=$committed_repo_realpath"
assert_contains "$output" 'worktree_status=dirty'
assert_contains "$output" 'staged_count=1'
assert_contains "$output" 'unstaged_count=1'
assert_contains "$output" 'untracked_count=1'
assert_contains "$output" 'last_commit='
assert_contains "$output" 'tracked.sh'
assert_contains "$output" 'staged.sh'
assert_contains "$output" 'untracked.txt'

after_status=$(cd -- "$committed_repo" && git status --short --untracked-files=normal)
[[ "$after_status" == "$baseline_status" ]] || fail 'session-summary 不应修改工作树'

set +e
output=$(cd -- "$committed_repo" && "$hook_script" handoff 2>&1)
handoff_status=$?
set -e

(( handoff_status == 0 )) || fail "handoff 别名不应失败\n输出：\n$output"
assert_contains "$output" 'codex-summary event=session-summary'
after_alias_status=$(cd -- "$committed_repo" && git status --short --untracked-files=normal)
[[ "$after_alias_status" == "$baseline_status" ]] || fail 'handoff 不应修改工作树'

printf 'PASS: session-summary/handoff 输出只读摘要\n'

check_script=$script_dir/check.sh
staged_repo=$test_root/staged-repo
mkdir -p "$staged_repo/skills"
git -C "$staged_repo" init -q
printf '#!/usr/bin/env bash\necho staged\n' > "$staged_repo/skills/demo"
chmod 0755 "$staged_repo/skills/demo"
git -C "$staged_repo" add -- skills/demo

fake_bin=$test_root/fake-git-bin
mkdir -p "$fake_bin"
real_git=$(command -v git)
cat > "$fake_bin/git" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == show ]]; then
    printf 'simulated git show failure\n' >&2
    exit 1
fi
exec "$REAL_GIT" "$@"
EOF
chmod 0755 "$fake_bin/git"

set +e
output=$(cd -- "$staged_repo" && REAL_GIT="$real_git" PATH="$fake_bin:$PATH" bash "$check_script" --staged 2>&1)
show_status=$?
set -e

(( show_status != 0 )) || fail '暂存内容读取失败时 check.sh 不应通过'
assert_contains "$output" '无法读取暂存内容'

printf 'PASS: 暂存内容读取失败被报告\n'

mode_repo=$test_root/mode-repo
mkdir -p "$mode_repo/skills/form/references/source-snapshots/vendor"
git -C "$mode_repo" init -q
git -C "$mode_repo" config user.name 'Hook Test'
git -C "$mode_repo" config user.email 'hook-test@example.invalid'
printf '#!/usr/bin/env bash\necho entry\n' > "$mode_repo/skills/entry"
chmod 0755 "$mode_repo/skills/entry"
printf '# non-shell documentation\n' > "$mode_repo/skills/README.md"
printf '#!/usr/bin/env bash\necho upstream\n' \
    > "$mode_repo/skills/form/references/source-snapshots/vendor/upstream.sh"
chmod 0644 "$mode_repo/skills/form/references/source-snapshots/vendor/upstream.sh"
git -C "$mode_repo" add -- skills
git -C "$mode_repo" commit -qm initial

set +e
output=$(cd -- "$mode_repo" && bash "$check_script" --tracked 2>&1)
mode_baseline_status=$?
set -e
(( mode_baseline_status == 0 )) || fail "合理非 Shell 文件与快照不应触发权限失败\n输出：\n$output"

git -C "$mode_repo" update-index --chmod=-x -- skills/entry
set +e
staged_mode_output=$(cd -- "$mode_repo" && bash "$check_script" --staged 2>&1)
staged_mode_status=$?
tracked_mode_output=$(cd -- "$mode_repo" && bash "$check_script" --tracked 2>&1)
tracked_mode_status=$?
set -e

(( staged_mode_status != 0 )) || fail 'mode-only 100755→100644 变更不应通过 check.sh --staged'
(( tracked_mode_status != 0 )) || fail '索引中非可执行 Shell 入口不应通过 check.sh --tracked'
assert_contains "$staged_mode_output" 'Shell 入口索引权限应为 100755'
assert_contains "$staged_mode_output" '100644'
assert_contains "$tracked_mode_output" 'Shell 入口索引权限应为 100755'
assert_contains "$tracked_mode_output" '100644'
printf 'PASS: check.sh 校验 Shell 入口索引权限并保留快照例外\n'
