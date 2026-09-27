#!/usr/bin/env bash
set -euo pipefail
LC_ALL=C

usage() {
  cat <<'EOF'
Usage: form-snapshot-verify.sh [--quiet]

Verify the local form reference snapshots without network access.
Checks SHA-256 files, manifest Git object hashes, excluded binaries, and symlinks.
EOF
}

die() {
  printf 'form-snapshot-verify: %s\n' "$*" >&2
  exit 2
}

fail() {
  printf 'form-snapshot-verify: %s\n' "$*" >&2
  exit 1
}

QUIET=0
while (($# > 0)); do
  case "$1" in
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

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
SNAP_ROOT=${FORM_SNAPSHOT_ROOT:-"$SCRIPT_DIR/../references/source-snapshots"}
[[ -d "$SNAP_ROOT" ]] || die "snapshot root does not exist: $SNAP_ROOT"

if command -v sha256sum >/dev/null 2>&1; then
  SHA256_CHECK=(sha256sum -c)
elif command -v shasum >/dev/null 2>&1; then
  SHA256_CHECK=(shasum -a 256 -c)
else
  die "sha256sum or shasum is required"
fi

list_symlinks() {
  local dir=$1 path target
  while IFS= read -r path; do
    target=$(readlink "$path")
    printf '%s\t%s\n' "${path#"$dir"/}" "$target"
  done < <(find "$dir" -type l -print)
}

SNAPSHOT_COUNT=0
for dir in "$SNAP_ROOT"/*; do
  [[ -d "$dir" ]] || continue
  SNAPSHOT_COUNT=$((SNAPSHOT_COUNT + 1))
  name=${dir##*/}
  for required in MANIFEST.tsv SHA256SUMS.txt SYMLINKS.tsv; do
    [[ -f "$dir/$required" ]] || fail "$name is missing $required"
  done

  (cd "$dir" && "${SHA256_CHECK[@]}" SHA256SUMS.txt >/dev/null) ||
    fail "$name SHA-256 verification failed"

  expected_regular=$(wc -l <"$dir/SHA256SUMS.txt")
  actual_regular=$(find "$dir" -type f ! -name SHA256SUMS.txt | wc -l)
  [[ "$expected_regular" -eq "$actual_regular" ]] ||
    fail "$name has unlisted regular files"

  cmp -s <(list_symlinks "$dir" | sort) \
    "$dir/SYMLINKS.tsv" ||
    fail "$name symlink inventory mismatch"

  while IFS=$'\t' read -r mode type object size path state; do
    case "$mode" in
      [0-9][0-9][0-9][0-9][0-9][0-9]) ;;
      *) continue ;;
    esac
    if [[ "$state" == included ]]; then
      if [[ ! -e "$dir/$path" && ! -L "$dir/$path" ]]; then
        fail "$name is missing manifest entry: $path"
      fi
      if [[ -L "$dir/$path" ]]; then
        actual_object=$(
          printf '%s' "$(readlink "$dir/$path")" | git hash-object --stdin
        )
      else
        actual_object=$(git hash-object --no-filters -- "$dir/$path")
      fi
      [[ "$actual_object" == "$object" ]] ||
        fail "$name Git object mismatch: $path"
    elif [[ "$state" == excluded-binary ]]; then
      if [[ -e "$dir/$path" || -L "$dir/$path" ]]; then
        fail "$name unexpectedly contains excluded binary: $path"
      fi
    else
      fail "$name has unknown manifest state for $path: $state"
    fi
  done <"$dir/MANIFEST.tsv"

  if ((QUIET == 0)); then
    printf '[ok] %s: %s regular files, %s manifest rows\n' \
      "$name" "$actual_regular" "$(wc -l <"$dir/MANIFEST.tsv")"
  fi
done

((SNAPSHOT_COUNT > 0)) || die "no snapshots found under $SNAP_ROOT"
