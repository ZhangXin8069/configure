#!/usr/bin/env bash

set -u
set -o pipefail
export LC_ALL=C

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd)
resolver="$script_dir/tag-baseline.sh"
test_root=$(mktemp -d "${TMPDIR:-/tmp}/tag-baseline-test.XXXXXX")

cleanup() {
    rm -rf "$test_root"
}
trap cleanup EXIT HUP INT TERM

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_eq() {
    [ "$1" = "$2" ] || fail "期望 [$2]，实际 [$1]"
}

make_repo() {
    local repo=$1
    git init -q "$repo" || fail "初始化测试仓库失败: $repo"
    git -C "$repo" config user.name 'Tag Baseline Test'
    git -C "$repo" config user.email 'tag-baseline-test@example.invalid'
}

commit_file() {
    local repo=$1
    local message=$2
    local stamp=$3
    printf '%s\n' "$message" >> "$repo/history.txt"
    git -C "$repo" add history.txt || fail "暂存失败: $message"
    GIT_AUTHOR_DATE="$stamp" GIT_COMMITTER_DATE="$stamp" \
        git -C "$repo" commit -q -m "$message" || fail "提交失败: $message"
}

make_tag() {
    local repo=$1
    local tag_name=$2
    local stamp=$3
    local message=$4
    GIT_COMMITTER_DATE="$stamp" git -C "$repo" tag -a "$tag_name" -m "$message" || \
        fail "创建标签失败: $tag_name"
}

repo="$test_root/repo"
make_repo "$repo"

commit_file "$repo" root '2024-01-01T00:00:00Z'
make_tag "$repo" stab5 '2024-01-01T00:00:01Z' 'stab5 init, 1. root; [test].'

commit_file "$repo" bug '2024-03-01T00:00:00Z'
make_tag "$repo" bug1 '2024-03-01T00:00:01Z' 'follow stab5, 1. bug; [test].'

commit_file "$repo" dev '2024-06-01T00:00:00Z'
make_tag "$repo" dev2 '2024-06-01T00:00:01Z' 'follow bug1, 1. dev; [test].'
make_tag "$repo" test3 '2024-06-01T00:00:01Z' 'follow dev2, 1. tie; [test].'

commit_file "$repo" unrelated '2024-07-01T00:00:00Z'
make_tag "$repo" v1.0 '2024-07-01T00:00:01Z' 'unmanaged tag.'

latest=$(bash "$resolver" --repo "$repo" --latest) || fail '解析最新标签失败'
assert_eq "$latest" 'test3'

list=$(bash "$resolver" --repo "$repo" --list) || fail '列出标签失败'
expected_list=$(printf 'test3\ndev2\nbug1\nstab5')
assert_eq "$list" "$expected_list"

assert_eq "$(bash "$resolver" --repo "$repo" --previous dev2)" 'bug1'
assert_eq "$(bash "$resolver" --repo "$repo" --previous bug1)" 'stab5'
assert_eq "$(bash "$resolver" --repo "$repo" --previous stab5)" ''

if bash "$resolver" --repo "$repo" --previous v1.0 >/dev/null 2>&1; then
    fail '非受管标签不应作为前驱目标'
fi

empty_repo="$test_root/empty-repo"
make_repo "$empty_repo"
assert_eq "$(bash "$resolver" --repo "$empty_repo" --latest)" ''
assert_eq "$(bash "$resolver" --repo "$empty_repo" --list)" ''

printf 'PASS: tag 基线按 tagger 时间选择并支持前驱解析。\n'
