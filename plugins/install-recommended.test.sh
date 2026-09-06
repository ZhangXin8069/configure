#!/usr/bin/env bash

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
installer=$script_dir/install-recommended.sh
test_root=$(mktemp -d "${TMPDIR:-/tmp}/install-recommended-test.XXXXXX")

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
        *) ;;
    esac
}

clean_path=/usr/bin:/bin
set +e
dry_output=$(PATH="$clean_path" bash "$installer" --dry-run superpowers 2>&1)
dry_status=$?
set -e
(( dry_status == 0 )) || fail '官方插件 dry-run 意外失败'
assert_contains "$dry_output" 'codex plugin marketplace add openai/plugins'
assert_contains "$dry_output" 'codex plugin add superpowers --marketplace openai-curated'
printf 'PASS: dry-run 展示完整官方 marketplace 命令\n'

set +e
ref_output=$(PATH="$clean_path" bash "$installer" --dry-run ecc 2>&1)
ref_status=$?
set -e
(( ref_status != 0 )) || fail '社区插件缺少固定 ref 时不应通过'
assert_contains "$ref_output" '社区插件必须显式指定固定 Git ref'
printf 'PASS: 社区插件缺少固定 ref 时被拒绝\n'

fake_bin=$test_root/fake-bin
mkdir -p "$fake_bin"
call_log=$test_root/calls.log
cat > "$fake_bin/codex" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$CODEX_CALL_LOG"
case "$*" in
    'plugin marketplace --help'|'plugin add --help') exit 0 ;;
    'plugin marketplace list --json')
        if [[ "${FAKE_MARKETPLACE_STATE:-failure}" == absent ]]; then
            printf '%s\n' '{"marketplaces":[]}'
            exit 0
        fi
        if [[ "${FAKE_MARKETPLACE_STATE:-failure}" == configured ]]; then
            printf '%s\n' '{"marketplaces":[{"name":"ecc"}]}'
            exit 0
        fi
        exit 1
        ;;
    'plugin list --json')
        printf '%s\n' '{"installed":[{"name":"ecc","installed":true}]}'
        exit 0
        ;;
    *) exit 0 ;;
esac
EOF
chmod 0755 "$fake_bin/codex"

set +e
query_output=$(CODEX_CALL_LOG="$call_log" PATH="$fake_bin:$clean_path" \
    bash "$installer" --ref v2.2.0 ecc 2>&1)
query_status=$?
set -e
(( query_status != 0 )) || fail 'marketplace 查询失败时不应继续安装'
assert_contains "$query_output" 'marketplace 查询失败'
calls=$(< "$call_log")
assert_not_contains "$calls" 'plugin marketplace add'
assert_not_contains "$calls" 'plugin add ecc'
printf 'PASS: marketplace 查询失败时 fail-closed\n'

for state in absent configured; do
    : > "$call_log"
    set +e
    state_output=$(FAKE_MARKETPLACE_STATE="$state" CODEX_CALL_LOG="$call_log" PATH="$fake_bin:$clean_path" \
        bash "$installer" --ref v2.2.0 ecc 2>&1)
    state_status=$?
    set -e
    (( state_status == 0 )) || fail "合法 JSON 状态意外失败：$state\n输出：\n$state_output"
    state_calls=$(< "$call_log")
    if [[ "$state" == absent ]]; then
        assert_contains "$state_calls" 'plugin marketplace add affaan-m/ECC --ref v2.2.0'
    else
        assert_not_contains "$state_calls" 'plugin marketplace add'
    fi
    assert_contains "$state_calls" 'plugin add ecc --marketplace ecc'
done
printf 'PASS: marketplace 合法 JSON 的未匹配/已配置状态正确\n'
