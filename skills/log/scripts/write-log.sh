#!/usr/bin/env bash
set -euo pipefail
LC_ALL=C

usage() {
  cat <<'EOF'
Usage: write-log.sh --task TEXT [options] < log-body

Write a main-task log under the current Git root's logs/ directory.

Options:
  --mode stage|general|final  Log mode (default: general)
  --task TEXT                 One-line task definition
  --batch TEXT                Batch identifier
  --summary TEXT              One-line index summary
  --timestamp-style STYLE     compact (default) or hyphen
  --timestamp VALUE           Test/reproduction timestamp override
  -h, --help                  Show this help

Input body requirements:
  all modes   ## 关键日志
  stage/final ## Agent 全文报告
  final       ## 用户输入指令

The script never stages, commits, or pushes Git changes.
EOF
}

die() {
  printf 'write-log: %s\n' "$*" >&2
  exit 2
}

MODE=general
TASK=
BATCH=
SUMMARY=
TIMESTAMP_STYLE=compact
TIMESTAMP_OVERRIDE=

while (($# > 0)); do
  case "$1" in
    --mode)
      (($# >= 2)) || die "--mode requires a value"
      MODE=$2
      shift 2
      ;;
    --task)
      (($# >= 2)) || die "--task requires a value"
      TASK=$2
      shift 2
      ;;
    --batch)
      (($# >= 2)) || die "--batch requires a value"
      BATCH=$2
      shift 2
      ;;
    --summary)
      (($# >= 2)) || die "--summary requires a value"
      SUMMARY=$2
      shift 2
      ;;
    --timestamp-style)
      (($# >= 2)) || die "--timestamp-style requires a value"
      TIMESTAMP_STYLE=$2
      shift 2
      ;;
    --timestamp)
      (($# >= 2)) || die "--timestamp requires a value"
      TIMESTAMP_OVERRIDE=$2
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ -n "$TASK" ]] || die "--task is required"
case "$MODE" in
  stage|general|final) ;;
  *) die "invalid mode: $MODE" ;;
esac
case "$TIMESTAMP_STYLE" in
  compact|hyphen) ;;
  *) die "invalid timestamp style: $TIMESTAMP_STYLE" ;;
esac
case "$TASK$BATCH$SUMMARY" in
  *$'\n'*) die "task, batch, and summary must be single-line values" ;;
esac

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) ||
  die "current directory is not inside a Git worktree"
REPO_ROOT=$(cd "$REPO_ROOT" && pwd -P)
LOG_DIR="$REPO_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG_DIR_REAL=$(cd "$LOG_DIR" && pwd -P)
case "$LOG_DIR_REAL/" in
  "$REPO_ROOT/"*) ;;
  *) die "logs directory resolves outside the Git root: $LOG_DIR_REAL" ;;
esac

INDEX_FILE="$LOG_DIR/AGENT.md"
[[ ! -L "$INDEX_FILE" ]] || die "logs/AGENT.md must not be a symlink"
[[ ! -e "$INDEX_FILE" || -f "$INDEX_FILE" ]] ||
  die "logs/AGENT.md must be a regular file"

GENERATED_AT=$(date '+%Y-%m-%d %H:%M:%S %z')
BATCH=${BATCH:-$GENERATED_AT}
SUMMARY=${SUMMARY:-$TASK}
case "$MODE" in
  stage)
    TRIGGER='阶段成果'
    BATCH_STATUS='in-progress'
    ;;
  general)
    TRIGGER='一般记录'
    BATCH_STATUS='in-progress'
    ;;
  final)
    TRIGGER='任务完成'
    BATCH_STATUS='complete'
    ;;
esac

TMP_FILE=
cleanup() {
  if [[ -n "$TMP_FILE" && -f "$TMP_FILE" ]]; then
    rm -f "$TMP_FILE"
  fi
}
trap cleanup EXIT

TMP_FILE=$(mktemp "$LOG_DIR/.log-draft.XXXXXX")
{
  printf '[日志元数据]\n'
  printf '日志类型: %s\n' "$MODE"
  printf '生成时间: %s\n' "$GENERATED_AT"
  printf '批次: %s\n' "$BATCH"
  printf '主任务: %s\n' "$TASK"
  printf '触发原因: %s\n' "$TRIGGER"
  printf '摘要: %s\n' "$SUMMARY"
  printf 'Git 根目录: %s\n\n' "$REPO_ROOT"
  cat
} >"$TMP_FILE"

require_section() {
  local heading=$1
  grep -qxF -- "$heading" "$TMP_FILE" ||
    die "missing required section: $heading"
}

section_has_content() {
  local heading=$1
  awk -v heading="$heading" '
    $0 == heading { active=1; next }
    active && /^## / { exit }
    active && NF { found=1; exit }
    END { exit(found ? 0 : 1) }
  ' "$TMP_FILE"
}

