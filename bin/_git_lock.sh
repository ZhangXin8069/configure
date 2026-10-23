#!/usr/bin/env bash
# Recover stale Git index locks without deleting them or racing fresh locks.

_git_lock_file_mtime_epoch() {
    local file=$1
    local value

    if value=$(stat -c %Y -- "${file}" 2>/dev/null); then
        printf '%s\n' "${value}"
        return 0
    fi
    if value=$(stat -f %m "${file}" 2>/dev/null); then
        printf '%s\n' "${value}"
        return 0
    fi
    return 1
}

_git_quarantine_stale_index_lock() {
    local lock=$1
    local backup="${lock}.stale.$(date "+%Y%m%d%H%M%S").$$"

    while [[ -e "${backup}" ]]; do
        backup="${backup}.new"
    done
    if mv -- "${lock}" "${backup}"; then
        echo "RECOVERED: quarantined stale index lock as ${backup}" >&2
        return 0
    fi
    if [[ ! -e "${lock}" ]]; then
        return 0
    fi
    echo "ERROR: Unable to quarantine stale index lock: ${lock}" >&2
    return 1
}

_git_prepare_index_lock() {
    local repo=$1
    local wait_seconds=${GIT_INDEX_LOCK_WAIT_SECONDS:-${GPULL_INDEX_LOCK_WAIT_SECONDS:-15}}
    local stale_seconds=${GIT_INDEX_LOCK_STALE_SECONDS:-${GPULL_INDEX_LOCK_STALE_SECONDS:-300}}
    local lock
    local repo_root
    local waited=0
    local mtime
    local age

    if [[ ! "${wait_seconds}" =~ ^[0-9]+$ ]]; then
        echo "ERROR: GIT_INDEX_LOCK_WAIT_SECONDS must be a non-negative integer; got '${wait_seconds}'." >&2
        return 64
    fi
    if [[ ! "${stale_seconds}" =~ ^[0-9]+$ ]]; then
        echo "ERROR: GIT_INDEX_LOCK_STALE_SECONDS must be a non-negative integer; got '${stale_seconds}'." >&2
        return 64
    fi

    lock=$(git -C "${repo}" rev-parse --git-path index.lock) || return 1
    if [[ "${lock}" != /* ]]; then
        repo_root=$(git -C "${repo}" rev-parse --show-toplevel) || return 1
        lock="${repo_root}/${lock}"
    fi
    while [[ -e "${lock}" ]]; do
        if ! mtime=$(_git_lock_file_mtime_epoch "${lock}"); then
            echo "ERROR: Index lock exists and its age cannot be determined: ${lock}" >&2
            return 1
        fi
        age=$(( $(date +%s) - mtime ))
        if (( age >= stale_seconds )); then
            _git_quarantine_stale_index_lock "${lock}" || return 1
            return 0
        fi
        if (( waited >= wait_seconds )); then
            echo "ERROR: Git index lock remains active: ${lock}" >&2
            echo "Hint:  wait for the other Git process, or set GIT_INDEX_LOCK_STALE_SECONDS after confirming it is stale." >&2
            return 1
        fi
        sleep 1
        waited=$((waited + 1))
    done
}
