#!/usr/bin/env bash
# gback — Force local repo to exactly match its remote, discarding ALL local changes
# (uncommitted edits, untracked/ignored files, local-only commits, stale tags)

_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

# Locate the git repository root (works from any subdirectory)
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "ERROR: Not inside a git repository."
    exit 1
}
echo "Repo:    ${REPO_ROOT}"
cd "$REPO_ROOT" || exit 1

BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Branch:  ${BRANCH}"

# Fetch latest state from all remotes (prune deleted remote branches and tags)
git fetch --all --prune --prune-tags || {
    echo "ERROR: git fetch failed."
    exit 1
}

if [[ "${BRANCH}" == "HEAD" ]]; then
    echo "ERROR: Detached HEAD; check out a branch first."
    exit 1
fi

# Resolve upstream; refuse to proceed if none exists
UPSTREAM=$(git rev-parse --abbrev-ref "${BRANCH}@{upstream}" 2>/dev/null) || {
    echo "ERROR: Branch '${BRANCH}' has no upstream; cannot sync to remote."
    exit 1
}
echo "Upstream: ${UPSTREAM}"

# Report local-only commits that will be discarded
UNPUSHED=$(git log --oneline --reverse "${UPSTREAM}..${BRANCH}" 2>/dev/null)
if [[ -n "${UNPUSHED}" ]]; then
    echo "Discarding local-only commits:"
    echo "${UNPUSHED}"
fi

# Preview untracked/ignored files that will be removed
TO_CLEAN=$(git clean -ndx | wc -l)
echo "Removing ${TO_CLEAN} untracked or ignored file(s):"
git clean -ndx | sed 's/^Would remove /  /' | head -20

# Force branch pointer and working tree to exactly match remote
git reset --hard "${UPSTREAM}"
git clean -fdx
git checkout -B "${BRANCH}" "${UPSTREAM}"

# Verify: working tree clean, local HEAD == remote HEAD
if [[ -z "$(git status --porcelain)" ]]; then
    echo "OK: working tree clean"
else
    echo "WARNING: working tree still dirty:"
    git status --porcelain
fi
if [[ "$(git rev-parse HEAD)" == "$(git rev-parse "${UPSTREAM}")" ]]; then
    echo "OK: local HEAD matches ${UPSTREAM}"
else
    echo "WARNING: local HEAD differs from ${UPSTREAM}"
fi
echo "HEAD:    $(git log --oneline -1)"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
