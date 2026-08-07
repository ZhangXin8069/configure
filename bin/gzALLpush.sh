#!/usr/bin/env bash
_PATH=$(
    cd "$(dirname "${BASH_SOURCE[0]:-$0}")"
    pwd
)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
bash ${_PATH}/gzCONFIGUREpush.sh
bash ${_PATH}/gzLATTICE-PDFpush.sh
bash ${_PATH}/gzPYQCUpush.sh
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
