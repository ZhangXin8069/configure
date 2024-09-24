# BASH
# unset

# EXPORT
export PATH=${HOME}/sbin:$PATH
export LD_LIBRARY_PATH=${HOME}/slib:$LD_LIBRARY_PATH

# ALIAS
alias wechat="flatpak run com.tencent.WeChat"
alias wemeet="flatpak run com.tencent.wemeet"
alias qq="flatpak run com.qq.QQ"
alias joplin="flatpak run net.cozic.joplin_desktop"

# SOURCE
pushd ${HOME}/qcu
source ./computer-env.sh
popd
