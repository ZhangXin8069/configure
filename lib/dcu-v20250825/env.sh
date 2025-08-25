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
module load compiler/dtk/25.04
module load sghpcdas/25.6
module list

# EXPORT
pushd /opt/dtk-25.04/cuda
source ./env.sh
popd

# CONDA
# conda init bash
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
conda activate cupy310
