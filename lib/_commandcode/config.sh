#!/usr/bin/env bash
# Idempotently merge user-level Command Code preferences and settings.
# Default is dry-run; --apply backs up and writes both JSON files atomically.
# Usage: bash config.sh [options]

set -euo pipefail
umask 077

config_dir="${HOME:?HOME is required}/.commandcode"
config_file="$config_dir/config.json"
settings_file="$config_dir/settings.json"

apply=0
model=""
provider=""
theme=""
compact_mode=""
effort=""
taste=""
artifacts=""
collapse_pasted_text=""
local_only=""
permission_mode=""
disable_bypass=""
allow_rules=()
ask_rules=()
deny_rules=()
extra_directories=()
skill_directories=()
config_ops=()
settings_ops=()
temp_file=""

cleanup() {
    if [ -n "$temp_file" ]; then
        rm -f "$temp_file"
    fi
}
trap cleanup EXIT HUP INT TERM

usage() {
    cat <<EOF
用法: bash config.sh [选项]

  --check                        检查安装与现有配置（只读）
  --apply                        写入配置（默认 dry-run）
  --provider NAME                认证 provider: command-code|anthropic|github-copilot|codex
  --model MODEL                  默认模型，格式由 Command Code 模型目录定义
  --theme auto|dark|light        终端主题
  --compact-mode default|fast    自动压缩策略
  --effort LEVEL                 全局推理强度: low|medium|high|xhigh|max
  --reasoning-effort MODEL=LEVEL 为指定模型覆盖推理强度（可重复）
  --permission-mode MODE         默认权限模式: default|accept-edits|plan|yolo|dont-ask
  --allow RULE                   添加权限 allow 规则（可重复）
  --ask RULE                     添加权限 ask 规则（可重复）
  --deny RULE                    添加权限 deny 规则（可重复）
  --disable-bypass on|off        禁止/恢复 yolo 权限绕过
  --extra-dir PATH               添加工作区外目录（可重复）
  --skill PATH                   添加额外技能目录（可重复）
  --taste on|off                 开关 taste 学习
  --artifacts on|off             开关 artifact 工具
  --collapse-pasted-text on|off  开关长粘贴折叠
  --local-only on|off            开关 local-only 模式
  -h, --help                     显示帮助

文件:
  $config_file
  $settings_file

配置器只合并 JSON 对象并保留未知字段；不会写入 API key、token 或项目目录。
EOF
}

die() {
    printf '错误: %s\n' "$1" >&2
    exit 1
}

require_argument() {
    [ "$#" -ge 2 ] || die "$1 需要参数"
}

validate_text() {
    local label="$1" value="$2"
    [ -n "$value" ] || die "$label 不能为空"
    case "$value" in
        *$'\n'*|*$'\r'*) die "$label 不能包含换行" ;;
    esac
}

parse_boolean() {
    case "$1" in
        on|true|1) printf 'true' ;;
        off|false|0) printf 'false' ;;
        *) return 1 ;;
    esac
}

command_binary() {
    if command -v command-code >/dev/null 2>&1; then
        command -v command-code
    elif command -v cmdc >/dev/null 2>&1; then
        command -v cmdc
    elif command -v cmd >/dev/null 2>&1; then
        command -v cmd
    else
        return 1
    fi
}

