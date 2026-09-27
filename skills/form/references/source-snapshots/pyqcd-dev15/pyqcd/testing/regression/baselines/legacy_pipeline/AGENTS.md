# AGENTS.md — frozen legacy pipeline

**冻结的全量蒸馏 GPU 计算基线（10 组态）**。以 `refer/sush/lqcddb` 为蓝本
（照抄不 import）。实现顶点函数、Wick/动态收缩、关联函数、统计分析和 LaTeX 报告。

**版本身份**：历史标签 v20260805；现仅作为只读回归基线。

## 文件

`config.py`（集中配置）、`lib/`（自包含蒸馏收缩框架）、`compute_vertex.py`（VdV/VVV，x-slice 分解，比单 einsum 快 20×）、`compute_contraction.py`、`compute_ope.py`（donghx 胶子算符：Clover F̃ + Wilson 线）、`analyze.py`、`run_pipeline.py`（9 步，支持 `--run-dir` 续跑）、`report.py`、`utils.py`。

## 运行

```bash
python run_pipeline.py                                           # 全部步骤（10 组态，~5.2h）
python run_pipeline.py --conf-id 6250 --skip-3pt --skip-4pt --skip-report  # 冒烟测试
python run_pipeline.py --run-dir output/output_XXX --steps analysis,plots,report
```

## 关键物理结论（勿重复调试）

- **pn 2pt = 0**：质子(uud)↔中子(udd) 味不守恒，Wick 无有效图。物理正确。
- **质子质量 ~1.12 GeV**（非 1.0）：该系综夸克重（m_π≈0.286），v20260803 得 1.053。平台窗 [6,12] 避免早期激发态污染。
- **OPE 已验证**：与 v20260802 相关系数 1.0。`.lime` 文件有 136 字节 trailer → 数据偏移 = `file_size - expected_bytes - 136`。
- 不相连比值（code_1.py 形式）在 10 组态下噪声大；连通 3pt/2pt 比值 R(τ) 是干净结果（pion P0 ≈ -0.96）。
