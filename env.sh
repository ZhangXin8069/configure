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

# do
## export
### zx
export TERM=xterm-256color
export PATH=$PATH:${_HOME}/bin
export PATH=$PATH:${HOME}/.local/bin
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
alias nvvp="nvvp -vm /usr/lib/jvm/java-8-openjdk-amd64/jre/bin/java" # strange, never mind.
## alias
alias python="python3"
# alias noita="pushd /home/zhangxin/Game/Noita\ v20230311 && wine noita.exe && popd"
# alias dwarf="pushd /home/zhangxin/Game/Dwarf\ Fortress && wine Dwarf\ Fortress.exe && popd"
# alias rain="pushd /home/zhangxin/Game/Rain\ World\ v1.9.07b && wine RainWorld.exe && popd"
# alias oriwotw="pushd /home/zhangxin/Game/Ori\ and\ the\ Will\ of\ the\ Wisps && wine oriwotw.exe && popd"
# alias deadcells="pushd /home/zhangxin/Game/Dead\ Cells2 && wine deadcells.exe  && popd"
# alias space="pushd /home/zhangxin/Package && wine SpaceSniffer.exe  && popd"
alias clash="pushd /home/zhangxin/Package/Clash\ for\ Windows && ./cfw && popd"
alias joplin="pushd /home/zhangxin/Package/Joplin && ./Joplin.AppImage && popd"
alias krita="pushd /home/zhangxin/Package/Krita && ./krita.appimage && popd"
alias onenote="pushd /home/zhangxin/Package/OneNote && ./onenote-desktop.AppImage && popd"
# alias winrar="pushd /home/zhangxin/Package/WinRARPortable && wine WinRARPortable.exe && popd"
# alias matlab="pushd /home/zhangxin/Package/MATLAB/R2023b/bin && bash matlab && popd"



