# AGENTS.md — snsc-v20260817

SNSC 超算中心（Slurm）环境配置 v2026-08-17（当前最新），单文件 `env.sh`：

| 文件 | 说明 |
|---|---|
| `env.sh` | 主配置：module purge/load（gcc 10.3.0、cuda 11.4.4、openmpi 4.1.5、intel oneAPI）、PATH/LD_LIBRARY_PATH/PYTHONPATH、工具链变量（原 activate.d 钩子内容并入，本文件为唯一权威来源）、`conda activate zhangxin-snsc`、`.local/bin` 追加 PATH（jupyter-lab 等）、source PyQCU env.sh |

v20260817 相对 v20260816 的变更：

1. 删除 `alias python="python3.9"` / `alias pip="pip3.9"` 伪装——alias 只在交互式 shell 展开，非交互/脚本/他人套用时 `python` 落回系统旧版（实测 2.7.5）；
2. 新增 `source $HOME/miniconda3/etc/profile.d/conda.sh && conda activate zhangxin-snsc`：zhangxin-snsc 的 `bin/` 软链指向 module python3.9.10；`CONDA_DEFAULT_ENV` 判断保证重复 source 幂等；
3. 新增 `.local/bin` 追加到 PATH 尾部（防重复）——提供 `jupyter-lab` 等可执行文件，修复其命令不可用；
4. 工具链块并入（CC/CXX/FC/CUDA/MPI/CMAKE/PYTHON/GIT 变量、PATH/LD_LIBRARY_PATH/CPATH/CMAKE_PREFIX_PATH/PKG_CONFIG_PATH/MANPATH、.local PYTHONPATH 防重复）——`etc/conda/activate.d/env_vars.sh` 钩子改为**引用式**：设 `ZHANGXIN_SNSC_READY=1` 则钩子立即返回（激活零额外开销），未经 env.sh 直接 `conda activate` 时钩子 `. ~/env.sh` 兜底（`CONDA_DEFAULT_ENV` 判断防递归）；路径不再重复明文，便于移植与套用；
5. 环境摘要（python/gcc/nvcc/mpicc/cmake 版本）仅交互式 shell 输出，避免污染管道/日志。

分节/版本约定见 `../AGENTS.md`。