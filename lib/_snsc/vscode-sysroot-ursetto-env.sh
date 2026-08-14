# > https://code.visualstudio.com/docs/remote/faq#_can-i-run-vs-code-server-on-older-linux-distributions
# > https://github.com/ursetto/vscode-sysroot
mkdir -p ~/.vscode-server
tar zxf /public/home/zhangxin/configure/lib/_snsc/vscode-sysroot-x86_64-linux-gnu.tgz -C ~/.vscode-server
cp /public/home/zhangxin/configure/lib/_snsc/sysroot.sh ~/.vscode-server/sysroot.sh
echo 'source ~/.vscode-server/sysroot.sh' >> ~/.bashrc
