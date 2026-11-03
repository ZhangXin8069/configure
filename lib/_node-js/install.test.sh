#!/usr/bin/env bash

set -Eeuo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
test_root="$(mktemp -d "${TMPDIR:-/tmp}/node-js-install-test.XXXXXX")"

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
        *) fail "输出缺少: $2"$'\n'"实际输出: $1" ;;
    esac
}

fake_bin="$test_root/bin"
home_dir="$test_root/home"
nvm_dir="$test_root/nvm"
wrapper_dir="$test_root/wrapper"
nvm_log="$test_root/nvm.log"
mkdir -p "$fake_bin" "$home_dir" "$nvm_dir" "$wrapper_dir"

cp "$script_dir/install.sh" "$wrapper_dir/install.sh"

cat > "$wrapper_dir/nvm-install.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s' "${NODE_VERSION:?}" > "${FAKE_NVM_LOG:?}"
node_dir="${NVM_DIR:?}/versions/node/v${NODE_VERSION}.1.0/bin"
mkdir -p "$node_dir"
cat > "$node_dir/node" <<INNER
#!/usr/bin/env bash
printf 'v${NODE_VERSION}.1.0\n'
INNER
chmod 0755 "$node_dir/node"
EOF
chmod 0755 "$wrapper_dir/nvm-install.sh"

cat > "$fake_bin/npm" <<'EOF'
#!/usr/bin/env bash
printf '10.0.0\n'
EOF
chmod 0755 "$fake_bin/npm"

make_node() {
    local major="$1"
    cat > "$fake_bin/node" <<EOF
#!/usr/bin/env bash
case "\${1:-}" in
    --version) printf 'v$major.0.0\n' ;;
    -p) printf '$major\n' ;;
    *) exit 1 ;;
esac
EOF
    chmod 0755 "$fake_bin/node"
}

run_install() {
    HOME="$home_dir" \
        NODE_VERSION= \
        PROFILE=/dev/null \
        NVM_DIR="$nvm_dir" \
        FAKE_NVM_LOG="$nvm_log" \
        PATH="$fake_bin:$PATH" \
        bash "$wrapper_dir/install.sh" "$@"
}

make_node 24

check_output="$(run_install --check)"
assert_contains "$check_output" '已满足要求'

noop_output="$(run_install)"
assert_contains "$noop_output" '无需安装'
[ ! -e "$nvm_log" ] || fail '已满足要求时不应调用 nvm 安装器'

make_node 20

if old_check_output="$(run_install --check 2>&1)"; then
    fail 'Node.js 20 的 --check 应失败'
fi
assert_contains "$old_check_output" '不满足 >= 22'

rm -f "$nvm_log"
install_output="$(run_install 22)"
assert_contains "$(cat "$nvm_log")" '22'
assert_contains "$install_output" 'Node.js 安装完成: v22.1.0'
assert_contains "$install_output" 'nvm use 22'
assert_contains "$install_output" '未修改 shell 启动文件'

rm -f "$nvm_log"
run_install v24 >/dev/null
assert_contains "$(cat "$nvm_log")" '24'

if run_install abc >/dev/null 2>&1; then
    fail '非法版本应失败'
fi
if run_install 22 24 >/dev/null 2>&1; then
    fail '多余位置参数应失败'
fi

help_output="$(run_install --help)"
assert_contains "$help_output" '--check'
assert_contains "$help_output" 'nvm-install.sh'

printf 'PASS: _node-js install.sh 复用、nvm 委派、版本校验与隔离流程\n'
