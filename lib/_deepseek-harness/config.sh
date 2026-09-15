#!/usr/bin/env bash
# DeepSeek Harness (dsh) 一键配置脚本（Linux / macOS）
# 幂等合并生成 $DSH_HOME/settings.yaml 与 $DSH_HOME/.credentials.yaml，保留已有键与注释；
# 默认仅打印与检查，--apply 才写盘。
# Usage: bash config.sh [选项]

set -euo pipefail

DSH_DIR="${DSH_HOME:-$HOME/.dsh}"
SETTINGS_FILE="$DSH_DIR/settings.yaml"
CRED_FILE="$DSH_DIR/.credentials.yaml"

APPLY=0
BASE_URL=""
API_KEY_ENV=""
THINKING=""
EFFORT=""
MAX_TOKENS=""
MODEL=""
PROVIDER=""
SET_KEY=""
KEY_FROM_ENV=""
KEY_FROM_ENV_SET=0
UNSET_KEY=0

list_models() {
    cat <<'EOF'
推荐模型（deepseek-official 路由；未列出的 id 仍可透传，由端点自行校验）:
  deepseek-flash                   V4.1 Flash，默认；支持 systemPromptUpdate=in-history
  deepseek-v4-flash                V4 Flash，纯文本
  deepseek-v4-pro                  V4 Pro，纯文本
  deepseek-v4-flash-vision-exp     V4 Flash Vision 实验版，支持图片输入
说明: 上下文窗口约 1,000,000 token；模型 id 以 DeepSeek 官方文档为准。
EOF
}

list_efforts() {
    cat <<'EOF'
推理强度（llm-deepseek.reasoningEffort / agent-default-model.reasoningEffort）:
  off    关闭思考
  low    低强度
  high   默认
  max    最大强度
EOF
}

usage() {
    cat <<EOF
用法: bash config.sh [选项]

  --check                检查 dsh 安装与现有配置（只读，不打印任何密钥）
  --apply                合并并写盘（默认 dry-run；写盘前自动备份旧文件）
  --base-url URL         设置 llm-deepseek.baseURL（默认 https://api.deepseek.com）
  --api-key-env NAME     设置 llm-deepseek.apiKeyEnv（凭证引用，默认 DEEPSEEK_API_KEY）
  --thinking MODE        设置 llm-deepseek.thinking: enabled|disabled
  --reasoning-effort E   设置默认推理强度: off|low|high|max（写 llm-deepseek；与 --model 同用时同步 agent-default-model）
  --max-tokens N         设置 llm-deepseek.maxTokens（正整数）
  --model MODEL          设置默认模型（agent-default-model.model；provider 默认 deepseek-official）
  --provider ROUTE       设置默认模型的 provider route（需与 --model 同用）
  --set-key VALUE        写入 $CRED_FILE 的 refs 条目；VALUE 为 - 时从 stdin 读取（不回显）
  --key-from-env [VAR]   从环境变量读取密钥写入（默认取 --api-key-env 或 DEEPSEEK_API_KEY；
                         显式给出 VAR 时同时作为凭证引用名，除非另有 --api-key-env）
  --unset-key            删除 refs 中的密钥条目
  --list-models          列出 DeepSeek 官方路由的常用模型 id
  --list-efforts         列出推理强度取值
  -h, --help             显示帮助

默认行为: 打印将要合并的 YAML 差异，不写盘；加 --apply 才写入。
配置位置: $SETTINGS_FILE 与 $CRED_FILE（合并保留已有键与注释；凭证文件强制 600）
认证:     API key 也可稍后在 dsh web 的 Settings → Models 中填写（二者等价）。
EOF
}

die() { printf '错误: %s\n' "$1" >&2; exit 1; }

require_python() {
    command -v python3 >/dev/null 2>&1 || die "需要 python3 合并 YAML；本脚本不自动安装依赖。"
}

