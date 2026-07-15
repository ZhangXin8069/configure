#!/bin/bash
#=============================================================================
# Claude Code & cc-switch 离线安装包批量下载脚本
#
# 用法:
#   ./download_all.sh                    # 下载全部
#   ./download_all.sh --claude-code      # 仅 Claude Code
#   ./download_all.sh --cc-switch-cli    # 仅 cc-switch-cli
#   ./download_all.sh --cc-switch        # 仅 cc-switch
#
# 所有文件下载到脚本所在目录下的 claude-code/ cc-switch-cli/ cc-switch/
# 已存在的文件会自动跳过，可安全重复运行。
#=============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$SCRIPT_DIR"

# ── 公共函数 ────────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "  ${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "  ${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "  ${RED}[ERR]${NC}   $*"; }
step()  { echo -e "\n${GREEN}==>${NC} $*"; }

# curl 带重试的封装
_curl() {
    # 用法: _curl url dest [timeout_sec]
    local url="$1" dest="$2" timeout="${3:-300}"
    curl -fL --connect-timeout 15 --max-time "$timeout" \
         --retry 2 --retry-delay 5 \
         -o "$dest" "$url"
}

_curl_get() {
    # 用法: _curl_get url [timeout_sec]
    local url="$1" timeout="${2:-30}"
    curl -fsSL --connect-timeout 15 --max-time "$timeout" "$url"
}

# 检查文件是否已有效下载（大小 > 0）
_is_done() {
    [ -f "$1" ] && [ -s "$1" ]
}

# ── 各组件配置 ──────────────────────────────────────────────────────────────

GCS_BUCKET="http://storage.googleapis.com/claude-code-dist-86c565f3-f756-42ad-8dfa-d59b1c096819/claude-code-releases"
PLATFORM="linux-x64"

CC_SWITCH_CLI_REPO="SaladDay/cc-switch-cli"
CC_SWITCH_REPO="farion1231/cc-switch"

# ── Phase 1: Claude Code ────────────────────────────────────────────────────

