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

_assert_contains() {
    local output=$1
    local expected=$2

    [[ $output == *"$expected"* ]] || _fail "输出缺少内容：$expected"
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

_create_mib_file() {
    local file=$1
    local mib=$2
    local extra_byte=${3:-0}

    dd if=/dev/zero of="$file" bs=1048576 count="$mib" 2>/dev/null
    (( extra_byte == 0 )) || printf 'x' >>"$file"
}

_create_large_files_repo() {
    local repo=$1

    mkdir -p "$repo/nested"
    git -C "$repo" init -q -b main
    git -C "$repo" config user.name 'configure test'
    git -C "$repo" config user.email 'configure-test@example.invalid'

    _create_mib_file "$repo/small-at-threshold.bin" 1
    _create_mib_file "$repo/nested/blue one plus.bin" 1 1
    _create_mib_file "$repo/nested/blue five exact.bin" 5
    _create_mib_file "$repo/nested/yellow five plus.bin" 5 1
    _create_mib_file "$repo/nested/yellow ten exact.bin" 10
    _create_mib_file "$repo/nested/red ten plus one.bin" 10 1
    _create_mib_file "$repo/nested/duplicate-a.bin" 2
    _create_mib_file "$repo/nested/duplicate-b.bin" 2

    git -C "$repo" add -- \
        small-at-threshold.bin \
        'nested/blue one plus.bin' \
        'nested/blue five exact.bin' \
        'nested/yellow five plus.bin' \
        'nested/yellow ten exact.bin' \
        'nested/red ten plus one.bin' \
        'nested/duplicate-a.bin' \
        'nested/duplicate-b.bin'
    git -C "$repo" commit -q -m 'add large file fixtures'
    git -C "$repo" branch audit-branch
    git -C "$repo" tag -a audit-tag -m 'large file audit fixture'

    git -C "$repo" rm -q -- 'nested/red ten plus one.bin'
    git -C "$repo" commit -q -m 'delete history-only large file'
}

_run_git_large_files_case() {
    local shell_path=$1
    local repo=$2
    local color_mode=$3
    local stdout_file=$test_root/git-large-files.out
    local stderr_file=$test_root/git-large-files.err
    local status

    set +e
    "$shell_path" -c '
        source "$1" >/dev/null 2>&1
        cd "$2" || exit 1
        GET_GIT_LARGE_FILES_COLOR=$3
        export GET_GIT_LARGE_FILES_COLOR
        get_git_large_files
    ' configure-env-test "$env_file" "$repo" "$color_mode" \
        >"$stdout_file" 2>"$stderr_file"
    status=$?
    set -e

    (( status == 0 )) || _fail "$shell_path 的 get_git_large_files 返回 $status"
    cat "$stdout_file"
    cat "$stderr_file" >&2
}

_check_git_large_files_output() {
    local shell_path=$1
    local repo=$2
    local output=$3
    local color_mode=$4
    local base_commit red_oid red_row duplicate_oid duplicate_a_row duplicate_b_row

    base_commit=$(git -C "$repo" rev-parse 'audit-tag^{commit}')
    red_oid=$(git -C "$repo" rev-parse "$base_commit:nested/red ten plus one.bin")
    duplicate_oid=$(git -C "$repo" rev-parse "$base_commit:nested/duplicate-a.bin")
    red_row=$(grep -F '路径=[nested/red ten plus one.bin]' <<<"$output")
    duplicate_a_row=$(grep -F '路径=[nested/duplicate-a.bin]' <<<"$output")
    duplicate_b_row=$(grep -F '路径=[nested/duplicate-b.bin]' <<<"$output")

    [[ -n "$red_row" ]] || _fail "$shell_path 未输出已从当前分支删除的历史大文件"
    _assert_contains "$red_row" '分支=[audit-branch,main]'
    _assert_contains "$red_row" '标签=[audit-tag]'
    _assert_contains "$red_row" "提交=[$base_commit]"
    _assert_contains "$red_row" '文件名=[red ten plus one.bin]'
    _assert_contains "$red_row" '10.00 MiB (10485761 bytes)'
    _assert_contains "$red_row" "哈希=[$red_oid]"
    _assert_contains "$duplicate_a_row" "哈希=[$duplicate_oid]"
    _assert_contains "$duplicate_b_row" "哈希=[$duplicate_oid]"
    _assert_contains "$output" '共 7 个历史大文件版本（> 1 MiB）。'

    if grep -Fq '路径=[small-at-threshold.bin]' <<<"$output"; then
        _fail "$shell_path 错误包含了恰好 1 MiB 的文件"
    fi
    if [[ "$color_mode" == always ]]; then
        _assert_contains "$(grep -F '路径=[nested/blue one plus.bin]' <<<"$output")" \
            $'\033[34m1.00 MiB (1048577 bytes)\033[0m'
        _assert_contains "$(grep -F '路径=[nested/blue five exact.bin]' <<<"$output")" \
            $'\033[34m5.00 MiB (5242880 bytes)\033[0m'
        _assert_contains "$(grep -F '路径=[nested/yellow five plus.bin]' <<<"$output")" \
            $'\033[33m5.00 MiB (5242881 bytes)\033[0m'
        _assert_contains "$(grep -F '路径=[nested/yellow ten exact.bin]' <<<"$output")" \
            $'\033[33m10.00 MiB (10485760 bytes)\033[0m'
        _assert_contains "$red_row" $'\033[31m10.00 MiB (10485761 bytes)\033[0m'
    else
        if [[ $output == *$'\033'* ]]; then
            _fail "$shell_path 在 never 颜色模式下仍输出 ANSI 控制符"
        fi
    fi
}

_check_git_large_files_edge_cases() {
    local shell_path=$1
    local empty_repo=$2
    local non_repo=$3
    local output
    local status

    set +e
    output=$(GIT_CEILING_DIRECTORIES="$test_root" "$shell_path" -c '
        source "$1" >/dev/null 2>&1
        cd "$2" || exit 1
        get_git_large_files
    ' configure-env-test "$env_file" "$empty_repo" 2>&1)
    status=$?
    set -e
    (( status == 0 )) || _fail "$shell_path 在空仓库中应返回 0，实际为 $status"
    _assert_contains "$output" '仓库中没有可用 ref 或提交'

    set +e
    output=$(GIT_CEILING_DIRECTORIES="$test_root" "$shell_path" -c '
        source "$1" >/dev/null 2>&1
        cd "$2" || exit 1
        get_git_large_files
    ' configure-env-test "$env_file" "$non_repo" 2>&1)
    status=$?
    set -e
    (( status == 1 )) || _fail "$shell_path 在非 Git 目录中应返回 1，实际为 $status"
    _assert_contains "$output" '当前目录不在 Git 仓库中'
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
    local large_files_repo=$test_root/large-files-repo
    local empty_repo=$test_root/empty-repo
    local non_repo=$test_root/non-repo
    local large_files_output

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

    _create_large_files_repo "$large_files_repo"
    mkdir -p "$empty_repo" "$non_repo"
    git -C "$empty_repo" init -q -b main

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

        large_files_output=$(_run_git_large_files_case "$shell_path" "$large_files_repo" never) ||
            _fail "$shell_path 无法审计 Git 历史大文件"
        _check_git_large_files_output "$shell_path" "$large_files_repo" \
            "$large_files_output" never

        large_files_output=$(_run_git_large_files_case "$shell_path" "$large_files_repo" always) ||
            _fail "$shell_path 无法输出 Git 历史大文件颜色"
        _check_git_large_files_output "$shell_path" "$large_files_repo" \
            "$large_files_output" always
        _check_git_large_files_edge_cases "$shell_path" "$empty_repo" "$non_repo"
        printf '通过：%s 的历史大文件审计、颜色边界与异常边界\n' "$shell_path"
    done
}

main "$@"
