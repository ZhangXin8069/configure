#!/usr/bin/env bash
# ccgpush.sh — git push with auto-generated Claude Code annotated tag
#
# Tag convention: stab<N> (sequential), with a detailed English changelog
# as the tag annotation.
#
# Usage:
#   ccgpush.sh [tag-message]
#     - If message is provided, uses it as the tag annotation
#     - If omitted, auto-generates a changelog from recent commit messages
#     - If --amend is passed, re-tags the last tag instead of creating a new one
#
# Examples:
#   ccgpush.sh "optimize env.sh, extract git aliases"
#   ccgpush.sh                    # auto-generate changelog from git log
#   ccgpush.sh --amend "fix typo" # amend last tag annotation

set -e

_PATH=$(cd "$(dirname "$0")" && pwd)
_NAME=$(basename "$0")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

AMEND=false
TAG_MSG=""

# Parse arguments
for arg in "$@"; do
    case "$arg" in
        --amend) AMEND=true ;;
        *) [ -z "$TAG_MSG" ] && TAG_MSG="$arg" || TAG_MSG="$TAG_MSG $arg" ;;
    esac
done

# --- Determine tag annotation ---
if [ -z "$TAG_MSG" ]; then
    # Auto-generate changelog from recent commits since last tag
    LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
    if [ -n "$LAST_TAG" ]; then
        COMMITS_SINCE=$(git log "${LAST_TAG}..HEAD" --oneline --no-merges 2>/dev/null | head -10)
    else
        COMMITS_SINCE=$(git log --oneline --no-merges -10 2>/dev/null)
    fi

    if [ -z "$COMMITS_SINCE" ]; then
        TAG_MSG="Automatic tag — no new commits since last tag ($(date "+%Y-%m-%d %H:%M:%S"))"
    else
        # Build a bullet-point changelog from commit messages
        CHANGELOG=""
        while IFS= read -r line; do
            COMMIT_HASH=$(echo "$line" | awk '{print $1}')
            COMMIT_MSG=$(echo "$line" | cut -d' ' -f2-)
            CHANGELOG="${CHANGELOG}  - ${COMMIT_MSG} (${COMMIT_HASH})
"
        done <<< "$COMMITS_SINCE"
        TAG_MSG="Changes in this tag:
${CHANGELOG}"
    fi
fi

# --- Determine tag number ---
CLAUDE_SIG="Claude Code"
TAG_PREFIX="stab"

# Get the latest stab<N> tag number
LAST_STAB=$(git tag -l "${TAG_PREFIX}*" --sort=-v:refname | head -1)

if [ -z "$LAST_STAB" ]; then
    NEW_NUM=0
else
    # Extract number from stab<N>
    LAST_NUM=$(echo "$LAST_STAB" | sed "s/^${TAG_PREFIX}//")
    NEW_NUM=$((LAST_NUM + 1))
fi

NEW_TAG="${TAG_PREFIX}${NEW_NUM}"

# Build the full tag annotation (English only, no tag-name prefix)
TAG_DATE=$(date "+%Y-%m-%d %H:%M:%S")
if [ -n "$LAST_STAB" ]; then
    TAG_MESSAGE="Release ${NEW_TAG}

Changelog since ${LAST_STAB}:
${TAG_MSG}

Tag created by ${CLAUDE_SIG} on ${TAG_DATE}"
else
    TAG_MESSAGE="Release ${NEW_TAG} (initial)

${TAG_MSG}

Tag created by ${CLAUDE_SIG} on ${TAG_DATE}"
fi

# --- Handle amend mode ---
if $AMEND; then
    if [ -z "$LAST_STAB" ]; then
        echo "No existing tag to amend."
        exit 1
    fi
    NEW_TAG="$LAST_STAB"
    PREV_STAB=$(git tag -l "${TAG_PREFIX}*" --sort=-v:refname | sed -n '2p')
    if [ -n "$PREV_STAB" ]; then
        TAG_MESSAGE="Release ${NEW_TAG} (amended)

Changelog since ${PREV_STAB}:
${TAG_MSG}

Tag updated by ${CLAUDE_SIG} on ${TAG_DATE}"
    else
        TAG_MESSAGE="Release ${NEW_TAG} (amended, initial)

${TAG_MSG}

Tag updated by ${CLAUDE_SIG} on ${TAG_DATE}"
    fi
    echo "Amending tag: ${NEW_TAG}"
    git tag -d "$NEW_TAG" 2>/dev/null || true
    git push origin ":refs/tags/${NEW_TAG}" 2>/dev/null || true
fi

# --- Confirm and create tag ---
echo ""
echo "  Tag:     ${NEW_TAG}"
echo "  Message:"
echo "${TAG_MESSAGE}"
echo ""

if [ -t 0 ]; then
    read -p "Proceed? [Y/n] " -r REPLY
    REPLY=${REPLY:-Y}
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# Create annotated tag
git tag -a "$NEW_TAG" -m "$TAG_MESSAGE"

# --- Commit and push ---
# Stage all changes
git add .gitignore 2>/dev/null || true
git add -A

# Commit with timestamp (only if there are staged changes)
if ! git diff --cached --quiet 2>/dev/null; then
    COMMIT_MSG="$(date "+%Y-%m-%d-%H-%M-%S") [${CLAUDE_SIG}]"
    git commit -m "$COMMIT_MSG"
else
    echo "No changes to commit, pushing tags only."
fi

# Push commits and tags
git push origin --tags
git push

echo ""
echo "✅ Pushed: ${NEW_TAG}"
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