download_claude_code() {
    step "Phase 1/3: Claude Code (GCS)"

    local versions=(
        2.1.210 2.1.209 2.1.208 2.1.207 2.1.206 2.1.205 2.1.204 2.1.203
        2.1.202 2.1.201 2.1.200 2.1.199 2.1.198 2.1.197 2.1.196 2.1.195
        2.1.193 2.1.191 2.1.190 2.1.187
        2.1.0 2.0.50 2.0.0 1.0.100 1.0.50
    )

    local total=${#versions[@]} count=0 ok=0 skip=0 fail=0
    local dir="$BASE/claude-code"
    mkdir -p "$dir"

    for ver in "${versions[@]}"; do
        count=$((count + 1))
        local vdir="$dir/$ver"
        mkdir -p "$vdir"

        # 下载 manifest
        local manifest_url="$GCS_BUCKET/$ver/manifest.json"
        if _is_done "$vdir/manifest.json"; then
            skip=$((skip + 1))
            echo "[$count/$total] $ver: manifest (skip)"
        elif _curl "$manifest_url" "$vdir/manifest.json" 30; then
            echo "[$count/$total] $ver: manifest (ok)"
        else
            echo "[$count/$total] $ver: manifest (FAIL)"
            fail=$((fail + 1))
            continue
        fi

        # 下载二进制
        local binary_url="$GCS_BUCKET/$ver/$PLATFORM/claude"
        if _is_done "$vdir/claude"; then
            echo "           binary (skip, $(du -h "$vdir/claude" | cut -f1))"
            ok=$((ok + 1))
        elif _curl "$binary_url" "$vdir/claude" 600; then
            chmod +x "$vdir/claude"
            echo "           binary (ok, $(du -h "$vdir/claude" | cut -f1))"
            ok=$((ok + 1))
        else
            echo "           binary (FAIL)"
            rm -f "$vdir/claude"
            fail=$((fail + 1))
        fi
    done

    # latest 指针
    _curl_get "$GCS_BUCKET/latest" 10 > "$dir/latest.txt" 2>/dev/null || true

    info "Claude Code: $ok 成功, $skip 跳过, $fail 失败 (共 $total)"
}

# ── Phase 2: cc-switch-cli ──────────────────────────────────────────────────

download_cc_switch_cli() {
    step "Phase 2/3: cc-switch-cli (GitHub)"

    local dir="$BASE/cc-switch-cli"
    mkdir -p "$dir"

    # 获取所有 releases
    local api_json
    api_json=$(_curl_get "https://api.github.com/repos/${CC_SWITCH_CLI_REPO}/releases?per_page=100" 30) || {
        err "获取 cc-switch-cli releases 失败，GitHub 可能不可达"
        return 1
    }

    echo "$api_json" | python3 << 'PYEOF'
import json, sys, os, subprocess

BASE = os.environ.get("SCRIPT_DIR", ".") + "/cc-switch-cli"
releases = json.load(sys.stdin)
total = len(releases)
ok = skip = fail = 0

for i, r in enumerate(releases, 1):
    tag = r['tag_name']
    d = os.path.join(BASE, tag)
    os.makedirs(d, exist_ok=True)

    for a in r['assets']:
        name = a['name']
        url = a['browser_download_url']

        if name not in ('cc-switch-cli-linux-x64-musl.tar.gz', 'install.sh'):
            continue

        dest = os.path.join(d, name)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print(f"[{i}/{total}] {tag}: {name} (skip)")
            skip += 1
            continue

        size_mb = a['size'] / 1024 / 1024
        print(f"[{i}/{total}] {tag}: {name} ({size_mb:.1f} MB)...", end=" ", flush=True)
        rc = subprocess.run(
            ['curl', '-fL', '--connect-timeout', '15', '--max-time', '120',
             '--retry', '2', '--retry-delay', '3', '-o', dest, url],
            capture_output=True
        )
        if rc.returncode == 0:
            print("ok")
            ok += 1
        else:
            print(f"FAIL ({rc.returncode})")
            fail += 1
            if os.path.exists(dest): os.remove(dest)

# latest.json
import subprocess
subprocess.run(['curl', '-fsSL',
    f'https://github.com/SaladDay/cc-switch-cli/releases/latest/download/latest.json',
    '-o', os.path.join(BASE, 'latest.json')], capture_output=True)

print(f"\ncc-switch-cli: {ok} ok, {skip} skip, {fail} fail (total {total} releases)")
PYEOF
}

# ── Phase 3: cc-switch ──────────────────────────────────────────────────────

download_cc_switch() {
    step "Phase 3/3: cc-switch (GitHub)"

    local dir="$BASE/cc-switch"
    mkdir -p "$dir"

    local api_json
    api_json=$(_curl_get "https://api.github.com/repos/${CC_SWITCH_REPO}/releases?per_page=100" 30) || {
        err "获取 cc-switch releases 失败，GitHub 可能不可达"
        return 1
    }

    echo "$api_json" | python3 << 'PYEOF'
import json, sys, os, subprocess

BASE = os.environ.get("SCRIPT_DIR", ".") + "/cc-switch"
releases = json.load(sys.stdin)
total = len(releases)

# 统计当前状态
empty_dirs = []
filled_dirs = []
for d in sorted(os.listdir(BASE)):
    dpath = os.path.join(BASE, d)
    if not os.path.isdir(dpath):
        continue
    files = [f for f in os.listdir(dpath) if f != 'latest.json']
    if files:
        filled_dirs.append(d)
    else:
        empty_dirs.append(d)

print(f"已有: {len(filled_dirs)}, 待下载: {len(empty_dirs)}, 共 {total} releases")

ok = skip = fail = 0

for r in releases:
    tag = r['tag_name']
    d = os.path.join(BASE, tag)
    os.makedirs(d, exist_ok=True)

    for a in r['assets']:
        name = a['name']
        url = a['browser_download_url']
        nl = name.lower()

        # ── 过滤：只保留 Linux x86_64/amd64 ──
        # 排除 arm64 / aarch64 / Windows / macOS
        skip_asset = False
        for pat in ['arm64', 'aarch64', 'windows', '.exe', '.msi',
                     'macos', '.dmg', 'mac.zip', '-mac.', '.app.tar']:
            if pat in nl:
                skip_asset = True
                break
        if skip_asset:
            continue

        # 必须匹配以下模式之一
        match = False
        for pat in ['linux-x86_64', 'linux-x64',
                     '-linux.', 'amd64',
                     '.appimage', '.deb', '.rpm']:
            if pat in nl:
                match = True
                break
        # 也匹配 latest.json，但不匹配非 Linux 的 .appimage
        if not match and name == 'latest.json':
            match = True
        if not match:
            continue

        dest = os.path.join(d, name)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print(f"  {tag}: {name} (skip, {os.path.getsize(dest)/1024/1024:.0f}MB)")
            skip += 1
            continue

        size_mb = a['size'] / 1024 / 1024
        print(f"  {tag}: {name} ({size_mb:.0f}MB)...", end=" ", flush=True)
        rc = subprocess.run([
            'curl', '-fL', '--connect-timeout', '15', '--max-time', '600',
            '--retry', '2', '--retry-delay', '5',
            '-o', dest, url
        ], capture_output=True, timeout=620)
        if rc.returncode == 0:
            print("ok")
            ok += 1
        else:
            print(f"FAIL ({rc.returncode})")
            fail += 1
            if os.path.exists(dest): os.remove(dest)

# latest.json
import subprocess
subprocess.run(['curl', '-fsSL',
    f'https://github.com/farion1231/cc-switch/releases/latest/download/latest.json',
    '-o', os.path.join(BASE, 'latest.json')], capture_output=True)

total_files = sum(1 for _ in os.listdir(BASE))
print(f"\ncc-switch: {ok} ok, {skip} skip, {fail} fail (total {total} releases)")
PYEOF
}

# ── 汇总 ────────────────────────────────────────────────────────────────────

summary() {
    echo ""
    echo "========================================"
    echo "  下载汇总"
    echo "========================================"

    for component in claude-code cc-switch-cli cc-switch; do
        local comp_dir="$BASE/$component"
        if [ -d "$comp_dir" ]; then
            local ver_count=$(find "$comp_dir" -maxdepth 1 -type d ! -name "$(basename "$comp_dir")" 2>/dev/null | wc -l)
            local size=$(du -sh "$comp_dir" 2>/dev/null | cut -f1)
            printf "  %-20s  %3d versions  %s\n" "$component" "$ver_count" "$size"
        fi
    done
    echo "----------------------------------------"
    printf "  %-20s  %s\n" "总计" "$(du -sh "$BASE" 2>/dev/null | cut -f1)"
    echo "========================================"
}

# ── 主入口 ──────────────────────────────────────────────────────────────────

run_all=false; run_cc=false; run_cli=false; run_switch=false

if [ $# -eq 0 ]; then
    run_all=true
else
    for arg in "$@"; do
        case "$arg" in
            --claude-code) run_cc=true ;;
            --cc-switch-cli) run_cli=true ;;
            --cc-switch) run_switch=true ;;
            --all) run_all=true ;;
            *) echo "未知选项: $arg"; echo "用法: $0 [--claude-code|--cc-switch-cli|--cc-switch|--all]"; exit 1 ;;
        esac
    done
fi

$run_all || $run_cc   && download_claude_code
$run_all || $run_cli  && download_cc_switch_cli
$run_all || $run_switch && download_cc_switch

summary
