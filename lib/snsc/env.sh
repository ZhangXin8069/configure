# BASH
# unset
export PYTHONPATH=
export LD_LIBRARY_PATH=
pushd /public/home/zhangxin
pushd ./configure
source ./env.sh
popd
popd

# MODULE
module purge
module load gcc/10.3.0-gcc-4.8.5 
module load cuda/11.4.4-gcc-10.3.0
module load git/2.40.0-gcc-10.3.0
module load openmpi/4.1.5-gcc-10.3.0
module load cmake/3.22.2-gcc-10.3.0
module load python/3.10.10-gcc-10.3.0
module load ncurses/6.2-intel-2022.0.2
module load intel-oneapi/compiler-rt/2024.0.0 
module list
unset

# EXPORT
export PATH=/public/home/zhangxin/sbin:$PATH
export PYTHONPATH=/public/home/zhangxin/external-libraries:$PYTHONPATH
export LD_LIBRARY_PATH=/public/home/zhangxin/slib:$LD_LIBRARY_PATH

# ALIAS
alias pip="pip3.10"
