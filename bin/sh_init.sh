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
echo "###${_NAME} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
echo "ln -s ${work_path}/_bashrc .bashrc"
echo "ln -s ${work_path}/_zshrc .zshrc"
echo "ln -s ${work_path}/_oh-my-zsh .oh-my-zsh"
mv ./.bashrc .bashrc.bak
mv ./.zshrc .zshrc.bak
# apt install zsh wget
# sh -c "$(wget https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh -O -)"
mkdir -p .oh-my-zsh
mv .oh-my-zsh .oh-my-zsh.bak
ln -s ${work_path}/_bashrc .bashrc
ln -s ${work_path}/_zshrc .zshrc
ln -s ${work_path}/_oh-my-zsh .oh-my-zsh
echo "###${_NAME} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
popd

# done
