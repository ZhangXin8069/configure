#!/usr/bin/env bash

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
report_script=$script_dir/coverage-report.sh
test_root=$(mktemp -d "${TMPDIR:-/tmp}/coverage-report-test.XXXXXX")

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

assert_not_contains() {
    case "$1" in
        *"$2"*) fail "输出不应包含: $2\n实际输出:\n$1" ;;
        *) ;;
    esac
}

assert_same_text() {
    if [[ "$1" != "$2" ]]; then
        fail "文本不一致\n--- before ---\n$1\n--- after ---\n$2"
    fi
}

repo_ok=$test_root/repo-ok
mkdir -p "$repo_ok/skills/demo" "$repo_ok/tools" "$repo_ok/hooks" \
    "$repo_ok/plugins/demo/.codex-plugin" "$repo_ok/plugins/demo/assets" \
    "$repo_ok/.opencode/skills/demo"
git -C "$repo_ok" init -q

cat > "$repo_ok/skills/AGENTS.md" <<'EOF'
| 技能 | 用途 |
|---|---|
| `demo` | 测试 |
EOF
cat > "$repo_ok/skills/demo/SKILL.md" <<'EOF'
---
name: demo
description: Use when testing coverage-report fixtures.
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
printf '%s\n' '# demo' > "$repo_ok/skills/demo/AGENTS.md"
cat > "$repo_ok/tools/good.sh" <<'EOF'
#!/usr/bin/env bash
printf 'ok\n'
EOF
chmod 0755 "$repo_ok/tools/good.sh"
cat > "$repo_ok/hooks/pre-commit" <<'EOF'
#!/usr/bin/env bash
printf 'hook\n'
EOF
chmod 0755 "$repo_ok/hooks/pre-commit"
printf '%s\n' 'payload' > "$repo_ok/plugins/demo/assets/payload.txt"
cat > "$repo_ok/plugins/demo/.codex-plugin/plugin.json" <<'EOF'
{
  "name": "demo",
  "version": "1.0.0",
  "assets": ["assets/payload.txt"]
}
EOF
cp "$repo_ok/skills/AGENTS.md" "$repo_ok/.opencode/skills/AGENTS.md"
cp "$repo_ok/skills/demo/SKILL.md" "$repo_ok/.opencode/skills/demo/SKILL.md"
cp "$repo_ok/skills/demo/AGENTS.md" "$repo_ok/.opencode/skills/demo/AGENTS.md"

baseline_status=$(git -C "$repo_ok" status --porcelain)
set +e
output=$(bash "$report_script" --root "$repo_ok" 2>&1)
status=$?
set -e
after_status=$(git -C "$repo_ok" status --porcelain)

(( status == 0 )) || fail "coverage-report.sh 不应失败\n输出：\n$output"
assert_same_text "$baseline_status" "$after_status"
assert_contains "$output" '四树覆盖摘要'
assert_contains "$output" 'skills: 目录=1'
assert_contains "$output" 'AGENTS.md=1/1'
assert_contains "$output" '登记=1/1'
assert_contains "$output" 'tools: 脚本=1'
assert_contains "$output" 'hooks: 脚本=1'
assert_contains "$output" 'plugins: manifest=1/1'
assert_contains "$output" '镜像一致性线索'
assert_contains "$output" 'missing=0'
assert_contains "$output" 'extra=0'
assert_contains "$output" 'diff=0'
assert_contains "$output" '未发现明显缺口'
printf 'PASS: coverage-report 对完整样本输出摘要且不改仓库\n'

repo_gap=$test_root/repo-gap
mkdir -p "$repo_gap/skills/demo" "$repo_gap/tools" "$repo_gap/hooks" \
    "$repo_gap/plugins/demo/.codex-plugin" "$repo_gap/plugins/demo/assets" \
    "$repo_gap/.opencode/skills/demo"
git -C "$repo_gap" init -q

cat > "$repo_gap/skills/AGENTS.md" <<'EOF'
| 技能 | 用途 |
|---|---|
| `demo` | 测试 |
EOF
cat > "$repo_gap/skills/demo/SKILL.md" <<'EOF'
---
name: demo
description: Use when testing coverage-report gaps.
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
printf '%s\n' '# demo' > "$repo_gap/skills/demo/AGENTS.md"
cat > "$repo_gap/tools/bad.sh" <<'EOF'
#!/usr/bin/env bash
printf 'bad\n'
EOF
chmod 0644 "$repo_gap/tools/bad.sh"
cat > "$repo_gap/hooks/pre-commit" <<'EOF'
#!/usr/bin/env bash
printf 'hook\n'
EOF
chmod 0755 "$repo_gap/hooks/pre-commit"
printf '%s\n' 'payload' > "$repo_gap/plugins/demo/assets/payload.txt"
cat > "$repo_gap/plugins/demo/.codex-plugin/plugin.json" <<'EOF'
{
  "name": "demo",
  "version": "1.0.0",
  "assets": ["assets/payload.txt"]
}
EOF
cp "$repo_gap/skills/AGENTS.md" "$repo_gap/.opencode/skills/AGENTS.md"
cp "$repo_gap/skills/demo/SKILL.md" "$repo_gap/.opencode/skills/demo/SKILL.md"
printf '%s\n' 'mirror-only' > "$repo_gap/.opencode/skills/demo/mirror.txt"
rm -f -- "$repo_gap/skills/demo/AGENTS.md"

set +e
gap_output=$(bash "$report_script" --root "$repo_gap" 2>&1)
gap_status=$?
set -e

(( gap_status == 0 )) || fail "coverage-report.sh 在缺口样本上不应失败\n输出：\n$gap_output"
assert_contains "$gap_output" 'skills/demo 缺少 AGENTS.md'
assert_contains "$gap_output" 'tools/bad.sh 不可执行'
assert_contains "$gap_output" 'skills 镜像多余文件：demo/mirror.txt'
assert_contains "$gap_output" 'missing=0'
assert_contains "$gap_output" 'extra=1'
assert_not_contains "$gap_output" '未发现明显缺口'
printf 'PASS: coverage-report 报出缺口与镜像漂移线索\n'
