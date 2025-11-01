## CONFIGURE
pushd /home/phyww/zhangxin
pushd ./configure
source env.sh
popd
popd

## CONDA
# wget https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-py311_25.7.0-2-Linux-aarch64.sh
# conda create --name qcu python=3.11 cmake

## TORCH
# https://www.hiascend.com/document/detail/zh/CANNCommunityEdition/82RC1/softwareinst/instg/instg_quick.html
### 1.
# conda config --add channels https://repo.huaweicloud.com/ascend/repos/conda/
# conda install ascend::cann-toolkit
# source /home/phyww/zhangxin/miniconda3/Ascend/ascend-toolkit/set_env.sh
# conda install ascend::a3-cann-kernels
### 2.
# chmod +x Ascend-cann-toolkit_8.2.RC1_linux-aarch64.run
# ./Ascend-cann-toolkit_8.2.RC1_linux-aarch64.run --install
# source /usr/local/Ascend/ascend-toolkit/set_env.sh
# chmod +x Atlas-A3-cann-kernels_8.2.RC1_linux-aarch64.run
# ./Atlas-A3-cann-kernels_8.2.RC1_linux-aarch64.run --install
# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
__conda_setup="$('/home/phyww/zhangxin/miniconda3/bin/conda' 'shell.bash' 'hook' 2>/dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "/home/phyww/zhangxin/miniconda3/etc/profile.d/conda.sh" ]; then
        . "/home/phyww/zhangxin/miniconda3/etc/profile.d/conda.sh"
    else
        export PATH="/home/phyww/zhangxin/miniconda3/bin:$PATH"
    fi
fi
unset __conda_setup
conda activate qcu
source /home/phyww/zhangxin/miniconda3/Ascend/ascend-toolkit/set_env.sh
# <<< conda initialize <<<
# wget https://gitee.com/ascend/pytorch/releases/download/v7.1.0.2-pytorch2.5.1/torch_npu-2.5.1.post3-cp311-cp311-manylinux_2_17_aarch64.manylinux2014_aarch64.whl
# pip install torch_npu-2.5.1.post3-cp311-cp311-manylinux_2_17_aarch64.manylinux2014_aarch64.whl
# pip install pyyaml
# python3 -c "import torch;import torch_npu; a = torch.randn(3, 4).npu(); print(a + a);"

## MPI
# wget https://download.open-mpi.org/release/open-mpi/v4.1/openmpi-4.1.5.tar.gz
# tar -xzf openmpi-4.1.5.tar.gz
# ./configure --prefix=/home/phyww/zhangxin/lib/openmpi-4.1.5
# make -j$(nproc)
# make install
export PATH=/home/phyww/zhangxin/lib/openmpi-4.1.5/bin:$PATH
export MPI_INCLUDE_PATH=/home/phyww/zhangxin/lib/openmpi-4.1.5/include
export LD_LIBRARY_PATH=/home/phyww/zhangxin/lib/openmpi-4.1.5/lib:$LD_LIBRARY_PATH

# HDF5
# wget https://github.com/HDFGroup/hdf5/releases/download/hdf5-1_14_2/hdf5-1_14_2.tar.gz
# tar -xzf hdf5-1_14_2.tar.gz
# CC=mpicc CXX=mpicxx FC=mpif90 ./configure --prefix=/home/phyww/zhangxin/lib/hdfsrc --enable-fortran --enable-static=yes --enable-parallel --enable-shared 
# make -j$(nproc)
# make install
export HDF5_DIR=/home/phyww/zhangxin/lib/hdfsrc
export PATH=/home/phyww/zhangxin/lib/hdfsrc/bin:$PATH
export LD_LIBRARY_PATH=/home/phyww/zhangxin/lib/hdfsrc/lib:$LD_LIBRARY_PATH

## H5PY
# export HDF5_MPI="ON" && pip install --no-binary=h5py h5py

## PYTHON PACKAGES
# pip install cython matplotlib