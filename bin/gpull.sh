# source
_PATH=$(
    cd "$(dirname "$0")"
    pwd
)
# pushd ${_PATH}/../
# source ./env.sh
# popd
# init
_NAME=$(basename "$0")
# do
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
echo "git pull --all"
git pull --all
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
# done
