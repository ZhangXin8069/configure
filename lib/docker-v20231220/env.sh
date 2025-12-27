# DO NOTHING
popd /root/PyQCU
source ./env.sh
pushd
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/root/PyQCU/lib
alias mpirun='mpirun --allow-run-as-root'
alias python='python3 -u'