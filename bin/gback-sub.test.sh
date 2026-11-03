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
    grep -Fq 'Remote target: gitlab.itp.ac.cn' "${TEST_DIR}/restore.log" \
        || _fail "gback-sub 省略 -t 时未应用默认远程目标"
    grep -Fq 'RESTORED: refer/forced-sub' "${TEST_DIR}/restore.log" || _fail "缺少恢复成功提示"
    git -C "${super}" diff --quiet --cached -- refer/forced-sub \
        || _fail "gback-sub 不应自动暂存父库 gitlink"
}

_test_dot_path_is_rejected() {
    local remote="${TEST_DIR}/unsafe-dot-remote.git"
    local seed="${TEST_DIR}/unsafe-dot-seed"
    local super="${TEST_DIR}/unsafe-dot-super"
    local status

    _create_remote "${remote}" "${seed}"
    git init -q -b main "${super}"
    _configure_identity "${super}"
    printf 'super\n' > "${super}/README.md"
    git -C "${super}" add README.md
    git -C "${super}" commit -q -m super-initial
    git -C "${super}" -c protocol.file.allow=always \
        submodule add -q "${remote}" refer/safe-sub
    git -C "${super}" config -f .gitmodules submodule.unsafe.path .
    git -C "${super}" config -f .gitmodules submodule.unsafe.url "${remote}"
    git -C "${super}" commit -q -am add-submodules
    git -C "${super}" config protocol.file.allow always

    set +e
    (cd "${super}" && bash "${_PATH}/gback-sub.sh" --dry-run --path .) \
        > "${TEST_DIR}/unsafe-dot.log" 2>&1
    status=$?
    set -e

    ((status != 0)) || {
        cat "${TEST_DIR}/unsafe-dot.log" >&2
        _fail "gback-sub 应拒绝 path=. 的伪子模块"
    }
    grep -Fq 'unsafe submodule path' "${TEST_DIR}/unsafe-dot.log" \
        || _fail "gback-sub 拒绝 path=. 时缺少明确错误"
    ! grep -Fq 'DRY-RUN: would force-align .' "${TEST_DIR}/unsafe-dot.log" \
        || _fail "gback-sub 不应把父仓库根目录当作子模块"
}

_test_overwritten_local_branch_is_backed_up() {
    local remote="${TEST_DIR}/branch-backup-remote.git"
    local seed="${TEST_DIR}/branch-backup-seed"
    local super="${TEST_DIR}/branch-backup-super"
    local submodule="${super}/refer/branch-backup-sub"
    local base_head
    local local_branch_head

    _create_remote "${remote}" "${seed}"
    git init -q -b main "${super}"
    _configure_identity "${super}"
    printf 'super\n' > "${super}/README.md"
    git -C "${super}" add README.md
    git -C "${super}" commit -q -m super-initial
    git -C "${super}" -c protocol.file.allow=always \
        submodule add -q "${remote}" refer/branch-backup-sub
    git -C "${super}" commit -q -am add-submodule
    git -C "${super}" config protocol.file.allow always

    base_head=$(git -C "${submodule}" rev-parse HEAD)
    printf 'local branch commit\n' > "${submodule}/local-branch.txt"
    git -C "${submodule}" add local-branch.txt
    git -C "${submodule}" commit -q -m local-branch-commit
    local_branch_head=$(git -C "${submodule}" rev-parse HEAD)
    git -C "${submodule}" checkout -q --detach "${base_head}"

    printf 'remote latest\n' > "${seed}/value.txt"
    git -C "${seed}" commit -q -am remote-latest
    git -C "${seed}" push -q

    (cd "${super}" && bash "${_PATH}/gback-sub.sh" --path refer/branch-backup-sub) \
        > "${TEST_DIR}/branch-backup.log" 2>&1

    git -C "${submodule}" for-each-ref --format='%(objectname)' refs/gback-sub-backups \
        | grep -Fqx "${local_branch_head}" \
        || _fail "被 checkout -B 覆盖的本地分支尖端未进入备份 ref"
    grep -Fq 'BACKUP: refer/branch-backup-sub branch trunk' "${TEST_DIR}/branch-backup.log" \
        || _fail "缺少本地分支尖端备份提示"
}

