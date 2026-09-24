#!/usr/bin/env bash

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
test_root=$(mktemp -d "${TMPDIR:-/tmp}/opencode-config-test.XXXXXX")
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
        *) fail "输出缺少：$2"$'\n'"实际输出：$1" ;;
    esac
}

make_opencode() {
    local path="$1" version="$2"
    cat > "$path" <<EOF
#!/usr/bin/env bash
printf '$version\n'
EOF
    chmod 0755 "$path"
}

run_config() {
    PATH="$fake_bin:$PATH" XDG_CONFIG_HOME="$config_home" bash "$script_dir/config.sh" "$@"
}

fake_bin="$test_root/bin"
config_home="$test_root/config"
mkdir -p "$fake_bin" "$config_home"

make_opencode "$fake_bin/opencode" 'opencode v2.0.16'
run_config --apply --model opencode-go/deepseek-v4.1-flash \
    --permission bash=ask --permission edit=allow \
    --plugin '@acme/opencode-plugin' --theme tokyonight >/dev/null

python3 - "$config_home/opencode/opencode.json" "$config_home/opencode/cli.json" <<'PY' || fail 'OpenCode V2 配置不符合预期'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    config = json.load(handle)
assert config["model"] == "opencode-go/deepseek-v4.1-flash"
assert config["plugins"] == ["@acme/opencode-plugin"]
assert config["permissions"] == [
    {"action": "shell", "resource": "*", "effect": "ask"},
    {"action": "edit", "resource": "*", "effect": "allow"},
]
with open(sys.argv[2], encoding="utf-8") as handle:
    cli = json.load(handle)
assert cli["theme"]["name"] == "tokyonight"
assert cli["$schema"] == "https://opencode.ai/v2/cli.json"
PY

v1_home="$test_root/config-v1"
mkdir -p "$v1_home"
make_opencode "$fake_bin/opencode" '1.18.32'
config_home="$v1_home" run_config --apply --theme dracula \
    --permission bash=ask --plugin old-plugin >/dev/null

python3 - "$v1_home/opencode/opencode.json" "$v1_home/opencode/tui.json" <<'PY' || fail 'OpenCode V1 兼容配置不符合预期'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    config = json.load(handle)
assert config["plugin"] == ["old-plugin"]
assert config["permission"] == {"bash": "ask"}
with open(sys.argv[2], encoding="utf-8") as handle:
    tui = json.load(handle)
assert tui["theme"] == "dracula"
PY

make_opencode "$fake_bin/opencode" 'opencode v2.0.16'
config_home="$test_root/config"
check_output="$(run_config --check)"
assert_contains "$check_output" '配置模式: OpenCode V2'

printf 'PASS: _opencode config.sh V2 原生配置与 V1 兼容分支\n'
