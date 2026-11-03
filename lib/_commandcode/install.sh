#!/usr/bin/env bash
# Install Command Code on Linux, macOS, or WSL through the official npm package.
# Usage: bash install.sh [VERSION|--new]
# Env:   COMMAND_CODE_INSTALL_DIR  安装目录（默认 $HOME/.local/bin）

set -euo pipefail

package_name="command-code"
default_version="1.88.2"
install_dir="${COMMAND_CODE_INSTALL_DIR:-${HOME:?HOME is required}/.local/bin}"
install_prefix="$(dirname -- "$install_dir")"

usage() {
    cat <<EOF
用法: bash install.sh [VERSION|--new]

  VERSION       安装指定版本（默认: $default_version）
  --new         安装 npm 上的最新版本
  -h, --help    显示帮助

要求:
  Node.js >= 22、npm、可访问 npm registry。
安装目录:
  $install_dir

环境变量:
  COMMAND_CODE_INSTALL_DIR  覆盖安装目录

安装范围:
  使用 npm --global --prefix；仅在安装目录不在 PATH 时更新当前 shell 配置。
EOF
}

die() {
    printf '错误: %s\n' "$1" >&2
    exit 1
}

case "${1:-}" in
    -h|--help)
        usage
        exit 0
        ;;
esac

if [ "$#" -gt 1 ]; then
    die "最多接受一个版本参数"
fi

case "$(uname -s)" in
    Linux|Darwin) ;;
    MINGW*|MSYS*|CYGWIN*)
        die "原生 Windows 请运行 install.bat"
        ;;
    *)
        die "不支持的系统: $(uname -s)"
        ;;
esac

command -v node >/dev/null 2>&1 || die "未找到 node；请先安装 Node.js 22 或更新版本"
command -v npm >/dev/null 2>&1 || die "未找到 npm；请先安装 Node.js 22 或更新版本"

node_major="$(node -p 'Number(process.versions.node.split(".")[0])')"
if [ "$node_major" -lt 22 ]; then
    die "当前 Node.js 为 $(node --version)，Command Code 要求 Node.js 22 或更新版本"
fi

argument="${1:-}"
case "$argument" in
    "")
        version="$default_version"
        ;;
    --new)
        version="latest"
        ;;
    -*)
        die "未知选项: $argument"
        ;;
    *)
        version="${argument#v}"
        ;;
esac

package_spec="$package_name@$version"
printf '安装 Command Code: %s\n' "$package_spec"
npm install --global --prefix "$install_prefix" --no-fund --no-audit "$package_spec"

global_bin="$install_dir/command-code"

[ -x "$global_bin" ] || die "npm 安装结束，但找不到可执行文件: $global_bin"
installed_version="$($global_bin --version 2>/dev/null | sed -n '1p' || true)"

[ -n "$installed_version" ] || die "已安装 command-code，但版本检查失败"

printf '\nCommand Code 安装完成: %s\n' "$installed_version"
printf '安装目录: %s\n' "$install_dir"
printf '常用入口: command-code、cmd；原生 Windows 使用 cmdc。\n'

case ":$PATH:" in
    *":$install_dir:"*) ;;
    *)
        case "${SHELL##*/}" in
            zsh)  profile="$HOME/.zshrc" ;;
            bash) profile="$HOME/.bashrc" ;;
            *)    profile="$HOME/.profile" ;;
        esac
        line="export PATH=\"$install_dir:\$PATH\""
        if grep -Fqs "$install_dir" "$profile" 2>/dev/null; then
            :
        else
            printf '\n# command-code\n%s\n' "$line" >> "$profile"
            printf '\nPATH 已写入: %s\n' "$profile"
        fi
        printf '请重启 shell，或立即在当前终端执行:\n  %s\n' "$line"
        ;;
esac

printf '\n下一步: command-code login\n'
