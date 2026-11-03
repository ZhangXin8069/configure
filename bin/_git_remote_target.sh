#!/usr/bin/env bash
# Shared per-invocation Git remote host override.

_GIT_REMOTE_DEFAULT_TARGET=gitlab.itp.ac.cn
_GIT_REMOTE_ALLOWED_TARGETS="gitlab.itp.ac.cn gitee.com github.com gitlab.com gitlab.itp.ac.cn"
_GIT_REMOTE_SELECTED_TARGET=
_GIT_REMOTE_HELP_REQUESTED=0
_GIT_REMOTE_REMAINING_ARGS=()

_git_remote_target_usage_line() {
    printf '%s\n' \
        "  -t, --target [DOMAIN]  Temporarily replace the remote host for this call." \
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

_git_remote_target_apply() {
    local target=${1:-}
    local source
    local base_count
    local index
    local count

    [[ -n "${target}" ]] || return 0
    _git_remote_target_validate "${target}" || return $?

    if [[ "${_GIT_REMOTE_TARGET_APPLIED:-}" == "${target}" ]]; then
        return 0
    fi

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

    index=${base_count}
    while (( index < count )); do
        unset "GIT_CONFIG_KEY_${index}" "GIT_CONFIG_VALUE_${index}"
        index=$((index + 1))
    done
    export GIT_CONFIG_COUNT=${base_count}
    export _GIT_REMOTE_CONFIG_BASE_COUNT=${base_count}

    for source in ${_GIT_REMOTE_ALLOWED_TARGETS}; do
        [[ "${source}" == "${target}" ]] && continue
        _git_remote_target_append_config \
            "url.git@${target}:.insteadOf" "git@${source}:"
        _git_remote_target_append_config \
            "url.ssh://git@${target}/.insteadOf" "ssh://git@${source}/"
        _git_remote_target_append_config \
            "url.ssh://${target}/.insteadOf" "ssh://${source}/"
        _git_remote_target_append_config \
            "url.git+ssh://git@${target}/.insteadOf" "git+ssh://git@${source}/"
        _git_remote_target_append_config \
            "url.git+ssh://${target}/.insteadOf" "git+ssh://${source}/"
        _git_remote_target_append_config \
            "url.https://${target}/.insteadOf" "https://${source}/"
        _git_remote_target_append_config \
            "url.http://${target}/.insteadOf" "http://${source}/"
        _git_remote_target_append_config \
            "url.git://${target}/.insteadOf" "git://${source}/"
    done

    export _GIT_REMOTE_TARGET_APPLIED=${target}
    printf 'Remote target: %s (temporary; protocol and repository path preserved)\n' "${target}"
}
