#!/usr/bin/env bash
set -euo pipefail
LC_ALL=C

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
AUDIT="$SCRIPT_DIR/form-audit.sh"
AGENTS_SYNC="$SCRIPT_DIR/form-agents-sync.sh"
LARGE_FILES="$SCRIPT_DIR/form-large-files-check.sh"
DATA_TRACKING="$SCRIPT_DIR/form-data-tracking-check.sh"
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
printf '' >"$complex/pyqcu/dev26_1_solver.py"
printf '' >"$complex/pyqcu/test_bad.py"
printf '' >"$complex/pyqcu/AGENT.md"
printf '' >"$complex/pyqcu/notes.log"
printf '' >"$complex/docs/guide.txt"
printf '' >"$complex/logs/run.log"
printf '' >"$complex/logs/v20261016bad.txt"
printf '' >"$complex/logs/notes.md"
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
grep -q $'^WARNING\tTAG_NAME_IN_PATH\tpyqcu/dev26_1_solver.py\t' <<<"$complex_output" ||
  fail "missing TAG_NAME_IN_PATH finding"
grep -q $'^ERROR\tAGENT_FILE_SINGULAR\tpyqcu/AGENT.md\t' <<<"$complex_output" ||
  fail "missing AGENT_FILE_SINGULAR finding"
grep -q $'^WARNING\tDOC_EXTENSION\tdocs/guide.txt\t' <<<"$complex_output" ||
  fail "missing DOC_EXTENSION finding"
grep -q $'^WARNING\tLOG_OUTSIDE_LOGS\tpyqcu/notes.log\t' <<<"$complex_output" ||
  fail "missing LOG_OUTSIDE_LOGS finding"
grep -q $'^WARNING\tLOG_TIMESTAMP_NAME\tlogs/v20261016bad.txt\t' <<<"$complex_output" ||
  fail "missing LOG_TIMESTAMP_NAME finding"
grep -q $'^WARNING\tLOG_EXTENSION\tlogs/notes.md\t' <<<"$complex_output" ||
  fail "missing LOG_EXTENSION finding"
grep -q $'^WARNING\tUNLISTED_TOP_DIR\tMisc/\t' <<<"$complex_output" ||
  fail "missing UNLISTED_TOP_DIR finding"
[[ "$(grep -c $'^WARNING\tUNLISTED_TOP_DIR\tMisc/\t' <<<"$complex_output")" -eq 1 ]] ||
  fail "top-level warning should be reported once"
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
mkdir -p "$simple/docs" "$simple/logs" \
  "$simple/.opencode/skills/form/references/source-snapshots/configure-main/bin"
printf '**/\n' >"$simple/docs/.gitignore"
printf '*\n' >"$simple/logs/.gitignore"
printf '' >"$simple/.opencode/skills/form/references/source-snapshots/configure-main/bin/gzBad.sh"
cat >"$simple/data/.gitignore" <<'EOF'
*
!.gitignore
!AGENTS.md
!README.md
EOF
printf '' >"$simple/data/AGENTS.md"
printf '' >"$simple/data/README.md"
printf '' >"$simple/docs/task.md"
printf '' >"$simple/logs/run.log"
printf '' >"$simple/logs/AGENTS.md"
printf '' >"$simple/logs/v20261016.txt"
printf '' >"$simple/logs/v2026101617.txt"
printf '' >"$simple/logs/v202610161725.txt"
printf '' >"$simple/logs/v20261016172512.txt"
printf '' >"$simple/logs/v202610161725-2.txt"
printf '' >"$simple/logs/v2026-10-16-17.txt"
printf '' >"$simple/logs/v2026-10-16-17-25.txt"
printf '' >"$simple/logs/v2026-10-16-17-25-12.txt"
printf '' >"$simple/refer/README.md"
printf '' >"$simple/skills/README.md"
printf '' >"$simple/hooks/README.md"
printf '' >"$simple/plugins/README.md"
printf '' >"$simple/tools/README.md"
printf '' >"$simple/static/README.md"
git -C "$simple" add -f .

