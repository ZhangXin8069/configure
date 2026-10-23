#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail
export GIT_ALLOW_PROTOCOL=file

TEST_DIR="${_PATH}/.gback-sub-test.$$"
cleanup() {
    rm -rf -- "${TEST_DIR}"
}
trap cleanup EXIT
mkdir -p "${TEST_DIR}"

_fail() {
    echo "FAIL: $*" >&2
    exit 1
}

_configure_identity() {
    local repo=$1
    git -C "${repo}" config user.name gback-sub-test
    git -C "${repo}" config user.email gback-sub-test@example.invalid
}

_create_remote() {
    local remote=$1
    local seed=$2

    git init -q --bare "${remote}"
    git -C "${remote}" symbolic-ref HEAD refs/heads/trunk
    git init -q "${seed}"
    _configure_identity "${seed}"
    git -C "${seed}" checkout -q -b trunk
    printf 'base\n' > "${seed}/value.txt"
    git -C "${seed}" add value.txt
    git -C "${seed}" commit -q -m initial
    git -C "${seed}" remote add origin "${remote}"
    git -C "${seed}" push -q -u origin trunk
}

_test_force_remote_default_with_backups() {
    local remote="${TEST_DIR}/remote.git"
    local seed="${TEST_DIR}/seed"
    local super="${TEST_DIR}/super"
    local submodule="${super}/refer/forced-sub"
    local local_commit

    _create_remote "${remote}" "${seed}"
    git init -q "${super}"
    _configure_identity "${super}"
    git -C "${super}" checkout -q -b main
    printf 'super\n' > "${super}/README.md"
    git -C "${super}" add README.md
    git -C "${super}" commit -q -m super-initial
    git -C "${super}" -c protocol.file.allow=always submodule add -q "${remote}" refer/forced-sub
    git -C "${super}" commit -q -am add-submodule
    git -C "${super}" config protocol.file.allow always

    git -C "${submodule}" checkout -q --detach HEAD
    printf 'detached local\n' > "${submodule}/local-only.txt"
    git -C "${submodule}" add local-only.txt
    git -C "${submodule}" commit -q -m detached-local
    local_commit=$(git -C "${submodule}" rev-parse HEAD)
    printf 'dirty tracked\n' > "${submodule}/value.txt"
    printf 'untracked scratch\n' > "${submodule}/scratch.txt"

    printf 'latest remote\n' > "${seed}/value.txt"
    git -C "${seed}" add value.txt
    git -C "${seed}" commit -q -m latest-remote
    git -C "${seed}" push -q

    (cd "${super}" && bash "${_PATH}/gback-sub.sh" --dry-run --path refer/forced-sub) \
        > "${TEST_DIR}/dry-run.log" 2>&1
    [[ "$(git -C "${submodule}" rev-parse HEAD)" == "${local_commit}" ]] \
        || _fail "dry-run 不应改变子模块 HEAD"
    [[ -f "${submodule}/local-only.txt" ]] || _fail "dry-run 不应删除本地文件"

    (cd "${super}" && bash "${_PATH}/gback-sub.sh" --path refer/forced-sub) \
        > "${TEST_DIR}/restore.log" 2>&1

    [[ "$(git -C "${submodule}" symbolic-ref --quiet --short HEAD)" == trunk ]] \
        || _fail "未恢复到远端默认分支 trunk"
    grep -Fqx 'latest remote' "${submodule}/value.txt" || _fail "未强制覆盖为远端最新内容"
    [[ ! -e "${submodule}/local-only.txt" ]] || _fail "本地提交文件未被清理"
    [[ ! -e "${submodule}/scratch.txt" ]] || _fail "未跟踪文件未被清理"
    [[ -n "$(git -C "${submodule}" stash list)" ]] || _fail "本地脏状态未保存到 stash"
    git -C "${submodule}" for-each-ref --format='%(objectname)' refs/gback-sub-backups \
        | grep -Fqx "${local_commit}" || _fail "旧 HEAD 未保留备份引用"
    grep -Fq 'BACKUP:' "${TEST_DIR}/restore.log" || _fail "缺少备份提示"
    grep -Fq 'RESTORED: refer/forced-sub' "${TEST_DIR}/restore.log" || _fail "缺少恢复成功提示"
    git -C "${super}" diff --quiet --cached -- refer/forced-sub \
        || _fail "gback-sub 不应自动暂存父库 gitlink"
}

main() {
    _test_force_remote_default_with_backups
}

main "$@"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
