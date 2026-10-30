#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

TEST_DIR="${_PATH}/.give-git-ignore-test.$$"
cleanup() {
    rm -rf -- "${TEST_DIR}"
}
trap cleanup EXIT
mkdir -p "${TEST_DIR}"

_fail() {
    echo "FAIL: $*" >&2
    exit 1
}

_make_repo() {
    local repo=$1

    git init -q "${repo}"
    git -C "${repo}" config user.name give-git-ignore-test
    git -C "${repo}" config user.email give-git-ignore-test@example.invalid
    mkdir -p "${repo}/docs"
    printf 'notes\n' > "${repo}/docs/notes.md"
}

_test_docs_ignore_dry_run_and_write() {
    local repo="${TEST_DIR}/repo"
    local dry_output="${TEST_DIR}/dry-run.log"

    _make_repo "${repo}"
    (
        cd "${repo}"
        bash "${_PATH}/give_git_ignore.sh" -n
    ) > "${dry_output}" 2>&1

    [[ ! -e "${repo}/docs/.gitignore" ]] \
        || _fail "dry-run 创建了 docs/.gitignore"
    grep -Fq -- '--- docs/.gitignore (dry-run) ---' "${dry_output}" || {
        cat "${dry_output}" >&2
        _fail "dry-run 未输出 docs/.gitignore 计划"
    }
    grep -Fxq -- '**/' "${dry_output}" || {
        cat "${dry_output}" >&2
        _fail "dry-run 未输出 docs/.gitignore 固定内容 **/"
    }

    (
        cd "${repo}"
        bash "${_PATH}/give_git_ignore.sh" -f
    ) > "${TEST_DIR}/write.log" 2>&1

    [[ -f "${repo}/docs/.gitignore" ]] \
        || _fail "未创建 docs/.gitignore"
    cmp -s <(printf '**/\n') "${repo}/docs/.gitignore" \
        || _fail "docs/.gitignore 内容不是精确的 **/"
}

_test_sub_only_preserves_root_ignore() {
    local repo="${TEST_DIR}/sub-only-repo"

    _make_repo "${repo}"
    mkdir -p "${repo}/data" "${repo}/logs"
    printf 'root sentinel\n' > "${repo}/.gitignore"

    if ! (
        cd "${repo}"
        bash "${_PATH}/give_git_ignore.sh" -sub -f
    ) > "${TEST_DIR}/sub-only.log" 2>&1; then
        cat "${TEST_DIR}/sub-only.log" >&2
        _fail "-sub 运行失败"
    fi

    cmp -s <(printf 'root sentinel\n') "${repo}/.gitignore" \
        || _fail "-sub 修改了根 .gitignore"
    cmp -s <(printf '**/\n') "${repo}/docs/.gitignore" \
        || _fail "-sub 未写入 docs/.gitignore"
    cmp -s <(printf '*\n!.gitignore\n!AGENTS.md\n!README.md\n') \
        "${repo}/data/.gitignore" \
        || _fail "-sub 未写入 data/.gitignore"
    cmp -s <(printf '*\n*\n!.gitignore\n!AGENTS.md\n!README.md\n!*.txt\n') \
        "${repo}/logs/.gitignore" \
        || _fail "-sub 未写入 logs/.gitignore"
    printf 'log\n' > "${repo}/logs/v20261031000000.txt"
    if git -C "${repo}" check-ignore --no-index -q -- logs/v20261031000000.txt; then
        _fail "-sub 生成的 logs/.gitignore 忽略了普通 .txt 日志"
    fi
}

_test_form_snapshot_symlinks_are_kept() {
    local repo="${TEST_DIR}/snapshot-keep-repo"
    local root relative

    _make_repo "${repo}"
    for root in \
        skills/form/references/source-snapshots/configure-main/bin \
        .opencode/skills/form/references/source-snapshots/configure-main/bin; do
        mkdir -p "${repo}/${root}"
        printf '#!/usr/bin/env bash\n' > "${repo}/${root}/agent.sh"
        ln -s agent.sh "${repo}/${root}/cl"
        ln -s agent.sh "${repo}/${root}/cls"
        ln -s agent.sh "${repo}/${root}/co"
        ln -s agent.sh "${repo}/${root}/cos"
        ln -s agent.sh "${repo}/${root}/op"
        ln -s agent.sh "${repo}/${root}/ops"
    done

    (
        cd "${repo}"
        bash "${_PATH}/give_git_ignore.sh" -f
    ) > "${TEST_DIR}/snapshot-keep.log" 2>&1

    for relative in \
        skills/form/references/source-snapshots/configure-main/bin/cl \
        skills/form/references/source-snapshots/configure-main/bin/cls \
        skills/form/references/source-snapshots/configure-main/bin/co \
        skills/form/references/source-snapshots/configure-main/bin/cos \
        skills/form/references/source-snapshots/configure-main/bin/op \
        skills/form/references/source-snapshots/configure-main/bin/ops \
        .opencode/skills/form/references/source-snapshots/configure-main/bin/cl \
        .opencode/skills/form/references/source-snapshots/configure-main/bin/cls \
        .opencode/skills/form/references/source-snapshots/configure-main/bin/co \
        .opencode/skills/form/references/source-snapshots/configure-main/bin/cos \
        .opencode/skills/form/references/source-snapshots/configure-main/bin/op \
        .opencode/skills/form/references/source-snapshots/configure-main/bin/ops; do
        if git -C "${repo}" check-ignore --no-index -q -- "$relative"; then
            _fail "form 快照软链接仍被忽略：${relative}"
        fi
    done
}

_test_help_documents_sub_only() {
    local output="${TEST_DIR}/help.log"

    bash "${_PATH}/give_git_ignore.sh" -h > "${output}"
    grep -Fq -- '-sub             只写 data/、logs/、docs/ 子目录的 .gitignore' "${output}" \
        || _fail "帮助文本未说明 -sub"
    ! grep -Fxq -- 'set -euo pipefail' "${output}" \
        || _fail "帮助文本泄露实现语句"
}

main() {
    _test_docs_ignore_dry_run_and_write
    _test_sub_only_preserves_root_ignore
    _test_form_snapshot_symlinks_are_kept
    _test_help_documents_sub_only
}

main
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
