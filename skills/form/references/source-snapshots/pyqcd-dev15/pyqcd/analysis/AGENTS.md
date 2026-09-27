# AGENTS.md — pyqcd/analysis

Jackknife/Bootstrap/meff/ratio_3pt、disconnected/3pt 编排、色散拟合（`_dispersion.py`）、
c0 裸矩阵元提取（`_ratio_fit.py`，zengch 逻辑移植）、
数据分析与作图功能链（独立实现，功能对齐 refer/huangcl 02/03/04/05/06 步）。

## 功能链模块

| 模块 | 功能（参考脚本） | 顶层入口 |
|---|---|---|
| `_ana_3dir.py` | 05：三方向 ratio/corr2 → meff/相关矩阵/直方图 | `analyze_3dir` |
| `_plots.py` | 图表工具全集（plot_errbar/scatter/hist + single/multi + 10 色 + 峰值内存） | — |
| `_fitter.py` | calc_chi2(_dof)/fit（lsqfit 封装，prior 优先）/FitParams/make_summary_table | — |
| `_ratio2pt.py` | 02：2pt+OPE → 真空扣除 ratio → 逐 z 拟合 → ratio/c0/chi2 图 | `run_ratio2pt` |
| `_ana_ratio.py` | 03：纯画图（单 fit 图/对比图/nofit 图，读 02 输出） | `ana_ratio_plot_all` |
| `_bare_matrix.py` | 03_bare：三方向（动量置换+OPE 组合）ratio → 平均 → 拟合 → 图 | `run_bare_matrix` |
| `_proton_energy.py` | 04：2pt → corr2 → E0 拟合 → eff_mass 图（unit=0.197/a GeV） | `run_energy` |
| `_fh.py` | 06：6 方向 ratio 平均 → FH 变换（多 nex）→ 常数拟合 → FH/参数/对比图 | `run_fh` |

## 约定

- 统计基元 sem/resample/cov_mat/model_ratio 复用 `_disconnected.py`；图表一律走 `_plots.py`
  （matplotlib 函数内延迟导入 + `use('Agg')`）；报告 ASCII 表用 `_fitter.make_summary_table`
  （不引入 prettytable 依赖）。
- 数据路径全部参数化（data_root 注入），中间产物（ratio/corr2/fit npz/report txt/png）可读写；
  run_ratio2pt/run_bare_matrix 支持 parts=(start,end) 断点续跑。
- 测试：`bash data/from-logs/logs/test0_{ratio,anaratio,bare,energy,fh}/run-local.sh`
  （test12 风格：makedata 合成物理可解析数据 → verify 断言产物/形状/参数恢复）。
`_analyse.py` 增 dis_connect disconnected 矩阵元构造（PFF/PDF）与分组聚合基元
mean/sum_over_array_of_list（take+stack 等价实现）。
