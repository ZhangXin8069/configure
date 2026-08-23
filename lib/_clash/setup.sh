#!/usr/bin/env bash
# setup.sh — 解压 clash-for-linux.tar.gz 并通过 source env.sh 检验代理
# 路径解析参考 /root/configure/bin/gpull.sh（BASH_SOURCE + git rev-parse 兼容）
# 用法：
#   bash setup.sh                # 解压并检验（默认）
#   bash setup.sh --check        # 仅检验已解压的 env.sh，不解压
#   source setup.sh              # 同上（source 时不执行，仅定义函数）

set -euo pipefail
sed -i 's/\r$//' "$0" 2>/dev/null || true

# ── 路径解析（动态化，不硬编码 /root/...） ──────────────────────────
_SETUP_SRC="${BASH_SOURCE[0]:-${0}}"
_SETUP_DIR="$(cd "$(dirname "${_SETUP_SRC}")" 2>/dev/null && pwd)" || _SETUP_DIR="$(pwd)"
# 兼容 git 仓库根探测（参考 gpull.sh），若 _SETUP_DIR 不含 clash-for-linux.tar.gz 则尝试 git top-level
if [ ! -f "${_SETUP_DIR}/clash-for-linux.tar.gz" ]; then
  _SETUP_GIT_ROOT="$(git -C "${_SETUP_DIR}" rev-parse --show-toplevel 2>/dev/null || true)"
  if [ -n "${_SETUP_GIT_ROOT}" ] && [ -f "${_SETUP_GIT_ROOT}/lib/_clash/clash-for-linux.tar.gz" ]; then
    _SETUP_DIR="${_SETUP_GIT_ROOT}/lib/_clash"
  fi
fi

TARBALL="${_SETUP_DIR}/clash-for-linux.tar.gz"
TARGET_DIR="${_SETUP_DIR}/clash-for-linux"
ENV_FILE="${TARGET_DIR}/env.sh"

# ── 工具函数 ─────────────────────────────────────────────────────────
_setup_log()  { echo "ℹ️  $*" ; }
_setup_ok()   { echo "✅ $*" ; }
_setup_warn() { echo "⚠️  $*" >&2 ; }
_setup_err()  { echo "❌ $*" >&2 ; }

_setup_usage() {
  cat <<'EOF'
用法: bash setup.sh [选项]
  默认: 解压 clash-for-linux.tar.gz 到当前目录并通过 source env.sh 检验
选项:
  --check     仅检验已存在的 env.sh，不解压
  --help,-h   显示此帮助
环境变量:
  CLASH_ENV_TEST_URL / CLASH_ENV_TEST_TIMEOUT  透传给 env.sh 的检测参数
EOF
}

# 解压
setup_extract() {
  _setup_log "准备解压: ${TARBALL}"
  if [ ! -f "${TARBALL}" ]; then
    _setup_err "未找到压缩包: ${TARBALL}"
    return 1
  fi

  # 校验 tar 完整性（不解压）
  if ! tar -tzf "${TARBALL}" >/dev/null 2>&1; then
    _setup_err "压缩包损坏或非 gzip 格式: ${TARBALL}"
    return 1
  fi

  if [ -d "${TARGET_DIR}" ]; then
    _setup_log "已存在目录 ${TARGET_DIR}，将覆盖解压（tar 增量覆盖）"
  fi

  _setup_log "解压中: tar -xzf ${TARBALL} -C ${_SETUP_DIR}"
  if tar -xzf "${TARBALL}" -C "${_SETUP_DIR}"; then
    _setup_ok "解压完成: ${TARGET_DIR}"
  else
    _setup_err "解压失败"
    return 1
  fi

  if [ ! -f "${ENV_FILE}" ]; then
    _setup_err "解压后未找到 env.sh: ${ENV_FILE}"
    return 1
  fi
  _setup_ok "已确认 env.sh: ${ENV_FILE}"
}

