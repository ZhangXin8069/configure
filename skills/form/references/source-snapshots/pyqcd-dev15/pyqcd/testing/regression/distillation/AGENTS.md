# AGENTS.md — pyqcd/testing/regression/distillation

**test0** —— pyqcd 全量蒸馏管线一致性测试套件（参考 /root/PyQCU/logs/test12 形式）。
调用 pyqcd 包复现冻结基线
`pyqcd/testing/regression/baselines/legacy_pipeline/output/output_20260802_120104`
的全量结果：中间数据 + 图表 + LaTeX 报告完整保存、逐项数值一致。

## 运行

```bash
python -m pyqcd.testing.regression.distillation.main env
python -m pyqcd.testing.regression.distillation.main run --conf-ids 6250
python -m pyqcd.testing.regression.distillation.main run
python -m pyqcd.testing.regression.distillation.main verify --run-dir <run>
python -m pyqcd.testing.regression.distillation.main check --run-dir <run>
bash pyqcd/testing/regression/distillation/run-local.sh
TEST0_SMOKE=1 bash pyqcd/testing/regression/distillation/run-local.sh
```

## 约定

- **版本目录**：`artifacts/run_<YYYYMMDDHHMM>/`，一次运行一个版本目录，
  同名产物跨环境可直接 diff/叠图；`--outdir` > `$TEST0_OUTDIR` > `v<ts>/` 优先级。
- **main.py 只含测试/编排代码**：计算全部委托 `pyqcd.pipeline.run_pipeline`（`_steps.py`），
  无核心计算逻辑。
- 输入数据路径参考 `../baselines/docker_support/README.md`。
- 一致性容差：中间数据 rel < 1e-6（complex64）、分析数组/拟合参数 rel < 1e-8。
- `verify` 只读基线磁盘数据（np.load 比对），不 import 冻结基线代码。

## 产物结构（与基线 output_20260802_120104 一致）

```
v<ts>/
├── env.json  run_config.json  run-local-*.log  test0_verify.json  test0_collect.json
├── data/conf{id}/        VdV/VVV_mom, corr_*, ops_*.npz, ope_combined, *_3pt, pjnnjnp_4pt
├── data/analysis/        meff/corr/ratio_{had}_{mom}_{mean,err}.npy
├── analysis/disconnected/  ratio_*.npy, 0_fit_data.npz, 1_fit_report.txt, c0/chi2/ratio png
├── plots/                meff_all_channels / correlators_all_channels / ratio_3pt_all_channels.png
├── physics_report.tex/pdf/log/out/aux/toc
└── analysis_summary.json
```
