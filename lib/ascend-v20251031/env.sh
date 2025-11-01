pushd /home/phyww/zhangxin
source ./miniconda3/Ascend/ascend-toolkit/set_env.sh
pushd ./configure
source env.sh
popd
popd
# wget https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-py311_25.7.0-2-Linux-aarch64.sh
# https://www.hiascend.com/document/detail/zh/CANNCommunityEdition/82RC1/softwareinst/instg/instg_quick.html
# conda config --add channels https://repo.huaweicloud.com/ascend/repos/conda/ 
# conda install ascend::cann-toolkit
# source /home/phyww/zhangxin/miniconda3/Ascend/ascend-toolkit/set_env.sh
# conda install ascend::a3-cann-kernels
# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
__conda_setup="$('/home/phyww/zhangxin/miniconda3/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "/home/phyww/zhangxin/miniconda3/etc/profile.d/conda.sh" ]; then
        . "/home/phyww/zhangxin/miniconda3/etc/profile.d/conda.sh"
    else
        export PATH="/home/phyww/zhangxin/miniconda3/bin:$PATH"
    fi
fi
unset __conda_setup
# <<< conda initialize <<<