#!/usr/bin/env bash
_PATH=$(cd "$(dirname "$0")" && pwd)
_NAME=$(basename "$0")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
case "${_NAME}" in
    conservative.sh)
        sudo cpupower -c all frequency-set -d 1400000 -u 4500000 -g conservative
        sudo cpupower idle-set -e 0
        sudo cpupower idle-set -e 1
        sudo cpupower idle-set -d 2
        sudo cpupower idle-set -e 3
        ;;
    ondemand.sh)
        sudo cpupower -c all frequency-set -d 1400000 -u 3400000 -g ondemand
        sudo cpupower idle-set -e 0
        sudo cpupower idle-set -e 1
        sudo cpupower idle-set -d 2
        sudo cpupower idle-set -e 3
        ;;
    performance.sh)
        sudo cpupower -c all frequency-set -g performance
        sudo cpupower idle-set -e 0
        sudo cpupower idle-set -d 1
        sudo cpupower idle-set -d 2
        sudo cpupower idle-set -d 3
        ;;
    powersave.sh)
        sudo cpupower -c all frequency-set -g powersave
        sudo cpupower idle-set -d 0
        sudo cpupower idle-set -d 1
        sudo cpupower idle-set -d 2
        sudo cpupower idle-set -e 3
        ;;
    *)
        echo "Usage: ln -s cpupower.sh {conservative|ondemand|performance|powersave}.sh"
        exit 1
        ;;
esac
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
