#!/usr/bin/env bash
# Codex HPC/snsc 入口：复用 ccodex.sh 的驱动实现，默认使用 -m（GPT-5.6-Luna max）。

_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ -n "${CODEX_SCRIPT_DIR:-}" ]]; then
    _PATH="${CODEX_SCRIPT_DIR}"
else
    if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
fi

# CODEX_BIN 可指定 snsc 上手动部署的 Codex 二进制；未指定时沿用 PATH 中的 codex。
CODEX_LAUNCHER_VARIANT=snsc \
CODEX_DEFAULT_MODEL_FLAG="${CODEX_DEFAULT_MODEL_FLAG:--m}" \
CODEX_LAUNCHER_NAME="${_SRC##*/}" \
exec "${_PATH}/ccodex.sh" "$@"
