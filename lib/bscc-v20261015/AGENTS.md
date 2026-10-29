# AGENTS.md — bscc-v20261015

BSCC HPC 环境配置 v2026-10-15。包含环境入口 `env.sh` 和一个 Slurm 休眠探针。

- `env.sh`：加载 GCC 11.3、CUDA 12.4、cuDNN、NCCL、OpenMPI、conda `qcu`、HDF5、
  PyQCU 与 PyQuda 环境变量；多数安装命令保留为注释，便于复现。
- `sleep.sh`：单 GPU、5 分钟 Slurm 模板，正文执行 `sleep 600s`。提交前应核对时限与
  脚本内硬编码的集群用户/仓库路径，避免作业超时或加载错误环境。
- 本目录只描述当前集群配置，不保证模块名和固定路径可迁移到其他机器。
