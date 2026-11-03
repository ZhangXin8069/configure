#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

TEST_DIR="${_PATH}/.gpull-test.$$"
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
    git -C "${repo}" config user.name gpull-test
    git -C "${repo}" config user.email gpull-test@example.invalid
}

_test_pull_preserves_changes() {
    local remote="${TEST_DIR}/remote.git"
    local seed="${TEST_DIR}/seed"
    local work="${TEST_DIR}/work"
    local other="${TEST_DIR}/other"
    local real_git
    local fake_bin="${TEST_DIR}/fake-bin"
    local fake_git="${fake_bin}/git"
    local locale_bin="${TEST_DIR}/locale-bin"
    local locale_git="${locale_bin}/git"
    local locale_log="${TEST_DIR}/locale.log"

    real_git=$(command -v git)
    mkdir -p "${locale_bin}"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'case " $* " in' \
        '    *" fetch "*) printf "fetch-locale=%s/%s\\n" "${LANG:-}" "${LC_ALL:-}" >> "${FAKE_GIT_LOCALE_LOG}" ;;' \
        '    *" remote set-head "*) printf "set-head-locale=%s/%s\\n" "${LANG:-}" "${LC_ALL:-}" >> "${FAKE_GIT_LOCALE_LOG}" ;;' \
        'esac' \
        "exec $(printf '%q' "${real_git}") \"\$@\"" >"${locale_git}"
    chmod +x "${locale_git}"

    git init -q --bare "${remote}"
    git -C "${remote}" symbolic-ref HEAD refs/heads/main

    git init -q "${seed}"
    _configure_identity "${seed}"
    git -C "${seed}" checkout -q -b main
    printf 'base\n' > "${seed}/local.txt"
    printf 'base\n' > "${seed}/remote.txt"
    git -C "${seed}" add local.txt remote.txt
    git -C "${seed}" commit -q -m initial
    git -C "${seed}" remote add origin "${remote}"
    git -C "${seed}" push -q -u origin main

    git clone -q "${remote}" "${work}"
    _configure_identity "${work}"
    git clone -q "${remote}" "${other}"
    _configure_identity "${other}"

    printf 'remote update\n' > "${other}/remote.txt"
    git -C "${other}" add remote.txt
    git -C "${other}" commit -q -m remote-update
    git -C "${other}" push -q

    printf 'local update\n' > "${work}/local.txt"
    (
        cd "${work}"
        PATH="${locale_bin}:${PATH}" FAKE_GIT_LOCALE_LOG="${locale_log}" \
            bash "${_PATH}/gpull.sh"
    ) > "${TEST_DIR}/pull.log" 2>&1

    grep -Fqx 'remote update' "${work}/remote.txt" || _fail "未拉取远端更新"
    grep -Fqx 'local update' "${work}/local.txt" || _fail "未恢复本地 tracked 改动"
    [[ -z "$(git -C "${work}" stash list)" ]] || _fail "拉取后仍有未恢复的自动 stash"
    grep -Fqx 'fetch-locale=C/C' "${locale_log}" \
        || _fail "gpull fetch 未同时使用 POSIX LANG/LC_ALL"

    mkdir -p "${fake_bin}"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'if [[ ${1:-} == merge && ${2:-} == -h ]]; then' \
        '    echo "usage: git merge [<options>] (autostash unavailable)"' \
        '    exit 0' \
        'fi' \
        'if [[ ${1:-} == stash && ${2:-} == push ]]; then' \
        '    exit 129' \
        'fi' \
        "exec $(printf '%q' "${real_git}") \"\$@\"" > "${fake_git}"
    chmod +x "${fake_git}"

    printf 'remote update 2\n' > "${other}/remote.txt"
    git -C "${other}" add remote.txt
    git -C "${other}" commit -q -m remote-update-2
    git -C "${other}" push -q
    printf 'local update 2\n' > "${work}/local.txt"

    (
        cd "${work}"
        PATH="${fake_bin}:${PATH}" bash "${_PATH}/gpull.sh"
    ) > "${TEST_DIR}/fallback.log" 2>&1

    grep -Fq 'manual stash fallback' "${TEST_DIR}/fallback.log" || _fail "未进入旧版 Git 回退流程"
    grep -Fqx 'remote update 2' "${work}/remote.txt" || _fail "旧版 Git 回退未拉取远端更新"
    grep -Fqx 'local update 2' "${work}/local.txt" || _fail "旧版 Git 回退未恢复本地改动"
    [[ -z "$(git -C "${work}" stash list)" ]] || _fail "旧版 Git 回退后仍有未恢复的 stash"

}

