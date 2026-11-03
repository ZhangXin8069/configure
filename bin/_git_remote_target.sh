#!/usr/bin/env bash
# Shared per-invocation Git remote host override.

_GIT_REMOTE_DEFAULT_TARGET=gitlab.itp.ac.cn
_GIT_REMOTE_ALLOWED_TARGETS="gitlab.itp.ac.cn gitee.com github.com gitlab.com"
_GIT_REMOTE_LEGACY_SOURCE_HOSTS="code.itp.ac.cn"
_GIT_REMOTE_SELECTED_TARGET=
_GIT_REMOTE_HELP_REQUESTED=0
_GIT_REMOTE_REMAINING_ARGS=()

_git_remote_target_usage_line() {
    printf '%s\n' \
        "  -t, --target [DOMAIN]  Temporarily replace the remote host for this call," \
        "                         including URLs already configured in .git/config." \
        "                         Supported: ${_GIT_REMOTE_ALLOWED_TARGETS}." \
        "                         Bare -t uses ${_GIT_REMOTE_DEFAULT_TARGET}."
}

_git_remote_target_validate() {
    local target=${1:-}
    local allowed

    for allowed in ${_GIT_REMOTE_ALLOWED_TARGETS}; do
        [[ "${target}" == "${allowed}" ]] && return 0
    done

    echo "ERROR: Unsupported remote target: ${target:-<empty>}" >&2
    echo "Supported targets: ${_GIT_REMOTE_ALLOWED_TARGETS}" >&2
    return 64
}

