#!/usr/bin/env bash

_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

TEST_DIR="${_PATH}/.git-remote-wrappers-test.$$"
cleanup() {
    rm -rf -- "${TEST_DIR}"
}
trap cleanup EXIT

_fail() {
    echo "FAIL: $*" >&2
    exit 1
}

_write_fake_base() {
    local path=$1

    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'printf "%s %s\n" "${0##*/}" "$*" >> "${WRAPPER_CALL_LOG:?}"' >"${path}"
    chmod +x "${path}"
}

_wrapper_base() {
    case "$1" in
        *-pull-sub.sh) printf 'gpull-sub.sh\n' ;;
        *-back-sub.sh) printf 'gback-sub.sh\n' ;;
        *-pull.sh) printf 'gpull.sh\n' ;;
        *-back.sh) printf 'gback.sh\n' ;;
        *-push.sh) printf 'gpush.sh\n' ;;
        *) return 1 ;;
    esac
}

_test_base_cli_contract() {
    local script
    local status

    for script in gpush.sh gpull.sh gback.sh gpull-sub.sh gback-sub.sh \
        zg-all-pull.sh grm-ignore.sh; do
        grep -Fq '_git_remote_target_apply' "${_PATH}/${script}" \
            || _fail "${script} does not apply the temporary remote target"
        bash "${_PATH}/${script}" --help >"${TEST_DIR}/${script}.help.log" 2>&1
        grep -Fq -- '-t, --target' "${TEST_DIR}/${script}.help.log" \
            || _fail "${script} help does not document -t"
        grep -Eq 'when omitted|when -t/--target is omitted' "${TEST_DIR}/${script}.help.log" \
            || _fail "${script} help does not document the default target for omitted -t"

        set +e
        (cd "${_PATH}/.." && bash "${_PATH}/${script}" -t example.com) \
            >"${TEST_DIR}/${script}.invalid.log" 2>&1
        status=$?
        set -e
        [[ "${status}" -eq 64 ]] \
            || _fail "${script} invalid target returned ${status}, expected 64"
    done
}

main() {
    local bin="${TEST_DIR}/configure/bin"
    local call_log="${TEST_DIR}/calls.log"
    local wrapper
    local base
    local wrapper_name
    local actual

    mkdir -p "${TEST_DIR}"
    _test_base_cli_contract

    mkdir -p "${bin}" "${TEST_DIR}/configure/.git" \
        "${TEST_DIR}/MyQCD/.git" "${TEST_DIR}/PyQCD/.git" "${TEST_DIR}/PyQCU/.git"
    for base in gpull.sh gpull-sub.sh gback.sh gback-sub.sh gpush.sh; do
        _write_fake_base "${bin}/${base}"
    done

    while IFS= read -r wrapper; do
        [[ -n "${wrapper}" ]] || continue
        wrapper_name=${wrapper##*/}
        case "${wrapper_name}" in
            *-all-*) continue ;;
        esac
        base=$(_wrapper_base "${wrapper_name}") || _fail "no base mapping for ${wrapper_name}"
        cp "${wrapper}" "${bin}/${wrapper_name}"
        : >"${call_log}"
        WRAPPER_CALL_LOG="${call_log}" bash "${bin}/${wrapper_name}" -t github.com \
            >"${TEST_DIR}/${wrapper_name}.log" 2>&1
        actual=$(cat "${call_log}")
        [[ "${actual}" == "${base} -t github.com" ]] \
            || _fail "${wrapper_name} did not forward -t (got: ${actual})"
    done < <(
        compgen -G "${_PATH}/zg-*-pull.sh"
        compgen -G "${_PATH}/zg-*-pull-sub.sh"
        compgen -G "${_PATH}/zg-*-back.sh"
        compgen -G "${_PATH}/zg-*-back-sub.sh"
        compgen -G "${_PATH}/gz-*-push.sh"
    )
}

main "$@"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
