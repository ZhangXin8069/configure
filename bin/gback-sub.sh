#!/usr/bin/env bash
# Force initialized submodules to match the latest remote default branch.

set -o pipefail

_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in
    */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/" ;;
    *) _DIR=. ;;
esac
if [[ "${_DIR}" == /* ]]; then
    _PATH="${_DIR}"
else
    _PATH=$(cd "${_DIR}" && pwd)
fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

if [[ ! -r "${_PATH}/_git_remote_target.sh" ]]; then
    echo "ERROR: Missing Git remote target helper: ${_PATH}/_git_remote_target.sh" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "${_PATH}/_git_remote_target.sh"

_INIT=0
_RECURSIVE=0
_DRY_RUN=0
_TARGET=${_GIT_REMOTE_DEFAULT_TARGET}
_FILTERS=()

_usage() {
    cat <<'EOF'
Usage: gback-sub.sh [options] [--path submodule-path-or-name ...]

Force initialized submodules of the current Git repository to match the latest
remote default branch. Old HEADs are retained under refs/gback-sub-backups/ and
dirty state is preserved in each submodule's stash before reset and clean.

Options:
  --init       Initialize missing submodules before backing them up.
  --path PATH  Process only the named submodule path or name (repeatable).
  --recursive  Recursively restore nested mapped submodules.
  --dry-run    Print actions without initializing, fetching, stashing, or resetting.
  -h, --help   Show this help.
EOF
    _git_remote_target_usage_line
}

while (( $# > 0 )); do
    case "$1" in
        --init) _INIT=1 ;;
        --recursive) _RECURSIVE=1 ;;
        --dry-run) _DRY_RUN=1 ;;
        -t|--target)
            shift
            if (( $# > 0 )) && [[ "$1" != -* ]]; then
                _TARGET=$1
                shift
            else
                _TARGET=${_GIT_REMOTE_DEFAULT_TARGET}
            fi
            _git_remote_target_validate "${_TARGET}" || exit $?
            ;;
        --target=*|-t=*)
            _TARGET=${1#*=}
            _git_remote_target_validate "${_TARGET}" || exit $?
            ;;
        -t?*)
            _TARGET=${1#-t}
            _git_remote_target_validate "${_TARGET}" || exit $?
            ;;
        --path)
            shift
            if (( $# == 0 )); then
                echo "ERROR: --path requires a submodule path or name." >&2
                exit 64
            fi
            _FILTERS+=("$1")
            ;;
        -h|--help)
            _usage
            exit 0
            ;;
        --)
            shift
            while (( $# > 0 )); do
                _FILTERS+=("$1")
                shift
            done
            break
            ;;
        -*)
            echo "ERROR: Unknown option: $1" >&2
            _usage >&2
            exit 64
            ;;
        *)
            _FILTERS+=("$1")
            ;;
    esac
    shift
done

_git_remote_target_apply "${_TARGET}" || exit $?

_REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "ERROR: Not inside a Git work tree." >&2
    exit 1
}
echo "Repo:    ${_REPO_ROOT}"

if [[ ! -r "${_PATH}/_git_lock.sh" ]]; then
    echo "ERROR: Missing Git lock helper: ${_PATH}/_git_lock.sh" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "${_PATH}/_git_lock.sh"

_GITMODULES="${_REPO_ROOT}/.gitmodules"
if [[ ! -f "${_GITMODULES}" ]]; then
    echo "No submodule mappings found (.gitmodules is absent)."
    echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
    exit 0
fi

_ENTRIES=$(git -C "${_REPO_ROOT}" config -f .gitmodules \
    --get-regexp '^submodule\..*\.path$')
_ENTRIES_STATUS=$?
if (( _ENTRIES_STATUS == 1 )); then
    echo "No mapped submodules found in .gitmodules."
    echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
    exit 0
elif (( _ENTRIES_STATUS != 0 )); then
    echo "ERROR: Failed to read submodule mappings from .gitmodules." >&2
    exit 1
fi

_matches_filter() {
    local path=$1
    local name=$2
    local filter

    if (( ${#_FILTERS[@]} == 0 )); then
        return 0
    fi
    for filter in "${_FILTERS[@]}"; do
        if [[ "${filter}" == "${path}" || "${filter}" == "${name}" ]]; then
            return 0
        fi
    done
    return 1
}

_validate_submodule_path() {
    local path=$1

    case "${path}" in
        ""|"."|"./"|/*|..|../*|*/..|*/../*|./*|*/./*|*/.|*$'\n'*) return 1 ;;
    esac
    return 0
}

