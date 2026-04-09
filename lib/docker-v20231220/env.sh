# @EXPORT@
export LD_LIBRARY_PATH=/root/PyQCU/lib:$LD_LIBRARY_PATH
export LD_LIBRARY_PATH=/root/Build-USQCD-SciDAC/scidac/build/quda-mpi-sm_80/lib:$LD_LIBRARY_PATH
export PYTHONPATH=/root/PyQCU/:${PYTHONPATH}
export PYTHONPATH=/root/lib/PyQuda-master:${PYTHONPATH}
export MPI_ALLOW_RUN_AS_ROOT=1
export OMPI_ALLOW_RUN_AS_ROOT=1
export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1
alias mpirun='mpirun --allow-run-as-root'
alias python='python3 -u'