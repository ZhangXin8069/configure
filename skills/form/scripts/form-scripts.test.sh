#!/usr/bin/env bash
set -euo pipefail
LC_ALL=C

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
AUDIT="$SCRIPT_DIR/form-audit.sh"
TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/form-audit-test.XXXXXX")
trap 'rm -rf "$TMP_ROOT"' EXIT

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

make_repo() {
  local dir=$1
  mkdir -p "$dir"
  git -C "$dir" init -q
  git -C "$dir" config user.name form-test
  git -C "$dir" config user.email form-test@example.invalid
}

complex="$TMP_ROOT/PyQCU"
make_repo "$complex"
mkdir -p "$complex/pyqcu" "$complex/docs" "$complex/logs" "$complex/Misc"
printf '' >"$complex/pyqcu/GoodName.py"
printf '' >"$complex/pyqcu/test_bad.py"
printf '' >"$complex/pyqcu/notes.log"
printf '' >"$complex/docs/guide.txt"
printf '' >"$complex/logs/run.log"
printf '' >"$complex/Misc/tool.sh"
git -C "$complex" add -f .
complex_status_before=$(git -C "$complex" status --porcelain=v1)

set +e
complex_output=$("$AUDIT" --root "$complex" --strict 2>/dev/null)
complex_status=$?
set -e
[[ "$complex_status" -eq 1 ]] || fail "complex fixture should fail strict audit"
[[ "$(git -C "$complex" status --porcelain=v1)" == "$complex_status_before" ]] ||
  fail "audit modified the complex fixture"
grep -q $'^WARNING\tFILE_UPPERCASE\tpyqcu/GoodName.py\t' <<<"$complex_output" ||
  fail "missing FILE_UPPERCASE finding"
grep -q $'^WARNING\tDOC_EXTENSION\tdocs/guide.txt\t' <<<"$complex_output" ||
  fail "missing DOC_EXTENSION finding"
grep -q $'^WARNING\tLOG_OUTSIDE_LOGS\tpyqcu/notes.log\t' <<<"$complex_output" ||
  fail "missing LOG_OUTSIDE_LOGS finding"
grep -q $'^WARNING\tUNLISTED_TOP_DIR\tMisc/\t' <<<"$complex_output" ||
  fail "missing UNLISTED_TOP_DIR finding"
grep -q $'^WARNING\tTEST_LOCATION\tpyqcu/test_bad.py\t' <<<"$complex_output" ||
  fail "missing TEST_LOCATION finding"

excluded_output=$("$AUDIT" --root "$complex" --exclude '^Misc/' 2>/dev/null)
! grep -q $'^WARNING\tUNLISTED_TOP_DIR\tMisc/\t' <<<"$excluded_output" ||
  fail "--exclude did not suppress the matching finding"

allowed_output=$(FORM_ALLOWED_TOP_DIRS=Misc \
  "$AUDIT" --root "$complex" 2>/dev/null)
! grep -q $'^WARNING\tUNLISTED_TOP_DIR\tMisc/\t' <<<"$allowed_output" ||
  fail "FORM_ALLOWED_TOP_DIRS did not allow Misc/"

simple="$TMP_ROOT/configure"
make_repo "$simple"
for dir in bin lib data docs logs refer skills hooks plugins tools static; do
  mkdir -p "$simple/$dir"
done
printf '' >"$simple/bin/agent-dispatch.sh"
printf '' >"$simple/bin/agent.test.sh"
printf '' >"$simple/lib/env.sh"
printf '' >"$simple/data/.gitignore"
printf '' >"$simple/data/AGENTS.md"
printf '' >"$simple/data/README.md"
printf '' >"$simple/docs/task.md"
printf '' >"$simple/logs/run.log"
printf '' >"$simple/refer/README.md"
printf '' >"$simple/skills/README.md"
printf '' >"$simple/hooks/README.md"
printf '' >"$simple/plugins/README.md"
printf '' >"$simple/tools/README.md"
printf '' >"$simple/static/README.md"
git -C "$simple" add -f .

simple_output=$("$AUDIT" --root "$simple" --strict 2>/dev/null)
[[ -z "$simple_output" ]] || fail "simple fixture should pass audit"

mkdir -p "$TMP_ROOT/not-a-repo"
set +e
"$AUDIT" --root "$TMP_ROOT/not-a-repo" >/dev/null 2>&1
not_git_status=$?
set -e
[[ "$not_git_status" -eq 2 ]] || fail "non-Git root should return exit 2"

"$AUDIT" --help >/dev/null

mkdir -p "$TMP_ROOT/empty-snapshots"
set +e
FORM_SNAPSHOT_ROOT="$TMP_ROOT/empty-snapshots" \
  "$SCRIPT_DIR/form-snapshot-verify.sh" --quiet >/dev/null 2>&1
empty_snapshot_status=$?
set -e
[[ "$empty_snapshot_status" -eq 2 ]] ||
  fail "empty snapshot root should return exit 2"

fake_root="$TMP_ROOT/fake-snapshots"
fake_snapshot="$fake_root/fixture"
mkdir -p "$fake_snapshot"
printf 'ok\n' >"$fake_snapshot/data.txt"
: >"$fake_snapshot/SYMLINKS.tsv"
fake_blob=$(git hash-object --no-filters -- "$fake_snapshot/data.txt")
fake_size=$(wc -c <"$fake_snapshot/data.txt")
{
  printf 'url\thttps://example.invalid/fixture\n'
  printf 'ref_kind\tbranch\nref\tmain\nref_object\tfixture\ncommit\tfixture\npath\tfixture\n'
  printf 'mode\ttype\tobject\tsize\tpath\tlocal\n'
  printf '100644\tblob\t%s\t%s\tdata.txt\tincluded\n' "$fake_blob" "$fake_size"
} >"$fake_snapshot/MANIFEST.tsv"
(cd "$fake_snapshot" && sha256sum data.txt MANIFEST.tsv SYMLINKS.tsv >SHA256SUMS.txt)

FORM_SNAPSHOT_ROOT="$fake_root" "$SCRIPT_DIR/form-snapshot-verify.sh" --quiet ||
  fail "valid synthetic snapshot should pass"

printf 'tampered\n' >"$fake_snapshot/data.txt"
(cd "$fake_snapshot" && sha256sum data.txt MANIFEST.tsv SYMLINKS.tsv >SHA256SUMS.txt)
set +e
FORM_SNAPSHOT_ROOT="$fake_root" \
  "$SCRIPT_DIR/form-snapshot-verify.sh" --quiet >/dev/null 2>&1
tampered_status=$?
set -e
[[ "$tampered_status" -eq 1 ]] ||
  fail "Git object tampering should return exit 1"

"$SCRIPT_DIR/form-snapshot-verify.sh" --help >/dev/null
printf 'form script tests: PASS\n'
