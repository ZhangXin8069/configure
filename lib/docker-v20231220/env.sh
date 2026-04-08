# @EXPORT@
export PYTHONPATH=/root/PyQCU/:${PYTHONPATH}
export PYTHONPATH=/root/lib/PyQuda-master:${PYTHONPATH}
export MPI_ALLOW_RUN_AS_ROOT=1
export OMPI_ALLOW_RUN_AS_ROOT=1
export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/root/lib
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/root/PyQCU/lib
alias mpirun='mpirun --allow-run-as-root'
alias python='python3 -u'