#!/usr/bin/env bash
# OpenCode 一键配置脚本（Linux / macOS）
# 幂等合并生成 ~/.config/opencode/opencode.json 与 tui.json，不覆盖已有键；
# 默认仅打印与检查，--apply 才写盘。参考 awesome-opencode/awesome-opencode 生态清单。
# Usage: bash config.sh [选项]

set -euo pipefail

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
CONFIG_FILE="$CONFIG_DIR/opencode.json"
TUI_FILE="$CONFIG_DIR/tui.json"
SCHEMA="https://opencode.ai/config.json"
TUI_SCHEMA="https://opencode.ai/tui.json"

APPLY=0
MODEL=""
SMALL_MODEL=""
THEME=""
LSP=""
PERMISSIONS=()
PLUGINS=()

# --- 推荐清单（来源：https://github.com/awesome-opencode/awesome-opencode） ---
list_plugins() {
    cat <<'EOF'
推荐插件（npm 模块名须以各仓库 README 安装说明为准）:
  opencode-arise            并行后台任务编排 (@bluelovers/opencode-arise)
  opencode-autotitle        AI 自动会话命名 (pawelma/opencode-autotitle)
  opencode-background       后台进程管理 (zenobi-us/opencode-background)
  opencode-dynamic-pruning  token 优化: 裁剪过期工具输出 (Tarquinen/opencode-dynamic-context-pruning)
  opencode-context-analysis token 用量分析 (IgorWarzocha/Opencode-Context-Analysis-Plugin)
  opencode-ccs-sync         从 Claude Code Switch 同步 providers (JasonLandbridge/opencode-ccs-sync)
  opencode-models-discovery 模型发现与过滤 (yuhp/opencode-models-discovery)
  其他候选: 见 https://github.com/awesome-opencode/awesome-opencode#plugins
EOF
}

list_themes() {
    cat <<'EOF'
推荐主题（来源: awesome-opencode THEMES 与官方内置; 安装方式见各仓库）:
  内置:    tokyonight / dracula / catppuccin / gruvbox / nord / solarized / light / dark
  ayu:     postrednik/opencode-ayu-theme
  charcoal: VyomJain6904/charcoal-theme
  lavi:    b0o/lavi (contrib/opencode)
  moonlight: brunogabriel/opencode-moonlight-theme
  light:   fatihtoprakk/opencode-light-themes (21 浅色主题, 一键安装脚本)
  poimandres: ajaxdude/opencode-ai-poimandres-theme
  vscode:  regen45t/opencode-vscode-themes (一行安装脚本)
EOF
}

usage() {
    cat <<EOF
用法: bash config.sh [选项]

  --check               检查 opencode 安装与现有配置（只读）
  --apply               合并并写盘（默认 dry-run；写盘前自动备份旧配置）
  --model MODEL         设置默认模型（provider/model 格式）
  --small-model MODEL   设置轻量模型（标题生成等）
  --theme NAME          设置 TUI 主题（写入 tui.json）
  --lsp on|off          启用/关闭 LSP
  --permission TOOL=VAL 设置工具权限 (allow/ask/deny)，如 bash=ask、edit=ask；可多次
  --plugin NAME         将 npm 插件加入 plugin 数组（不联网安装，需先 opencode plugin NAME）
  --list-plugins        列出推荐插件
  --list-themes         列出推荐主题
  -h, --help            显示帮助

默认行为: 打印将要合并的 JSON 差异，不写盘；加 --apply 才写入。
配置位置: $CONFIG_FILE（合并保留已有键）与 $TUI_FILE
EOF
}

die() { printf '错误: %s\n' "$1" >&2; exit 1; }

require_python() {
    command -v python3 >/dev/null 2>&1 || die "需要 python3 合并 JSON；本脚本不自动安装依赖。"
}

check_status() {
    if command -v opencode >/dev/null 2>&1; then
        printf 'opencode: %s\n' "$(opencode --version 2>/dev/null | head -1 || echo '版本未知')"
    else
        printf 'opencode: 未安装（见同目录 install.sh）\n'
    fi
    printf '配置目录: %s\n' "$CONFIG_DIR"
    [ -f "$CONFIG_FILE" ] && printf 'opencode.json: 存在 (%s 字节)\n' "$(wc -c < "$CONFIG_FILE" | tr -d ' ')" \
                          || printf 'opencode.json: 不存在\n'
    [ -f "$TUI_FILE" ] && printf 'tui.json: 存在\n' || printf 'tui.json: 不存在\n'
    if [ -f "$CONFIG_FILE" ]; then
        printf '已配置模型: '
        python3 - "$CONFIG_FILE" <<'PY' 2>/dev/null || printf '（解析失败）\n'
import json,sys
try:
    d=json.load(open(sys.argv[1]))
    print(d.get("model","（未设置）"))
except Exception:
    print("（解析失败）")
PY
    fi
}

# 读入 JSON 对象；非法则报错退出
load_json() {
    python3 -c 'import json,sys
try:
    d=json.load(open(sys.argv[1]))
    assert isinstance(d, dict)
    print(json.dumps(d))
except Exception:
    print("{}")' "$1"
}

# 合并写盘：backup -> merge -> atomic rename
write_config() {
    local file="$1" payload="$2"
    if [ "$APPLY" != 1 ]; then
        printf '[dry-run] 将写: %s\n%s\n' "$file" "$(printf '%s' "$payload" | python3 -m json.tool)"
        return 0
    fi
    mkdir -p "$(dirname "$file")"
    if [ -f "$file" ]; then
        cp "$file" "$file.bak.$(date +%Y%m%d-%H%M%S)"
    fi
    printf '%s\n' "$payload" > "$file.tmp"
    mv "$file.tmp" "$file"
    printf '已写: %s\n' "$file"
}