simple_output=$("$AUDIT" --root "$simple" --strict 2>/dev/null)
[[ -z "$simple_output" ]] || fail "simple fixture should pass audit"
"$DATA_TRACKING" --root "$simple" --quiet ||
  fail "data tracking guard should pass the clean fixture"

data_repo="$TMP_ROOT/data-tracking-repo"
make_repo "$data_repo"
mkdir -p "$data_repo/data/cache"
cat >"$data_repo/data/.gitignore" <<'EOF'
*
!.gitignore
!AGENTS.md
!README.md
EOF
printf '' >"$data_repo/data/AGENTS.md"
printf '' >"$data_repo/data/README.md"
printf 'must-not-be-tracked\n' >"$data_repo/data/cache/runtime.env"
git -C "$data_repo" add -f data
set +e
data_output=$("$AUDIT" --root "$data_repo" --strict 2>/dev/null)
data_status=$?
set -e
[[ "$data_status" -eq 1 ]] || fail "tracked data runtime should fail strict audit"
grep -q $'^ERROR\tTRACKED_DATA_CONTENT\tdata/cache/runtime.env\t' <<<"$data_output" ||
  fail "missing TRACKED_DATA_CONTENT finding"
set +e
data_guard_output=$("$DATA_TRACKING" --root "$data_repo" 2>/dev/null)
data_guard_status=$?
set -e
[[ "$data_guard_status" -eq 1 ]] || fail "data tracking guard should reject tracked cache"
grep -q $'TRACKED_DATA_CONTENT\tdata/cache/runtime.env\t' <<<"$data_guard_output" ||
  fail "data tracking guard should report tracked cache"

bypass_repo="$TMP_ROOT/data-ignore-bypass-repo"
make_repo "$bypass_repo"
mkdir -p "$bypass_repo/data"
printf '' >"$bypass_repo/data/.gitignore"
printf '' >"$bypass_repo/data/AGENTS.md"
printf '' >"$bypass_repo/data/README.md"
git -C "$bypass_repo" add data
set +e
bypass_output=$("$AUDIT" --root "$bypass_repo" --strict 2>/dev/null)
bypass_status=$?
set -e
[[ "$bypass_status" -eq 1 ]] || fail "ineffective data ignore rules should fail strict audit"
grep -q $'^ERROR\tDATA_IGNORE_BYPASS\tdata/cache/form-audit-probe\t' <<<"$bypass_output" ||
  fail "missing DATA_IGNORE_BYPASS finding"
grep -q $'^ERROR\tDATA_IGNORE_PATTERN\tdata/.gitignore\t' <<<"$bypass_output" ||
  fail "missing DATA_IGNORE_PATTERN finding"

credential_repo="$TMP_ROOT/inline-url-credential-repo"
make_repo "$credential_repo"
mkdir -p "$credential_repo/lib/example"
printf 'export http_proxy=https://user:password@example.invalid:8080\n' \
  >"$credential_repo/lib/example/env.sh"
git -C "$credential_repo" add lib/example/env.sh
set +e
credential_output=$("$AUDIT" --root "$credential_repo" --strict 2>/dev/null)
credential_status=$?
set -e
[[ "$credential_status" -eq 1 ]] || fail "inline URL userinfo should fail strict audit"
grep -q $'^ERROR\tINLINE_URL_CREDENTIALS\tlib/example/env.sh\t' <<<"$credential_output" ||
  fail "missing INLINE_URL_CREDENTIALS finding"

reference_repo="$TMP_ROOT/reference-repo"
make_repo "$reference_repo"
mkdir -p "$reference_repo/refer/git-rep/Vendored/docs"
printf '# Sources\n\n- https://example.invalid/team/FakeSub.git\n' \
  >"$reference_repo/refer/git-rep/README.md"
