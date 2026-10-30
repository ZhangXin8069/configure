#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

TEST_DIR="${_PATH}/.grm-ignore-test.$$"
cleanup() {
    rm -rf -- "${TEST_DIR}"
}
trap cleanup EXIT
mkdir -p "${TEST_DIR}"

_fail() {
    echo "FAIL: $*" >&2
    exit 1
}

_make_fixture() {
    local repo=$1
    local index

    git init -q "${repo}"
    git -C "${repo}" config user.name grm-ignore-test
    git -C "${repo}" config user.email grm-ignore-test@example.invalid
    git -C "${repo}" checkout -q -b main

    printf 'keep\n' > "${repo}/keep.txt"
    for index in $(seq -w 1 301); do
        printf 'ignored\n' > "${repo}/ignored-${index}.log"
    done
    git -C "${repo}" add .
    git -C "${repo}" commit -q -m 'track files before ignore rules'

    printf '%s\n' '*' '!*/' '!*.txt' '!.gitignore' > "${repo}/.gitignore"
    git -C "${repo}" add .gitignore
    git -C "${repo}" commit -q -m 'ignore log files'
}

_run_dry_run() {
    local repo=$1
    local output_file=$2
    local status

    set +e
    (
        cd "${repo}"
        bash "${_PATH}/grm-ignore.sh" -n -r origin
    ) > "${output_file}" 2>&1
    status=$?
    set -e
    printf '%s\n' "${status}"
}

_test_dry_run_selects_only_ignored_paths() {
    local repo="${TEST_DIR}/dry-run-repo"
    local output="${TEST_DIR}/dry-run.log"
    local status

    _make_fixture "${repo}"
    status=$(_run_dry_run "${repo}" "${output}")
    ((status == 0)) || {
        cat "${output}" >&2
        _fail "dry-run 在超过 300 个命中项时应正常结束，实际退出码 ${status}"
    }

    grep -Fxq '  ignored-001.log' "${output}" || {
        cat "${output}" >&2
        _fail "dry-run 未列出被忽略文件"
    }
    grep -Fxq '  ... (还有 1 个)' "${output}" || {
        cat "${output}" >&2
        _fail "dry-run 未正确截断长列表"
    }
    ! grep -Fxq '  keep.txt' "${output}" || {
        cat "${output}" >&2
        _fail "否定规则中的未忽略文件被误判"
    }
}

_test_rewrite_removes_ignored_history() {
    local repo="${TEST_DIR}/rewrite-repo"
    local output="${TEST_DIR}/rewrite.log"

    _make_fixture "${repo}"
    (
        cd "${repo}"
        bash "${_PATH}/grm-ignore.sh" -y --no-push --no-gc
    ) > "${output}" 2>&1 || {
        cat "${output}" >&2
        _fail "隔离仓库中的历史重写失败"
    }

    git -C "${repo}" cat-file -e HEAD:keep.txt 2>/dev/null \
        || _fail "重写后未保留未忽略文件"
    if git -C "${repo}" cat-file -e HEAD:ignored-001.log 2>/dev/null; then
        _fail "重写后仍保留被忽略文件"
    fi
    git -C "${repo}" cat-file -e HEAD:.gitignore 2>/dev/null \
        || _fail "重写后误删 .gitignore"
}

main() {
    command -v git-filter-repo >/dev/null || _fail "测试依赖 git-filter-repo"
    _test_dry_run_selects_only_ignored_paths
    _test_rewrite_removes_ignored_history
}

main
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