main() {
    [ $# -eq 0 ] && usage && exit 0
    while [ $# -gt 0 ]; do
        case "$1" in
            --check)      check_status; return 0;;
            --apply)      APPLY=1; shift;;
            --model)      [ $# -ge 2 ] || die "--model 需要参数"; MODEL="$2"; shift 2;;
            --small-model)[ $# -ge 2 ] || die "--small-model 需要参数"; SMALL_MODEL="$2"; shift 2;;
            --theme)      [ $# -ge 2 ] || die "--theme 需要参数"; THEME="$2"; shift 2;;
            --lsp)        [ $# -ge 2 ] || die "--lsp 需要 on|off"; LSP="$2"; shift 2;;
            --permission) [ $# -ge 2 ] || die "--permission 需要 TOOL=VAL"; PERMISSIONS+=("$2"); shift 2;;
            --plugin)     [ $# -ge 2 ] || die "--plugin 需要名称"; PLUGINS+=("$2"); shift 2;;
            --list-plugins) list_plugins; return 0;;
            --list-themes)  list_themes; return 0;;
            -h|--help)    usage; return 0;;
            *) die "未知选项: $1（用法见 --help）";;
        esac
    done

    require_python
    local changed=0

    # --- opencode.json 合并 ---
    local cur="{}" merged
    [ -f "$CONFIG_FILE" ] && cur="$(load_json "$CONFIG_FILE")"
    merged="$cur"
    [ -n "$MODEL" ] && merged="$(printf '%s' "$merged" | python3 -c 'import json,sys
d=json.load(sys.stdin); d["model"]=sys.argv[1]; print(json.dumps(d))' "$MODEL")"
    [ -n "$SMALL_MODEL" ] && merged="$(printf '%s' "$merged" | python3 -c 'import json,sys
d=json.load(sys.stdin); d["small_model"]=sys.argv[1]; print(json.dumps(d))' "$SMALL_MODEL")"
    case "$LSP" in
        on)  merged="$(printf '%s' "$merged" | python3 -c 'import json,sys
d=json.load(sys.stdin); d["lsp"]=True; print(json.dumps(d))')";;
        off) merged="$(printf '%s' "$merged" | python3 -c 'import json,sys
d=json.load(sys.stdin); d["lsp"]=False; print(json.dumps(d))')";;
        "") ;;
        *) die "--lsp 仅接受 on|off";;
    esac
    if [ ${#PERMISSIONS[@]} -gt 0 ]; then
        local perm_args=""
        for p in "${PERMISSIONS[@]}"; do
            case "$p" in
                *=*) ;;
                *) die "--permission 需要 TOOL=VAL 格式（如 bash=ask）: $p";;
            esac
            perm_args+=" $p"
        done
        merged="$(printf '%s' "$merged" | python3 -c 'import json,sys
d=json.load(sys.stdin)
perm=d.setdefault("permission",{})
for kv in sys.argv[1:]:
    k,v=kv.split("=",1)
    perm[k]=v
print(json.dumps(d))' $perm_args)"
    fi
    if [ ${#PLUGINS[@]} -gt 0 ]; then
        local pl_args=""
        for p in "${PLUGINS[@]}"; do pl_args+=" $p"; done
        merged="$(printf '%s' "$merged" | python3 -c 'import json,sys
d=json.load(sys.stdin)
pl=d.setdefault("plugin",[])
for name in sys.argv[1:]:
    if name not in pl:
        pl.append(name)
print(json.dumps(d))' $pl_args)"
    fi

    if [ "$merged" != "$cur" ]; then
        # 保留 $schema 一致性
        merged="$(printf '%s' "$merged" | python3 -c 'import json,sys
d=json.load(sys.stdin)
d["$schema"]=sys.argv[1]
print(json.dumps(d, indent=2))' "$SCHEMA")"
        write_config "$CONFIG_FILE" "$merged"
        changed=1
    else
        printf 'opencode.json: 无变更\n'
    fi

    # --- tui.json 主题 ---
    if [ -n "$THEME" ]; then
        local tcur="{}" tmerged tcur_cmp tmerged_cmp
        [ -f "$TUI_FILE" ] && tcur="$(load_json "$TUI_FILE")"
        tmerged="$(printf '%s' "$tcur" | python3 -c 'import json,sys
d=json.load(sys.stdin); d["theme"]=sys.argv[1]
d["$schema"]=sys.argv[2]
print(json.dumps(d, indent=2))' "$THEME" "$TUI_SCHEMA")"
        tcur_cmp="$(printf '%s' "$tcur" | python3 -c 'import json,sys
print(json.dumps(json.load(sys.stdin), sort_keys=True))')"
        tmerged_cmp="$(printf '%s' "$tmerged" | python3 -c 'import json,sys
print(json.dumps(json.load(sys.stdin), sort_keys=True))')"
        if [ "$tmerged_cmp" != "$tcur_cmp" ]; then
            write_config "$TUI_FILE" "$tmerged"
            changed=1
        else
            printf 'tui.json: 无变更\n'
        fi
    fi

    [ "$changed" = 0 ] && printf '全部无变更（配置已是最新或仅提供参数不一致）\n'
    [ "$APPLY" = 1 ] && printf '\n提示: 合并采用「保留已有键」策略；外部主题插件需按仓库说明安装后生效。\n'
}

main "$@"