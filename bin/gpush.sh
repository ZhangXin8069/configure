#!/usr/bin/env bash
# gpush — Stage all changes, commit, and push from anywhere inside a repo

_NAME=$(basename "$0")
echo "###${_NAME} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

# Locate the git repository root (works from any subdirectory)
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "ERROR: Not inside a git repository."
    exit 1
}
echo "Repo:    ${REPO_ROOT}"

cd "$REPO_ROOT" || exit 1

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
