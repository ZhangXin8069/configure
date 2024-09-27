# BASH
# unset

# EXPORT
export PATH=/usr/local/python/bin:$PATH
export PATH=${HOME}/sbin:$PATH
export PATH=${HOME}/.local/bin:$PATH
export LD_LIBRARY_PATH=${HOME}/slib:$LD_LIBRARY_PATH
export LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH

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
alias firefox="flatpak run org.mozilla.firefox"
alias goldendict="flatpak run io.github.xiaoyifang.goldendict_ng"
alias media_writer="flatpak run org.fedoraproject.MediaWriter"
#########
# EXAMPLE
# http://dict.youdao.com/search?q=%GDWORD%&ue=utf8 # goldendict settings
#########

# SOURCE
pushd ${HOME}/qcu
source ./computer-env.sh
popd
