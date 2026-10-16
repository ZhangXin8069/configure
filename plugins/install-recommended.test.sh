#!/usr/bin/env bash

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
installer=$script_dir/install-recommended.sh
test_root=$(mktemp -d "${TMPDIR:-/tmp}/install-recommended-test.XXXXXX")
export CODEX_HOME=$test_root/codex-home
mkdir -p "$CODEX_HOME"

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
real_git=$(command -v git)
export REAL_GIT="$real_git"
help_output=$(bash "$installer" --help 2>&1)
assert_contains "$help_output" '76aaa77df6adc5b889e689007bf99b9a4f74af34'
assert_not_contains "$help_output" '0123456789abcdef0123456789abcdef01234567'
printf 'PASS: help 示例使用真实固定 commit\n'

git_bin=$test_root/git-bin
git_log=$test_root/git.log
mkdir -p "$git_bin"
cat > "$git_bin/git" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${FAKE_GIT_LOG:-/dev/null}"
if [[ "${1:-}" == check-ref-format ]]; then
    exec "$REAL_GIT" "$@"
fi
if [[ "${FAKE_GIT_STATE:-verified}" == network-failure ]]; then
    exit 128
fi
if [[ $# -eq 5 && "$1" == ls-remote && "$2" == --exit-code && "$3" == --tags &&
      "$5" == "refs/tags/${FAKE_VALID_TAG:-v2.2.0}" ]]; then
    exit 0
fi
exit 2
EOF
chmod 0755 "$git_bin/git"

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
all_output=$(PATH="$clean_path" bash "$installer" --profile all --dry-run 2>&1)
all_status=$?
set -e
(( all_status == 0 )) || fail "all profile 在精简 Bash 环境中意外失败\n输出：\n$all_output"
assert_contains "$all_output" '社区插件使用内建固定 commit'
assert_contains "$all_output" '组合定位：全部登记项，风险最高。'
assert_contains "$all_output" 'build-web-data-visualization figma build-web-apps build-ios-apps build-macos-apps expo netlify'
assert_contains "$all_output" 'affaan-m/ECC --ref 76aaa77df6adc5b889e689007bf99b9a4f74af34'
assert_contains "$all_output" 'addyosmani/agent-skills --ref aeac41d4d005999432bb7312f7ff06383a91d59d'
assert_contains "$all_output" 'EveryInc/compound-engineering-plugin --ref fac349c0c31a543d497fd4825af9b44bdb7e7dfe'
assert_contains "$all_output" 'a5c-ai/babysitter-codex --ref 694028503ae14a1111d4e32eaa5279752bc2194c'
printf 'PASS: all profile 包含新增官方候选\n'

set +e
global_ref_output=$(PATH="$clean_path" bash "$installer" --profile all \
    --ref 76aaa77df6adc5b889e689007bf99b9a4f74af34 --dry-run 2>&1)
global_ref_status=$?
set -e
(( global_ref_status != 0 )) || fail '单个 --ref 不应覆盖多个社区插件'
assert_contains "$global_ref_output" '单次 --ref 只能覆盖一个社区插件'
printf 'PASS: 多社区 profile 拒绝共享一个 --ref\n'

set +e
ref_output=$(PATH="$clean_path" bash "$installer" --dry-run ecc 2>&1)
ref_status=$?
set -e
(( ref_status == 0 )) || fail "社区插件内建固定 ref 时不应失败\n输出：\n$ref_output"
assert_contains "$ref_output" 'affaan-m/ECC --ref 76aaa77df6adc5b889e689007bf99b9a4f74af34'
printf 'PASS: 社区插件使用内建完整 commit\n'

fake_bin=$test_root/fake-bin
mkdir -p "$fake_bin"
call_log=$test_root/calls.log
cat > "$fake_bin/codex" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$CODEX_CALL_LOG"
if [[ "$*" == 'plugin add '* && "$*" != 'plugin add --help' ]]; then
    exit "${FAKE_PLUGIN_ADD_RC:-0}"
