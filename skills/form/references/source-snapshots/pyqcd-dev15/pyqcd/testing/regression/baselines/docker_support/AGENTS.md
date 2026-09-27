# AGENTS.md — agent/docker

GPU 流水线启动器与数据管理枢纽，将实际计算委托给最新 `docker-v*` 版本目录。

| 文件 | 用途 |
|---|---|
| `run_gpu_pipeline.sh` | 一键启动器：`test`/`run`/`check`/`status`/`plots`/`report`/`package`/`clean` |
| `download_beta6.20_mu-0.2770_ms-0.2400_L24x72.sh` | 从集群下载 L24x72 数据（SSH/rsync，222.200.137.16:10023） |
| `pack_beta6.20_mu-0.2770_ms-0.2400_L24x72.sh` | 打包本地数据为便携 tar.gz |
| `README.md` | 完整文档：流水线步骤、配置、数据路径、输出结构 |

## 使用

```bash
cd /root/PyQCD/pyqcd/testing/regression/baselines/docker_support
bash run_gpu_pipeline.sh check      # 环境检查
bash run_gpu_pipeline.sh test       # 单组态快速测试（~3 分钟）
bash run_gpu_pipeline.sh run        # 完整 3 组态运行
bash download_beta6.20_mu-0.2770_ms-0.2400_L24x72.sh --yes --skip-existing
```
