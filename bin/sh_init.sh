_PATH=$(
    cd "$(dirname "$0")"
    pwd
)
_NAME=$(basename "$0")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
pushd ~
mkdir -p .oh-my-zsh
mv ./.bashrc .bashrc."$(date "+%Y-%m-%d-%H-%M-%S")".bak
mv ./.zshrc .zshrc."$(date "+%Y-%m-%d-%H-%M-%S")".bak
mv .oh-my-zsh .oh-my-zsh."$(date "+%Y-%m-%d-%H-%M-%S")".bak
# apt install zsh wget
# sh -c "$(wget https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh -O -)"
cp -r ${_PATH}/../lib/_bashrc .bashrc
cp -r ${_PATH}/../lib/_zshrc .zshrc
cp -r ${_PATH}/../lib/_oh-my-zsh .oh-my-zsh
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
