source /work_ssd/software/HPCKit/25.2.1/setvars.sh
module use /work_ssd/software/modulefile/modules/
module purge
module load anaconda3/2023.3 cmake/2026.1.RC1
module list
source ${CONDA_SH}
# pip download cython -i https://pypi.tuna.tsinghua.edu.cn/simple --only-binary=:all: --platform manylinux_2_27_aarch64 --platform manylinux2014_aarch64 --python-version 310
# pip download mpi4py -i https://pypi.tuna.tsinghua.edu.cn/simple --only-binary=:all: --platform manylinux_2_27_aarch64 --platform manylinux2014_aarch64 --python-version 310
export PYTHONPATH=/home/share/nsls_yangyb/.local/lib/python3.10/site-packages:${PYTHONPATH}
[ -r "/home/share/nsls_yangyb/PyQCU/env.sh" ] && source "/home/share/nsls_yangyb/PyQCU/env.sh"
alias sinfo="dinfo -q q_hpcapp --type rack"
alias zsinfo="dnode -q q_hpcapp -s 'OK'"
alias squeue="djob -u nsls_yangyb"
alias sbatch="dsub -s"
alias scancel="dkill"
conda deactivate
conda activate base
