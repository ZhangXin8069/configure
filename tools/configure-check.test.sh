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

agent_trigger_repo=$test_root/agent-trigger-repo
mkdir -p "$agent_trigger_repo/skills/demo" "$agent_trigger_repo/tools" "$agent_trigger_repo/hooks" "$agent_trigger_repo/plugins"
sed 's/description: Use when testing configure-check fixtures./description: 当 agent 主任务完成并需要归档时使用。/' \
    "$repo/skills/demo/SKILL.md" > "$agent_trigger_repo/skills/demo/SKILL.md"
cp "$repo/skills/demo/AGENTS.md" "$agent_trigger_repo/skills/demo/AGENTS.md"
cp "$strict_repo/skills/AGENTS.md" "$agent_trigger_repo/skills/AGENTS.md"

set +e
agent_trigger_output=$(bash "$checker" --root "$agent_trigger_repo" 2>&1)
agent_trigger_status=$?
set -e
(( agent_trigger_status == 0 )) || fail "合法的“当 agent”触发描述不应失败\n输出：\n$agent_trigger_output"
printf 'PASS: “当 agent”触发描述被接受\n'

missing_trigger_repo=$test_root/missing-trigger-repo
mkdir -p "$missing_trigger_repo/skills/demo" "$missing_trigger_repo/tools" "$missing_trigger_repo/hooks" "$missing_trigger_repo/plugins"
sed 's/description: Use when testing configure-check fixtures./description: 归档任务日志。/' \
    "$repo/skills/demo/SKILL.md" > "$missing_trigger_repo/skills/demo/SKILL.md"
cp "$repo/skills/demo/AGENTS.md" "$missing_trigger_repo/skills/demo/AGENTS.md"
cp "$strict_repo/skills/AGENTS.md" "$missing_trigger_repo/skills/AGENTS.md"

set +e
missing_trigger_output=$(bash "$checker" --root "$missing_trigger_repo" 2>&1)
missing_trigger_status=$?
set -e
(( missing_trigger_status != 0 )) || fail '缺少触发条件的 description 不应通过检查'
assert_contains "$missing_trigger_output" 'description 缺少明确触发条件'
printf 'PASS: 缺少触发条件的 description 被拒绝\n'

malformed_repo=$test_root/malformed-repo
mkdir -p "$malformed_repo/skills/demo" "$malformed_repo/tools" "$malformed_repo/hooks" "$malformed_repo/plugins"
cp "$repo/skills/demo/SKILL.md" "$malformed_repo/skills/demo/SKILL.md"
cp "$repo/skills/demo/AGENTS.md" "$malformed_repo/skills/demo/AGENTS.md"
printf '%s\n' \
    '| 技能 | 用途 |' \
    '|---|---|' \
    '| `demo` | 测试 | 额外列 |' > "$malformed_repo/skills/AGENTS.md"

set +e
malformed_output=$(bash "$checker" --root "$malformed_repo" 2>&1)
malformed_status=$?
set -e
(( malformed_status != 0 )) || fail '技能表列数漂移不应通过检查'
assert_contains "$malformed_output" '技能表列数不一致'
printf 'PASS: 技能表列数漂移被拒绝\n'

mutual_repo=$test_root/mutual-repo
mkdir -p "$mutual_repo/skills/demo" "$mutual_repo/tools" "$mutual_repo/hooks" "$mutual_repo/plugins"
cp "$repo/skills/demo/SKILL.md" "$mutual_repo/skills/demo/SKILL.md"
cp "$repo/skills/demo/AGENTS.md" "$mutual_repo/skills/demo/AGENTS.md"
printf '%s\n' \
    '## 技能' \
    '' \
    '| 技能 | 用途 |' \
    '|---|---|' \
    '| `demo` | 测试 |' \
    '' \
    '## 各技能优点互鉴（可供其他技能借鉴的亮点）' \
    '' \
    '| 技能 | 标志性优点（可借鉴处） | 适合借鉴到的场景 |' \
    '|---|---|---|' \
    '| `demo` | 优点 |' > "$mutual_repo/skills/AGENTS.md"

set +e
mutual_output=$(bash "$checker" --root "$mutual_repo" 2>&1)
mutual_status=$?
set -e
(( mutual_status != 0 )) || fail '互鉴表列数漂移不应通过检查'
assert_contains "$mutual_output" '互鉴表列数不一致'
printf 'PASS: 互鉴表列数漂移被拒绝\n'

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

snapshot_repo=$test_root/snapshot-repo
mkdir -p "$snapshot_repo/skills/demo" "$snapshot_repo/skills/form" \
    "$snapshot_repo/skills/form/references/source-snapshots/vendor" \
    "$snapshot_repo/tools" "$snapshot_repo/hooks" "$snapshot_repo/plugins"
printf '%s\n' '| 技能 | 用途 |' '|---|---|' '| `demo` | 测试 |' '| `form` | 测试快照 |' > "$snapshot_repo/skills/AGENTS.md"
cp "$repo/skills/demo/SKILL.md" "$snapshot_repo/skills/demo/SKILL.md"
cp "$repo/skills/demo/AGENTS.md" "$snapshot_repo/skills/demo/AGENTS.md"
sed 's/^name: demo$/name: form/' "$repo/skills/demo/SKILL.md" > "$snapshot_repo/skills/form/SKILL.md"
cp "$repo/skills/demo/AGENTS.md" "$snapshot_repo/skills/form/AGENTS.md"
printf '%s\n' '#!/usr/bin/env bash' 'printf ok' > "$snapshot_repo/skills/form/references/source-snapshots/vendor/executable.sh"
chmod 0755 "$snapshot_repo/skills/form/references/source-snapshots/vendor/executable.sh"
printf '%s\n' 'printf no-shebang' > "$snapshot_repo/skills/form/references/source-snapshots/vendor/upstream-owned.sh"
chmod 0644 "$snapshot_repo/skills/form/references/source-snapshots/vendor/upstream-owned.sh"
mkdir -p "$snapshot_repo/skills/form/scripts"
printf '%s\n' '#!/usr/bin/env bash' 'printf maintained' > "$snapshot_repo/skills/form/scripts/maintained.sh"
chmod 0755 "$snapshot_repo/skills/form/scripts/maintained.sh"

set +e
snapshot_output=$(bash "$checker" --root "$snapshot_repo" 2>&1)
snapshot_status=$?
set -e
(( snapshot_status == 0 )) || fail "vendored 快照脚本不应被当作仓库脚本检查\n输出：\n$snapshot_output"
assert_contains "$snapshot_output" 'skills 脚本检查完成：1 个'
printf 'PASS: vendored source-snapshots 被排除在仓库脚本检查之外\n'
