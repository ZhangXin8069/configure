#!/usr/bin/env bash
# Remove macOS Gatekeeper quarantine attribute from common user directories
# Usage: xxattr.sh [directories...]
#   If no arguments given, defaults to standard macOS user folders.

set -e

if [ "$(uname -s)" != "Darwin" ]; then
    echo "xxattr.sh: macOS only (uses xattr)"
    exit 1
fi

if [ $# -gt 0 ]; then
    TARGETS=("$@")
else
    TARGETS=(
        "${HOME}/Desktop"
        "${HOME}/Documents"
        "${HOME}/Downloads"
        "${HOME}/Pictures"
        "${HOME}/Music"
        "${HOME}/Movies"
        "${HOME}/Draft"
        "${HOME}/Favorites"
    )
fi

for dir in "${TARGETS[@]}"; do
    if [ -d "$dir" ]; then
        echo "Clearing quarantine on: $dir"
        xattr -dr com.apple.quarantine "$dir" 2>/dev/null || true
    else
        echo "Skipping (not found): $dir"
    fi
done

echo "Done."
