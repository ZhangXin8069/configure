#!/usr/bin/env bash
# Install DeepSeek Harness CLI (dsh) on Linux / macOS via npm global.
# TUI (@deepseek-harness-tui/dsh-tui) is installed alongside by default.
# Usage: bash install.sh [OPTIONS] [VERSION]   (default: latest; VERSION may be an npm dist-tag or exact version)

set -euo pipefail

APP="dsh"
PKG="@deepseek-ai/dsh"
TUI_PKG="${DSH_TUI_PKG:-@deepseek-harness-tui/dsh-tui}"
INSTALL_TUI=1

usage() {
    cat <<EOF
用法: bash install.sh [选项] [VERSION]

  VERSION           dsh 版本或 npm dist-tag（默认 latest，如 next）
  --tui-pkg PKG     TUI 包（默认 $TUI_PKG；环境变量 DSH_TUI_PKG 亦可指定）
  --no-tui          仅安装 dsh 本体，跳过 TUI 配套
  -h, --help        显示本帮助

默认行为: 安装 dsh 后配套安装 TUI（$TUI_PKG），并以 dsh-tui 为默认启动方式。
EOF
}

# --- 参数解析（位置参数 VERSION 保持兼容） ---
version=""
while [ $# -gt 0 ]; do
    case "$1" in
        --no-tui)  INSTALL_TUI=0; shift;;
        --tui-pkg) [ $# -ge 2 ] || { echo "Error: --tui-pkg 需要参数" >&2; exit 2; }; TUI_PKG="$2"; shift 2;;
        -h|--help) usage; exit 0;;
        -*)        echo "Error: 未知选项: $1（用法见 --help）" >&2; exit 2;;
        *)         [ -z "$version" ] || { echo "Error: 多余参数: $1（用法见 --help）" >&2; exit 2; }; version="$1"; shift;;
    esac
done

# --- 依赖检查 ---
if ! command -v node >/dev/null 2>&1; then
    echo "Error: Node.js is required but not installed (recommended ^22.19.0 || >=24.0.0)" >&2
    exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
    echo "Error: npm is required but not installed" >&2
    exit 1
fi
if ! npm --version >/dev/null 2>&1; then
    echo "Error: npm 无法正常运行（系统 npm 与当前 node 不匹配，或 npm 依赖模块缺失）" >&2
    echo "  当前 node: $(command -v node) ($(node -v 2>/dev/null || echo '?'))" >&2
    echo "  当前 npm:  $(command -v npm)" >&2
    echo "  建议: 使用官方 Node 发行包自带的 npm（受支持 Node: ^22.19.0 || >=24.0.0）" >&2
    echo "        检查: type -a node npm（两者应来自同一安装）" >&2
    exit 1
fi

