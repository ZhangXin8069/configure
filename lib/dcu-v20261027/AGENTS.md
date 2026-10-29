# AGENTS.md — dcu-v20261027

DCU（DTK 23.10）环境配置 v2026-10-27。包含环境入口和两个 Slurm 休眠探针。

- `env.sh`：加载 Git、CMake、devtoolset、HPC-X、GCC 13.3、DTK 23.10，设置 HIP/ROCm、
  gfx906、HDF5、QUDA、虚拟环境与 PyQCU。
- `sleep.sh`：四卡、独占节点模板；`1dcu_sleep.sh`：单卡模板，声明 10 分钟时限。
- 两个作业都 source 集群固定用户环境，且 `sleep.sh` 未声明时限；提交前应改为当前账号路径
  并补齐 `--time`，同时复核 `1dcu_sleep.sh` 的 `--gres` 参数格式。
