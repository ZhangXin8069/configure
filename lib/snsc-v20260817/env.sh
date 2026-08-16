# BASH
# unset
# MODULE
module purge
module use /public/soft/modulefiles/linux-centos7-x86_64
module load gcc/10.3.0-gcc-4.8.5
module load cuda/11.4.4-gcc-10.3.0
module load git/2.40.0-gcc-10.3.0
module load openmpi/4.1.5-gcc-10.3.0
module load ncurses/6.2-intel-2022.0.2
module load cmake/3.22.2-gcc-10.3.0
module load python/3.9.10-gcc-10.3.0
module use /public/soft/modulefiles/apps
module load intel-oneapi/compiler/2024.0.0
module list
# EXPORT
export PATH=/public/home/zhangxin/sbin:$PATH
export PATH=/usr/local/texlive/2024/bin/x86_64-linux:$PATH
export LD_LIBRARY_PATH=/public/home/zhangxin/slib:$LD_LIBRARY_PATH
export PYTHONPATH=/public/home/zhangxin/.local/lib/python3.9/site-packages:$PYTHONPATH
# TOOLCHAIN -- 自 activate.d/env_vars.sh 并入, 本文件为单一权威来源:
# 激活钩子直接引用以下变量, 路径不再重复明文(便于移植与套用)
# --- toolchain compilers ---
export CC=/public/soft/linux-centos7-x86_64/gcc-4.8.5/gcc-10.3.0-uoicdrf766usj4ma5wxqq4zaqgatfyy3/bin/gcc
export CXX=/public/soft/linux-centos7-x86_64/gcc-4.8.5/gcc-10.3.0-uoicdrf766usj4ma5wxqq4zaqgatfyy3/bin/g++
export FC=/public/soft/linux-centos7-x86_64/gcc-4.8.5/gcc-10.3.0-uoicdrf766usj4ma5wxqq4zaqgatfyy3/bin/gfortran
export F77=/public/soft/linux-centos7-x86_64/gcc-4.8.5/gcc-10.3.0-uoicdrf766usj4ma5wxqq4zaqgatfyy3/bin/gfortran
export GCC_ROOT=/public/soft/linux-centos7-x86_64/gcc-4.8.5/gcc-10.3.0-uoicdrf766usj4ma5wxqq4zaqgatfyy3
# --- Intel oneAPI ---
export CMPLR_ROOT=/public/soft/apps/intel/oneapi/compiler/2024.0
export TBBROOT=/public/soft/apps/intel/oneapi/tbb/2021.11
export DIAGUTIL_PATH=/public/soft/apps/intel/oneapi/compiler/2024.0/etc/compiler/sys_check/sys_check.sh
export NLSPATH=/public/soft/apps/intel/oneapi/compiler/2024.0/lib/compiler/locale/%l_%t/%N
export OCL_ICD_FILENAMES="libintelocl_emu.so:libalteracl.so:/public/soft/apps/intel/oneapi/compiler/2024.0/lib/libintelocl.so"
# --- CUDA ---
export CUDA_HOME=/public/soft/linux-centos7-x86_64/gcc-10.3.0/cuda-11.4.4-uizl3zvwy66u3bqllanvuxwxxwfyytwo
export CUDA_ROOT=/public/soft/linux-centos7-x86_64/gcc-10.3.0/cuda-11.4.4-uizl3zvwy66u3bqllanvuxwxxwfyytwo
# --- MPI (OpenMPI) ---
export OPENMPI_ROOT=/public/soft/linux-centos7-x86_64/gcc-10.3.0/openmpi-4.1.5-atnooy4j3scc3fxoqn5scmzvpjqmoa3p
export MPICC=${OPENMPI_ROOT}/bin/mpicc
export MPICXX=${OPENMPI_ROOT}/bin/mpic++
export MPIF77=${OPENMPI_ROOT}/bin/mpif77
export MPIF90=${OPENMPI_ROOT}/bin/mpif90
export PMIX_ROOT=/public/soft/linux-centos7-x86_64/gcc-10.3.0/pmix-4.2.3-ubyezqsqijflgxmbem7rnu4durhmxihh
export UCX_ROOT=/public/soft/linux-centos7-x86_64/gcc-10.3.0/ucx-1.14.0-thg2ethlnec5vdv6cmpok3zg52lfkvoy
export HWLOC_ROOT=/public/soft/linux-centos7-x86_64/gcc-10.3.0/hwloc-2.9.1-n35tnosj7xojsolcwnoamonp2zgk3xo2
export LIBEVENT_ROOT=/public/soft/linux-centos7-x86_64/gcc-10.3.0/libevent-2.1.12-4pbdwhqbk3r2vgv54webjc4w4pwv6dqw
export OMPI_MCA_btl_openib_warn_default_gid_prefix=0
export MPI_ALLOW_RUN_AS_ROOT=1
export OMPI_ALLOW_RUN_AS_ROOT=1
export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1
# --- other tools ---
export CMAKE_ROOT=/public/soft/linux-centos7-x86_64/gcc-10.3.0/cmake-3.22.2-lfaoe2iesrumw7ukmdw7y73tlps2sinl
export NCURSES_ROOT=/public/soft/linux-centos7-x86_64/intel-2022.0.2/ncurses-6.2-6bbomi7ea6lf6fbo4htoipiu6dvaxsip
export PYTHON_ROOT=/public/soft/linux-centos7-x86_64/gcc-10.3.0/python-3.9.10-66y7kbgel6kp6sqtg4z6r5wjuazbxxeh
export GIT_ROOT=/public/soft/linux-centos7-x86_64/gcc-10.3.0/git-2.40.0-723pst5pdujmhe6kflhgqyhq32ic456l
# --- PATH: conda activate 会把 $CONDA_PREFIX/bin(envs/zhangxin-snsc/bin) 前置,
# 此处工具链 bin 亦前置以覆盖系统旧版(git 等); sbin 防重复 ---
export PATH="${PYTHON_ROOT}/bin:${CUDA_HOME}/bin:${OPENMPI_ROOT}/bin:${CMAKE_ROOT}/bin:${GCC_ROOT}/bin:${GIT_ROOT}/bin:$PATH"
case ":$PATH:" in
    *":/public/home/zhangxin/sbin:"*) ;;
    *) export PATH=/public/home/zhangxin/sbin:$PATH ;;
