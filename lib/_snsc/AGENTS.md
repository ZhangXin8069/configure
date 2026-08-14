# AGENTS.md — _snsc

SNSC（超算中心）集群共享配置目录（不部署到 `$HOME`）：

- `sysroot.sh` — VS Code Remote Server 在 CentOS 7（自定义 glibc）上的兼容环境变量（链接器/LD 路径/patchelf）
- `vscode-sysroot-ursetto-env.sh` — 一键安装脚本：解压 sysroot tgz 到 `~/.vscode-server` 并 source 配置
- `vscode-sysroot-x86_64-linux-gnu.tgz` — ursetto vscode-sysroot 预编译 sysroot（31MB，已入库）
- `envs/` — conda 环境目录（`envs/zhangxin-snsc/` 为完整 conda env，依赖内容，不入库、不生成 AGENTS.md）

被 `lib/snsc-v20260705/env.sh` 等版本化配置引用。
