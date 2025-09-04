# BASH
# unset
# MODULE
module use /public/software/modules
module use /opt/hpc/software/modules
module use /public/home/sghpc_sdk/modulefiles
module purge
# module load sghpc-mpi-gcc-mlnx/25.6
module load sghpc-mpi-gcc/25.6
module list

# EXPORT
export PATH=/public/home/zhangxin80699/hdf5-hdf5-1_12_2/build/hdf5-mpi/bin:$PATH
export LD_LIBRARY_PATH=/public/home/zhangxin80699/hdf5-hdf5-1_12_2/build/hdf5-mpi/lib:$LD_LIBRARY_PATH
export PYTHONPATH=/public/home/zhangxin80699/PyQCU:${PYTHONPATH}
export LD_LIBRARY_PATH=/public/home/zhangxin80699/PyQCU/lib:${LD_LIBRARY_PATH}
export CUPY_INSTALL_USE_HIP=1
export OMPI_MCA_opal_cuda_support=0
export ROCM_HOME=$ROCM_PATH
pushd ${ROCM_HOME}
pushd ./cuda
source ./env.sh
popd
popd
export HIPCC=hipcc
export CC=hipcc
export CXX=hipcc
export HCC_AMDGPU_TARGET=gfx936

# CONDA
# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
__conda_setup="$('/public/home/sghpc_sdk/Linux_x86_64/25.6/das/conda/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "/public/home/sghpc_sdk/Linux_x86_64/25.6/das/conda/etc/profile.d/conda.sh" ]; then
        . "/public/home/sghpc_sdk/Linux_x86_64/25.6/das/conda/etc/profile.d/conda.sh"
    else
        export PATH="/public/home/sghpc_sdk/Linux_x86_64/25.6/das/conda/bin:$PATH"
    fi
fi
unset __conda_setup
# <<< conda initialize <<<
pushd /public/home/zhangxin80699
conda activate cupy-env/ 
popd
