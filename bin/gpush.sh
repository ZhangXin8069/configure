#!/usr/bin/env bash
# gpush — Stage all changes, commit, and push from anywhere inside a repo

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

# Stage everything (including deletions) from repo root
git add -A

# Skip commit if nothing staged
if git diff --cached --quiet; then
    echo "Nothing to commit."
else
    COMMIT_MSG="$(date "+%Y-%m-%d-%H-%M-%S")"
    git commit -m "$COMMIT_MSG"
fi

# Push current branch to its upstream (or origin)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
git push origin "$BRANCH"

# Push tags
git push origin --tags

echo "###${_NAME} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
