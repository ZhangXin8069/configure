#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail
export GIT_ALLOW_PROTOCOL=file

TEST_DIR="${_PATH}/.gpull-sub-test.$$"
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
    git -C "${repo}" config user.name gpull-sub-test
    git -C "${repo}" config user.email gpull-sub-test@example.invalid
}

_run_gpull_sub() {
    local workdir=$1
    local log=$2
    shift 2

    set +e
    (cd "${workdir}" && bash "${_PATH}/gpull-sub.sh" "$@") > "${log}" 2>&1
    local status=$?
    set -e
    if ((status != 0)); then
        cat "${log}" >&2
    fi
    return "${status}"
}

_create_remote() {
    local remote=$1
    local seed=$2

    git init -q --bare "${remote}"
    git -C "${remote}" symbolic-ref HEAD refs/heads/main
    git init -q "${seed}"
    _configure_identity "${seed}"
    git -C "${seed}" checkout -q -b main
    printf 'base\n' > "${seed}/value.txt"
    git -C "${seed}" add value.txt
    git -C "${seed}" commit -q -m initial
    git -C "${seed}" remote add origin "${remote}"
    git -C "${seed}" push -q -u origin main
}

_create_submodule_fixture() {
    local remote=$1
    local seed=$2
    local super=$3
    local path=$4

    _create_remote "${remote}" "${seed}"
    git init -q "${super}"
    _configure_identity "${super}"
    git -C "${super}" checkout -q -b main
    printf 'super\n' > "${super}/README.md"
    git -C "${super}" add README.md
    git -C "${super}" commit -q -m super-initial
    git -C "${super}" -c protocol.file.allow=always submodule add -q "${remote}" "${path}"
    git -C "${super}" commit -q -am add-submodule
    git -C "${super}" config protocol.file.allow always
}

_test_mapped_submodule_pull() {
    local remote="${TEST_DIR}/sub-remote.git"
    local seed="${TEST_DIR}/sub-seed"
    local super="${TEST_DIR}/super"
    local submodule="${super}/refer/test-sub"
    local clone="${TEST_DIR}/super-clone"

    _create_remote "${remote}" "${seed}"
    git init -q "${super}"
    _configure_identity "${super}"
    git -C "${super}" checkout -q -b main
    printf 'super\n' > "${super}/README.md"
    git -C "${super}" add README.md
    git -C "${super}" commit -q -m super-initial
    git -C "${super}" -c protocol.file.allow=always submodule add -q "${remote}" refer/test-sub
    git -C "${super}" commit -q -am add-submodule
    git -C "${submodule}" checkout -q --detach HEAD
    git -C "${super}" config protocol.file.allow always

    printf 'remote update\n' > "${seed}/value.txt"
    git -C "${seed}" add value.txt
    git -C "${seed}" commit -q -m remote-update
    git -C "${seed}" push -q

    mkdir -p "${super}/nested/workdir"
    _run_gpull_sub "${super}/nested/workdir" "${TEST_DIR}/mapped.log" --path refer/test-sub \
        || _fail "已映射子模块 pull 失败"

    grep -Fqx 'remote update' "${submodule}/value.txt" || _fail "未拉取子模块远端更新"
    [[ "$(git -C "${submodule}" symbolic-ref --quiet --short HEAD)" == main ]] \
        || _fail "detached 子模块未恢复到远程默认分支"
    grep -Fq 'processed=1 failed=0' "${TEST_DIR}/mapped.log" || _fail "缺少成功汇总"
    grep -Fq 'Remote target: gitlab.itp.ac.cn' "${TEST_DIR}/mapped.log" \
        || _fail "gpull-sub 省略 -t 时未应用默认远程目标"
    git -C "${super}" diff --quiet --cached -- refer/test-sub \
        || _fail "脚本不应自动暂存父库 gitlink"

    git clone -q "${super}" "${clone}"
    _configure_identity "${clone}"
    git -C "${clone}" config protocol.file.allow always

    _run_gpull_sub "${clone}" "${TEST_DIR}/uninitialized.log" \
        || _fail "未初始化子模块默认跳过流程失败"
    grep -Fq 'SKIP: refer/test-sub is not initialized' "${TEST_DIR}/uninitialized.log" \
        || _fail "未初始化子模块应默认跳过"
    [[ ! -e "${clone}/refer/test-sub/.git" ]] || _fail "默认模式不应初始化子模块"

    printf 'initialized update\n' > "${seed}/value.txt"
    git -C "${seed}" add value.txt
    git -C "${seed}" commit -q -m initialized-update
    git -C "${seed}" push -q

    _run_gpull_sub "${clone}" "${TEST_DIR}/init.log" --init --path refer/test-sub \
        || _fail "--init 子模块 pull 失败"
    grep -Fqx 'initialized update' "${clone}/refer/test-sub/value.txt" \
        || _fail "--init 后未拉取子模块远端更新"

    printf 'dry run update\n' > "${seed}/value.txt"
    git -C "${seed}" add value.txt
    git -C "${seed}" commit -q -m dry-run-update
    git -C "${seed}" push -q
    _run_gpull_sub "${super}" "${TEST_DIR}/dry-run.log" --dry-run --path refer/test-sub \
        || _fail "dry-run 失败"
    grep -Fq 'DRY-RUN: would pull refer/test-sub' "${TEST_DIR}/dry-run.log" \
        || _fail "dry-run 缺少计划输出"
    grep -Fqx 'remote update' "${submodule}/value.txt" || _fail "dry-run 不应修改子模块"
}

