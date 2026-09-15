#!/usr/bin/env bash
# Install Claude Code (Linux / macOS)：默认联网从官方 GCS 下载最新版安装到 ~/.local/bin，
# 指定 VERSION 时优先用本目录离线包（缺失则联网下载该版本），--npm 走官方 npm 全局安装。
# Usage: bash install.sh [VERSION] [选项]
# 安装布局（与 setup.md 一致）:
#   ~/.local/bin/claude-<ver>   二进制（软链 ~/.local/bin/claude -> claude-<ver>）
#   ~/.claude.json              installMethod=native / autoUpdates=false（幂等合并，保留已有键）

set -euo pipefail

# --- 脚本真实目录（兼容 _claude_code 符号链接引用与 macOS BSD readlink） ---
command -v python3 >/dev/null 2>&1 || { echo "Error: python3 is required" >&2; exit 1; }
SCRIPT_DIR="$(python3 -c 'import os,sys; print(os.path.dirname(os.path.realpath(sys.argv[1])))' "${BASH_SOURCE[0]}")"
PKG_DIR="$SCRIPT_DIR/claude-code"
BIN_DIR="$HOME/.local/bin"
CLAUDE_JSON="$HOME/.claude.json"

GCS_BUCKET="http://storage.googleapis.com/claude-code-dist-86c565f3-f756-42ad-8dfa-d59b1c096819/claude-code-releases"
TMP_DIR=""

NPM=0
CHECK=0
VERSION=""

usage() {
    cat <<EOF
用法: bash install.sh [VERSION] [选项]

  [VERSION]   安装指定版本（本地离线包 $PKG_DIR/<ver> 优先，缺失时联网下载）
              省略则联网从官方 GCS 下载最新版
  --npm       改为 npm 全局安装 @anthropic-ai/claude-code@latest（需联网）
  --check     只读检查安装现状，不安装
  -h, --help  显示帮助
EOF
}

die() { printf '错误: %s\n' "$1" >&2; exit 1; }

cleanup() { [ -n "${TMP_DIR:-}" ] && rm -rf "$TMP_DIR"; }
trap cleanup EXIT

check_status() {
    if command -v claude >/dev/null 2>&1; then
        printf 'claude: %s\n' "$(claude --version 2>/dev/null | head -1 || echo '版本未知')"
        printf '路径:   %s\n' "$(command -v claude)"
    else
        printf 'claude: 未安装（bash install.sh 联网装最新版，或 --npm / 指定离线包版本）\n'
    fi
    printf '本地包: '
    if [ -f "$PKG_DIR/latest.txt" ]; then
        printf '%s（latest.txt）\n' "$(cat "$PKG_DIR/latest.txt")"
    else
        printf '未找到 latest.txt\n'
    fi
    printf '~/.claude.json: %s\n' "$([ -f "$CLAUDE_JSON" ] && echo '存在' || echo '不存在')"
}

# 幂等合并写 ~/.claude.json（保留已有键；缺失时新建）
write_claude_json() {
    python3 - "$CLAUDE_JSON" <<'PY'
import json, os, sys

path = sys.argv[1]
d = {}
if os.path.exists(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        assert isinstance(d, dict)
    except Exception:
        print("错误: %s 不是合法 JSON，请先人工处理" % path, file=sys.stderr)
        sys.exit(2)

d["installMethod"] = "native"
d["autoUpdates"] = False
d["autoUpdatesProtectedForNative"] = True

payload = json.dumps(d, indent=2) + "\n"
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    f.write(payload)
os.replace(tmp, path)
print("已写: %s" % path)
PY
}

# 平台标识（与官方 cc-v20260706.sh 一致：Linux musl 后缀、macOS Rosetta 转 arm64）
detect_platform() {
    local os arch
    case "$(uname -s)" in
        Linux)  os=linux;;
        Darwin) os=darwin;;
        *) die "不支持的系统: $(uname -s)（仅 Linux / macOS，Windows 请用 cc-v20260706.ps1）";;
    esac
    case "$(uname -m)" in
        x86_64|amd64)  arch=x64;;
        arm64|aarch64) arch=arm64;;
        *) die "不支持的架构: $(uname -m)";;
    esac
    if [ "$os" = darwin ] && [ "$arch" = x64 ] \
        && [ "$(sysctl -n sysctl.proc_translated 2>/dev/null || true)" = 1 ]; then
        arch=arm64
    fi
    if [ "$os" = linux ] \
        && { [ -f /lib/libc.musl-x86_64.so.1 ] || [ -f /lib/libc.musl-aarch64.so.1 ] \
             || (ldd /bin/ls 2>&1 || true) | grep -q musl; }; then
        printf 'linux-%s-musl\n' "$arch"
    else
        printf '%s-%s\n' "$os" "$arch"
    fi
}

