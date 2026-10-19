#!/usr/bin/env bash
set -euo pipefail
LC_ALL=C

START_MARKER='<!-- form-skill:start -->'
END_MARKER='<!-- form-skill:end -->'

usage() {
  cat <<'EOF'
用法: form-agents-sync.sh [--root DIR] [--target FILE] [--content FILE]
                          [--check] [--quiet]

在仓库根规则文件 AGENTS.md 中插入或更新 form 标记块；文件不存在时创建。
内容来自 --content 或标准输入。

选项:
  --root DIR      Git 仓库根目录，默认使用当前仓库
  --target FILE   根规则文件名，仅支持 AGENTS.md
  --content FILE  待托管的 Markdown 内容；省略时读取标准输入
  --check         只检查不写入；当前已一致返回 0，需要更新返回 1
  --quiet         隐藏成功状态
  -h, --help      显示帮助

标记:
  <!-- form-skill:start -->
  <!-- form-skill:end -->
EOF
}

die() {
  printf 'form-agents-sync: 错误: %s\n' "$*" >&2
  exit 2
}

ROOT=
TARGET=
CONTENT_FILE=
CHECK=0
QUIET=0

while (($# > 0)); do
  case "$1" in
    --root)
      (($# >= 2)) || die "--root 需要目录"
      ROOT=$2
      shift 2
      ;;
    --target)
      (($# >= 2)) || die "--target 需要文件名"
      TARGET=$2
      shift 2
      ;;
    --content)
      (($# >= 2)) || die "--content 需要文件"
      CONTENT_FILE=$2
      shift 2
      ;;
    --check)
      CHECK=1
      shift
      ;;
    --quiet)
      QUIET=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "未知参数: $1"
      ;;
  esac
done

if [[ -z "$ROOT" ]]; then
  ROOT=$(git rev-parse --show-toplevel 2>/dev/null) ||
    die "当前目录不在 Git 仓库内"
fi
[[ -d "$ROOT" ]] || die "根目录不存在: $ROOT"
ROOT=$(cd "$ROOT" && pwd -P)
git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 ||
  die "不是 Git 工作树: $ROOT"
GIT_ROOT=$(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null) ||
  die "无法解析 Git 根目录: $ROOT"
GIT_ROOT=$(cd "$GIT_ROOT" && pwd -P)
[[ "$GIT_ROOT" == "$ROOT" ]] ||
  die "--root 必须是 Git 根目录: $GIT_ROOT"

if [[ -z "$TARGET" ]]; then
  TARGET=AGENTS.md
fi

case "$TARGET" in
  AGENTS.md) ;;
  *) die "--target 只能是 AGENTS.md" ;;
esac

TARGET_PATH="$ROOT/$TARGET"
[[ -L "$TARGET_PATH" ]] && die "拒绝替换符号链接: $TARGET_PATH"
[[ -e "$TARGET_PATH" && ! -f "$TARGET_PATH" ]] &&
  die "目标不是普通文件: $TARGET_PATH"

if [[ -n "$CONTENT_FILE" ]]; then
  [[ -f "$CONTENT_FILE" ]] || die "内容文件不存在: $CONTENT_FILE"
  [[ ! "$CONTENT_FILE" -ef "$TARGET_PATH" ]] ||
    die "内容文件与目标文件不能相同"
fi

TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/form-agents-sync.XXXXXX")
CONTENT_TMP="$TMP_DIR/content.md"
BLOCK_TMP="$TMP_DIR/block.md"
OUTPUT_TMP="$TMP_DIR/output.md"
trap 'rm -rf "$TMP_DIR"' EXIT

if [[ -n "$CONTENT_FILE" ]]; then
  cat "$CONTENT_FILE" >"$CONTENT_TMP"
else
  if [[ -t 0 ]]; then
    die "请提供 --content 文件或通过标准输入传入托管内容"
  fi
  cat >"$CONTENT_TMP"
fi

grep -q '[^[:space:]]' "$CONTENT_TMP" ||
  die "托管内容不能为空"
if grep -Fq "$START_MARKER" "$CONTENT_TMP" ||
   grep -Fq "$END_MARKER" "$CONTENT_TMP"; then
  die "托管内容不能包含 form-skill 标记"
fi

{
  printf '%s\n' "$START_MARKER"
  cat "$CONTENT_TMP"
  if [[ -n "$(tail -c 1 "$CONTENT_TMP")" ]]; then
    printf '\n'
  fi
  printf '%s\n' "$END_MARKER"
} >"$BLOCK_TMP"

if [[ ! -e "$TARGET_PATH" ]]; then
  {
    printf '# %s - 仓库说明\n\n' "$TARGET"
    cat "$BLOCK_TMP"
  } >"$OUTPUT_TMP"
else
  START_COUNT=$(grep -Fxc "$START_MARKER" "$TARGET_PATH" || true)
  END_COUNT=$(grep -Fxc "$END_MARKER" "$TARGET_PATH" || true)
  if [[ "$START_COUNT" -eq 0 && "$END_COUNT" -eq 0 ]]; then
    awk -v start="$START_MARKER" -v end="$END_MARKER" \
      -v block="$BLOCK_TMP" '
      BEGIN {
        while ((getline line < block) > 0) {
          managed = managed line "\n"
        }
        close(block)
      }
      { print }
      END {
        if (NR > 0) {
          print ""
        }
        printf "%s", managed
      }
    ' "$TARGET_PATH" >"$OUTPUT_TMP"
  elif [[ "$START_COUNT" -eq 1 && "$END_COUNT" -eq 1 ]]; then
    START_LINE=$(grep -Fn "$START_MARKER" "$TARGET_PATH" | cut -d: -f1)
    END_LINE=$(grep -Fn "$END_MARKER" "$TARGET_PATH" | cut -d: -f1)
    if ((START_LINE >= END_LINE)); then
      die "form-skill 标记顺序错误: $TARGET_PATH"
    fi
    awk -v start="$START_MARKER" -v end="$END_MARKER" \
      -v block="$BLOCK_TMP" '
      BEGIN {
        while ((getline line < block) > 0) {
          managed = managed line "\n"
        }
        close(block)
      }
      $0 == start {
        printf "%s", managed
        replacing = 1
        next
      }
      replacing && $0 == end {
        replacing = 0
        next
      }
      !replacing {
        print
      }
    ' "$TARGET_PATH" >"$OUTPUT_TMP"
  else
    die "目标包含缺失或重复的 form-skill 标记: $TARGET_PATH"
  fi
fi

if [[ -e "$TARGET_PATH" ]] && cmp -s "$OUTPUT_TMP" "$TARGET_PATH"; then
  [[ "$QUIET" -eq 1 ]] ||
    printf '状态: 已是最新\n文件: %s\n' "$TARGET_PATH"
  exit 0
fi

if [[ "$CHECK" -eq 1 ]]; then
  [[ "$QUIET" -eq 1 ]] ||
    printf '状态: 需要更新\n文件: %s\n' "$TARGET_PATH"
  exit 1
fi

MODE=0644
if [[ -e "$TARGET_PATH" ]]; then
  if MODE=$(stat -c '%a' "$TARGET_PATH" 2>/dev/null); then
    :
  elif MODE=$(stat -f '%Lp' "$TARGET_PATH" 2>/dev/null); then
    :
  else
    MODE=0644
  fi
fi
chmod "$MODE" "$OUTPUT_TMP"
mv -f "$OUTPUT_TMP" "$TARGET_PATH"

[[ "$QUIET" -eq 1 ]] ||
  printf '状态: 已更新\n文件: %s\n' "$TARGET_PATH"
