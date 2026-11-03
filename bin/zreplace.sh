#!/usr/bin/env bash
_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

_usage() {
    printf 'Usage: %s [--] DIRECTORY SEARCH_TEXT REPLACEMENT_TEXT\n' "${_NAME}" >&2
    printf 'Example: %s ./lib libqcu libquda\n' "${_NAME}" >&2
    printf 'Only literal file-content matches are replaced; file names are not changed.\n' >&2
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    _usage
    exit 0
fi
if [[ "${1:-}" == "--" ]]; then
    shift
fi
if [[ "$#" -ne 3 ]]; then
    _usage
    exit 1
fi

search_dir=$1
search_text=$2
replacement_text=$3

if [[ ! -d "${search_dir}" ]]; then
    printf 'Error: not a directory: %s\n' "${search_dir}" >&2
    exit 1
fi
if [[ -z "${search_text}" ]]; then
    printf 'Error: SEARCH_TEXT must not be empty.\n' >&2
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    printf 'Error: python3 is required for safe literal replacement.\n' >&2
    exit 1
fi

zsearch_path="${_PATH}/zsearch.sh"
if [[ ! -x "${zsearch_path}" ]]; then
    printf 'Error: zsearch.sh is not executable: %s\n' "${zsearch_path}" >&2
    exit 1
fi

search_dir_abs=$(cd -- "${search_dir}" && pwd -P)

printf '=== Step 1: zsearch matches ===\n'
bash "${zsearch_path}" -- "${search_dir_abs}" "${search_text}"

printf '\n=== Step 2: literal replacement preview and confirmation ===\n'
# Preserve the caller's stdin because the heredoc below supplies Python's stdin.
exec 3<&0
python3 - "${search_dir_abs}" "${search_text}" "${replacement_text}" <<'PY'
import os
import stat
import sys
import tempfile


root, search_text, replacement_text = sys.argv[1:4]
search_bytes = os.fsencode(search_text)
replacement_bytes = os.fsencode(replacement_text)

if search_bytes == replacement_bytes:
    print("SEARCH_TEXT and REPLACEMENT_TEXT are identical; nothing to replace.")
    raise SystemExit(0)

matches = []
for current_dir, dir_names, file_names in os.walk(root, followlinks=False):
    dir_names[:] = [
        name
        for name in dir_names
        if not os.path.islink(os.path.join(current_dir, name))
    ]
    for file_name in file_names:
        path = os.path.join(current_dir, file_name)
        try:
            metadata = os.lstat(path)
            if not stat.S_ISREG(metadata.st_mode):
                continue
            with open(path, "rb") as source:
                data = source.read()
        except OSError as error:
            print(f"Warning: skipped unreadable file {path}: {error}", file=sys.stderr)
            continue
        if b"\0" in data:
            continue
        count = data.count(search_bytes)
        if count:
            matches.append((path, count))

matches.sort(key=lambda item: item[0])
if not matches:
    print("No literal file-content matches; nothing to replace.")
    raise SystemExit(0)

total_count = sum(count for _, count in matches)
print(f"Matched {total_count} occurrence(s) in {len(matches)} file(s):")
for path, count in matches:
    print(f"  {os.path.relpath(path, root)}: {count}")
print(
    f"Replace {search_text!r} with {replacement_text!r} in these files? [y/N] ",
    end="",
    flush=True,
)

with os.fdopen(3, "r", encoding="utf-8", errors="replace") as confirmation_input:
    answer = confirmation_input.readline()
if not answer:
    print("\nNo confirmation received; canceled.")
    raise SystemExit(1)
if answer.strip().lower() not in {"y", "yes"}:
    print("Canceled; no files changed.")
    raise SystemExit(0)

staged = []
try:
    for path, expected_count in matches:
        try:
            metadata = os.lstat(path)
            if not stat.S_ISREG(metadata.st_mode):
                print(f"Warning: skipped non-regular file {path}", file=sys.stderr)
                continue
            with open(path, "rb") as source:
                data = source.read()
            if b"\0" in data:
                print(f"Warning: skipped binary file {path}", file=sys.stderr)
                continue
            count = data.count(search_bytes)
            if count != expected_count:
                print(
                    f"Warning: skipped changed file {path}: "
                    f"expected {expected_count} match(es), found {count}",
                    file=sys.stderr,
                )
                continue

            modified = data.replace(search_bytes, replacement_bytes)
            parent_dir = os.path.dirname(path)
            file_descriptor, temporary_path = tempfile.mkstemp(
                prefix=f".{os.path.basename(path)}.zreplace.",
                dir=parent_dir,
            )
            try:
                with os.fdopen(file_descriptor, "wb") as target:
                    target.write(modified)
                    target.flush()
                    os.fsync(target.fileno())
                os.chmod(temporary_path, stat.S_IMODE(metadata.st_mode))
            except BaseException:
                try:
                    os.close(file_descriptor)
                except OSError:
                    pass
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass
                raise
            staged.append((temporary_path, path, count))
        except OSError as error:
            print(f"Error: failed to prepare {path}: {error}", file=sys.stderr)
            for temporary_path, _, _ in staged:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass
            raise SystemExit(1)

    if not staged:
        print("No files were replaced because all matches changed during confirmation.")
        raise SystemExit(1)

    for temporary_path, path, _ in staged:
        os.replace(temporary_path, path)
except OSError as error:
    print(f"Error: replacement failed: {error}", file=sys.stderr)
    for temporary_path, _, _ in staged:
        if os.path.exists(temporary_path):
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
    raise SystemExit(1)

print(
    f"Replaced {sum(count for _, _, count in staged)} occurrence(s) "
    f"in {len(staged)} file(s)."
)
PY
exec 3<&-

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
