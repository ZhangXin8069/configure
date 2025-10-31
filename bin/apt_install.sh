# source
_PATH=$(
    cd "$(dirname "$0")"
    pwd
)
pushd ${_PATH}/../
source ./env.sh
popd

# init
_NAME=$(basename "$0")
work_name="lib"
tmp_name="tmp"
work_path=${_HOME}/${work_name}
tmp_path=${_HOME}/${tmp_name}

# do
pushd ${work_path}
echo "###${_NAME} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
echo "apt install $(cat apt_require.txt)"
sudo apt install $(cat apt_require.txt)
echo "###${_NAME} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
popd

# done