# 通过 source env.sh 检验
setup_verify_via_source() {
  _setup_log "通过 source env.sh 检验代理环境..."
  if [ ! -f "${ENV_FILE}" ]; then
    _setup_err "env.sh 不存在: ${ENV_FILE}，请先执行解压"
    return 1
  fi
  if [ ! -r "${ENV_FILE}" ]; then
    _setup_err "env.sh 不可读: ${ENV_FILE}"
    return 1
  fi

  # 语法检查
  if ! bash -n "${ENV_FILE}" 2>&1; then
    _setup_err "env.sh 语法检查失败"
    return 1
  fi
  _setup_ok "env.sh 语法检查通过 (bash -n)"

  # 在当前 shell 中 source 并检验（为避免污染，用子 shell 先做一轮预检，成功后再在当前 shell 应用）
  _setup_log "子 shell 预检: source env.sh --status"
  local _verify_output _verify_rc
  _verify_output="$(bash -c "set -e; source \"${ENV_FILE}\" --status 2>&1; echo \"__VERIFY_RC:\$?\"")" || true
  _verify_rc="$(printf '%s' "${_verify_output}" | sed -nE 's/.*__VERIFY_RC:([0-9]+).*/\1/p' | tail -n 1)"
  # 展示预检输出（去掉末尾标记行）
  printf '%s\n' "${_verify_output}" | sed -E '/__VERIFY_RC:[0-9]+/d'

  # 判断 http_proxy 是否在子 shell 中被设置（通过解析输出或再次执行）
  local _sub_http
  _sub_http="$(bash -c "source \"${ENV_FILE}\" >/dev/null 2>&1; printf '%s' \"\${http_proxy:-}\"")"
  if [ -z "${_sub_http}" ]; then
    _setup_warn "子 shell 中 http_proxy 未设置（可能项目目录定位失败，见上方输出）"
  else
    _setup_ok "子 shell 中 http_proxy=${_sub_http}"
  fi

  # 检查增强函数是否存在（新 env.sh 应包含）
  local _has_show _has_test
  _has_show="$(bash -c "source \"${ENV_FILE}\" >/dev/null 2>&1; typeset -f clash_env_proxy_show >/dev/null 2>&1 && echo yes || echo no")"
  _has_test="$(bash -c "source \"${ENV_FILE}\" >/dev/null 2>&1; typeset -f clash_env_proxy_test >/dev/null 2>&1 && echo yes || echo no")"
  if [ "${_has_show}" = "yes" ]; then
    _setup_ok "检测到显示功能: clash_env_proxy_show"
  else
    _setup_warn "未检测到 clash_env_proxy_show（env.sh 可能为旧版）"
  fi
  if [ "${_has_test}" = "yes" ]; then
    _setup_ok "检测到检验功能: clash_env_proxy_test"
  else
    _setup_warn "未检测到 clash_env_proxy_test（env.sh 可能为旧版）"
  fi

  # 在当前 shell 实际 source，使代理变量对后续命令生效
  _setup_log "在当前 Shell 中 source env.sh ..."
  # shellcheck disable=SC1090
  source "${ENV_FILE}" || {
    _setup_err "source env.sh 失败"
    return 1
  }

  # 再次在当前 shell 中检验变量
  if [ -n "${http_proxy:-}" ] && [ -n "${https_proxy:-}" ] && [ -n "${all_proxy:-}" ]; then
    _setup_ok "当前 Shell 代理已生效"
    _setup_log "  http_proxy=${http_proxy}"
    _setup_log "  https_proxy=${https_proxy}"
    _setup_log "  all_proxy=${all_proxy}"
    _setup_log "  no_proxy=${no_proxy:-}"
  else
    _setup_err "当前 Shell 中代理变量未完全设置"
    _setup_log "  http_proxy=${http_proxy:-<空>}"
    _setup_log "  https_proxy=${https_proxy:-<空>}"
    _setup_log "  all_proxy=${all_proxy:-<空>}"
    return 1
  fi

  # 调用增强函数做最终展示与检测（若存在）
  if typeset -f clash_env_proxy_show >/dev/null 2>&1; then
    _setup_log "调用 clash_env_proxy_show 展示当前代理:"
    clash_env_proxy_show || true
  fi
  if typeset -f clash_env_proxy_test >/dev/null 2>&1; then
    _setup_log "调用 clash_env_proxy_test 检验连通性:"
    if clash_env_proxy_test; then
      _setup_ok "代理连通性检验通过"
    else
      local _test_rc=$?
      if [ "${_test_rc}" -eq 2 ]; then
        _setup_warn "代理检验跳过（环境缺失或无 curl/wget）"
      else
        _setup_warn "代理连通性检验未通过（代理可能未启动或外网不可达，见上方诊断）"
        # 检验失败不视为 setup 整体失败，仍返回 0（代理变量已设置即算成功）
        # 若需严格模式，可改为 return 1
      fi
    fi
  else
    # 兼容旧版 env.sh 的最小检验：检查 http_proxy 格式与端口可达
    _setup_log "旧版 env.sh，无增强函数，执行最小检验..."
    local _hostport
    _hostport="$(printf '%s' "${http_proxy}" | sed -nE 's|^[a-z]+://([^/]+).*|\1|p')"
    if [ -n "${_hostport}" ]; then
      _setup_ok "代理地址格式正常: ${_hostport}"
    else
      _setup_warn "代理地址格式异常: ${http_proxy}"
    fi
  fi

  _setup_ok "检验完成: source ${ENV_FILE} 成功"
  return 0
}

