# BASH
# unset

# EXPORT
export PATH=/usr/local/python/bin:$PATH
export PATH=${HOME}/sbin:$PATH
export PATH=${HOME}/.local/bin:$PATH
export LD_LIBRARY_PATH=${HOME}/slib:$LD_LIBRARY_PATH
export LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH
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

# ALIAS
#########
# EXAMPLE
# sudo apt install flatpak
# flatpak install flathub
# flatpak run com.tencent.WeChat
# flatpak run com.tencent.WeChat
# in ${HOME}/.local/share/flatpak/exports/bin
# in /var/lib/flatpak/exports/bin
#########
# TIPS
# flatpak install flatseal # flatpak settings
#########
alias wechat="flatpak run com.tencent.WeChat"
alias wemeet="flatpak run com.tencent.wemeet"
alias qq="flatpak run com.qq.QQ"
alias qqmusic="flatpak run com.qq.QQmusic"
alias joplin="flatpak run net.cozic.joplin_desktop"
# alias code="flatpak run com.visualstudio.code" # recommend to install by dpkg(deb format).
alias krita="flatpak run org.kde.krita"
# alias firefox="flatpak run org.mozilla.firefox" # recommend to install with 'sudo apt install firefox'
alias goldendict="flatpak run io.github.xiaoyifang.goldendict_ng"
alias media_writer="flatpak run org.fedoraproject.MediaWriter"
# steam # recommend to install with 'sudo apt install steam-installer' first, then 'steam'
alias clash="flatpak run io.github.Fndroid.clash_for_windows"
#########
# EXAMPLE
# http://dict.youdao.com/search?q=%GDWORD%&ue=utf8 # goldendict settings
#########

# SOURCE
pushd ${HOME}/qcu
source ./usb-env.sh
popd
