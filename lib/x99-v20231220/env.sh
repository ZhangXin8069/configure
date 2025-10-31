# BASH
# unset

# EXPORT
export LD_LIBRARY_PATH=${HOME}/slib:$LD_LIBRARY_PATH
export PATH=${HOME}/sbin:$PATH

# ALIAS
alias ncu="nv-nsight-cu-cli"
alias ncu-ui="nv-nsight-cu"

# SOURCE
pushd /home/kfutfd/qcu
source ./x99-env.sh
popd
