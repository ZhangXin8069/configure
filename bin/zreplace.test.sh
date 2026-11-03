#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

TEST_DIR="${_PATH}/.zreplace-test.$$"
cleanup() {
    rm -rf -- "${TEST_DIR}"
}
trap cleanup EXIT
mkdir -p "${TEST_DIR}"

_fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

_run_zreplace() {
    local directory=$1
    local search_text=$2
    local replacement_text=$3
    local answer=$4
    local output=$5

    if ! printf '%s\n' "${answer}" |
        TERM=xterm bash "${_PATH}/zreplace.sh" \
            "${directory}" "${search_text}" "${replacement_text}" >"${output}" 2>&1; then
        cat "${output}" >&2
        return 1
    fi
}

_test_confirmed_replacement() {
    local directory="${TEST_DIR}/confirm case"
    local output="${TEST_DIR}/confirm.log"

    mkdir -p "${directory}/nested"
    printf 'libqcu\nprefix-libqcu-suffix\nlibqxcu\n' >"${directory}/one.txt"
    printf 'libqcu\n' >"${directory}/nested/two.txt"
    printf 'filename match only\n' >"${directory}/libqcu_filename.txt"
    printf 'untouched\n' >"${directory}/untouched.txt"
    printf 'libqcu\0binary\n' >"${directory}/binary.dat"

    _run_zreplace "${directory}" libqcu libquda y "${output}"

    grep -Fxq -- 'libquda' "${directory}/one.txt" \
        || _fail "未替换第一处匹配"
    grep -Fxq -- 'prefix-libquda-suffix' "${directory}/one.txt" \
        || _fail "未替换行内匹配"
    grep -Fxq -- 'libqxcu' "${directory}/one.txt" \
        || _fail "误替换非匹配字段"
    grep -Fxq -- 'libquda' "${directory}/nested/two.txt" \
        || _fail "未递归替换嵌套文件"
    grep -Fxq -- 'filename match only' "${directory}/libqcu_filename.txt" \
        || _fail "仅文件名命中的文件内容被修改"
    cmp -s <(printf 'libqcu\0binary\n') "${directory}/binary.dat" \
        || _fail "二进制文件被修改"
    grep -Fq -- 'Matched 3 occurrence(s) in 2 file(s)' "${output}" \
        || _fail "预览统计不正确"
    grep -Fq -- 'Replaced 3 occurrence(s) in 2 file(s)' "${output}" \
        || _fail "替换统计不正确"
}

_test_cancel_leaves_files_unchanged() {
    local directory="${TEST_DIR}/cancel"
    local output="${TEST_DIR}/cancel.log"

    mkdir -p "${directory}"
    printf 'libqcu\n' >"${directory}/one.txt"

    _run_zreplace "${directory}" libqcu libquda n "${output}"

    grep -Fxq -- 'libqcu' "${directory}/one.txt" \
        || _fail "取消后文件内容发生变化"
    grep -Fq -- 'Canceled; no files changed.' "${output}" \
        || _fail "取消操作未给出明确提示"
}

_test_literal_special_characters() {
    local directory="${TEST_DIR}/literal"
    local output="${TEST_DIR}/literal.log"

    mkdir -p "${directory}"
    printf 'a.b axb a.b\n' >"${directory}/one.txt"

    _run_zreplace "${directory}" 'a.b' 'x&y\1' y "${output}"

    grep -Fxq -- 'x&y\1 axb x&y\1' "${directory}/one.txt" \
        || _fail "特殊字符未被按字面替换"
}

_test_no_match_does_not_prompt() {
    local directory="${TEST_DIR}/no-match"
    local output="${TEST_DIR}/no-match.log"

    mkdir -p "${directory}"
    printf 'unrelated\n' >"${directory}/one.txt"

    TERM=xterm bash "${_PATH}/zreplace.sh" \
        "${directory}" missing replacement </dev/null >"${output}" 2>&1

    grep -Fq -- 'No literal file-content matches' "${output}" \
        || _fail "无匹配时未输出明确结果"
}

_test_missing_confirmation_is_canceled() {
    local directory="${TEST_DIR}/missing-confirmation"
    local output="${TEST_DIR}/missing-confirmation.log"

    mkdir -p "${directory}"
    printf 'libqcu\n' >"${directory}/one.txt"

    if TERM=xterm bash "${_PATH}/zreplace.sh" \
        "${directory}" libqcu libquda </dev/null >"${output}" 2>&1; then
        _fail "缺少确认答案时仍成功退出"
    fi
    grep -Fxq -- 'libqcu' "${directory}/one.txt" \
        || _fail "缺少确认答案时文件被修改"
    grep -Fq -- 'No confirmation received; canceled.' "${output}" \
        || _fail "缺少确认答案时未输出取消原因"
}

main() {
    _test_confirmed_replacement
    _test_cancel_leaves_files_unchanged
    _test_literal_special_characters
    _test_no_match_does_not_prompt
    _test_missing_confirmation_is_canceled
}

main
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
