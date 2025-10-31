# BASH
# unset
# MODULE
module purge
module load compiler/devtoolset/7.3.1
module load compiler/dtk-23.04
module load compiler/gcc/7.3.1
module load hpcx/gcc-7.3.1
module list
# EXPORT
export PATH=/public/home/zhangxin/dcu/sbin:$PATH
export CUPY_INSTALL_USE_HIP=1
export OMPI_MCA_opal_cuda_support=0
export ROCM_HOME=/public/sugon/software/compiler/dtk-23.04
pushd ${ROCM_HOME}
source ./env.sh
pushd ./cuda
source ./env.sh
popd
popd
export HIPCC=hipcc
export CC=hipcc
export CXX=hipcc
export HCC_AMDGPU_TARGET=gfx906
export LD_LIBRARY_PATH=/public/home/zhangxin/dcu/lib:$LD_LIBRARY_PATH
