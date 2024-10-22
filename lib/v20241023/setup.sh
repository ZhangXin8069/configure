######
# computer:
## docker run -itd --gpus all --name v20241023 -e NVIDIA_DRIVER_CAPABILITIES=compute,utility -e NVIDIA_VISIBLE_DEVICES=all -v /c/Users/zhang/v20241023:/home/vscode/v20241023 docker.io/nvidia/cuda:12.4.0-devel-ubuntu22.04
# laptop:
## docker run -itd --gpus all --name v20241023 -v /c/Users/zhang/v20241023:/home/vscode/v20241023 docker.io/nvidia/cuda:12.4.0-devel-ubuntu22.04
######
apt update
######
apt install vim
apt install htop btop nvtop
apt install python3-dev
apt install cmake
apt install openmpi-bin openmpi-common libopenmpi-dev
# apt --fix-broken install
# dpkg --configure -a 
######
pushd ~
apt install zsh wget
sh -c "$(wget https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh -O -)"
# git clone https://gitee.com/zhangxin8069/configure.git
pushd ./configure
bash ./scripts/script_alias.sh
cp ./lib/v20241023/env.sh ~/env.sh
popd
# mv ./.bashrc .bashrc.bak
# mv ./.zshrc .zshrc.bak
# mv ./.oh-my-zsh .oh-my-zsh.bak
# ln -s ./configure/_bashrc .bashrc
# ln -s ./configure/v20241023/_zshrc .zshrc
# ln -s ./configure/_oh-my-zsh .oh-my-zsh
# ######
# wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.0-1_all.deb
# dpkg -i cuda-keyring_1.0-1_all.deb
# apt update
# apt install libnccl2=2.20.5-1+cuda12.4 libnccl-dev=2.20.5-1+cuda12.4
# # apt install nsight-systems-target
# ######
# wget https://gitee.com/zhangxin8069/quda_packages/raw/main/quda-develop.tar.gz
# tar -xzf quda-develop.tar.gz
# mv quda-develop quda
# pushd ./quda
# mkdir build -p && pushd build
# cmake .. -DQUDA_DIRAC_DOMAIN_WALL=OFF -DQUDA_CLOVER_DYNAMIC=OFF -DQUDA_CLOVER_RECONSTRUCT=OFF -DQUDA_DIRAC_NDEG_TWISTED_CLOVER=OFF -DQUDA_DIRAC_NDEG_TWISTED_MASS=OFF -DQUDA_DIRAC_TWISTED_CLOVER=OFF -DQUDA_DIRAC_TWISTED_MASS=OFF -DQUDA_INTERFACE_MILC=OFF -DQUDA_LAPLACE=ON -DQUDA_MULTIGRID=ON -DQUDA_GPU_ARCH=sm_80 -DQUDA_MPI=ON
# cmake --build . -j6
# cmake --install .
# popd
# popd
popd
######

