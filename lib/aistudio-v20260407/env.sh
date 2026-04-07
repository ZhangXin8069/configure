# ln -s ./configure/lib/aistudio-v20260407/env.sh .
## ZHANGXIN
# git clone https://gitee.com/zhangxin8069/configure.git
pushd /home/aistudio/configure
source ./env.sh
popd

## CONDA
# wget https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-py311_25.7.0-2-Linux-x86_64.sh
# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
__conda_setup="$('/home/aistudio/miniconda3/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
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
# <<< conda initialize <<<
# conda create --name qcu --clone base
conda activate qcu

## HTOP
# git clone https://gitee.com/mirrors/htop.git
# ./autogen.sh
# ./configure --prefix=/home/aistudio/lib/htop
# make -j$(nproc)
# make install
export PATH=/home/aistudio/lib/htop/bin:$PATH

## MPI
# wget https://gitee.com/zhangxin8069/Packages/raw/main/openmpi_packages/openmpi-4.1.5.tar.gz
# tar -xzf openmpi-4.1.5.tar.gz
# ./configure --prefix=/home/aistudio/lib/openmpi-4.1.5
# make -j$(nproc)
# make install
export MPI_DIR=/home/aistudio/lib/openmpi-4.1.5
export PATH=/home/aistudio/lib/openmpi-4.1.5/bin:$PATH
export MPI_INCLUDE_PATH=/home/aistudio/lib/openmpi-4.1.5/include
export LD_LIBRARY_PATH=/home/aistudio/lib/openmpi-4.1.5/lib:$LD_LIBRARY_PATH

# HDF5
# wget https://gitee.com/zhangxin8069/Packages/raw/main/hdf5_packages/hdf5-1_14_2.tar.gz
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
# pip install cython matplotlib mpi4py tilelang

## PYTHONPATH
# git clone https://gitee.com/zhangxin8069/PyQCU.git
export PYTHONPATH=/home/aistudio/PyQCU:$PYTHONPATH