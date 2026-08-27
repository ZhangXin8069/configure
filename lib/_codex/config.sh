#!/usr/bin/env bash
# Codex CLI 一键配置脚本（Linux / macOS）
# 幂等合并生成 ~/.codex/config.toml，保留已有键与注释；
# 默认仅打印与检查，--apply 才写盘。
# Usage: bash config.sh [选项]

set -euo pipefail

CONFIG_DIR="${CODEX_HOME:-$HOME/.codex}"
CONFIG_FILE="$CONFIG_DIR/config.toml"

APPLY=0
MODEL=""
APPROVAL=""
SANDBOX=""
THEME=""
PROVIDERS=()

# --- 推荐 provider 清单（base_url 为官方/vendor 兼容端点，env_key 为所需环境变量） ---
list_providers() {
    cat <<'EOF'
推荐 model_providers（用法: --provider NAME=base_url=ENV_KEY[=wire_api]，wire_api 默认 chat）:
  anthropic   https://api.anthropic.com/v1/           ANTHROPIC_API_KEY   wire_api=completions
  xai         https://api.x.ai/v1                      XAI_API_KEY         wire_api=chat
  deepseek    https://api.deepseek.com/v1              DEEPSEEK_API_KEY    wire_api=chat
  openrouter  https://openrouter.ai/api/v1             OPENROUTER_API_KEY  wire_api=chat
  moonshot    https://api.moonshot.cn/v1               MOONSHOT_API_KEY    wire_api=chat
  zhipu       https://open.bigmodel.cn/api/paas/v4     ZHIPU_API_KEY       wire_api=chat
说明: openai 为内置 provider，无需配置；base_url 与 env_key 请以各厂商文档为准。
EOF
}

list_themes() {
    cat <<'EOF'
推荐主题（写入顶层 theme 键）:
  dark   深色（默认）
  light  浅色
  auto   跟随系统
EOF
}

usage() {
    cat <<EOF
用法: bash config.sh [选项]

  --check               检查 codex 安装与现有配置（只读）
  --apply               合并并写盘（默认 dry-run；写盘前自动备份旧配置）
  --model MODEL         设置默认模型（如 gpt-5-codex / deepseek-chat）
  --approval-policy P   设置审批策略: never|on-request|untrusted|off
  --sandbox-mode M      设置沙箱模式: read-only|workspace-write|danger-full-access
  --theme NAME          设置 TUI 主题: dark|light|auto
  --provider SPEC       添加 model_providers 条目: NAME=base_url=ENV_KEY[=wire_api]；可多次
  --list-providers      列出推荐 provider 配置
  --list-themes         列出推荐主题
  -h, --help            显示帮助

默认行为: 打印将要合并的 TOML 差异，不写盘；加 --apply 才写入。
配置位置: $CONFIG_FILE（合并保留已有键与注释，只改顶层键与追加 provider 块）
认证:     安装后请运行 codex login 完成登录（脚本不代做）。
EOF
}

die() { printf '错误: %s\n' "$1" >&2; exit 1; }

require_python() {
    command -v python3 >/dev/null 2>&1 || die "需要 python3 合并 TOML；本脚本不自动安装依赖。"
}

check_status() {
    if command -v codex >/dev/null 2>&1; then
        printf 'codex: %s\n' "$(codex --version 2>/dev/null | head -1 || echo '版本未知')"
    else
        printf 'codex: 未安装（见同目录 install.sh）\n'
    fi
    printf '配置目录: %s\n' "$CONFIG_DIR"
    if [ -f "$CONFIG_FILE" ]; then
        printf 'config.toml: 存在 (%s 字节)\n' "$(wc -c < "$CONFIG_FILE" | tr -d ' ')"
        printf '已配置: '
        python3 - "$CONFIG_FILE" <<'PY' 2>/dev/null || printf '（解析失败）\n'
import sys
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("（需 python3.11+ 或 tomli 库解析）")
        sys.exit(0)
try:
    d = tomllib.load(open(sys.argv[1], "rb"))
    out = []
    if d.get("model"): out.append("model=" + d["model"])
    if d.get("approval_policy"): out.append("approval_policy=" + d["approval_policy"])
    if d.get("sandbox_mode"): out.append("sandbox_mode=" + d["sandbox_mode"])
    if d.get("theme"): out.append("theme=" + d["theme"])
    if d.get("model_providers"):
        out.append("providers=[" + ",".join(sorted(d["model_providers"])) + "]")
    print("; ".join(out) if out else "（无顶层自定义键）")
except Exception as e:
    print("（解析失败: %s）" % e)
PY
    else
        printf 'config.toml: 不存在\n'
    fi
}

