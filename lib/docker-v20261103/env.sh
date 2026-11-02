# @EXPORT@
export LD_LIBRARY_PATH=/root/PyQCU/cpp/cuda/qcu:$LD_LIBRARY_PATH
export PYTHONPATH=/root/PyQCU:${PYTHONPATH}
export NO_PROXY="127.0.0.1,localhost"
export MPI_ALLOW_RUN_AS_ROOT=1
export OMPI_ALLOW_RUN_AS_ROOT=1
export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1
alias mpirun='mpirun --allow-run-as-root'
alias python='python3 -u'

# @ENV@
[ -r "${HOME}/env-key.sh" ] && source ${HOME}/env-key.sh
[ -r "${HOME}/PyQCU/env.sh" ] && source ${HOME}/PyQCU/env.sh
