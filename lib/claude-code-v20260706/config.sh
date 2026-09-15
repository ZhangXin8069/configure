#!/usr/bin/env bash
# Claude Code 一键配置脚本（Linux / macOS）
# 幂等合并生成 ~/.claude/settings.json，保留已有键；默认 dry-run，--apply 才写盘。
# 只写用户级设置文件，不触碰 ~/.claude.json（安装/登录凭据区，由 install.sh 管理）。
# Usage: bash config.sh [选项]

set -euo pipefail

CONFIG_DIR="$HOME/.claude"
CONFIG_FILE="$CONFIG_DIR/settings.json"

APPLY=0
MODEL=""
THEME=""
PERM_ALLOW=()
PERM_DENY=()
ENVS=()

list_themes() {
    cat <<'EOF'
推荐主题（写入顶层 theme 键）:
  dark   深色（默认）
  light  浅色
  tmrw   Tomorrow（明亮对比）
EOF
}

usage() {
    cat <<EOF
用法: bash config.sh [选项]

  --check               检查 claude 安装与现有配置（只读）
  --apply               合并并写盘（默认 dry-run；写盘前自动备份旧配置）
  --model MODEL         设置默认模型（如 claude-sonnet-4-5 / deepseek-chat）
  --theme NAME          设置主题: dark|light|tmrw
  --permission-allow T  将工具加入 permissions.allow（可多次，去重）
  --permission-deny T   将工具加入 permissions.deny（可多次，去重）
  --env KEY=VALUE       设置 env 键（保留已有键；可多次）
  --list-themes         列出推荐主题
  -h, --help            显示帮助

默认行为: 打印将要合并的 JSON 差异，不写盘；加 --apply 才写入。
配置位置: $CONFIG_FILE（合并保留已有键）
EOF
}

die() { printf '错误: %s\n' "$1" >&2; exit 1; }

require_python() {
    command -v python3 >/dev/null 2>&1 || die "需要 python3 合并 JSON；本脚本不自动安装依赖。"
}

check_status() {
    if command -v claude >/dev/null 2>&1; then
        printf 'claude: %s\n' "$(claude --version 2>/dev/null | head -1 || echo '版本未知')"
    else
        printf 'claude: 未安装（见同目录 install.sh）\n'
    fi
    printf '配置目录: %s\n' "$CONFIG_DIR"
    [ -f "$CONFIG_FILE" ] && printf 'settings.json: 存在 (%s 字节)\n' "$(wc -c < "$CONFIG_FILE" | tr -d ' ')" \
                          || printf 'settings.json: 不存在\n'
    if [ -f "$CONFIG_FILE" ]; then
        printf '已配置: '
        python3 - "$CONFIG_FILE" <<'PY' 2>/dev/null || printf '（解析失败）\n'
import json,sys
try:
    d=json.load(open(sys.argv[1]))
    out=[]
    if d.get("model"): out.append("model="+str(d["model"]))
    if d.get("theme"): out.append("theme="+str(d["theme"]))
    if d.get("permissions"):
        p=d["permissions"]
        if p.get("allow"): out.append("allow=%d" % len(p["allow"]))
        if p.get("deny"): out.append("deny=%d" % len(p["deny"]))
    if d.get("env"): out.append("env=%d" % len(d["env"]))
    print("; ".join(out) if out else "（无自定义键）")
except Exception:
    print("（解析失败）")
PY
    fi
}

load_json() {
    python3 -c 'import json,sys
try:
    d=json.load(open(sys.argv[1]))
    assert isinstance(d, dict)
    print(json.dumps(d))
except Exception:
    print("{}")' "$1"
}

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
            --check)        check_status; return 0;;
            --apply)        APPLY=1; shift;;
            --model)        [ $# -ge 2 ] || die "--model 需要参数"; MODEL="$2"; shift 2;;
            --theme)        [ $# -ge 2 ] || die "--theme 需要参数"; THEME="$2"; shift 2;;
            --permission-allow) [ $# -ge 2 ] || die "--permission-allow 需要工具名"; PERM_ALLOW+=("$2"); shift 2;;
            --permission-deny)  [ $# -ge 2 ] || die "--permission-deny 需要工具名"; PERM_DENY+=("$2"); shift 2;;
            --env)          [ $# -ge 2 ] || die "--env 需要 KEY=VALUE"; ENVS+=("$2"); shift 2;;
            --list-themes)  list_themes; return 0;;
            -h|--help)      usage; return 0;;
            *) die "未知选项: $1（用法见 --help）";;
        esac
    done

    require_python
    case "$THEME" in
        dark|light|tmrw|"") ;;
        *) die "--theme 仅接受 dark|light|tmrw";;
    esac

    local changed=0 cur="{}" merged

    [ -f "$CONFIG_FILE" ] && cur="$(load_json "$CONFIG_FILE")"
    merged="$cur"

    if [ -n "$MODEL" ]; then
        merged="$(printf '%s' "$merged" | python3 -c 'import json,sys
d=json.load(sys.stdin); d["model"]=sys.argv[1]; print(json.dumps(d))' "$MODEL")"
    fi
    if [ -n "$THEME" ]; then
        merged="$(printf '%s' "$merged" | python3 -c 'import json,sys
d=json.load(sys.stdin); d["theme"]=sys.argv[1]; print(json.dumps(d))' "$THEME")"
    fi
    if [ ${#ENVS[@]} -gt 0 ]; then
        local env_args=""
        for e in "${ENVS[@]}"; do
            case "$e" in
                *=*) ;;
                *) die "--env 需要 KEY=VALUE 格式: $e";;
            esac
            env_args+=" $e"
        done
        merged="$(printf '%s' "$merged" | python3 -c 'import json,sys
d=json.load(sys.stdin)
env=d.setdefault("env",{})
for kv in sys.argv[1:]:
    k,v=kv.split("=",1)
    env[k]=v
print(json.dumps(d))' $env_args)"
    fi
    if [ ${#PERM_ALLOW[@]} -gt 0 ] || [ ${#PERM_DENY[@]} -gt 0 ]; then
        local pa="" pd=""
        for t in "${PERM_ALLOW[@]}"; do pa+=" $t"; done
        for t in "${PERM_DENY[@]}"; do pd+=" $t"; done
        merged="$(printf '%s' "$merged" | python3 -c 'import json,sys
d=json.load(sys.stdin)
perm=d.setdefault("permissions",{})
def add(lst,item):
    if item not in lst: lst.append(item)
allow=perm.setdefault("allow",[])
for t in sys.argv[1].split(): add(allow,t)
deny=perm.setdefault("deny",[])
for t in sys.argv[2].split(): add(deny,t)
print(json.dumps(d))' "$pa" "$pd")"
    fi

    local cur_cmp merged_cmp
    cur_cmp="$(printf '%s' "$cur" | python3 -c 'import json,sys
print(json.dumps(json.load(sys.stdin), sort_keys=True))')"
    merged_cmp="$(printf '%s' "$merged" | python3 -c 'import json,sys
print(json.dumps(json.load(sys.stdin), sort_keys=True))')"

    if [ "$merged_cmp" != "$cur_cmp" ]; then
        merged="$(printf '%s' "$merged" | python3 -m json.tool)"
        write_config "$CONFIG_FILE" "$merged"
        changed=1
    else
        printf 'settings.json: 无变更\n'
    fi

    [ "$changed" = 0 ] && printf '全部无变更（配置已是最新）\n'
    [ "$APPLY" = 1 ] && printf '\n提示: 合并采用「保留已有键」策略；权限/hooks 等数组项为追加去重。\n'
}

main "$@"