# TOML 顶层键/表 幂等合并（纯文本行级操作，保留注释与未知内容）：
#   - set key=value    : 顶层键已存在则原位替换，否则插入到首个 [table] 之前
#   - provider SPEC    : [model_providers.NAME] 块已存在则跳过，否则追加到文件末尾
merge_toml() {
    python3 - "$CONFIG_FILE" "$@" <<'PY'
import os, sys

path, ops = sys.argv[1], sys.argv[2:]
text = ""
if os.path.exists(path):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

lines = text.splitlines()
changed = False

def fmt_str(v):
    if v in ("true", "false"):
        return v
    return '"%s"' % v.replace("\\", "\\\\").replace('"', '\\"')

def find_top_level(lines):
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("["):
            return i
        if "=" in s and not s.startswith("["):
            return None  # 未进入任何 table，全部为顶层区域
    return len(lines)

def set_top_level(lines, key, value):
    found = False
    val_changed = False
    in_table = False
    insert_at = None
    new_lines = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("["):
            in_table = True
            if insert_at is None:
                insert_at = len(new_lines)
        if not in_table and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k == key:
                found = True
                new_line = "%s = %s" % (key, fmt_str(value))
                if ln.strip() == new_line:
                    new_lines.append(ln)
                else:
                    new_lines.append(new_line)
                    val_changed = True
                continue
        new_lines.append(ln)
    if not found:
        if insert_at is None:
            insert_at = len(new_lines)
        if insert_at > 0 and new_lines[insert_at - 1].strip() != "":
            new_lines.insert(insert_at, "")
            insert_at += 1
        new_lines.insert(insert_at, "%s = %s" % (key, fmt_str(value)))
        return new_lines, True
    return new_lines, val_changed

def add_provider(lines, spec):
    parts = spec.split("=", 2)
    if len(parts) < 2 or not parts[0]:
        print("错误: --provider 需要 NAME=base_url=ENV_KEY[=wire_api] 格式: %s" % spec, file=sys.stderr)
        sys.exit(2)
    name, base_url = parts[0].strip(), parts[1].strip()
    env_key = parts[2].split("=", 1)[0].strip() if len(parts) > 2 else ""
    wire_api = parts[2].split("=", 1)[1].strip() if len(parts) > 2 and "=" in parts[2] else "chat"
    if not env_key:
        print("错误: provider %s 缺少 ENV_KEY（如 OPENAI_API_KEY）" % name, file=sys.stderr)
        sys.exit(2)
    header = "[model_providers.%s]" % name
    for ln in lines:
        if ln.strip() == header:
            print("提示: model_providers.%s 已存在，跳过" % name, file=sys.stderr)
            return lines, False
    block = [
        "",
        header,
        'name = "%s"' % name,
        'base_url = "%s"' % base_url.replace("\\", "\\\\").replace('"', '\\"'),
        'env_key = "%s"' % env_key,
        'wire_api = "%s"' % wire_api,
    ]
    return lines + block, True

new_lines = lines
i = 0
while i < len(ops):
    op = ops[i]
    if op == "set" and i + 2 < len(ops) + 1:
        k, v = ops[i + 1], ops[i + 2]
        new_lines, c = set_top_level(new_lines, k, v)
        changed = changed or c
        i += 3
    elif op == "provider" and i + 1 < len(ops):
        new_lines, c = add_provider(new_lines, ops[i + 1])
        changed = changed or c
        i += 2
    else:
        print("错误: 内部操作序列非法", file=sys.stderr)
        sys.exit(2)

print("\n".join(new_lines) + ("\n" if new_lines else ""))
sys.exit(0 if changed else 1)
PY
}

