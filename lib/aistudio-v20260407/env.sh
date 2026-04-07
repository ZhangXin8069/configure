## CONDA
# conda create --name qcu python=3.11 cmake zsh htop
# cp -r /home/aistudio/.conda/envs/ lib/

# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
__conda_setup="$('/home/aistudio/miniconda3/bin/conda' 'shell.bash' 'hook' 2>/dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "/home/aistudio/miniconda3/etc/profile.d/conda.sh" ]; then
        . "/home/aistudio/miniconda3/etc/profile.d/conda.sh"
    else
        export PATH="/home/aistudio/miniconda3/bin:$PATH"
    fi
fi
unset __conda_setup
conda activate /home/aistudio/lib/envs/qcu
# <<< conda initialize <<<

## TORCH
# pip3 install torch-npu==2.1.0.post17 pyyaml numpy==1.26.4
# python3 -c "import torch; a = torch.randn(3, 4).cuda(); print(a + a);"

## MPI
# wget https://download.open-mpi.org/release/open-mpi/v4.1/openmpi-4.1.5.tar.gz
# tar -xzf openmpi-4.1.5.tar.gz
# ./configure --prefix=/home/aistudio/lib/openmpi-4.1.5
# make -j$(nproc)
# make install
export MPI_DIR=/home/aistudio/lib/openmpi-4.1.5
export PATH=/home/aistudio/lib/openmpi-4.1.5/bin:$PATH
export MPI_INCLUDE_PATH=/home/aistudio/lib/openmpi-4.1.5/include
export LD_LIBRARY_PATH=/home/aistudio/lib/openmpi-4.1.5/lib:$LD_LIBRARY_PATH

# HDF5
# wget https://github.com/HDFGroup/hdf5/releases/download/hdf5-1_14_2/hdf5-1_14_2.tar.gz
# tar -xzf hdf5-1_14_2.tar.gz
# CC=mpicc CXX=mpicxx FC=mpif90 ./configure --prefix=/home/aistudio/lib/hdfsrc --enable-parallel --enable-shared --enable-hl --enable-build-hl-shared
# make -j$(nproc)
# make install
# cp ./hl/src/hdf5_hl* include/
# cp ./hl/src/.libs/libhdf5_hl* lib
export HDF5_DIR=/home/aistudio/lib/hdfsrc
export PATH=/home/aistudio/lib/hdfsrc/bin:$PATH
export HDF5_INCLUDE_PATH=/home/aistudio/lib/hdfsrc/include
export LD_LIBRARY_PATH=/home/aistudio/lib/hdfsrc/lib:$LD_LIBRARY_PATH

## H5PY
# export HDF5_MPI="ON"
# # export CFLAGS="-I/path/to/include"
# export CFLAGS="-I${MPI_INCLUDE_PATH} -I${HDF5_INCLUDE_PATH} -I${HDF5_DIR}/hl/src"
# # export LDFLAGS="-L/path/to/lib"
# pip install --no-binary=h5py h5py

## PYTHON PACKAGES
# pip install cython matplotlib mpi4py

## NUMPY
# pip install numpy==1.26.4 -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple --verbose

## PYTHONPATH
export PYTHONPATH=/home/aistudio/PyQCU:$PYTHONPATH

## ZHANGXIN
echo "/home/aistudio/lib/envs/qcu/bin/zsh" > ~/.bashrc
ln -s /home/aistudio/configure/lib/_zshrc .zshrc
ln -s /home/aistudio/configure/lib/_oh-my-zsh .oh-my-zsh
# git clone https://gitee.com/zhangxin8069/configure.git
# bash configure/bin/sh_init.sh
# git clone https://gitee.com/zhangxin8069/PyQCU.git