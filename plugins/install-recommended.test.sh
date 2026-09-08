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
default_output=$(PATH="$clean_path" bash "$installer" --dry-run 2>&1)
default_status=$?
set -e
(( default_status == 0 )) || fail "默认 profile 在精简 Bash 环境中意外失败\n输出：\n$default_output"
assert_contains "$default_output" '目标插件：superpowers nvidia zotero'
official_marketplace_adds=$(printf '%s\n' "$default_output" | grep -c 'codex plugin marketplace add openai/plugins' || true)
(( official_marketplace_adds == 1 )) || fail '默认 profile 的 dry-run 不应重复注册官方 marketplace'
printf 'PASS: 默认 profile 兼容无 mapfile 的 Bash 环境\n'

set +e
research_output=$(PATH="$clean_path" bash "$installer" --profile research-workbench --dry-run 2>&1)
research_status=$?
set -e
(( research_status == 0 )) || fail "research-workbench profile 在精简 Bash 环境中意外失败\n输出：\n$research_output"
assert_contains "$research_output" '组合定位：物理/ML 研究、文献、模型、图表和报告。'
assert_contains "$research_output" '目标插件：nvidia zotero hugging-face notion google-drive build-web-data-visualization'
assert_contains "$research_output" '提示：hugging-face 可能需要在首次使用时完成外部账号授权或连接；本脚本不会代为登录。'
printf 'PASS: research-workbench profile 的 dry-run 与提示信息覆盖\n'

set +e
workspace_output=$(PATH="$clean_path" bash "$installer" --profile workspace --dry-run 2>&1)
workspace_status=$?
set -e
(( workspace_status == 0 )) || fail "workspace profile 在精简 Bash 环境中意外失败\n输出：\n$workspace_output"
assert_contains "$workspace_output" '提示：workspace 会连接外部文档/账号；首次使用通常要完成 OAuth 或服务授权。'
assert_contains "$workspace_output" '组合定位：日常协作、知识库、文件和结构化台账。'
assert_contains "$workspace_output" '目标插件：notion google-drive airtable'
assert_contains "$workspace_output" '提示：notion 可能需要在首次使用时完成外部账号授权或连接；本脚本不会代为登录。'
printf 'PASS: workspace profile 的 dry-run 与候选提示覆盖\n'

set +e
appdev_output=$(PATH="$clean_path" bash "$installer" --profile app-dev --dry-run 2>&1)
appdev_status=$?
set -e
(( appdev_status == 0 )) || fail "app-dev profile 在精简 Bash 环境中意外失败\n输出：\n$appdev_output"
assert_contains "$appdev_output" '该 profile 含多个大体量或职责重叠插件；建议先用 --dry-run 复核。'
assert_contains "$appdev_output" '组合定位：前端、移动端、设计联动和部署发布。'
assert_contains "$appdev_output" '目标插件：figma build-web-apps build-ios-apps build-macos-apps expo netlify'
assert_contains "$appdev_output" '提示：figma 可能需要在首次使用时完成外部账号授权或连接；本脚本不会代为登录。'
printf 'PASS: app-dev profile 的 dry-run 与候选提示覆盖\n'

set +e
all_output=$(PATH="$clean_path" bash "$installer" --ref v2.2.0 --profile all --dry-run 2>&1)
all_status=$?
set -e
(( all_status == 0 )) || fail "all profile 在精简 Bash 环境中意外失败\n输出：\n$all_output"
assert_contains "$all_output" 'Git ref：v2.2.0'
assert_contains "$all_output" '组合定位：全部登记项，风险最高。'
assert_contains "$all_output" 'build-web-data-visualization figma build-web-apps build-ios-apps build-macos-apps expo netlify'
printf 'PASS: all profile 包含新增官方候选\n'

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
        printf '%s\n' '{"installed":[{"name":"ecc","installed":true},{"name":"superpowers","installed":true}]}'
        exit 0
        ;;
    'plugin list --available --json')
        printf '%s\n' '{"installed":[{"name":"ecc","marketplaceName":"ecc","installed":true}],"available":[{"name":"superpowers","marketplaceName":"openai-api-curated","installed":false}]}'
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

: > "$call_log"
set +e
official_output=$(CODEX_CALL_LOG="$call_log" PATH="$fake_bin:$clean_path" \
    bash "$installer" superpowers 2>&1)
official_status=$?
set -e
(( official_status == 0 )) || fail "官方 marketplace 动态发现意外失败\n输出：\n$official_output"
official_calls=$(< "$call_log")
assert_contains "$official_calls" 'plugin add superpowers --marketplace openai-api-curated'
printf 'PASS: 官方 marketplace 名称从 Codex JSON 动态发现\n'
