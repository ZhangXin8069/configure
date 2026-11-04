#!/usr/bin/env bash
# Ensure Node.js (default 22+) for the current user.
# Reuses an existing adequate Node.js; otherwise installs nvm and Node.js.
# Usage: bash install.sh [VERSION|--check|-h|--help]
# Env:   NODE_VERSION  默认目标版本（默认 22）
#        NVM_DIR       nvm 安装目录（默认 ~/.nvm 或 $XDG_CONFIG_HOME/nvm）
#        NODE_BIN_DIR  稳定入口目录（默认 $HOME/.local/bin），node/npm/npx 软链到此处
#        PROFILE       写入 nvm 加载语句的 shell 配置；/dev/null 表示不修改
#        METHOD        nvm 安装方式：git（默认）或 script

set -euo pipefail

: "${HOME:?HOME is required}"

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
default_version="${NODE_VERSION:-22}"
target_version="$default_version"
check_only=0
positional=0

usage() {
    cat <<EOF
用法: bash install.sh [VERSION|--check|-h|--help]

  VERSION       目标主版本或完整版本（默认: $default_version）
  --check       只检查 node/npm，不修改任何文件
  -h, --help    显示帮助

行为:
  当前 Node.js 主版本满足目标且 npm 可用时不安装。
  否则调用同目录 nvm-install.sh 安装 nvm 与指定版本。

环境变量:
  NODE_VERSION   默认目标版本（默认: 22）
  NVM_DIR        nvm 安装目录（默认: \$HOME/.nvm；设置 XDG_CONFIG_HOME 时为 \$XDG_CONFIG_HOME/nvm）
  NODE_BIN_DIR   稳定入口目录（默认: \$HOME/.local/bin），node/npm/npx 软链到此处
  PROFILE        写入 nvm 加载语句的 shell 配置；/dev/null 表示不修改
  METHOD         nvm 安装方式: git（需 git）或 script（需 curl/wget）；未设置时自动选择

安装结果:
  Node.js 运行时在 nvm 版本目录；$HOME/.local/bin/{node,npm,npx} 为指向它的软链，
  与 lib/_codex、lib/_claude-code 的稳定入口约定一致，不把版本路径写进 PATH。

要求:
  Bash 3.2+；安装时需要 git 或 curl/wget，以及访问 nodejs.org 与 GitHub 的网络。
EOF
}

die() {
    printf '错误: %s\n' "$1" >&2
    exit 1
}

node_major() {
    command -v node >/dev/null 2>&1 || return 1
    local major
    major="$(node -p 'Number(process.versions.node.split(".")[0])' 2>/dev/null)" || return 1
    case "$major" in
        ''|*[!0-9]*) return 1 ;;
    esac
    printf '%s' "$major"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --check)
            check_only=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -*)
            die "未知选项: $1（用法见 --help）"
            ;;
        *)
            [ "$positional" -eq 0 ] || die "最多接受一个版本参数"
            target_version="$1"
            positional=1
            shift
            ;;
    esac
done

case "$target_version" in
    v*) target_version="${target_version#v}" ;;
esac
case "$target_version" in
    ''|.*|*.|*..*|*[!0-9.]*)
        die "版本格式无效: $target_version（示例: 22、24、22.11.0）"
        ;;
esac
target_major="${target_version%%.*}"

# 与 lib/_codex、lib/_claude-code 及 setup.md 的约定一致：稳定入口放 $HOME/.local/bin，
# 不把版本的 nvm 路径写进 PATH。node/npm/npx 软链到该目录；用户自有的非软链文件保留不动。
link_stable_bin() {
    local source_dir="$1"
    [ -n "$source_dir" ] || return 0
    [ -d "$source_dir" ] || return 0
    local bin_dir="${NODE_BIN_DIR:-$HOME/.local/bin}"
    if ! mkdir -p "$bin_dir" 2>/dev/null; then
        printf '警告: 无法创建 %s，跳过稳定入口软链\n' "$bin_dir" >&2
        return 0
    fi
    local tool source_tool target_tool
    for tool in node npm npx; do
        source_tool="$source_dir/$tool"
        [ -x "$source_tool" ] || continue
        target_tool="$bin_dir/$tool"
        # 源与目标同一路径（稳定入口本身就是 node 来源）时不得建自指软链。
        if [ "$(readlink -f "$source_tool" 2>/dev/null || printf '%s' "$source_tool")" = \
             "$(readlink -f "$target_tool" 2>/dev/null || printf '%s' "$target_tool")" ]; then
            continue
        fi
        if [ -e "$target_tool" ] && [ ! -L "$target_tool" ]; then
            printf '跳过 %s：%s 已存在且不是软链（保留用户自有安装）\n' "$tool" "$target_tool"
            continue
        fi
        ln -sfn "$source_tool" "$target_tool"
        printf '已链接: %s -> %s\n' "$target_tool" "$source_tool"
    done
    case ":$PATH:" in
        *":$bin_dir:"*) ;;
        *) printf '提示: %s 不在当前 PATH 中，请确保登录 shell 包含它\n' "$bin_dir" ;;
    esac
}

