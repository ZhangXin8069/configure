#!/usr/bin/env bash

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
checker=$script_dir/configure-check.sh
test_root=$(mktemp -d "${TMPDIR:-/tmp}/configure-check-test.XXXXXX")

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
        *) fail "输出缺少: $2" ;;
    esac
}

repo=$test_root/repo
plugin=$repo/plugins/demo
outside=$test_root/outside
mkdir -p "$repo/skills/demo" "$repo/tools" "$repo/hooks" \
    "$plugin/.codex-plugin" "$plugin/assets" "$outside"

cat > "$repo/skills/demo/SKILL.md" <<'EOF'
---
name: demo
description: demo skill
metadata:
  openclaw:
    emoji: 🔧
---
## 执行前置
说明
## 核心原则
说明
## 触发时机
说明
## 工作流程
说明
## 错误处理
| 场景 | 处理 |
|---|---|
| x | y |
## 注意事项
说明
EOF
printf '%s\n' '# demo' > "$repo/skills/demo/AGENTS.md"
printf '%s\n' 'outside' > "$outside/secret.txt"
ln -s "$outside" "$plugin/assets/escape"
cat > "$plugin/.codex-plugin/plugin.json" <<'EOF'
{
  "name": "demo",
  "version": "1.0.0",
  "assets": ["assets/escape"]
}
EOF

set +e
output=$(bash "$checker" --root "$repo" 2>&1)
check_status=$?
set -e

(( check_status != 0 )) || fail '插件 manifest 的越界符号链接不应通过检查'
assert_contains "$output" '越界路径'

printf 'PASS: 插件 manifest 的越界符号链接被拒绝\n'

fake_bin=$test_root/fake-bin
mkdir -p "$fake_bin"
cat > "$fake_bin/find" <<'EOF'
#!/usr/bin/env sh
exit 1
EOF
chmod 0755 "$fake_bin/find"

set +e
output=$(PATH="$fake_bin:$PATH" bash "$checker" --root "$repo" 2>&1)
find_status=$?
set -e

(( find_status != 0 )) || fail '文件枚举失败时检查器不应通过'
assert_contains "$output" '文件枚举失败'

printf 'PASS: 文件枚举失败被报告\n'
