cd ${HOME}
# @NETWATCH@
# b=$(readlink -f "$(which netwatch)") && sudo groupadd -f netwatch && sudo usermod -aG netwatch "$USER" && sudo chown root:netwatch "$b" && sudo chmod 0750 "$b" && sudo setcap 'cap_net_raw,cap_bpf,cap_perfmon+eip' "$b" && echo 'Log in again to join the group: netwatch cannot start until you do'
alias iftop='sudo ~/miniforge3/bin/netwatch'
# @EXPORT@
export CUDA_PATH=$CONDA_PREFIX/targets/x86_64-linux
export CPLUS_INCLUDE_PATH=$CUDA_PATH/include:$CPLUS_INCLUDE_PATH
export PATH=$CONDA_PREFIX/nvvm/bin:$PATH
export HDF5_MPI="ON"
export HDF5_DIR=$CONDA_PREFIX
