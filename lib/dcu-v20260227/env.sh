# @MODULE@
module purge
module load anaconda3/2023.09
module load compiler/dtk/25.04.2
module load compiler/gcc/12.2.0
module load mpi/openmpi/4.1.8/gcc-12.2.0/shca
module list
# @EXPORT@
export PYTHONPATH=/public/home/scnethpc2623/PyQCU:${PYTHONPATH}

export CUDA_PATH=${ROCM_PATH}/cuda/cuda-12
export CUDA_BIN_PATH=$CUDA_PATH/bin
export PATH=$CUDA_BIN_PATH:${PATH}
export LD_LIBRARY_PATH=$CUDA_PATH/lib64:$CUDA_PATH/extras/CUPTI/lib64:${LD_LIBRARY_PATH}
export LIBRARY_PATH=$CUDA_PATH/lib64:$CUDA_PATH/extras/CUPTI/lib64:${LIBRARY_PATH}
export C_INCLUDE_PATH=$CUDA_PATH/include:$CUDA_PATH/extras/CUPTI/include:${C_INCLUDE_PATH}
export CPLUS_INCLUDE_PATH=$CUDA_PATH/include:$CUDA_PATH/extras/CUPTI/include:${CPLUS_INCLUDE_PATH}
export CUDAARCHS=75
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
# conda create -n qcu python=3.10.10
# conda create -n qcu --clone qcu_base
conda activate qcu
# @TILELANG@
# pip install ninja pytest mpi4py h5py -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple --force-reinstall -v
# wget https://download.sourcefind.cn:65024/file/4/tilelang/DAS1.7/tilelang-0.1.6.post2+das.opt1.dtk25042-cp310-cp310-manylinux_2_28_x86_64.whl
# pip install tilelang-0.1.6.post2+das.opt1.dtk25042-cp310-cp310-manylinux_2_28_x86_64.whl -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple --force-reinstall -v
# wget https://download.sourcefind.cn:65024/file/4/pytorch/DAS1.7/torch-2.7.1+das.opt1.dtk25042-cp310-cp310-manylinux_2_28_x86_64.whl
# pip install torch-2.7.1+das.opt1.dtk25042-cp310-cp310-manylinux_2_28_x86_64.whl numpy==1.26.4 -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple --force-reinstall -v
