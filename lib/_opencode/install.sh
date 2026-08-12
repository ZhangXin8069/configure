#!/usr/bin/env bash
# Install opencode (Linux / macOS) from GitHub releases into ~/.opencode/bin
# Usage: bash install.sh [VERSION]   (default: latest)

set -euo pipefail

APP="opencode"
INSTALL_DIR="$HOME/.opencode/bin"
REPO="https://github.com/anomalyco/opencode/releases"

# --- 依赖检查 ---
if ! command -v curl >/dev/null 2>&1; then
    echo "Error: curl is required but not installed" >&2
    exit 1
fi

# --- 平台检测 ---
case "$(uname -s)" in
    Darwin) os="darwin" ;;
    Linux)  os="linux" ;;
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
    x86_64|amd64) arch="x64" ;;
    aarch64|arm64) arch="arm64" ;;
    *)
        echo "Unsupported architecture: $(uname -m)" >&2
        exit 1
        ;;
esac

# Rosetta 2: shell 以 x64 运行在 Apple Silicon 上时改用原生 arm64 二进制
if [ "$os" = "darwin" ] && [ "$arch" = "x64" ]; then
    if [ "$(sysctl -n sysctl.proc_translated 2>/dev/null)" = "1" ]; then
        arch="arm64"
    fi
fi

target="$os-$arch"

# 无 AVX2 的 x64 CPU 需要 baseline 构建（先 baseline 后 musl，匹配资产命名）
if [ "$arch" = "x64" ]; then
    avx2=0
    if [ "$os" = "linux" ]; then
        grep -qwi avx2 /proc/cpuinfo 2>/dev/null && avx2=1
    else
        [ "$(sysctl -n hw.optional.avx2_0 2>/dev/null)" = "1" ] && avx2=1
    fi
    if [ "$avx2" = "0" ]; then
        target="$target-baseline"
    fi
fi

# musl libc (Alpine 等)
if [ "$os" = "linux" ]; then
    if [ -f /etc/alpine-release ] || { command -v ldd >/dev/null 2>&1 && ldd --version 2>&1 | grep -qi musl; }; then
        target="$target-musl"
    fi
fi

ext=".zip"
[ "$os" = "linux" ] && ext=".tar.gz"
filename="$APP-$target$ext"

# --- 版本解析 ---
version="${1:-}"
if [ -z "$version" ]; then
    url="$REPO/latest/download/$filename"
    tag="$(curl -fsSL "https://api.github.com/repos/anomalyco/opencode/releases/latest" \
        | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"v\([^"]*\)".*/\1/p')"
    if [ -z "$tag" ]; then
        echo "Error: failed to resolve latest version from GitHub API" >&2
        exit 1
    fi
    version="${tag#v}"
else
    version="${version#v}"
    url="$REPO/download/v${version}/$filename"
fi

echo "============================================================"
echo "  OpenCode installer: $os/$arch"
echo "  version: $version"
echo "  asset:   $filename"
echo "============================================================"

# --- 下载与解压 ---
tmpdir="${TMPDIR:-/tmp}/opencode_install_$$"
mkdir -p "$tmpdir"
trap 'rm -rf "$tmpdir"' EXIT

if [ "$os" = "linux" ] && ! command -v tar >/dev/null 2>&1; then
    echo "Error: tar is required but not installed" >&2
    exit 1
fi
if [ "$os" = "darwin" ] && ! command -v unzip >/dev/null 2>&1; then
    echo "Error: unzip is required but not installed" >&2
    exit 1
fi

curl -fL --progress-bar -o "$tmpdir/$filename" "$url"

if [ "$os" = "linux" ]; then
    tar -xzf "$tmpdir/$filename" -C "$tmpdir"
else
    unzip -q "$tmpdir/$filename" -d "$tmpdir"
fi

if [ ! -f "$tmpdir/opencode" ]; then
    echo "Error: 'opencode' not found inside the archive" >&2
    exit 1
fi

mkdir -p "$INSTALL_DIR"
mv "$tmpdir/opencode" "$INSTALL_DIR/opencode"
chmod 755 "$INSTALL_DIR/opencode"

# --- 验证 ---
"$INSTALL_DIR/opencode" --version

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
        printf '\n# opencode\n%s\n' "$line" >> "$profile"
        echo "PATH 已写入: $profile"
    fi
fi

echo ""
echo "OpenCode $version 安装完成: $INSTALL_DIR/opencode"
echo "请重启 shell,或立即在当前终端执行:"
echo "  $line"
