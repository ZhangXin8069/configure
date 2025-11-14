## UBUNTU
# pkg update
# mv /data/data/vn.vhn.vsc/files/usr/var/lib/dpkg/status /data/data/vn.vhn.vsc/files/usr/var/lib/dpkg/status.old
# pkg install git file proot-distro wget
# proot-distro list
# proot-distro install ubuntu
# echo 'proot-distro login ubuntu' >.bashrc
# reboot
# apt update
# apt upgrade -y
# apt install zsh ssh vim htop tree make cmake gcc python3-full libhdf5-mpi-dev -y
# python3 -m venv /root/venv
export PATH='/root/venv/bin':$PATH
# export HDF5_MPI="ON" 
# pip install --no-binary=h5py h5py
# pip install torch cython scipy mpi4py matplotlib
# reboot
# git config --global user.name "zhangxin"
# git config --global user.email "zhangxin8069@qq.com"
# ssh-keygen -t ed25519 -C "zhangxin8069@qq.com"
# eval "$(ssh-agent -s)"
# ssh-add /root/.ssh/id_ed25519
# echo -e "id_rsa.pub:\n"
# cat /root/.ssh/id_ed25519.pub
# echo -e "\nput this to gitee's ssh.then run\"ssh -T git@gitee.com\""
# reboot
# git clone git@gitee.com:zhangxin8069/configure.git
# git clone git@gitee.com:zhangxin8069/PyQCU.git
pushd /root/configure
source env.sh
popd
# sh_init.sh
# reboot