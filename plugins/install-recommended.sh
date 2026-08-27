#!/usr/bin/env bash
set -Eeuo pipefail

# 只调用 Codex 的 marketplace 命令；不复制第三方源码、不安装 npm 依赖、不删除插件。
DEFAULT_PROFILE="recommended"
REF="${CODEX_PLUGIN_REF:-main}"
DRY_RUN=false
PROFILE=""
REQUESTED=()

usage() {
  cat <<'EOF'
用法：install-recommended.sh [选项] [插件名 ...]

默认安装 recommended profile。也可以选择 profile 或逐个指定插件：
  --profile NAME       core、recommended、gpu-research、bioinformatics、
                       engineering、orchestration、all
  --ref REF            marketplace Git ref；默认读取 CODEX_PLUGIN_REF 或 main
  --dry-run            只打印命令，不写入 Codex 配置
  --list               列出可安装的推荐项
  -h, --help           显示帮助

示例：
  ./install-recommended.sh
  ./install-recommended.sh --profile gpu-research
  ./install-recommended.sh ecc agent-skills
  ./install-recommended.sh --ref v2.1.0 ecc
  ./install-recommended.sh --profile all --dry-run

说明：
  - 需要 Codex CLI 的 `codex plugin marketplace` 和 `codex plugin add` 子命令。
  - 官方插件优先复用当前已配置的官方 marketplace；没有时注册 openai/plugins。
  - 重复注册和重复安装由 Codex 处理；脚本不会自动信任 hooks。
  - CODEX_PLUGIN_REF 可用于将社区 marketplace 固定到 tag 或 commit。
EOF
}

die() {
  printf '错误：%s\n' "$1" >&2
  exit 1
}

show_cmd() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
}

run_cmd() {
  show_cmd "$@"
  if [[ "$DRY_RUN" != true ]]; then
    "$@"
  fi
}

plugin_spec() {
  case "$1" in
    superpowers)             printf '%s\n' 'official|openai/plugins|openai-curated|superpowers' ;;
    nvidia)                  printf '%s\n' 'official|openai/plugins|openai-curated|nvidia' ;;
    zotero)                  printf '%s\n' 'official|openai/plugins|openai-curated|zotero' ;;
    ngs-analysis)            printf '%s\n' 'official|openai/plugins|openai-curated|ngs-analysis' ;;
    life-science-research)   printf '%s\n' 'official|openai/plugins|openai-curated|life-science-research' ;;
    ecc)                     printf '%s\n' 'community|affaan-m/ECC|ecc|ecc' ;;
    agent-skills)            printf '%s\n' 'community|addyosmani/agent-skills|agent-skills|agent-skills' ;;
    compound-engineering)   printf '%s\n' 'community|EveryInc/compound-engineering-plugin|compound-engineering-plugin|compound-engineering' ;;
    babysitter)              printf '%s\n' 'community|a5c-ai/babysitter-codex|babysitter|babysitter' ;;
    *) return 1 ;;
  esac
}

profile_plugins() {
  case "$1" in
    core)             printf '%s\n' superpowers ;;
    recommended)      printf '%s\n' superpowers nvidia zotero ;;
    gpu-research)     printf '%s\n' nvidia zotero ;;
    bioinformatics)   printf '%s\n' life-science-research ngs-analysis ;;
    engineering)      printf '%s\n' ecc agent-skills compound-engineering ;;
    orchestration)    printf '%s\n' babysitter ;;
    all)              printf '%s\n' superpowers nvidia zotero life-science-research ngs-analysis ecc agent-skills compound-engineering babysitter ;;
    *) return 1 ;;
  esac
}

print_catalog() {
  cat <<'EOF'
可安装推荐项：
  superpowers             官方：规划、TDD、调试与交付流程
  nvidia                  官方：CUDA、GPU、推理、机器人与仿真
  zotero                  官方：Zotero 文献检索、BibTeX 与引用
  ngs-analysis            官方：NGS/FASTQ/BCL 及测序分析路由
  life-science-research   官方：生命科学检索与证据综合
  ecc                     社区：TDD、安全、审查与自主开发工作流
  agent-skills            社区：规格、计划、实现、测试、审查与发布
  compound-engineering    社区：brainstorm → plan → build → review → compound
  babysitter              社区：事件溯源的复杂流程编排与人工审批

profile：core、recommended、gpu-research、bioinformatics、engineering、
orchestration、all。
EOF
}

