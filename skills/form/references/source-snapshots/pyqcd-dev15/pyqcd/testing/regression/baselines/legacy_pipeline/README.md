# 冻结蒸馏 GPU 计算基线

生产级 GPU (CUDA) 格点QCD蒸馏管线，实现从顶点函数到关联函数再到统计分析的完整流程。

**历史版本标识**: v20260805。以 `refer/sush/lqcddb` 为蓝本（照抄不 import）的自包含 `lib/` +
集中式 `config.py` + Wick/动态收缩引擎 + 全关联函数集（2pt pp/pn、OPE、3pt PJN、4pt PJNNJNp）+
code_1.py 形式的统计输出 + LaTeX 物理报告。

## 与 docker-v20260803 的对照

| 项目 | v20260803 | v20260805 |
|------|-----------|-----------|
| 组态数 | 3 (6250,6450,6650) | **10** (6250…8050) |
| Nev | 50 (GPU测试) | **100** (全量) |
| 精度 | complex64 | complex64（可切 complex128） |
| 2pt | pp + pion (P0/P2) | **pp + pn + pion** (P0/P2) |
| 3pt / 4pt | 3pt (ratio_analysis) | **3pt PJN + 4pt PJNNJNp** |
| OPE | 未计算 | **donghx 胶子算符** (Clover F̃ + Wilson 线) |
| 统计 | Jackknife/meff/ratio | **Jackknife/meff/ratio_3p + code_1.py 不相连比值拟合** |
| 报告 | physics_report.tex | **physics_report.tex（自动生成数值表）** |

## 文件

| 文件 | 作用 |
|------|------|
| `config.py` | 集中配置（系综、组态、动量、算符、OPE、路径） |
| `utils.py` | 日志、计时、GPU 显存、数组 I/O |
| `lib/` | 自包含蒸馏收缩框架（lqcddb 快照，照抄不 import） |
| `compute_vertex.py` | VdV/VVV 顶点函数（GPU，x-slice 分解） |
| `compute_contraction.py` | Wick + 动态收缩：2pt/3pt/4pt 关联函数 |
| `compute_ope.py` | 不相连胶子算符（donghx 算法） |
| `analyze.py` | Jackknife / meff / ratio_3p / code_1.py 拟合与绘图 |
| `run_pipeline.py` | 主调度器（9 步） |
| `report.py` | 自动生成并编译 LaTeX 报告 |

## 运行

```bash
cd /root/PyQCD/pyqcd/testing/regression/baselines/legacy_pipeline

# 快速冒烟测试（单组态，跳过 3pt/4pt/报告）
python run_pipeline.py --conf-id 6250 --skip-3pt --skip-4pt --skip-report

# 完整运行（10 组态，全部步骤）
python run_pipeline.py

# 选择步骤 / 截断 Nev / 双精度
python run_pipeline.py --steps vertex,2pt,analysis
python run_pipeline.py --Nev1 60
python run_pipeline.py --precision complex128

# 生成并编译 LaTeX 报告（并复制到 agent/logs）
python report.py --run-dir output/output_YYYYMMDD_HHMMSS --out /root/PyQCD/logs
```

## 输出

```
output/output_YYYYMMDD_HHMMSS/
├── data/conf{id}/        VdV_mom.npy, VVV_mom.npy, corr_{pp|pn|pi}_{P0|P2}.npy,
│                          {proton|pion}_{P0|P2}_3pt.npy, pjnnjnp_4pt.npy,
│                          ops_mu{μ}_nu{ν}_dz24_conf{id}.npz, ope_combined.npy
├── data/analysis/        meff_{ch}_mean/err.npy, ratio_{ch}_mean/err.npy
├── analysis/disconnected/ ratio_*.npy, 0_fit_data.npz, 1_fit_report.txt, plots
├── plots/                meff/correlators/ratio 图
├── run_config.json       analysis_summary.json   physics_report.tex/.pdf
└── (日志同时写入 /root/PyQCD/logs/)
```

## 物理验证目标

| 粒子 | P | 期望 E (GeV) |
|------|---|--------------|
| pion | (0,0,0) | ~0.3 |
| pion | (0,0,2) | ~0.98 (√(0.3²+0.98²)) |
| proton | (0,0,0) | ~1.0 |
| proton | (0,0,2) | ~1.4 (√(1.0²+0.98²)) |
