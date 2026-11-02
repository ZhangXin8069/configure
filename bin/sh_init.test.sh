#!/usr/bin/env bash
set -euo pipefail

_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/" ;; *) _DIR=. ;; esac
if [[ "${_DIR}" == /* ]]; then _PATH=${_DIR}; else _PATH=$(cd "${_DIR}" && pwd); fi
_ROOT=$(cd "${_PATH}/.." && pwd)
_TMP=$(mktemp -d "${_ROOT}/.sh-init-test.XXXXXX")
trap 'rm -rf "${_TMP}"' EXIT

fail()
{
    echo "FAIL: $*" >&2
    exit 1
}

bash -n "${_ROOT}/bin/sh_init.sh"
bash -n "${_ROOT}/lib/_bashrc"
if command -v zsh >/dev/null 2>&1; then
    zsh -n "${_ROOT}/lib/_zshrc"
fi
for _metadata in .version .revision-hash; do
    [ -s "${_ROOT}/lib/_oh-my-zsh/custom/plugins/zsh-syntax-highlighting/${_metadata}" ] \
        || fail "缺少 zsh-syntax-highlighting 元数据: ${_metadata}"
done

_FIXTURE=${_TMP}/fixture
_HOME="${_FIXTURE}/home with space"
mkdir -p "${_FIXTURE}/bin" "${_FIXTURE}/lib" "${_HOME}"
cp "${_ROOT}/bin/sh_init.sh" "${_FIXTURE}/bin/sh_init.sh"
printf 'original bashrc\n' >"${_HOME}/.bashrc"

if HOME=${_HOME} bash "${_FIXTURE}/bin/sh_init.sh" -b >"${_TMP}/missing-bashrc.log" 2>&1; then
    fail "缺少 _bashrc 时应当失败"
fi
grep -Fq '部署源缺失' "${_TMP}/missing-bashrc.log" || fail "缺少明确的部署源错误"
grep -Fqx 'original bashrc' "${_HOME}/.bashrc" || fail "源缺失时不得移动 .bashrc"
if compgen -G "${_HOME}/.bashrc.*.bak" >/dev/null; then
    fail "源缺失时不得创建备份"
fi

printf 'fixture bashrc\n' >"${_FIXTURE}/lib/_bashrc"
printf '#!/usr/bin/env bash\nexit 0\n' >"${_FIXTURE}/bin/zsh"
chmod +x "${_FIXTURE}/bin/zsh"

if PATH="${_FIXTURE}/bin:${PATH}" HOME=${_HOME} bash "${_FIXTURE}/bin/sh_init.sh" -a >"${_TMP}/missing-zshrc.log" 2>&1; then
    fail "缺少 _zshrc 时 -a 应当失败"
fi
grep -Fq '部署源缺失' "${_TMP}/missing-zshrc.log" || fail "缺少 _zshrc 的明确错误"
grep -Fqx 'original bashrc' "${_HOME}/.bashrc" || fail "预检失败时不得先部署 .bashrc"
if compgen -G "${_HOME}/.bashrc.*.bak" >/dev/null; then
    fail "预检失败时不得创建备份"
fi

printf 'fixture zshrc\n' >"${_FIXTURE}/lib/_zshrc"
mkdir -p "${_FIXTURE}/lib/_oh-my-zsh/custom"
printf 'fixture metadata\n' >"${_FIXTURE}/lib/_oh-my-zsh/custom/.version"

PATH="${_FIXTURE}/bin:${PATH}" HOME=${_HOME} bash "${_FIXTURE}/bin/sh_init.sh" -a >"${_TMP}/success.log" 2>&1
grep -Fqx 'fixture bashrc' "${_HOME}/.bashrc" || fail "Bash 部署内容不正确"
grep -Fqx 'fixture zshrc' "${_HOME}/.zshrc" || fail "Zsh 部署内容不正确"
grep -Fqx 'fixture metadata' "${_HOME}/.oh-my-zsh/custom/.version" || fail "隐藏文件未被部署"
_BACKUP=$(compgen -G "${_HOME}/.bashrc.*.bak" | head -n 1)
[ -n "${_BACKUP}" ] || fail "成功部署前应备份原 .bashrc"
grep -Fqx 'original bashrc' "${_BACKUP}" || fail "备份内容不正确"
grep -Fq 'is done' "${_TMP}/success.log" || fail "成功部署缺少完成标记"

echo "PASS: sh_init.sh deployment and missing-source preflight"
