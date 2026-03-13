# @CONFIGURE@
pushd /public/home/scnethpc2623/configure
source ./env.sh
popd
# @@UNALIAS@@
unalias history
unalias his
# @MODULE@
module purge
module load anaconda3/2023.09
module load compiler/dtk/25.04
module list
# @EXPORT@
export PYTHONPATH=/public/home/scnethpc2623/PyQCU:${PYTHONPATH}
export CUDA_PATH="/public/software/compiler/dtk-25.04/cuda"
export CUDA_BIN_PATH=$CUDA_PATH/bin
export PATH=$CUDA_BIN_PATH:$PATH
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$CUDA_PATH/lib64:$CUDA_PATH/extras/CUPTI/lib64
export LIBRARY_PATH=$LIBRARY_PATH:$CUDA_PATH/lib64:$CUDA_PATH/extras/CUPTI/lib64
export C_INCLUDE_PATH=$CUDA_PATH/include:$CUDA_PATH/extras/CUPTI/include${C_INCLUDE_PATH:+:${C_INCLUDE_PATH}}

export CPLUS_INCLUDE_PATH=$CUDA_PATH/include:$CUDA_PATH/extras/CUPTI/include${CPLUS_INCLUDE_PATH:+:${CPLUS_INCLUDE_PATH}}
export CUDAARCHS=75
export DCC_PLATFORM=nvcc
# @CONDA@
# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
__conda_setup="$('/public/software/apps/anaconda3/2023.09/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "/public/software/apps/anaconda3/2023.09/etc/profile.d/conda.sh" ]; then
        . "/public/software/apps/anaconda3/2023.09/etc/profile.d/conda.sh"
    else
        export PATH="/public/software/apps/anaconda3/2023.09/bin:$PATH"
    fi
fi
unset __conda_setup
# <<< conda initialize <<<
# conda create -n qcu python=3.10.12
conda activate qcu
# conda install pytorch h5py mpi4py
# pip install -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple tilelang --resume-retries 10
