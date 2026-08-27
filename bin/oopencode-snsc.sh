#!/usr/bin/env bash
# OpenCode HPC/snsc 入口：复用 oopencode.sh 的 prompt、项目上下文注入与驱动实现，默认使用 -f（DeepSeek V4 Flash）。
# snsc 上 opencode 二进制通常手动部署在 vscode-server 目录内；用 OPENCODE_BIN 覆盖，未指定时沿用下方默认路径，
# 默认路径也不可用时再由 oopencode.sh 回退 PATH 中的 opencode。

_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ -n "${OPENCODE_SCRIPT_DIR:-}" ]]; then
    _PATH="${OPENCODE_SCRIPT_DIR}"
else
    if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
fi

# 部署参考（vscode-server 内手动部署 debug 二进制；vscode-server 升级后路径会变，请更新此处默认值或设 OPENCODE_BIN）：
#   mkdir -p /public/home/zhangxin/.vscode-server./cli/servers/Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/server/node/Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/server/out/debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/result_debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/output_result_debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/
#   cp /public/home/zhangxin/.opencode/bin/opencode <上路径>/output_result_debug_Stable-.../
OPENCODE_BIN="${OPENCODE_BIN:-/public/home/zhangxin/.vscode-server./cli/servers/Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/server/node/Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/server/out/debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/result_debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713/output_result_debug_Stable-4fe60c8b1cdac1c4c174f2fb180d0d758272d713}" \
OPENCODE_LAUNCHER_VARIANT=snsc \
OPENCODE_LAUNCHER_NAME="${_SRC##*/}" \
exec "${_PATH}/oopencode.sh" "$@"
