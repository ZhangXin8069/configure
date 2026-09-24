#!/usr/bin/env bash
# OpenCode 一键配置脚本（Linux / macOS）
# V2 生成 opencode.json + cli.json；V1 兼容生成 opencode.json + tui.json。
# 幂等合并且不覆盖无关键；默认仅打印与检查，--apply 才写盘。
# Usage: bash config.sh [选项]

set -euo pipefail

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
CONFIG_FILE="$CONFIG_DIR/opencode.json"
TUI_FILE="$CONFIG_DIR/tui.json"
CLI_FILE="$CONFIG_DIR/cli.json"
SCHEMA="https://opencode.ai/config.json"
TUI_SCHEMA="https://opencode.ai/tui.json"
CLI_SCHEMA="https://opencode.ai/v2/cli.json"

OPENCODE_MAJOR=2
if command -v opencode >/dev/null 2>&1; then
    _version="$(opencode --version 2>/dev/null | head -1 || true)"
    _version="${_version##* }"
    _version="${_version#v}"
    case "$_version" in
        0.*|1.*) OPENCODE_MAJOR=1;;
        2.*) OPENCODE_MAJOR=2;;
    esac
fi
unset _version

APPLY=0
MODEL=""
SMALL_MODEL=""
THEME=""
LSP=""
PERMISSIONS=()
PLUGINS=()

# --- V2 插件说明（V1 插件 API 与 V2 不兼容，不再推荐未经确认迁移的旧包） ---
list_plugins() {
    cat <<'EOF'
OpenCode V2 插件 API 与 V1 不兼容。
仅安装明确声明支持 V2 的插件；安装使用:
  opencode plugin add <package>
插件目录见: https://opencode.ai/v2/docs/plugins/

本脚本的 --plugin 只把包名写入 opencode.json 的 plugins 数组，不联网安装。
EOF
}

list_themes() {
    cat <<'EOF'
主题应优先使用 V2 内置主题或已验证兼容 cli.json 的外部主题:
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
  --theme NAME          设置 TUI 主题（V2 写入 cli.json，V1 写入 tui.json）
  --lsp on|off          启用/关闭 LSP
  --permission TOOL=VAL 设置权限 (allow/ask/deny)，如 bash=ask、edit=ask；V2 自动映射 action
  --plugin NAME         将包名加入 plugins/plugin 数组（不联网安装）
  --list-plugins        显示 V2 插件安装说明
  --list-themes         列出推荐主题
  -h, --help            显示帮助

默认行为: 打印将要合并的 JSON 差异，不写盘；加 --apply 才写入。
模式: OpenCode V$OPENCODE_MAJOR
配置位置: $CONFIG_FILE（合并保留已有键）与 $([ "$OPENCODE_MAJOR" = 2 ] && printf '%s' "$CLI_FILE" || printf '%s' "$TUI_FILE")
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
    printf '配置模式: OpenCode V%s\n' "$OPENCODE_MAJOR"
    printf '配置目录: %s\n' "$CONFIG_DIR"
    [ -f "$CONFIG_FILE" ] && printf 'opencode.json: 存在 (%s 字节)\n' "$(wc -c < "$CONFIG_FILE" | tr -d ' ')" \
                          || printf 'opencode.json: 不存在\n'
    if [ "$OPENCODE_MAJOR" = 2 ]; then
        [ -f "$CLI_FILE" ] && printf 'cli.json: 存在\n' || printf 'cli.json: 不存在\n'
    else
        [ -f "$TUI_FILE" ] && printf 'tui.json: 存在\n' || printf 'tui.json: 不存在\n'
    fi
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
        for p in "${PERMISSIONS[@]}"; do
            case "$p" in
                *=*)
                    _perm_value="${p#*=}"
                    case "$_perm_value" in
                        allow|ask|deny) ;;
                        *) die "--permission 的值必须是 allow/ask/deny: $p";;
                    esac
                    ;;
                *) die "--permission 需要 TOOL=VAL 格式（如 bash=ask）: $p";;
            esac
        done
        unset _perm_value
        if [ "$OPENCODE_MAJOR" = 2 ]; then
            merged="$(printf '%s' "$merged" | python3 -c 'import json,sys