_test_failure_propagates() {
    local remote="${TEST_DIR}/failure-remote.git"
    local seed="${TEST_DIR}/failure-seed"
    local super="${TEST_DIR}/failure-super"
    local submodule="${super}/refer/failure-sub"

    _create_remote "${remote}" "${seed}"
    git init -q "${super}"
    _configure_identity "${super}"
    git -C "${super}" checkout -q -b main
    printf 'super\n' > "${super}/README.md"
    git -C "${super}" add README.md
    git -C "${super}" commit -q -m super-initial
    git -C "${super}" -c protocol.file.allow=always submodule add -q "${remote}" refer/failure-sub
    git -C "${super}" commit -q -am add-submodule
    git -C "${submodule}" remote set-url origin "${TEST_DIR}/missing.git"

    set +e
    (cd "${super}" && bash "${_PATH}/gpull-sub.sh") > "${TEST_DIR}/failure.log" 2>&1
    local status=$?
    set -e

    ((status != 0)) || _fail "子模块 pull 失败应传播为非零退出码"
    grep -Fq 'ERROR: Pull failed for submodule refer/failure-sub.' "${TEST_DIR}/failure.log" \
        || _fail "缺少子模块 pull 失败原因"
}

_test_unmapped_gitlink_is_ignored() {
    local remote="${TEST_DIR}/ignore-remote.git"
    local seed="${TEST_DIR}/ignore-seed"
    local orphan="${TEST_DIR}/orphan"
    local super="${TEST_DIR}/ignore-super"
    local orphan_commit

    _create_remote "${remote}" "${seed}"
    git init -q "${orphan}"
    _configure_identity "${orphan}"
    git -C "${orphan}" checkout -q -b main
    printf 'orphan\n' > "${orphan}/file.txt"
    git -C "${orphan}" add file.txt
    git -C "${orphan}" commit -q -m orphan
    orphan_commit=$(git -C "${orphan}" rev-parse HEAD)

    git init -q "${super}"
    _configure_identity "${super}"
    git -C "${super}" checkout -q -b main
    printf 'super\n' > "${super}/README.md"
    git -C "${super}" add README.md
    git -C "${super}" commit -q -m super-initial
    git -C "${super}" -c protocol.file.allow=always submodule add -q "${remote}" refer/mapped-sub
    git -C "${super}" update-index --add --cacheinfo "160000,${orphan_commit},unmapped-link"
    git -C "${super}" commit -q -am add-mapped-and-unmapped

    (cd "${super}" && bash "${_PATH}/gpull-sub.sh") > "${TEST_DIR}/unmapped.log" 2>&1
    grep -Fq '### Submodule: refer/mapped-sub ###' "${TEST_DIR}/unmapped.log" \
        || _fail "未处理已映射子模块"
    ! grep -Fq 'unmapped-link' "${TEST_DIR}/unmapped.log" \
        || _fail "不应处理缺少 .gitmodules 映射的 gitlink"
}

