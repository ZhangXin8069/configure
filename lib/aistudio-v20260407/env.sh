## CONDA
# wget https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-py311_25.7.0-2-Linux-aarch64.sh
# conda create --name qcu python=3.11 cmake

## TORCH
# https://www.hiascend.com/document/detail/zh/CANNCommunityEdition/82RC1/softwareinst/instg/instg_quick.html
### 1.
# conda config --add channels https://repo.huaweicloud.com/ascend/repos/conda/
# conda install ascend::cann-toolkit
# source /usr/local/Ascend/ascend-toolkit/set_env.sh
# conda install ascend::a3-cann-kernels
### 2.
# wget https://ascend-repo.obs.cn-east-2.myhuaweicloud.com/CANN/CANN%208.5.1/Ascend-cann-910b-ops_8.5.1_linux-aarch64.run?response-content-type=application/octet-stream
# chmod +x Ascend-cann-910b-ops_8.5.1_linux-aarch64.run
# ./Ascend-cann-910b-ops_8.5.1_linux-aarch64.run --install
# wget https://ascend-repo.obs.cn-east-2.myhuaweicloud.com/CANN/CANN%208.5.1/Ascend-cann-toolkit_8.5.1_linux-aarch64.run?response-content-type=application/octet-stream
# chmod +x Ascend-cann-toolkit_8.5.1_linux-aarch64.run
# ./Ascend-cann-toolkit_8.5.1_linux-aarch64.run --install
source /usr/local/Ascend/ascend-toolkit/set_env.sh
# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
__conda_setup="$('/root/miniconda3/bin/conda' 'shell.bash' 'hook' 2>/dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "/root/miniconda3/etc/profile.d/conda.sh" ]; then
        . "/root/miniconda3/etc/profile.d/conda.sh"
    else
        export PATH="/root/miniconda3/bin:$PATH"
    fi
fi
unset __conda_setup
conda activate qcu
# <<< conda initialize <<<
# pip3 install torch-npu==2.1.0.post17 pyyaml numpy==1.26.4
# python3 -c "import torch;import torch_npu; a = torch.randn(3, 4).npu(); print(a + a);"

## MPI
# wget https://download.open-mpi.org/release/open-mpi/v4.1/openmpi-4.1.5.tar.gz
# tar -xzf openmpi-4.1.5.tar.gz
# ./configure --prefix=/root/lib/openmpi-4.1.5
# make -j$(nproc)
# make install
export MPI_DIR=/root/lib/openmpi-4.1.5
export PATH=/root/lib/openmpi-4.1.5/bin:$PATH
export MPI_INCLUDE_PATH=/root/lib/openmpi-4.1.5/include
export LD_LIBRARY_PATH=/root/lib/openmpi-4.1.5/lib:$LD_LIBRARY_PATH

# HDF5
# wget https://github.com/HDFGroup/hdf5/releases/download/hdf5-1_14_2/hdf5-1_14_2.tar.gz
# tar -xzf hdf5-1_14_2.tar.gz
# CC=mpicc CXX=mpicxx FC=mpif90 ./configure --prefix=/root/lib/hdfsrc --enable-parallel --enable-shared --enable-hl --enable-build-hl-shared
# make -j$(nproc)
# make install
# cp ./hl/src/hdf5_hl* include/
# cp ./hl/src/.libs/libhdf5_hl* lib
export HDF5_DIR=/root/lib/hdfsrc
export PATH=/root/lib/hdfsrc/bin:$PATH
export HDF5_INCLUDE_PATH=/root/lib/hdfsrc/include
export LD_LIBRARY_PATH=/root/lib/hdfsrc/lib:$LD_LIBRARY_PATH

## H5PY
# export HDF5_MPI="ON"
# # export CFLAGS="-I/path/to/include"
# export CFLAGS="-I${MPI_INCLUDE_PATH} -I${HDF5_INCLUDE_PATH} -I${HDF5_DIR}/hl/src"
# # export LDFLAGS="-L/path/to/lib"
# pip install --no-binary=h5py h5py

