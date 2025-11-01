# CONFIGURE
pushd /home/phyww/zhangxin
pushd ./configure
source env.sh
popd
popd

# CONDA
# wget https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-py311_25.7.0-2-Linux-aarch64.sh
# conda create --name qcu python=3.11 cmake
# TORCH
# https://www.hiascend.com/document/detail/zh/CANNCommunityEdition/82RC1/softwareinst/instg/instg_quick.html
### 1.
# conda config --add channels https://repo.huaweicloud.com/ascend/repos/conda/
# conda install ascend::cann-toolkit
# source /home/phyww/zhangxin/miniconda3/Ascend/ascend-toolkit/set_env.sh
# conda install ascend::a3-cann-kernels
### 2.
# chmod +x Ascend-cann-toolkit_8.2.RC1_linux-aarch64.run
# ./Ascend-cann-toolkit_8.2.RC1_linux-aarch64.run --install
# source /usr/local/Ascend/ascend-toolkit/set_env.sh
# chmod +x Atlas-A3-cann-kernels_8.2.RC1_linux-aarch64.run
# ./Atlas-A3-cann-kernels_8.2.RC1_linux-aarch64.run --install

# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
__conda_setup="$('/home/phyww/zhangxin/miniconda3/bin/conda' 'shell.bash' 'hook' 2>/dev/null)"
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
conda activate qcu
source /home/phyww/zhangxin/miniconda3/Ascend/ascend-toolkit/set_env.sh
# <<< conda initialize <<<
# conda install python=3.11
# wget https://gitee.com/ascend/pytorch/releases/download/v7.1.0.2-pytorch2.5.1/torch_npu-2.5.1.post3-cp311-cp311-manylinux_2_17_aarch64.manylinux2014_aarch64.whl
# pip install torch_npu-2.5.1.post3-cp311-cp311-manylinux_2_17_aarch64.manylinux2014_aarch64.whl
# pip install pyyaml
# python3 -c "import torch;import torch_npu; a = torch.randn(3, 4).npu(); print(a + a);"
