#!/usr/bin/env bash
# gadd-ignore — 将 lib/_gitignore 模板内容逐行去重补加到当前 git 仓库根的 .gitignore（无则新建）
# 规则源优先按脚本自身定位 ../lib/_gitignore（与调用 CWD 无关），缺失时回退 ${HOME}/configure/lib/_gitignore

set -euo pipefail
_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

case "${1:-}" in
    "") ;;
    -h|--help) echo "用法: ${_NAME} — 将 lib/_gitignore 模板逐行去重补加到当前 git 仓库根 .gitignore（无则新建）"; exit 0 ;;
    *) echo "ERROR: 无法识别的参数: $1"; echo "用法: ${_NAME}（无参数）"; exit 2 ;;
esac

GITIGNORE="${_PATH}/../lib/_gitignore"
[ -f "${GITIGNORE}" ] || GITIGNORE="${HOME}/configure/lib/_gitignore"
[ -f "${GITIGNORE}" ] || { echo "ERROR: 忽略规则文件不存在: ${_PATH}/../lib/_gitignore 与 ${HOME}/configure/lib/_gitignore 均缺失"; exit 1; }

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "ERROR: 不在 git 仓库内"; exit 1; }
TARGET="${REPO_ROOT}/.gitignore"
echo "Repo:   ${REPO_ROOT}"
echo "Rule:   ${GITIGNORE}"
echo "Target: ${TARGET}"

MARKER="# ---- 追加自 lib/_gitignore 模板 (gadd-ignore.sh)：逐行精确匹配去重补加，分节含义见该模板 ----"

touch -- "${TARGET}"

# TMP 为去重基准（现有目标内容 + 本次已收集行），grep -Fxq 整行精确匹配
TMP=$(mktemp)
trap 'rm -f "${TMP}"' EXIT
cp -- "${TARGET}" "${TMP}"

ADD=()
marker_done=0
while IFS= read -r line || [ -n "${line}" ]; do
    [ -z "${line}" ] && continue
    if grep -Fxq -- "${line}" "${TMP}"; then continue; fi
    if [ "${marker_done}" -eq 0 ] && ! grep -Fxq -- "${MARKER}" "${TMP}"; then
        ADD+=("${MARKER}")
        marker_done=1
        printf '%s\n' "${MARKER}" >> "${TMP}"
    fi
    ADD+=("${line}")
    printf '%s\n' "${line}" >> "${TMP}"
done < "${GITIGNORE}"

# 目标末行缺换行时先补分隔换行，避免追加拼接坏行
if [ -s "${TARGET}" ] && [ "$(tail -c 1 -- "${TARGET}" | wc -l)" -eq 0 ]; then
    printf '\n' >> "${TARGET}"
fi

if [ "${#ADD[@]}" -eq 0 ]; then
    echo "无需补加：目标已含全部规则行。"
else
    printf '%s\n' "${ADD[@]}" >> "${TARGET}"
    echo "已补加 ${#ADD[@]} 行:"
    printf '  + %s\n' "${ADD[@]}"
fi

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
