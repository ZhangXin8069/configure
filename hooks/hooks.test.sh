#!/usr/bin/env bash

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
verify_script=$script_dir/codex-verify.sh
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

repo=$test_root/repo
mkdir -p "$repo"
git -C "$repo" init -q

printf 'trailing whitespace  \n' > "$repo/untracked.txt"
set +e
output=$(cd -- "$repo" && "$verify_script" --paths untracked.txt 2>&1)
status=$?
set -e

(( status != 0 )) || fail '未跟踪文件的尾随空白不应通过 codex-verify'
assert_contains "$output" 'trailing whitespace'

printf 'PASS: 未跟踪文件的尾随空白被拒绝\n'

set +e
output=$(cd -- "$repo" && "$verify_script" --paths missing.sh 2>&1)
missing_status=$?
set -e

(( missing_status != 0 )) || fail '显式指定的不存在路径不应通过 codex-verify'
assert_contains "$output" '路径不存在或不是普通文件'

printf 'PASS: 不存在的显式路径被拒绝\n'

check_script=$script_dir/check.sh
staged_repo=$test_root/staged-repo
mkdir -p "$staged_repo/skills"
git -C "$staged_repo" init -q
printf '#!/usr/bin/env bash\necho staged\n' > "$staged_repo/skills/demo"
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
