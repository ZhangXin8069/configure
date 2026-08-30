#!/usr/bin/env bash

set -u
set -o pipefail
export LC_ALL=C

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd)
checker="$script_dir/tag-chain.sh"
test_root=$(mktemp -d "${TMPDIR:-/tmp}/tag-chain-test.XXXXXX")

cleanup() {
    rm -rf "$test_root"
}
trap cleanup EXIT HUP INT TERM

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_contains() {
    case "$1" in
        *"$2"*) ;;
        *) fail "输出缺少: $2" ;;
    esac
}

repo="$test_root/repo"
remote="$test_root/remote.git"
git init -q "$repo" || fail '初始化测试仓库失败'
git -C "$repo" config user.name 'Tag Chain Test'
git -C "$repo" config user.email 'tag-chain-test@example.invalid'

commit_file() {
    local message=$1
    local stamp=$2
    printf '%s\n' "$message" >> "$repo/history.txt"
    git -C "$repo" add history.txt || fail "暂存失败: $message"
    GIT_AUTHOR_DATE="$stamp" GIT_COMMITTER_DATE="$stamp" \
        git -C "$repo" commit -q -m "$message" || fail "提交失败: $message"
}

make_tag() {
    local tag_name=$1
    local stamp=$2
    local message=$3
    local target=$4
    GIT_COMMITTER_DATE="$stamp" git -C "$repo" tag -a "$tag_name" "$target" -m "$message" || \
        fail "创建标签失败: $tag_name"
}

commit_file init '2024-01-01T00:00:00Z'
root_commit=$(git -C "$repo" rev-parse HEAD)
# The root tagger date is intentionally later than its descendants.  init,
# rather than the timestamp, must anchor the chain.
make_tag stab0 '2030-01-01T00:00:00Z' 'stab0 init, 1. init; [test].' "$root_commit"
root_tag_date=$(git -C "$repo" for-each-ref --format='%(creatordate:unix)' refs/tags/stab0)

commit_file dev '2024-01-02T00:00:00Z'
dev_commit=$(git -C "$repo" rev-parse HEAD)
make_tag dev0 '2024-01-02T00:00:01Z' 'follow stab0, 1. dev; [test].' "$dev_commit"

commit_file stable '2024-01-03T00:00:00Z'
stable_commit=$(git -C "$repo" rev-parse HEAD)
make_tag stab1 '2024-01-03T00:00:01Z' 'follow stab0, 1. stable; [test].' "$stable_commit"

commit_file bug '2024-01-04T00:00:00Z'
bug_commit=$(git -C "$repo" rev-parse HEAD)
make_tag bug0 '2024-01-04T00:00:01Z' 'NVIDIA CUDA 默认线程块性能调优与显存回归; [test].' "$bug_commit"

if output=$(bash "$checker" --check --repo "$repo" 2>&1); then
    fail '错误链检查意外通过'
fi
assert_contains "$output" '[FIX] stab1: follow stab0 -> follow dev0'
assert_contains "$output" '[FIX] bug0: 缺少 follow 前缀 -> 补 follow stab1'

old_stable_object=$(git -C "$repo" rev-parse refs/tags/stab1)
if output=$(bash "$checker" --repair --dry-run --repo "$repo" 2>&1); then
    fail 'dry-run 意外返回成功'
fi
assert_contains "$output" 'DRY-RUN: 未写入任何本地或远程标签。'
[ "$(git -C "$repo" rev-parse refs/tags/stab1)" = "$old_stable_object" ] || \
    fail 'dry-run 改写了本地标签'

bash "$checker" --repair --apply --repo "$repo" >/dev/null || fail '本地修正失败'
subject=$(git -C "$repo" for-each-ref --format='%(contents:subject)' refs/tags/stab1)
[ "$subject" = 'follow dev0, 1. stable; [test].' ] || fail "stab1 消息错误: $subject"
subject=$(git -C "$repo" for-each-ref --format='%(contents:subject)' refs/tags/bug0)
[ "$subject" = 'follow stab1, NVIDIA CUDA 默认线程块性能调优与显存回归; [test].' ] || fail "bug0 消息错误: $subject"
[ "$(git -C "$repo" rev-parse 'stab1^{}')" = "$stable_commit" ] || fail 'stab1 peeled commit 被改变'
[ "$(git -C "$repo" rev-parse 'bug0^{}')" = "$bug_commit" ] || fail 'bug0 peeled commit 被改变'
[ "$(git -C "$repo" for-each-ref --format='%(creatordate:unix)' refs/tags/stab0)" = \
    "$root_tag_date" ] || fail '根标签 tagger 日期未保留'

local_refs_before=$(git -C "$repo" show-ref --tags)
bash "$checker" --repair --apply --repo "$repo" >/dev/null || fail '重复本地修正失败'
local_refs_after=$(git -C "$repo" show-ref --tags)
[ "$local_refs_after" = "$local_refs_before" ] || fail '重复修正改变了本地标签 refs'

commit_file remote '2024-01-05T00:00:00Z'
remote_commit=$(git -C "$repo" rev-parse HEAD)
make_tag dev1 '2024-01-05T00:00:01Z' 'follow stab0, 1. remote; [test].' "$remote_commit"
git init -q --bare "$remote" || fail '初始化测试远端失败'
git -C "$repo" remote add origin "$remote"
git -C "$repo" push -q --set-upstream origin HEAD
git -C "$repo" push -q origin --tags

bash "$checker" --repair --apply --repo "$repo" --remote origin \
    --confirm-remote-rewrite >/dev/null || fail '远端修正失败'
remote_subject=$(git -C "$repo" for-each-ref --format='%(contents:subject)' refs/tags/dev1)
[ "$remote_subject" = 'follow bug0, 1. remote; [test].' ] || fail "dev1 本地消息错误: $remote_subject"
[ "$(git -C "$repo" rev-parse 'dev1^{}')" = "$remote_commit" ] || fail 'dev1 peeled commit 被改变'
bash "$checker" --check --repo "$repo" --remote origin >/dev/null || fail '远端修正后的检查失败'

printf 'PASS: tag-chain 自检、dry-run、本地修正和远端 lease 重写测试通过。\n'
