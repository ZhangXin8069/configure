_PATH=$(
    cd "$(dirname "$0")"
    pwd
)
_NAME=$(basename "$0")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
dir_path="${1:-.}"
depth="${2:-2}"
command="du -h -d ${depth} ${dir_path} | sort -h"
echo "command: ${command}"
eval "${command}"
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"