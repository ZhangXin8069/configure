######
sudo apt update
######
sudo apt install htop btop nvtop
sudo apt install wine32 wine
sudo apt install firefox
sudo apt install vim
sudo apt install git
sudo apt install tree
sudo apt install libreoffice
# sudo apt install steam-installer
######
firefox 'https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64'
# sudo dpkg -i code_******_amd64.deb
######
git clone https://gitee.com/zhangxin8069/configure.git
git clone https://gitee.com/zhangxin8069/qcu.git
pushd ~/configure
source env.sh
bash ./scripts/script_alias.sh
bash ./bin/sh_init.sh
popd
sudo apt install zsh
# sudo chsh -s $(which zsh)
cp ~/configure/lib/computer/env.sh ~/env.sh
cp -r ~/configure/lib/_oh-my-zsh/ ~/.oh-my-zsh
sh -c "$(wget https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh -O -)" &
######
sudo add-apt-repository ppa:flatpak/stable
sudo apt install flatpak
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install flathub
flatpak install flatseal
######
flatpak install flathub com.qq.QQ
flatpak install flathub com.qq.QQmusic
flatpak install flathub com.tencent.WeChat
flatpak install flathub com.tencent.wemeet
flatpak install flathub net.cozic.joplin_desktop
flatpak install flathub org.kde.krita
flatpak install flathub io.github.xiaoyifang.goldendict_ng
flatpak install flathub org.fedoraproject.MediaWriter
#########
echo -e "APT::Periodic::Update-Package-Lists \"0\";\nAPT::Periodic::Download-Upgradeable-Packages \"0\";\nAPT::Periodic::AutocleanInterval \"0\";\nAPT::Periodic::Unattended-Upgrade \"0\";" | sudo tee /etc/apt/apt.conf.d/10periodic
echo -e "APT::Periodic::Update-Package-Lists \"0\";\nAPT::Periodic::Unattended-Upgrade \"0\";" | sudo tee /etc/apt/apt.conf.d/20auto-upgrades
sudo apt-mark hold $(apt list --installed | cut -d/ -f1)
# sudo apt-mark showhold
# sudo apt-mark unhold package_name
# sudo apt-mark unhold $(apt list --installed | cut -d/ -f1)
sudo apt update
#########
# reboot
#########
