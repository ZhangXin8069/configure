pushd ~/
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
chmod +x Miniconda3-latest-Linux-x86_64.sh
wget https://developer.download.nvidia.com/compute/cuda/12.4.0/local_installers/cuda_12.4.0_550.54.14_linux.run &
./Miniconda3-latest-Linux-x86_64.sh
popd
######
conda create --no-default-packages --name qcu
conda activate qcu
conda install conda-forge::cuda-toolkit=12.4
conda install conda-forge::openmpi=4.1.5
conda install conda-forge::python=3.10.12
conda install conda-forge::nccl=2.23.4
conda install conda-forge::cupy=13.3.0
conda install conda-forge::mpi4py=3.1.4
conda install conda-forge::Cython=3.0.11
pushd ~/miniconda3/envs/qcu
wget https://gitee.com/zhangxin8069/quda_packages/raw/main/quda-develop.tar.gz
tar -xzf quda-develop.tar.gz
mv quda-develop quda
pushd ./quda
mkdir build -p && pushd build
cmake .. -DQUDA_DIRAC_DOMAIN_WALL=OFF -DQUDA_CLOVER_DYNAMIC=OFF -DQUDA_CLOVER_RECONSTRUCT=OFF -DQUDA_DIRAC_NDEG_TWISTED_CLOVER=OFF -DQUDA_DIRAC_NDEG_TWISTED_MASS=OFF -DQUDA_DIRAC_TWISTED_CLOVER=OFF -DQUDA_DIRAC_TWISTED_MASS=OFF -DQUDA_INTERFACE_MILC=OFF -DQUDA_LAPLACE=ON -DQUDA_MULTIGRID=ON -DQUDA_GPU_ARCH=sm_80 -DQUDA_MPI=ON
cmake --build . -j6
cmake --install .
pushd ./lib
ln -s ../quda/build/lib/libquda.so .
popd
popd
popd
popd