# settings.yaml 幂等合并（纯文本行级操作，保留注释与未知内容）：
#   操作序列为 section key value 三元组；section 已存在则原位替换/块内插入，否则在文件末尾追加
merge_settings() {
    python3 - "$SETTINGS_FILE" "$@" <<'PY'
import re, sys

path, ops = sys.argv[1], sys.argv[2:]
if not ops or len(ops) % 3 != 0:
    print("错误: 内部操作序列非法", file=sys.stderr)
    sys.exit(2)

try:
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
except FileNotFoundError:
    lines = []

def scalar(v):
    if re.fullmatch(r"-?[0-9]+", v):
        return v
    return '"%s"' % v.replace("\\", "\\\\").replace('"', '\\"')

def section(lines, name):
    """返回 section 主体行区间 (start, end)；None 表示不存在；"inline" 表示内联映射。"""
    for i, ln in enumerate(lines):
        if not re.match(r"^%s\s*:" % re.escape(name), ln):
            continue
        rest = ln.split(":", 1)[1].strip()
        if rest and not rest.startswith("#"):
            return "inline"
        start = i + 1
        end = len(lines)
        for j in range(start, len(lines)):
            s = lines[j]
            if s and not s[0].isspace() and not s.lstrip().startswith("#"):
                end = j
                break
        return (start, end)
    return None

changed = False
i = 0
while i < len(ops):
    name, key, value = ops[i], ops[i + 1], ops[i + 2]
    i += 3
    loc = section(lines, name)
    if loc == "inline":
        print("错误: %s 为内联映射，无法安全编辑，请手动修改 %s" % (name, path), file=sys.stderr)
        sys.exit(3)
    key_re = re.compile(r"^(\s+)%s\s*:" % re.escape(key))
    if loc is None:
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.append("%s:" % name)
        lines.append("  %s: %s" % (key, scalar(value)))
        changed = True
        continue
    start, end = loc
    found = False
    for j in range(start, end):
        m = key_re.match(lines[j])
        if not m:
            continue
        indent = m.group(1)
        new_line = "%s%s: %s" % (indent, key, scalar(value))
        if lines[j].rstrip() != new_line:
            lines[j] = new_line
            changed = True
        found = True
        break
    if not found:
        indent = "  "
        if start < end:
            m = re.match(r"^(\s+)\S", lines[start])
            if m:
                indent = m.group(1)
        insert_at = end
        while insert_at > start and lines[insert_at - 1].strip() == "":
            insert_at -= 1
        lines.insert(insert_at, "%s%s: %s" % (indent, key, scalar(value)))
        changed = True

sys.stdout.write("\n".join(lines) + ("\n" if lines else ""))
sys.exit(0 if changed else 1)
PY
}

