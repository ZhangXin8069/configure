#!/usr/bin/env bash
# gpush — Stage parent changes, commit, and push only the current repository

_SRC=${BASH_SOURCE[0]:-${0}}
_NAME=${_SRC##*/}
echo "###${_NAME} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

# Locate the git repository root (works from any subdirectory)
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "ERROR: Not inside a git repository."
    exit 1
}
echo "Repo:    ${REPO_ROOT}"

cd "$REPO_ROOT" || exit 1

# SSH may forward the local locale name to a remote shell that does not have it.
_git_remote() {
    LANG=C LC_ALL=C git "$@"
}

BRANCH=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)
if [[ -z "${BRANCH}" ]]; then
    echo "ERROR: Detached HEAD; checkout a branch before gpush." >&2
    exit 1
fi
echo "Branch:  ${BRANCH}"

_submodule_paths() {
    local entry
    local metadata
    local path
    local line

    while IFS= read -r -d '' entry; do
        metadata=${entry%%$'\t'*}
        path=${entry#*$'\t'}
        if [[ "${metadata%% *}" == 160000 ]]; then
            printf '%s\0' "${path}"
        fi
    done < <(git ls-files --stage -z)

    if [[ -f .gitmodules ]]; then
        while IFS= read -r line; do
            [[ -n "${line}" ]] || continue
            printf '%s\0' "${line#* }"
        done < <(git config -f .gitmodules --get-regexp '^submodule\..*\.path$' 2>/dev/null || true)
    fi
}

_stage_parent_changes() {
    local path
    local -a exclusions=()

    while IFS= read -r -d '' path; do
        exclusions+=(":(exclude,literal)${path}")
    done < <(_submodule_paths)

    git add -A -- . "${exclusions[@]}"
}

_has_staged_submodule_changes() {
    local entry
    local metadata
    local old_mode
    local new_mode

    while IFS= read -r -d '' entry; do
        metadata=${entry%%$'\t'*}
        old_mode=${metadata#:}
        old_mode=${old_mode%% *}
        metadata=${metadata#* }
        new_mode=${metadata%% *}
        if [[ "${old_mode}" == 160000 || "${new_mode}" == 160000 ]]; then
            return 0
        fi
    done < <(git diff --cached --raw -z --ignore-submodules=none)

    return 1
}

# Fail closed whenever the repository uses the configure data/ boundary.
if [[ -d "$REPO_ROOT/data" ]]; then
    _SELF_DIR=$(cd "$(dirname "$_SRC")" && pwd -P)
    _DATA_TRACKING_CHECK="$_SELF_DIR/../skills/form/scripts/form-data-tracking-check.sh"
    if [[ ! -x "$_DATA_TRACKING_CHECK" ]]; then
        echo "ERROR: data tracking guard is missing: $_DATA_TRACKING_CHECK"
        exit 1
    fi
    if ! "$_DATA_TRACKING_CHECK" --root "$REPO_ROOT" --quiet; then
        echo "ERROR: data/ tracking guard failed; gpush stopped before staging, committing, or pushing."
        exit 1
    fi
fi

# Stage parent-repository changes only. Submodule gitlinks require an explicit
# workflow and must not be rewritten from the submodule worktree state.
if _has_staged_submodule_changes; then
    echo "ERROR: Staged submodule changes require an explicit submodule workflow; gpush aborted." >&2
    exit 1
fi
if ! _stage_parent_changes; then
    echo "ERROR: Unable to stage parent-repository changes." >&2
    exit 1
fi

# Skip commit if nothing staged
git diff --cached --quiet --ignore-submodules=all
_DIFF_STATUS=$?
if (( _DIFF_STATUS == 0 )); then
    echo "Nothing to commit."
elif (( _DIFF_STATUS == 1 )); then
    COMMIT_MSG="$(date "+%Y-%m-%d-%H-%M-%S")"
    if ! git commit -m "$COMMIT_MSG"; then
        echo "ERROR: commit failed; gpush aborted before push." >&2
        exit 1
    fi
else
    echo "ERROR: Unable to inspect staged changes; gpush aborted before push." >&2
    exit 1
fi

# Push current branch to its upstream (or origin)
PUSH_FAILED=0
if ! _git_remote push --recurse-submodules=no origin "$BRANCH"; then
    echo "ERROR: branch push failed: $BRANCH" >&2
    PUSH_FAILED=1
fi

# Push tags
if ! _git_remote push --recurse-submodules=no origin --tags; then
    echo "ERROR: tag push failed" >&2
    PUSH_FAILED=1
fi

if (( PUSH_FAILED != 0 )); then
    exit 1
fi

echo "###${_NAME} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
