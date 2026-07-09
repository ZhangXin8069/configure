#!/usr/bin/env bash
# gpull — Pull latest changes from anywhere inside a repo

_NAME=$(basename "$0")
echo "###${_NAME} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

# Locate the git repository root (works from any subdirectory)
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "ERROR: Not inside a git repository."
    exit 1
}
echo "Repo:    ${REPO_ROOT}"

cd "$REPO_ROOT" || exit 1

BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Branch:  ${BRANCH}"

# Fetch all remotes
git fetch --all --prune

# Pull current branch with rebase for a clean linear history
git pull --rebase origin "$BRANCH"

echo "###${_NAME} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