# .credentials.yaml 幂等合并：refs 段内 set/unset 一个引用，其余内容原样保留；
# 旧版扁平格式（无 version: 段）拒绝编辑，交由 dsh 启动时迁移。
merge_credentials() {
    python3 - "$CRED_FILE" "$@" <<'PY'
import os, re, sys

path, op, ref = sys.argv[1], sys.argv[2], sys.argv[3]
value = sys.argv[4] if len(sys.argv) > 4 else ""

if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", ref):
    print("错误: 凭证引用名不合法: %s" % ref, file=sys.stderr)
    sys.exit(2)

lines = []
if os.path.exists(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

def top_section(lines, name):
    for i, ln in enumerate(lines):
        if not re.match(r"^%s\s*:" % re.escape(name), ln):
            continue
        rest = ln.split(":", 1)[1].strip()
        if rest and not rest.startswith("#"):
            return "inline"
        start = i + 1
        end = len(lines)
        for j in range(start, len(lines)):
            s = lines[j]
            if s and not s[0].isspace() and not s.lstrip().startswith("#"):
                end = j
                break
        return (start, end)
    return None

has_version = any(re.match(r"^version\s*:", ln) for ln in lines)
loc = top_section(lines, "refs")
if loc == "inline":
    print("错误: refs 为内联映射，无法安全编辑: %s" % path, file=sys.stderr)
    sys.exit(3)
if loc is None:
    if lines and not has_version:
        print("错误: %s 疑似旧版扁平格式，请先启动一次 dsh 让其迁移，或手工编辑" % path, file=sys.stderr)
        sys.exit(3)
    if not lines:
        lines = ["version: 1", ""]
    if lines and lines[-1].strip() != "":
        lines.append("")
    lines.append("refs:")
    loc = (len(lines), len(lines))
start, end = loc

key_re = re.compile(r"^(\s+)%s\s*:" % re.escape(ref))
match = None
for j in range(start, end):
    m = key_re.match(lines[j])
    if m:
        match = (j, m.group(1))
        break

def continuation_end(j, end, indent):
    """一条引用若带更深缩进的续行（多行值），一并纳入替换/删除范围。"""
    k = j + 1
    while k < end and lines[k].strip() and (len(lines[k]) - len(lines[k].lstrip())) > len(indent):
        k += 1
    return k

if op == "set":
    if not re.fullmatch(r"\S+", value):
        print("错误: 密钥值不能为空或含空白字符；含空白/多行的值请手工编辑 %s" % path, file=sys.stderr)
        sys.exit(3)
    if match:
        j, indent = match
        k = continuation_end(j, end, indent)
        new_line = "%s%s: %s" % (indent, ref, value)
        if k == j + 1 and lines[j] == new_line:
            sys.exit(1)
        lines[j:k] = [new_line]
    else:
        indent = "  "
        if start < end:
            m = re.match(r"^(\s+)\S", lines[start])
            if m:
                indent = m.group(1)
        insert_at = end
        while insert_at > start and lines[insert_at - 1].strip() == "":
            insert_at -= 1
        lines.insert(insert_at, "%s%s: %s" % (indent, ref, value))
elif op == "unset":
    if not match:
        sys.exit(1)
    j, indent = match
    k = continuation_end(j, end, indent)
    del lines[j:k]
else:
    print("错误: 未知凭证操作 %s" % op, file=sys.stderr)
    sys.exit(2)

sys.stdout.write("\n".join(lines) + ("\n" if lines else ""))
sys.exit(0)
PY
}

write_file() {
    local file="$1" payload="$2" secret="${3:-0}"
    mkdir -p "$(dirname "$file")"
    if [ -f "$file" ]; then
        cp -p "$file" "$file.bak.$(date +%Y%m%d-%H%M%S)"
    fi
    printf '%s\n' "$payload" > "$file.tmp"
    if [ "$secret" = 1 ]; then
        chmod 600 "$file.tmp"
    fi
    mv "$file.tmp" "$file"
    if [ "$secret" = 1 ]; then
        chmod 600 "$file"
    fi
    printf '已写: %s\n' "$file"
}

settings_summary() {
    python3 - "$SETTINGS_FILE" <<'PY' 2>/dev/null || printf 'llm-deepseek: （解析跳过，需 python3 + PyYAML）\n'
import sys
try:
    import yaml
except ImportError:
    print("llm-deepseek: （需 PyYAML 解析，跳过）")
    sys.exit(0)
try:
    with open(sys.argv[1], encoding="utf-8") as f:
        d = yaml.safe_load(f) or {}
except Exception as e:
    print("配置解析失败: %s" % e)
    sys.exit(0)
ds = d.get("llm-deepseek") or {}
ad = d.get("agent-default-model") or {}
fields = []
for k in ("apiKeyEnv", "baseURL", "thinking", "reasoningEffort", "maxTokens"):
    if ds.get(k) is not None:
        fields.append("%s=%s" % (k, ds[k]))
print("llm-deepseek: " + ("; ".join(fields) if fields else "（无覆盖）"))
if isinstance(ad, dict) and ad:
    eff = (" effort=%s" % ad["reasoningEffort"]) if ad.get("reasoningEffort") else ""
    print("agent-default-model: %s/%s%s" % (ad.get("provider", "?"), ad.get("model", "?"), eff))
else:
    print("agent-default-model: （未设置，使用组合默认）")
PY
}

check_status() {
    local dsh_ver="未安装（见同目录 install.sh）"
    if command -v dsh >/dev/null 2>&1; then
        dsh_ver="$(dsh --version 2>/dev/null | head -1 || echo '版本未知')"
    fi
    printf 'dsh:      %s\n' "$dsh_ver"
    printf 'node:     %s\n' "$(node -v 2>/dev/null || echo '未安装')"
    printf 'npm:      %s\n' "$(npm -v 2>/dev/null || echo '未安装')"
    printf 'DSH_HOME: %s\n' "$DSH_DIR"

    if [ -f "$SETTINGS_FILE" ]; then
        printf 'settings.yaml: 存在 (%s 字节)\n' "$(wc -c < "$SETTINGS_FILE" | tr -d ' ')"
        settings_summary
    else
        printf 'settings.yaml: 不存在（全部走默认值；--apply 可创建）\n'
    fi

    if [ -f "$CRED_FILE" ]; then
        local mode
        mode="$(stat -c '%a' "$CRED_FILE" 2>/dev/null || stat -f '%Lp' "$CRED_FILE" 2>/dev/null || echo '?')"
        printf '.credentials.yaml: 存在 (%s 字节, 权限 %s)\n' "$(wc -c < "$CRED_FILE" | tr -d ' ')" "$mode"
        case "$mode" in
            600|400) ;;
            *) printf '  警告: 权限 %s 过宽，dsh 会拒绝加载；建议 chmod 600 %s\n' "$mode" "$CRED_FILE" ;;
        esac
    else
        printf '.credentials.yaml: 不存在\n'
    fi

    local ref="DEEPSEEK_API_KEY"
    local from_settings
    from_settings="$(python3 - "$SETTINGS_FILE" <<'PY' 2>/dev/null || true
