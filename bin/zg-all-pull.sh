#!/usr/bin/env bash
# Discover zg-*-pull.sh siblings, clone missing repositories, and run them in order.

_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}

_usage() {
    cat <<'EOF'
Usage: zg-all-pull.sh

Clone missing sibling repositories and run every zg-*-pull.sh script in this
directory in filename order. At least two matching child scripts are required.
Set ZG_GIT_PROTOCOL=auto|ssh|https to select the clone protocol.
EOF
}

for _arg in "$@"; do
    case "${_arg}" in
        -h|--help)
            _usage
            exit 0
            ;;
    esac
done

echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

_CLONE_PROTOCOL=${ZG_GIT_PROTOCOL:-auto}
case "${_CLONE_PROTOCOL}" in
    auto|https|ssh) ;;
    *)
        echo "ERROR: ZG_GIT_PROTOCOL must be one of: auto, https, ssh." >&2
        exit 64
        ;;
esac

if [[ ! -r "${_PATH}/_all_series.sh" ]]; then
    echo "ERROR: Missing aggregate series helper: ${_PATH}/_all_series.sh" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "${_PATH}/_all_series.sh"
_all_series_discover "${_NAME}" "${_PATH}" || exit 1
echo "Matched: ${_ALL_SERIES_PATTERN} (${#_ALL_SERIES_SCRIPTS[@]} scripts)"

_is_git_checkout() {
    [[ -d "$1/.git" || -f "$1/.git" ]]
}

_clone_url() {
    case "$1" in
        https) printf 'https://gitee.com/zhangxin8069/%s.git\n' "$2" ;;
        ssh) printf 'git@gitee.com:zhangxin8069/%s.git\n' "$2" ;;
    esac
}

_clone_repo() {
    local repo=$1
    local target=$2
    local protocol=$3
    local url
    local temporary

    url=$(_clone_url "${protocol}" "${repo}")
    temporary=$(mktemp -d "${target}.clone.XXXXXX") || return 1
    if ! git clone "${url}" "${temporary}"; then
        rm -rf -- "${temporary}"
        return 1
    fi
    if ! mv -- "${temporary}" "${target}"; then
        rm -rf -- "${temporary}"
        return 1
    fi
}

_ensure_repository() {
    local child=$1
    local target
    local repo

    if ! target=$(bash "${child}" --print-repo-path 2>/dev/null); then
        echo "INFO: ${child##*/} does not expose clone metadata; delegating missing-checkout handling to the child."
        return 0
    fi
    if [[ -z "${target}" ]]; then
        echo "INFO: ${child##*/} returned no clone metadata; delegating missing-checkout handling to the child."
        return 0
    fi
    repo=${target%/}
    repo=${repo##*/}
    if _is_git_checkout "${target}"; then
        return 0
    fi
    if [[ -e "${target}" ]]; then
        echo "ERROR: Existing non-Git path blocks clone: ${target}" >&2
        return 1
    fi

    mkdir -p -- "$(dirname "${target}")" || return 1
    echo "### ${repo} local checkout is missing; cloning ${_CLONE_PROTOCOL} ###"
    case "${_CLONE_PROTOCOL}" in
        ssh)
            _clone_repo "${repo}" "${target}" ssh \
                || { echo "ERROR: ${repo} clone failed (ssh)." >&2; return 1; }
            ;;
        https)
            _clone_repo "${repo}" "${target}" https \
                || { echo "ERROR: ${repo} clone failed (https)." >&2; return 1; }
            ;;
        auto)
            if _clone_repo "${repo}" "${target}" ssh; then
                echo "### ${repo} cloned (ssh) ###"
            elif _clone_repo "${repo}" "${target}" https; then
                echo "### ${repo} cloned (https) ###"
            else
                echo "ERROR: ${repo} clone failed (ssh and https)." >&2
                return 1
            fi
            ;;
    esac
    _is_git_checkout "${target}"
}

_CLONE_FAILED=0
for _child in "${_ALL_SERIES_SCRIPTS[@]}"; do
    _ensure_repository "${_child}" || _CLONE_FAILED=$((_CLONE_FAILED + 1))
done

_all_series_run "$@"
echo "Summary: clone_failed=${_CLONE_FAILED} child_failed=${_ALL_SERIES_FAILED}"
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"

if (( _CLONE_FAILED > 0 || _ALL_SERIES_FAILED > 0 )); then
    exit 1
fi