## PYTHON PACKAGES
# pip install cython matplotlib mpi4py

## PROXY
# git config --global http.proxy http://10.147.32.201:3128

## TILELANG
# git clone --recursive https://gitee.com/zhangxin8069/tilelang-ascend.git
## the image gitmodule of tilelang
# [submodule "3rdparty/cutlass"]
# 	path = 3rdparty/cutlass
# 	url = https://gitee.com/zhangxin8069/cutlass
# [submodule "3rdparty/tvm"]
# 	path = 3rdparty/tvm
# 	url = https://gitee.com/zhangxin8069/tvm.git
# [submodule "3rdparty/composable_kernel"]
# 	path = 3rdparty/composable_kernel
# 	url = https://gitee.com/zhangxin8069/composable_kernel.git
# [submodule "3rdparty/catlass"]
# 	path = 3rdparty/catlass
# 	url = https://gitee.com/ascend/catlass.git
# [submodule "3rdparty/pto-isa"]
# 	path = 3rdparty/pto-isa
# 	url = https://gitcode.com/cann/pto-isa.git
# [submodule "3rdparty/shmem"]
# 	path = 3rdparty/shmem
# 	url = https://gitcode.com/cann/shmem.git
## the image gitmodule of tvm
# [submodule "dmlc-core"]
#         path = 3rdparty/dmlc-core
#         url = https://gitee.com/zhangxin8069/dmlc-core.git
# [submodule "dlpack"]
#         path = 3rdparty/dlpack
#         url = https://gitee.com/zhangxin8069/dlpack.git
# [submodule "3rdparty/rang"]
#         path = 3rdparty/rang
#         url = https://gitee.com/zhangxin8069/rang.git
# [submodule "3rdparty/vta-hw"]
#         path = 3rdparty/vta-hw
#         url = https://gitee.com/zhangxin8069/tvm-vta.git
# [submodule "3rdparty/libbacktrace"]
#         path = 3rdparty/libbacktrace
#         url = https://gitee.com/zhangxin8069/libbacktrace.git
# [submodule "3rdparty/cutlass"]
#         path = 3rdparty/cutlass
#         url = https://gitee.com/zhangxin8069/cutlass.git
# [submodule "3rdparty/OpenCL-Headers"]
#         path = 3rdparty/OpenCL-Headers
#         url = https://gitee.com/zhangxin8069/OpenCL-Headers.git
# [submodule "3rdparty/cnpy"]
#         path = 3rdparty/cnpy
#         url = https://gitee.com/zhangxin8069/cnpy.git
# [submodule "3rdparty/cutlass_fpA_intB_gemm"]
#         path = 3rdparty/cutlass_fpA_intB_gemm
#         url = https://gitee.com/zhangxin8069/cutlass_fpA_intB_gemm
# [submodule "3rdparty/libflash_attn"]
#         path = 3rdparty/libflash_attn
#         url = https://gitee.com/zhangxin8069/libflash_attn
# [submodule "3rdparty/flashinfer"]
#         path = 3rdparty/flashinfer
#         url = https://gitee.com/zhangxin8069/flashinfer.git
# [submodule "3rdparty/composable_kernel"]
#         path = 3rdparty/composable_kernel
#         url = https://gitee.com/zhangxin8069/composable_kernel
# pushd /root/tilelang-ascend
# bash ./install_ascend.sh
# source ./set_env.sh
export export TL_ROOT=/root/tilelang-ascend
export ACL_OP_INIT_MODE=1% 
# popd

## NUMPY
# pip install numpy==1.26.4 -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple --verbose

## PYTHONPATH
export PYTHONPATH=/root/PyQCU:$PYTHONPATH
export PYTHONPATH=/root/tilelang-ascend:$PYTHONPATH
