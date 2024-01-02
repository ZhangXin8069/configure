# init
_HOME=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
echo 'HOME:'${_HOME}
_NAME=$(basename "$0")
name='test'
work_name="test"
tmp_name="tmp"
work_path=${_HOME}/${work_name}
tmp_path=${_HOME}/${tmp_name}

# mkdir
mkdir ${_HOME}/bin -p
mkdir ${_HOME}/include -p
mkdir ${_HOME}/lib -p
mkdir ${_HOME}/scripts -p
mkdir ${_HOME}/test -p
mkdir ${_HOME}/tmp -p
# source
source ${_HOME}/tmp/scripts.sh
# source ${_HOME}/lib/.bashrc

# do
## export
MPI_HOME=/usr/local/openmpi
export PATH=${MPI_HOME}/bin:$PATH
export LD_LIBRARY_PATH=${MPI_HOME}/lib:$LD_LIBRARY_PATH
export MANPATH=${MPI_HOME}/share/man:$MANPATH
CUDA_HOME=/usr/local/cuda
export PATH=${CUDA_HOME}/bin:$PATH
export LD_LIBRARY_PATH=${CUDA_HOME}/lib:$LD_LIBRARY_PATH
export MANPATH=${CUDA_HOME}/share/man:$MANPATH
export TERM=xterm-256color
export PATH=$PATH:${_HOME}/bin

##alias
# alias noita="pushd /home/zhangxin/Game/Noita\ v20230311 && wine noita.exe && popd"
# alias dwarf="pushd /home/zhangxin/Game/Dwarf\ Fortress && wine Dwarf\ Fortress.exe && popd"
# alias rain="pushd /home/zhangxin/Game/Rain\ World\ v1.9.07b && wine RainWorld.exe && popd"
# alias oriwotw="pushd /home/zhangxin/Game/Ori\ and\ the\ Will\ of\ the\ Wisps && wine oriwotw.exe && popd"
# alias deadcells="pushd /home/zhangxin/Game/Dead\ Cells2 && wine deadcells.exe  && popd"
# alias space="pushd /home/zhangxin/Package && wine SpaceSniffer.exe  && popd"
# alias winrar="pushd /home/zhangxin/Package/WinRARPortable && wine WinRARPortable.exe && popd"
# alias matlab="pushd /home/zhangxin/Package/MATLAB/R2023b/bin && bash matlab && popd"

## alisync
#!/bin/bash
#flag_file=${_HOME}/.alisync
#if [ ! -f ${flag_file} ]; then
#  touch ${flag_file}
#  bash ${_HOME}/bin/alisync
#fi

# done

# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
# __conda_setup="$('/home/zhangxin/anaconda3/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
# if [ $? -eq 0 ]; then
#     eval "$__conda_setup"   
# else
#     if [ -f "/home/zhangxin/anaconda3/etc/profile.d/conda.sh" ]; then
#         . "/home/zhangxin/anaconda3/etc/profile.d/conda.sh"
#     else
#         export PATH="/home/zhangxin/anaconda3/bin:$PATH"
#     fi
# fi
# unset __conda_setup
# conda activate computer-nv-qcu
# <<< conda initialize <<<