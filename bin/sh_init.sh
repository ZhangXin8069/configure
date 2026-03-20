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
pushd ~
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
echo "cp -r ${work_path}/_bashrc .bashrc"
echo "cp -r ${work_path}/_zshrc .zshrc"
echo "cp -r ${work_path}/_oh-my-zsh .oh-my-zsh"
mv ./.bashrc .bashrc."$(date "+%Y-%m-%d-%H-%M-%S")".bak
mv ./.zshrc .zshrc."$(date "+%Y-%m-%d-%H-%M-%S")".bak
# apt install zsh wget
# sh -c "$(wget https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh -O -)"
mkdir -p .oh-my-zsh
mv .oh-my-zsh .oh-my-zsh."$(date "+%Y-%m-%d-%H-%M-%S")".bak
cp -r ${work_path}/_bashrc .bashrc
cp -r ${work_path}/_zshrc .zshrc
cp -r ${work_path}/_oh-my-zsh .oh-my-zsh
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
popd
# done
