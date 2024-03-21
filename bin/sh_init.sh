# source
_PATH=`cd "$(dirname "$0")";pwd`
pushd ${_PATH}/../
source ./env.sh
popd

# init
_NAME=`basename "$0"`
work_name="lib"
tmp_name="tmp"
work_path=${_HOME}/${work_name}
tmp_path=${_HOME}/${tmp_name}

# do
pushd ~
echo "###${_NAME} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
echo "ln -s ${work_path}/.bashrc ."
echo "ln -s ${work_path}/.zshrc ."
mv ./.bashrc .bashrc.bak
mv ./.zshrc .zshrc.bak
ln -s ${work_path}/.bashrc .
ln -s ${work_path}/.zshrc .
echo "###${_NAME} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
popd

# done