require_json_parser() {
  if command -v jq >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1; then
    return 0
  fi
  die '需要 jq 或 python3 解析 Codex 的 JSON 输出；脚本不会自动安装依赖。'
}

json_has_marketplace() {
  local marketplace="$1"
  local json="$2"
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$json" | jq -e --arg name "$marketplace" \
      'any((.marketplaces // [])[]; .name == $name)' >/dev/null 2>&1
    return
  fi
  printf '%s' "$json" | python3 -c 'import json, sys
name = sys.argv[1]
try:
    data = json.load(sys.stdin)
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if any(item.get("name") == name for item in data.get("marketplaces", [])) else 1)' "$marketplace" 2>/dev/null
}

configured_marketplace_for_plugin() {
  local plugin="$1"
  local json
  json="$(codex plugin list --available --json 2>/dev/null || true)"
  [[ -n "$json" ]] || return 0

  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$json" | jq -r --arg name "$plugin" \
      '((.installed // []) + (.available // []))[]
       | select(.name == $name and ((.marketplaceName // "") | startswith("openai")))
       | .marketplaceName' 2>/dev/null | sed -n '1p'
    return 0
  fi
  printf '%s' "$json" | python3 -c 'import json, sys
name = sys.argv[1]
try:
    data = json.load(sys.stdin)
except Exception:
    raise SystemExit(0)
for item in (data.get("installed", []) + data.get("available", [])):
    marketplace = item.get("marketplaceName", "")
    if item.get("name") == name and marketplace.startswith("openai"):
        print(marketplace)
        break' "$plugin" 2>/dev/null
}

marketplace_is_configured() {
  local marketplace="$1"
  local json
  json="$(codex plugin marketplace list --json 2>/dev/null || true)"
  [[ -n "$json" ]] && json_has_marketplace "$marketplace" "$json"
}

plugin_is_installed() {
  local plugin="$1"
  local json
  json="$(codex plugin list --json 2>/dev/null || true)"
  [[ -n "$json" ]] || return 1

  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$json" | jq -e --arg name "$plugin" \
      'any((.installed // [])[]; .name == $name and .installed == true)' >/dev/null 2>&1
    return
  fi
  printf '%s' "$json" | python3 -c 'import json, sys
name = sys.argv[1]
try:
    data = json.load(sys.stdin)
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if any(item.get("name") == name and item.get("installed") is True for item in data.get("installed", [])) else 1)' "$plugin" 2>/dev/null
}

ensure_community_marketplace() {
  local source="$1"
  local marketplace="$2"
  if [[ "$DRY_RUN" == true ]]; then
    run_cmd codex plugin marketplace add "$source" --ref "$REF"
  elif marketplace_is_configured "$marketplace"; then
    printf '已复用 marketplace：%s\n' "$marketplace"
  else
    run_cmd codex plugin marketplace add "$source" --ref "$REF"
  fi
}

official_marketplace_for() {
  local plugin="$1"
  local marketplace
  if [[ "$DRY_RUN" == true ]] && ! command -v codex >/dev/null 2>&1; then
    printf '%s\n' openai-curated
    return 0
  fi
  if ! command -v jq >/dev/null 2>&1 && ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' openai-curated
    return 0
  fi
  marketplace="$(configured_marketplace_for_plugin "$plugin")"
  if [[ -n "$marketplace" ]]; then
    printf '%s\n' "$marketplace"
    return 0
  fi
  run_cmd codex plugin marketplace add openai/plugins --ref "$REF" \
    --sparse .agents/plugins --sparse plugins >&2 || return 1
  printf '%s\n' openai-curated
}

install_one() {
  local key="$1"
  local spec kind source marketplace plugin
  spec="$(plugin_spec "$key")" || {
    printf '未知插件：%s（使用 --list 查看可用名称）\n' "$key" >&2
    return 1
  }
  IFS='|' read -r kind source marketplace plugin <<<"$spec"

  case "$key" in
    superpowers|ecc|agent-skills|compound-engineering)
      printf '提示：%s 与本库或彼此存在技能职责重叠，安装后请确认触发优先级。\n' "$key" ;;
  esac
  if [[ "$key" == ecc || "$key" == babysitter ]]; then
    printf '提示：%s 含 hooks/MCP 或运行时集成；安装后需单独审查并信任相关 hooks。\n' "$key"
  fi
  if [[ "$key" == babysitter ]]; then
    printf '提示：Babysitter 的完整运行还需要按上游说明安装其 CLI/SDK；本脚本不隐式安装 npm 依赖。\n'
  fi

  if [[ "$kind" == official ]]; then
    marketplace="$(official_marketplace_for "$plugin")"
  else
    ensure_community_marketplace "$source" "$marketplace" || return 1
  fi
  run_cmd codex plugin add "$plugin" --marketplace "$marketplace" || return 1

  if [[ "$DRY_RUN" != true ]]; then
    if plugin_is_installed "$plugin"; then
      printf '已验证插件注册：%s@%s\n' "$plugin" "$marketplace"
    else
      printf '警告：命令已返回成功，但未在 codex plugin list --json 中找到：%s\n' "$plugin" >&2
      return 1
    fi
  fi
}

require_codex() {
  command -v codex >/dev/null 2>&1 || die '找不到 codex，请先安装 Codex CLI。'
  codex plugin marketplace --help >/dev/null 2>&1 || \
    die '当前 Codex 不支持 plugin marketplace；请升级到支持 marketplace 的 CLI。'
  codex plugin add --help >/dev/null 2>&1 || \
    die '当前 Codex 不支持 plugin add；请升级到支持插件安装的 CLI。'
  require_json_parser
}

warn_profile() {
  case "$1" in
    all|engineering)
      printf '提示：该 profile 含多个大体量或职责重叠插件；建议先用 --dry-run 复核。\n' ;;
    bioinformatics)
      printf '提示：生命科学插件的许可证和可用性以官方 marketplace 当前条目为准。\n' ;;
  esac
}