_is_tracked_gitlink() {
    local path=$1
    local entry
    local metadata
    local mode
    local indexed_path

    while IFS= read -r -d '' entry; do
        metadata=${entry%%$'\t'*}
        indexed_path=${entry#*$'\t'}
        mode=${metadata%% *}
        if [[ "${indexed_path}" == "${path}" && "${mode}" == 160000 ]]; then
            return 0
        fi
    done < <(git -C "${_REPO_ROOT}" ls-files --stage -z -- "${path}" 2>/dev/null)
    return 1
}

_submodule_is_within_repo() {
    local submodule=$1
    local repo_real
    local submodule_real

    repo_real=$(cd "${_REPO_ROOT}" && pwd -P) || return 1
    submodule_real=$(cd "${submodule}" && pwd -P) || return 1
    [[ "${submodule_real}" == "${repo_real}/"* ]]
}

_remote_default_ref() {
    local submodule=$1
    local current_branch
    local remote_ref

    LANG=C LC_ALL=C git -C "${submodule}" remote set-head origin --auto >/dev/null 2>&1 || true
    remote_ref=$(git -C "${submodule}" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || true)
    if [[ "${remote_ref}" == origin/* ]] \
        && git -C "${submodule}" show-ref --verify --quiet "refs/remotes/${remote_ref}"; then
        printf '%s\n' "${remote_ref}"
        return 0
    fi

    current_branch=$(git -C "${submodule}" symbolic-ref --quiet --short HEAD 2>/dev/null || true)
    if [[ -n "${current_branch}" ]] \
        && git -C "${submodule}" show-ref --verify --quiet "refs/remotes/origin/${current_branch}"; then
        printf 'origin/%s\n' "${current_branch}"
        return 0
    fi
    if git -C "${submodule}" show-ref --verify --quiet refs/remotes/origin/main; then
        printf 'origin/main\n'
        return 0
    fi
    if git -C "${submodule}" show-ref --verify --quiet refs/remotes/origin/master; then
        printf 'origin/master\n'
        return 0
    fi
    return 1
}

_has_local_state() {
    local submodule=$1

    [[ -n "$(git -C "${submodule}" status --porcelain --untracked-files=all --ignored)" ]]
}

_stash_local_state() {
    local submodule=$1
    local message=$2
    local stash_before
    local stash_after

    stash_before=$(git -C "${submodule}" rev-parse --verify --quiet refs/stash 2>/dev/null || true)

    if git -C "${submodule}" stash push --all --quiet --message "${message}" >/dev/null 2>&1; then
        stash_after=$(git -C "${submodule}" rev-parse --verify --quiet refs/stash 2>/dev/null || true)
        [[ -n "${stash_after}" && "${stash_after}" != "${stash_before}" ]]
        return $?
    fi
    if git -C "${submodule}" stash save --quiet --all "${message}"; then
        stash_after=$(git -C "${submodule}" rev-parse --verify --quiet refs/stash 2>/dev/null || true)
        [[ -n "${stash_after}" && "${stash_after}" != "${stash_before}" ]]
        return $?
    fi
    return 1
}

_back_submodule() {
    local name=$1
    local path=$2
    local submodule="${_REPO_ROOT}/${path}"
    local remote_ref
    local remote_commit
    local branch
    local branch_backup_ref
    local branch_head
    local old_head
    local backup_ref
    local stash_message
    local recurse_args=(--recursive)

    if ! _validate_submodule_path "${path}"; then
        echo "ERROR: Refusing unsafe submodule path '${path}' from .gitmodules." >&2
        return 1
    fi
    if ! _is_tracked_gitlink "${path}"; then
        echo "ERROR: ${path} is mapped in .gitmodules but is not a tracked gitlink." >&2
        return 1
    fi
    if [[ ! -e "${submodule}/.git" ]]; then
        if (( _DRY_RUN )); then
            if (( _INIT )); then
                echo "DRY-RUN: would initialize and force-align ${path}"
            else
                echo "SKIP: ${path} is not initialized (use --init to initialize it)."
            fi
            return 0
        fi
        if (( ! _INIT )); then
            echo "SKIP: ${path} is not initialized (use --init to initialize it)."
            return 0
        fi
        echo "INIT:    ${path}"
        if ! LANG=C LC_ALL=C git -C "${_REPO_ROOT}" submodule update --init -- "${path}"; then
            echo "ERROR: Failed to initialize submodule ${path}." >&2
            return 1
        fi
    fi

    if ! _submodule_is_within_repo "${submodule}"; then
        echo "ERROR: Refusing submodule path outside repository: ${path}" >&2
        return 1
    fi

    if (( _DRY_RUN )); then
        echo "DRY-RUN: would force-align ${path} to origin's default branch"
    else
        _git_prepare_index_lock "${submodule}" || return 1
        if ! LANG=C LC_ALL=C git -C "${submodule}" fetch --prune origin; then
            echo "ERROR: Failed to fetch submodule ${path}." >&2
            return 1
        fi
        if ! remote_ref=$(_remote_default_ref "${submodule}"); then
            echo "ERROR: Unable to resolve origin's default branch for ${path}." >&2
            return 1
        fi
        remote_commit=$(git -C "${submodule}" rev-parse --verify "${remote_ref}^{commit}") || return 1
        old_head=$(git -C "${submodule}" rev-parse --verify HEAD) || return 1
        branch=${remote_ref#origin/}
        backup_ref="refs/gback-sub-backups/$(date "+%Y%m%d%H%M%S")-${old_head:0:12}-$$"
        if ! git -C "${submodule}" update-ref "${backup_ref}" "${old_head}"; then
            echo "ERROR: Unable to preserve old HEAD for ${path}." >&2
            return 1
        fi
        echo "BACKUP: ${path} HEAD ${old_head:0:12} -> ${backup_ref}"

        if _has_local_state "${submodule}"; then
            stash_message="gback-sub backup $(date "+%Y-%m-%d-%H-%M-%S") ${path}"
            if ! _stash_local_state "${submodule}" "${stash_message}"; then
                echo "ERROR: Unable to stash local state for ${path}." >&2
                return 1
            fi
            echo "BACKUP: ${path} dirty state -> git stash"
        fi

        if git -C "${submodule}" show-ref --verify --quiet "refs/heads/${branch}"; then
            branch_head=$(git -C "${submodule}" rev-parse --verify "refs/heads/${branch}") || return 1
            if [[ "${branch_head}" != "${old_head}" && "${branch_head}" != "${remote_commit}" ]]; then
                branch_backup_ref="${backup_ref}-branch"
                if ! git -C "${submodule}" update-ref "${branch_backup_ref}" "${branch_head}"; then
                    echo "ERROR: Unable to preserve local branch ${branch} for ${path}." >&2
                    return 1
                fi
                echo "BACKUP: ${path} branch ${branch} ${branch_head:0:12} -> ${branch_backup_ref}"
            fi
        fi

        if ! git -C "${submodule}" checkout -B "${branch}" --track "${remote_ref}"; then
            echo "ERROR: Unable to restore branch ${branch} for ${path}." >&2
            return 1
        fi
        if ! git -C "${submodule}" reset --hard "${remote_commit}"; then
            echo "ERROR: Unable to reset ${path} to ${remote_ref}." >&2
            return 1
        fi
        if ! git -C "${submodule}" clean -fdx; then
            echo "ERROR: Unable to clean ${path} after reset." >&2
            return 1
        fi
        if [[ "$(git -C "${submodule}" rev-parse HEAD)" != "${remote_commit}" ]]; then
            echo "ERROR: ${path} did not align to ${remote_ref}." >&2
            return 1
        fi
        echo "RESTORED: ${path} ${old_head:0:12}..${remote_commit:0:12} (${remote_ref})"
    fi

    if (( _RECURSIVE )) && [[ -f "${submodule}/.gitmodules" ]]; then
        (( _INIT )) && recurse_args+=(--init)
        (( _DRY_RUN )) && recurse_args+=(--dry-run)
        [[ -n "${_TARGET}" ]] && recurse_args+=(-t "${_TARGET}")
        if ! (cd "${submodule}" && bash "${_PATH}/${_NAME}" "${recurse_args[@]}"); then
            echo "ERROR: Nested submodule restore failed under ${path}." >&2
            return 1
        fi
    fi
}

_SELECTED=0
_PROCESSED=0
_FAILED=0

while IFS=' ' read -r key path; do
    [[ -n "${key}" && -n "${path}" ]] || continue
    name=${key#submodule.}
    name=${name%.path}
    if ! _matches_filter "${path}" "${name}"; then
        continue
    fi
    _SELECTED=$((_SELECTED + 1))
    echo
    echo "### Submodule: ${path} ###"
    if _back_submodule "${name}" "${path}"; then
        _PROCESSED=$((_PROCESSED + 1))
    else
        _FAILED=$((_FAILED + 1))
    fi
done <<< "${_ENTRIES}"

if (( _SELECTED == 0 )); then
    echo "ERROR: No mapped submodule matched the requested path or name." >&2
    _FAILED=1
fi

echo
echo "Summary: selected=${_SELECTED} processed=${_PROCESSED} failed=${_FAILED}"
if (( _DRY_RUN )); then
    echo "Mode:    dry-run"
fi
if (( _PROCESSED > 0 && ! _DRY_RUN )); then
    echo "Notice:  Submodule HEAD changes appear as gitlink updates in the parent repository."
fi
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"

if (( _FAILED > 0 )); then
    exit 1
fi
