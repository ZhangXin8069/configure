#!/usr/bin/env bash
# gpull — Safely fast-forward a repository from either HTTPS or SSH origin

set -o pipefail

_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}
echo "###${_NAME} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

# Locate the git repository root (works from any subdirectory)
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "ERROR: Not inside a git repository."
    exit 1
}
echo "Repo:    ${REPO_ROOT}"

cd "$REPO_ROOT" || exit 1

_DETACHED_MODE=${GPULL_DETACHED_MODE:-safe}

if [[ ! -r "${_PATH}/_git_lock.sh" ]]; then
    echo "ERROR: Missing Git lock helper: ${_PATH}/_git_lock.sh" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "${_PATH}/_git_lock.sh"
case "${_DETACHED_MODE}" in
    safe|back) ;;
    *)
        echo "ERROR: GPULL_DETACHED_MODE must be one of: safe, back." >&2
        exit 64
        ;;
esac
_git_prepare_index_lock "${REPO_ROOT}" || exit $?

_REMOTE_URL=$(git config --get remote.origin.url 2>/dev/null || true)
if [[ -z "${_REMOTE_URL}" ]]; then
    echo "ERROR: Remote 'origin' is not configured; pull aborted." >&2
    exit 1
fi
case "${_REMOTE_URL}" in
    https://*|http://*) _REMOTE_KIND=https ;;
    ssh://*|git@*|*@*:*) _REMOTE_KIND=ssh ;;
    file://*|/*|./*|../*) _REMOTE_KIND=local ;;
    *) _REMOTE_KIND=other ;;
esac
echo "Remote:  origin (${_REMOTE_KIND})"

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

    for candidate in origin/main origin/master; do
        if git show-ref --verify --quiet "refs/remotes/${candidate}"; then
            printf '%s\n' "${candidate}"
            return 0
        fi
    done

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
    local backup_ref
    local branch_backup_ref
    local old_head

    if ! remote_ref=$(_find_origin_default_ref); then
        echo "ERROR: Detached HEAD; no unique origin branch can be selected safely." >&2
        echo "Hint:  inspect and create a branch before pulling:" >&2
        echo "       git branch <backup-branch> && git checkout <target-branch>" >&2
        return 1
    fi

    branch=${remote_ref#origin/}
    if ! git merge-base --is-ancestor HEAD "${remote_ref}"; then
        if [[ "${_DETACHED_MODE}" != back ]]; then
            echo "ERROR: Detached HEAD is not contained in ${remote_ref}; refusing to switch branches." >&2
            echo "Hint:  preserve local commits first:" >&2
            echo "       git branch <backup-branch> && git checkout <target-branch>" >&2
            return 1
        fi

        old_head=$(git rev-parse HEAD) || return 1
        backup_ref="refs/gpull-backups/${branch}/$(date "+%Y%m%d%H%M%S")-${old_head:0:12}-$$"
        if ! git update-ref "${backup_ref}" HEAD; then
            echo "ERROR: Unable to preserve detached HEAD before restoring ${remote_ref}." >&2
            return 1
        fi
        echo "BACKUP: preserved detached HEAD as ${backup_ref}."

        if git show-ref --verify --quiet "refs/heads/${branch}"; then
            branch_backup_ref="${backup_ref}-branch"
            git update-ref "${branch_backup_ref}" "refs/heads/${branch}" || return 1
            echo "BACKUP: preserved local branch ${branch} as ${branch_backup_ref}."
        fi
        echo "NOTICE: Restoring ${branch} from ${remote_ref} and overriding the detached worktree."
        git checkout -B "${branch}" --track "${remote_ref}" || return 1
        BRANCH=${branch}
        echo "Branch:  ${BRANCH}"
        return 0
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
    shift
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

    git pull "$@" origin "$branch" || pull_status=$?
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

_determine_branch_relation() {
    local upstream_ref="refs/remotes/origin/${BRANCH}"
    local head_commit
    local upstream_commit

    if ! git show-ref --verify --quiet "${upstream_ref}"; then
        _BRANCH_RELATION=missing
        return 0
    fi

    head_commit=$(git rev-parse HEAD) || return 1
    upstream_commit=$(git rev-parse --verify "${upstream_ref}") || return 1
    if [[ "${head_commit}" == "${upstream_commit}" ]]; then
        _BRANCH_RELATION=equal
    elif git merge-base --is-ancestor HEAD "${upstream_ref}"; then
        _BRANCH_RELATION=behind
    elif git merge-base --is-ancestor "${upstream_ref}" HEAD; then
        _BRANCH_RELATION=ahead
    else
        _BRANCH_RELATION=diverged
    fi
}

_determine_branch_relation || {
    echo "ERROR: Unable to compare ${BRANCH} with origin/${BRANCH}." >&2
    exit 1
}
case "${_BRANCH_RELATION}" in
    missing)
        echo "ERROR: Remote branch origin/${BRANCH} does not exist; pull aborted." >&2
        exit 1
        ;;
    equal)
        echo "Already up to date."
        echo "###${_NAME} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
        exit 0
        ;;
    ahead)
        echo "Local ${BRANCH} is ahead of origin/${BRANCH}; nothing to pull."
        echo "###${_NAME} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
        exit 0
        ;;
    diverged)
        echo "ERROR: Local ${BRANCH} and origin/${BRANCH} have diverged; refusing automatic rebase." >&2
        echo "Hint:  inspect both sides:" >&2
        echo "       git log --oneline --left-right --graph HEAD...origin/${BRANCH}" >&2
        echo "Hint:  integrate deliberately (configure user.name/user.email first):" >&2
        echo "       git rebase origin/${BRANCH}   # or merge/reset after review" >&2
        exit 1
        ;;
esac

# Only fast-forward pulls are automatic; divergent histories require a manual decision.
_PULL_STATUS=0
_PULL_HELP=$(git pull -h 2>&1 || true)
if [[ "${_PULL_HELP}" == *"--autostash"* ]]; then
    git pull --ff-only --no-rebase --autostash origin "$BRANCH" || _PULL_STATUS=$?
else
    echo "Notice: Git lacks pull --autostash; using the manual stash fallback."
    _pull_with_manual_stash "$BRANCH" --ff-only --no-rebase || _PULL_STATUS=$?
fi

if ((_PULL_STATUS != 0)); then
    echo "ERROR: git pull failed with status ${_PULL_STATUS}." >&2
    exit "${_PULL_STATUS}"
fi

echo "###${_NAME} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
