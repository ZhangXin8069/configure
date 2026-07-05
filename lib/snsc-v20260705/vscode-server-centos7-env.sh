# > https://github.com/MikeWang000000/vscode-server-centos7
# wget https://github.com/MikeWang000000/vscode-server-centos7/releases/download/1.127.0/vscode-server_1.127.0_x64.tar.gz
mkdir -p ~/.vscode-server
tar xzf /public/home/zhangxin/external-libraries/vscode-server_1.127.0_x64.tar.gz -C ~/.vscode-server --strip-components 1
~/.vscode-server/code-latest --patch-now