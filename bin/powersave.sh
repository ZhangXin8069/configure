_PATH=$(
    cd "$(dirname "$0")"
    pwd
)
_NAME=$(basename "$0")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
sudo cpupower -c all frequency-set -g powersave
sudo cpupower idle-set -d 0
sudo cpupower idle-set -d 1
sudo cpupower idle-set -d 2
sudo cpupower idle-set -e 3
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
