# BASH
# unset
# MODULE
module purge
module load gcc/10.3.0-gcc-4.8.5 
module load cuda/11.4.4-gcc-10.3.0
module load git/2.40.0-gcc-10.3.0
module load openmpi/4.1.5-gcc-10.3.0
module load ncurses/6.2-intel-2022.0.2
module load cmake/3.22.2-gcc-10.3.0
module load intel-oneapi/compiler/2024.0.0
module load python/3.9.10-gcc-10.3.0
module list
# EXPORT
export PATH=/public/home/zhangxin/sbin:$PATH
export LD_LIBRARY_PATH=/public/home/zhangxin/slib:$LD_LIBRARY_PATH
export PYTHONPATH=/public/home/zhangxin/.local/lib/python3.9/site-packages:$PYTHONPATH
# ALIAS
alias python="python3.9"
alias pip="pip3.9"
# SOURCE
pushd /public/home/zhangxin/PyQCU
source ./env.sh
popd