installed_major="$(node_major || true)"
has_npm=0
if command -v npm >/dev/null 2>&1; then
    has_npm=1
fi

if [ -n "$installed_major" ] && [ "$has_npm" -eq 1 ] && [ "$installed_major" -ge "$target_major" ]; then
    installed_version="$(node --version 2>/dev/null || printf '版本未知')"
    printf 'Node.js %s 已满足要求（>= %s），npm 可用，无需安装。\n' "$installed_version" "$target_major"
    if [ "$check_only" -eq 0 ]; then
        link_stable_bin "$(dirname "$(command -v node)")"
    fi
    exit 0
fi

if [ "$check_only" -eq 1 ]; then
    if [ -n "$installed_major" ]; then
        printf 'Node.js 主版本 %s 不满足 >= %s，或 npm 不可用。\n' "$installed_major" "$target_major"
    else
        printf '未找到可用的 node/npm。\n'
    fi
    printf '安装或升级: bash %s %s\n' "$0" "$target_version"
    exit 1
fi

if [ -n "$installed_major" ]; then
    printf 'Node.js 主版本 %s 不满足 >= %s（或 npm 缺失），开始安装。\n' "$installed_major" "$target_major"
else
    printf '未找到 node/npm，开始安装 Node.js %s。\n' "$target_version"
fi

nvm_installer="$script_dir/nvm-install.sh"
[ -f "$nvm_installer" ] || die "缺少 nvm 安装器: $nvm_installer"

printf '使用 nvm 安装 Node.js %s（安装器: %s）\n' "$target_version" "$nvm_installer"
NODE_VERSION="$target_version" bash "$nvm_installer"

if [ -n "${NVM_DIR:-}" ]; then
    nvm_dir="$NVM_DIR"
elif [ -n "${XDG_CONFIG_HOME:-}" ]; then
    nvm_dir="$XDG_CONFIG_HOME/nvm"
else
    nvm_dir="$HOME/.nvm"
fi

candidate=""
for node_bin in "$nvm_dir"/versions/node/v"$target_major".*/bin/node "$nvm_dir"/versions/node/v"$target_major"/bin/node; do
    if [ -x "$node_bin" ]; then
        candidate="$node_bin"
    fi
done
[ -n "$candidate" ] || die "nvm 安装结束，但未在 $nvm_dir/versions/node 找到 Node.js v$target_major.*"

installed_version="$("$candidate" --version 2>/dev/null || true)"
[ -n "$installed_version" ] || die "已安装 Node.js，但无法执行: $candidate"

printf '\nNode.js 安装完成: %s\n' "$installed_version"
printf '可执行文件: %s\n' "$candidate"

link_stable_bin "$(dirname "$candidate")"
bin_dir="${NODE_BIN_DIR:-$HOME/.local/bin}"

if [ "${PROFILE:-}" = "/dev/null" ]; then
    printf '\n未修改 shell 启动文件（PROFILE=/dev/null）。若 %s 已在 PATH 中，直接使用 node/npm 即可；否则执行:\n' "$bin_dir"
else
    printf '\n新的登录 shell 会自动加载 nvm，并可从 %s 使用 node/npm；当前终端执行:\n' "$bin_dir"
fi
printf '  export NVM_DIR="%s"\n' "$nvm_dir"
printf '  . "$NVM_DIR/nvm.sh"\n'
printf '  nvm use %s\n' "$target_major"
