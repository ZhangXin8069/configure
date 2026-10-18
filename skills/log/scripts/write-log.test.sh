#!/usr/bin/env bash
set -euo pipefail
LC_ALL=C

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
WRITE_LOG="$SCRIPT_DIR/write-log.sh"
TMP_ROOT=$(mktemp -d "$SCRIPT_DIR/.write-log-test.XXXXXX")
trap 'rm -rf "$TMP_ROOT"' EXIT

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

REPO="$TMP_ROOT/repo"
mkdir -p "$REPO"
git -C "$REPO" init -q
cd "$REPO"

stage_body() {
  cat <<'EOF'
## 关键日志
### S1
- 命令: bash -n write-log.sh
- 退出码: 0

## 验证与证据
- 结果: 语法检查通过

## Agent 全文报告
--- report begin ---
阶段完整报告
--- report end ---
EOF
}

stage_output=$(stage_body | "$WRITE_LOG" \
  --mode stage \
  --task '验证阶段日志' \
  --batch 'batch-a' \
  --summary '阶段写入通过' \
  --timestamp 202610191234)
grep -q '^log_file=.*/logs/v202610191234\.txt$' <<<"$stage_output" ||
  fail "stage log filename mismatch"
test -s logs/v202610191234.txt || fail "stage log was not written"
grep -q '^## Agent 全文报告$' logs/v202610191234.txt ||
  fail "stage report section missing"
grep -q '日志文件: logs/v202610191234.txt' logs/AGENT.md ||
  fail "stage index entry missing"

collision_output=$(stage_body | "$WRITE_LOG" \
  --mode stage \
  --task '验证冲突文件名' \
  --batch 'batch-a' \
  --timestamp 202610191234)
grep -q '^log_file=.*/logs/v202610191234-2\.txt$' <<<"$collision_output" ||
  fail "collision suffix was not applied"

general_body() {
  cat <<'EOF'
## 关键日志
- 操作: 记录一般执行状态
- 退出码: 0
EOF
}

compact_general_output=$(general_body | "$WRITE_LOG" \
  --mode general \
  --task '验证紧凑一般日志' \
  --batch 'batch-b' \
  --timestamp 20261019123501)
grep -q '^log_file=.*/logs/v20261019123501\.txt$' <<<"$compact_general_output" ||
  fail "compact general log filename mismatch"

hyphen_output=$(general_body | "$WRITE_LOG" \
  --mode general \
  --task '验证一般日志' \
  --batch 'batch-b' \
  --timestamp-style hyphen \
  --timestamp 2026-10-19-12-35-01)
grep -q '^log_file=.*/logs/v2026-10-19-12-35-01\.txt$' <<<"$hyphen_output" ||
  fail "hyphenated timestamp filename mismatch"

if cat <<'EOF' | "$WRITE_LOG" --mode final --task '缺用户输入' --timestamp 202610191300 >/dev/null 2>&1
## 关键日志
- 阶段: S1

## Agent 全文报告
--- report begin ---
完整报告
--- report end ---
EOF
then
  fail "final log without user input should fail"
fi

final_body() {
  cat <<'EOF'
## 用户输入指令
请完成任务并归档最终报告。

## 关键日志
### S1
- 测试通过

## Agent 全文报告
--- report begin ---
最终完整报告
--- report end ---
EOF
}

final_output=$(final_body | "$WRITE_LOG" \
  --mode final \
  --task '验证最终日志' \
  --batch 'batch-c' \
  --timestamp 2026101913)
grep -q '^log_file=.*/logs/v2026101913\.txt$' <<<"$final_output" ||
  fail "final log filename mismatch"
grep -q '批次状态: complete' logs/AGENT.md ||
  fail "final index status missing"

if cat <<'EOF' | "$WRITE_LOG" --mode stage --task '缺阶段报告' --timestamp 202610191259 >/dev/null 2>&1
## 关键日志
- 阶段: S1
EOF
then
  fail "stage log without report should fail"
fi

oversized_body="$TMP_ROOT/oversized-body.txt"
{
  printf '## 关键日志\n'
  dd if=/dev/zero bs=1048576 count=11 2>/dev/null | tr '\000' x
  printf '\n'
} >"$oversized_body"

if "$WRITE_LOG" --mode general --task '验证大小上限' \
  --timestamp 202610191301 <"$oversized_body" >/dev/null 2>&1; then
  fail "10 MiB hard limit did not reject the log"
fi

printf 'logs/\n' >.gitignore
if general_body | "$WRITE_LOG" --mode general --task '验证忽略路径' \
  --timestamp 202610191302 >/dev/null 2>&1; then
  fail "ignored log path should fail"
fi

mkdir -p "$TMP_ROOT/not-a-repo"
if (cd "$TMP_ROOT/not-a-repo" &&
  export GIT_CEILING_DIRECTORIES="$TMP_ROOT" &&
  general_body | "$WRITE_LOG" --mode general --task '验证非 Git 目录') >/dev/null 2>&1; then
  fail "non-Git directory should fail"
fi

[[ -z "$(find logs -maxdepth 1 -name '.log-draft.*' -print)" ]] ||
  fail "temporary draft file was not cleaned up"

"$WRITE_LOG" --help >/dev/null
printf 'write-log tests: PASS\n'
