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
description: Use when testing configure-check fixtures.
metadata:
  openclaw:
    emoji: 🔧
---
## 执行前置
说明
## 核心原则
说明
## Git 检查
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

strict_repo=$test_root/strict-repo
mkdir -p "$strict_repo/skills/demo" "$strict_repo/tools" "$strict_repo/hooks" "$strict_repo/plugins"
cp "$repo/skills/demo/SKILL.md" "$strict_repo/skills/demo/SKILL.md"
cp "$repo/skills/demo/AGENTS.md" "$strict_repo/skills/demo/AGENTS.md"
printf '%s\n' '| 技能 | 用途 |' '|---|---|' '| `demo` | 测试 |' > "$strict_repo/skills/AGENTS.md"

set +e
strict_output=$(bash "$checker" --root "$strict_repo" --strict 2>&1)
strict_status=$?
set -e
(( strict_status != 0 )) || fail '--strict 应将无插件 manifest 警告提升为失败'
assert_contains "$strict_output" '严格模式'
printf 'PASS: --strict 将警告提升为失败\n'

mirror_repo=$test_root/mirror-repo
mkdir -p "$mirror_repo/skills/demo" "$mirror_repo/.opencode/skills/demo" \
    "$mirror_repo/tools" "$mirror_repo/hooks" "$mirror_repo/plugins"
cp "$strict_repo/skills/AGENTS.md" "$mirror_repo/skills/AGENTS.md"
cp "$strict_repo/skills/AGENTS.md" "$mirror_repo/.opencode/skills/AGENTS.md"
cp "$repo/skills/demo/SKILL.md" "$mirror_repo/skills/demo/SKILL.md"
cp "$repo/skills/demo/AGENTS.md" "$mirror_repo/skills/demo/AGENTS.md"
cp "$repo/skills/demo/SKILL.md" "$mirror_repo/.opencode/skills/demo/SKILL.md"
cp "$repo/skills/demo/AGENTS.md" "$mirror_repo/.opencode/skills/demo/AGENTS.md"

set +e
mirror_output=$(bash "$checker" --root "$mirror_repo" 2>&1)
mirror_status=$?
set -e
(( mirror_status == 0 )) || fail "一致的 skills 镜像意外失败\n输出：\n$mirror_output"
assert_contains "$mirror_output" 'skills 与 .opencode/skills 镜像核对完成'
printf 'PASS: 一致的 skills 镜像通过核对\n'

printf '%s\n' '镜像漂移' >> "$mirror_repo/.opencode/skills/demo/SKILL.md"
set +e
mirror_output=$(bash "$checker" --root "$mirror_repo" 2>&1)
drift_status=$?
set -e
(( drift_status != 0 )) || fail 'skills 镜像漂移不应通过检查'
assert_contains "$mirror_output" '镜像内容不一致'
printf 'PASS: skills 镜像漂移被拒绝\n'
