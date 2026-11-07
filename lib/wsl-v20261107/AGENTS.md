# AGENTS.md — wsl-v20261107

Windows + WSL 2 开发环境配置 v2026-11-07（当前最新）。含 `env.sh` 与 `setup.md`：

| 文件 | 说明 |
|---|---|
| `env.sh` | 机器级环境快照：`CUDA_PATH`、`CPLUS_INCLUDE_PATH`、NVVM `PATH`、`HDF5_MPI`/`HDF5_DIR`（变量以双引号包裹，`iftop` 使用 `${HOME}`），以及注释保留的 netwatch 权限块；部署为 `~/env.sh`。 |
| `setup.md` | 从 Windows 安装 Ubuntu 26.04、迁移到 `F:\WSL`、Miniforge/conda 工具链、源码依赖、QUDA/PyQUDA、Windows 数据盘、StarVPN 与 OpenSSH 的完整步骤。 |

宿主机 WSL 生命周期（`.wslconfig`、`/etc/wsl.conf`、导入导出、磁盘压缩）见 `../_wsl/setup.md`；三层环境加载见 `../_env/setup.md`。分节/版本约定见 `../AGENTS.md`。
