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
#### refer to https://blog.csdn.net/qq_46753404/article/details/116240081
## alias
alias noita="pushd /home/zhangxin/Game/Noita\ v20230311 && wine noita.exe && popd"
alias dwarf="pushd /home/zhangxin/Game/Dwarf\ Fortress && wine Dwarf\ Fortress.exe && popd"
alias rain="pushd /home/zhangxin/Game/Rain\ World\ v1.9.07b && wine RainWorld.exe && popd"
alias oriwotw="pushd /home/zhangxin/Game/Ori\ and\ the\ Will\ of\ the\ Wisps && wine oriwotw.exe && popd"
alias deadcells="pushd /home/zhangxin/Game/Dead\ Cells2 && wine deadcells.exe  && popd"
alias space="pushd /home/zhangxin/Package && wine SpaceSniffer.exe  && popd"
alias clash="pushd /home/zhangxin/Package/Clash\ for\ Windows && ./cfw && popd"
alias joplin="pushd /home/zhangxin/Package/Joplin && ./Joplin.AppImage && popd"
alias krita="pushd /home/zhangxin/Package/Krita && ./krita.appimage && popd"
alias onenote="pushd /home/zhangxin/Package/OneNote && ./onenote-desktop.AppImage && popd"
# alias winrar="pushd /home/zhangxin/Package/WinRARPortable && wine WinRARPortable.exe && popd"
# alias matlab="pushd /home/zhangxin/Package/MATLAB/R2023b/bin && bash matlab && popd"



