#!/usr/bin/env bash
# Install Codex CLI (Linux / macOS) from GitHub releases into ~/.local/bin
# Usage: bash install.sh [--new] [VERSION]
#        default: 0.154.0 ; --new: 最新版 ; VERSION: 指定版本（优先级高于 --new）
# Env:   CODEX_INSTALL_DIR  安装目录（默认 $HOME/.local/bin）

set -euo pipefail

APP="codex"
DEFAULT_VERSION="0.154.0"
INSTALL_DIR="${CODEX_INSTALL_DIR:-$HOME/.local/bin}"
REPO="https://github.com/openai/codex/releases"

# --- 依赖检查 ---
if ! command -v curl >/dev/null 2>&1; then
    echo "Error: curl is required but not installed" >&2
    exit 1
fi

# --- 平台检测 ---
case "$(uname -s)" in
    Darwin) os="apple-darwin" ;;
    Linux)  os="unknown-linux-musl" ;;
    MINGW*|MSYS*|CYGWIN*)
        echo "Windows: please use install.bat instead" >&2
        exit 1
        ;;
    *)
        echo "Unsupported OS: $(uname -s)" >&2
        exit 1
        ;;
esac

case "$(uname -m)" in
    x86_64|amd64) arch="x86_64" ;;
    aarch64|arm64) arch="aarch64" ;;
    *)
        echo "Unsupported architecture: $(uname -m)" >&2
        exit 1
        ;;
esac

# Rosetta 2: shell 以 x64 运行在 Apple Silicon 上时改用原生 arm64 二进制
if [ "$os" = "apple-darwin" ] && [ "$arch" = "x86_64" ]; then
    if [ "$(sysctl -n sysctl.proc_translated 2>/dev/null)" = "1" ]; then
        arch="aarch64"
    fi
fi

target="$arch-$os"
filename="$APP-$target.tar.gz"

# --- 参数解析 ---
# 无参数 => $DEFAULT_VERSION；--new => 最新版；显式 VERSION 优先级最高
use_latest=0
version=""
for arg in "$@"; do
    case "$arg" in
        --new) use_latest=1 ;;
        -*)    echo "Error: unknown option: $arg" >&2; exit 1 ;;
        *)     version="$arg" ;;
    esac
done

# --- 版本解析 ---
if [ -n "$version" ]; then
    version="${version#v}"
    url="$REPO/download/rust-v${version}/$filename"
elif [ "$use_latest" = 1 ]; then
    url="$REPO/latest/download/$filename"
    tag="$(curl -fsSL "https://api.github.com/repos/openai/codex/releases/latest" \
        | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
    if [ -z "$tag" ]; then
        echo "Error: failed to resolve latest version from GitHub API" >&2
        exit 1
    fi
    version="${tag#rust-v}"
    version="${version#v}"
else
    version="$DEFAULT_VERSION"
    url="$REPO/download/rust-v${version}/$filename"
fi

echo "============================================================"
echo "  Codex installer: $os/$arch"
echo "  version: $version"
echo "  asset:   $filename"
echo "============================================================"

# --- 下载与解压 ---
tmpdir="${TMPDIR:-/tmp}/codex_install_$$"
mkdir -p "$tmpdir"
trap 'rm -rf "$tmpdir"' EXIT

if ! command -v tar >/dev/null 2>&1; then
    echo "Error: tar is required but not installed" >&2
    exit 1
fi

curl -fL --progress-bar -o "$tmpdir/$filename" "$url"
tar -xzf "$tmpdir/$filename" -C "$tmpdir"

if [ ! -f "$tmpdir/$APP-$target" ]; then
    echo "Error: '$APP-$target' not found inside the archive" >&2
    exit 1
fi

mkdir -p "$INSTALL_DIR"
mv "$tmpdir/$APP-$target" "$INSTALL_DIR/$APP"
chmod 755 "$INSTALL_DIR/$APP"

# --- 验证 ---
"$INSTALL_DIR/$APP" --version

# --- PATH 配置 ---
case "${SHELL##*/}" in
    zsh)  profile="$HOME/.zshrc" ;;
    bash) profile="$HOME/.bashrc" ;;
    *)    profile="$HOME/.profile" ;;
esac
line="export PATH=\"$INSTALL_DIR:\$PATH\""
if [ ":$PATH:" != *":$INSTALL_DIR:"* ]; then
    if grep -Fqs "$INSTALL_DIR" "$profile" 2>/dev/null; then
        :
    else
        printf '\n# codex\n%s\n' "$line" >> "$profile"
        echo "PATH 已写入: $profile"
    fi
fi

echo ""
echo "Codex $version 安装完成: $INSTALL_DIR/$APP"
echo "请重启 shell,或立即在当前终端执行:"
echo "  $line"
echo "首次使用请先认证: codex login"