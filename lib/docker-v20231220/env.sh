# DO NOTHING
pushd /root/PyQCU
source ./env.sh
popd
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/root/PyQCU/lib
alias mpirun='mpirun --allow-run-as-root'
alias python='python3 -u'