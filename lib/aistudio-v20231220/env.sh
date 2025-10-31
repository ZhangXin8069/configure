pushd ~
echo "
## zhangxin
export NCCL_DEBUG=
# export NCCL_DEBUG=INFO
export PATH=\$PATH:/home/aistudio/external-libraries/sbin
export LD_LIBRARY_PATH=\$LD_LIBRARY_PATH:/home/aistudio/external-libraries/slib
export LD_LIBRARY_PATH=\$LD_LIBRARY_PATH:/home/aistudio/qcu/lib
export PYTHONPATH=\$PYTHONPATH:/home/aistudio/external-libraries
export PYTHONPATH=\$PYTHONPATH:/home/aistudio/qcu/lib
export LD_LIBRARY_PATH=\$LD_LIBRARY_PATH:/home/aistudio/external-libraries/quda-develop/build/lib
source /home/aistudio/configure/env.sh
## quda
export QUDA_ENABLE_P2P=0
export QUDA_ENABLE_TUNING=0
" >>./.bashrc
source ./.bashrc
popd