require_section '## 关键日志'
section_has_content '## 关键日志' ||
  die "## 关键日志 must contain at least one non-empty line"

case "$MODE" in
  stage|final)
    require_section '## Agent 全文报告'
    section_has_content '## Agent 全文报告' ||
      die "## Agent 全文报告 must contain at least one non-empty line"
    ;;
esac

if [[ "$MODE" == final ]]; then
  require_section '## 用户输入指令'
  section_has_content '## 用户输入指令' ||
    die "## 用户输入指令 must contain at least one non-empty line"
fi

if grep -qE '^(<<<<<<< .+|>>>>>>> .+)$' "$TMP_FILE"; then
  die "conflict markers found in the log body"
fi

SIZE_BYTES=$(wc -c <"$TMP_FILE" | tr -d ' ')
TARGET_BYTES=$((512 * 1024))
HARD_LIMIT_BYTES=$((10 * 1024 * 1024))
((SIZE_BYTES < HARD_LIMIT_BYTES)) ||
  die "log reached the 10 MiB hard limit"
if ((SIZE_BYTES > TARGET_BYTES)); then
  printf 'write-log: warning: log exceeds the 512 KiB target\n' >&2
fi

case "$TIMESTAMP_STYLE:$MODE" in
  compact:stage) DATE_FORMAT='%Y%m%d%H%M' ;;
  compact:general) DATE_FORMAT='%Y%m%d%H%M%S' ;;
  compact:final) DATE_FORMAT='%Y%m%d%H' ;;
  hyphen:stage) DATE_FORMAT='%Y-%m-%d-%H-%M' ;;
  hyphen:general) DATE_FORMAT='%Y-%m-%d-%H-%M-%S' ;;
  hyphen:final) DATE_FORMAT='%Y-%m-%d-%H' ;;
esac

if [[ -n "$TIMESTAMP_OVERRIDE" ]]; then
  case "$TIMESTAMP_OVERRIDE" in
    *[!0-9-]*) die "timestamp override may contain only digits and hyphens" ;;
  esac
  DATE_STAMP=$TIMESTAMP_OVERRIDE
else
  DATE_STAMP=$(date +"$DATE_FORMAT")
fi

FILE_STEM="v$DATE_STAMP"
SUFFIX=
PART=2
while :; do
  if [[ -n "$SUFFIX" ]]; then
    LOG_FILE="$LOG_DIR/${FILE_STEM}-${SUFFIX}.txt"
  else
    LOG_FILE="$LOG_DIR/${FILE_STEM}.txt"
  fi
  LOG_REL="logs/${LOG_FILE##*/}"

  if git -C "$REPO_ROOT" check-ignore -q -- "$LOG_REL" ||
     git -C "$REPO_ROOT" check-ignore -q -- 'logs/AGENT.md'; then
    die "log path is ignored by Git: $LOG_REL"
  fi

  if ln "$TMP_FILE" "$LOG_FILE" 2>/dev/null; then
    break
  fi
  if [[ -e "$LOG_FILE" || -L "$LOG_FILE" ]]; then
    SUFFIX=$PART
    PART=$((PART + 1))
    continue
  fi
  die "cannot create log file: $LOG_FILE"
done

rm -f "$TMP_FILE"
TMP_FILE=
trap - EXIT
chmod 0644 "$LOG_FILE"

if [[ ! -e "$INDEX_FILE" ]]; then
  printf '# Agent 日志索引\n\n' >"$INDEX_FILE"
fi
{
  printf '## %s - %s - %s\n' "$BATCH" "$MODE" "$GENERATED_AT"
  printf -- '- 主任务: %s\n' "$TASK"
  printf -- '- 日志文件: %s\n' "$LOG_REL"
  printf -- '- 文件大小: %s bytes\n' "$SIZE_BYTES"
  printf -- '- 触发原因: %s\n' "$TRIGGER"
  printf -- '- 关键内容: %s\n' "$SUMMARY"
  printf -- '- 验证: path, size, required sections, conflict markers\n'
  printf -- '- 批次状态: %s\n\n' "$BATCH_STATUS"
} >>"$INDEX_FILE"

printf 'status=written\n'
printf 'mode=%s\n' "$MODE"
printf 'log_file=%s\n' "$LOG_FILE"
printf 'log_relative=%s\n' "$LOG_REL"
printf 'size_bytes=%s\n' "$SIZE_BYTES"
printf 'target_bytes=%s\n' "$TARGET_BYTES"
printf 'hard_limit_bytes=%s\n' "$HARD_LIMIT_BYTES"
printf 'index_file=%s\n' "$INDEX_FILE"
