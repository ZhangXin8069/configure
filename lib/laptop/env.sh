# BASH
# unset

# EXPORT
export PATH=${HOME}/sbin:$PATH
export LD_LIBRARY_PATH=${HOME}/slib:$LD_LIBRARY_PATH

# ALIAS
alias python="/usr/local/python/python"
alias pip="/usr/local/python/python -m pip"

# SOURCE
pushd ${HOME}/qcu
source ./computer-env.sh
popd
