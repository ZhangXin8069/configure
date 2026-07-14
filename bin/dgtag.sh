#!/usr/bin/env bash
# dgtag — Delete all local git tags in the current repository

_NAME=$(basename "$0")
echo "###${_NAME} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

# Locate the git repository root (works from any subdirectory)
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "ERROR: Not inside a git repository."
    exit 1
}
echo "Repo:    ${REPO_ROOT}"

cd "$REPO_ROOT" || exit 1

# List all local tags
TAGS=$(git tag)

if [ -z "$TAGS" ]; then
    echo "No local tags found."
else
    echo "Deleting local tags..."
    echo "$TAGS" | while read -r tag; do
        echo "  deleting: $tag"
    done
    git tag -d $TAGS
    echo "All local tags deleted."
fi

echo "###${_NAME} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
