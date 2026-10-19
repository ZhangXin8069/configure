#!/usr/bin/env bash
set -euo pipefail
LC_ALL=C

usage() {
  cat <<'EOF'
用法: form-large-files-check.sh [--root DIR] [--max-bytes BYTES] [--quiet]

检查暂存区新增、修改、复制或重命名文件的索引 blob 大小，超过限制时阻止提交。
已删除文件以及不在索引中的路径不参与检查。

选项:
  --root DIR       Git 仓库根目录，默认使用当前仓库
  --max-bytes N    单个暂存文件的最大字节数，默认 10000000
  --quiet          隐藏成功摘要
  -h, --help       显示帮助

环境变量:
  FORM_MAX_COMMIT_FILE_BYTES  未传 --max-bytes 时覆盖默认阈值

退出码:
  0  没有暂存文件超过限制
  1  一个或多个暂存文件超过限制
  2  参数或仓库状态无效
EOF
}

die() {
  printf 'form-large-files-check: 错误: %s\n' "$*" >&2
  exit 2
}

ROOT=
MAX_BYTES=${FORM_MAX_COMMIT_FILE_BYTES:-10000000}
QUIET=0

while (($# > 0)); do
  case "$1" in
    --root)
      (($# >= 2)) || die "--root 需要目录"
      ROOT=$2
      shift 2
      ;;
    --max-bytes)
      (($# >= 2)) || die "--max-bytes 需要字节数"
      MAX_BYTES=$2
      shift 2
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

[[ "$MAX_BYTES" =~ ^[0-9]+$ ]] || die "--max-bytes 必须是非负整数"

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

CHECKED=0
VIOLATIONS=0

while IFS= read -r -d '' path; do
  CHECKED=$((CHECKED + 1))
  size=$(git -C "$ROOT" cat-file -s ":$path" 2>/dev/null) ||
    die "无法读取暂存 blob 大小: $path"
  if ((size > MAX_BYTES)); then
    VIOLATIONS=$((VIOLATIONS + 1))
    printf '错误\tLARGE_STAGED_FILE\t%s\t%s 字节，超过限制 %s 字节\n' \
      "$path" "$size" "$MAX_BYTES"
  fi
done < <(
  git -C "$ROOT" diff --cached --name-only --diff-filter=ACMRT -z
)

if ((VIOLATIONS > 0)); then
  printf 'form-large-files-check: 已阻止 %d 个超限暂存文件；限制=%s 字节\n' \
    "$VIOLATIONS" "$MAX_BYTES" >&2
  exit 1
fi

if ((QUIET == 0)); then
  printf 'form-large-files-check: 通过 已检查=%d 限制=%s 字节\n' \
    "$CHECKED" "$MAX_BYTES"
fi
