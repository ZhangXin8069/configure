######
# x99:
# docker run -itd --gpus all --ipc=host --name x99-v20241023 -e NVIDIA_DRIVER_CAPABILITIES=compute,utility -e NVIDIA_VISIBLE_DEVICES=all -v /c/Users/kfutfd/x99-v20241023:/root/x99-v20241023 docker.io/nvidia/cuda:11.8.0-devel-ubuntu20.04
# zhangxin8069/x99-v20241023-image:ubuntu-20.04_gcc-9.4.0_-python-3.8.10_cuda-11.8.0_quda-1.1.0-sm60_pyquda-0.3.2_qcu-dev10
######
apt update
######
apt install git
apt install vim tree
apt install htop # btop nvtop
apt install python3-dev pip
# apt install cmake
wget  https://github.com/Kitware/CMake/releases/download/v3.31.0/cmake-3.31.0-linux-x86_64.sh
wget https://github.com/Syllo/nvtop/releases/download/3.1.0/nvtop-x86_64.AppImage
wget https://github.com/aristocratos/btop/releases/download/v1.4.0/btop-x86_64-linux-musl.tbz
mv cmake-3.31.0-linux-x86_64.sh nvtop-x86_64.AppImage btop-x86_64-linux-musl.tbz /usr/local
pushd /usr/local
sh cmake-3.31.0-linux-x86_64.sh
mv cmake-3.31.0-linux-x86_64 cmake
chmod +x nvtop-x86_64.AppImage
./nvtop-x86_64.AppImage --appimage-extract
mkdir nvtop
mv squashfs-root nvtop
tar -xf btop-x86_64-linux-musl.tbz
pushd ./bin
ln -s /usr/local/cmake/bin/* .
ln -s /usr/local/btop/bin/* .
ln -s /usr/local/nvtop/squashfs-root/usr/bin/* .
popd
popd
pushd /usr/bin 
ln -s ./python3 python
popd
apt install openmpi-bin openmpi-common libopenmpi-dev
apt install libnccl2 libnccl-dev
# apt --fix-broken install
# dpkg --configure -a 
######
pushd ~
apt install zsh wget
sh -c "$(wget https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh -O -)"
git clone https://github.com/jeffreytse/zsh-vi-mode $ZSH_CUSTOM/plugins/zsh-vi-mode
git clone https://github.com/MichaelAquilina/zsh-you-should-use.git $ZSH_CUSTOM/plugins/you-should-use
git clone https://github.com/zsh-users/zsh-syntax-highlighting.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting
git clone https://github.com/zsh-users/zsh-autosuggestions ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-autosuggestions
######
git config --global user.name "zhangxin"
git config --global user.email "zhangxin8069@qq.com"
ssh-keygen -t ed25519 -C "zhangxin8069@qq.com"
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
echo -e "id_rsa.pub:\n"
cat ~/.ssh/id_ed25519.pub
echo -e "\nput this to github's ssh.then run\"ssh -T git@github.com\""
git clone git@gitee.com:zhangxin8069/configure.git
git clone git@gitee.com:zhangxin8069/qcu.git
######
pushd ./configure
bash ./scripts/script_alias.sh
cp ./lib/x99-v20241023/env.sh ~/env.sh
popd
######
wget https://gitee.com/zhangxin8069/quda_packages/raw/main/quda-develop.tar.gz
tar -xzf quda-develop.tar.gz
mv quda-develop quda
pushd ./quda
mkdir build -p && pushd build
cmake .. -DQUDA_DIRAC_DOMAIN_WALL=OFF -DQUDA_CLOVER_DYNAMIC=OFF -DQUDA_CLOVER_RECONSTRUCT=OFF -DQUDA_DIRAC_NDEG_TWISTED_CLOVER=OFF -DQUDA_DIRAC_NDEG_TWISTED_MASS=OFF -DQUDA_DIRAC_TWISTED_CLOVER=OFF -DQUDA_DIRAC_TWISTED_MASS=OFF -DQUDA_INTERFACE_MILC=OFF -DQUDA_LAPLACE=ON -DQUDA_MULTIGRID=ON -DQUDA_GPU_ARCH=sm_60 -DQUDA_MPI=ON
cmake --build . -j6
cmake --install .
popd
popd
popd
######
# apt install apt-file
# apt-file update
# apt-file search mpi.h
######