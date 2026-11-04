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
for tool in npm npx; do
    cat > "$node_dir/$tool" <<INNER
#!/usr/bin/env bash
printf '${tool}-${NODE_VERSION}.1.0\n'
INNER
    chmod 0755 "$node_dir/$tool"
done
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
        NODE_BIN_DIR="${NODE_BIN_DIR:-}" \
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
# 已满足分支同样套用稳定入口约定（--check 只读，不改文件）
satisfied_bin="$home_dir/.local/bin"
[ -L "$satisfied_bin/node" ] || fail "已满足分支未创建稳定入口: $satisfied_bin/node"
printf 'PASS: 已满足分支同样链接稳定入口\n'

# 幂等：重复运行不报错且软链仍指向 node 来源
run_install >/dev/null
[ -L "$satisfied_bin/node" ] || fail '重复运行后软链丢失'
if [ -L "$satisfied_bin/node" ]; then
    case "$(readlink "$satisfied_bin/node")" in
        "$fake_bin"/*) ;;
        *) fail "稳定入口应指向当前 node 来源: $(readlink "$satisfied_bin/node")" ;;
    esac
fi
printf 'PASS: 稳定入口链接幂等\n'

# 回归：node 来源本身就是稳定入口时，不得建立自指软链（曾把正确软链覆盖成自指）
self_case_dir="$test_root/selfbin"
mkdir -p "$self_case_dir"
cat > "$self_case_dir/node" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
    --version) printf 'v24.0.0\n' ;;
    -p) printf '24\n' ;;
    *) exit 1 ;;
esac
EOF
cp "$fake_bin/npm" "$self_case_dir/npm"
chmod 0755 "$self_case_dir/node" "$self_case_dir/npm"
env -u NODE_BIN_DIR HOME="$home_dir" PROFILE=/dev/null NVM_DIR="$nvm_dir" \
    NODE_VERSION= FAKE_NVM_LOG="$nvm_log" PATH="$self_case_dir:$PATH" \
    bash "$wrapper_dir/install.sh" >/dev/null 2>&1 || true
if [ -L "$self_case_dir/node" ]; then
    case "$(readlink "$self_case_dir/node")" in
        *selfbin/node) fail '不得建立自指软链' ;;
    esac
fi
[ -x "$self_case_dir/node" ] || fail '自指检查导致原文件不可用'
printf 'PASS: 源即目标时不建立自指软链\n'

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

# 稳定入口：node/npm/npx 必须软链到 $HOME/.local/bin（与 _codex、_claude-code 约定一致）
bin_dir="$home_dir/.local/bin"
[ -L "$bin_dir/node" ] || fail "未创建稳定入口软链: $bin_dir/node"
[ -L "$bin_dir/npm" ] || fail "未创建稳定入口软链: $bin_dir/npm"
[ -L "$bin_dir/npx" ] || fail "未创建稳定入口软链: $bin_dir/npx"
[ "$(readlink "$bin_dir/node")" = "$nvm_dir/versions/node/v22.1.0/bin/node" ] ||
    fail "node 软链指向错误: $(readlink "$bin_dir/node")"
case "$(readlink "$bin_dir/node")" in
    "$nvm_dir"/versions/node/v*/*/node) ;;
    *) fail "node 软链不应指向版本目录之外: $(readlink "$bin_dir/node")" ;;
esac
assert_contains "$install_output" '已链接:'
printf 'PASS: 稳定入口 node/npm/npx 软链到 $HOME/.local/bin\n'

# NODE_BIN_DIR 覆盖；用户自有非软链文件不得被覆盖
custom_bin="$test_root/custombin"
rm -f "$nvm_log"
NODE_BIN_DIR="$custom_bin" run_install 22 >/dev/null
[ -L "$custom_bin/node" ] || fail "NODE_BIN_DIR 未生效: $custom_bin/node"
printf 'PASS: NODE_BIN_DIR 可覆盖稳定入口目录\n'

user_owned="$test_root/userbin"
mkdir -p "$user_owned"
printf '#!/usr/bin/env bash\nprintf "user-owned\\n"\n' > "$user_owned/node"
chmod 0755 "$user_owned/node"
rm -f "$nvm_log"
override_output="$(NODE_BIN_DIR="$user_owned" run_install 22)"
[ ! -L "$user_owned/node" ] || fail '用户自有 node 不应被替换为软链'
assert_contains "$override_output" '跳过 node'
assert_contains "$(cat "$user_owned/node")" 'user-owned'
printf 'PASS: 用户自有可执行文件不被覆盖\n'

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