write_config() {
    local payload="$1"
    if [ "$APPLY" != 1 ]; then
        printf '[dry-run] 将写: %s\n%s\n' "$CONFIG_FILE" "$payload"
        return 0
    fi
    mkdir -p "$CONFIG_DIR"
    if [ -f "$CONFIG_FILE" ]; then
        cp "$CONFIG_FILE" "$CONFIG_FILE.bak.$(date +%Y%m%d-%H%M%S)"
    fi
    printf '%s\n' "$payload" > "$CONFIG_FILE.tmp"
    mv "$CONFIG_FILE.tmp" "$CONFIG_FILE"
    printf '已写: %s\n' "$CONFIG_FILE"
}

main() {
    [ $# -eq 0 ] && usage && exit 0
    while [ $# -gt 0 ]; do
        case "$1" in
            --check)        check_status; return 0;;
            --apply)        APPLY=1; shift;;
            --model)        [ $# -ge 2 ] || die "--model 需要参数"; MODEL="$2"; shift 2;;
            --approval-policy) [ $# -ge 2 ] || die "--approval-policy 需要参数"; APPROVAL="$2"; shift 2;;
            --sandbox-mode) [ $# -ge 2 ] || die "--sandbox-mode 需要参数"; SANDBOX="$2"; shift 2;;
            --theme)        [ $# -ge 2 ] || die "--theme 需要参数"; THEME="$2"; shift 2;;
            --provider)     [ $# -ge 2 ] || die "--provider 需要 NAME=base_url=ENV_KEY[=wire_api]"; PROVIDERS+=("$2"); shift 2;;
            --list-providers) list_providers; return 0;;
            --list-themes)  list_themes; return 0;;
            -h|--help)      usage; return 0;;
            *) die "未知选项: $1（用法见 --help）";;
        esac
    done

    require_python

    case "$APPROVAL" in
        never|on-request|untrusted|off|"") ;;
        *) die "--approval-policy 仅接受 never|on-request|untrusted|off";;
    esac
    case "$SANDBOX" in
        read-only|workspace-write|danger-full-access|"") ;;
        *) die "--sandbox-mode 仅接受 read-only|workspace-write|danger-full-access";;
    esac
    case "$THEME" in
        dark|light|auto|"") ;;
        *) die "--theme 仅接受 dark|light|auto";;
    esac

    local ops=()
    [ -n "$MODEL" ]    && ops+=(set model "$MODEL")
    [ -n "$APPROVAL" ] && ops+=(set approval_policy "$APPROVAL")
    [ -n "$SANDBOX" ]  && ops+=(set sandbox_mode "$SANDBOX")
    [ -n "$THEME" ]    && ops+=(set theme "$THEME")
    local p
    for p in "${PROVIDERS[@]}"; do
        case "$p" in
            *=*) ;;
            *) die "--provider 需要 NAME=base_url=ENV_KEY[=wire_api] 格式: $p";;
        esac
        ops+=(provider "$p")
    done
    if [ ${#ops[@]} -eq 0 ]; then
        printf '无参数变更请求（使用 --help 查看可用选项）\n'
        return 0
    fi

    # merge_toml 退出码: 0=有变更 1=无变更 2=参数错误
    local merged rc
    merged="$(merge_toml "${ops[@]}")"
    rc=$?
    case $rc in
        0) ;;
        1) printf 'config.toml: 无变更\n'; return 0;;
        2) exit 2;;
        *) die "merge_toml 异常退出 ($rc)";;
    esac
    write_config "$merged"
    [ "$APPLY" = 1 ] && printf '\n提示: provider 条目需配合 env_key 对应的环境变量使用；修改后重启 codex 生效。\n'
}

main "$@"