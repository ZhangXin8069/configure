# AGENTS.md — dcu-v20250825

AMD DCU 环境配置 v2025-08-25：

- `env.sh` — 模块加载（DTK 编译器、GCC、OpenMPI、conda）与导出
- `openmpi_bind_mlnx.sh` — Mellanox InfiniBand 的 OpenMPI 绑定脚本
- `_salloc.newlarge.sh` / `_salloc.onesitelarge.sh` — Slurm 交互作业模板
- `_sbatch.newlarge.sh` / `_sbatch.onesitelarge.sh` — Slurm 批处理作业模板
- `_stop.sh` — 取消作业

分节/版本约定见 `../AGENTS.md`。
