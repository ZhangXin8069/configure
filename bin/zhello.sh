#!/usr/bin/env bash
_PATH=$(
    cd "$(dirname "${BASH_SOURCE[0]:-$0}")"
    pwd
)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
echo $(cat ${_PATH}/../docs/hello.txt)
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"