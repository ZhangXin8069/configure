#!/usr/bin/env bash
_PATH=$(
    cd "$(dirname "${BASH_SOURCE[0]:-$0}")"
    pwd
)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
pushd ${_PATH}/../../lattice-pdf
bash ${_PATH}/gpush.sh
popd
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