_test_detached_head_recovery() {
    local remote="${TEST_DIR}/detached-remote.git"
    local seed="${TEST_DIR}/detached-seed"
    local work="${TEST_DIR}/detached-work"
    local other="${TEST_DIR}/detached-other"

    git init -q --bare "${remote}"
    git -C "${remote}" symbolic-ref HEAD refs/heads/main

    git init -q "${seed}"
    _configure_identity "${seed}"
    git -C "${seed}" checkout -q -b main
    printf 'base\n' > "${seed}/file.txt"
    git -C "${seed}" add file.txt
    git -C "${seed}" commit -q -m initial
    git -C "${seed}" remote add origin "${remote}"
    git -C "${seed}" push -q -u origin main

    git clone -q "${remote}" "${work}"
    _configure_identity "${work}"
    git clone -q "${remote}" "${other}"
    _configure_identity "${other}"

    git -C "${work}" checkout -q --detach HEAD
    printf 'remote update\n' > "${other}/file.txt"
    git -C "${other}" add file.txt
    git -C "${other}" commit -q -m remote-update
    git -C "${other}" push -q

    set +e
    (
        cd "${work}"
        bash "${_PATH}/gpull.sh"
    ) > "${TEST_DIR}/detached-recovery.log" 2>&1
    local recovery_status=$?
    set -e

    if ((recovery_status != 0)); then
        cat "${TEST_DIR}/detached-recovery.log" >&2
        _fail "安全 detached HEAD 恢复失败"
    fi

    [[ "$(git -C "${work}" symbolic-ref --quiet --short HEAD)" == main ]] \
        || _fail "安全 detached HEAD 未恢复到 main"
    grep -Fqx 'remote update' "${work}/file.txt" || _fail "安全 detached HEAD 恢复后未拉取远端更新"
    grep -Fq 'Restoring tracking branch main' "${TEST_DIR}/detached-recovery.log" \
        || _fail "缺少 detached HEAD 安全恢复提示"

    git -C "${work}" checkout -q --detach HEAD
    printf 'detached local commit\n' > "${work}/detached.txt"
    git -C "${work}" add detached.txt
    git -C "${work}" commit -q -m detached-local
    local detached_commit
    detached_commit=$(git -C "${work}" rev-parse HEAD)

    set +e
    (
        cd "${work}"
        bash "${_PATH}/gpull.sh"
    ) > "${TEST_DIR}/detached-local.log" 2>&1
    local detached_status=$?
    set -e

    ((detached_status != 0)) || _fail "含独立提交的 detached HEAD 应返回非零"
    [[ -z "$(git -C "${work}" symbolic-ref --quiet --short HEAD || true)" ]] \
        || _fail "含独立提交的 detached HEAD 不应自动切换分支"
    [[ "$(git -C "${work}" rev-parse HEAD)" == "${detached_commit}" ]] \
        || _fail "拒绝恢复时不应改变 detached HEAD"
    grep -Fq 'not contained in origin/main' "${TEST_DIR}/detached-local.log" \
        || _fail "缺少独立 detached 提交的失败原因"
}

