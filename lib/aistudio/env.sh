pushd ~
echo "
export PATH=\$PATH:/home/aistudio/external-libraries/sbin
export PYTHONPATH=\$PYTHONPATH:/home/aistudio/external-libraries
export LD_LIBRARY_PATH=\$LD_LIBRARY_PATH:/home/aistudio/external-libraries/quda-develop/build/lib
source ~/work/configure/env.sh
source ~/work/qcu/env.sh
" >> ./.bashrc
source ./.bashrc
popd

