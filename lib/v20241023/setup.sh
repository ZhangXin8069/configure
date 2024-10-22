######
# computer:
## docker run -itd --gpus all --name v20241023 -e NVIDIA_DRIVER_CAPABILITIES=compute,utility -e NVIDIA_VISIBLE_DEVICES=all -v /c/Users/zhang/v20241023:/home/vscode/v20241023 mcr.microsoft.com/devcontainers/base:noble
# laptop:
## docker run -itd --name v20241023 -v /c/Users/zhangxin/v20241023:/home/vscode/v20241023 mcr.microsoft.com/devcontainers/base:noble
######
sudo apt update
######
sudo apt install htop btop nvtop
sudo apt install python3-dev
sudo apt install cmake 
sudo apt install openmpi-bin openmpi-common libopenmpi-dev
sudo apt install nvidia-cuda-toolkit
######
# pushd ~
# git clone https://gitee.com/zhangxin8069/configure.git
# pushd ./configure
# bash ./scripts/script_alias.sh
# bash ./bin/sh_init.sh
# cp ./lib/v20241023/env.sh ~/env.sh
# popd
######
git clone https://github.com/NVIDIA/nccl.git
pushd ./nccl
make -j src.build NVCC_GENCODE="-gencode=arch=compute_80,code=sm_80"
sudo apt install build-essential devscripts debhelper fakeroot
# Build NCCL deb package
make pkg.debian.build
ls build/pkg/deb/
popd
git clone https://github.com/NVIDIA/nccl-tests.git
pushd ./nccl-tests
make
./build/all_reduce_perf -b 8 -e 256M -f 2 -g 1
# ./build/all_reduce_perf -b 8 -e 256M -f 2 -g <ngpus>
popd
wget https://gitee.com/zhangxin8069/quda_packages/raw/main/quda-develop.tar.gz
tar -xzf quda-develop.tar.gz
mv quda-develop quda
pushd ./quda
mkdir build -p && pushd build
cmake .. -DQUDA_DIRAC_DOMAIN_WALL=OFF -DQUDA_CLOVER_DYNAMIC=OFF -DQUDA_CLOVER_RECONSTRUCT=OFF -DQUDA_DIRAC_NDEG_TWISTED_CLOVER=OFF -DQUDA_DIRAC_NDEG_TWISTED_MASS=OFF -DQUDA_DIRAC_TWISTED_CLOVER=OFF -DQUDA_DIRAC_TWISTED_MASS=OFF -DQUDA_INTERFACE_MILC=OFF -DQUDA_LAPLACE=ON -DQUDA_MULTIGRID=ON -DQUDA_GPU_ARCH=sm_80 -DQUDA_MPI=ON
cmake --build . -j6
cmake --install .
popd
popd
popd
######

