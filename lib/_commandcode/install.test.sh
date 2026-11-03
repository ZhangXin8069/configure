#!/usr/bin/env bash

set -Eeuo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
test_root="$(mktemp -d "${TMPDIR:-/tmp}/commandcode-install-test.XXXXXX")"

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
install_prefix="$home_dir/.local"
install_dir="$install_prefix/bin"
npm_log="$test_root/npm.log"
mkdir -p "$fake_bin" "$home_dir"

cat > "$fake_bin/node" <<'EOF'
#!/usr/bin/env bash
major="${FAKE_NODE_MAJOR:-24}"
case "${1:-}" in
    --version) printf 'v%s.0.0\n' "$major" ;;
    -p) printf '%s\n' "$major" ;;
    *) printf 'unexpected node arguments: %s\n' "$*" >&2; exit 1 ;;
esac
EOF

cat > "$fake_bin/npm" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
    install)
        printf '%s\n' "$*" >> "$FAKE_NPM_LOG"
        prefix=""
        args=("$@")
        for ((index = 0; index < ${#args[@]}; index++)); do
            if [ "${args[index]}" = "--prefix" ]; then
                prefix="${args[index + 1]:-}"
                break
            fi
        done
        [ "$prefix" = "$FAKE_INSTALL_PREFIX" ] || {
            printf 'unexpected npm prefix: %s\n' "$prefix" >&2
            exit 1
        }
        mkdir -p "$FAKE_INSTALL_DIR"
        cat > "$FAKE_INSTALL_DIR/command-code" <<'INNER'
#!/usr/bin/env bash
printf '1.88.2\n'
INNER
        chmod 0755 "$FAKE_INSTALL_DIR/command-code"
        ;;
    *)
        printf 'unexpected npm arguments: %s\n' "$*" >&2
        exit 1
        ;;
esac
EOF
chmod 0755 "$fake_bin/node" "$fake_bin/npm"

run_install() {
    HOME="$home_dir" \
        SHELL=/bin/zsh \
        PATH="$fake_bin:$PATH" \
        FAKE_INSTALL_PREFIX="$install_prefix" \
        FAKE_INSTALL_DIR="$install_dir" \
        FAKE_NPM_LOG="$npm_log" \
        bash "$script_dir/install.sh" "$@"
}

install_output="$(run_install)"
assert_contains "$(cat "$npm_log")" "--prefix $install_prefix"
assert_contains "$(cat "$npm_log")" '--no-fund --no-audit command-code@1.88.2'
assert_contains "$install_output" "PATH 已写入: $home_dir/.zshrc"
assert_contains "$(cat "$home_dir/.zshrc")" "export PATH=\"$install_dir:\$PATH\""

run_install --new >/dev/null
assert_contains "$(cat "$npm_log")" 'command-code@latest'

run_install v1.88.2 >/dev/null
assert_contains "$(tail -n 1 "$npm_log")" 'command-code@1.88.2'

if run_install 1.88.2 extra >/dev/null 2>&1; then
    fail '多余位置参数应失败'
fi
if run_install --unknown >/dev/null 2>&1; then
    fail '未知选项应失败'
fi
if FAKE_NODE_MAJOR=20 run_install >/dev/null 2>&1; then
    fail 'Node.js 20 应失败'
fi

help_output="$(run_install --help)"
assert_contains "$help_output" 'Node.js >= 22'
assert_contains "$help_output" 'COMMAND_CODE_INSTALL_DIR'

[ "$(grep -Fc "export PATH=\"$install_dir:\$PATH\"" "$home_dir/.zshrc")" = 1 ] || fail 'PATH 写入应幂等'

printf 'PASS: _commandcode install.sh 版本选择、统一安装路径与 PATH 幂等流程\n'
