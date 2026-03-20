_PATH=$(
    cd "$(dirname "$0")"
    pwd
)
_NAME=$(basename "$0")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
# jupyter-lab --no-browser --allow-root &
jupyter-lab --allow-root &
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
