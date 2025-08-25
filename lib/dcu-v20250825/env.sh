# BASH
# unset
pushd ~/configure
source ./env.sh
popd
clear
# MODULE
module purge
module load sghpc-mpi-gcc-mlnx/25.6
module load compiler/cmake/3.25.3  
module list

# EXPORT
# export CUPY_INSTALL_USE_HIP=1
# export OMPI_MCA_opal_cuda_support=0
# export ROCM_HOME=/public/sugon/software/compiler/dtk-23.04
# pushd ${ROCM_HOME}
# source ./env.sh
# pushd ./cuda
# source ./env.sh
# popd
# popd
# export HIPCC=hipcc
# export CC=hipcc
# export CXX=hipcc
# export HCC_AMDGPU_TARGET=gfx906                