import os, sys
p = sys.argv[1]
if os.path.exists(p):
    try:
        import yaml
        d = yaml.safe_load(open(p, encoding="utf-8")) or {}
        v = (d.get("llm-deepseek") or {}).get("apiKeyEnv")
        if isinstance(v, str) and v:
            print(v)
    except Exception:
        pass
PY
)"
    if [ -n "$from_settings" ]; then
        ref="$from_settings"
    fi

    local ref_ok=no
    case "$ref" in
        [A-Za-z_]*) case "$ref" in *[!A-Za-z0-9_]*) ;; *) ref_ok=yes ;; esac ;;
    esac

    local source=""
    if [ "$ref_ok" = yes ]; then
        if [ -n "${!ref:-}" ]; then
            source="环境变量 $ref"
        elif [ -f "$CRED_FILE" ] && grep -Eq "^[[:space:]]+$ref[[:space:]]*:" "$CRED_FILE"; then
            source="凭证文件"
        elif [ -f "$DSH_DIR/.env" ] && grep -Eq "^[[:space:]]*$ref=" "$DSH_DIR/.env"; then
            source="DSH_HOME/.env"
        elif [ -f "./.env" ] && grep -Eq "^[[:space:]]*$ref=" "./.env"; then
            source="项目 .env"
        fi
    fi
    if [ -n "$source" ]; then
        printf 'API key（ref %s）: 已配置（来源: %s）\n' "$ref" "$source"
    else
        printf 'API key（ref %s）: 未配置（dsh web → Settings → Models，或本脚本 --key-from-env --apply）\n' "$ref"
    fi
    printf '启动: dsh web   （无头模式: dsh --profile headless "<任务>"）\n'
}

