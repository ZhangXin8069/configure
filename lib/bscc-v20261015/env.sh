## MODULE
module purge
module load compilers/gcc/11.3.0 compilers/cuda/12.4 cudnn/8.9.5.29_cuda12.x nccl/2.26.5-1_cuda12.4 curl/8.7.1 openssl/3.3.0 git/2.45.1 git-lfs/3.5.1 mpi/openmpi4.1.5-gcc11.3.0-cuda12.4
module list

## GIT & SSH
# cd ${HOME}
# git config --global user.name "zhangxin"
# git config --global user.email "zhangxin8069@qq.com"
# ssh-keygen -t ed25519 -C "zhangxin8069@qq.com"
# eval "$(ssh-agent -s)"
# ssh-add ~/.ssh/id_ed25519
# echo -e "id_rsa.pub:\n"
# cat ~/.ssh/id_ed25519.pub
# echo -e "\nput this to gitee's ssh.then run\"ssh -T git@gitee.com\""
# git clone git@gitee.com:zhangxin8069/configure.git
# git clone git@gitee.com:zhangxin8069/PyQCU.git
# source ./env.sh
# sh_init.sh

## BUILD LIBRARIES DIR
# mkdir -p ${HOME}/lib

## CONDA
# /home/bingxing2/apps/anaconda/2021.11
# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
__conda_setup="$('/home/bingxing2/apps/anaconda/2021.11/bin/conda' 'shell.bash' 'hook' 2>/dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "/home/bingxing2/apps/anaconda/2021.11/etc/profile.d/conda.sh" ]; then
        . "/home/bingxing2/apps/anaconda/2021.11/etc/profile.d/conda.sh"
    else
        export PATH="/home/bingxing2/apps/anaconda/2021.11/bin:$PATH"
    fi
fi
unset __conda_setup
# <<< conda initialize <<<
# conda create --name qcu python=3.11.10 cmake autoconf automake libtool wget
conda activate qcu
# conda install -c conda-forge btop
# conda deactivate
# conda env remove -n qcu

## HTOP
# git clone https://gitee.com/zhangxin8069/htop.git
# ./autogen.sh
# ./configure --prefix=${HOME}/lib/htop
# make -j8
export PATH=${HOME}/lib/htop:$PATH

## TORCH
# pip install /home/bingxing2/apps/package/pytorch/2.7.0-cu124_cp311/torch-2.7.0+cu124-cp311-cp311-linux_aarch64.whl -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple --verbose

## PYTHON PACKAGES
# pip install scipy cython matplotlib opt_einsum psutil -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple --verbose

## HDF5 & MPI4PY & H5PY & CUPY
# wget https://github.com/HDFGroup/hdf5/releases/download/hdf5-1_14_2/hdf5-1_14_2.tar.gz
# tar -xzf hdf5-1_14_2.tar.gz
# CC=mpicc CXX=mpicxx FC=mpif90 ./configure --prefix=${HOME}/lib/hdfsrc --enable-parallel --enable-shared --enable-hl --enable-build-hl-shared
# make -j$(nproc)
# make install
# cp ./hl/src/hdf5_hl* include/
# cp ./hl/src/.libs/libhdf5_hl* lib
export HDF5_DIR=${HOME}/lib/hdfsrc
export PATH=${HOME}/lib/hdfsrc/bin:$PATH
export HDF5_INCLUDE_PATH=${HOME}/lib/hdfsrc/include
export LD_LIBRARY_PATH=${HOME}/lib/hdfsrc/lib:$LD_LIBRARY_PATH
export HDF5_MPI="ON"
# # export CFLAGS="-I/path/to/include"
export MPI_INCLUDE_PATH="/home/bingxing2/apps/mpi/4.1.5-gcc11.3.0-cuda12.4/include"
# export CFLAGS="-I${MPI_INCLUDE_PATH} -I${HDF5_INCLUDE_PATH} -I${HDF5_DIR}/hl/src"
# # export LDFLAGS="-L/path/to/lib"
# export LDFLAGS="-L${LD_LIBRARY_PATH}"
# pip install --no-binary=mpi4py mpi4py -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple --verbose
# pip install --no-binary=h5py h5py -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple --verbose
# pip install --no-binary=cupy cupy -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple --verbose

## PYQCU
[ -r "${HOME}/PyQCU/env.sh" ] && source "${HOME}/PyQCU/env.sh"
