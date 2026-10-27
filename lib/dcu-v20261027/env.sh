# @JIANGXY@
module purge
module load apps/git/2.30.2
module load compiler/cmake/3.25.0
module load compiler/devtoolset/7.3.1
module load mpi/hpcx/2.11.0/gcc-7.3.1
module load compiler/gcc/13.3.0
module load compiler/dtk/23.10
module list
export CMAKE_PREFIX_PATH=$(dirname $(which hipcc))/../lib64/cmake/amd_comgr
export ROCM_HOME=$ROCM_PATH
export CUPY_INSTALL_USE_HIP=1
export HCC_AMDGPU_TARGET=gfx906
export HDF5_MPI=ON
export HDF5_DIR="/public/software/mathlib/hdf5/1.12.2/gnu_fortran_parallel"
export AMDGPU_TARGETS=gfx906
export CC=clang
export CXX=clang++
export HIPCXX=dcc
export CFLAGS="-Wno-return-type -Wno-inconsistent-missing-override"
export CXXFLAGS="-Wno-return-type -Wno-inconsistent-missing-override"
export HIPFLAGS="-Wno-return-type -Wno-inconsistent-missing-override"
# @@QUDA@@
source /public/home/jiangxy_1/.venv/bin/activate
export QUDA_PATH="/public/home/jiangxy_1/Build-USQCD-SciDAC/scidac/install/quda-mpi-gfx906"   #JiangXY 2026.04.01
export PYTHONPATH="/public/home/jiangxy_1/.venv/lib/python3.8/site-packages":${PYTHONPATH}
# @ZHANGXIN@
# @@TORCH@@
# pip install /public/software/apps/DeepLearning/whl/dtk-23.10/pytorch/torch2.1/py38/torch-2.1.0a0+git793d2b5.abi0.dtk2310-cp38-cp38-manylinux2014_x86_64.whl --force-reinstall -t /public/home/sunpeng_1/.local/lib/python3.8/site-packages -U
export PYTHONPATH="/public/home/sunpeng_1/.local/lib/python3.8/site-packages":${PYTHONPATH}
# @@QCU@@
pushd ${ROCM_PATH}/cuda
source ./env.sh
popd
pushd /public/home/sunpeng_1/PyQCU
source ./env.sh
popd
