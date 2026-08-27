#!/usr/bin/env bash
# Install Claude Code (Linux / macOS) 从本目录离线安装包安装到 ~/.local/bin，
# 或加 --npm 走官方 npm 全局安装。
# Usage: bash install.sh [VERSION] [选项]   （默认版本读 claude-code/latest.txt）
# 离线安装布局（与 setup.md 一致）:
#   ~/.local/bin/claude-<ver>   二进制（软链 ~/.local/bin/claude -> claude-<ver>）
#   ~/.claude.json              installMethod=native / autoUpdates=false（幂等合并，保留已有键）

set -euo pipefail

# --- 脚本真实目录（兼容 _claude_code 符号链接引用与 macOS BSD readlink） ---
command -v python3 >/dev/null 2>&1 || { echo "Error: python3 is required" >&2; exit 1; }
SCRIPT_DIR="$(python3 -c 'import os,sys; print(os.path.dirname(os.path.realpath(sys.argv[1])))' "${BASH_SOURCE[0]}")"
PKG_DIR="$SCRIPT_DIR/claude-code"
BIN_DIR="$HOME/.local/bin"
CLAUDE_JSON="$HOME/.claude.json"

NPM=0
CHECK=0
VERSION=""

usage() {
    cat <<EOF
用法: bash install.sh [VERSION] [选项]

  [VERSION]   离线包版本（默认读 $PKG_DIR/latest.txt）
  --npm       改为 npm 全局安装 @anthropic-ai/claude-code@latest（需联网）
  --check     只读检查安装现状，不安装
  -h, --help  显示帮助
EOF
}

die() { printf '错误: %s\n' "$1" >&2; exit 1; }

check_status() {
    if command -v claude >/dev/null 2>&1; then
        printf 'claude: %s\n' "$(claude --version 2>/dev/null | head -1 || echo '版本未知')"
        printf '路径:   %s\n' "$(command -v claude)"
    else
        printf 'claude: 未安装（离线包路径 %s，或运行 bash install.sh --npm）\n' "$PKG_DIR"
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

install_offline() {
    local ver="$1"
    local src="$PKG_DIR/$ver/claude"
    [ -f "$src" ] || die "离线包不存在: $src（先运行 download_all.sh --claude-code）"
    command -v curl >/dev/null 2>&1 || true
    mkdir -p "$BIN_DIR"
    install -m 755 "$src" "$BIN_DIR/claude-$ver"
    ln -sf "$BIN_DIR/claude-$ver" "$BIN_DIR/claude"
    write_claude_json
    echo ""
    echo "Claude Code $ver 安装完成: $BIN_DIR/claude -> claude-$ver"
    if [ ":$PATH:" != *":$BIN_DIR:"* ]; then
        echo "提示: $BIN_DIR 不在 PATH，请先执行: export PATH=\"$BIN_DIR:\$PATH\""
    fi
}

install_npm() {
    command -v npm >/dev/null 2>&1 || die "需要 npm（Node.js）；离线环境请改用默认离线安装"
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
        [ -f "$PKG_DIR/latest.txt" ] || die "未指定版本且 latest.txt 缺失；用法: bash install.sh <VERSION>"
        VERSION="$(cat "$PKG_DIR/latest.txt")"
    fi
    install_offline "$VERSION"
}

main "$@"