printf '' >"$reference_repo/refer/git-rep/Vendored/docs/analy.tex"
printf '' >"$reference_repo/refer/git-rep/Vendored/docs/pure.pdf"
printf 'anchor\n' >"$reference_repo/anchor.txt"
git -C "$reference_repo" add anchor.txt
git -C "$reference_repo" commit -qm init
anchor_sha=$(git -C "$reference_repo" rev-parse HEAD)
cat >"$reference_repo/.gitmodules" <<'EOF'
[submodule "refer/git-rep/FakeSub"]
	path = refer/git-rep/FakeSub
	url = https://example.invalid/team/FakeSub.git
EOF
git -C "$reference_repo" update-index --add \
  --cacheinfo "160000,$anchor_sha,refer/git-rep/FakeSub"
git -C "$reference_repo" add -f \
  .gitmodules refer/git-rep/README.md \
  refer/git-rep/Vendored/docs/analy.tex refer/git-rep/Vendored/docs/pure.pdf

set +e
reference_output=$("$AUDIT" --root "$reference_repo" --strict 2>/dev/null)
reference_status=$?
set -e
[[ "$reference_status" -eq 1 ]] || fail "reference fixture should fail strict audit"
grep -q $'^WARNING\tREFERENCE_DOC_MISPLACED\trefer/git-rep/Vendored/docs/analy.tex\t' <<<"$reference_output" ||
  fail "missing REFERENCE_DOC_MISPLACED for TeX analysis document"
grep -q $'^WARNING\tREFERENCE_DOC_MISPLACED\trefer/git-rep/Vendored/docs/pure.pdf\t' <<<"$reference_output" ||
  fail "missing REFERENCE_DOC_MISPLACED for PDF analysis document"
! grep -q $'^WARNING\tREFERENCE_README_MISSING\t' <<<"$reference_output" ||
  fail "unexpected REFERENCE_README_MISSING finding"
! grep -q $'^ERROR\tREFERENCE_SUBMODULE_METADATA\t' <<<"$reference_output" ||
  fail "unexpected REFERENCE_SUBMODULE_METADATA finding"
! grep -q $'^WARNING\tREFERENCE_README_SOURCE_MISSING\t' <<<"$reference_output" ||
  fail "unexpected REFERENCE_README_SOURCE_MISSING finding"

reference_excluded=$("$AUDIT" --root "$reference_repo" \
  --exclude '^refer/git-rep/Vendored/' 2>/dev/null)
! grep -q $'REFERENCE_DOC_MISPLACED' <<<"$reference_excluded" ||
  fail "--exclude did not suppress reference findings"

git -C "$reference_repo" rm -q --cached refer/git-rep/README.md
set +e
reference_no_readme=$("$AUDIT" --root "$reference_repo" 2>/dev/null)
set -e
grep -q $'^WARNING\tREFERENCE_README_MISSING\trefer/git-rep/README.md\t' <<<"$reference_no_readme" ||
  fail "missing REFERENCE_README_MISSING finding"
git -C "$reference_repo" add -- refer/git-rep/README.md

printf '# Sources\n\n- no source recorded\n' >"$reference_repo/refer/git-rep/README.md"
git -C "$reference_repo" add -- refer/git-rep/README.md
set +e
reference_no_source=$("$AUDIT" --root "$reference_repo" 2>/dev/null)
set -e
grep -q $'^WARNING\tREFERENCE_README_SOURCE_MISSING\trefer/git-rep/README.md\t' <<<"$reference_no_source" ||
  fail "missing REFERENCE_README_SOURCE_MISSING finding"

: >"$reference_repo/refer/git-rep/README.md"
git -C "$reference_repo" add -- refer/git-rep/README.md
set +e
reference_empty=$("$AUDIT" --root "$reference_repo" 2>/dev/null)
set -e
grep -q $'^WARNING\tREFERENCE_README_EMPTY\trefer/git-rep/README.md\t' <<<"$reference_empty" ||
  fail "missing REFERENCE_README_EMPTY finding"

printf '# Sources\n\n- https://example.invalid/team/FakeSub.git\n' \
  >"$reference_repo/refer/git-rep/README.md"