_git_remote_target_parse_args() {
    local target

    _GIT_REMOTE_SELECTED_TARGET=
    _GIT_REMOTE_HELP_REQUESTED=0
    _GIT_REMOTE_REMAINING_ARGS=()

    while (( $# > 0 )); do
        case "$1" in
            -t|--target)
                shift
                if (( $# > 0 )) && [[ "$1" != -* ]]; then
                    target=$1
                    shift
                else
                    target=${_GIT_REMOTE_DEFAULT_TARGET}
                fi
                _git_remote_target_validate "${target}" || return $?
                _GIT_REMOTE_SELECTED_TARGET=${target}
                ;;
            --target=*|-t=*)
                target=${1#*=}
                _git_remote_target_validate "${target}" || return $?
                _GIT_REMOTE_SELECTED_TARGET=${target}
                shift
                ;;
            -t?*)
                target=${1#-t}
                _git_remote_target_validate "${target}" || return $?
                _GIT_REMOTE_SELECTED_TARGET=${target}
                shift
                ;;
            -h|--help)
                _GIT_REMOTE_HELP_REQUESTED=1
                shift
                ;;
            --)
                shift
                while (( $# > 0 )); do
                    _GIT_REMOTE_REMAINING_ARGS+=("$1")
                    shift
                done
                ;;
            *)
                _GIT_REMOTE_REMAINING_ARGS+=("$1")
                shift
                ;;
        esac
    done
}

_git_remote_target_append_config() {
    local key=$1
    local value=$2
    local index=${GIT_CONFIG_COUNT:-0}

    export "GIT_CONFIG_KEY_${index}=${key}"
    export "GIT_CONFIG_VALUE_${index}=${value}"
    export GIT_CONFIG_COUNT=$((index + 1))
}

_git_remote_target_config_has_mapping() {
    local key=$1
    local value=$2
    local index=${_GIT_REMOTE_CONFIG_BASE_COUNT:-0}
    local count=${GIT_CONFIG_COUNT:-0}
    local key_name
    local value_name

    while (( index < count )); do
        printf -v key_name 'GIT_CONFIG_KEY_%s' "${index}"
        printf -v value_name 'GIT_CONFIG_VALUE_%s' "${index}"
        if [[ "${!key_name:-}" == "${key}" && "${!value_name:-}" == "${value}" ]]; then
            return 0
        fi
        index=$((index + 1))
    done
    return 1
}

_git_remote_target_add_mapping() {
    local key=$1
    local value=$2

    if _git_remote_target_config_has_mapping "${key}" "${value}"; then
        return 0
    fi
    _git_remote_target_append_config "${key}" "${value}"
}

_git_remote_target_rewrite_url() {
    local url=${1:-}
    local target=${2:-}
    local scheme
    local rest
    local authority
    local suffix
    local userinfo
    local hostport
    local host
    local port
    local path

    case "${url}" in
        ""|*$'\n'*|*$'\r'*|file://*|/*|./*|../*|~*|[[:alpha:]]:[\\/]*) return 1 ;;
        *://*)
            scheme=${url%%://*}
            rest=${url#*://}
            authority=${rest%%/*}
            if [[ "${rest}" == */* ]]; then
                suffix=/${rest#*/}
            else
                suffix=
            fi
            [[ -n "${scheme}" && -n "${authority}" ]] || return 1

            userinfo=
            hostport=${authority}
            if [[ "${authority}" == *@* ]]; then
                userinfo=${authority%@*}@
                hostport=${authority##*@}
            fi
            if [[ "${hostport}" == \[*\]* ]]; then
                host=${hostport#\[}
                host=${host%\]*}
                port=${hostport#*\]}
            elif [[ "${hostport}" == *:* ]]; then
                host=${hostport%%:*}
                port=:${hostport#*:}
            else
                host=${hostport}
                port=
            fi
            [[ -n "${host}" && "${host}" != "${target}" ]] || return 1
            printf '%s://%s%s%s%s\n' "${scheme}" "${userinfo}" "${target}" "${port}" "${suffix}"
            ;;
        *:*)
            authority=${url%%:*}
            path=${url#*:}
            [[ -n "${authority}" && -n "${path}" ]] || return 1
            userinfo=
            host=${authority}
            if [[ "${authority}" == *@* ]]; then
                userinfo=${authority%@*}@
                host=${authority##*@}
            fi
            [[ -n "${host}" && "${host}" != "${target}" ]] || return 1
            printf '%s%s:%s\n' "${userinfo}" "${target}" "${path}"
            ;;
        *) return 1 ;;
    esac
}

_git_remote_target_add_configured_url_mappings() {
    local target=$1
    local record
    local url
    local rewritten

    while IFS= read -r -d '' record; do
        [[ "${record}" == *$'\n'* ]] || continue
        url=${record#*$'\n'}
        if rewritten=$(_git_remote_target_rewrite_url "${url}" "${target}"); then
            _git_remote_target_add_mapping "url.${rewritten}.insteadOf" "${url}"
        fi
    done < <(git config --null --get-regexp '^(remote|submodule)\..*\.url$' 2>/dev/null || true)
}

_git_remote_target_apply() {
    local target=${1:-}
    local source
    local base_count
    local index
    local count
    local announce=0

    [[ -n "${target}" ]] || return 0
    _git_remote_target_validate "${target}" || return $?

    count=${GIT_CONFIG_COUNT:-0}
    if [[ ! "${count}" =~ ^[0-9]+$ ]]; then
        echo "ERROR: GIT_CONFIG_COUNT must be a non-negative integer; got '${count}'." >&2
        return 64
    fi
    base_count=${_GIT_REMOTE_CONFIG_BASE_COUNT:-${count}}
    if [[ ! "${base_count}" =~ ^[0-9]+$ ]] || (( base_count > count )); then
        echo "ERROR: Invalid inherited Git config base count: ${base_count}." >&2
        return 64
    fi

    export _GIT_REMOTE_CONFIG_BASE_COUNT=${base_count}
    if [[ "${_GIT_REMOTE_TARGET_APPLIED:-}" != "${target}" ]]; then
        index=${base_count}
        while (( index < count )); do
            unset "GIT_CONFIG_KEY_${index}" "GIT_CONFIG_VALUE_${index}"
            index=$((index + 1))
        done
        export GIT_CONFIG_COUNT=${base_count}
        export _GIT_REMOTE_TARGET_APPLIED=${target}
        announce=1
    fi

    for source in ${_GIT_REMOTE_LEGACY_SOURCE_HOSTS} ${_GIT_REMOTE_ALLOWED_TARGETS}; do
        [[ "${source}" == "${target}" ]] && continue
        _git_remote_target_add_mapping \
            "url.git@${target}:.insteadOf" "git@${source}:"
        _git_remote_target_add_mapping \
            "url.ssh://git@${target}/.insteadOf" "ssh://git@${source}/"
        _git_remote_target_add_mapping \
            "url.ssh://${target}/.insteadOf" "ssh://${source}/"
        _git_remote_target_add_mapping \
            "url.git+ssh://git@${target}/.insteadOf" "git+ssh://git@${source}/"
        _git_remote_target_add_mapping \
            "url.git+ssh://${target}/.insteadOf" "git+ssh://${source}/"
        _git_remote_target_add_mapping \
            "url.https://${target}/.insteadOf" "https://${source}/"
        _git_remote_target_add_mapping \
            "url.http://${target}/.insteadOf" "http://${source}/"
        _git_remote_target_add_mapping \
            "url.git://${target}/.insteadOf" "git://${source}/"
    done
    _git_remote_target_add_configured_url_mappings "${target}"

    if (( announce )) || [[ "${_GIT_REMOTE_TARGET_ANNOUNCED:-}" != "${target}" ]]; then
        export _GIT_REMOTE_TARGET_ANNOUNCED=${target}
        printf 'Remote target: %s (temporary; protocol and repository path preserved)\n' "${target}"
    fi
}
