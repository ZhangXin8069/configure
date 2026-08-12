# AGENTS.md — _snsc

NSC（超算中心）集群共享配置目录（不部署到 `$HOME`）：

- `vscode-server-sysroot-env.sh` — VS Code Remote Server 在 CentOS 7（自定义 glibc）上的兼容环境设置
- `envs/` — conda 环境目录（`envs/zhangxin-snsc/` 为完整 conda env，依赖内容，不入库、不生成 AGENTS.md）

被 `lib/snsc-v20260705/env.sh` 等版本化配置引用。