printf '[submodule "refer/git-rep/FakeSub"]\n\tpath = refer/git-rep/FakeSub\n' \
  >"$reference_repo/.gitmodules"
git -C "$reference_repo" add -- .gitmodules refer/git-rep/README.md
set +e
reference_no_url=$("$AUDIT" --root "$reference_repo" 2>/dev/null)
set -e
grep -q $'^ERROR\tREFERENCE_SUBMODULE_METADATA\trefer/git-rep/FakeSub\t' <<<"$reference_no_url" ||
  fail "missing REFERENCE_SUBMODULE_METADATA finding"

printf '[submodule "refer/git-rep/FakeSub"]\n\tpath = refer/git-rep/FakeSub\n\turl = https://example.invalid/team/FakeSub.git\n' \
  >"$reference_repo/.gitmodules"
git -C "$reference_repo" rm -r -q --cached refer/git-rep/Vendored
rm -rf "$reference_repo/refer/git-rep/Vendored"
mkdir -p "$reference_repo/refer/git-rep/docs"
printf '' >"$reference_repo/refer/git-rep/docs/analy.tex"
git -C "$reference_repo" add -f -- .gitmodules refer/git-rep/docs/analy.tex
set +e
reference_clean_output=$("$AUDIT" --root "$reference_repo" --strict 2>/dev/null)
reference_clean_status=$?
set -e
[[ "$reference_clean_status" -eq 0 ]] ||
  fail "compliant reference fixture should pass strict audit"
[[ -z "$reference_clean_output" ]] ||
  fail "compliant reference fixture should have no findings"

sync_repo="$TMP_ROOT/sync-repo"
make_repo "$sync_repo"
printf '# Existing rules\n\n- local rule wins\n' >"$sync_repo/AGENTS.md"
sync_section="$TMP_ROOT/form-section.md"
printf '## form sync\n\n- protect local rules\n' >"$sync_section"
"$AGENTS_SYNC" --root "$sync_repo" --content "$sync_section" --quiet
grep -Fq -- '- local rule wins' "$sync_repo/AGENTS.md" ||
  fail "AGENTS sync removed existing rules"
grep -Fq -- '<!-- form-skill:start -->' "$sync_repo/AGENTS.md" ||
  fail "AGENTS sync did not add the start marker"
grep -Fq -- '<!-- form-skill:end -->' "$sync_repo/AGENTS.md" ||
  fail "AGENTS sync did not add the end marker"
"$AGENTS_SYNC" --root "$sync_repo" --content "$sync_section" --check --quiet ||
  fail "AGENTS sync check should pass after synchronization"
cp "$sync_repo/AGENTS.md" "$TMP_ROOT/agents-before-second-sync.md"
"$AGENTS_SYNC" --root "$sync_repo" --content "$sync_section" --quiet
cmp -s "$TMP_ROOT/agents-before-second-sync.md" "$sync_repo/AGENTS.md" ||
  fail "AGENTS sync should be idempotent"
printf '## form sync\n\n- updated managed rule\n' >"$sync_section"
set +e
"$AGENTS_SYNC" --root "$sync_repo" --content "$sync_section" --check --quiet
sync_check_status=$?
set -e
[[ "$sync_check_status" -eq 1 ]] ||
  fail "AGENTS sync check should report an update when content differs"
cmp -s "$TMP_ROOT/agents-before-second-sync.md" "$sync_repo/AGENTS.md" ||
  fail "AGENTS sync check should not modify the target"
"$AGENTS_SYNC" --root "$sync_repo" --content "$sync_section" --quiet
grep -Fq -- '- local rule wins' "$sync_repo/AGENTS.md" ||
  fail "AGENTS sync update removed local rules"
grep -Fq -- '- updated managed rule' "$sync_repo/AGENTS.md" ||
  fail "AGENTS sync did not update its managed section"
! grep -Fq -- '- protect local rules' "$sync_repo/AGENTS.md" ||
  fail "AGENTS sync retained the superseded managed section"