esac
# --- LIBRARY_PATH ---
export LIBRARY_PATH="/public/soft/apps/intel/oneapi/compiler/2024.0/lib:/public/soft/apps/intel/oneapi/tbb/2021.11/lib:${PYTHON_ROOT}/lib:${NCURSES_ROOT}/lib:${OPENMPI_ROOT}/lib:${UCX_ROOT}/lib:${PMIX_ROOT}/lib:${LIBEVENT_ROOT}/lib:${HWLOC_ROOT}/lib:${CUDA_HOME}/lib64:${GCC_ROOT}/lib64:${GCC_ROOT}/lib"
# --- LD_LIBRARY_PATH: PyQCU/cpp/cuda/qcu 由 PyQCU/env.sh 负责(不重复); slib 防重复 ---
export LD_LIBRARY_PATH="/public/soft/apps/intel/oneapi/compiler/2024.0/opt/compiler/lib:/public/soft/apps/intel/oneapi/compiler/2024.0/lib:/public/soft/apps/intel/oneapi/tbb/2021.11/lib:${PYTHON_ROOT}/lib:${NCURSES_ROOT}/lib:${OPENMPI_ROOT}/lib:${UCX_ROOT}/lib:${PMIX_ROOT}/lib:${LIBEVENT_ROOT}/lib:${HWLOC_ROOT}/lib:${CUDA_HOME}/lib64:${GCC_ROOT}/lib64:${GCC_ROOT}/lib"
case ":$LD_LIBRARY_PATH:" in
    *":/public/home/zhangxin/slib:"*) ;;
    *) export LD_LIBRARY_PATH=/public/home/zhangxin/slib:$LD_LIBRARY_PATH ;;
