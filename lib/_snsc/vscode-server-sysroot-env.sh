# > https://code.visualstudio.com/docs/remote/faq#_can-i-run-vs-code-server-on-older-linux-distributions
# Path to the dynamic linker in the sysroot (used for --set-interpreter option with patchelf)
export VSCODE_SERVER_CUSTOM_GLIBC_LINKER=/public/home/zhangxin/external-libraries/sysroot/lib/ld-linux-x86-64.so.2
# Path to the library locations in the sysroot (used as --set-rpath option with patchelf)
export VSCODE_SERVER_CUSTOM_GLIBC_PATH=/public/home/zhangxin/external-libraries/sysroot/usr/lib:/public/home/zhangxin/external-libraries/sysroot/lib
# Path to the patchelf binary on the remote host
export VSCODE_SERVER_PATCHELF_PATH=/public/home/zhangxin/external-libraries/sysroot/usr/bin/patchelf