## UBUNTU
# pkg update
# mv /data/data/vn.vhn.vsc/files/usr/var/lib/dpkg/status /data/data/vn.vhn.vsc/files/usr/var/lib/dpkg/status.old
# pkg install git file proot-distro wget
# proot-distro list
# proot-distro install ubuntu
# echo 'proot-distro login ubuntu' >.bashrc
# reboot
# apt update
# apt upgrade
# apt install zsh ssh vim htop tree
# reboot
# git config --global user.name "zhangxin"
# git config --global user.email "zhangxin8069@qq.com"
# ssh-keygen -t ed25519 -C "zhangxin8069@qq.com"
# eval "$(ssh-agent -s)"
# ssh-add ~/.ssh/id_ed25519
# echo -e "id_rsa.pub:\n"
# cat ~/.ssh/id_ed25519.pub
# echo -e "\nput this to gitee's ssh.then run\"ssh -T git@gitee.com\""
# reboot
# git clone git@gitee.com:zhangxin8069/configure.git
# git clone git@gitee.com:zhangxin8069/PyQCU.git
# cd ./configure
# source env.sh
# sh_init.sh
# reboot
## CONFIGURE
pushd $HOME
# mkdir lib
pushd ./configure
source env.sh
popd
popd
## CONDA
# wget https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-py311_25.7.0-2-Linux-aarch64.sh
# bash ./Miniconda3-py311_25.7.0-2-Linux-aarch64.sh
# conda create --name qcu python=3.11 cmake
# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
__conda_setup="$('$HOME/miniconda3/bin/conda' 'shell.bash' 'hook' 2>/dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
        . "$HOME/miniconda3/etc/profile.d/conda.sh"
    else
        export PATH="$HOME/miniconda3/bin:$PATH"
    fi
fi
unset __conda_setup
conda activate qcu
# <<< conda initialize <<<
## PIP
# pip install torch cython scipy matplotlib
## MPI
cd ~/lib
wget https://download.open-mpi.org/release/open-mpi/v4.1/openmpi-4.1.5.tar.gz
tar -xzf openmpi-4.1.5.tar.gz
cd openmpi-4.1.5
./configure --prefix=$HOME/lib/openmpi-4.1.5
make -j$(nproc)
make install
export MPI_DIR=$HOME/lib/openmpi-4.1.5
export PATH=$HOME/lib/openmpi-4.1.5/bin:$PATH
export MPI_INCLUDE_PATH=$HOME/lib/openmpi-4.1.5/include
export LD_LIBRARY_PATH=$HOME/lib/openmpi-4.1.5/lib:$LD_LIBRARY_PATH
## HDF5
cd ~/lib
wget https://github.com/HDFGroup/hdf5/releases/download/hdf5-1_14_2/hdf5-1_14_2.tar.gz
tar -xzf hdf5-1_14_2.tar.gz
CC=mpicc CXX=mpicxx FC=mpif90 ./configure --prefix=$HOME/lib/hdfsrc --enable-parallel --enable-shared --enable-hl --enable-build-hl-shared
make -j$(nproc)
make install
cp ./hl/src/hdf5_hl* include/
cp ./hl/src/.libs/libhdf5_hl* lib
export HDF5_DIR=$HOME/lib/hdfsrc
export PATH=$HOME/lib/hdfsrc/bin:$PATH
export HDF5_INCLUDE_PATH=$HOME/lib/hdfsrc/include
export LD_LIBRARY_PATH=$HOME/lib/hdfsrc/lib:$LD_LIBRARY_PATH
## H5PY
cd ~/lib
export HDF5_MPI="ON"
# export CFLAGS="-I/path/to/include"
export CFLAGS="-I${MPI_INCLUDE_PATH} -I${HDF5_INCLUDE_PATH} -I${HDF5_DIR}/hl/src"
# export LDFLAGS="-L/path/to/lib"
pip install --no-binary=h5py h5py