# 联网取官方最新版本号
fetch_latest_version() {
    local ver
    command -v curl >/dev/null 2>&1 || die "需要 curl 联网获取最新版本（离线安装请指定 VERSION）"
    ver="$(curl -fsSL --connect-timeout 15 --max-time 30 --retry 2 --retry-delay 3 "$GCS_BUCKET/latest")" \
        || die "获取最新版本失败（需联网；离线请先运行 download_all.sh --claude-code 再指定 VERSION）"
    ver="${ver//[[:space:]]/}"
    [[ "$ver" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]] || die "latest 返回值非法: '$ver'"
    printf '%s\n' "$ver"
}

# 从 manifest.json 提取本平台 SHA-256
manifest_checksum() {
    python3 - "$1" "$2" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    manifest = json.load(f)
print((manifest.get("platforms", {}).get(sys.argv[2]) or {}).get("checksum", ""))
PY
}

sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | cut -d' ' -f1
    else
        die "需要 sha256sum 或 shasum 校验下载文件"
    fi
}

# 联网下载指定版本、校验后安装
install_download() {
    local ver="$1" platform expected actual url
    command -v curl >/dev/null 2>&1 || die "需要 curl 下载（离线安装请先运行 download_all.sh --claude-code）"
    platform="$(detect_platform)"
    TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/claude-install.XXXXXX")"

    curl -fL --connect-timeout 15 --max-time 60 --retry 2 --retry-delay 3 \
        -o "$TMP_DIR/manifest.json" "$GCS_BUCKET/$ver/manifest.json" \
        || die "下载 manifest 失败: $GCS_BUCKET/$ver/manifest.json"
    expected="$(manifest_checksum "$TMP_DIR/manifest.json" "$platform")"
    [[ "$expected" =~ ^[a-f0-9]{64}$ ]] || die "版本 $ver 不支持平台 $platform（manifest 中无有效 checksum）"

    url="$GCS_BUCKET/$ver/$platform/claude"
    printf '下载 Claude Code %s（%s）...\n' "$ver" "$platform"
    curl -fL --connect-timeout 15 --max-time 600 --retry 2 --retry-delay 5 \
        -o "$TMP_DIR/claude" "$url" \
        || die "下载二进制失败: $url"

    actual="$(sha256_of "$TMP_DIR/claude")"
    [ "$actual" = "$expected" ] || die "SHA-256 校验失败（期望 $expected，实际 $actual），已丢弃下载文件"

    mkdir -p "$BIN_DIR"
    install -m 755 "$TMP_DIR/claude" "$BIN_DIR/claude-$ver"
    finish_install "$ver"
}

# 本目录离线包安装
install_offline() {
    local ver="$1"
    local src="$PKG_DIR/$ver/claude"
    [ -f "$src" ] || die "离线包不存在: $src（先运行 download_all.sh --claude-code）"
    mkdir -p "$BIN_DIR"
    install -m 755 "$src" "$BIN_DIR/claude-$ver"
    finish_install "$ver"
}

finish_install() {
    local ver="$1"
    ln -sf "$BIN_DIR/claude-$ver" "$BIN_DIR/claude"
    write_claude_json
    echo ""
    echo "Claude Code $ver 安装完成: $BIN_DIR/claude -> claude-$ver"
    if [ ":$PATH:" != *":$BIN_DIR:"* ]; then
        echo "提示: $BIN_DIR 不在 PATH，请先执行: export PATH=\"$BIN_DIR:\$PATH\""
    fi
}

install_npm() {
    command -v npm >/dev/null 2>&1 || die "需要 npm（Node.js）；离线环境请改用本地离线包"
    npm install -g "@anthropic-ai/claude-code@latest"
    echo ""
    echo "Claude Code 已通过 npm 安装；检查: claude --version"
}

main() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --npm)  NPM=1; shift;;
            --check) CHECK=1; shift;;
            -h|--help) usage; exit 0;;
            --*) die "未知选项: $1";;
            *)  [ -z "$VERSION" ] || die "多余参数: $1"; VERSION="$1"; shift;;
        esac
    done

    if [ "$CHECK" = 1 ]; then
        check_status
        return 0
    fi

    if [ "$NPM" = 1 ]; then
        install_npm
        return 0
    fi

    if [ -z "$VERSION" ]; then
        VERSION="$(fetch_latest_version)"
        printf '最新版本: %s\n' "$VERSION"
    fi

    if [ -f "$PKG_DIR/$VERSION/claude" ]; then
        install_offline "$VERSION"
    else
        install_download "$VERSION"
    fi
}

main "$@"