# ── 主流程（仅当直接执行时触发，source 时不自动执行） ─────────────
# 判定是否被 source：BASH_SOURCE[0] != $0 或 ZSH_EVAL_CONTEXT 含 file
_setup_is_sourced="false"
if [ -n "${ZSH_VERSION:-}" ]; then
  # zsh: 通过 $0 与 %x 判断
  case "${ZSH_EVAL_CONTEXT:-}" in
    *:file*) _setup_is_sourced="true" ;;
  esac
  # 额外判断：若 BASH_SOURCE 存在且与 $0 不同则为被 source
  if [ -n "${BASH_SOURCE[0]:-}" ] && [ "${BASH_SOURCE[0]}" != "${0:-}" ]; then
    _setup_is_sourced="true"
  fi
else
  if [ -n "${BASH_SOURCE[0]:-}" ] && [ "${BASH_SOURCE[0]}" != "${0:-}" ]; then
    _setup_is_sourced="true"
  fi
fi

if [ "${_setup_is_sourced}" = "true" ]; then
  # 被 source 时仅暴露函数，不自动执行
  :
else
  # 直接执行
  _do_check_only="false"
  for _arg in "$@"; do
    case "${_arg}" in
      --check) _do_check_only="true" ;;
      --help|-h) _setup_usage; exit 0 ;;
      *) _setup_warn "未知参数: ${_arg}"; _setup_usage; exit 2 ;;
    esac
  done

  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "🚀 clash-for-linux setup.sh"
  echo "📂 目录: ${_SETUP_DIR}"
  echo "📦 压缩包: ${TARBALL}"
  echo "📄 目标: ${TARGET_DIR}"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  if [ "${_do_check_only}" = "true" ]; then
    setup_verify_via_source
    rc=$?
    if [ $rc -eq 0 ]; then
      _setup_ok "setup.sh --check 完成"
    fi
    exit $rc
  else
    setup_extract || exit $?
    echo ""
    setup_verify_via_source || exit $?
    echo ""
    _setup_ok "setup.sh 全流程完成（解压 + source 检验）"
    echo "💡 后续在任意 Shell 中执行: source ${ENV_FILE} --status  查看与检验"
  fi
fi

# 清理临时变量（不删函数与代理变量）
unset _SETUP_SRC _SETUP_DIR _SETUP_GIT_ROOT TARBALL TARGET_DIR ENV_FILE _setup_is_sourced _do_check_only 2>/dev/null || true