_test_divergent_detached_submodule_uses_remote_default() {
    local remote="${TEST_DIR}/divergent-remote.git"
    local seed="${TEST_DIR}/divergent-seed"
    local super="${TEST_DIR}/divergent-super"
    local submodule="${super}/refer/divergent-sub"
    local local_commit

    _create_submodule_fixture "${remote}" "${seed}" "${super}" refer/divergent-sub
    git -C "${submodule}" checkout -q --detach HEAD
    printf 'detached local\n' > "${submodule}/local-only.txt"
    git -C "${submodule}" add local-only.txt
    git -C "${submodule}" commit -q -m detached-local
    local_commit=$(git -C "${submodule}" rev-parse HEAD)

    printf 'latest remote\n' > "${seed}/value.txt"
    git -C "${seed}" add value.txt
    git -C "${seed}" commit -q -m latest-remote
    git -C "${seed}" push -q

    _run_gpull_sub "${super}" "${TEST_DIR}/divergent.log" --path refer/divergent-sub \
        || _fail "分歧 detached 子模块应默认恢复远端主分支"

    grep -Fqx 'latest remote' "${submodule}/value.txt" \
        || _fail "分歧 detached 子模块未更新到远端最新版"
    [[ "$(git -C "${submodule}" symbolic-ref --quiet --short HEAD)" == main ]] \
        || _fail "分歧 detached 子模块未恢复到 main"
    git -C "${submodule}" for-each-ref --format='%(objectname)' refs/gpull-backups \
        | grep -Fqx "${local_commit}" || _fail "分歧 detached 提交未保留备份引用"
    grep -Fq 'BACKUP: preserved detached HEAD' "${TEST_DIR}/divergent.log" \
        || _fail "缺少 detached 提交备份提示"
}