# --- Node 版本提示（上游仓库 engines: ^22.19.0 || >=24.0.0；仅告警不阻断） ---
node_version="$(node -v 2>/dev/null | sed 's/^v//')"
node_major="${node_version%%.*}"
node_minor="$(printf '%s' "${node_version#*.}" | cut -d. -f1)"
if [ -n "$node_major" ] && [ -n "$node_minor" ]; then
    if [ "$node_major" -lt 22 ] \
        || { [ "$node_major" -eq 22 ] && [ "$node_minor" -lt 19 ]; } \
        || [ "$node_major" -eq 23 ]; then
        echo "Warning: Node.js $node_version 不在推荐范围 (^22.19.0 || >=24.0.0)，dsh 可能无法运行" >&2
    fi
fi

# --- 版本解析 ---
spec="$PKG"
if [ -n "$version" ]; then
    spec="$PKG@${version#v}"
else
    version="latest"
fi

echo "============================================================"
echo "  DeepSeek Harness installer: $(uname -s)/$(uname -m)"
echo "  package: $spec"
[ "$INSTALL_TUI" = 1 ] && echo "  tui:     $TUI_PKG（--no-tui 可跳过）"
[ "$version" = "latest" ] && echo "  dist-tag: latest（上游当前为 developer preview，latest 可能指向 rc 版本）"
echo "============================================================"

resolved="$(npm view "$spec" version 2>/dev/null | tail -1 || true)"
[ -n "$resolved" ] && echo "  解析版本: $resolved"

# --- 安装 ---
# npm 11+ 默认拦截依赖的 install-time 脚本（node-pty/koffi 等原生依赖需要执行）；
# 包名列表来自 npm 对 @deepseek-ai/dsh 当前版本的 install-scripts 告警（含 TUI 的 sharp 可选依赖），上游更换依赖时需同步。
# 老版本 npm 无该策略与 flag，通过 help 输出做能力探测后按需传入。
npm_allow_scripts=""
if npm install --help 2>/dev/null | grep -q -- '--allow-scripts'; then
    npm_allow_scripts="--allow-scripts=@deepseek-ai/dsh-subprocess-local,koffi,node-pty,@google/genai,protobufjs,sharp"
fi
if ! npm install -g ${npm_allow_scripts:+"$npm_allow_scripts"} "$spec"; then
    echo "Error: npm install failed（全局目录无写权限时可改用: npm install -g $spec --prefix \"\$HOME/.local\" 并自行加入 PATH）" >&2
    exit 1
fi

# --- TUI 配套安装（默认；--no-tui 跳过） ---
tui_installed=0
if [ "$INSTALL_TUI" = 1 ]; then
    echo ""
    echo "安装 TUI: $TUI_PKG ..."
    if npm install -g ${npm_allow_scripts:+"$npm_allow_scripts"} "$TUI_PKG"; then
        tui_installed=1
    else
        echo "Warning: TUI 安装失败（dsh 本体不受影响）；稍后可手动重试: npm install -g $TUI_PKG" >&2
    fi
fi

# --- 验证与 PATH 配置 ---
BIN="$(command -v "$APP" 2>/dev/null || true)"

if [ -z "$BIN" ]; then
    npm_bin_dir="$(npm prefix -g 2>/dev/null || true)/bin"
    if [ -n "${npm_bin_dir%/bin}" ] && [ -x "$npm_bin_dir/$APP" ]; then
        BIN="$npm_bin_dir/$APP"
        case "${SHELL##*/}" in
            zsh)  profile="$HOME/.zshrc" ;;
            bash) profile="$HOME/.bashrc" ;;
            *)    profile="$HOME/.profile" ;;
        esac
        line="export PATH=\"$npm_bin_dir:\$PATH\""
        if [ ":$PATH:" != *":$npm_bin_dir:"* ]; then
            if grep -Fqs "$npm_bin_dir" "$profile" 2>/dev/null; then
                :
            else
                printf '\n# deepseek-harness\n%s\n' "$line" >> "$profile"
                echo "PATH 已写入: $profile"
            fi
        fi
    else
        echo "Error: $APP not found after install (npm global bin 不在 PATH)" >&2
        exit 1
    fi
fi

echo ""
if ! "$BIN" --version; then
    echo "Error: '$BIN --version' 执行失败，安装可能不完整（Node 版本不符或 npm 依赖缺失）" >&2
    exit 1
fi

# --- TUI 命令定位（dsh 与 TUI 同属 npm global bin） ---
TUI_BIN=""
if [ "$tui_installed" = 1 ]; then
    TUI_BIN="$(command -v dsh-tui 2>/dev/null || true)"
    if [ -z "$TUI_BIN" ]; then
        tui_bin_dir="$(npm prefix -g 2>/dev/null || true)/bin"
        if [ -n "${tui_bin_dir%/bin}" ] && [ -x "$tui_bin_dir/dsh-tui" ]; then
            TUI_BIN="$tui_bin_dir/dsh-tui"
        fi
    fi
    [ -n "$TUI_BIN" ] || echo "Warning: 未找到 dsh-tui（npm global bin 可能不在 PATH；重启 shell 后重试）" >&2
fi

echo ""
echo "DeepSeek Harness 安装完成: $BIN"
if [ -n "$TUI_BIN" ]; then
    echo "启动 TUI（默认）: dsh-tui   （短命令: dst；首次运行自动初始化 dsh-tui profile）"
    if ! command -v pnpm >/dev/null 2>&1; then
        echo "  注意: 首次初始化需 pnpm（当前未检测到）: npm install -g pnpm  或  corepack enable pnpm"
    fi
elif [ "$INSTALL_TUI" = 1 ]; then
    echo "TUI 未就绪；稍后可执行: npm install -g $TUI_PKG && dsh-tui"
fi
echo "启动 Web UI:  dsh web      （默认 http://127.0.0.1:3080）"
echo "无头模式:     dsh --profile headless \"<任务>\""
echo "首次使用请配置 DeepSeek API key: TUI 内 /settings 或 dsh web → Settings → Models"
echo "  或运行同目录: bash config.sh --key-from-env --apply"
if [ "$BIN" != "$(command -v "$APP" 2>/dev/null || true)" ]; then
    echo "请重启 shell,或立即在当前终端执行: export PATH=\"$(dirname "$BIN"):\$PATH\""
fi