esac
# --- CPATH ---
export CPATH="/public/soft/apps/intel/oneapi/tbb/2021.11/include:${PYTHON_ROOT}/include:${NCURSES_ROOT}/include:${OPENMPI_ROOT}/include:${UCX_ROOT}/include:${PMIX_ROOT}/include:${LIBEVENT_ROOT}/include:${HWLOC_ROOT}/include:${CUDA_HOME}/include:${GCC_ROOT}/include"
# --- CMAKE_PREFIX_PATH ---
export CMAKE_PREFIX_PATH="/public/soft/apps/intel/oneapi/compiler/2024.0:/public/soft/apps/intel/oneapi/tbb/2021.11:${PYTHON_ROOT}/.:${CMAKE_ROOT}/.:${NCURSES_ROOT}/.:${OPENMPI_ROOT}/.:${UCX_ROOT}/.:${PMIX_ROOT}/.:${LIBEVENT_ROOT}/.:${HWLOC_ROOT}/.:${GIT_ROOT}/.:${CUDA_HOME}/.:${GCC_ROOT}/."
# --- PKG_CONFIG_PATH ---
export PKG_CONFIG_PATH="/public/soft/apps/intel/oneapi/compiler/2024.0/lib/pkgconfig:${PYTHON_ROOT}/lib/pkgconfig:${NCURSES_ROOT}/lib/pkgconfig:${OPENMPI_ROOT}/lib/pkgconfig:${UCX_ROOT}/lib/pkgconfig:${PMIX_ROOT}/lib/pkgconfig:${LIBEVENT_ROOT}/lib/pkgconfig:${HWLOC_ROOT}/lib/pkgconfig"
# --- ACLOCAL_PATH ---
export ACLOCAL_PATH="${CMAKE_ROOT}/share/aclocal"
# --- MANPATH ---
export MANPATH="/public/soft/apps/intel/oneapi/compiler/2024.0/share/man:${PYTHON_ROOT}/share/man:${OPENMPI_ROOT}/share/man:${PMIX_ROOT}/share/man:${HWLOC_ROOT}/share/man:${GIT_ROOT}/share/man:${GCC_ROOT}/share/man:/usr/local/man:"
# --- PYTHONPATH: .local 防重复 ---
case ":$PYTHONPATH:" in
    *":/public/home/zhangxin/.local/lib/python3.9/site-packages:"*) ;;
    *) export PYTHONPATH=/public/home/zhangxin/.local/lib/python3.9/site-packages:$PYTHONPATH ;;
esac
# --- misc ---
export EDITOR=vim
# CONDA (zhangxin-snsc) -- 真正的 conda 激活替代 alias 伪装:
# python/pip 由 envs/zhangxin-snsc/bin 软链提供(指向 module python3.9.10),
# 非交互 shell 与脚本中同样生效(不依赖 alias); CONDA_DEFAULT_ENV 判断保证
# 重复 source 幂等; ZHANGXIN_SNSC_READY 供激活钩子引用(钩子不再重复配置)
export ZHANGXIN_SNSC_READY=1
source /public/home/zhangxin/miniconda3/etc/profile.d/conda.sh
if [ "${CONDA_DEFAULT_ENV:-}" != "zhangxin-snsc" ]; then
    conda activate zhangxin-snsc
fi
# USER BIN -- .local/bin 提供 jupyter-lab 等(追加尾部, 防重复, 不干扰 python 解析)
case ":$PATH:" in
    *":/public/home/zhangxin/.local/bin:"*) ;;
    *) export PATH="$PATH:/public/home/zhangxin/.local/bin" ;;
esac
# SOURCE
pushd /public/home/zhangxin/PyQCU
source ./env.sh
popd
# SUMMARY (仅交互式 shell 输出, 避免污染管道/脚本日志)
if [[ $- == *i* ]]; then
    echo "Conda environment activated: $CONDA_DEFAULT_ENV"
    echo "  conda prefix : $CONDA_PREFIX"
    echo "  python       : $(which python 2>/dev/null || echo 'not found')  [$(python --version 2>&1)]"
    echo "  gcc          : $($CC --version 2>/dev/null | head -1 || echo 'not found')"
    echo "  nvcc         : $(which nvcc 2>/dev/null || echo 'not found')  [$(nvcc --version 2>/dev/null | tail -1)]"
    echo "  mpicc        : $(which mpicc 2>/dev/null || echo 'not found')  [$($MPICC --version 2>&1 | head -1)]"
    echo "  cmake        : $(which cmake 2>/dev/null || echo 'not found')  [$(cmake --version 2>&1 | head -1)]"
    echo "  libquda.so   : $(find /public/home/zhangxin/slib -maxdepth 1 -name 'libquda.so' 2>/dev/null | head -1 || echo 'not found')  -> $(readlink /public/home/zhangxin/slib/libquda.so 2>/dev/null || echo '?')"
    echo "  libhdf5.so   : $(find /public/home/zhangxin/slib -maxdepth 1 -name 'libhdf5.so' 2>/dev/null | head -1 || echo 'not found')  -> $(readlink /public/home/zhangxin/slib/libhdf5.so 2>/dev/null || echo '?')"
fi