fi
official_marketplace="${FAKE_OFFICIAL_MARKETPLACE:-openai-api-curated}"
case "$*" in
    'plugin marketplace --help'|'plugin add --help'|'plugin list --help') exit 0 ;;
    'plugin marketplace list --json')
        if [[ "${FAKE_STATUS_STATE:-normal}" == status ]]; then
            printf '%s\n' '{"marketplaces":[{"name":"openai-api-curated"},{"name":"ecc"}]}'
            exit 0
        fi
        if [[ "${FAKE_STATUS_STATE:-normal}" == unconfigured ]]; then
            printf '%s\n' '{"marketplaces":[{"name":"ecc"}]}'
            exit 0
        fi
        if [[ "${FAKE_STATUS_STATE:-normal}" == bad-marketplace-name ]]; then
            printf '%s\n' '{"marketplaces":[{"name":123}]}'
            exit 0
        fi
        case "${FAKE_MARKETPLACE_STATE:-failure}" in
            absent) printf '%s\n' '{"marketplaces":[]}' ;;
            configured) printf '%s\n' '{"marketplaces":[{"name":"ecc"}]}' ;;
            bad-json) printf '%s\n' '{broken-json' ;;
            bad-schema) printf '%s\n' '{"marketplaces":{}}' ;;
            *) exit 1 ;;
        esac
        exit 0
        ;;
    'plugin list --json')
        if [[ "${FAKE_STATUS_STATE:-normal}" == status ]]; then
            printf '%s\n' '{"installed":[{"name":"superpowers","installed":true},{"name":"ecc","installed":true}]}'
            exit 0
        fi
        case "${FAKE_INSTALLED_STATE:-match}" in
            mismatch)
                printf '%s\n' '{"installed":[{"name":"ecc","marketplaceName":"other","installed":true},{"name":"superpowers","marketplaceName":"openai-api-curated","installed":true}]}'
                ;;
            bad-json)
                printf '%s\n' '{broken-json'
                ;;
            *)
                printf '{"installed":[{"name":"ecc","marketplaceName":"ecc","installed":true},{"name":"superpowers","marketplaceName":"%s","installed":true}]}\n' \
                    "$official_marketplace"
                ;;
        esac
        exit 0
        ;;
    'plugin list --available --json')
        if [[ "${FAKE_STATUS_STATE:-normal}" == status ]]; then
            printf '%s\n' '{"installed":[{"name":"superpowers","marketplaceName":"openai-api-curated","installed":true},{"name":"ecc","marketplaceName":"ecc","installed":true}],"available":[{"name":"nvidia","marketplaceName":"openai-api-curated","installed":false}]}'
            exit 0
        fi
        printf '{"installed":[{"name":"ecc","marketplaceName":"ecc","installed":true}],"available":[{"name":"superpowers","marketplaceName":"%s","installed":false}]}\n' \
            "$official_marketplace"
        exit 0
        ;;
    *) exit 0 ;;
esac
EOF
chmod 0755 "$fake_bin/codex"
test_path=$git_bin:$fake_bin:$clean_path

: > "$call_log"
set +e
query_output=$(CODEX_CALL_LOG="$call_log" PATH="$test_path" \
    bash "$installer" --ref v2.2.0 ecc 2>&1)
query_status=$?
set -e
(( query_status == 2 )) || fail "marketplace 查询失败应返回 2，实际：$query_status"
assert_contains "$query_output" 'marketplace 查询失败'
calls=$(< "$call_log")
assert_not_contains "$calls" 'plugin marketplace add'
assert_not_contains "$calls" 'plugin add ecc'
printf 'PASS: marketplace 查询失败时 fail-closed 并返回状态 2\n'

: > "$call_log"
set +e
absent_output=$(FAKE_MARKETPLACE_STATE=absent CODEX_CALL_LOG="$call_log" PATH="$test_path" \
    bash "$installer" --ref v2.2.0 ecc 2>&1)
absent_status=$?
set -e
(( absent_status == 0 )) || fail "确定不存在 marketplace 时应继续安装\n输出：\n$absent_output"
absent_calls=$(< "$call_log")
assert_contains "$absent_calls" 'plugin marketplace add affaan-m/ECC --ref v2.2.0'
assert_contains "$absent_calls" 'plugin add ecc --marketplace ecc'
printf 'PASS: 确定不存在 marketplace 时登记并安装\n'

: > "$call_log"
set +e
configured_output=$(FAKE_MARKETPLACE_STATE=configured CODEX_CALL_LOG="$call_log" PATH="$test_path" \
    bash "$installer" --ref v2.2.0 ecc 2>&1)
configured_status=$?
set -e
(( configured_status != 0 )) || fail '已配置社区 marketplace 无法证明 ref 时不应继续'
assert_contains "$configured_output" '不提供 source/ref'
assert_contains "$configured_output" '移除该 marketplace'
configured_calls=$(< "$call_log")
assert_not_contains "$configured_calls" 'plugin marketplace add'
assert_not_contains "$configured_calls" 'plugin add ecc'
printf 'PASS: 已配置社区 marketplace 无法证明 ref 时拒绝复用\n'

