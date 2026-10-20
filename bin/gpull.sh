#!/usr/bin/env bash
# gpull — Pull latest changes from anywhere inside a repo

set -o pipefail

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

BRANCH=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)
if [[ -n "${BRANCH}" ]]; then
    echo "Branch:  ${BRANCH}"
else
    echo "Branch:  (detached HEAD)"
fi

# Fetch all remotes
if ! git fetch --all --prune; then
    echo "ERROR: git fetch failed; pull aborted." >&2
    exit 1
fi

_find_origin_default_ref() {
    local remote_ref
    local candidate
    local candidates

    remote_ref=$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || true)
    if [[ "${remote_ref}" == origin/* ]] \
        && git show-ref --verify --quiet "refs/remotes/${remote_ref}"; then
        printf '%s\n' "${remote_ref}"
        return 0
    fi

    # Some old clones do not create origin/HEAD. Accept a remote branch only
    # when exactly one branch contains the detached commit.
    candidates=$(
        git for-each-ref --format='%(refname:short)' --contains HEAD refs/remotes/origin 2>/dev/null \
            | while IFS= read -r candidate; do
                [[ "${candidate}" == "origin/HEAD" ]] || printf '%s\n' "${candidate}"
            done
    )
    if [[ -n "${candidates}" && "${candidates}" != *$'\n'* ]]; then
        printf '%s\n' "${candidates}"
        return 0
    fi

    return 1
}

_restore_detached_branch() {
    local remote_ref
    local branch

    if ! remote_ref=$(_find_origin_default_ref); then
        echo "ERROR: Detached HEAD; no unique origin branch can be selected safely." >&2
        echo "Hint:  inspect and create a branch before pulling:" >&2
        echo "       git branch <backup-branch> && git checkout <target-branch>" >&2
        return 1
    fi

    branch=${remote_ref#origin/}
    if ! git merge-base --is-ancestor HEAD "${remote_ref}"; then
        echo "ERROR: Detached HEAD is not contained in ${remote_ref}; refusing to switch branches." >&2
        echo "Hint:  preserve local commits first:" >&2
        echo "       git branch <backup-branch> && git checkout <target-branch>" >&2
        return 1
    fi

    echo "NOTICE: Restoring tracking branch ${branch} from ${remote_ref}."
    if git show-ref --verify --quiet "refs/heads/${branch}"; then
        git checkout "${branch}" || return 1
    else
        git checkout -b "${branch}" --track "${remote_ref}" || return 1
    fi

    BRANCH=${branch}
    echo "Branch:  ${BRANCH}"
}

if [[ -z "${BRANCH}" ]]; then
    _restore_detached_branch || exit 1
fi

_has_local_changes() {
    ! git diff --quiet || ! git diff --cached --quiet
}

_pull_with_manual_stash() {
    local branch=$1
    local message="gpull auto-stash $(date "+%Y-%m-%d-%H-%M-%S")"
    local stash_created=0
    local pull_status=0

    if _has_local_changes; then
        # Git < 2.13 lacks `stash push`; Git >= 2.13 accepts the modern form.
        if git stash push --quiet --message "$message" >/dev/null 2>&1; then
            stash_created=1
        elif git stash save --quiet "$message"; then
            stash_created=1
        else
            echo "ERROR: Unable to stash local tracked changes; pull aborted." >&2
            return 1
        fi
    fi

    git pull --rebase origin "$branch" || pull_status=$?
    if ((pull_status != 0)); then
        if ((stash_created)); then
            echo "WARN: Pull failed; local changes remain in git stash." >&2
        fi
        return "$pull_status"
    fi

    if ((stash_created)) && ! git stash pop --quiet; then
        echo "ERROR: Pull succeeded, but restoring local changes conflicted." >&2
        echo "Resolve the conflict, then run: git stash pop" >&2
        return 1
    fi

    return 0
}

# Pull current branch with a linear history; preserve tracked worktree changes.
_PULL_STATUS=0
_PULL_HELP=$(git pull -h 2>&1 || true)
if [[ "${_PULL_HELP}" == *"--autostash"* ]]; then
    git pull --rebase --autostash origin "$BRANCH" || _PULL_STATUS=$?
else
    echo "Notice: Git lacks pull --autostash; using the manual stash fallback."
    _pull_with_manual_stash "$BRANCH" || _PULL_STATUS=$?
fi

if ((_PULL_STATUS != 0)); then
    echo "ERROR: git pull failed with status ${_PULL_STATUS}." >&2
    exit "${_PULL_STATUS}"
fi

echo "###${_NAME} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
