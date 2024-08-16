# BASH
# unset

# MODULE
module purge
module load gcc/10.3.0-gcc-4.8.5 
module load cuda/11.4.4-gcc-10.3.0
module load git/2.40.0-gcc-10.3.0
module load openmpi/4.1.5-gcc-10.3.0
module load cmake/3.22.2-gcc-10.3.0
module load ncurses/6.2-intel-2022.0.2
module load intel-oneapi/compiler-rt/2024.0.0 
module load miniconda3/22.11.1-gcc-10.3.0
module list

# EXPORT
export PATH=/public/home/zhangxin/sbin:$PATH
export LD_LIBRARY_PATH=/public/home/zhangxin/slib:$LD_LIBRARY_PATH

# CONDA
# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
__conda_setup="$('/public/soft/linux-centos7-x86_64/gcc-10.3.0/miniconda3-22.11.1-jrusysshr36o4fjbexlhrpljufoxhu4b/bin/conda' 'shell.zsh' 'hook' 2> /dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "/public/soft/linux-centos7-x86_64/gcc-10.3.0/miniconda3-22.11.1-jrusysshr36o4fjbexlhrpljufoxhu4b/etc/profile.d/conda.sh" ]; then
        . "/public/soft/linux-centos7-x86_64/gcc-10.3.0/miniconda3-22.11.1-jrusysshr36o4fjbexlhrpljufoxhu4b/etc/profile.d/conda.sh"
    else
        export PATH="/public/soft/linux-centos7-x86_64/gcc-10.3.0/miniconda3-22.11.1-jrusysshr36o4fjbexlhrpljufoxhu4b/bin:$PATH"
    fi
fi
unset __conda_setup
# <<< conda initialize <<<
conda activate snsc-qcu