for state in bad-json bad-schema; do
    : > "$call_log"
    set +e
    bad_json_output=$(FAKE_MARKETPLACE_STATE="$state" CODEX_CALL_LOG="$call_log" PATH="$test_path" \
        bash "$installer" --ref v2.2.0 ecc 2>&1)
    bad_json_status=$?
    set -e
    (( bad_json_status == 2 )) || fail "坏 JSON 状态 $state 应返回 2，实际：$bad_json_status"
    assert_contains "$bad_json_output" 'JSON 解析/schema 校验失败'
    bad_json_calls=$(< "$call_log")
    assert_not_contains "$bad_json_calls" 'plugin marketplace add'
    assert_not_contains "$bad_json_calls" 'plugin add ecc'
done
printf 'PASS: JSON 解析/schema 异常返回状态 2 且不触发 add\n'

: > "$call_log"
set +e
official_output=$(CODEX_CALL_LOG="$call_log" PATH="$test_path" \
    bash "$installer" superpowers 2>&1)
official_status=$?
set -e
(( official_status == 0 )) || fail "官方 marketplace 动态发现意外失败\n输出：\n$official_output"
official_calls=$(< "$call_log")
assert_contains "$official_calls" 'plugin add superpowers --marketplace openai-api-curated'
printf 'PASS: 官方 marketplace 名称从 Codex JSON 动态发现\n'

: > "$call_log"
set +e
evil_output=$(FAKE_OFFICIAL_MARKETPLACE=openai-evil CODEX_CALL_LOG="$call_log" PATH="$test_path" \
    bash "$installer" superpowers 2>&1)
evil_status=$?
set -e
(( evil_status != 0 )) || fail 'openai-evil 等伪造前缀不应被视为官方 marketplace'
evil_calls=$(< "$call_log")
assert_not_contains "$evil_calls" 'plugin add superpowers --marketplace openai-evil'
assert_contains "$evil_calls" 'plugin add superpowers --marketplace openai-curated'
printf 'PASS: 官方 marketplace 只接受精确受信别名\n'

: > "$call_log"
set +e
status_output=$(FAKE_STATUS_STATE=status CODEX_CALL_LOG="$call_log" PATH="$test_path" \
    bash "$installer" --status superpowers nvidia ecc 2>&1)
status_rc=$?
set -e
(( status_rc == 0 )) || fail "status 查询不应失败\n输出：\n$status_output"
assert_contains "$status_output" 'superpowers'
assert_contains "$status_output" 'nvidia'
assert_contains "$status_output" '可用但未安装'
assert_contains "$status_output" 'ecc'
status_calls=$(< "$call_log")
assert_not_contains "$status_calls" 'plugin add'
assert_not_contains "$status_calls" 'marketplace add'
printf 'PASS: status 只读查询已安装/可用状态且不调用安装命令\n'

set +e
bad_status_output=$(FAKE_STATUS_STATE=bad-marketplace-name CODEX_CALL_LOG="$call_log" PATH="$test_path" \
    bash "$installer" --status zotero 2>&1)
bad_status_rc=$?
set -e
(( bad_status_rc == 2 )) || fail "marketplace 行字段类型错误时应返回 2，实际：$bad_status_rc"
assert_contains "$bad_status_output" 'marketplace JSON 无效'
printf 'PASS: status schema 错误在 Python 解析分支返回 2\n'

: > "$call_log"
set +e
unconfigured_output=$(FAKE_STATUS_STATE=unconfigured CODEX_CALL_LOG="$call_log" PATH="$test_path" \
    bash "$installer" --audit zotero 2>&1)
unconfigured_rc=$?
set -e
(( unconfigured_rc == 0 )) || fail "未配置 marketplace 的 status 不应失败\n输出：\n$unconfigured_output"
assert_contains "$unconfigured_output" 'zotero'
assert_contains "$unconfigured_output" 'marketplace 未配置'
printf 'PASS: audit 别名报告 marketplace 未配置\n'

set +e
commit_reject_output=$(PATH="$clean_path" bash "$installer" --dry-run --ref-policy commit --ref main ecc 2>&1)
commit_reject_rc=$?
set -e
(( commit_reject_rc != 0 )) || fail 'commit 策略不应接受浮动 ref'
assert_contains "$commit_reject_output" '--ref-policy commit 要求 40 或 64 位十六进制提交哈希'

commit_ref=76aaa77df6adc5b889e689007bf99b9a4f74af34
set +e
commit_accept_output=$(PATH="$clean_path" bash "$installer" --dry-run --ref-policy commit --ref "$commit_ref" ecc 2>&1)
commit_accept_rc=$?
set -e
(( commit_accept_rc == 0 )) || fail "commit 策略应接受 40 位提交哈希\n输出：\n$commit_accept_output"
assert_contains "$commit_accept_output" "marketplace add affaan-m/ECC --ref $commit_ref"
printf 'PASS: commit ref 策略拒绝浮动分支并接受提交哈希\n'

