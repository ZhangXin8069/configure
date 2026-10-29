# AGENTS.md — dcu-v20261020

DCU（DTK 23.10）环境配置 v2026-10-20。包含 `env.sh` 和四卡 Slurm 休眠探针。

- `env.sh`：加载 CMake、devtoolset、HPC-X、GCC 13.3、DTK 23.10，设置 HIP/ROCm、
  gfx906、HDF5、虚拟环境、QUDA 与 PyQCU。
- `sleep.sh`：`kshdnormal` 分区、单节点、4 个 DCU、独占节点，正文休眠 600 秒且未声明
  `--time`；提交前必须补齐时限并核对个人环境路径。
- 配置混合使用多位用户的固定路径，跨账号或跨节点复用前应逐项替换并验证。
