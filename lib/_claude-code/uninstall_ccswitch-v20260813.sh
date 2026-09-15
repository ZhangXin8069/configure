#!/bin/sh

# Uninstall cc-switch (cc-switch-cli + cc-switch GUI) on Linux/macOS.
# Companion to uninstall_cc-v20260812.sh; see setup.md for install layout.

set -u

usage() {
    cat <<'EOF'
Usage: uninstall_ccswitch-v20260813.sh [OPTIONS]

Uninstall cc-switch (command-line tool and GUI) on Linux / macOS.

Options:
  -h, --help      Show this help message and exit
  -y, --yes       Skip the confirmation prompt
      --purge     Also remove user data: provider/settings directories under
                  ~/.config and ~/.local/share (includes API provider
                  credentials managed by cc-switch)
      --dry-run   Show what would be removed without removing anything

Default behavior:
  Remove the cc-switch CLI binary from ~/.local/bin, shell completions, and
  (with root/sudo) the cc-switch GUI package if installed via dpkg or rpm.
  AppImage installs are not tracked; delete the AppImage file manually.
  User data is kept unless --purge is given. ~/.claude.json and ~/.claude/
  (Claude Code data) are never touched.
EOF
}

PURGE=false
YES=false
DRY_RUN=false

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)    usage; exit 0 ;;
        -y|--yes)     YES=true ;;
        --purge)      PURGE=true ;;
        --dry-run)    DRY_RUN=true ;;
        *)            echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
    esac
    shift
done

BIN_DIR="$HOME/.local/bin"
CLI_BIN="$BIN_DIR/cc-switch"
GUI_NAME="cc-switch"

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

# Shell completions installed by `cc-switch completions install --activate`
completion_candidates() {
    printf '%s\n' \
        "$HOME/.local/share/bash-completion/completions/cc-switch" \
        "$HOME/.local/share/zsh/site-functions/_cc-switch" \
        "$HOME/.config/fish/completions/cc-switch.fish"
}

# Detect GUI packages installed via dpkg or rpm (dynamic, no hardcoded names)
gui_packages() {
    if command -v dpkg >/dev/null 2>&1; then
        dpkg -l 2>/dev/null | awk '$1 == "ii" && tolower($2) ~ /cc-switch/ { print $2 }'
    fi
    if command -v rpm >/dev/null 2>&1; then
        rpm -qa 2>/dev/null | grep -i '^cc-switch'
    fi
}

# Data directories matching cc-switch (case-insensitive) under user config/share
data_dirs() {
    for base in "$HOME/.config" "$HOME/.local/share"; do
        [ -d "$base" ] || continue
        for d in "$base"/*[cC]c-[sS]witch* "$base"/[cC]c_[sS]witch*; do
            if [ -e "$d" ]; then
                echo "$d"
            fi
        done
    done
    if [ -d "$HOME/.cc-switch" ]; then
        echo "$HOME/.cc-switch"
    fi
}

root_cmd() {
    if [ "$(id -u)" -eq 0 ]; then
        :
    elif command -v sudo >/dev/null 2>&1; then
        echo sudo
    else
        echo ""
    fi
}

remove_gui_packages() {
    packages=$(gui_packages)
    [ -n "$packages" ] || return 0

    cmd_prefix=$(root_cmd)
    if [ -z "$cmd_prefix" ] && [ "$(id -u)" -ne 0 ]; then
        echo "GUI package(s) found but neither root nor sudo is available:" >&2
        echo "$packages" >&2
        echo "Run with root privileges or manually: dpkg -r <pkg> / rpm -e <pkg>" >&2
        removed_something=true
        return 0
    fi

    for pkg in $packages; do
        if command -v dpkg >/dev/null 2>&1 && dpkg -l "$pkg" 2>/dev/null | grep -q '^ii'; then
            if [ "$DRY_RUN" = true ]; then
                echo "[dry-run] would run: $cmd_prefix dpkg -r $pkg"
            else
                echo "Removing GUI package: $pkg"
                $cmd_prefix dpkg -r "$pkg"
            fi
        elif command -v rpm >/dev/null 2>&1 && rpm -q "$pkg" >/dev/null 2>&1; then
            if [ "$DRY_RUN" = true ]; then
                echo "[dry-run] would run: $cmd_prefix rpm -e $pkg"
            else
                echo "Removing GUI package: $pkg"
                $cmd_prefix rpm -e "$pkg"
            fi
        fi
        removed_something=true
    done
}

main() {
    echo "=== cc-switch uninstaller ==="

    found=false
    if [ -e "$CLI_BIN" ] || [ -L "$CLI_BIN" ]; then
        found=true
    fi
    for f in $(completion_candidates); do
        if [ -e "$f" ] || [ -L "$f" ]; then
            found=true
            break
        fi
    done
    if [ -n "$(gui_packages)" ]; then
        found=true
    fi
    if [ "$PURGE" = true ] && [ -n "$(data_dirs)" ]; then
        found=true
    fi

    if [ "$found" = false ]; then
        echo "No cc-switch installation found in the standard locations."
        echo "If installed via AppImage, delete the AppImage file manually."
        exit 0
    fi

    scope="CLI binary, completions and GUI package"
    if [ "$PURGE" = true ]; then
        scope="CLI binary, completions, GUI package and user data (provider/settings directories)"
    fi
    confirm "Remove $scope?"

    rm_path "$CLI_BIN" file
    for f in $(completion_candidates); do
        if [ -e "$f" ] || [ -L "$f" ]; then
            rm_path "$f" file
        fi
    done

    remove_gui_packages

    if [ "$PURGE" = true ]; then
        for d in $(data_dirs); do
            rm_path "$d" dir
        done
    fi

    if [ "$PURGE" = false ]; then
        echo ""
        echo "User data kept: cc-switch provider/settings directories under ~/.config and ~/.local/share"
        echo "Re-run with --purge to remove them too."
    fi

    echo ""
    echo "Uninstall complete."
    if [ "$DRY_RUN" = true ]; then
        echo "(dry run - nothing was actually removed)"
    fi
    echo "If the GUI was installed via AppImage, delete the AppImage file manually."
}

main "$@"
