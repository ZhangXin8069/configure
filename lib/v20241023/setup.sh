######
# DOCKER - Linux 4665a126ebff 5.15.153.1-microsoft-standard-WSL2 #1 SMP Fri Mar 29 23:14:13 UTC 2024 x86_64 x86_64 x86_64 GNU/Linux
# UBUNTU22.04 - JAMMY
######
sudo apt update
######
sudo apt install htop btop nvtop
sudo apt install python3 pip 
sudo apt install cmake 
sudo apt install openmpi-bin openmpi-common libopenmpi-dev
sudo apt install nvidia-cuda-toolkit libnccl2 libnccl-dev
######
pushd ~
git clone https://gitee.com/zhangxin8069/configure.git
pushd ./configure
bash ./scripts/script_alias.sh
bash ./bin/sh_init.sh
cp ./lib/v20241023/env.sh ~/env.sh
popd
popd
######