check_status() {
    local program version
    if program="$(command_binary)"; then
        version="$("$program" --version 2>/dev/null | sed -n '1p' || true)"
        printf 'command-code: %s\n' "${version:-版本未知}"
        printf '可执行文件: %s\n' "$program"
    else
        printf 'command-code: 未安装（见同目录 install.sh / install.bat）\n'
    fi

    printf '配置目录: %s\n' "$config_dir"
    if [ -f "$config_file" ]; then
        printf 'config.json: 存在 (%s 字节)\n' "$(wc -c < "$config_file" | tr -d ' ')"
    else
        printf 'config.json: 不存在\n'
    fi
    if [ -f "$settings_file" ]; then
        printf 'settings.json: 存在 (%s 字节)\n' "$(wc -c < "$settings_file" | tr -d ' ')"
    else
        printf 'settings.json: 不存在\n'
    fi

    if [ -f "$config_file" ]; then
        python3 - "$config_file" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        data = json.load(handle)
    print(f"默认模型: {data.get('model', '（未设置）')}")
    print(f"主题: {data.get('theme', 'auto')}")
    print(f"local-only: {data.get('localOnly', False)}")
except Exception as error:
    print(f"config.json 解析失败: {error}")
PY
    fi

    if [ -f "$settings_file" ]; then
        python3 - "$settings_file" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        data = json.load(handle)
    permissions = data.get("permissions", {})
    print(f"默认权限模式: {permissions.get('defaultMode', 'default')}")
    for key in ("allow", "ask", "deny", "additionalDirectories"):
        value = permissions.get(key, [])
        print(f"权限 {key}: {len(value) if isinstance(value, list) else '格式异常'}")
except Exception as error:
    print(f"settings.json 解析失败: {error}")
PY
    fi
}

load_json_object() {
    local file="$1"
    python3 - "$file" <<'PY'
import json
import os
import sys

path = sys.argv[1]
if not os.path.exists(path):
    print("{}")
    raise SystemExit(0)
try:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("顶层必须是 JSON 对象")
    print(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
except Exception as error:
    print(f"无法读取 {path}: {error}", file=sys.stderr)
    raise SystemExit(1)
PY
}

merge_config() {
    python3 - "$config_file" "${config_ops[@]}" <<'PY'
import json
import os
import sys

path = sys.argv[1]
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as error:
        print(f"无法读取 {path}: {error}", file=sys.stderr)
        raise SystemExit(1)
else:
    data = {}
if not isinstance(data, dict):
    print(f"无法读取 {path}: 顶层必须是 JSON 对象", file=sys.stderr)
    raise SystemExit(1)

for operation in sys.argv[2:]:
    kind, payload = operation.split(":", 1)
    key, value = payload.split("=", 1)
    if kind == "string":
        data[key] = value
    elif kind == "bool":
        data[key] = value == "true"
    elif kind == "reasoning":
        efforts = data.setdefault("reasoningEffort", {})
        if not isinstance(efforts, dict):
            raise SystemExit(f"{path}: reasoningEffort 必须是 JSON 对象")
        efforts[key] = value
    else:
        raise SystemExit(f"内部错误: 未知 config 操作 {kind}")

print(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
PY
}

merge_settings() {
    python3 - "$settings_file" "${settings_ops[@]}" <<'PY'
import json
import os
import sys

path = sys.argv[1]
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as error:
        print(f"无法读取 {path}: {error}", file=sys.stderr)
        raise SystemExit(1)
else:
    data = {}
if not isinstance(data, dict):
    print(f"无法读取 {path}: 顶层必须是 JSON 对象", file=sys.stderr)
    raise SystemExit(1)

def parent_for(key, create):
    parts = key.split(".")
    current = data
    for part in parts[:-1]:
        if part not in current:
            if not create:
                return None, parts[-1]
            current[part] = {}
        if not isinstance(current[part], dict):
            raise SystemExit(f"{path}: {part} 必须是 JSON 对象")
        current = current[part]
    return current, parts[-1]

for operation in sys.argv[2:]:
    kind, payload = operation.split(":", 1)
    key, value = payload.split("=", 1)
    parent, leaf = parent_for(key, kind != "pop")
    if parent is None:
        continue
    if kind == "string":
        parent[leaf] = value
    elif kind == "set":
        parent[leaf] = value == "true"
    elif kind == "list":
        items = parent.setdefault(leaf, [])
        if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
            raise SystemExit(f"{path}: {key} 必须是字符串数组")
        if value not in items:
            items.append(value)
    elif kind == "pop":
        parent.pop(leaf, None)
    else:
        raise SystemExit(f"内部错误: 未知 settings 操作 {kind}")

print(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
PY
}

write_json() {
    local file="$1" payload="$2"
    if [ "$apply" -ne 1 ]; then
        printf '[dry-run] 将写: %s\n' "$file"
        printf '%s' "$payload" | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin), ensure_ascii=False, sort_keys=True, indent=2))'
        return 0
    fi

    mkdir -p "$(dirname "$file")"
    if [ -f "$file" ]; then
        local backup="$file.bak.$(date +%Y%m%d-%H%M%S)"
        [ ! -e "$backup" ] || backup="$backup-$$"
        cp -p "$file" "$backup"
        printf '已备份: %s\n' "$backup"
    fi

    temp_file="$file.tmp.$$"
    printf '%s' "$payload" | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin), ensure_ascii=False, sort_keys=True, indent=2))' > "$temp_file"
    chmod 0600 "$temp_file"
    mv "$temp_file" "$file"
    temp_file=""
    printf '已写: %s\n' "$file"
}