_test_stale_index_lock_is_recovered() {
    local remote="${TEST_DIR}/lock-remote.git"
    local seed="${TEST_DIR}/lock-seed"
    local super="${TEST_DIR}/lock-super"
    local submodule="${super}/refer/lock-sub"
    local lock

    _create_submodule_fixture "${remote}" "${seed}" "${super}" refer/lock-sub
    git -C "${submodule}" checkout -q --detach HEAD
    lock=$(git -C "${submodule}" rev-parse --git-path index.lock)
    [[ "${lock}" == /* ]] || lock="${submodule}/${lock}"
    : > "${lock}"
    sleep 2

    GIT_INDEX_LOCK_STALE_SECONDS=1 \
        _run_gpull_sub "${super}" "${TEST_DIR}/stale-lock.log" --path refer/lock-sub \
        || _fail "过期 index.lock 应被自动隔离"

    [[ ! -e "${lock}" ]] || _fail "过期 index.lock 应被移走"
    compgen -G "${lock}.stale.*" >/dev/null || _fail "过期 index.lock 未保留备份"
    grep -Fq 'quarantined stale index lock' "${TEST_DIR}/stale-lock.log" \
        || _fail "缺少过期锁恢复证据"
}

_test_ignored_file_collision_is_not_overwritten() {
    local remote="${TEST_DIR}/ignored-collision-remote.git"
    local seed="${TEST_DIR}/ignored-collision-seed"
    local super="${TEST_DIR}/ignored-collision-super"
    local submodule="${super}/refer/ignored-sub"
    local old_head
    local status

    git init -q --bare "${remote}"
    git -C "${remote}" symbolic-ref HEAD refs/heads/main
    git init -q -b main "${seed}"
    _configure_identity "${seed}"
    printf 'artifact.txt\n' > "${seed}/.gitignore"
    printf 'base\n' > "${seed}/value.txt"
    git -C "${seed}" add .gitignore value.txt
    git -C "${seed}" commit -q -m initial
    git -C "${seed}" remote add origin "${remote}"
    git -C "${seed}" push -q -u origin main

    git init -q -b main "${super}"
    _configure_identity "${super}"
    printf 'super\n' > "${super}/README.md"
    git -C "${super}" add README.md
    git -C "${super}" commit -q -m super-initial
    git -C "${super}" -c protocol.file.allow=always \
        submodule add -q "${remote}" refer/ignored-sub
    git -C "${super}" commit -q -am add-submodule
    git -C "${super}" config protocol.file.allow always
    git -C "${submodule}" checkout -q --detach HEAD
    git -C "${submodule}" branch -D main >/dev/null
    old_head=$(git -C "${submodule}" rev-parse HEAD)
    printf 'local precious data\n' > "${submodule}/artifact.txt"
    if ! git -C "${submodule}" check-ignore -q artifact.txt; then
        _fail "子模块 ignored 文件碰撞夹具未生效"
    fi

    printf 'remote tracked artifact\n' > "${seed}/artifact.txt"
    git -C "${seed}" add -f artifact.txt
    git -C "${seed}" commit -q -m add-tracked-artifact
    git -C "${seed}" push -q

    set +e
    (cd "${super}" && bash "${_PATH}/gpull-sub.sh" --path refer/ignored-sub) \
        > "${TEST_DIR}/ignored-collision.log" 2>&1
    status=$?
    set -e

    ((status != 0)) || {
        cat "${TEST_DIR}/ignored-collision.log" >&2
        _fail "子模块 detached 恢复覆盖 ignored 文件时应失败"
    }
    grep -Fqx 'local precious data' "${submodule}/artifact.txt" \
        || _fail "子模块 detached 恢复覆盖了 ignored 文件"
    [[ "$(git -C "${submodule}" rev-parse HEAD)" == "${old_head}" ]] \
        || _fail "拒绝 ignored 文件覆盖时不应移动子模块 HEAD"
}

_test_stale_origin_head_uses_new_remote_default() {
    local remote="${TEST_DIR}/stale-head-remote.git"
    local seed="${TEST_DIR}/stale-head-seed"
    local super="${TEST_DIR}/stale-head-super"
    local submodule="${super}/refer/stale-head-sub"

    git init -q --bare "${remote}"
    git -C "${remote}" symbolic-ref HEAD refs/heads/main
    git init -q -b main "${seed}"
    _configure_identity "${seed}"
    printf 'main\n' > "${seed}/value.txt"
    git -C "${seed}" add value.txt
    git -C "${seed}" commit -q -m main-initial
    git -C "${seed}" remote add origin "${remote}"
    git -C "${seed}" push -q -u origin main
    git -C "${seed}" checkout -q -b trunk
    printf 'trunk\n' > "${seed}/value.txt"
    git -C "${seed}" commit -q -am trunk-update
    git -C "${seed}" push -q -u origin trunk

    git init -q -b main "${super}"
    _configure_identity "${super}"
    printf 'super\n' > "${super}/README.md"
    git -C "${super}" add README.md
    git -C "${super}" commit -q -m super-initial
    git -C "${super}" -c protocol.file.allow=always \
        submodule add -q "${remote}" refer/stale-head-sub
    git -C "${super}" commit -q -am add-submodule
    git -C "${super}" config protocol.file.allow always
    git -C "${submodule}" checkout -q --detach HEAD

    git -C "${remote}" symbolic-ref HEAD refs/heads/trunk
    (cd "${super}" && bash "${_PATH}/gpull-sub.sh" --path refer/stale-head-sub) \
        > "${TEST_DIR}/stale-head.log" 2>&1

    [[ "$(git -C "${submodule}" symbolic-ref --quiet --short HEAD)" == trunk ]] \
        || _fail "远端默认分支变更后仍恢复到陈旧的 origin/HEAD"
    grep -Fqx 'trunk' "${submodule}/value.txt" \
        || _fail "未检出远端新的默认分支 trunk"
}

_test_dot_path_is_rejected() {
    local remote="${TEST_DIR}/unsafe-dot-remote.git"
    local seed="${TEST_DIR}/unsafe-dot-seed"
    local super="${TEST_DIR}/unsafe-dot-super"
    local status

    _create_submodule_fixture "${remote}" "${seed}" "${super}" refer/safe-sub
    git -C "${super}" config -f .gitmodules submodule.unsafe.path .
    git -C "${super}" config -f .gitmodules submodule.unsafe.url "${remote}"
    git -C "${super}" add .gitmodules
    git -C "${super}" commit -q -m add-unsafe-dot-submodule

    set +e
    (cd "${super}" && bash "${_PATH}/gpull-sub.sh" --dry-run --path .) \
        > "${TEST_DIR}/unsafe-dot.log" 2>&1
    status=$?
    set -e

    ((status != 0)) || {
        cat "${TEST_DIR}/unsafe-dot.log" >&2
        _fail "gpull-sub 应拒绝 path=. 的伪子模块"
    }
    grep -Fq 'unsafe submodule path' "${TEST_DIR}/unsafe-dot.log" \
        || _fail "gpull-sub 拒绝 path=. 时缺少明确错误"
    ! grep -Fq 'DRY-RUN: would pull .' "${TEST_DIR}/unsafe-dot.log" \
        || _fail "gpull-sub 不应把父仓库根目录当作子模块"
}

main() {
    _test_mapped_submodule_pull
    _test_failure_propagates
    _test_unmapped_gitlink_is_ignored
    _test_divergent_detached_submodule_uses_remote_default
    _test_stale_index_lock_is_recovered
    _test_ignored_file_collision_is_not_overwritten
    _test_stale_origin_head_uses_new_remote_default
    _test_dot_path_is_rejected
}

main "$@"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