main() {
  while (($# > 0)); do
    case "$1" in
      --profile|-p)
        (($# >= 2)) || die "${1} 需要一个名称。"
        [[ -z "$PROFILE" ]] || die '不能重复指定 profile。'
        PROFILE="$2"
        shift 2
        ;;
      --ref)
        (($# >= 2)) || die '--ref 需要一个 Git ref。'
        REF="$2"
        shift 2
        ;;
      --dry-run)
        DRY_RUN=true
        shift
        ;;
      --list)
        print_catalog
        return 0
        ;;
      -h|--help)
        usage
        return 0
        ;;
      --)
        shift
        while (($# > 0)); do REQUESTED+=("$1"); shift; done
        ;;
      -*)
        die "未知选项：$1"
        ;;
      *)
        REQUESTED+=("$1")
        shift
        ;;
    esac
  done

  if [[ -n "$PROFILE" && ${#REQUESTED[@]} -gt 0 ]]; then
    die '不能同时指定 profile 和插件名。'
  fi

  local -a selected=()
  if [[ -n "$PROFILE" ]]; then
    mapfile -t selected < <(profile_plugins "$PROFILE" || true)
    ((${#selected[@]} > 0)) || die "未知 profile：$PROFILE"
    warn_profile "$PROFILE"
  elif ((${#REQUESTED[@]} > 0)); then
    selected=("${REQUESTED[@]}")
  else
    mapfile -t selected < <(profile_plugins "$DEFAULT_PROFILE")
    printf '未指定目标，使用默认 profile：%s\n' "$DEFAULT_PROFILE"
  fi

  [[ "$DRY_RUN" == true ]] || require_codex
  printf '目标插件：%s\n' "${selected[*]}"
  printf 'Git ref：%s\n' "$REF"
  [[ "$DRY_RUN" == true ]] && printf '模式：dry-run（不会写入 Codex 配置）\n'

  local -a failed=()
  local key
  for key in "${selected[@]}"; do
    printf '\n==> 安装 %s\n' "$key"
    if install_one "$key"; then
      printf '完成：%s\n' "$key"
    else
      failed+=("$key")
      printf '失败：%s（继续处理其余目标）\n' "$key" >&2
    fi
  done

  if ((${#failed[@]} > 0)); then
    printf '\n失败目标：%s\n' "${failed[*]}" >&2
    return 1
  fi
  printf '\n全部目标处理完成。需要时重启 Codex 或打开 /plugins 检查启用状态。\n'
}

main "$@"
