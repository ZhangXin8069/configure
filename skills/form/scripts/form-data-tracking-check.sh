#!/usr/bin/env bash
set -euo pipefail
LC_ALL=C

usage() {
  cat <<'EOF'
Usage: form-data-tracking-check.sh [--root DIR] [--quiet]

Fail when data/ tracks anything outside the contract allowlist or when the local
data ignore shield does not protect cache/runtime content.

Options:
  --root DIR  Git repository root (default: current repository)
  --quiet     Suppress the stderr summary
  -h, --help  Show this help

Output:
  TSV: severity<TAB>rule<TAB>path<TAB>message
EOF
}

die() {
  printf 'form-data-tracking-check: %s\n' "$*" >&2
  exit 2
}

ROOT=
QUIET=0

while (($# > 0)); do
  case "$1" in
    --root)
      (($# >= 2)) || die "--root requires DIR"
      ROOT=$2
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

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
AUDIT="$SCRIPT_DIR/form-audit.sh"
[[ -x "$AUDIT" ]] || die "form audit is missing or not executable: $AUDIT"

audit_status=0
audit_output=$("$AUDIT" --root "$ROOT" --quiet) || audit_status=$?
((audit_status <= 1)) || die "form audit failed with exit $audit_status"

violations=$(grep -E $'^ERROR\t(TRACKED_DATA_CONTENT|DATA_IGNORE_MISSING|DATA_IGNORE_PATTERN|DATA_IGNORE_BYPASS|DATA_CONTRACT_IGNORED)\t' \
  <<<"$audit_output" || true)

if [[ -n "$violations" ]]; then
  printf '%s\n' "$violations"
  if ((QUIET == 0)); then
    count=$(printf '%s\n' "$violations" | wc -l | tr -d ' ')
    printf '# form-data-tracking-check root=%s violations=%s\n' "$ROOT" "$count" >&2
  fi
  exit 1
fi

if ((QUIET == 0)); then
  printf '# form-data-tracking-check root=%s violations=0\n' "$ROOT" >&2
fi
