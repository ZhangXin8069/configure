#!/usr/bin/env bash
# env.sh 加载前冲突预检：只读当前 Shell 与 PATH，不修改父 Shell。

_env_conflicts_preflight() {
    local root_dir=$1
    local env_file=$2
    local probe_shell=''
    local probe_output=''
    local alias_candidates=''
    local function_candidates=''
    local candidate=''
    local resolved=''
    local resolved_dir=''
    local own_bin=''
    local own_bin_dir=''
    local conflicts=''

    own_bin="${root_dir%/}/bin"
    if [[ ! -d "${own_bin}" ]]; then
        printf '[WARN] env.sh 未加载：找不到仓库 bin 目录 %s\n' "${own_bin}" >&2
        return 2
    fi
    own_bin_dir=$(CDPATH= cd -P -- "${own_bin}" 2>/dev/null && pwd -P) || {
        printf '[WARN] env.sh 未加载：无法解析仓库 bin 目录 %s\n' "${own_bin}" >&2
        return 2
    }

    if [[ -n "${ZSH_VERSION:-}" ]]; then
        probe_shell=$(command -v zsh 2>/dev/null) || probe_shell=''
        if [[ -z "${probe_shell}" ]]; then
            printf '[WARN] env.sh 未加载：当前为 zsh，但找不到 zsh 可执行文件用于冲突预检。\n' >&2
            return 2
        fi
        probe_output=$(command env -i \
            HOME="${HOME:-}" USER="${USER:-}" LOGNAME="${LOGNAME:-}" \
            SHELL="${SHELL:-${probe_shell}}" TERM="${TERM:-dumb}" PATH="${PATH:-}" \
            _CONFIGURE_ENV_PROBE="${env_file}" \
            "${probe_shell}" -f -c '
                unalias -m "*" >/dev/null 2>&1 || :
                . "$1" 2>/dev/null
            ' configure-env-probe "${env_file}") || {
            printf '[WARN] env.sh 未加载：隔离 zsh 冲突预检失败。\n' >&2
            return 2
        }
    else
        probe_shell=${BASH:-}
        [[ -n "${probe_shell}" ]] || probe_shell=$(command -v bash 2>/dev/null) || probe_shell=''
        if [[ -z "${probe_shell}" ]]; then
            printf '[WARN] env.sh 未加载：当前为 bash，但找不到 bash 可执行文件用于冲突预检。\n' >&2
            return 2
        fi
        probe_output=$(command env -i \
            HOME="${HOME:-}" USER="${USER:-}" LOGNAME="${LOGNAME:-}" \
            SHELL="${SHELL:-${probe_shell}}" TERM="${TERM:-dumb}" PATH="${PATH:-}" \
            _CONFIGURE_ENV_PROBE="${env_file}" \
            "${probe_shell}" --noprofile --norc -c '
                unalias -a >/dev/null 2>&1 || :
                . "$1" 2>/dev/null
            ' configure-env-probe "${env_file}") || {
            printf '[WARN] env.sh 未加载：隔离 bash 冲突预检失败。\n' >&2
            return 2
        }
    fi

    alias_candidates=$(printf '%s\n' "${probe_output}" | command awk '
        $0 == "@@CONFIGURE_ENV_ALIASES@@" { section = "alias"; next }
        $0 == "@@CONFIGURE_ENV_FUNCTIONS@@" { section = "function"; next }
        section == "alias" { print }
    ')
    function_candidates=$(printf '%s\n' "${probe_output}" | command awk '
        $0 == "@@CONFIGURE_ENV_FUNCTIONS@@" { section = "function"; next }
        section == "function" { print }
    ')

    while IFS= read -r candidate; do
        [[ -n "${candidate}" ]] || continue
        if alias "${candidate}" >/dev/null 2>&1; then
            conflicts+="alias ${candidate}"$'\n'
        fi
    done <<EOF
${alias_candidates}
EOF

    while IFS= read -r candidate; do
        [[ -n "${candidate}" ]] || continue
        if [[ -n "${ZSH_VERSION:-}" ]]; then
            resolved=$(whence -w "${candidate}" 2>/dev/null) || resolved=''
            if [[ "${resolved}" == "${candidate}: function" ]]; then
                conflicts+="function ${candidate}"$'\n'
            fi
        elif declare -F "${candidate}" >/dev/null 2>&1; then
            conflicts+="function ${candidate}"$'\n'
        fi
    done <<EOF
${function_candidates}
EOF

    while IFS= read -r candidate; do
        [[ -n "${candidate}" && -x "${candidate}" ]] || continue
        candidate=${candidate##*/}
        if alias "${candidate}" >/dev/null 2>&1; then
            conflicts+="executable ${candidate} (alias)"$'\n'
            continue
        fi
        if [[ -n "${ZSH_VERSION:-}" ]]; then
            resolved=$(whence -w "${candidate}" 2>/dev/null) || resolved=''
            if [[ "${resolved}" == "${candidate}: function" ]]; then
                conflicts+="executable ${candidate} (function)"$'\n'
                continue
            fi
        elif declare -F "${candidate}" >/dev/null 2>&1; then
            conflicts+="executable ${candidate} (function)"$'\n'
            continue
        fi
        resolved=$(command -v "${candidate}" 2>/dev/null) || continue
        case "${resolved}" in
            /*)
                resolved_dir=${resolved%/*}
                [[ -n "${resolved_dir}" ]] || resolved_dir=/
                resolved_dir=$(CDPATH= cd -P -- "${resolved_dir}" 2>/dev/null && pwd -P) ||
                    resolved_dir=''
                if [[ -n "${resolved_dir}" && "${resolved_dir}/${candidate}" == "${own_bin_dir}/${candidate}" ]]; then
                    continue
                fi
                ;;
        esac
        conflicts+="executable ${candidate} (${resolved})"$'\n'
    done < <(command find "${own_bin}" \
        -type d ! -path "${own_bin}" -prune -o \
        \( -type f -o -type l \) -print 2>/dev/null)

    if [[ -z "${conflicts}" ]]; then
        return 0
    fi

    printf '%s\n' \
        '[WARN] env.sh 未加载：原 Shell 环境与仓库公开内容存在名称冲突。' \
        '冲突项：' >&2
    while IFS= read -r candidate; do
        [[ -n "${candidate}" ]] && printf '  - %s\n' "${candidate}" >&2
    done <<EOF
${conflicts}
EOF
    printf '%s\n' \
        "加载标记: ${_CONFIGURE_ENV_LOADED_PATH:-<未设置>}" \
        '请先移除或重命名上述 alias、function、可执行命令后重新 source。' \
        '若冲突来自 oh-my-zsh 等 rc/plugin 的同名定义，请先 source env.sh，再加载该 rc/plugin。' >&2
    return 1
}