_test_diverged_branch_refuses_rebase() {
    local remote="${TEST_DIR}/diverged-remote.git"
    local seed="${TEST_DIR}/diverged-seed"
    local work="${TEST_DIR}/diverged-work"
    local other="${TEST_DIR}/diverged-other"
    local no_identity_home="${TEST_DIR}/no-identity-home"

    git init -q --bare "${remote}"
    git -C "${remote}" symbolic-ref HEAD refs/heads/main

    git init -q "${seed}"
    _configure_identity "${seed}"
    git -C "${seed}" checkout -q -b main
    printf 'base\n' > "${seed}/file.txt"
    git -C "${seed}" add file.txt
    git -C "${seed}" commit -q -m initial
    git -C "${seed}" remote add origin "${remote}"
    git -C "${seed}" push -q -u origin main

    git clone -q "${remote}" "${work}"
    _configure_identity "${work}"
    git clone -q "${remote}" "${other}"
    _configure_identity "${other}"

    printf 'local side\n' > "${work}/local.txt"
    git -C "${work}" add local.txt
    git -C "${work}" commit -q -m local-side
    printf 'remote side\n' > "${other}/remote.txt"
    git -C "${other}" add remote.txt
    git -C "${other}" commit -q -m remote-side
    git -C "${other}" push -q

    git -C "${work}" config --unset-all user.name || true
    git -C "${work}" config --unset-all user.email || true
    mkdir -p "${no_identity_home}"
    local previous_head
    previous_head=$(git -C "${work}" rev-parse HEAD)

    set +e
    (
        cd "${work}"
        HOME="${no_identity_home}" GIT_CONFIG_NOSYSTEM=1 bash "${_PATH}/gpull.sh"
    ) > "${TEST_DIR}/diverged.log" 2>&1
    local diverged_status=$?
    set -e

    ((diverged_status != 0)) || _fail "分叉分支应在自动 rebase 前返回非零"
    grep -Fq 'have diverged; refusing automatic rebase' "${TEST_DIR}/diverged.log" \
        || _fail "缺少分叉分支拒绝自动 rebase 的提示"
    [[ "$(git -C "${work}" rev-parse HEAD)" == "${previous_head}" ]] \
        || _fail "拒绝分叉 rebase 时不应改变 HEAD"
    [[ ! -d "$(git -C "${work}" rev-parse --git-path rebase-merge)" ]] \
        || _fail "拒绝分叉 rebase 后不应遗留 rebase-merge 状态"
    [[ ! -d "$(git -C "${work}" rev-parse --git-path rebase-apply)" ]] \
        || _fail "拒绝分叉 rebase 后不应遗留 rebase-apply 状态"
}

_test_wrapper_propagates_failure() {
    local wrapper_root="${TEST_DIR}/wrapper"
    local wrapper_bin="${wrapper_root}/bin"
    local wrapper_remote="${TEST_DIR}/wrapper-remote.git"

    mkdir -p "${wrapper_bin}"
    cp "${_PATH}/zg-configure-pull.sh" "${wrapper_bin}/"
    cp "${_PATH}/gpull.sh" "${wrapper_bin}/"
    cp "${_PATH}/_git_lock.sh" "${wrapper_bin}/"
    cp "${_PATH}/_git_remote_target.sh" "${wrapper_bin}/"
    git init -q --bare "${wrapper_remote}"
    git -C "${wrapper_remote}" symbolic-ref HEAD refs/heads/main
    git init -q "${wrapper_root}"
    _configure_identity "${wrapper_root}"
    git -C "${wrapper_root}" checkout -q -b main
    printf 'base\n' > "${wrapper_root}/file.txt"
    git -C "${wrapper_root}" add file.txt
    git -C "${wrapper_root}" commit -q -m initial
    git -C "${wrapper_root}" remote add origin "${wrapper_remote}"
    git -C "${wrapper_root}" push -q -u origin main
    git -C "${wrapper_root}" checkout -q --detach HEAD
    printf 'detached local commit\n' > "${wrapper_root}/detached.txt"
    git -C "${wrapper_root}" add detached.txt
    git -C "${wrapper_root}" commit -q -m detached-local

    set +e
    bash "${wrapper_bin}/zg-configure-pull.sh" > "${TEST_DIR}/wrapper.log" 2>&1
    local wrapper_status=$?
    set -e
    ((wrapper_status != 0)) || _fail "zg-configure-pull.sh 应传播 gpull 失败"
    grep -Fq 'Detached HEAD' "${TEST_DIR}/wrapper.log" || _fail "包装脚本未输出根因"
}

_test_fetch_failure_propagates() {
    local repo="${TEST_DIR}/fetch-failure"

    git init -q "${repo}"
    _configure_identity "${repo}"
    printf 'base\n' > "${repo}/file.txt"
    git -C "${repo}" add file.txt
    git -C "${repo}" commit -q -m initial
    git -C "${repo}" remote add origin "${TEST_DIR}/missing.git"

    set +e
    (
        cd "${repo}"
        bash "${_PATH}/gpull.sh"
    ) > "${TEST_DIR}/fetch-failure.log" 2>&1
    local fetch_status=$?
    set -e
    ((fetch_status != 0)) || _fail "fetch 失败应返回非零"
    grep -Fq 'git fetch failed' "${TEST_DIR}/fetch-failure.log" || _fail "缺少 fetch 失败提示"
}

