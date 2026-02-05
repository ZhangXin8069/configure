# @CONFIGURE@
pushd /public/home/zhangxin80699
pushd ./configure
source env.sh
popd
popd
# @MODULE@
module purge
module list

# @EXPORT@
export PYTHONPATH=/public/home/zhangxin80699/PyQCU:${PYTHONPATH}
export ROCM_HOME="/public/home/sghpc_sdk/Linux_x86_64/25.8/dtk/dtk-25.04.2"
source ${ROCM_HOME}/env.sh
# @CONDA@
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
conda activate pytorch-python3.10
# @@TILELANG@@
# git clone https://gitee.com/zhangxin8069/tilelang-ascend.git
pushd ./tilelang-ascend
# bash ./install_ascend.sh
source ./set_env.sh
popd