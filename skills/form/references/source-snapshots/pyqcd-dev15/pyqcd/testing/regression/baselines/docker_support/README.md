# Docker — GPU 加速胶子 PDF 验证管线 (Launcher)

本目录包含胶子 PDF 验证管线的启动脚本和数据集管理工具。
`run_gpu_pipeline.sh` 显式委托到冻结基线 `../legacy_pipeline/`。

## 脚本说明

| 脚本 | 用途 |
|------|------|
| `run_gpu_pipeline.sh` | 一键运行 GPU 管线 (test / full / check / status / plots / report / package / clean) |
| `download_beta6.20_mu-0.2770_ms-0.2400_L24x72.sh` | 从集群 (222.200.137.16:10023) 下载 L24x72 系综数据 |
| `pack_beta6.20_mu-0.2770_ms-0.2400_L24x72.sh` | 将本地数据打包为便携 tar.gz 归档 (含自解压脚本) |

## 快速开始

```bash
# 环境检查
bash run_gpu_pipeline.sh check

# 单组态快速冒烟测试 (跳过 3pt/4pt/报告)
bash run_gpu_pipeline.sh test

# 完整运行（冻结基线，10 组态约 5.2 h；可加透传参数）
bash run_gpu_pipeline.sh run
bash run_gpu_pipeline.sh run --conf-ids 6250,6450 --skip-4pt

# 下载数据 (如路径缺失)
bash download_beta6.20_mu-0.2770_ms-0.2400_L24x72.sh --yes --skip-existing
```

## Configuration

| Parameter | Value |
|-----------|-------|
| Ensemble | beta6.20_mu-0.2770_ms-0.2400_L24x72 (L24x72) |
| Lattice | 72×24³, β=6.2 |
| Lattice spacing | a=0.1053 fm |
| Configs | [6250] (Nconf=1) |
| Momentum | P=(0,0,-2) |
| Nev / Nev1 | 100 / 100 |
| Element | _Cg5g4 |
| delta_z | 24 |
| Jackknife | True |
| GPU precision | **complex64** |
| OPE mode | **FROM SCRATCH (GPU)** |
| VVV / Wick | **GPU (CuPy einsum)** |
| F_{μν} | **GPU (CuPy plaquette_clover)** |

## Data Paths

| Data | Path |
|------|------|
| Eigenvectors | `/public/group/lqcd/eigensystem/beta6.20_mu-0.2770_ms-0.2400_L24x72/{conf_id}/` |
| Perambulators | `/public/group/lqcd/perambulators/beta6.20_mu-0.2770_ms-0.2400_L24x72/light/{conf_id}/` |
| Gauge configs | `/public/group/lqcd/configurations/CLOVER/beta6.20_mu-0.2770_ms-0.2400_L24x72/` |
| OPE | *Computed from scratch (GPU)* |

## 管线步骤

| 步骤 | 描述 | GPU 加速 | 典型耗时 |
|------|------|----------|---------|
| 0 | 环境检查 (CUDA/CuPy, Python 模块, 数据路径) | — | <1s |
| 1 | 质子 2pt 蒸馏 | VVV, Wick 收缩 | ~125s |
| 2 | OPE 从头计算 | F_{μν}, Wilson 线, 缩并 | ~42s |
| 3 | huangcl 比率分析 | Jackknife 重采样 | ~3s |
| 4 | 最终报告 (Markdown + LaTeX) | — | <1s |

## 输出结构

```
output_YYYYMMDD_HHMMSS/
├── run.log                    # 完整日志
├── timing.jsonl               # 每步耗时与显存
├── final_report.md            # Markdown 综合报告
├── gpu_info.json              # GPU 设备信息
├── run_config.json            # 运行配置
├── data/
│   ├── eigenvalues_Nev100.npy
│   ├── conf_6250/             # VVV, F_{μν}×3, OPE×3, 2pt, meff
│   ├── conf_6450/
│   └── conf_6650/
└── plots/
    ├── ratio.png
    ├── ratio_diagnostics.png
    ├── effective_mass.png
    └── field_strength_diagnostics.png
```

## 依赖

- Python 3.8+
- CuPy (CUDA 12.x)
- numpy, scipy, matplotlib
- opt_einsum (可选)
- SSH 访问集群 (仅 `download_*.sh` 需要)
