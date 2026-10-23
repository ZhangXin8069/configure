#!/usr/bin/env bash
# gpull-sub - Safely fast-forward initialized submodules from their remotes

set -o pipefail

_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in
    */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/" ;;
    *) _DIR=. ;;
esac
if [[ "${_DIR}" == /* ]]; then
    _PATH="${_DIR}"
else
    _PATH=$(cd "${_DIR}" && pwd)
fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

_INIT=0
_RECURSIVE=0
_DRY_RUN=0
_FILTERS=()

_usage() {
    cat <<'EOF'
Usage: gpull-sub.sh [options] [--path submodule-path-or-name ...]

Fast-forward initialized submodules of the current Git repository by invoking
gpull.sh inside each mapped submodule. Uninitialized submodules are skipped
unless --init is specified. Detached submodules are restored to the remote
default branch; locally divergent detached commits are preserved under
refs/gpull-backups/ before the worktree is aligned.

Options:
  --init       Initialize missing submodules before pulling.
  --path PATH  Process only the named submodule path or name (repeatable).
  --recursive  Recursively update nested mapped submodules.
  --dry-run    Print actions without initializing, fetching, or pulling.
  -h, --help   Show this help.
EOF
}

while (( $# > 0 )); do
    case "$1" in
        --init) _INIT=1 ;;
        --recursive) _RECURSIVE=1 ;;
        --dry-run) _DRY_RUN=1 ;;
        --path)
            shift
            if (( $# == 0 )); then
                echo "ERROR: --path requires a submodule path or name." >&2
                exit 64
            fi
            _FILTERS+=("$1")
            ;;
        -h|--help)
            _usage
            exit 0
            ;;
        --)
            shift
            while (( $# > 0 )); do
                _FILTERS+=("$1")
                shift
            done
            break
            ;;
        -*)
            echo "ERROR: Unknown option: $1" >&2
            _usage >&2
            exit 64
            ;;
        *)
            _FILTERS+=("$1")
            ;;
    esac
    shift
done

_REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "ERROR: Not inside a Git work tree." >&2
    exit 1
}
echo "Repo:    ${_REPO_ROOT}"

_GITMODULES="${_REPO_ROOT}/.gitmodules"
if [[ ! -f "${_GITMODULES}" ]]; then
    echo "No submodule mappings found (.gitmodules is absent)."
    echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
    exit 0
fi

_GPULL="${_PATH}/gpull.sh"
if [[ ! -r "${_GPULL}" ]]; then
    echo "ERROR: Required pull script is missing or unreadable: ${_GPULL}" >&2
    exit 1
fi

_ENTRIES=$(git -C "${_REPO_ROOT}" config -f .gitmodules \
    --get-regexp '^submodule\..*\.path$')
_ENTRIES_STATUS=$?
if (( _ENTRIES_STATUS == 1 )); then
    echo "No mapped submodules found in .gitmodules."
    echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
    exit 0
elif (( _ENTRIES_STATUS != 0 )); then
    echo "ERROR: Failed to read submodule mappings from .gitmodules." >&2
    exit 1
fi

_matches_filter() {
    local path=$1
    local name=$2
    local filter

    if (( ${#_FILTERS[@]} == 0 )); then
        return 0
    fi
    for filter in "${_FILTERS[@]}"; do
        if [[ "${filter}" == "${path}" || "${filter}" == "${name}" ]]; then
            return 0
        fi
    done
    return 1
}

_validate_submodule_path() {
    local path=$1

    case "${path}" in
        ""|/*|..|../*|*/..|*/../*|*$'\n'*)
            return 1
            ;;
    esac
    return 0
}

_ensure_origin_head() {
    local submodule=$1

    if git -C "${submodule}" symbolic-ref --quiet refs/remotes/origin/HEAD >/dev/null 2>&1; then
        return 0
    fi
    git -C "${submodule}" remote set-head origin --auto >/dev/null 2>&1 || true
}

_pull_submodule() {
    local name=$1
    local path=$2
    local submodule="${_REPO_ROOT}/${path}"
    local old_head
    local new_head
    local recurse_args=(--recursive)

    if ! _validate_submodule_path "${path}"; then
        echo "ERROR: Refusing unsafe submodule path '${path}' from .gitmodules." >&2
        return 1
    fi

    if ! git -C "${_REPO_ROOT}" ls-files --stage -- "${path}" | grep -q '^160000 '; then
        echo "ERROR: ${path} is mapped in .gitmodules but is not a tracked gitlink." >&2
        return 1
    fi

    # An empty submodule path still resolves to the parent repository, so use
    # the submodule's .git file/directory to detect initialization precisely.
    if [[ ! -e "${submodule}/.git" ]]; then
        if (( _DRY_RUN )); then
            if (( _INIT )); then
                echo "DRY-RUN: would initialize and pull ${path}"
            else
                echo "SKIP: ${path} is not initialized (use --init to initialize it)."
            fi
            return 0
        fi
        if (( ! _INIT )); then
            echo "SKIP: ${path} is not initialized (use --init to initialize it)."
            return 0
        fi
        echo "INIT:    ${path}"
        if ! git -C "${_REPO_ROOT}" submodule update --init -- "${path}"; then
            echo "ERROR: Failed to initialize submodule ${path}." >&2
            return 1
        fi
    fi

    if (( _DRY_RUN )); then
        echo "DRY-RUN: would pull ${path}"
    else
        old_head=$(git -C "${submodule}" rev-parse --verify HEAD 2>/dev/null || true)
        _ensure_origin_head "${submodule}"
        if ! (
            cd "${submodule}" \
                && GPULL_DETACHED_MODE="${GPULL_SUB_DETACHED_MODE:-${GPULL_DETACHED_MODE:-back}}" \
                    bash "${_GPULL}"
        ); then
            echo "ERROR: Pull failed for submodule ${path}." >&2
            return 1
        fi
        new_head=$(git -C "${submodule}" rev-parse --verify HEAD 2>/dev/null || true)
        if [[ -n "${old_head}" && -n "${new_head}" && "${old_head}" != "${new_head}" ]]; then
            echo "UPDATED: ${path} ${old_head:0:12}..${new_head:0:12}"
        else
            echo "OK:      ${path} is up to date"
        fi
    fi

    if (( _RECURSIVE )) && [[ -f "${submodule}/.gitmodules" ]]; then
        (( _INIT )) && recurse_args+=(--init)
        (( _DRY_RUN )) && recurse_args+=(--dry-run)
        if ! (cd "${submodule}" && bash "${_PATH}/${_NAME}" "${recurse_args[@]}"); then
            echo "ERROR: Nested submodule pull failed under ${path}." >&2
            return 1
        fi
    fi
    return 0
}

_SELECTED=0
_UPDATED=0
_FAILED=0

while IFS=' ' read -r key path; do
    [[ -n "${key}" && -n "${path}" ]] || continue
    name=${key#submodule.}
    name=${name%.path}
    if ! _matches_filter "${path}" "${name}"; then
        continue
    fi
    _SELECTED=$((_SELECTED + 1))
    echo
    echo "### Submodule: ${path} ###"
    if _pull_submodule "${name}" "${path}"; then
        _UPDATED=$((_UPDATED + 1))
    else
        _FAILED=$((_FAILED + 1))
    fi
done <<< "${_ENTRIES}"

if (( _SELECTED == 0 )); then
    echo "ERROR: No mapped submodule matched the requested path or name." >&2
    _FAILED=1
fi

echo
echo "Summary: selected=${_SELECTED} processed=${_UPDATED} failed=${_FAILED}"
if (( _DRY_RUN )); then
    echo "Mode:    dry-run"
fi
if (( _UPDATED > 0 && ! _DRY_RUN )); then
    echo "Notice:  Submodule HEAD changes appear as gitlink updates in the parent repository."
fi
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"

if (( _FAILED > 0 )); then
    exit 1
fi
