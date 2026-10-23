#!/usr/bin/env bash
# Shared filename-based discovery for *-all-* aggregate scripts.

_all_series_discover() {
    local all_name=$1
    local directory=$2
    local minimum=${ALL_SERIES_MIN:-2}
    local base
    local prefix
    local suffix
    local pattern
    local candidate
    local candidate_name
    local -a matches=()

    _ALL_SERIES_SCRIPTS=()
    _ALL_SERIES_PATTERN=

    if [[ ! "${minimum}" =~ ^[0-9]+$ ]] || (( minimum < 2 )); then
        echo "ERROR: ALL_SERIES_MIN must be an integer greater than or equal to 2; got '${minimum}'." >&2
        return 64
    fi
    case "${all_name}" in
        *-all-*.sh) ;;
        *)
            echo "ERROR: Aggregate script name must contain '-all-': ${all_name}" >&2
            return 64
            ;;
    esac

    base=${all_name%.sh}
    prefix=${base%%-all-*}
    suffix=${base#*-all-}
    pattern="${prefix}-*-${suffix}.sh"

    while IFS= read -r candidate; do
        [[ -n "${candidate}" ]] || continue
        candidate_name=${candidate##*/}
        [[ "${candidate_name}" == "${all_name}" ]] && continue
        [[ "${candidate_name}" == *-all-* ]] && continue
        if [[ ! -f "${candidate}" || ! -x "${candidate}" ]]; then
            echo "ERROR: Matched series script is not executable: ${candidate}" >&2
            return 1
        fi
        matches+=("${candidate}")
    done < <(compgen -G "${directory}/${pattern}" | LC_ALL=C sort)

    if (( ${#matches[@]} < minimum )); then
        echo "ERROR: ${all_name} requires at least ${minimum} matching ${pattern} scripts; found ${#matches[@]}." >&2
        return 1
    fi

    _ALL_SERIES_PATTERN=${pattern}
    _ALL_SERIES_SCRIPTS=("${matches[@]}")
    return 0
}

_all_series_run() {
    local script
    local status

    _ALL_SERIES_FAILED=0
    for script in "${_ALL_SERIES_SCRIPTS[@]}"; do
        echo "### Series: ${script##*/} ###"
        if bash "${script}" "$@"; then
            echo "OK: ${script##*/}"
        else
            status=$?
            _ALL_SERIES_FAILED=$((_ALL_SERIES_FAILED + 1))
            echo "ERROR: ${script##*/} failed with status ${status}" >&2
        fi
    done
}
