# DO NOTHING
pushd /root/PyQCU
source ./env.sh
popd
export LD_LIBRARY_PATH=/root/lib:$LD_LIBRARY_PATH
export LD_LIBRARY_PATH=/root/PyQCU/lib:$LD_LIBRARY_PATH
alias mpirun='mpirun --allow-run-as-root'
alias python='python3 -u'