d=json.load(sys.stdin)
rules=d.setdefault("permissions",[])
for kv in sys.argv[1:]:
    action,effect=kv.split("=",1)
    action={"bash":"shell","task":"subagent","write":"edit","patch":"edit"}.get(action,action)
    resource="*"
    rules=[r for r in rules if not (isinstance(r,dict) and r.get("action")==action and r.get("resource")==resource)]
    rules.append({"action":action,"resource":resource,"effect":effect})
d["permissions"]=rules
print(json.dumps(d))' "${PERMISSIONS[@]}")"
        else
            merged="$(printf '%s' "$merged" | python3 -c 'import json,sys
d=json.load(sys.stdin)
perm=d.setdefault("permission",{})
for kv in sys.argv[1:]:
    k,v=kv.split("=",1)
perm[k]=v
print(json.dumps(d))' "${PERMISSIONS[@]}")"
        fi
    fi
    if [ ${#PLUGINS[@]} -gt 0 ]; then
        if [ "$OPENCODE_MAJOR" = 2 ]; then
            merged="$(printf '%s' "$merged" | python3 -c 'import json,sys
d=json.load(sys.stdin)
plugins=d.setdefault("plugins",[])
for name in sys.argv[1:]:
    if name not in plugins:
        plugins.append(name)
print(json.dumps(d))' "${PLUGINS[@]}")"
        else
            merged="$(printf '%s' "$merged" | python3 -c 'import json,sys
d=json.load(sys.stdin)
plugins=d.setdefault("plugin",[])
for name in sys.argv[1:]:
    if name not in plugins:
        plugins.append(name)
print(json.dumps(d))' "${PLUGINS[@]}")"
        fi
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

    # --- CLI 主题：V2=cli.json，V1=tui.json ---
    if [ -n "$THEME" ]; then
        local tcur="{}" tmerged tcur_cmp tmerged_cmp
        local theme_file
        if [ "$OPENCODE_MAJOR" = 2 ]; then
            theme_file="$CLI_FILE"
        else
            theme_file="$TUI_FILE"
        fi
        [ -f "$theme_file" ] && tcur="$(load_json "$theme_file")"
        if [ "$OPENCODE_MAJOR" = 2 ]; then
            tmerged="$(printf '%s' "$tcur" | python3 -c 'import json,sys
d=json.load(sys.stdin)
theme=d.setdefault("theme",{})
theme["name"]=sys.argv[1]
d["$schema"]=sys.argv[2]
print(json.dumps(d, indent=2))' "$THEME" "$CLI_SCHEMA")"
        else
            tmerged="$(printf '%s' "$tcur" | python3 -c 'import json,sys
d=json.load(sys.stdin); d["theme"]=sys.argv[1]
d["$schema"]=sys.argv[2]
print(json.dumps(d, indent=2))' "$THEME" "$TUI_SCHEMA")"
        fi
        tcur_cmp="$(printf '%s' "$tcur" | python3 -c 'import json,sys
print(json.dumps(json.load(sys.stdin), sort_keys=True))')"
        tmerged_cmp="$(printf '%s' "$tmerged" | python3 -c 'import json,sys
print(json.dumps(json.load(sys.stdin), sort_keys=True))')"
        if [ "$tmerged_cmp" != "$tcur_cmp" ]; then
            write_config "$theme_file" "$tmerged"
            changed=1
        else
            printf '%s: 无变更\n' "$(basename "$theme_file")"
        fi
    fi

    [ "$changed" = 0 ] && printf '全部无变更（配置已是最新或仅提供参数不一致）\n'
    [ "$APPLY" = 1 ] && printf '\n提示: 合并采用「保留已有键」策略；插件包需确认支持 OpenCode V%s 后安装。\n' "$OPENCODE_MAJOR"
}

main "$@"