_test_outer_reset_does_not_move_nested_before_backup() {
    local nested_remote="${TEST_DIR}/nested-remote.git"
    local nested_seed="${TEST_DIR}/nested-seed"
    local outer_remote="${TEST_DIR}/outer-remote.git"
    local outer_seed="${TEST_DIR}/outer-seed"
    local super="${TEST_DIR}/nested-super"
    local outer="${super}/refer/outer-sub"
    local nested="${outer}/nested"
    local nested_before

    git init -q --bare "${nested_remote}"
    git -C "${nested_remote}" symbolic-ref HEAD refs/heads/main
    git init -q -b main "${nested_seed}"
    _configure_identity "${nested_seed}"
    printf 'nested base\n' > "${nested_seed}/value.txt"
    git -C "${nested_seed}" add value.txt
    git -C "${nested_seed}" commit -q -m nested-base
    git -C "${nested_seed}" remote add origin "${nested_remote}"
    git -C "${nested_seed}" push -q -u origin main

    git init -q --bare "${outer_remote}"
    git -C "${outer_remote}" symbolic-ref HEAD refs/heads/main
    git init -q -b main "${outer_seed}"
    _configure_identity "${outer_seed}"
    git -C "${outer_seed}" -c protocol.file.allow=always \
        submodule add -q "${nested_remote}" nested
    git -C "${outer_seed}" commit -q -m outer-base
    git -C "${outer_seed}" remote add origin "${outer_remote}"
    git -C "${outer_seed}" push -q -u origin main

    git init -q -b main "${super}"
    _configure_identity "${super}"
    printf 'super\n' > "${super}/README.md"
    git -C "${super}" add README.md
    git -C "${super}" commit -q -m super-initial
    git -C "${super}" -c protocol.file.allow=always \
        submodule add -q "${outer_remote}" refer/outer-sub
    git -C "${super}" commit -q -am add-outer-submodule
    git -C "${super}" config protocol.file.allow always
    git -C "${super}" -c protocol.file.allow=always \
        submodule update -q --init --recursive
    git -C "${outer}" config protocol.file.allow always
    nested_before=$(git -C "${nested}" rev-parse HEAD)

    printf 'nested latest\n' > "${nested_seed}/value.txt"
    git -C "${nested_seed}" commit -q -am nested-latest
    git -C "${nested_seed}" push -q
    git -C "${outer_seed}/nested" fetch -q origin
    git -C "${outer_seed}/nested" checkout -q origin/main
    git -C "${outer_seed}" add nested
    git -C "${outer_seed}" commit -q -m outer-updates-nested
    git -C "${outer_seed}" push -q

    git -C "${outer}" config submodule.recurse true
    git -C "${outer}" config fetch.recurseSubmodules on-demand
    (cd "${super}" && bash "${_PATH}/gback-sub.sh" --path refer/outer-sub --recursive) \
        > "${TEST_DIR}/nested-recursion.log" 2>&1

    git -C "${nested}" for-each-ref --format='%(objectname)' refs/gback-sub-backups \
        | grep -Fqx "${nested_before}" \
        || _fail "外层 checkout/reset 在递归备份前移动了 nested HEAD"
    [[ "$(git -C "${nested}" rev-parse HEAD)" == "$(git -C "${nested_seed}" rev-parse HEAD)" ]] \
        || _fail "递归阶段未将 nested 对齐到远端最新提交"
}

_test_silent_stash_success_aborts_before_reset() {
    local remote="${TEST_DIR}/silent-stash-remote.git"
    local seed="${TEST_DIR}/silent-stash-seed"
    local super="${TEST_DIR}/silent-stash-super"
    local submodule="${super}/refer/silent-stash-sub"
    local fake_bin="${TEST_DIR}/silent-stash-bin"
    local real_git
    local status

    _create_remote "${remote}" "${seed}"
    git init -q -b main "${super}"
    _configure_identity "${super}"
    printf 'super\n' > "${super}/README.md"
    git -C "${super}" add README.md
    git -C "${super}" commit -q -m super-initial
    git -C "${super}" -c protocol.file.allow=always \
        submodule add -q "${remote}" refer/silent-stash-sub
    git -C "${super}" commit -q -am add-submodule
    git -C "${super}" config protocol.file.allow always
    printf 'dirty tracked\n' > "${submodule}/value.txt"
    printf 'dirty untracked\n' > "${submodule}/scratch.txt"

    real_git=$(command -v git)
    mkdir -p "${fake_bin}"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'if [[ ${1:-} == -C && ${3:-} == stash && ${4:-} == push ]]; then' \
        '    exit 0' \
        'fi' \
        "exec $(printf '%q' "${real_git}") \"\$@\"" > "${fake_bin}/git"
    chmod +x "${fake_bin}/git"

    set +e
    (
        cd "${super}"
        PATH="${fake_bin}:${PATH}" bash "${_PATH}/gback-sub.sh" --path refer/silent-stash-sub
    ) > "${TEST_DIR}/silent-stash.log" 2>&1
    status=$?
    set -e

    ((status != 0)) || {
        cat "${TEST_DIR}/silent-stash.log" >&2
        _fail "stash ref 未变化时 gback-sub 仍返回 0"
    }
    [[ -z "$(git -C "${submodule}" stash list)" ]] \
        || _fail "静默成功夹具意外创建了 stash"
    grep -Fqx 'dirty tracked' "${submodule}/value.txt" \
        || _fail "stash 未确认时不应 reset 覆盖 tracked 文件"
    grep -Fqx 'dirty untracked' "${submodule}/scratch.txt" \
        || _fail "stash 未确认时不应 clean 删除 untracked 文件"
}

main() {
    _test_force_remote_default_with_backups
    _test_dot_path_is_rejected
    _test_overwritten_local_branch_is_backed_up
    _test_outer_reset_does_not_move_nested_before_backup
    _test_silent_stash_success_aborts_before_reset
}

main "$@"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
