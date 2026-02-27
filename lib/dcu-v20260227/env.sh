# @CONFIGURE@
pushd /public/home/scnethpc2623
pushd ./configure
source env.sh
# @@UNALIAS@@
unalias history
unalias his
popd
popd
# @MODULE@
module purge
module load anaconda3/2023.09
module load compiler/dtk/25.04
module list
# @EXPORT@
export PYTHONPATH=/public/home/scnethpc2623/PyQCU:${PYTHONPATH}
export ROCM_HOME="/public/software/compiler/dtk-25.04"
source ${ROCM_HOME}/cuda/env.sh

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