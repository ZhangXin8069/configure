# init
_HOME=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
echo 'HOME:'${_HOME}
# export
## zhangxin
export LD_LIBRARY_PATH=${_HOME}/lib:$LD_LIBRARY_PATH # if any
export TERM=xterm-256color
# export PYTHONPATH=${HOME}/.local/lib/python3.10/site-packages # wsl
export PYTHONPATH=${_HOME}/lib:${PYTHONPATH}
export LD_LIBRARY_PATH="/usr/lib/wsl/lib:${LD_LIBRARY_PATH}" # wsl
## openmpi
MPI_HOME=/usr/local/openmpi
export PATH=${MPI_HOME}/bin:$PATH
export LD_LIBRARY_PATH=${MPI_HOME}/lib:$LD_LIBRARY_PATH
export MPI_INCLUDE_PATH=${MPI_HOME}/include:$MPI_INCLUDE_PATH
export MANPATH=${MPI_HOME}/share/man:$MANPATH
## cuda
CUDA_HOME=/usr/local/cuda
export PATH=${CUDA_HOME}/bin:$PATH
export LD_LIBRARY_PATH=${CUDA_HOME}/lib:$LD_LIBRARY_PATH
export CUDA_INCLUDE_PATH=${CUDA_HOME}/include:$CUDA_INCLUDE_PATH
export MANPATH=${CUDA_HOME}/share/man:$MANPATH