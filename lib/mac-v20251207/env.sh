## GIT & SSH
# cd /Users/zhangxin
# git config --global user.name "zhangxin"
# git config --global user.email "zhangxin8069@qq.com"
# ssh-keygen -t ed25519 -C "zhangxin8069@qq.com"
# eval "$(ssh-agent -s)"
# ssh-add ~/.ssh/id_ed25519
# echo -e "id_rsa.pub:\n"
# cat ~/.ssh/id_ed25519.pub
# echo -e "\nput this to gitee's ssh.then run\"ssh -T git@gitee.com\""
# git clone git@gitee.com:zhangxin8069/configure.git
# git clone git@gitee.com:zhangxin8069/PyQCU.git
# source env.sh
# sh_init.sh

## BUILD LIBRARIES DIR
# mkdir -p /Users/zhangxin/lib

## CONDA
# wget https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-py311_25.9.1-3-MacOSX-arm64.sh
# conda create --name qcu python=3.11 cmake autoconf automake libtool wget
# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
__conda_setup="$('/Users/zhangxin/miniconda3/bin/conda' 'shell.bash' 'hook' 2>/dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "/Users/zhangxin/miniconda3/etc/profile.d/conda.sh" ]; then
        . "/Users/zhangxin/miniconda3/etc/profile.d/conda.sh"
    else
        export PATH="/Users/zhangxin/miniconda3/bin:$PATH"
    fi
fi
unset __conda_setup
conda activate qcu
# conda install -c conda-forge mpi4py
# conda install -c conda-forge h5py
# <<< conda initialize <<<

## WATCH
# git clone https://github.com/tj/watch.git
# make -j8
export PATH=/Users/zhangxin/lib/watch:$PATH

## TREE
# git clone https://github.com/kddnewton/tree.git
# make -j8
export PATH=/Users/zhangxin/lib/tree:$PATH

## HTOP
# git clone https://github.com/htop-dev/htop.git
# ./autogen.sh
# ./configure --prefix=/Users/zhangxin/lib/htop
# make -j8
export PATH=/Users/zhangxin/lib/htop:$PATH

## BTOP
# git clone https://github.com/aristocratos/btop.git
# make -j8
export PATH=/Users/zhangxin/lib/btop/bin:$PATH

## PYTHON PACKAGES
# pip install torch scipy cython matplotlib opt_einsum

## ENV
export KMP_DUPLICATE_LIB_OK=TRUE
export PYTORCH_ENABLE_MPS_FALLBACK=1
export PATH=/Library/TeX/texbin:$PATH

