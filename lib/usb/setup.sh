# source
_PATH=`cd "$(dirname "$0")";pwd`
pushd ${_PATH}
source ./env.sh
popd
#########
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
#########
sudo apt install docker-io
sudo docker pull zhangxin8069/v20241023-image
#########
# echo -e "APT::Periodic::Update-Package-Lists \"0\";\nAPT::Periodic::Download-Upgradeable-Packages \"0\";\nAPT::Periodic::AutocleanInterval \"0\";\nAPT::Periodic::Unattended-Upgrade \"0\";" | sudo tee /etc/apt/apt.conf.d/10periodic
# echo -e "APT::Periodic::Update-Package-Lists \"0\";\nAPT::Periodic::Unattended-Upgrade \"0\";" | sudo tee /etc/apt/apt.conf.d/20auto-upgrades
sudo apt-mark hold $(apt list --installed | cut -d/ -f1)
# sudo apt-mark showhold
# sudo apt-mark unhold package_name
# sudo apt-mark unhold $(apt list --installed | cut -d/ -f1)
sudo apt update
#########
# reboot
#########