_test_stale_index_lock_recovery() {
    local remote="${TEST_DIR}/lock-remote.git"
    local seed="${TEST_DIR}/lock-seed"
    local work="${TEST_DIR}/lock-work"
    local lock

    git init -q --bare "${remote}"
    git -C "${remote}" symbolic-ref HEAD refs/heads/main
    git init -q "${seed}"
    _configure_identity "${seed}"
    git -C "${seed}" checkout -q -b main
    printf 'base\n' > "${seed}/file.txt"
    git -C "${seed}" add file.txt
    git -C "${seed}" commit -q -m initial
    git -C "${seed}" remote add origin "${remote}"
    git -C "${seed}" push -q -u origin main

    git clone -q "${remote}" "${work}"
    lock=$(git -C "${work}" rev-parse --git-path index.lock)
    [[ "${lock}" == /* ]] || lock="${work}/${lock}"
    : > "${lock}"
    sleep 2

    (
        cd "${work}"
        GIT_INDEX_LOCK_STALE_SECONDS=1 bash "${_PATH}/gpull.sh"
    ) > "${TEST_DIR}/stale-lock.log" 2>&1

    [[ ! -e "${lock}" ]] || _fail "过期 index.lock 应被隔离"
    compgen -G "${lock}.stale.*" >/dev/null || _fail "过期 index.lock 未保留备份"
    grep -Fq 'quarantined stale index lock' "${TEST_DIR}/stale-lock.log" \
        || _fail "缺少过期锁恢复提示"
}

_test_fresh_index_lock_is_not_removed() {
    local remote="${TEST_DIR}/fresh-lock-remote.git"
    local seed="${TEST_DIR}/fresh-lock-seed"
    local work="${TEST_DIR}/fresh-lock-work"
    local lock
    local status

    git init -q --bare "${remote}"
    git -C "${remote}" symbolic-ref HEAD refs/heads/main
    git init -q "${seed}"
    _configure_identity "${seed}"
    git -C "${seed}" checkout -q -b main
    printf 'base\n' > "${seed}/file.txt"
    git -C "${seed}" add file.txt
    git -C "${seed}" commit -q -m initial
    git -C "${seed}" remote add origin "${remote}"
    git -C "${seed}" push -q -u origin main

    git clone -q "${remote}" "${work}"
    lock=$(git -C "${work}" rev-parse --git-path index.lock)
    [[ "${lock}" == /* ]] || lock="${work}/${lock}"
    : > "${lock}"

    set +e
    (
        cd "${work}"
        GIT_INDEX_LOCK_WAIT_SECONDS=0 GIT_INDEX_LOCK_STALE_SECONDS=3600 \
            bash "${_PATH}/gpull.sh"
    ) > "${TEST_DIR}/fresh-lock.log" 2>&1
    status=$?
    set -e

    ((status != 0)) || _fail "新 index.lock 应触发有界失败"
    [[ -e "${lock}" ]] || _fail "新 index.lock 不应被自动删除"
    grep -Fq 'Git index lock remains active' "${TEST_DIR}/fresh-lock.log" \
        || _fail "缺少新锁等待失败提示"
}

_test_submodule_recurse_config_is_ignored() {
    local root="${TEST_DIR}/submodule-recurse"
    local sub_remote="${root}/sub-remote.git"
    local super_remote="${root}/super-remote.git"
    local sub_seed="${root}/sub-seed"
    local super_seed="${root}/super-seed"
    local work="${root}/super-work"
    local sub_one
    local sub_two
    local parent_one
    local parent_two
    local sub_before
    local sub_after

    mkdir -p "${root}"
    git init -q --bare "${sub_remote}"
    git -C "${sub_remote}" symbolic-ref HEAD refs/heads/main
    git init -q -b main "${sub_seed}"
    _configure_identity "${sub_seed}"
    printf 'one\n' > "${sub_seed}/value.txt"
    git -C "${sub_seed}" add value.txt
    git -C "${sub_seed}" commit -q -m sub-one
    git -C "${sub_seed}" remote add origin "${sub_remote}"
    git -C "${sub_seed}" push -q -u origin main
    sub_one=$(git -C "${sub_seed}" rev-parse HEAD)

    git init -q --bare "${super_remote}"
    git -C "${super_remote}" symbolic-ref HEAD refs/heads/main
    git init -q -b main "${super_seed}"
    _configure_identity "${super_seed}"
    git -C "${super_seed}" -c protocol.file.allow=always \
        submodule add -q "${sub_remote}" child
    git -C "${super_seed}" commit -q -m parent-one
    git -C "${super_seed}" remote add origin "${super_remote}"
    git -C "${super_seed}" push -q -u origin main
    parent_one=$(git -C "${super_seed}" rev-parse HEAD)

    git clone -q "${super_remote}" "${work}"
    _configure_identity "${work}"
    git -C "${work}" -c protocol.file.allow=always \
        submodule update -q --init --checkout
    git -C "${work}" config submodule.recurse true
    git -C "${work}" config fetch.recurseSubmodules true

    printf 'two\n' > "${sub_seed}/value.txt"
    git -C "${sub_seed}" commit -q -am sub-two
    git -C "${sub_seed}" push -q
    sub_two=$(git -C "${sub_seed}" rev-parse HEAD)
    git -C "${super_seed}/child" fetch -q origin main
    git -C "${super_seed}/child" checkout -q "${sub_two}"
    git -C "${super_seed}" add child
    git -C "${super_seed}" commit -q -m parent-two
    git -C "${super_seed}" push -q
    parent_two=$(git -C "${super_seed}" rev-parse HEAD)

    sub_before=$(git -C "${work}/child" rev-parse HEAD)
    (
        cd "${work}"
        GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null bash "${_PATH}/gpull.sh"
    ) > "${TEST_DIR}/submodule-recurse.log" 2>&1
    sub_after=$(git -C "${work}/child" rev-parse HEAD)

    [[ "$(git -C "${work}" rev-parse HEAD)" == "${parent_two}" ]] \
        || _fail "未拉取父仓库更新"
    [[ "${sub_before}" == "${sub_one}" ]] || _fail "测试夹具初始子模块提交错误"
    [[ "${sub_after}" == "${sub_one}" ]] \
        || _fail "gpull 不应在 submodule.recurse=true 时切换子模块 HEAD"
    grep -Fqx 'one' "${work}/child/value.txt" \
        || _fail "gpull 不应更新子模块工作树"
    [[ "$(git -C "${work}" status --porcelain --ignore-submodules=none -- child)" == ' M child' ]] \
        || _fail "父仓库应保留待显式处理的子模块指针差异"
    [[ "$(git -C "${super_seed}" rev-parse HEAD^)" == "${parent_one}" ]] \
        || _fail "父仓库测试提交链错误"

    local parent_before_push
    parent_before_push=$(git -C "${work}" rev-parse HEAD)
    (
        cd "${work}"
        GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null bash "${_PATH}/gpush.sh"
    ) > "${TEST_DIR}/pull-then-push.log" 2>&1
    [[ "$(git -C "${work}" rev-parse HEAD)" == "${parent_before_push}" ]] \
        || _fail "pull 后 gpush 不应提交子模块工作树回退"
    grep -Fq 'Nothing to commit.' "${TEST_DIR}/pull-then-push.log" \
        || _fail "pull 后 gpush 未报告无改动"
    [[ "$(git --git-dir="${super_remote}" rev-parse refs/heads/main)" == "${parent_two}" ]] \
        || _fail "pull 后 gpush 不应改变父仓库远端"
    grep -Fq 'Submodule worktrees were left unchanged' "${TEST_DIR}/submodule-recurse.log" \
        || _fail "gpull 未提示子模块工作树有意保持不变"
}

_test_unavailable_submodule_target_does_not_block_parent_pull() {
    local root="${TEST_DIR}/missing-submodule-target"
    local sub_remote="${root}/sub-remote.git"
    local super_remote="${root}/super-remote.git"
    local sub_seed="${root}/sub-seed"
    local super_seed="${root}/super-seed"
    local work="${root}/super-work"
    local sub_before
    local missing_child
    local parent_before
    local parent_after

    mkdir -p "${root}"
    git init -q --bare "${sub_remote}"
    git -C "${sub_remote}" symbolic-ref HEAD refs/heads/main
    git init -q -b main "${sub_seed}"
    _configure_identity "${sub_seed}"
    printf 'one\n' > "${sub_seed}/value.txt"
    git -C "${sub_seed}" add value.txt
    git -C "${sub_seed}" commit -q -m sub-one
    git -C "${sub_seed}" remote add origin "${sub_remote}"
    git -C "${sub_seed}" push -q -u origin main

    git init -q --bare "${super_remote}"
    git -C "${super_remote}" symbolic-ref HEAD refs/heads/main
    git init -q -b main "${super_seed}"
    _configure_identity "${super_seed}"
    git -C "${super_seed}" -c protocol.file.allow=always \
        submodule add -q "${sub_remote}" child
    git -C "${super_seed}" commit -q -m parent-one
    git -C "${super_seed}" remote add origin "${super_remote}"
    git -C "${super_seed}" push -q -u origin main
    parent_before=$(git -C "${super_seed}" rev-parse HEAD)

    git clone -q "${super_remote}" "${work}"
    _configure_identity "${work}"
    git -C "${work}" config protocol.file.allow always
    git -C "${work}" -c protocol.file.allow=always submodule update -q --init --checkout
    git -C "${work}" config submodule.recurse true
    git -C "${work}" config fetch.recurseSubmodules on-demand
    sub_before=$(git -C "${work}/child" rev-parse HEAD)

    printf 'unpublished\n' > "${sub_seed}/value.txt"
    git -C "${sub_seed}" commit -q -am sub-unpublished
    missing_child=$(git -C "${sub_seed}" rev-parse HEAD)
    if git -C "${work}/child" cat-file -e "${missing_child}^{commit}" 2>/dev/null; then
        _fail "缺失子模块目标夹具意外包含目标对象"
    fi

    git -C "${super_seed}" update-index --cacheinfo "160000,${missing_child},child"
    git -C "${super_seed}" commit -q -m parent-missing-submodule-target
    git -C "${super_seed}" push -q
    parent_after=$(git -C "${super_seed}" rev-parse HEAD)

    (
        cd "${work}"
        bash "${_PATH}/gpull.sh"
    ) > "${TEST_DIR}/missing-submodule-target.log" 2>&1 || {
        cat "${TEST_DIR}/missing-submodule-target.log" >&2
        _fail "不可获取的子模块目标不应阻断父仓库 fast-forward"
    }

    [[ "${parent_before}" != "${parent_after}" ]] || _fail "父仓库测试夹具未产生新提交"
    [[ "$(git -C "${work}" rev-parse HEAD)" == "${parent_after}" ]] \
        || _fail "父仓库未 fast-forward 到缺失子模块目标所在提交"
    [[ "$(git -C "${work}/child" rev-parse HEAD)" == "${sub_before}" ]] \
        || _fail "gpull 不应尝试切换子模块工作树"
    [[ "$(git -C "${work}" status --porcelain --ignore-submodules=none -- child)" == ' M child' ]] \
        || _fail "父仓库应保留待显式处理的子模块指针差异"
}

_test_ignored_file_collision_is_not_overwritten() {
    local remote="${TEST_DIR}/ignored-collision-remote.git"
    local seed="${TEST_DIR}/ignored-collision-seed"
    local work="${TEST_DIR}/ignored-collision-work"
    local other="${TEST_DIR}/ignored-collision-other"
    local original_head
    local status

    git init -q --bare "${remote}"
    git -C "${remote}" symbolic-ref HEAD refs/heads/main
    git init -q -b main "${seed}"
    _configure_identity "${seed}"
    printf 'artifact.txt\n' > "${seed}/.gitignore"
    printf 'base\n' > "${seed}/tracked.txt"
    git -C "${seed}" add .gitignore tracked.txt
    git -C "${seed}" commit -q -m initial
    git -C "${seed}" remote add origin "${remote}"
    git -C "${seed}" push -q -u origin main

    git clone -q "${remote}" "${work}"
    _configure_identity "${work}"
    git clone -q "${remote}" "${other}"
    _configure_identity "${other}"
    original_head=$(git -C "${work}" rev-parse HEAD)

    printf 'local precious data\n' > "${work}/artifact.txt"
    if ! git -C "${work}" check-ignore -q artifact.txt; then
        _fail "ignored 文件碰撞夹具未生效"
    fi

    printf 'remote tracked artifact\n' > "${other}/artifact.txt"
    git -C "${other}" add -f artifact.txt
    git -C "${other}" commit -q -m add-tracked-artifact
    git -C "${other}" push -q

    set +e
    (
        cd "${work}"
        bash "${_PATH}/gpull.sh"
    ) > "${TEST_DIR}/ignored-collision.log" 2>&1
    status=$?
    set -e

    ((status != 0)) || {
        cat "${TEST_DIR}/ignored-collision.log" >&2
        _fail "远程 tracked 文件与本地 ignored 文件碰撞时 gpull 应拒绝覆盖"
    }
    grep -Fqx 'local precious data' "${work}/artifact.txt" \
        || _fail "gpull 覆盖了本地 ignored 文件内容"
    [[ "$(git -C "${work}" rev-parse HEAD)" == "${original_head}" ]] \
        || _fail "拒绝 ignored 文件覆盖时不应移动 HEAD"
}

_test_dirty_submodule_does_not_create_false_stash() {
    local root="${TEST_DIR}/dirty-submodule-stash"
    local sub_remote="${root}/sub-remote.git"
    local super_remote="${root}/super-remote.git"
    local sub_seed="${root}/sub-seed"
    local super_seed="${root}/super-seed"
    local work="${root}/super-work"
    local sub_one
    local sub_two
    local parent_two

    mkdir -p "${root}"
    git init -q --bare "${sub_remote}"
    git -C "${sub_remote}" symbolic-ref HEAD refs/heads/main
    git init -q -b main "${sub_seed}"
    _configure_identity "${sub_seed}"
    printf 'one\n' > "${sub_seed}/value.txt"
    git -C "${sub_seed}" add value.txt
    git -C "${sub_seed}" commit -q -m sub-one
    git -C "${sub_seed}" remote add origin "${sub_remote}"
    git -C "${sub_seed}" push -q -u origin main
    sub_one=$(git -C "${sub_seed}" rev-parse HEAD)

    git init -q --bare "${super_remote}"
    git -C "${super_remote}" symbolic-ref HEAD refs/heads/main
    git init -q -b main "${super_seed}"
    _configure_identity "${super_seed}"
    git -C "${super_seed}" -c protocol.file.allow=always \
        submodule add -q "${sub_remote}" child
    printf 'base\n' > "${super_seed}/local.txt"
    git -C "${super_seed}" add .gitmodules child local.txt
    git -C "${super_seed}" commit -q -m parent-one
    git -C "${super_seed}" remote add origin "${super_remote}"
    git -C "${super_seed}" push -q -u origin main

    git clone -q "${super_remote}" "${work}"
    _configure_identity "${work}"
    git -C "${work}" -c protocol.file.allow=always \
        submodule update -q --init --checkout
    printf 'dirty child\n' > "${work}/child/value.txt"

    printf 'two\n' > "${sub_seed}/value.txt"
    git -C "${sub_seed}" commit -q -am sub-two
    git -C "${sub_seed}" push -q
    sub_two=$(git -C "${sub_seed}" rev-parse HEAD)
    git -C "${super_seed}/child" fetch -q origin main
    git -C "${super_seed}/child" checkout -q "${sub_two}"
    git -C "${super_seed}" add child
    git -C "${super_seed}" commit -q -m parent-two
    git -C "${super_seed}" push -q
    parent_two=$(git -C "${super_seed}" rev-parse HEAD)

    set +e
    (
        cd "${work}"
        GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null bash "${_PATH}/gpull.sh"
    ) > "${TEST_DIR}/dirty-submodule-stash.log" 2>&1
    local pull_status=$?
    set -e

    ((pull_status == 0)) || _fail "仅子模块脏时 gpull 不应失败: ${pull_status}"

    [[ "$(git -C "${work}" rev-parse HEAD)" == "${parent_two}" ]] \
        || _fail "含脏子模块时未拉取父仓库更新"
    [[ "$(git -C "${work}/child" rev-parse HEAD)" == "${sub_one}" ]] \
        || _fail "gpull 不应切换脏子模块 HEAD"
    grep -Fqx 'dirty child' "${work}/child/value.txt" \
        || _fail "gpull 不应覆盖子模块未提交改动"
    [[ -z "$(git -C "${work}" stash list)" ]] || _fail "gpull 留下了 stash"
    ! grep -Fq 'No stash entries found' "${TEST_DIR}/dirty-submodule-stash.log" \
        || _fail "gpull 错误地尝试恢复不存在的 stash"
}

main() {
    _test_pull_preserves_changes
    _test_detached_head_recovery
    _test_diverged_branch_refuses_rebase
    _test_wrapper_propagates_failure
    _test_fetch_failure_propagates
    _test_stale_index_lock_recovery
    _test_fresh_index_lock_is_not_removed
    _test_submodule_recurse_config_is_ignored
    _test_unavailable_submodule_target_does_not_block_parent_pull
    _test_ignored_file_collision_is_not_overwritten
    _test_dirty_submodule_does_not_create_false_stash
}

main "$@"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
