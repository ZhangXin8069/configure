# source
_PATH=`cd "$(dirname "$0")";pwd`
pushd ${_PATH}
source ./env.sh
popd

# do
pushd ~
echo "###${_NAME} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
# apt install zsh wget
# sh -c "$(wget https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh -O -)"
mv ./.bashrc .bashrc.bak
mv ./.zshrc .zshrc.bak
ln -s ${_PATH}/_bashrc .bashrc
ln -s ${_PATH}/_zshrc .zshrc
echo "###${_NAME} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
popd