singular_target_repo="$TMP_ROOT/singular-target-repo"
make_repo "$singular_target_repo"
set +e
"$AGENTS_SYNC" --root "$singular_target_repo" --target AGENT.md \
  --content "$sync_section" >/dev/null 2>&1
singular_target_status=$?
set -e
[[ "$singular_target_status" -eq 2 ]] ||
  fail "AGENTS sync should reject the singular target name"
[[ ! -e "$singular_target_repo/AGENT.md" && ! -e "$singular_target_repo/AGENTS.md" ]] ||
  fail "AGENTS sync should not create files for an invalid target"

new_agents_repo="$TMP_ROOT/new-agents-repo"
make_repo "$new_agents_repo"
"$AGENTS_SYNC" --root "$new_agents_repo" --content "$sync_section" --quiet
[[ -s "$new_agents_repo/AGENTS.md" ]] ||
  fail "AGENTS sync should create AGENTS.md when neither file exists"

mkdir -p "$new_agents_repo/subdir"
set +e
"$AGENTS_SYNC" --root "$new_agents_repo/subdir" --content "$sync_section" \
  >/dev/null 2>&1
subdir_sync_status=$?
set -e
[[ "$subdir_sync_status" -eq 2 ]] ||
  fail "AGENTS sync should reject a non-root --root directory"

broken_agents_repo="$TMP_ROOT/broken-agents-repo"
make_repo "$broken_agents_repo"
printf '%s\n' '<!-- form-skill:start -->' >"$broken_agents_repo/AGENTS.md"
set +e
"$AGENTS_SYNC" --root "$broken_agents_repo" --content "$sync_section" \
  >/dev/null 2>&1
broken_agents_status=$?
set -e
[[ "$broken_agents_status" -eq 2 ]] ||
  fail "AGENTS sync should reject incomplete markers"

out_of_order_agents_repo="$TMP_ROOT/out-of-order-agents-repo"
make_repo "$out_of_order_agents_repo"
{
  printf '%s\n' '<!-- form-skill:end -->'
  printf '%s\n' '<!-- form-skill:start -->'
} >"$out_of_order_agents_repo/AGENTS.md"
set +e
"$AGENTS_SYNC" --root "$out_of_order_agents_repo" --content "$sync_section" \
  >/dev/null 2>&1
out_of_order_agents_status=$?
set -e
[[ "$out_of_order_agents_status" -eq 2 ]] ||
  fail "AGENTS sync should reject out-of-order markers"

large_repo="$TMP_ROOT/large-files-repo"
make_repo "$large_repo"
printf '1234567\n' >"$large_repo/small.txt"
git -C "$large_repo" add small.txt
"$LARGE_FILES" --root "$large_repo" --max-bytes 8 --quiet ||
  fail "large-file check should accept a file at the size limit"
git -C "$large_repo" update-index --add --cacheinfo \
  160000 1111111111111111111111111111111111111111 fake-sub
"$LARGE_FILES" --root "$large_repo" --max-bytes 8 --quiet ||
  fail "large-file check should ignore gitlink entries"
printf '123456789\n' >"$large_repo/large.txt"
git -C "$large_repo" add large.txt
set +e
large_output=$("$LARGE_FILES" --root "$large_repo" --max-bytes 8 2>/dev/null)
large_status=$?
set -e
[[ "$large_status" -eq 1 ]] || fail "large-file check should reject an oversized staged file"
grep -q $'LARGE_STAGED_FILE\tlarge.txt\t' <<<"$large_output" ||
  fail "large-file check should identify the oversized staged file"

mkdir -p "$TMP_ROOT/not-a-repo"
set +e
"$AUDIT" --root "$TMP_ROOT/not-a-repo" >/dev/null 2>&1
not_git_status=$?
set -e
[[ "$not_git_status" -eq 2 ]] || fail "non-Git root should return exit 2"

"$AUDIT" --help >/dev/null
"$AGENTS_SYNC" --help >/dev/null
"$LARGE_FILES" --help >/dev/null
"$DATA_TRACKING" --help >/dev/null

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
