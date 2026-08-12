# AGENTS.md — snsc-v20260705

SNSC 超算中心（Slurm）环境配置 v2026-07-05（当前最新），模块化拆分多个 env 文件，均由 `env.sh` 汇总：

| 文件 | 说明 |
|---|---|
| `env.sh` | 主配置：module purge/load（gcc 10.3.0、cuda 11.4.4、openmpi 4.1.5、intel oneAPI）、PATH/LD_LIBRARY_PATH/PYTHONPATH、source PyQCU env.sh |
| `conda-env.sh` | conda 环境 |
| `crosstool-ng-env.sh` | crosstool-ng 交叉编译工具链 |
| `gperf-env.sh` / `help2man-env.sh` / `texinfo-env.sh` | 构建辅助工具 |
| `sysroot-env.sh` | sysroot 设置 |
| `vscode-server-centos7-env.sh` | VS Code Server（CentOS 7 自定义 glibc/patchelf 兼容） |

分节/版本约定见 `../AGENTS.md`。