commit_ref_64=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
set +e
commit_accept_output_64=$(PATH="$clean_path" bash "$installer" --dry-run --ref-policy commit --ref "$commit_ref_64" ecc 2>&1)
commit_accept_rc_64=$?
set -e
(( commit_accept_rc_64 == 0 )) || fail "commit 策略应接受 64 位提交哈希\n输出：\n$commit_accept_output_64"
assert_contains "$commit_accept_output_64" "marketplace add affaan-m/ECC --ref $commit_ref_64"
printf 'PASS: commit ref 策略接受 64 位提交哈希\n'

: > "$git_log"
set +e
branch_output=$(FAKE_GIT_LOG="$git_log" PATH="$git_bin:$clean_path" \
    bash "$installer" --dry-run --ref main ecc 2>&1)
branch_status=$?
set -e
(( branch_status != 0 )) || fail '默认策略不应接受浮动 main 分支'
assert_contains "$branch_output" '拒绝浮动分支 ref'
branch_git_calls=$(< "$git_log")
assert_not_contains "$branch_git_calls" 'ls-remote'
printf 'PASS: 默认策略拒绝 main/master 等浮动分支\n'

set +e
wildcard_output=$(PATH="$clean_path" bash "$installer" --dry-run --ref '*' ecc 2>&1)
wildcard_status=$?
set -e
(( wildcard_status != 0 )) || fail '通配 ref 不应通过固定 tag 校验'
assert_contains "$wildcard_output" '不是合法固定 tag'
assert_not_contains "$wildcard_output" 'codex plugin marketplace add'
printf 'PASS: 通配 ref 在校验前被拒绝\n'

: > "$git_log"
set +e
tag_output=$(FAKE_GIT_LOG="$git_log" FAKE_VALID_TAG=v2.1.0 PATH="$git_bin:$clean_path" \
    bash "$installer" --dry-run --ref v2.1.0 ecc 2>&1)
tag_status=$?
set -e
(( tag_status == 0 )) || fail "已存在 tag 应通过验证\n输出：\n$tag_output"
assert_contains "$tag_output" 'marketplace add affaan-m/ECC --ref v2.1.0'
tag_git_calls=$(< "$git_log")
assert_contains "$tag_git_calls" 'ls-remote --exit-code --tags https://github.com/affaan-m/ECC.git refs/tags/v2.1.0'
printf 'PASS: dry-run 用 ls-remote 验证并接受固定 tag\n'

set +e
network_output=$(FAKE_GIT_STATE=network-failure PATH="$git_bin:$clean_path" \
    bash "$installer" --dry-run --ref v2.1.0 ecc 2>&1)
network_status=$?
set -e
(( network_status != 0 )) || fail 'tag 验证网络失败时不应继续'
assert_contains "$network_output" '无法用 git ls-remote 验证 tag'
assert_not_contains "$network_output" 'codex plugin marketplace add'
printf 'PASS: tag 验证缺失网络时 fail-closed\n'

: > "$call_log"
set +e
mismatch_output=$(FAKE_MARKETPLACE_STATE=absent FAKE_INSTALLED_STATE=mismatch \
    CODEX_CALL_LOG="$call_log" PATH="$test_path" \
    bash "$installer" --ref v2.2.0 ecc 2>&1)
mismatch_status=$?
set -e
(( mismatch_status != 0 )) || fail '安装结果 marketplaceName 不匹配时不应通过验证'
assert_contains "$mismatch_output" '未在 codex plugin list --json 中找到匹配注册：ecc@ecc'
mismatch_calls=$(< "$call_log")
assert_contains "$mismatch_calls" 'plugin add ecc --marketplace ecc'
printf 'PASS: 安装后同时校验插件名与 marketplaceName\n'

: > "$call_log"
set +e
stop_output=$(FAKE_MARKETPLACE_STATE=absent FAKE_PLUGIN_ADD_RC=2 \
    CODEX_CALL_LOG="$call_log" PATH="$test_path" \
    bash "$installer" --profile engineering 2>&1)
stop_status=$?
set -e
(( stop_status == 2 )) || fail "首个安全失败状态 2 应原样返回，实际：$stop_status"
stop_calls=$(< "$call_log")
assert_contains "$stop_calls" 'plugin add ecc --marketplace ecc'
assert_not_contains "$stop_calls" 'plugin add agent-skills'
assert_contains "$stop_output" '停止处理后续目标'
printf 'PASS: 状态 2 保留并停止后续目标\n'
