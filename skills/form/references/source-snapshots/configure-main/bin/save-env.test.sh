#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

set -euo pipefail

TEST_DIR="${_PATH}/.save-env-test.$$"
cleanup() {
  rm -rf -- "${TEST_DIR}"
}
trap cleanup EXIT
mkdir "${TEST_DIR}"

ALIAS_FILE="${TEST_DIR}/aliases.txt"
OUT_FILE="${TEST_DIR}/env.sh"
LOG_FILE="${TEST_DIR}/stdout"
printf '%s\n' \
  "alias nv-smi='nvidia-smi'" \
  "alias foo_bar='true'" \
  "alias plain='true'" > "${ALIAS_FILE}"

SAVE_ENV_ALIASES_FILE="${ALIAS_FILE}" bash "${_PATH}/save-env.sh" "${OUT_FILE}" > "${LOG_FILE}"

grep -Fqx -- "alias nv-smi='nvidia-smi'" "${OUT_FILE}"
grep -Fqx -- "alias foo_bar='true'" "${OUT_FILE}"
grep -Fqx -- "alias plain='true'" "${OUT_FILE}"
grep -Fq -- "3 个别名" "${LOG_FILE}"

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
