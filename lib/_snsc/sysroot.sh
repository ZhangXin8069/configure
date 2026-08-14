# Path to the dynamic linker in the sysroot (used for --set-interpreter option with patchelf)
export VSCODE_SERVER_CUSTOM_GLIBC_LINKER=$HOME/.vscode-server/sysroot/lib/ld-linux-x86-64.so.2
# Path to the library locations in the sysroot (used as --set-rpath option with patchelf)
export VSCODE_SERVER_CUSTOM_GLIBC_PATH=$HOME/.vscode-server/sysroot/usr/lib:$HOME/.vscode-server/sysroot/lib
# Path to the patchelf binary on the remote host
export VSCODE_SERVER_PATCHELF_PATH=$HOME/.vscode-server/sysroot/usr/bin/patchelf