main() {
    [ "$#" -eq 0 ] && usage && exit 0

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --check)
                command -v python3 >/dev/null 2>&1 || die "需要 python3 读取 JSON；本脚本不自动安装依赖"
                check_status
                return 0
                ;;
            --apply)
                apply=1
                shift
                ;;
            --provider)
                require_argument "$@"
                provider="$2"
                case "$provider" in
                    command-code|anthropic|github-copilot|codex) ;;
                    *) die "--provider 仅接受 command-code|anthropic|github-copilot|codex" ;;
                esac
                shift 2
                ;;
            --model)
                require_argument "$@"
                model="$2"
                validate_text "--model" "$model"
                shift 2
                ;;
            --theme)
                require_argument "$@"
                theme="$2"
                case "$theme" in
                    auto|dark|light) ;;
                    *) die "--theme 仅接受 auto|dark|light" ;;
                esac
                shift 2
                ;;
            --compact-mode)
                require_argument "$@"
                compact_mode="$2"
                case "$compact_mode" in
                    default|fast) ;;
                    *) die "--compact-mode 仅接受 default|fast" ;;
                esac
                shift 2
                ;;
            --effort)
                require_argument "$@"
                effort="$2"
                case "$effort" in
                    low|medium|high|xhigh|max) ;;
                    *) die "--effort 仅接受 low|medium|high|xhigh|max" ;;
                esac
                shift 2
                ;;
            --reasoning-effort)
                require_argument "$@"
                case "$2" in
                    *=*) ;;
                    *) die "--reasoning-effort 需要 MODEL=LEVEL" ;;
                esac
                reasoning_model="${2%%=*}"
                reasoning_level="${2#*=}"
                validate_text "--reasoning-effort MODEL" "$reasoning_model"
                case "$reasoning_level" in
                    low|medium|high|xhigh|max) ;;
                    *) die "--reasoning-effort LEVEL 仅接受 low|medium|high|xhigh|max" ;;
                esac
                config_ops+=("reasoning:$reasoning_model=$reasoning_level")
                shift 2
                ;;
            --permission-mode)
                require_argument "$@"
                case "$2" in
                    default|standard|manual) permission_mode="default" ;;
                    accept-edits|auto-accept|acceptEdits) permission_mode="accept-edits" ;;
                    plan) permission_mode="plan" ;;
                    yolo|bypass|bypassPermissions) permission_mode="yolo" ;;
                    dont-ask|dontAsk) permission_mode="dont-ask" ;;
                    *) die "--permission-mode 接受 default|accept-edits|plan|yolo|dont-ask" ;;
                esac
                shift 2
                ;;
            --allow|--ask|--deny)
                require_argument "$@"
                option="$1"
                rule="$2"
                validate_text "$option" "$rule"
                case "$option" in
                    --allow) allow_rules+=("$rule") ;;
                    --ask) ask_rules+=("$rule") ;;
                    --deny) deny_rules+=("$rule") ;;
                esac
                shift 2
                ;;
            --disable-bypass)
                require_argument "$@"
                if ! disable_bypass="$(parse_boolean "$2")"; then
                    die "--disable-bypass 仅接受 on|off"
                fi
                shift 2
                ;;
            --extra-dir)
                require_argument "$@"
                validate_text "--extra-dir" "$2"
                extra_directories+=("$2")
                shift 2
                ;;
            --skill)
                require_argument "$@"
                validate_text "--skill" "$2"
                skill_directories+=("$2")
                shift 2
                ;;
            --taste|--artifacts|--collapse-pasted-text|--local-only)
                require_argument "$@"
                option="$1"
                if ! boolean_value="$(parse_boolean "$2")"; then
                    die "$option 仅接受 on|off"
                fi
                case "$option" in
                    --taste) taste="$boolean_value" ;;
                    --artifacts) artifacts="$boolean_value" ;;
                    --collapse-pasted-text) collapse_pasted_text="$boolean_value" ;;
                    --local-only) local_only="$boolean_value" ;;
                esac
                shift 2
                ;;
            -h|--help)
                usage
                return 0
                ;;
            *)
                die "未知选项: $1（用法见 --help）"
                ;;
        esac
    done

    command -v python3 >/dev/null 2>&1 || die "需要 python3 合并 JSON；本脚本不自动安装依赖"

    [ -n "$provider" ] && config_ops+=("string:provider=$provider")
    [ -n "$model" ] && config_ops+=("string:model=$model")
    [ -n "$theme" ] && config_ops+=("string:theme=$theme")
    [ -n "$compact_mode" ] && config_ops+=("string:compactMode=$compact_mode")
    [ -n "$taste" ] && config_ops+=("bool:tasteLearning=$taste")
    [ -n "$artifacts" ] && config_ops+=("bool:artifactsEnabled=$artifacts")
    [ -n "$collapse_pasted_text" ] && config_ops+=("bool:collapsePastedText=$collapse_pasted_text")
    [ -n "$local_only" ] && config_ops+=("bool:localOnly=$local_only")

    [ -n "$effort" ] && settings_ops+=("string:effort=$effort")
    [ -n "$permission_mode" ] && settings_ops+=("string:permissions.defaultMode=$permission_mode")
    case "$disable_bypass" in
        true) settings_ops+=("set:permissions.disableBypass=true") ;;
        false) settings_ops+=("pop:permissions.disableBypass=") ;;
    esac
    for rule in "${allow_rules[@]}"; do
        settings_ops+=("list:permissions.allow=$rule")
    done
    for rule in "${ask_rules[@]}"; do
        settings_ops+=("list:permissions.ask=$rule")
    done
    for rule in "${deny_rules[@]}"; do
        settings_ops+=("list:permissions.deny=$rule")
    done
    for directory in "${extra_directories[@]}"; do
        settings_ops+=("list:permissions.additionalDirectories=$directory")
    done
    for directory in "${skill_directories[@]}"; do
        settings_ops+=("list:skills=$directory")
    done

    config_changed=0
    settings_changed=0
    current_config=""
    merged_config=""
    current_settings=""
    merged_settings=""

    if [ "${#config_ops[@]}" -gt 0 ]; then
        current_config="$(load_json_object "$config_file")"
        merged_config="$(merge_config)"
        if [ "$merged_config" != "$current_config" ]; then
            config_changed=1
        fi
    fi

    if [ "${#settings_ops[@]}" -gt 0 ]; then
        current_settings="$(load_json_object "$settings_file")"
        merged_settings="$(merge_settings)"
        if [ "$merged_settings" != "$current_settings" ]; then
            settings_changed=1
        fi
    fi

    if [ "$config_changed" -eq 1 ]; then
        write_json "$config_file" "$merged_config"
    elif [ "${#config_ops[@]}" -gt 0 ]; then
        printf 'config.json: 无变更\n'
    fi

    if [ "$settings_changed" -eq 1 ]; then
        write_json "$settings_file" "$merged_settings"
    elif [ "${#settings_ops[@]}" -gt 0 ]; then
        printf 'settings.json: 无变更\n'
    fi

    if [ "$config_changed" -eq 0 ] && [ "$settings_changed" -eq 0 ]; then
        printf '全部无变更（未提供写入参数或配置已是最新）\n'
    elif [ "$apply" -eq 1 ]; then
        printf '\n提示: 配置不保存原始密钥；BYOK 请使用 /connect 或 $ENV_VAR 引用。\n'
    fi
}

main "$@"
