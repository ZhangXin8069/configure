#!/bin/sh

# Uninstall Claude Code (native installer layout) on Linux/macOS.
# Companion to cc-v20260706.sh.

set -u

usage() {
    cat <<'EOF'
Usage: uninstall_cc-v20260812.sh [OPTIONS]

Uninstall Claude Code on Linux / macOS.

Options:
  -h, --help      Show this help message and exit
  -y, --yes       Skip the confirmation prompt
      --npm       Also uninstall the npm-installed @anthropic-ai/claude-code
      --purge     Also remove user data: ~/.claude.json and ~/.claude/
                  (includes credentials and settings)
      --dry-run   Show what would be removed without removing anything

Default behavior:
  Remove the claude binary and claude-<version> binaries from ~/.local/bin,
  the version cache ~/.local/share/claude, state and cache directories, and
  the PATH export line added to shell startup files. User data is kept
  unless --purge is given.
EOF
}

PURGE=false
YES=false
DRY_RUN=false
REMOVE_NPM=false

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)    usage; exit 0 ;;
        -y|--yes)     YES=true ;;
        --purge)      PURGE=true ;;
        --npm)        REMOVE_NPM=true ;;
        --dry-run)    DRY_RUN=true ;;
        *)            echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
    esac
    shift
done

BIN_DIR="$HOME/.local/bin"
LINK_PATH="$BIN_DIR/claude"
INSTALL_BASE="$HOME/.local/share/claude"
CONFIG_PATH="$HOME/.claude.json"
CLAUDE_DIR="$HOME/.claude"
STATE_DIR="$HOME/.local/state/claude"
CACHE_DIR="$HOME/.cache/claude"
PATH_EXPORT='export PATH="$HOME/.local/bin:$PATH"'
NPM_PACKAGE="@anthropic-ai/claude-code"

removed_something=false

rm_path() {
    path="$1"
    type="$2"

    if [ ! -e "$path" ] && [ ! -L "$path" ]; then
        return 0
    fi

    if [ "$DRY_RUN" = true ]; then
        echo "[dry-run] would remove: $path"
        removed_something=true
        return 0
    fi

    if [ "$type" = "dir" ]; then
        rm -rf "$path"
    else
        rm -f "$path"
    fi
    echo "removed: $path"
    removed_something=true
}

strip_path_export() {
    file="$1"

    if [ ! -f "$file" ]; then
        return 0
    fi
    if ! grep -Fqs "$PATH_EXPORT" "$file"; then
        return 0
    fi

    if [ "$DRY_RUN" = true ]; then
        echo "[dry-run] would remove PATH export from: $file"
        removed_something=true
        return 0
    fi

    tmp=$(mktemp) || return 1
    grep -Fv "$PATH_EXPORT" "$file" > "$tmp"
    cat "$tmp" > "$file"
    rm -f "$tmp"
    echo "removed PATH export from: $file"
    removed_something=true
}

confirm() {
    prompt="$1"

    if [ "$YES" = true ] || [ "$DRY_RUN" = true ]; then
        return 0
    fi

    if ! exec 3<> /dev/tty 2>/dev/null; then
        echo "Not a terminal and -y was not given; aborting." >&2
        exit 1
    fi

    printf '%s [y/N] ' "$prompt" >&3
    IFS= read -r reply <&3
    exec 3>&-

    case "$reply" in
        y|Y|yes|YES) return 0 ;;
        *) echo "Aborted."; exit 0 ;;
    esac
}

handle_npm() {
    if ! command -v npm >/dev/null 2>&1; then
        return 0
    fi
    if ! npm ls -g --depth=0 "$NPM_PACKAGE" >/dev/null 2>&1; then
        return 0
    fi

    echo "Found npm-installed Claude Code ($NPM_PACKAGE)."
    if [ "$REMOVE_NPM" = true ]; then
        if [ "$DRY_RUN" = true ]; then
            echo "[dry-run] would run: npm uninstall -g $NPM_PACKAGE"
            removed_something=true
            return 0
        fi
        echo "Running: npm uninstall -g $NPM_PACKAGE"
        npm uninstall -g "$NPM_PACKAGE"
    else
        echo "Run 'npm uninstall -g $NPM_PACKAGE' or re-run with --npm to remove it."
    fi
}

main() {
    echo "=== Claude Code uninstaller ==="

    binaries_found=false
    if [ -e "$LINK_PATH" ] || [ -L "$LINK_PATH" ]; then
        binaries_found=true
    fi
    for f in "$BIN_DIR"/claude-*; do
        if [ -e "$f" ] || [ -L "$f" ]; then
            binaries_found=true
            break
        fi
    done
    if [ -d "$INSTALL_BASE" ]; then
        binaries_found=true
    fi

    data_found=false
    if [ "$PURGE" = true ]; then
        if [ -e "$CONFIG_PATH" ] || [ -e "$CLAUDE_DIR" ]; then
            data_found=true
        fi
    fi

    if [ "$binaries_found" = false ] && [ "$data_found" = false ]; then
        echo "No Claude Code installation found in the standard locations."
        handle_npm
        exit 0
    fi

    scope="binaries, version files, state and cache"
    if [ "$PURGE" = true ]; then
        scope="binaries, version files, state, cache and user data (~/.claude.json, ~/.claude)"
    fi
    confirm "Remove $scope?"

    rm_path "$LINK_PATH" file
    for f in "$BIN_DIR"/claude-*; do
        if [ -e "$f" ] || [ -L "$f" ]; then
            rm_path "$f" file
        fi
    done
    rm_path "$INSTALL_BASE" dir
    rm_path "$STATE_DIR" dir
    rm_path "$CACHE_DIR" dir

    case "$(uname -s)" in
        Darwin)
            rm_path "$HOME/Library/Caches/claude" dir
            rm_path "$HOME/Library/Logs/claude" dir
            ;;
    esac

    if [ "$PURGE" = true ]; then
        rm_path "$CONFIG_PATH" file
        rm_path "$CLAUDE_DIR" dir
    fi

    strip_path_export "$HOME/.zshrc"
    strip_path_export "$HOME/.bashrc"
    strip_path_export "$HOME/.profile"
    strip_path_export "$HOME/.zprofile"
    strip_path_export "$HOME/.bash_profile"

    if [ "$DRY_RUN" = false ]; then
        rmdir "$HOME/.local/state" 2>/dev/null || true
        rmdir "$HOME/.cache" 2>/dev/null || true
        rmdir "$HOME/.local/share" 2>/dev/null || true
    fi

    if [ "$PURGE" = false ]; then
        echo ""
        echo "User data kept: $CONFIG_PATH, $CLAUDE_DIR"
        echo "Re-run with --purge to remove them too."
    fi

    handle_npm

    echo ""
    echo "Uninstall complete."
    if [ "$DRY_RUN" = true ]; then
        echo "(dry run - nothing was actually removed)"
    fi
    echo "Restart your shell for PATH changes to take effect."
}

main "$@"
