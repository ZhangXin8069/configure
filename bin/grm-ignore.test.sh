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
    printf 'ignored unicode\n' > "${repo}/ignored 中文.log"
    printf 'legacy regular file\n' > "${repo}/transition"
    mkdir -p "${repo}/a-symlink-parent"
    printf 'ignored through a future symlink\n' > "${repo}/a-symlink-parent/ignored.log"
    ln -s keep.txt "${repo}/tracked-link"
    ln -s keep.txt "${repo}/removed-link"
    mkdir -p "${repo}/data" "${repo}/nested/data" "${repo}/database" "${repo}/a/metadata"
    printf 'runtime data\n' > "${repo}/data/runtime-cache"
    printf 'nested runtime data\n' > "${repo}/nested/data/runtime-cache"
    printf 'database data\n' > "${repo}/database/runtime-cache"
    printf 'metadata data\n' > "${repo}/a/metadata/runtime-cache"
    printf 'protected data\n' > "${repo}/data/secret.cache"
    mkdir -p "${repo}/literal:data"
    printf 'literal directive filename\n' > "${repo}/literal:data/secret.cache"
    printf 'literal symlink directive filename\n' > "${repo}/literal:tracked-link"
    printf 'glob directive filename\n' > "${repo}/glob:*"
    printf 'regex directive filename\n' > "${repo}/regex:.*"
    printf 'rename directive filename\n' > "${repo}/victim==>renamed"
    printf 'comment directive filename\n' > "${repo}/#ignored"
    printf 'victim\n' > "${repo}/victim.txt"
    for index in $(seq -w 1 301); do
        printf 'ignored\n' > "${repo}/ignored-${index}.log"
    done
    git -C "${repo}" add .
    git -C "${repo}" commit -q -m 'track files before ignore rules'
    git -C "${repo}" rm -q removed-link transition
    git -C "${repo}" rm -r -q a-symlink-parent
    ln -s data "${repo}/a-symlink-parent"
    git -C "${repo}" add a-symlink-parent
    mkdir -p "${repo}/transition/data"
    ln -s ../keep.txt "${repo}/transition/link"
    printf 'transition data\n' > "${repo}/transition/data/runtime-cache"
    git -C "${repo}" add transition
    git -C "${repo}" commit -q -m 'replace a regular file with a protected directory'

    printf '%s\n' '*' '!*/' 'transition/' '!*.txt' '!.gitignore' > "${repo}/.gitignore"
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
    local head_before refs_before blob_before head_after refs_after blob_after

    _make_fixture "${repo}"
    head_before=$(git -C "${repo}" rev-parse HEAD)
    refs_before=$(git -C "${repo}" for-each-ref --format='%(refname) %(objectname)' | sort)
    blob_before=$(git -C "${repo}" rev-parse HEAD:ignored-001.log)
    status=$(_run_dry_run "${repo}" "${output}")
    ((status == 0)) || {
        cat "${output}" >&2
        _fail "dry-run 在超过 300 个命中项时应正常结束，实际退出码 ${status}"
    }
    head_after=$(git -C "${repo}" rev-parse HEAD)
    refs_after=$(git -C "${repo}" for-each-ref --format='%(refname) %(objectname)' | sort)
    blob_after=$(git -C "${repo}" rev-parse HEAD:ignored-001.log)
    [[ "${head_after}" == "${head_before}" ]] \
        || _fail "dry-run 修改了 HEAD"
    [[ "${refs_after}" == "${refs_before}" ]] \
        || _fail "dry-run 修改了 Git refs"
    [[ "${blob_after}" == "${blob_before}" ]] \
        || _fail "dry-run 修改了历史对象"

    grep -Fxq '  ignored-001.log' "${output}" || {
        cat "${output}" >&2
        _fail "dry-run 未列出被忽略文件"
    }
    grep -Eq '^  \.\.\. \(还有 [1-9][0-9]* 个\)$' "${output}" || {
        cat "${output}" >&2
        _fail "dry-run 未正确截断长列表"
    }
    ! grep -Fxq '  keep.txt' "${output}" || {
        cat "${output}" >&2
        _fail "否定规则中的未忽略文件被误判"
    }
    ! grep -Fxq '  tracked-link' "${output}" || {
        cat "${output}" >&2
        _fail "dry-run 将历史软链接列为删除候选"
    }
    ! grep -Fxq '  removed-link' "${output}" || {
        cat "${output}" >&2
        _fail "dry-run 将已从当前树删除的历史软链接列为删除候选"
    }
    grep -Fxq '  data/runtime-cache' "${output}" || {
        cat "${output}" >&2
        _fail "dry-run 未匹配被忽略的根级 data 文件"
    }
    ! grep -Fxq '  transition' "${output}" || {
        cat "${output}" >&2
        _fail "dry-run 未保护受保护后代的祖先文件路径"
    }
    ! grep -Fxq '  transition/link' "${output}" || {
        cat "${output}" >&2
        _fail "dry-run 将路径类型转换后的软链接列为删除候选"
    }
    grep -Fxq '  database/runtime-cache' "${output}" || {
        cat "${output}" >&2
        _fail "dry-run 将 database 目录误判为 data 目录"
    }
    grep -Fxq '  a/metadata/runtime-cache' "${output}" || {
        cat "${output}" >&2
        _fail "dry-run 将 metadata 目录误判为 data 目录"
    }
    ! grep -Fq '穿过当前软链接的历史路径（无法安全分类）' "${output}" || {
        cat "${output}" >&2
        _fail "dry-run 未通过影子工作树恢复 symlink 后的 ignore 路径"
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
    if git -C "${repo}" cat-file -e HEAD:ignored-301.log 2>/dev/null; then
        _fail "重写后仍保留内容相同的后续被忽略文件"
    fi
    if git -C "${repo}" cat-file -e 'HEAD:ignored 中文.log' 2>/dev/null; then
        _fail "重写后仍保留含中文的被忽略文件"
    fi
    if git -C "${repo}" log --all --pretty=format: --name-only --no-renames \
        | grep -Eq '^ignored.*\.log$'; then
        _fail "重写后历史中仍有被忽略文件"
    fi
    git -C "${repo}" cat-file -e HEAD:.gitignore 2>/dev/null \
        || _fail "重写后误删 .gitignore"
    [[ "$(git -C "${repo}" ls-tree HEAD -- tracked-link | awk '{print $1}')" == 120000 ]] || {
        cat "${output}" >&2
        _fail "重写后未保留历史软链接 tracked-link"
    }
    if git -C "${repo}" cat-file -e HEAD:data/runtime-cache 2>/dev/null; then
        _fail "重写后仍保留根级 data 目录中的被忽略文件"
    fi
    if git -C "${repo}" cat-file -e HEAD:nested/data/runtime-cache 2>/dev/null; then
        _fail "重写后仍保留嵌套 data 目录中的被忽略文件"
    fi
    if git -C "${repo}" cat-file -e HEAD:data/secret.cache 2>/dev/null; then
        _fail "重写后仍保留 data 目录中的被忽略文件"
    fi
    git -C "${repo}" cat-file -e HEAD:victim.txt 2>/dev/null \
        || _fail "paths-from-file 重命名指令被当作字面文件名处理"
    if git -C "${repo}" cat-file -e HEAD:renamed.txt 2>/dev/null; then
        _fail "paths-from-file 重命名指令意外改写了普通文件"
    fi
    if git -C "${repo}" cat-file -e 'HEAD:literal:data/secret.cache' 2>/dev/null; then
        _fail "literal: 特殊文件未被作为普通忽略文件删除"
    fi
    if git -C "${repo}" cat-file -e 'HEAD:literal:tracked-link' 2>/dev/null; then
        _fail "literal: 特殊文件未被作为普通忽略文件删除（protected symlink 场景）"
    fi
    if git -C "${repo}" cat-file -e 'HEAD:glob:*' 2>/dev/null; then
        _fail "glob: 特殊文件未被作为普通忽略文件删除"
    fi
    if git -C "${repo}" cat-file -e 'HEAD:regex:.*' 2>/dev/null; then
        _fail "regex: 特殊文件未被作为普通忽略文件删除"
    fi
    if git -C "${repo}" cat-file -e 'HEAD:victim==>renamed' 2>/dev/null; then
        _fail "==> 特殊文件未被作为普通忽略文件删除"
    fi
    if git -C "${repo}" cat-file -e 'HEAD:#ignored' 2>/dev/null; then
        _fail "# 特殊文件未被作为普通忽略文件删除"
    fi
    [[ "$(git -C "${repo}" ls-tree HEAD -- transition/link | awk '{print $1}')" == 120000 ]] || {
        cat "${output}" >&2
        _fail "重写后未保留路径类型转换后的软链接"
    }
    git -C "${repo}" log --all --raw --no-renames --format= -- transition \
        | grep -Eq '^:000000 100644 ' \
        || _fail "重写后未保留路径类型转换前的普通文件历史"
    if git -C "${repo}" cat-file -e HEAD:transition/data/runtime-cache 2>/dev/null; then
        _fail "重写后仍保留路径类型转换后的 data 目录文件"
    fi
    if git -C "${repo}" cat-file -e HEAD:database/runtime-cache 2>/dev/null; then
        _fail "重写后未清除 database 目录中的被忽略文件"
    fi
    if git -C "${repo}" cat-file -e HEAD:a/metadata/runtime-cache 2>/dev/null; then
        _fail "重写后未清除 metadata 目录中的被忽略文件"
    fi
    git -C "${repo}" log --all --raw --no-renames --format= -- removed-link \
        | grep -Eq '^:[0-7]{6} 120000 ' \
        || _fail "重写后未保留已删除历史软链接的对象记录"
    if git -C "${repo}" log --all --raw --no-renames --format= -- a-symlink-parent/ignored.log \
        | grep -Eq '^:[0-7]{6} 100644 '; then
        _fail "重写后仍保留应由影子工作树分类并删除的历史文件"
    fi
}

main() {
    command -v git-filter-repo >/dev/null || _fail "测试依赖 git-filter-repo"
    _test_dry_run_selects_only_ignored_paths
    _test_rewrite_removes_ignored_history
}

main
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
