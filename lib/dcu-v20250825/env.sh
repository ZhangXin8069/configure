# BASH
# unset
# MODULE
module purge
module load compiler/dtk/25.04.1
module load sghpc-mpi-gcc-mlnx/25.6
module load sghpcdas/25.6
module list

# EXPORT
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
# conda init bash
# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
__conda_setup="$('/public/home/sghpc_sdk/Linux_x86_64/25.6/das/conda/bin/conda' 'shell.bash' 'hook' 2>/dev/null)"
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
conda activate cupy310
