#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

TEST_DIR="${_PATH}/.gpush-test.$$"
cleanup() {
    rm -rf -- "${TEST_DIR}"
}
trap cleanup EXIT
mkdir -p "${TEST_DIR}/bin" "${TEST_DIR}/repo"

_fail() {
    echo "FAIL: $*" >&2
    exit 1
}

cat > "${TEST_DIR}/bin/git" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${FAKE_GIT_LOG}"
case "$*" in
    "rev-parse --show-toplevel") printf '%s\n' "${FAKE_REPO_ROOT}" ;;
    "add -A"|"diff --cached --quiet") ;;
    "rev-parse --abbrev-ref HEAD") printf 'main\n' ;;
    "push origin main") ;;
    "push origin --tags") exit 1 ;;
    *) exit 1 ;;
esac
SH
chmod +x "${TEST_DIR}/bin/git"

set +e
PATH="${TEST_DIR}/bin:${PATH}" \
FAKE_GIT_LOG="${TEST_DIR}/git.log" \
FAKE_REPO_ROOT="${TEST_DIR}/repo" \
    bash "${_PATH}/gpush.sh" > "${TEST_DIR}/output.log" 2>&1
status=$?
set -e

((status != 0)) || {
    cat "${TEST_DIR}/output.log" >&2
    _fail "标签 push 失败后 gpush 仍返回 0"
}
grep -Fq 'ERROR: tag push failed' "${TEST_DIR}/output.log" || {
    cat "${TEST_DIR}/output.log" >&2
    _fail "标签 push 失败后未输出明确错误"
}
! grep -Fq "###${_NAME%.test.sh} is done" "${TEST_DIR}/output.log" || {
    cat "${TEST_DIR}/output.log" >&2
    _fail "标签 push 失败后仍打印 done"
}

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
