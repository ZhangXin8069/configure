#!/usr/bin/env bash
# _gpush-claude_code.sh — git push with auto-generated Claude Code tag
#
# Tag convention: stab<N> follow stab<N-1>, <changelog> (Claude Code)
#
# Usage:
#   _gpush-claude_code.sh [tag-message]
#     - If message is provided, uses it as the tag annotation
#     - If omitted, auto-generates from recent commit messages
#     - If --amend is passed, re-tags the last tag instead of creating a new one
#
# Examples:
#   _gpush-claude_code.sh "optimize env.sh, extract git aliases"
#   _gpush-claude_code.sh                    # auto-generate from git log
#   _gpush-claude_code.sh --amend "fix typo" # amend last tag message

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

# --- Determine tag message ---
if [ -z "$TAG_MSG" ]; then
    # Auto-generate from recent commits since last tag
    LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
    if [ -n "$LAST_TAG" ]; then
        COMMITS_SINCE=$(git log "${LAST_TAG}..HEAD" --oneline --no-merges 2>/dev/null | head -10)
    else
        COMMITS_SINCE=$(git log --oneline --no-merges -10 2>/dev/null)
    fi

    if [ -z "$COMMITS_SINCE" ]; then
        TAG_MSG="auto-tag: $(date "+%Y-%m-%d-%H-%M-%S")"
    else
        # Build summary from commit messages
        SUMMARY=$(echo "$COMMITS_SINCE" | head -5 | cut -d' ' -f2- | tr '\n' '; ' | sed 's/; $//')
        TAG_MSG="${SUMMARY:0:200}"  # Truncate to 200 chars
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

# Build the full tag message
if [ -n "$LAST_STAB" ]; then
    TAG_MESSAGE="${NEW_TAG} follow ${LAST_STAB}, ${TAG_MSG} (${CLAUDE_SIG})"
else
    TAG_MESSAGE="${NEW_TAG} init, ${TAG_MSG} (${CLAUDE_SIG})"
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
        TAG_MESSAGE="${NEW_TAG} follow ${PREV_STAB}, ${TAG_MSG} (${CLAUDE_SIG})"
    else
        TAG_MESSAGE="${NEW_TAG} init, ${TAG_MSG} (${CLAUDE_SIG})"
    fi
    echo "Amending tag: ${NEW_TAG}"
    git tag -d "$NEW_TAG" 2>/dev/null || true
    git push origin ":refs/tags/${NEW_TAG}" 2>/dev/null || true
fi

# --- Confirm and create tag ---
echo ""
echo "  Tag:     ${NEW_TAG}"
echo "  Message: ${TAG_MESSAGE}"
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
echo "✅ Pushed: ${NEW_TAG} — ${TAG_MSG}"
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
