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
source ${_HOME}/lib/.bashrc

# do
## export
#eport CPATH=$CPATH:$HOME/lib/
#eport CPATH=$CPATH:$HOME/lib/eigen-3.4.0/
#eport CPATH=$CPATH:$HOME/lib/openmpi-4.1.2/
#eport PATH=$PATH:$HOME/cling/bin/
#eport PYTHONPATH=/home/aistudio/external-libraries:$PYTHONPATH
#eport LD_LIBRARY_PATH=/home/aistudio/external-libraries/quda/build/lib/libquda.so:$LD_LIBRARY_PATH
export TERM=xterm-256color

##alias
alias noita="pushd /home/zhangxin/Game/Noita\ v20230311 && wine noita.exe && popd"
alias dwarf="pushd /home/zhangxin/Game/Dwarf\ Fortress && wine Dwarf\ Fortress.exe && popd"
alias rain="pushd /home/zhangxin/Game/Rain\ World\ v1.9.07b && wine RainWorld.exe && popd"
alias oriwotw="pushd /home/zhangxin/Game/Ori\ and\ the\ Will\ of\ the\ Wisps && wine oriwotw.exe && popd"
alias deadcells="pushd /home/zhangxin/Game/Dead\ Cells2 && wine deadcells.exe  && popd"
alias space="pushd /home/zhangxin/Packages && wine SpaceSniffer.exe  && popd"
alias winrar="pushd /home/zhangxin/Packages/WinRARPortable && wine WinRARPortable.exe && popd"
alias matlab="pushd /home/zhangxin/Packages/MATLAB/R2023b/bin && bash matlab && popd"

# done
