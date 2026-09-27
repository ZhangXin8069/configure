#!/usr/bin/env bash
set -euo pipefail
LC_ALL=C

usage() {
  cat <<'EOF'
Usage: form-audit.sh [--root DIR] [--strict] [--exclude REGEX] [--quiet]

Read-only baseline audit for form naming and repository layout rules.
Tracked paths are checked; semantic function/variable names still require review.

Options:
  --root DIR       Git repository root (default: current repository)
  --strict         Exit 1 when warnings or errors are found
  --exclude REGEX  Skip paths matching an extended regular expression
  --quiet          Suppress the stderr summary
  -h, --help       Show this help

Output:
  TSV: severity<TAB>rule<TAB>path<TAB>message

Environment:
  FORM_ALLOWED_TOP_DIRS  Colon-separated extra top-level directory names
EOF
}

die() {
  printf 'form-audit: %s\n' "$*" >&2
  exit 2
}

ROOT=
STRICT=0
QUIET=0
declare -a USER_EXCLUDES=()

while (($# > 0)); do
  case "$1" in
    --root)
      (($# >= 2)) || die "--root requires DIR"
      ROOT=$2
      shift 2
      ;;
    --strict)
      STRICT=1
      shift
      ;;
    --exclude)
      (($# >= 2)) || die "--exclude requires REGEX"
      USER_EXCLUDES+=("$2")
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
      die "unknown argument: $1"
      ;;
  esac
done

if [[ -z "$ROOT" ]]; then
  ROOT=$(git rev-parse --show-toplevel 2>/dev/null) ||
    die "current directory is not inside a Git repository"
fi
[[ -d "$ROOT" ]] || die "root directory does not exist: $ROOT"
ROOT=$(cd "$ROOT" && pwd -P)
git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 ||
  die "not a Git worktree: $ROOT"

REPO_NAME=${ROOT##*/}
if [[ "$REPO_NAME" =~ [A-Z] ]]; then
  REPO_CLASS=complex
else
  REPO_CLASS=simple
fi
LOWER_REPO_NAME=$(printf '%s' "$REPO_NAME" | tr '[:upper:]' '[:lower:]')

declare -a ALLOWED_TOP=(data docs logs refer skills)
if [[ "$REPO_CLASS" == complex ]]; then
  ALLOWED_TOP+=("$LOWER_REPO_NAME" cpp)
else
  ALLOWED_TOP+=(bin lib hooks plugins tools static)
fi
if [[ -n "${FORM_ALLOWED_TOP_DIRS:-}" ]]; then
  IFS=':' read -r -a EXTRA_TOP <<<"$FORM_ALLOWED_TOP_DIRS"
  ALLOWED_TOP+=("${EXTRA_TOP[@]}")
fi

FINDINGS=0
ERRORS=0
WARNINGS=0

sanitize() {
  local value=$1
  value=${value//$'\t'/ }
  value=${value//$'\n'/ }
  printf '%s' "$value"
}

report() {
  local severity=$1 rule=$2 path=$3 message=$4
  FINDINGS=$((FINDINGS + 1))
  case "$severity" in
    ERROR) ERRORS=$((ERRORS + 1)) ;;
    WARNING) WARNINGS=$((WARNINGS + 1)) ;;
  esac
  printf '%s\t%s\t%s\t%s\n' \
    "$severity" "$rule" "$(sanitize "$path")" "$(sanitize "$message")"
}

is_allowed_top() {
  local top=$1 allowed
  for allowed in "${ALLOWED_TOP[@]}"; do
    [[ "$top" == "$allowed" ]] && return 0
  done
  return 1
}

is_excluded() {
  local path=$1 pattern
  case "$path" in
    .git/*|data/*|refer/*|skills/form/references/source-snapshots/*|\
    node_modules/*|*/node_modules/*|vendor/*|*/vendor/*|\
    third_party/*|*/third_party/*|.venv/*|*/.venv/*|\
    site-packages/*|*/site-packages/*|build/*|*/build/*|\
    dist/*|*/dist/*|CMakeFiles/*|*CMakeFiles/*|*.min.*)
      return 0
      ;;
  esac
  for pattern in "${USER_EXCLUDES[@]}"; do
    if [[ "$path" =~ $pattern ]]; then
      return 0
    fi
  done
  return 1
}

is_code_extension() {
  case "$1" in
    h|hh|hpp|hxx|c|cc|cpp|cxx|cu|cuh|py|pyx|pxd|sh|bash|zsh|js|ts|css|json)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_named_exception() {
  case "$1" in
    AGENTS.md|README.md|LICENSE|Makefile|Dockerfile|CMakeLists.txt|CMakeLists-*.txt)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

declare -A SEEN_TOP=()
while IFS= read -r -d '' path; do
  [[ "$path" == */* ]] || continue
  top=${path%%/*}
  if [[ -n "${SEEN_TOP[$top]+seen}" ]]; then
    continue
  fi
  SEEN_TOP[$top]=1
  if ! is_excluded "$top/" && ! is_allowed_top "$top"; then
    report WARNING UNLISTED_TOP_DIR "$top/" \
      "top-level directory is outside the form whitelist"
  fi
done < <(git -C "$ROOT" ls-files -z)

while IFS= read -r -d '' path; do
  if is_excluded "$path"; then
    continue
  fi

  base=${path##*/}
  ext=
  [[ "$base" == *.* ]] && ext=${base##*.}

  if [[ "$base" =~ [[:space:]] ]]; then
    report WARNING FILE_WHITESPACE "$path" "filename contains whitespace"
  fi

  case "$base" in
    *.bak|*.tmp|*.orig|*.rej|*.swp|*.swo|*.sw?)
      report ERROR STALE_BACKUP "$path" "tracked temporary or backup file"
      ;;
  esac

  if is_code_extension "$ext" && [[ "$base" =~ [A-Z] ]] &&
     ! is_named_exception "$base"; then
    report WARNING FILE_UPPERCASE "$path" \
      "code filename should be all lowercase"
  fi

  case "$path" in
    docs/*)
      case "$ext" in
        tex|pdf|md|png|jpg|jpeg|gif|svg|webp) ;;
        *)
          report WARNING DOC_EXTENSION "$path" \
            "docs/ only allows task documents and image attachments"
          ;;
      esac
      ;;
  esac

  case "$path" in
    logs/*)
      case "$ext" in
        log|json|tsv|csv|txt) ;;
        *)
          report WARNING LOG_EXTENSION "$path" \
            "logs/ only allows log/json/tsv/csv/txt files"
          ;;
      esac
      ;;
  esac

  case "$base" in
    *.log)
      case "$path" in
        logs/*) ;;
        *)
          report WARNING LOG_OUTSIDE_LOGS "$path" \
            "log file is outside logs/"
          ;;
      esac
      ;;
  esac

  case "$ext" in
    npy|npz|pt|pth|h5|hdf5|lime)
      case "$path" in
        data/*) ;;
        *)
          report WARNING DATA_OUTSIDE_DATA "$path" \
            "data-like file is outside data/"
          ;;
      esac
      ;;
  esac

  if [[ "$REPO_CLASS" == complex ]]; then
    case "$path" in
      */testing/*) ;;
      */tests/*)
        report WARNING TEST_LOCATION "$path" \
          "complex repository tests should live under <lowercase-repo>/testing/"
        ;;
      *)
        case "$base" in
          test_*.py|*_test.py|*.test.sh)
            report WARNING TEST_LOCATION "$path" \
              "complex repository test is outside <lowercase-repo>/testing/"
            ;;
        esac
        ;;
    esac
  fi
done < <(git -C "$ROOT" ls-files -z)

while IFS= read -r -d '' path; do
  case "$path" in
    data/.gitignore|data/AGENTS.md|data/README.md) ;;
    *)
      report ERROR TRACKED_DATA_CONTENT "$path" \
        "data/ may track only .gitignore, AGENTS.md, and README.md"
      ;;
  esac
done < <(git -C "$ROOT" ls-files -z -- data)

if ((QUIET == 0)); then
  printf '# form-audit root=%s class=%s findings=%d errors=%d warnings=%d\n' \
    "$ROOT" "$REPO_CLASS" "$FINDINGS" "$ERRORS" "$WARNINGS" >&2
fi

if ((STRICT == 1 && (ERRORS > 0 || WARNINGS > 0))); then
  exit 1
fi
exit 0
