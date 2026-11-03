#!/usr/bin/env bash

set -Eeuo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
test_root="$(mktemp -d "${TMPDIR:-/tmp}/commandcode-config-test.XXXXXX")"

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
mkdir -p "$fake_bin" "$home_dir"

cat > "$fake_bin/command-code" <<'EOF'
#!/usr/bin/env bash
printf '1.88.2\n'
EOF
chmod 0755 "$fake_bin/command-code"

run_config() {
    HOME="$home_dir" PATH="$fake_bin:$PATH" bash "$script_dir/config.sh" "$@"
}

dry_run_output="$(run_config --model opencode-go/deepseek-v4.1-flash --theme dark)"
assert_contains "$dry_run_output" '[dry-run]'
[ ! -e "$home_dir/.commandcode/config.json" ] || fail 'dry-run 不应创建 config.json'

run_config --apply \
    --provider command-code \
    --model opencode-go/deepseek-v4.1-flash \
    --theme auto \
    --compact-mode fast \
    --effort high \
    --reasoning-effort opencode-go/deepseek-v4.1-flash=max \
    --permission-mode dont-ask \
    --allow 'Shell(git status:*)' \
    --allow 'Shell(git status:*)' \
    --ask 'Read(.env*)' \
    --deny 'Read(secrets/**)' \
    --disable-bypass on \
    --extra-dir '~/shared-libs' \
    --skill '~/shared-skills' \
    --taste off \
    --artifacts off \
    --collapse-pasted-text off \
    --local-only on >/dev/null

python3 - "$home_dir/.commandcode/config.json" "$home_dir/.commandcode/settings.json" <<'PY' || fail '生成配置不符合预期'
import json
import os
import stat
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    config = json.load(handle)
assert config["provider"] == "command-code"
assert config["model"] == "opencode-go/deepseek-v4.1-flash"
assert config["theme"] == "auto"
assert config["compactMode"] == "fast"
assert config["tasteLearning"] is False
assert config["artifactsEnabled"] is False
assert config["collapsePastedText"] is False
assert config["localOnly"] is True
assert config["reasoningEffort"] == {"opencode-go/deepseek-v4.1-flash": "max"}

with open(sys.argv[2], encoding="utf-8") as handle:
    settings = json.load(handle)
assert settings["effort"] == "high"
assert settings["skills"] == ["~/shared-skills"]
assert settings["permissions"] == {
    "allow": ["Shell(git status:*)"],
    "ask": ["Read(.env*)"],
    "deny": ["Read(secrets/**)"],
    "additionalDirectories": ["~/shared-libs"],
    "defaultMode": "dont-ask",
    "disableBypass": True,
}
assert stat.S_IMODE(os.stat(sys.argv[1]).st_mode) == 0o600
assert stat.S_IMODE(os.stat(sys.argv[2]).st_mode) == 0o600
PY

python3 - "$home_dir/.commandcode/config.json" "$home_dir/.commandcode/settings.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    config = json.load(handle)
config["unknownPreference"] = {"preserved": True}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(config, handle)

with open(sys.argv[2], encoding="utf-8") as handle:
    settings = json.load(handle)
settings["unknownSetting"] = ["preserved"]
with open(sys.argv[2], "w", encoding="utf-8") as handle:
    json.dump(settings, handle)
PY

run_config --apply \
    --theme light \
    --allow 'Shell(git status:*)' \
    --disable-bypass off >/dev/null

python3 - "$home_dir/.commandcode/config.json" "$home_dir/.commandcode/settings.json" <<'PY' || fail '幂等合并未保留未知字段或唯一规则'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    config = json.load(handle)
assert config["theme"] == "light"
assert config["unknownPreference"] == {"preserved": True}

with open(sys.argv[2], encoding="utf-8") as handle:
    settings = json.load(handle)
assert settings["unknownSetting"] == ["preserved"]
assert settings["permissions"]["allow"] == ["Shell(git status:*)"]
assert "disableBypass" not in settings["permissions"]
PY

config_checksum="$(cksum "$home_dir/.commandcode/config.json")"
settings_checksum="$(cksum "$home_dir/.commandcode/settings.json")"
backup_count="$(find "$home_dir/.commandcode" -maxdepth 1 -type f -name '*.bak.*' | wc -l | tr -d ' ')"

run_config --apply \
    --theme light \
    --allow 'Shell(git status:*)' \
    --disable-bypass off >/dev/null

[ "$(cksum "$home_dir/.commandcode/config.json")" = "$config_checksum" ] || fail '二次执行不应改变 config.json'
[ "$(cksum "$home_dir/.commandcode/settings.json")" = "$settings_checksum" ] || fail '二次执行不应改变 settings.json'
[ "$(find "$home_dir/.commandcode" -maxdepth 1 -type f -name '*.bak.*' | wc -l | tr -d ' ')" = "$backup_count" ] || fail '无变更时不应创建备份'

check_output="$(run_config --check)"
assert_contains "$check_output" 'command-code: 1.88.2'
assert_contains "$check_output" '默认模型: opencode-go/deepseek-v4.1-flash'
assert_contains "$check_output" '默认权限模式: dont-ask'

if run_config --theme blue >/dev/null 2>&1; then
    fail '非法主题应失败'
fi
if run_config --permission-mode unsafe >/dev/null 2>&1; then
    fail '非法权限模式应失败'
fi
if run_config --reasoning-effort model=extreme >/dev/null 2>&1; then
    fail '非法推理强度应失败'
fi

help_output="$(run_config --help)"
assert_contains "$help_output" '--permission-mode MODE'

printf 'PASS: _commandcode config.sh 个人偏好、权限规则、幂等合并与隔离校验\n'