main() {
    [ $# -eq 0 ] && usage && exit 0
    while [ $# -gt 0 ]; do
        case "$1" in
            --check)        check_status; return 0;;
            --apply)        APPLY=1; shift;;
            --base-url)     [ $# -ge 2 ] || die "--base-url 需要参数"; BASE_URL="$2"; shift 2;;
            --api-key-env)  [ $# -ge 2 ] || die "--api-key-env 需要参数"; API_KEY_ENV="$2"; shift 2;;
            --thinking)     [ $# -ge 2 ] || die "--thinking 需要参数"; THINKING="$2"; shift 2;;
            --reasoning-effort) [ $# -ge 2 ] || die "--reasoning-effort 需要参数"; EFFORT="$2"; shift 2;;
            --max-tokens)   [ $# -ge 2 ] || die "--max-tokens 需要参数"; MAX_TOKENS="$2"; shift 2;;
            --model)        [ $# -ge 2 ] || die "--model 需要参数"; MODEL="$2"; shift 2;;
            --provider)     [ $# -ge 2 ] || die "--provider 需要参数"; PROVIDER="$2"; shift 2;;
            --set-key)      [ $# -ge 2 ] || die "--set-key 需要参数（VALUE 或 -）"; SET_KEY="$2"; shift 2;;
            --key-from-env)
                case "${2:-}" in
                    ""|-*) KEY_FROM_ENV="${API_KEY_ENV:-DEEPSEEK_API_KEY}"; KEY_FROM_ENV_SET=1; shift;;
                    *)     KEY_FROM_ENV="$2"; KEY_FROM_ENV_SET=1; shift 2;;
                esac;;
            --unset-key)    UNSET_KEY=1; shift;;
            --list-models)  list_models; return 0;;
            --list-efforts) list_efforts; return 0;;
            -h|--help)      usage; return 0;;
            *) die "未知选项: $1（用法见 --help）";;
        esac
    done

    require_python

    case "$THINKING" in
        enabled|disabled|"") ;;
        *) die "--thinking 仅接受 enabled|disabled";;
    esac
    case "$EFFORT" in
        off|low|high|max|"") ;;
        *) die "--reasoning-effort 仅接受 off|low|high|max";;
    esac
    if [ -n "$MAX_TOKENS" ]; then
        case "$MAX_TOKENS" in
            ''|*[!0-9]*|0) die "--max-tokens 需要正整数";;
        esac
    fi
    if [ -n "$API_KEY_ENV" ]; then
        case "$API_KEY_ENV" in
            [A-Za-z_]*) case "$API_KEY_ENV" in *[!A-Za-z0-9_]*) die "--api-key-env 需为合法的环境变量名";; esac;;
            *) die "--api-key-env 需为合法的环境变量名";;
        esac
    fi
    if [ -n "$PROVIDER" ] && [ -z "$MODEL" ]; then
        die "--provider 需与 --model 同时使用"
    fi
    if [ "$UNSET_KEY" = 1 ] && { [ -n "$SET_KEY" ] || [ "$KEY_FROM_ENV_SET" = 1 ]; }; then
        die "--unset-key 不能与 --set-key/--key-from-env 同时使用"
    fi
    if [ "$KEY_FROM_ENV_SET" = 1 ] && [ -n "$SET_KEY" ]; then
        die "--set-key 与 --key-from-env 不能同时使用"
    fi

    local key_ref="${API_KEY_ENV:-${KEY_FROM_ENV:-DEEPSEEK_API_KEY}}"
    local key_op=0 key_value=""
    case "$key_ref" in
        [A-Za-z_]*) case "$key_ref" in *[!A-Za-z0-9_]*) die "凭证引用名不合法: $key_ref";; esac;;
        *) die "凭证引用名不合法: $key_ref";;
    esac
    if [ -n "$SET_KEY" ]; then
        if [ "$SET_KEY" = "-" ]; then
            printf '请输入密钥（输入不回显）: ' >&2
            IFS= read -rs key_value || true
            printf '\n' >&2
            [ -n "$key_value" ] || die "未从标准输入读取到密钥"
        else
            key_value="$SET_KEY"
        fi
        key_op=1
    elif [ "$KEY_FROM_ENV_SET" = 1 ]; then
        key_value="${!KEY_FROM_ENV:-}"
        [ -n "$key_value" ] || die "环境变量 $KEY_FROM_ENV 未设置或为空"
        key_op=1
    elif [ "$UNSET_KEY" = 1 ]; then
        key_op=2
    fi
    if [ "$key_op" = 1 ]; then
        case "$key_value" in
            *[[:space:]]*) die "密钥含空白字符；含空白/多行的值请手工编辑 $CRED_FILE";;
        esac
    fi

    local ops=()
    [ -n "$BASE_URL" ] && ops+=(llm-deepseek baseURL "$BASE_URL")
    [ -n "$API_KEY_ENV" ] && ops+=(llm-deepseek apiKeyEnv "$API_KEY_ENV")
    [ -n "$THINKING" ] && ops+=(llm-deepseek thinking "$THINKING")
    [ -n "$EFFORT" ] && ops+=(llm-deepseek reasoningEffort "$EFFORT")
    [ -n "$MAX_TOKENS" ] && ops+=(llm-deepseek maxTokens "$MAX_TOKENS")
    if [ -n "$MODEL" ]; then
        ops+=(agent-default-model provider "${PROVIDER:-deepseek-official}")
        ops+=(agent-default-model model "$MODEL")
        [ -n "$EFFORT" ] && ops+=(agent-default-model reasoningEffort "$EFFORT")
    fi

    local requested=0
    [ ${#ops[@]} -gt 0 ] && requested=1
    [ "$key_op" != 0 ] && requested=1

    local settings_payload="" settings_rc=0 have_settings=0
    if [ ${#ops[@]} -gt 0 ]; then
        settings_payload="$(merge_settings "${ops[@]}")" || settings_rc=$?
        case $settings_rc in
            0) have_settings=1;;
            1) printf 'settings.yaml: 无变更\n';;
            2) exit 2;;
            3) exit 3;;
            *) die "merge_settings 异常退出 ($settings_rc)";;
        esac
    fi

    local cred_payload="" cred_rc=0 have_cred=0
    if [ "$key_op" = 1 ]; then
        cred_payload="$(merge_credentials set "$key_ref" "$key_value")" || cred_rc=$?
    elif [ "$key_op" = 2 ]; then
        cred_payload="$(merge_credentials unset "$key_ref")" || cred_rc=$?
    fi
    if [ "$key_op" != 0 ]; then
        case $cred_rc in
            0) have_cred=1;;
            1) printf '.credentials.yaml: 无变更\n';;
            2) exit 2;;
            3) exit 3;;
            *) die "merge_credentials 异常退出 ($cred_rc)";;
        esac
    fi

    if [ "$requested" = 0 ]; then
        printf '无参数变更请求（使用 --help 查看可用选项）\n'
        return 0
    fi
    if [ "$have_settings" = 0 ] && [ "$have_cred" = 0 ]; then
        return 0
    fi

    if [ "$APPLY" != 1 ]; then
        if [ "$have_settings" = 1 ]; then
            printf '[dry-run] 将写: %s\n%s\n' "$SETTINGS_FILE" "$settings_payload"
        fi
        if [ "$have_cred" = 1 ]; then
            if [ "$key_op" = 1 ]; then
                printf '[dry-run] 将写: %s\n  refs.%s: <redacted>\n' "$CRED_FILE" "$key_ref"
            else
                printf '[dry-run] 将删: %s\n  refs.%s\n' "$CRED_FILE" "$key_ref"
            fi
        fi
        return 0
    fi

    if [ "$have_settings" = 1 ]; then
        write_file "$SETTINGS_FILE" "$settings_payload" 0
    fi
    if [ "$have_cred" = 1 ]; then
        write_file "$CRED_FILE" "$cred_payload" 1
    fi
    printf '\n提示: settings.yaml 与 .credentials.yaml 均热加载，修改在下一个请求生效，无需重启 dsh。\n'
}

main "$@"
