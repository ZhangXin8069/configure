#!/usr/bin/env bash

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
env_file=$script_dir/env.sh
test_root=$(mktemp -d "${TMPDIR:-/tmp}/configure-env-test.XXXXXX")

_cleanup() {
    rm -rf -- "$test_root"
}
trap _cleanup EXIT HUP INT TERM

_fail() {
    printf '失败：%s\n' "$*" >&2
    exit 1
}

_assert_line() {
    local output=$1
    local expected=$2

    grep -Fqx -- "$expected" <<<"$output" ||
        _fail "输出缺少行：$expected"
}

_run_case() {
    local shell_path=$1
    local fixture=$2
    local fake_bin=${3:-}
    local stdout_file=$test_root/stdout.txt
    local stderr_file=$test_root/stderr.txt
    local status

    set +e
    "$shell_path" -c '
        source "$1" >/dev/null 2>&1
        [[ -z "$2" ]] || PATH="$2:$PATH"
        get_soft_links "$3"
    ' configure-env-test "$env_file" "$fake_bin" "$fixture" \
        >"$stdout_file" 2>"$stderr_file"
    status=$?
    set -e

    (( status == 0 )) || _fail "$shell_path 返回状态码 $status"
    cat "$stdout_file"
    cat "$stderr_file" >&2
}

_check_output() {
    local shell_path=$1
    local output=$2
    local fixture=$3

    _assert_line "$output" "$fixture/valid link -> target file.txt"
    _assert_line "$output" "$fixture/.hidden link -> target file.txt"
    _assert_line "$output" "$fixture/nested/nested link -> ../target file.txt"
    _assert_line "$output" "$fixture/dir link -> dir target"
    _assert_line "$output" "$fixture/broken link -> missing target [broken]"

    if grep -Fq -- ' -> ?' <<<"$output"; then
        _fail "$shell_path 丢失了一个或多个链接目标"
    fi
    if grep -Fq -- '/.git/' <<<"$output" || grep -Fq -- '/node_modules/' <<<"$output"; then
        _fail "$shell_path 遍历了应排除的目录"
    fi
    if [[ $output == *$'\033'* ]]; then
        _fail "$shell_path 在非 TTY 输出中包含颜色控制符"
    fi
}

main() {
    local fixture=$test_root/fixtures/path\ with\ spaces
    local readlink_failure=$test_root/failing-readlink
    local ls_failure=$test_root/failing-ls
    local python_failure=$test_root/failing-python
    local false_path
    local shell_paths=()
    local -a fallback_bins=()
    local -a fallback_labels=()
    local shell_path
    local output
    local stderr_file
    local index

    mkdir -p "$fixture/nested" "$fixture/dir target" \
        "$fixture/.git" "$fixture/node_modules" \
        "$readlink_failure" "$ls_failure" "$python_failure"
    printf 'target\n' >"$fixture/target file.txt"
    ln -s 'target file.txt' "$fixture/valid link"
    ln -s 'target file.txt' "$fixture/.hidden link"
    ln -s '../target file.txt' "$fixture/nested/nested link"
    ln -s 'dir target' "$fixture/dir link"
    ln -s 'missing target' "$fixture/broken link"
    ln -s 'missing target' "$fixture/.git/ignored link"
    ln -s 'missing target' "$fixture/node_modules/ignored link"

    false_path=$(command -v false) || _fail '缺少 false 命令'
    ln -s "$false_path" "$readlink_failure/readlink"
    ln -s "$false_path" "$ls_failure/readlink"
    ln -s "$false_path" "$ls_failure/ls"
    ln -s "$false_path" "$python_failure/readlink"
    ln -s "$false_path" "$python_failure/ls"
    ln -s "$false_path" "$python_failure/python3"

    fallback_bins=("$readlink_failure")
    fallback_labels=(ls)
    if command -v python3 >/dev/null 2>&1; then
        fallback_bins+=("$ls_failure")
        fallback_labels+=(python3)
    fi
    if command -v perl >/dev/null 2>&1; then
        fallback_bins+=("$python_failure")
        fallback_labels+=(perl)
    fi

    command -v bash >/dev/null 2>&1 && shell_paths+=("$(command -v bash)")
    command -v zsh >/dev/null 2>&1 && shell_paths+=("$(command -v zsh)")
    ((${#shell_paths[@]} > 0)) || _fail '需要 bash 或 zsh'

    for shell_path in "${shell_paths[@]}"; do
        output=$(_run_case "$shell_path" "$fixture") ||
            _fail "$shell_path 的原生读取器链失败"
        _check_output "$shell_path" "$output" "$fixture"

        for index in "${!fallback_bins[@]}"; do
            output=$(_run_case "$shell_path" "$fixture" "${fallback_bins[index]}") ||
                _fail "$shell_path 的 ${fallback_labels[index]} 回退失败"
            _check_output "$shell_path" "$output" "$fixture"
            stderr_file=$test_root/stderr.txt
            _assert_line "$(<"$stderr_file")" '5 symlink(s), 1 broken'
        done
        printf '通过：%s 使用以下读取器链解析目标：readlink %s\n' \
            "$shell_path" "${fallback_labels[*]}"
    done
}

main "$@"
